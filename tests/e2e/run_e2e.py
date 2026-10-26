"""Kiểm thử đầu-cuối trên trình duyệt thật (Chromium headless) với server Streamlit thật.

Chạy:  python tests/e2e/run_e2e.py
Yêu cầu: pip install -r requirements-dev.txt && python -m playwright install chromium

Kịch bản dùng CSDL SQLite tạm, dữ liệu giả lập. Camera được giả lập bằng
video Y4M chứa mã QR thật -> kiểm tra toàn bộ chuỗi: camera trình duyệt ->
giải mã JS -> Streamlit -> CSDL.
"""
from __future__ import annotations

import io
import re
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import expect, sync_playwright  # noqa: E402

from tests.e2e.helpers import BASE, OUT, fill, login, shot, wait_idle  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f" – {detail}" if detail else ""), flush=True)


def start_server(env: dict) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true", "--server.port", "8599"],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/_stcore/health", timeout=1)
            return proc
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Server không khởi động được")


def stop_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


def make_y4m(path: Path, images: list[Image.Image], frames_each: int = 25, size=(640, 480)) -> None:
    """Video YUV4MPEG2 (4:2:0) cho --use-file-for-fake-video-capture."""
    w, h = size
    with open(path, "wb") as f:
        f.write(f"YUV4MPEG2 W{w} H{h} F10:1 Ip A1:1 C420jpeg\n".encode())
        for img in images:
            canvas = Image.new("RGB", size, (90, 96, 110))
            im = img.convert("RGB")
            im.thumbnail((h - 60, h - 60))
            canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
            y, cb, cr = [np.asarray(c, dtype=np.uint8) for c in canvas.convert("YCbCr").split()]
            frame = b"FRAME\n" + y.tobytes() + cb[::2, ::2].tobytes() + cr[::2, ::2].tobytes()
            for _ in range(frames_each):
                f.write(frame)


def cards_safe(text: str) -> str:
    from tntt.cards import safe_filename

    return safe_filename(text)


def blank(text: str) -> Image.Image:
    img = Image.new("RGB", (400, 400), "white")
    ImageDraw.Draw(img).text((20, 190), text, fill="black")
    return img


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tntt_e2e_"))
    db_url = f"sqlite:///{(tmp / 'e2e.db').as_posix()}"
    if os.environ.get("E2E_DB") == "postgres":  # PostgreSQL thật, nhúng qua pgserver
        import pgserver

        pg = pgserver.get_server(str(tmp / "pg"), cleanup_mode="stop")
        db_url = pg.get_uri()
        print("E2E trên PostgreSQL:", db_url)
    env = {**os.environ, "DATABASE_URL": db_url, "SETUP_TOKEN": "e2e-token", "PYTHONIOENCODING": "utf-8"}
    os.environ["DATABASE_URL"] = db_url
    proc = start_server(env)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()
            console_errors = []
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" and "404" not in m.text else None)
            page.on("response", lambda r: console_errors.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)

            # 1. Khởi tạo quản trị viên
            page.goto(BASE)
            page.get_by_label("Mã khởi tạo").wait_for(timeout=30000)
            fill(page, "Mã khởi tạo", "sai-token")
            fill(page, "Họ tên quản trị viên", "Quản Trị")
            fill(page, "Mật khẩu (≥ 8 ký tự, có chữ và số)", "Admin12345")
            fill(page, "Nhập lại mật khẩu", "Admin12345")
            page.get_by_role("button", name="Tạo tài khoản quản trị").click()
            wait_idle(page)
            check("Setup token sai bị từ chối", page.get_by_text("không đúng").count() > 0)
            fill(page, "Mã khởi tạo", "e2e-token")
            fill(page, "Mật khẩu (≥ 8 ký tự, có chữ và số)", "Admin12345")
            fill(page, "Nhập lại mật khẩu", "Admin12345")
            page.get_by_role("button", name="Tạo tài khoản quản trị").click()
            wait_idle(page)
            page.get_by_role("heading", name="Tổng quan").wait_for(timeout=20000)
            check("Tạo quản trị viên & vào Tổng quan", True)

            # 2. Cấu hình Xứ đoàn + logo
            page.get_by_role("link", name="Cấu hình Xứ đoàn").click()
            wait_idle(page)
            fill(page, "Tên Xứ đoàn *", "Xứ đoàn Đaminh Savio")
            fill(page, "Tên Giáo xứ *", "Giáo xứ Thử Nghiệm")
            page.get_by_role("button", name="Lưu thông tin").click()
            wait_idle(page)
            check("Lưu tên Xứ đoàn hiển thị ở header",
                  page.locator(".tn-header").get_by_text("Xứ đoàn Đaminh Savio").count() > 0)
            page.get_by_role("tab", name="🖼️ Logo").click()
            logo = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
            d = ImageDraw.Draw(logo)
            d.ellipse([20, 20, 580, 580], fill=(150, 20, 40, 255))
            d.rectangle([270, 100, 330, 500], fill="white")
            d.rectangle([170, 220, 430, 280], fill="white")
            buf = io.BytesIO()
            logo.save(buf, format="PNG")
            page.locator("input[type=file]").first.set_input_files(
                files=[{"name": "logo.png", "mimeType": "image/png", "buffer": buf.getvalue()}])
            wait_idle(page)
            try:
                page.get_by_role("button", name="💾 Lưu logo này").wait_for(timeout=20000)
            except Exception:
                shot(page, "FAIL_logo")
                raise
            shot(page, "10_logo_editor")
            page.get_by_role("button", name="💾 Lưu logo này").click()
            wait_idle(page)
            check("Lưu logo mới", page.get_by_text("Đã lưu logo").count() > 0)

            # 3. Nhập Excel
            page.get_by_role("link", name="Thiếu nhi").click()
            wait_idle(page)
            page.get_by_role("tab", name="📥 Nhập Excel").click()
            page.locator("input[type=file]").first.set_input_files(str(ROOT / "sample_data" / "mau_day_du_120_em.xlsx"))
            wait_idle(page, 30)
            btn = page.get_by_role("button", name="✅ Nhập 120 mới")
            btn.wait_for(timeout=30000)
            shot(page, "11_import_preview")
            btn.click()
            wait_idle(page, 30)
            check("Nhập 120 thiếu nhi từ Excel", page.get_by_text("thêm 120").count() > 0)
            page.get_by_role("tab", name="📋 Danh sách").click()
            fill(page, "Tìm theo tên hoặc mã (không dấu được)", "0001")
            page.keyboard.press("Enter")
            wait_idle(page)
            check("Tìm theo mã giữ số 0 ở đầu", page.get_by_text("1 em ·").count() > 0)

            # 4. Tạo buổi sinh hoạt cho 2 lớp
            page.get_by_role("link", name="Buổi sinh hoạt").click()
            wait_idle(page)
            page.get_by_role("tab", name="➕ Tạo buổi").click()
            page.get_by_label("Lớp tham dự").first.click()
            page.get_by_role("option", name="Ấu Nhi 1 · Ấu Nhi").click()
            page.keyboard.press("Escape")
            wait_idle(page)
            page.get_by_role("button", name="Tạo buổi").click()
            wait_idle(page)
            check("Tạo & mở buổi sinh hoạt", page.get_by_text("Đã tạo buổi sinh hoạt").count() > 0)

            # 5. Điểm danh thủ công một chạm
            page.get_by_role("link", name="Điểm danh", exact=True).click()
            wait_idle(page)
            page.get_by_text("Đã điểm danh 0/20 em").wait_for(timeout=20000)
            shot(page, "12_manual_list")
            page.get_by_role("radio", name="Có mặt").first.click()
            wait_idle(page)
            page.wait_for_timeout(800)
            check("Một chạm → Có mặt được lưu", page.get_by_text("Đã điểm danh 1/20 em").count() > 0)

            from tntt import db as tdb
            from tntt.services import qrcodes, students as stsvc
            from tntt.security import SYSTEM_ACTOR

            tdb.configure(db_url)
            sid_a = stsvc.find_by_code("0025").id  # lớp Ấu Nhi 1
            sid_b = stsvc.find_by_code("0001").id  # lớp Chiên Con A – không thuộc phiên
            tokens = qrcodes.ensure_tokens(SYSTEM_ACTOR, [sid_a, sid_b])
            from tntt import qrimage
            from tntt.services import branding

            branding.invalidate()
            qa = qrimage.make_qr(qrcodes.payload_for(tokens[sid_a]), logo=branding.get_logo(), fg="#1B2A4A").image
            qb = qrimage.make_qr(qrcodes.payload_for(tokens[sid_b]), logo=branding.get_logo()).image
            video = tmp / "cam.y4m"
            make_y4m(video, [blank("..."), qa, blank("..."), qa, blank("..."), qb, blank("...")], frames_each=30)

            # 6. Kiểm tra giao diện mobile (danh sách)
            mob = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
                                      has_touch=True)
            mpage = mob.new_page()
            login(mpage, "admin", "Admin12345")
            mpage.goto(BASE + "/diem-danh")  # tải trang mới = phiên Streamlit mới
            wait_idle(mpage)
            mpage.get_by_text("Đã điểm danh 1/20 em").wait_for(timeout=20000)
            check("Tải lại trang vẫn giữ đăng nhập (cookie ghi nhớ)", True)
            shot(mpage, "20_mobile_manual", full=False)
            mpage.mouse.wheel(0, 900)
            mpage.wait_for_timeout(600)
            shot(mpage, "20b_mobile_manual_rows", full=False)
            sw = mpage.evaluate("document.documentElement.scrollWidth")
            check("Mobile 390px không cuộn ngang", sw <= 392, f"scrollWidth={sw}")
            mob.close()

            # 7. Quét QR bằng camera giả lập
            cam_browser = p.chromium.launch(args=[
                "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-video-capture={video}"])
            cctx = cam_browser.new_context(viewport={"width": 1280, "height": 900}, permissions=["camera"])
            cpage = cctx.new_page()
            login(cpage, "admin", "Admin12345")
            cpage.goto(BASE + "/quet-qr")
            wait_idle(cpage)
            frame = cpage.frame_locator("iframe[title='tntt.components.qr_scanner.tntt_qr_scanner']")
            frame.get_by_role("button", name="Bật camera").click(timeout=20000)
            ok_scan = False
            for _ in range(60):
                cpage.wait_for_timeout(500)
                if cpage.locator(".tn-result").filter(has_text="✓").count():
                    ok_scan = True
                    break
            shot(cpage, "13_qr_scan_success", full=False)
            check("Camera trình duyệt quét QR → ghi nhận", ok_scan)
            dup = False
            for _ in range(60):
                cpage.wait_for_timeout(500)
                if cpage.locator(".tn-result").filter(has_text="Đã điểm danh").count():
                    dup = True
                    break
            check("Quét lại cùng thẻ → báo đã điểm danh", dup)
            shot(cpage, "14_qr_scan_duplicate", full=False)
            other = False
            for _ in range(60):
                cpage.wait_for_timeout(500)
                if cpage.locator(".tn-result").filter(has_text="không thuộc danh sách").count():
                    other = True
                    break
            check("Thẻ của em ngoài phiên → báo không thuộc danh sách", other)
            # nhập mã thủ công
            cpage.get_by_placeholder("Ví dụ: 0012").fill("0026")
            cpage.get_by_role("button", name="Điểm danh", exact=True).click()
            wait_idle(cpage)
            check("Nhập mã thủ công tại trang quét", cpage.locator(".tn-result").filter(has_text="✓").count() > 0)
            cam_browser.close()

            from sqlalchemy import select
            from tntt.db import session_scope
            from tntt.models import AttendanceRecord

            with session_scope() as s:
                rec = s.scalar(select(AttendanceRecord).where(AttendanceRecord.student_id == sid_a))
                n_logs_ok = rec is not None and rec.method == "qr" and rec.status in ("present", "late")
            check("CSDL: bản ghi QR có method=qr, trạng thái có mặt/trễ", n_logs_ok)

            # 8. Báo cáo + xuất Excel
            page.reload()
            page.get_by_role("link", name="Báo cáo").click()
            wait_idle(page)
            with page.expect_download() as dl:
                page.get_by_role("button", name="⬇️ Excel").click()
            path = tmp / dl.value.suggested_filename
            dl.value.save_as(path)
            check("Xuất báo cáo Excel", path.stat().st_size > 3000, path.name)
            page.get_by_role("button", name="📄 Tạo PDF").click()
            wait_idle(page)
            with page.expect_download() as dl2:
                page.get_by_role("button", name="⬇️ Tải PDF").click()
            p2 = tmp / dl2.value.suggested_filename
            dl2.value.save_as(p2)
            check("Xuất báo cáo PDF", p2.read_bytes()[:4] == b"%PDF")
            shot(page, "15_reports")

            # 8b. Thẻ QR: tạo PDF qua giao diện, đọc lại QR từ file tải về
            page.get_by_role("link", name="Thẻ QR").click()
            wait_idle(page)
            page.get_by_role("tab", name="🖨️ In thẻ PDF / tải hàng loạt").click()
            page.get_by_role("button", name="🖨️ Tạo PDF thẻ thiếu nhi").click()
            page.get_by_role("button", name="⬇️ Tải PDF thẻ").wait_for(timeout=120000)
            with page.expect_download() as dl3:
                page.get_by_role("button", name="⬇️ Tải PDF thẻ").click()
            p3 = tmp / dl3.value.suggested_filename
            dl3.value.save_as(p3)
            shot(page, "17_qr_cards")
            try:
                import pypdfium2 as pdfium

                pg0 = pdfium.PdfDocument(p3.read_bytes())[0].render(scale=300 / 72).to_pil()
                mm = 300 / 25.4
                x0, y0 = (210 - (3 * 54 + 8)) / 2, (297 - (3 * 85.6 + 8)) / 2
                card = pg0.crop((int(x0 * mm), int(y0 * mm), int((x0 + 54) * mm), int((y0 + 85.6) * mm)))
                found = [t for t in qrimage.decode(card) if t.startswith("TNTT:")]
                check("PDF thẻ (tạo từ giao diện) đọc lại được QR", bool(found), found[0] if found else "")
            except ImportError:
                check("PDF thẻ tạo được", p3.read_bytes()[:4] == b"%PDF")

            # 8b2. Thu hồi & cấp lại thẻ (mã cũ phải bị vô hiệu)
            page.get_by_role("tab", name="♻️ Thu hồi / cấp lại").click()
            old_tokens = qrcodes.active_tokens([sid_a, sid_b])
            page.get_by_label("Thiếu nhi").last.click()
            page.keyboard.type("0025")
            page.keyboard.press("Enter")
            wait_idle(page)
            page.get_by_role("button", name="♻️ Thu hồi & cấp mã mới").click()
            wait_idle(page)
            new_tokens = qrcodes.active_tokens([sid_a])
            check("Cấp lại thẻ QR: mã cũ bị thay", new_tokens.get(sid_a) not in (None, old_tokens.get(sid_a)))

            # 8b3. Tạo buổi theo lịch (Chủ nhật hằng tuần, toàn Xứ đoàn)
            page.get_by_role("link", name="Buổi sinh hoạt").click()
            wait_idle(page)
            page.get_by_role("tab", name="🗓️ Tạo theo lịch").click()
            page.get_by_text("Toàn Xứ đoàn (mọi thiếu nhi đang sinh hoạt)").last.click()
            wait_idle(page)
            page.get_by_role("button", name="Tạo các buổi theo lịch").click()
            wait_idle(page)
            check("Tạo buổi theo lịch", page.get_by_text("Đã tạo").count() > 0)

            # 8b4. Sao lưu toàn bộ dữ liệu và tải về
            page.get_by_role("link", name="Cấu hình Xứ đoàn").click()
            wait_idle(page)
            page.get_by_role("tab", name="💾 Sao lưu").click()
            page.get_by_role("button", name="📦 Tạo bản sao lưu").click()
            wait_idle(page)
            with page.expect_download() as dl4:
                page.get_by_role("button", name="⬇️ Tải bản sao lưu").click()
            p4 = tmp / dl4.value.suggested_filename
            dl4.value.save_as(p4)
            from tntt.services import backup as bk

            check("Sao lưu tải về hợp lệ (120 em)", bk.read_manifest(p4.read_bytes())["counts"]["students"] == 120)

            # 8c. Duyệt mọi trang: không trang nào hiện lỗi Python
            broken = []
            for name in ["Tổng quan", "Điểm danh", "Quét QR", "Buổi sinh hoạt", "Thiếu nhi", "Ngành / Lớp", "Thẻ QR",
                         "Báo cáo", "Phân quyền", "Cấu hình Xứ đoàn", "Nhật ký hoạt động", "Tài khoản"]:
                page.get_by_role("link", name=name, exact=True).click()
                wait_idle(page)
                page.wait_for_timeout(500)
                if page.locator("[data-testid='stException']").count():
                    broken.append(name)
                    shot(page, f"FAIL_page_{cards_safe(name)}")
            check("Mọi trang mở không lỗi", not broken, ", ".join(broken))

            # 9. Dashboard có dữ liệu
            page.get_by_role("link", name="Tổng quan").click()
            wait_idle(page)
            page.wait_for_timeout(1500)
            shot(page, "16_dashboard")

            # 10. Phân quyền: Huynh trưởng
            from tntt import constants as C
            from tntt.services import org, users

            admin_actor = users.actor_for(1)
            year = org.current_year()
            cls2 = next(k for k, v in org.class_options(year.id).items() if v.startswith("Thiếu Nhi 1"))
            users.create_user(admin_actor, "ht.test", "HT Kiểm Thử", C.ROLE_LEADER, "Leader12345", class_ids=[cls2])
            lctx = browser.new_context(viewport={"width": 1280, "height": 900})
            lpage = lctx.new_page()
            login(lpage, "ht.test", "Leader12345")
            check("Bắt đổi mật khẩu lần đầu", lpage.get_by_text("cần đổi mật khẩu").count() > 0)
            fill(lpage, "Mật khẩu hiện tại", "Leader12345")
            fill(lpage, "Mật khẩu mới (≥ 8 ký tự, có chữ và số)", "Leader67890")
            fill(lpage, "Nhập lại mật khẩu mới", "Leader67890")
            lpage.get_by_role("button", name="Lưu mật khẩu mới").click()
            wait_idle(lpage)
            nav = lpage.locator("[data-testid='stSidebarNav']").inner_text()
            check("Huynh trưởng không thấy trang quản trị", "Phân quyền" not in nav and "Cấu hình" not in nav, nav[:80])
            lpage.get_by_role("link", name="Thiếu nhi").click()
            wait_idle(lpage)
            check("Huynh trưởng chỉ thấy lớp được phân công", lpage.get_by_text("20 em ·").count() > 0)
            lpage.goto(BASE + "/phan-quyen")
            wait_idle(lpage)
            check("Truy cập URL trang quản trị bị chặn", lpage.get_by_role("heading", name="Phân quyền").count() == 0)
            lctx.close()
            browser.close()
            # Streamlit tự thăm dò /<trang>/_stcore/* rồi quay về đường dẫn gốc -> 404 vô hại của framework.
            real = [e for e in console_errors if "favicon" not in e and "/_stcore/" not in e]
            check("Không có lỗi console JS / HTTP lỗi của ứng dụng", not real, str(real[:3]))

        # 11. Khởi động lại server -> dữ liệu còn nguyên
        stop_server(proc)
        proc = start_server(env)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            login(page, "admin", "Admin12345")
            ok = page.locator(".tn-header").get_by_text("Xứ đoàn Đaminh Savio").count() > 0
            page.get_by_role("link", name="Thiếu nhi").click()
            wait_idle(page)
            check("Sau khởi động lại: cấu hình & 120 em còn nguyên", ok and page.get_by_text("120 em ·").count() > 0)
            mob = browser.new_page(viewport={"width": 768, "height": 1024})
            login(mob, "admin", "Admin12345")
            shot(mob, "21_tablet_dashboard", full=False)
            browser.close()
    finally:
        stop_server(proc)
    passed = sum(ok for _, ok, _ in RESULTS)
    print(f"\n{passed}/{len(RESULTS)} kiểm tra E2E đạt. Ảnh chụp: {OUT}")
    (OUT / "e2e_results.txt").write_text(
        "\n".join(("PASS " if ok else "FAIL ") + n + (f" – {d}" if d else "") for n, ok, d in RESULTS), encoding="utf-8")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
