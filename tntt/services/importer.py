"""Nhập danh sách thiếu nhi từ Excel (.xlsx/.xls) hoặc CSV.

Quy trình: đọc bảng -> nhận diện/ánh xạ cột -> lập kế hoạch (kiểm lỗi, trùng,
thêm mới/cập nhật) -> người dùng xem trước -> áp dụng trong MỘT giao dịch.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy import select

from .. import constants as C
from ..db import session_scope
from ..models import Branch, ClassGroup, SchoolYear, Student
from ..security import P_STUDENTS_IMPORT, Actor
from ..textutil import clean_name, normalize_code, parse_date, search_key, split_saint_name, title_name
from . import audit, org
from .students import StudentInput, _apply, set_enrollment, validate_input

# field -> (nhãn, các tên cột thường gặp, viết không dấu)
FIELDS: dict[str, tuple[str, list[str]]] = {
    "code": ("Mã thiếu nhi", ["id", "ma", "ma tn", "ma thieu nhi", "ma so", "ma hs", "ma hoc sinh", "ma doan sinh", "code", "msts"]),
    "saint_name": ("Tên Thánh", ["ten thanh", "thanh", "thanh danh", "bon mang", "ten thanh bon mang"]),
    "full_name": ("Họ và tên", ["ho va ten", "ho ten", "ho ten thieu nhi", "ten thieu nhi", "name", "full name", "ho va ten thieu nhi", "ten"]),
    "family_name": ("Họ (và tên đệm)", ["ho", "ho dem", "ho va ten dem", "ho va dem"]),
    "given_name": ("Tên (khi tách cột Họ/Tên)", []),
    "birth_date": ("Ngày sinh", ["ngay sinh", "ns", "sinh ngay", "dob", "birthday", "ngay thang nam sinh"]),
    "gender": ("Giới tính", ["gioi tinh", "phai", "gt", "nam nu", "gender"]),
    "branch": ("Ngành", ["nganh"]),
    "class_name": ("Lớp", ["lop", "lop giao ly", "ten lop", "class"]),
    "team": ("Đội", ["doi", "to", "nhom", "doi nhom"]),
    "year": ("Năm học", ["nam hoc"]),
    "status": ("Tình trạng", ["tinh trang", "trang thai", "status", "tinh trang sinh hoat"]),
    "parent_name": ("Phụ huynh", ["phu huynh", "ten phu huynh", "ho ten phu huynh", "cha me", "ten cha", "ten me", "ho ten cha me"]),
    "parent_phone": ("SĐT phụ huynh", ["sdt", "so dien thoai", "dien thoai", "sdt phu huynh", "phone", "dt"]),
    "note": ("Ghi chú", ["ghi chu", "note"]),
}
IGNORE = "— bỏ qua —"
MAX_ROWS = 5000


def _header_key(value) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", search_key(str(value))).strip()


# ---- Đọc file -----------------------------------------------------------------
def list_sheets(data: bytes, filename: str) -> list[str]:
    name = filename.lower()
    if name.endswith(".csv"):
        return ["CSV"]
    engine = "xlrd" if name.endswith(".xls") else "openpyxl"
    return list(pd.ExcelFile(io.BytesIO(data), engine=engine).sheet_names)


def _read_csv(data: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp1258", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.StringIO(text), sep=None, engine="python", header=None, dtype=str,
                       keep_default_na=False)


def read_raw(data: bytes, filename: str, sheet: str | None = None) -> pd.DataFrame:
    """Đọc toàn bộ ô dạng CHUỖI (không để Excel/pandas làm mất số 0 ở đầu)."""
    name = filename.lower()
    if name.endswith(".csv"):
        raw = _read_csv(data)
    elif name.endswith((".xlsx", ".xlsm", ".xls")):
        engine = "xlrd" if name.endswith(".xls") else "openpyxl"
        raw = pd.read_excel(io.BytesIO(data), sheet_name=sheet or 0, header=None, dtype=str,
                            engine=engine, keep_default_na=False)
    else:
        raise ValueError("Chỉ hỗ trợ file .xlsx, .xls, .csv")
    raw = raw.fillna("").astype(str).map(lambda v: v.strip())
    raw = raw[(raw != "").any(axis=1)]
    raw = raw.loc[:, (raw != "").any(axis=0)]
    if len(raw) > MAX_ROWS + 20:
        raise ValueError(f"File quá lớn (>{MAX_ROWS} dòng). Hãy chia nhỏ file.")
    return raw.reset_index(drop=True)


def detect_header_row(raw: pd.DataFrame) -> int:
    known = {syn for _, syns in FIELDS.values() for syn in syns}
    best, best_score = 0, -1
    for i in range(min(10, len(raw))):
        keys = [_header_key(v) for v in raw.iloc[i].tolist()]
        score = sum(1 for k in keys if k in known)
        if score > best_score:
            best, best_score = i, score
    return best


def table_from_raw(raw: pd.DataFrame, header_row: int) -> pd.DataFrame:
    headers, seen = [], {}
    for j, h in enumerate(raw.iloc[header_row].tolist()):
        h = clean_name(h) or f"Cột {j + 1}"
        if h in seen:
            seen[h] += 1
            h = f"{h} ({seen[h]})"
        else:
            seen[h] = 1
        headers.append(h)
    df = raw.iloc[header_row + 1:].copy()
    df.columns = headers
    return df.reset_index(drop=True)


def auto_map(columns: list[str]) -> dict[str, str]:
    """Trả về {field: tên cột}. Ưu tiên khớp chính xác, sau đó khớp bắt đầu bằng."""
    keys = {c: _header_key(c) for c in columns}
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for exact in (True, False):
        for fld, (_, syns) in FIELDS.items():
            if fld in mapping:
                continue
            for col, key in keys.items():
                if col in used:
                    continue
                hit = key in syns if exact else any(key.startswith(s + " ") for s in syns if len(s) > 2)
                if hit:
                    mapping[fld] = col
                    used.add(col)
                    break
    # Tách cột "Họ" + "Tên": cột "Tên" đang bị hiểu là họ tên đầy đủ -> chuyển thành tên riêng
    if "family_name" in mapping and "full_name" in mapping and keys[mapping["full_name"]] == "ten":
        mapping["given_name"] = mapping.pop("full_name")
    return mapping


# ---- Lập kế hoạch ---------------------------------------------------------------
@dataclass
class ImportOptions:
    split_saint: bool = False
    pad_code_width: int = 0
    auto_code: bool = True
    title_case: bool = False
    update_existing: bool = True


@dataclass
class PlanRow:
    row_no: int
    data: StudentInput
    class_name: str | None = None
    branch: str | None = None
    team: str | None = None
    year: str | None = None
    action: str = "create"  # create | update | unchanged | error
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)


@dataclass
class ImportPlan:
    rows: list[PlanRow]

    def counts(self) -> dict[str, int]:
        out = {"create": 0, "update": 0, "unchanged": 0, "error": 0}
        for r in self.rows:
            out[r.action] = out.get(r.action, 0) + 1
        return out

    def to_frame(self) -> pd.DataFrame:
        labels = {"create": "Thêm mới", "update": "Cập nhật", "unchanged": "Không đổi", "error": "Lỗi"}
        return pd.DataFrame([{
            "Dòng": r.row_no, "Xử lý": labels[r.action], "Mã": r.data.code, "Tên Thánh": r.data.saint_name or "",
            "Họ và tên": r.data.full_name, "Ngày sinh": r.data.birth_date.strftime("%d/%m/%Y") if r.data.birth_date else "",
            "Ngành": r.branch or "", "Lớp": r.class_name or "", "Đội": r.team or "",
            "Ghi chú kiểm tra": "; ".join(r.errors + r.warnings + r.changes),
        } for r in self.rows])


_GENDER = {"nam": "M", "m": "M", "male": "M", "trai": "M", "nu": "F", "f": "F", "female": "F", "gai": "F"}
_STATUS = {search_key(v): k for k, v in C.STUDENT_STATUS_LABELS.items()} | {
    "dang hoc": "active", "active": "active", "nghi": "inactive", "tam nghi": "inactive", "chuyen": "moved"}


def build_plan(df: pd.DataFrame, mapping: dict[str, str], options: ImportOptions) -> ImportPlan:
    def cell(row, fld) -> str:
        col = mapping.get(fld)
        return clean_name(row[col]) if col and col in row else ""

    if "full_name" not in mapping and not ("family_name" in mapping and "given_name" in mapping):
        raise ValueError("Cần chọn cột 'Họ và tên' (hoặc cả hai cột 'Họ' và 'Tên').")
    if "code" not in mapping and not options.auto_code:
        raise ValueError("Cần chọn cột 'Mã thiếu nhi' hoặc bật tự sinh mã.")

    with session_scope() as s:
        existing = {st.code: st for st in s.scalars(select(Student)).all()}
        known_years = set(s.scalars(select(SchoolYear.name)).all())
    from .students import next_code

    auto_counter = None
    rows: list[PlanRow] = []
    seen_codes: dict[str, int] = {}
    for idx, row in df.iterrows():
        row_no = int(idx) + 2  # +1 vì header, +1 vì Excel đếm từ 1 (ước lượng)
        errors, warnings = [], []
        full = cell(row, "full_name") or " ".join(p for p in (cell(row, "family_name"), cell(row, "given_name")) if p)
        saint = cell(row, "saint_name")
        if options.split_saint and not saint and full:
            saint, rest = split_saint_name(full)
            full = rest if saint else full
        if options.title_case:
            full, saint = title_name(full), title_name(saint)
        code = normalize_code(cell(row, "code"))
        if code and options.pad_code_width and code.isdigit():
            code = code.zfill(options.pad_code_width)
        if not code and options.auto_code and full:
            if auto_counter is None:
                auto_counter = next_code()
            else:
                auto_counter = _increment(auto_counter)
            while auto_counter in existing or auto_counter in seen_codes:
                auto_counter = _increment(auto_counter)
            code = auto_counter
            warnings.append("Tự sinh mã")
        birth = None
        raw_birth = cell(row, "birth_date")
        if raw_birth:
            try:
                birth = parse_date(raw_birth)
            except ValueError as exc:
                errors.append(str(exc))
        gender = _GENDER.get(search_key(cell(row, "gender")), None) if cell(row, "gender") else None
        status_raw = cell(row, "status")
        status = _STATUS.get(search_key(status_raw), "active") if status_raw else "active"
        if status_raw and search_key(status_raw) not in _STATUS:
            warnings.append(f"Tình trạng '{status_raw}' không rõ -> Đang sinh hoạt")
        year = cell(row, "year") or None
        if year and year not in known_years:
            errors.append(f"Năm học '{year}' chưa có trong hệ thống")

        data = StudentInput(code=code, full_name=full, saint_name=saint or None, birth_date=birth,
                            gender=gender, parent_name=cell(row, "parent_name") or None,
                            parent_phone=cell(row, "parent_phone") or None, note=cell(row, "note") or None,
                            status=status).normalized()
        if not any([data.code, data.full_name]):
            continue  # dòng trống/tổng kết
        errors += validate_input(data)
        if data.code in seen_codes:
            errors.append(f"Trùng mã với dòng {seen_codes[data.code]} trong file")
        elif data.code:
            seen_codes[data.code] = row_no

        plan_row = PlanRow(row_no, data, cell(row, "class_name") or None, cell(row, "branch") or None,
                           cell(row, "team") or None, year, errors=errors, warnings=warnings)
        if errors:
            plan_row.action = "error"
        elif data.code in existing:
            if not options.update_existing:
                plan_row.action = "unchanged"
                plan_row.warnings.append("Đã có trong hệ thống – bỏ qua (chế độ chỉ thêm mới)")
            else:
                plan_row.changes = _diff(existing[data.code], data)
                plan_row.action = "update" if plan_row.changes or plan_row.class_name else "unchanged"
                if plan_row.changes and search_key(existing[data.code].full_name) != search_key(data.full_name):
                    plan_row.warnings.append(f"Tên khác dữ liệu cũ ('{existing[data.code].full_name}') – kiểm tra kỹ")
        rows.append(plan_row)
    return ImportPlan(rows)


def _increment(code: str) -> str:
    m = re.match(r"^(.*?)(\d+)$", code)
    if not m:
        return code + "1"
    prefix, num = m.groups()
    return f"{prefix}{int(num) + 1:0{len(num)}d}"


_DIFF_FIELDS = {"full_name": "Họ tên", "saint_name": "Tên Thánh", "birth_date": "Ngày sinh", "gender": "Giới tính",
                "parent_name": "Phụ huynh", "parent_phone": "SĐT", "note": "Ghi chú"}


def _diff(student: Student, data: StudentInput) -> list[str]:
    """Chỉ những trường có giá trị trong file mới ghi đè (ô trống không xóa dữ liệu cũ)."""
    changes = []
    for fld, label in _DIFF_FIELDS.items():
        new = getattr(data, fld)
        if new in (None, ""):
            continue
        if getattr(student, fld) != new:
            changes.append(f"{label}: '{getattr(student, fld) or ''}' → '{new}'")
    return changes


def _merge(student: Student, data: StudentInput) -> StudentInput:
    keep = {}
    for fld in ("saint_name", "birth_date", "gender", "parent_name", "parent_phone", "note"):
        value = getattr(data, fld)
        keep[fld] = value if value not in (None, "") else getattr(student, fld)
    return StudentInput(code=data.code, full_name=data.full_name or student.full_name,
                        status=student.status, **keep)


# ---- Áp dụng --------------------------------------------------------------------
def apply_plan(actor: Actor, plan: ImportPlan, year_id: int, default_class_id: int | None = None,
               default_branch_id: int | None = None, filename: str = "") -> dict[str, int]:
    """Áp dụng tất cả dòng hợp lệ trong MỘT giao dịch: lỗi giữa chừng -> không ghi gì."""
    actor.require(P_STUDENTS_IMPORT)
    result = {"created": 0, "updated": 0, "enrolled": 0, "classes_created": 0, "skipped_errors": 0}
    with session_scope() as s:
        years = {y.name: y.id for y in s.scalars(select(SchoolYear)).all()}
        branches = {search_key(b.name): b for b in s.scalars(select(Branch)).all()}
        class_cache: dict[tuple[int, str], int] = {}
        existing_classes = set(s.execute(select(ClassGroup.school_year_id, ClassGroup.name)).all())
        for r in plan.rows:
            if r.action == "error":
                result["skipped_errors"] += 1
                continue
            if r.action == "unchanged" and not r.class_name and default_class_id is None:
                continue
            target_year = years.get(r.year, year_id) if r.year else year_id
            student = s.scalar(select(Student).where(Student.code == r.data.code))
            if student is None:
                student = Student(code=r.data.code, full_name=r.data.full_name)
                s.add(student)
                _apply(student, r.data)
                s.flush()
                result["created"] += 1
            elif r.action == "update":
                _apply(student, _merge(student, r.data))
                result["updated"] += 1

            class_id = default_class_id
            if r.class_name:
                branch_id = default_branch_id
                if r.branch:
                    b = branches.get(search_key(r.branch))
                    if b is None:
                        b = Branch(name=clean_name(r.branch), sort_order=len(branches) + 1)
                        s.add(b)
                        s.flush()
                        branches[search_key(r.branch)] = b
                    branch_id = b.id
                key = (target_year, r.class_name)
                if key not in class_cache:
                    if key not in existing_classes:
                        result["classes_created"] += 1
                    class_cache[key] = org.get_or_create_class(s, target_year, r.class_name, branch_id).id
                class_id = class_cache[key]
            if class_id is not None or r.team:
                set_enrollment(s, student.id, target_year, class_id, r.team)
                result["enrolled"] += 1
            elif r.action == "create":
                set_enrollment(s, student.id, target_year, None, None)
        audit.record(s, actor, "student.import", "school_year", year_id, filename=filename, **result)
    return result


def template_bytes() -> bytes:
    """File Excel mẫu để tải về."""
    df = pd.DataFrame([
        {"Mã thiếu nhi": "0001", "Tên Thánh": "Maria", "Họ và tên": "Nguyễn Thị An", "Ngày sinh": "15/08/2014",
         "Giới tính": "Nữ", "Ngành": "Thiếu Nhi", "Lớp": "Thiếu 1A", "Đội": "Đội 1",
         "SĐT phụ huynh": "0901234567", "Ghi chú": ""},
        {"Mã thiếu nhi": "0002", "Tên Thánh": "Giuse", "Họ và tên": "Trần Văn Bình", "Ngày sinh": "02/03/2015",
         "Giới tính": "Nam", "Ngành": "Ấu Nhi", "Lớp": "Ấu 2B", "Đội": "Đội 2",
         "SĐT phụ huynh": "", "Ghi chú": ""},
    ])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Thiếu nhi")
        ws = writer.sheets["Thiếu nhi"]
        for col in ws.columns:  # định dạng Text để giữ số 0 ở đầu mã
            for c in col:
                c.number_format = "@"
            ws.column_dimensions[col[0].column_letter].width = 18
    return buf.getvalue()
