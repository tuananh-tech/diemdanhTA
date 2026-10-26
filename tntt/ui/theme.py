"""CSS, header và các khối hiển thị dùng chung."""
from __future__ import annotations

import base64
import html

import streamlit as st

from .. import constants as C
from ..services import branding


@st.cache_data(show_spinner=False, max_entries=8)
def _logo_b64(key: str, stamp: str, px: int) -> str:
    return base64.b64encode(branding.logo_png(key, px)).decode()


def logo_data_uri(key: str = branding.LOGO_XUDOAN, px: int = 160) -> str:
    return "data:image/png;base64," + _logo_b64(key, branding.logo_stamp(key), px)


def inject_css() -> None:
    s = branding.get_settings()
    primary, accent = s["primary_color"], s["accent_color"]
    size = int(s.get("logo_display_px", 64))
    st.html(f"""
<style>
:root {{ --tn-navy:{primary}; --tn-gold:{accent}; --tn-cream:#FBF7EE; --tn-line:#E7E2D5; --tn-muted:#5A6478; }}
.block-container {{ padding-top: 1.1rem; padding-bottom: 3rem; max-width: 1280px; }}
h1, h2, h3 {{ color: var(--tn-navy); letter-spacing: -.01em; }}
.tn-header {{ display:flex; align-items:center; gap:14px; color:#fff; padding:12px 18px; border-radius:16px;
  margin: 0 0 16px 0; background: linear-gradient(135deg, var(--tn-navy) 0%, color-mix(in srgb, var(--tn-navy) 82%, #fff) 100%);
  border-bottom: 3px solid var(--tn-gold); box-shadow: 0 4px 14px rgba(27,42,74,.12); }}
.tn-header img {{ width:{size}px; height:{size}px; object-fit:contain; background:#fff; border-radius:50%; padding:3px; flex:none; }}
.tn-header .t1 {{ font-weight:700; font-size:1.06rem; line-height:1.25; }}
.tn-header .t2 {{ color:var(--tn-gold); font-size:.84rem; }}
.tn-header .t3 {{ font-size:.78rem; opacity:.85; font-style:italic; }}
.tn-header .user {{ margin-left:auto; text-align:right; font-size:.8rem; opacity:.92; }}
.tn-kpi-grid {{ display:grid; grid-template-columns:repeat(var(--n, 4), minmax(0, 1fr)); gap:12px; }}
.tn-kpi {{ background:#fff; border:1px solid var(--tn-line); border-radius:14px; padding:12px 14px;
  border-left:5px solid var(--c, var(--tn-navy)); min-width:0; }}
.tn-kpi .v {{ font-size:1.65rem; font-weight:700; color:var(--tn-navy); line-height:1.15; }}
.tn-kpi .l {{ font-size:.8rem; color:var(--tn-muted); }}
.tn-kpi .h {{ font-size:.74rem; color:var(--tn-muted); }}
.tn-badge {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:.76rem; font-weight:600;
  color:#fff; background:var(--c, #9AA3B2); white-space:nowrap; }}
.tn-chips {{ display:flex; flex-wrap:wrap; gap:6px; margin:2px 0 6px; }}
.tn-chip {{ display:inline-flex; align-items:center; gap:5px; padding:4px 10px; border-radius:999px; font-size:.82rem;
  background:color-mix(in srgb, var(--c) 12%, #fff); border:1px solid color-mix(in srgb, var(--c) 40%, #fff); color:#1B2A4A; }}
.tn-chip::before {{ content:""; width:8px; height:8px; border-radius:50%; background:var(--c); }}
.tn-card {{ background:#fff; border:1px solid var(--tn-line); border-radius:14px; padding:14px 16px; }}
.tn-result {{ border-radius:16px; padding:16px 18px; color:#fff; }}
.tn-result .n {{ font-size:1.35rem; font-weight:700; }} .tn-result .m {{ opacity:.95; }}
.tn-row-name {{ font-weight:600; color:var(--tn-navy); line-height:1.25; }}
.tn-row-meta {{ font-size:.76rem; color:var(--tn-muted); }}
.tn-muted {{ color: var(--tn-muted); font-size:.85rem; }}
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{ border-radius:10px; min-height:44px; font-weight:600; }}
div[data-testid="stSegmentedControl"] button {{ min-height:40px; }}
@media (max-width: 900px) {{ .tn-kpi-grid {{ grid-template-columns:repeat(3, minmax(0, 1fr)); }} }}
@media (max-width: 640px) {{
  .block-container {{ padding-left:.75rem; padding-right:.75rem; padding-top:3.6rem; }}
  h1 {{ font-size:1.75rem !important; }}
  .tn-header {{ padding:10px 12px; gap:10px; }}
  .tn-header img {{ width:44px; height:44px; }}
  .tn-header .user, .tn-header .t3 {{ display:none; }}
  .tn-kpi-grid {{ grid-template-columns:repeat(var(--m, 2), minmax(0, 1fr)); gap:8px; }}
  .tn-kpi {{ padding:8px 10px; border-left-width:4px; }}
  .tn-kpi .v {{ font-size:1.2rem; }} .tn-kpi .l {{ font-size:.74rem; }} .tn-kpi .h {{ display:none; }}
  [class*="st-key-tnrow_"] [data-variant="segmented_control"] [data-testid="stIconEmoji"] {{ display:none; }}
  [class*="st-key-tnrow_"] [data-variant="segmented_control"] p {{ font-size:.86rem; white-space:nowrap; }}
  [class*="st-key-tnrow_"] button[data-variant="segmented_control"] {{ padding-left:6px !important; padding-right:6px !important;
    flex:1 1 auto; min-width:0; }}
  [class*="st-key-tnrow_"] button[data-variant="segmented_control"] > div,
  [class*="st-key-tnrow_"] button[data-variant="segmented_control"] > div > span {{ gap:0 !important; justify-content:center; }}
  [class*="st-key-tnrow_"] {{ padding:10px 12px !important; gap:6px !important; }}
}}
</style>""")


def header(actor=None, year_name: str | None = None) -> None:
    s = branding.get_settings()
    lines = [html.escape(s["xudoan_name"])]
    sub = " · ".join(html.escape(x) for x in (s["parish_name"], s.get("diocese")) if x)
    motto = html.escape(s.get("motto") or "")
    user = ""
    if actor:
        user = (f"<div class='user'><b>{html.escape(actor.full_name)}</b><br>{C.ROLE_LABELS.get(actor.role, '')}"
                f"{'<br>Năm học ' + html.escape(year_name) if year_name else ''}</div>")
    st.html(f"""<div class="tn-header"><img src="{logo_data_uri()}" alt="Logo">
<div><div class="t1">{lines[0]}</div><div class="t2">{sub}</div>{f'<div class="t3">{motto}</div>' if motto else ''}</div>
{user}</div>""")


def kpi(label: str, value, color: str | None = None, hint: str | None = None) -> str:
    return (f"<div class='tn-kpi' style='--c:{color or 'var(--tn-navy)'}'><div class='l'>{html.escape(label)}</div>"
            f"<div class='v'>{html.escape(str(value))}</div>{f'<div class=h>{html.escape(hint)}</div>' if hint else ''}</div>")


def kpi_row(items: list[tuple], per_row: int = 4) -> None:
    """Lưới thẻ số liệu: per_row cột trên máy tính, 2–3 cột trên điện thoại (không xếp 1 cột dài)."""
    cells = "".join(kpi(*item) for item in items)
    st.html(f"<div class='tn-kpi-grid' style='--n:{per_row}'>{cells}</div>")


def badge(status: str) -> str:
    return f"<span class='tn-badge' style='--c:{C.STATUS_COLORS[status]}'>{C.STATUS_LABELS[status]}</span>"


def pct(value) -> str:
    return "—" if value is None else f"{value:.1f}%"
