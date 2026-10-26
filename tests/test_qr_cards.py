import io

import pytest
from PIL import Image

from tntt import cards, qrimage
from tntt.services import branding, qrcodes


def test_token_has_no_personal_data_and_is_unique():
    tokens = {qrcodes.new_token() for _ in range(2000)}
    assert len(tokens) == 2000
    p = qrcodes.payload_for(next(iter(tokens)))
    assert p.startswith("TNTT:") and len(p) == 17


@pytest.mark.parametrize("fg", ["#000000", "#1B2A4A", "#D4A017"])
@pytest.mark.parametrize("ratio", [0.18, 0.24, 0.30])
def test_logo_qr_decodes(fg, ratio):
    payload = qrcodes.payload_for(qrcodes.new_token())
    res = qrimage.make_qr(payload, logo=branding.default_logo(), logo_ratio=ratio, fg=fg)
    assert res.logo_applied and res.verified and res.version >= 3
    assert payload in qrimage.decode(res.image)


def test_plain_qr_decodes():
    payload = qrcodes.payload_for(qrcodes.new_token())
    res = qrimage.make_qr(payload)
    assert res.verified and not res.logo_applied


def test_auto_shrink_then_drop_logo(monkeypatch):
    payload = qrcodes.payload_for(qrcodes.new_token())
    real_verify = qrimage.verify
    calls = []

    masks = len(qrimage._MASK_ORDER)

    # Mặt nạ đầu tiên "thất bại" -> thử mặt nạ khác, GIỮ nguyên kích thước logo
    def fail_first(img, expected):
        calls.append(img)
        return len(calls) >= 2 and real_verify(img, expected)

    monkeypatch.setattr(qrimage, "verify", fail_first)
    res0 = qrimage.make_qr(payload, logo=branding.default_logo(), logo_ratio=0.30)
    assert res0.logo_applied and res0.logo_ratio == pytest.approx(0.30) and len(calls) == 2

    # Mọi mặt nạ ở 0.30 và 0.27 đều "thất bại" -> logo giảm còn 0.24
    calls.clear()

    def fail_two_sizes(img, expected):
        calls.append(img)
        return len(calls) > 2 * masks and real_verify(img, expected)

    monkeypatch.setattr(qrimage, "verify", fail_two_sizes)
    res = qrimage.make_qr(payload, logo=branding.default_logo(), logo_ratio=0.30)
    assert res.logo_applied and res.logo_ratio == pytest.approx(0.24)

    # Mọi lần thử có logo (7 kích thước × mọi mặt nạ) đều "thất bại" -> phải bỏ logo
    calls.clear()

    def fail_with_logo(img, expected):
        calls.append(img)
        return len(calls) > 7 * masks and real_verify(img, expected)

    monkeypatch.setattr(qrimage, "verify", fail_with_logo)
    res2 = qrimage.make_qr(payload, logo=branding.default_logo(), logo_ratio=0.30)
    assert len(calls) == 7 * masks + 1
    assert not res2.logo_applied and res2.verified and "bỏ" in res2.message


def test_logo_kept_with_opencv_only(monkeypatch):
    """Tái hiện Streamlit Cloud (không có ZBar): mã ngẫu nhiên vẫn giữ logo 30% và qua kiểm tra."""
    monkeypatch.setattr(qrimage, "_decode_zbar", lambda img: [])
    monkeypatch.setattr(qrimage, "available_decoders", lambda: ["OpenCV"])
    logo = branding.default_logo()
    results = [qrimage.make_qr(qrcodes.payload_for(qrcodes.new_token()), logo=logo, logo_ratio=0.30)
               for _ in range(120)]
    assert all(r.verified for r in results)
    assert all(r.logo_applied and r.logo_ratio == pytest.approx(0.30) for r in results)


def test_foreground_contrast_enforced():
    light = qrimage.safe_foreground("#FFE680")
    assert qrimage.contrast_ratio(light, (255, 255, 255)) >= 7


def test_cards_pdf_qr_readable_after_rasterize():
    pdfium = pytest.importorskip("pypdfium2")
    logo = branding.default_logo()
    data = [cards.CardData(f"{i:04d}", "Maria", "Nguyễn Thị Ánh Tuyết", "Ấu Nhi 1", "Ấu Nhi",
                           qrcodes.payload_for(qrcodes.new_token())) for i in range(1, 4)]
    style = cards.CardStyle("Xứ đoàn Test", "Giáo xứ Test", "2025-2026", logo=logo, qr_logo=logo)
    rep = cards.build_cards_pdf(data, style)
    assert rep.pdf.startswith(b"%PDF") and not rep.unverified and not rep.without_logo
    page = pdfium.PdfDocument(rep.pdf)[0].render(scale=300 / 72).to_pil()
    decoded = set(qrimage.decode(page))
    # quét cả trang có thể chỉ thấy 1 mã -> cắt từng thẻ
    mm = 300 / 25.4
    x0, y0 = (210 - (3 * 54 + 8)) / 2, (297 - (3 * 85.6 + 8)) / 2
    for k in range(3):
        crop = page.crop((int((x0 + k * 58) * mm), int(y0 * mm), int((x0 + k * 58 + 54) * mm), int((y0 + 85.6) * mm)))
        decoded |= set(qrimage.decode(crop))
    assert {d.payload for d in data} <= decoded


def test_qr_zip():
    import zipfile

    data = [cards.CardData("0001", "", "Lê Văn A", "L1", "", qrcodes.payload_for(qrcodes.new_token()))]
    blob, problems = cards.build_qr_zip(data, logo=branding.default_logo(), logo_ratio=0.24, fg="#1B2A4A",
                                        with_label=True)
    assert not problems
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        assert names == ["0001_Le_Van_A.png"]
        img = Image.open(io.BytesIO(zf.read(names[0])))
        assert data[0].payload in qrimage.decode(img)
