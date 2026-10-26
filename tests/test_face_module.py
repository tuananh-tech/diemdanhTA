"""Module khuôn mặt: kiểm thử logic an toàn bằng VECTOR GIẢ LẬP (không dùng ảnh người thật)."""
from datetime import date, timedelta

import numpy as np
import pytest
from sqlalchemy import func, select

from tntt.db import session_scope
from tntt.models import FaceTemplate
from tntt.services import face


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FACE_MODULE_ALLOWED", raising=False)
    settings = {"face_enabled": True, "face_conditions_ack": [True] * len(face.CONDITIONS)}
    assert not face.is_enabled(settings)
    monkeypatch.setenv("FACE_MODULE_ALLOWED", "true")
    assert face.is_enabled(settings)
    assert not face.is_enabled({**settings, "face_conditions_ack": [True]})  # thiếu điều kiện


def test_match_thresholds():
    rng = np.random.default_rng(0)
    a, b = rng.normal(size=128), rng.normal(size=128)
    gallery = {1: [a], 2: [b]}
    probe = a + rng.normal(scale=0.1, size=128)
    c = face.match(probe, gallery, threshold=0.5, margin=0.06)
    assert c.student_id == 1 and c.decision == "suggest"
    stranger = rng.normal(size=128)
    assert face.match(stranger, gallery, threshold=0.5, margin=0.06).decision == "uncertain"
    twin = {1: [a], 2: [a + rng.normal(scale=0.01, size=128)]}  # quá giống nhau -> không chắc chắn
    assert face.match(probe, twin, threshold=0.5, margin=0.06).decision == "uncertain"
    assert face.match(probe, {}, 0.5, 0.06) is None


def test_consent_gating_withdraw_and_purge(admin, school):
    stu = school["students"][school["c1"]][0]
    with pytest.raises(ValueError):
        face.record_consent(admin, stu, "", "Mẹ", date.today(), date.today() + timedelta(days=30), "DK-01")
    cid = face.record_consent(admin, stu, "Nguyễn Thị Mẹ", "Mẹ", date.today(), date.today() + timedelta(days=30),
                              "DK-01")
    vec = np.ones(128, dtype=np.float32)
    with session_scope() as s:
        assert face.valid_consent(s, stu) is not None
        s.add(FaceTemplate(student_id=stu, consent_id=cid, model=face.MODEL_NAME, vector=vec.tobytes()))
    # hết hạn -> purge xóa vector
    assert face.purge_invalid(today=date.today() + timedelta(days=31)) == 1
    with session_scope() as s:
        s.add(FaceTemplate(student_id=stu, consent_id=cid, model=face.MODEL_NAME, vector=vec.tobytes()))
    assert face.withdraw_consent(admin, stu) == 1
    with session_scope() as s:
        assert face.valid_consent(s, stu) is None
        assert s.scalar(select(func.count(FaceTemplate.id))) == 0


def test_engine_reports_missing_models():
    ok, reason = face.engine_status()
    if not ok:
        assert "mô hình" in reason or "OpenCV" in reason
