"""Module nhận diện khuôn mặt – TÙY CHỌN, MẶC ĐỊNH VÔ HIỆU HÓA.

Dữ liệu khuôn mặt là dữ liệu sinh trắc học (dữ liệu cá nhân nhạy cảm) của trẻ
em. Module chỉ hoạt động khi đồng thời:
  1. Người triển khai bật FACE_MODULE_ALLOWED=true trong secrets/env;
  2. Quản trị viên xác nhận đủ các điều kiện pháp lý/vận hành (CONDITIONS);
  3. Từng em có văn bản đồng ý hợp lệ (còn hạn, chưa rút lại) của cha mẹ/người giám hộ.

Thiết kế an toàn:
- Chỉ lưu vector đặc trưng (128 số thực), KHÔNG lưu ảnh. Ảnh chụp chỉ xử lý trong bộ nhớ.
- Chỉ ĐƯA RA GỢI Ý trong phạm vi danh sách phiên; có ngưỡng điểm + khoảng cách
  với ứng viên thứ hai; trường hợp không chắc chắn bị từ chối.
- Huynh trưởng phải bấm xác nhận danh tính thì mới ghi điểm danh (method=face).
- Rút đồng ý / hết hạn -> vector bị xóa. Có chức năng xóa toàn bộ dữ liệu sinh trắc học.
- Lỗi trong module này không ảnh hưởng điểm danh QR / thủ công (import lười, cô lập).

Bộ máy: OpenCV YuNet (phát hiện) + SFace (đặc trưng), mô hình ONNX giấy phép
Apache-2.0 từ opencv_zoo. Mô hình KHÔNG đi kèm repo; quản trị viên tự đặt vào
thư mục models/ (xem docs/FACE_MODULE.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
from sqlalchemy import delete, select

from .. import config
from ..db import session_scope
from ..models import AttendanceRecord, FaceConsent, FaceTemplate, Student, utcnow
from ..security import P_FACE, Actor
from . import audit

MODEL_NAME = "sface-2021dec"
DETECTOR_FILE = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_FILE = "face_recognition_sface_2021dec.onnx"

CONDITIONS = [
    "Đã có văn bản đồng ý của cha mẹ/người giám hộ cho từng em (và ý kiến của chính em nếu đủ tuổi theo luật).",
    "Đã đánh giá tác động xử lý dữ liệu cá nhân nhạy cảm theo quy định pháp luật Việt Nam hiện hành "
    "(Luật Bảo vệ dữ liệu cá nhân và văn bản hướng dẫn) và có người chịu trách nhiệm bảo vệ dữ liệu.",
    "Đã thông báo rõ mục đích, thời hạn lưu giữ, quyền rút lại đồng ý và quyền yêu cầu xóa dữ liệu.",
    "Có quy trình xử lý khi nhận diện sai; QR và điểm danh thủ công luôn sẵn sàng thay thế.",
    "Hệ thống chạy qua HTTPS, CSDL không công khai, chỉ người được phân quyền truy cập.",
]


class FaceUnavailable(Exception):
    pass


# ---- Điều kiện kích hoạt ----------------------------------------------------------------
def model_paths():
    return config.MODELS_DIR / DETECTOR_FILE, config.MODELS_DIR / RECOGNIZER_FILE


def engine_status() -> tuple[bool, str]:
    try:
        import cv2
    except Exception:
        return False, "Thiếu thư viện OpenCV."
    if not (hasattr(cv2, "FaceDetectorYN") and hasattr(cv2, "FaceRecognizerSF")):
        return False, "Phiên bản OpenCV không hỗ trợ YuNet/SFace."
    det, rec = model_paths()
    missing = [p.name for p in (det, rec) if not p.exists()]
    if missing:
        return False, "Chưa có file mô hình: " + ", ".join(missing)
    return True, "Sẵn sàng."


def is_enabled(settings: dict) -> bool:
    acked = settings.get("face_conditions_ack") or []
    return (config.face_module_allowed() and bool(settings.get("face_enabled"))
            and len(acked) == len(CONDITIONS) and all(acked))


# ---- Đồng ý ---------------------------------------------------------------------------
def valid_consent(s, student_id: int, today: date | None = None) -> FaceConsent | None:
    today = today or date.today()
    return s.scalar(select(FaceConsent).where(
        FaceConsent.student_id == student_id, FaceConsent.withdrawn_at.is_(None),
        FaceConsent.expires_at >= today).order_by(FaceConsent.consent_date.desc()))


def record_consent(actor: Actor, student_id: int, guardian_name: str, relation: str, consent_date: date,
                   expires_at: date, document_ref: str) -> int:
    actor.require(P_FACE)
    if not guardian_name.strip() or not document_ref.strip():
        raise ValueError("Cần ghi tên người giám hộ và số/mã văn bản đồng ý.")
    if expires_at <= consent_date:
        raise ValueError("Ngày hết hạn phải sau ngày ký.")
    if (expires_at - consent_date).days > 366:
        raise ValueError("Thời hạn đồng ý tối đa 1 năm; gia hạn bằng văn bản mới.")
    with session_scope() as s:
        c = FaceConsent(student_id=student_id, guardian_name=guardian_name.strip(), relation=relation.strip(),
                        consent_date=consent_date, expires_at=expires_at, document_ref=document_ref.strip(),
                        recorded_by=actor.id)
        s.add(c)
        s.flush()
        audit.record(s, actor, "face.consent_record", "student", student_id, consent_id=c.id)
        return c.id


def withdraw_consent(actor: Actor, student_id: int) -> int:
    """Rút đồng ý: đánh dấu rút và XÓA ngay mọi vector của em."""
    actor.require(P_FACE)
    with session_scope() as s:
        for c in s.scalars(select(FaceConsent).where(FaceConsent.student_id == student_id,
                                                     FaceConsent.withdrawn_at.is_(None))).all():
            c.withdrawn_at, c.withdrawn_by = utcnow(), actor.id
        n = s.execute(delete(FaceTemplate).where(FaceTemplate.student_id == student_id)).rowcount
        audit.record(s, actor, "face.consent_withdraw", "student", student_id, deleted_templates=n)
        return n


def delete_templates(actor: Actor, student_id: int | None = None) -> int:
    actor.require(P_FACE)
    with session_scope() as s:
        stmt = delete(FaceTemplate)
        if student_id is not None:
            stmt = stmt.where(FaceTemplate.student_id == student_id)
        n = s.execute(stmt).rowcount
        audit.record(s, actor, "face.delete_templates", "student", student_id, deleted=n)
        return n


def purge_invalid(today: date | None = None) -> int:
    """Xóa vector không còn đồng ý hợp lệ (hết hạn/rút lại). Gọi định kỳ khi mở trang."""
    today = today or date.today()
    with session_scope() as s:
        valid_ids = select(FaceConsent.id).where(FaceConsent.withdrawn_at.is_(None), FaceConsent.expires_at >= today)
        n = s.execute(delete(FaceTemplate).where(FaceTemplate.consent_id.not_in(valid_ids))).rowcount
        if n:
            audit.record(s, None, "face.purge_invalid", "face_templates", None, deleted=n)
        return n


def consent_overview(student_ids: list[int]) -> dict[int, dict]:
    with session_scope() as s:
        out = {}
        for sid in student_ids:
            c = valid_consent(s, sid)
            n = len(s.scalars(select(FaceTemplate.id).where(FaceTemplate.student_id == sid)).all())
            out[sid] = {"consent": c.expires_at if c else None, "templates": n}
        return out


# ---- So khớp (thuần, kiểm thử được không cần mô hình) ------------------------------
@dataclass
class Candidate:
    student_id: int
    score: float
    second_score: float
    decision: str  # "suggest" | "uncertain"


def l2norm(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).ravel()
    n = np.linalg.norm(v)
    return v / n if n else v


def match(query: np.ndarray, gallery: dict[int, list[np.ndarray]], threshold: float, margin: float) -> Candidate | None:
    """Cosine similarity với từng em (lấy điểm cao nhất trong các mẫu của em đó)."""
    if not gallery:
        return None
    q = l2norm(query)
    scores = sorted(((max(float(np.dot(q, l2norm(v))) for v in vecs), sid) for sid, vecs in gallery.items() if vecs),
                    reverse=True)
    if not scores:
        return None
    best, sid = scores[0]
    second = scores[1][0] if len(scores) > 1 else -1.0
    decision = "suggest" if best >= threshold and (best - second) >= margin else "uncertain"
    return Candidate(sid, best, second, decision)


# ---- Bộ máy OpenCV ------------------------------------------------------------------------
_engine = None


def _get_engine():
    global _engine
    ok, reason = engine_status()
    if not ok:
        raise FaceUnavailable(reason)
    if _engine is None:
        import cv2

        det_path, rec_path = model_paths()
        detector = cv2.FaceDetectorYN.create(str(det_path), "", (320, 320), 0.85, 0.3, 50)
        recognizer = cv2.FaceRecognizerSF.create(str(rec_path), "")
        _engine = (detector, recognizer)
    return _engine


def _decode_image(data: bytes):
    import cv2

    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise ValueError("Ảnh không hợp lệ.")
    h, w = arr.shape[:2]
    scale = 960 / max(h, w)
    if scale < 1:
        arr = cv2.resize(arr, (int(w * scale), int(h * scale)))
    return arr


def embeddings(image_bytes: bytes) -> list[tuple[list[int], np.ndarray]]:
    detector, recognizer = _get_engine()
    img = _decode_image(image_bytes)
    h, w = img.shape[:2]
    detector.setInputSize((w, h))
    _, faces = detector.detect(img)
    out = []
    for f in faces if faces is not None else []:
        aligned = recognizer.alignCrop(img, f)
        feat = recognizer.feature(aligned)
        out.append(([int(x) for x in f[:4]], l2norm(feat)))
    return out


def enroll(actor: Actor, student_id: int, image_bytes: bytes, max_templates: int = 5) -> int:
    actor.require(P_FACE)
    faces = embeddings(image_bytes)
    if len(faces) != 1:
        raise ValueError(f"Ảnh phải có đúng 1 khuôn mặt (phát hiện {len(faces)}).")
    with session_scope() as s:
        consent = valid_consent(s, student_id)
        if consent is None:
            raise PermissionError("Em này chưa có văn bản đồng ý hợp lệ – không được đăng ký khuôn mặt.")
        count = len(s.scalars(select(FaceTemplate.id).where(FaceTemplate.student_id == student_id)).all())
        if count >= max_templates:
            raise ValueError(f"Đã đủ {max_templates} mẫu. Xóa mẫu cũ nếu cần đăng ký lại.")
        s.add(FaceTemplate(student_id=student_id, consent_id=consent.id, model=MODEL_NAME,
                           vector=faces[0][1].astype(np.float32).tobytes(), created_by=actor.id))
        audit.record(s, actor, "face.enroll", "student", student_id)
        return count + 1


def session_gallery(session_id: int) -> dict[int, list[np.ndarray]]:
    purge_invalid()
    with session_scope() as s:
        rows = s.execute(
            select(FaceTemplate.student_id, FaceTemplate.vector)
            .join(AttendanceRecord, AttendanceRecord.student_id == FaceTemplate.student_id)
            .where(AttendanceRecord.session_id == session_id, FaceTemplate.model == MODEL_NAME)
        ).all()
    gallery: dict[int, list[np.ndarray]] = {}
    for sid, blob in rows:
        gallery.setdefault(sid, []).append(np.frombuffer(blob, dtype=np.float32))
    return gallery


def suggest(session_id: int, image_bytes: bytes, threshold: float, margin: float) -> list[dict]:
    """Gợi ý danh tính cho từng khuôn mặt trong ảnh. KHÔNG ghi điểm danh."""
    gallery = session_gallery(session_id)
    results = []
    with session_scope() as s:
        for box, vec in embeddings(image_bytes):
            cand = match(vec, gallery, threshold, margin)
            item = {"box": box, "decision": "unknown", "score": None}
            if cand:
                st = s.get(Student, cand.student_id)
                item.update(decision=cand.decision, score=round(cand.score, 3), second=round(cand.second_score, 3),
                            student_id=cand.student_id, code=st.code,
                            name=f"{st.saint_name or ''} {st.full_name}".strip())
            results.append(item)
    return results
