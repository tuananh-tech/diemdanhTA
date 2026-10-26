"""Thành phần quét QR bằng camera của TRÌNH DUYỆT (thiết bị của Huynh trưởng).

Không dùng camera của máy chủ. Giải mã chạy hoàn toàn phía trình duyệt
(BarcodeDetector nếu có, nếu không dùng jsQR – Apache-2.0, đã đóng gói sẵn).
Mỗi lần đọc được mã, component trả về {"text", "nonce"}; Python xử lý rồi
truyền lại `result` để component phát màu/âm thanh phản hồi.
"""
from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component("tntt_qr_scanner", path=str(Path(__file__).parent))


def qr_scanner(result: dict | None = None, key: str = "qr_scanner"):
    """result: {"nonce", "kind", "title", "subtitle"} của lần quét gần nhất."""
    return _component(result=result, key=key, default=None)
