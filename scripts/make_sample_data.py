"""Sinh file Excel/CSV mẫu với tên GIẢ LẬP (không phải dữ liệu thật của trẻ em).

Chạy: python scripts/make_sample_data.py
"""
from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "sample_data"

SAINTS_M = ["Giuse", "Phêrô", "Phaolô", "Gioan", "Antôn", "Phanxicô Xaviê", "Đaminh", "Micae", "Vinh Sơn", "Anrê"]
SAINTS_F = ["Maria", "Anna", "Têrêsa", "Cêcilia", "Rosa", "Lucia", "Agnes", "Catarina", "Monica", "Isave"]
FAMILY = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý"]
MIDDLE_M = ["Văn", "Minh", "Quốc", "Đức", "Gia", "Hoàng", "Thành", "Anh"]
MIDDLE_F = ["Thị", "Ngọc", "Thu", "Khánh", "Bảo", "Phương", "Mai", "Thanh"]
GIVEN_M = ["An", "Bình", "Khoa", "Huy", "Phúc", "Long", "Nam", "Duy", "Tuấn", "Khang", "Đạt", "Quân"]
GIVEN_F = ["Châu", "Linh", "Ngân", "Thư", "Vy", "Hân", "My", "Uyên", "Trâm", "Nhi", "Hà", "Như"]

CLASSES = [
    ("Chiên Con", "Chiên Con A", 2019), ("Ấu Nhi", "Ấu Nhi 1", 2017), ("Ấu Nhi", "Ấu Nhi 2", 2016),
    ("Thiếu Nhi", "Thiếu Nhi 1", 2014), ("Thiếu Nhi", "Thiếu Nhi 2", 2013), ("Nghĩa Sĩ", "Nghĩa Sĩ 1", 2011),
]


def fake_person(rng: random.Random):
    male = rng.random() < 0.5
    saint = rng.choice(SAINTS_M if male else SAINTS_F)
    name = f"{rng.choice(FAMILY)} {rng.choice(MIDDLE_M if male else MIDDLE_F)} {rng.choice(GIVEN_M if male else GIVEN_F)}"
    return male, saint, name


def build(seed: int = 7, per_class: int = 20):
    rng = random.Random(seed)
    rows = []
    n = 0
    for branch, cls, birth_year in CLASSES:
        for _ in range(per_class):
            n += 1
            male, saint, name = fake_person(rng)
            birth = date(birth_year, 1, 1) + timedelta(days=rng.randint(0, 364))
            rows.append({
                "Mã thiếu nhi": f"{n:04d}", "Tên Thánh": saint, "Họ và tên": name,
                "Ngày sinh": birth.strftime("%d/%m/%Y"), "Giới tính": "Nam" if male else "Nữ",
                "Ngành": branch, "Lớp": cls, "Đội": f"Đội {rng.randint(1, 3)}",
                "SĐT phụ huynh": f"09{rng.randint(10000000, 99999999)}", "Ghi chú": "",
            })
    return pd.DataFrame(rows)


def write_text_excel(df: pd.DataFrame, path: Path, sheet: str = "Danh sách"):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet)
        ws = writer.sheets[sheet]
        for col in ws.columns:
            for c in col:
                c.number_format = "@"
            ws.column_dimensions[col[0].column_letter].width = 18


def main():
    OUT.mkdir(exist_ok=True)
    full = build()
    write_text_excel(full, OUT / "mau_day_du_120_em.xlsx")
    simple = pd.DataFrame({"ID": [str(i) for i in range(1, 25)],
                           "Tên": [f"{s} {n}" for _, s, n in (fake_person(random.Random(i)) for i in range(24))]})
    write_text_excel(simple, OUT / "mau_don_gian_ID_Ten.xlsx", "Sheet1")
    full.head(10).to_csv(OUT / "mau_csv_so_0_dau.csv", index=False, encoding="utf-8-sig")
    print("Đã tạo:", *sorted(p.name for p in OUT.iterdir()), sep="\n  ")


if __name__ == "__main__":
    sys.exit(main())
