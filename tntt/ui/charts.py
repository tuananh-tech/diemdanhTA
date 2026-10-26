"""Biểu đồ Plotly thống nhất: màu trạng thái cố định kèm nhãn, nét mảnh, một trục, có hover."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .. import constants as C

FONT = "Be Vietnam Pro, system-ui, sans-serif"
INK, MUTED, GRID = "#1B2A4A", "#5A6478", "#ECE8DD"
ORDER = [C.PRESENT, C.LATE, C.EXCUSED, C.ABSENT, C.UNMARKED]


def _layout(fig: go.Figure, height: int = 320, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), font=dict(family=FONT, color=INK, size=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title_text=""),
        hoverlabel=dict(font_family=FONT), bargap=0.35,
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID, tickfont=dict(color=MUTED))
    return fig


def status_by_group(stats: pd.DataFrame, group_col: str, height: int | None = None) -> go.Figure:
    """Thanh ngang chồng theo trạng thái cho từng nhóm (lớp/ngành)."""
    fig = go.Figure()
    stats = stats.sort_values(group_col, ascending=False)
    for st in ORDER:
        if st in stats and stats[st].sum() > 0:
            fig.add_bar(y=stats[group_col], x=stats[st], name=C.STATUS_LABELS[st], orientation="h",
                        marker=dict(color=C.STATUS_COLORS[st], line=dict(color="#FFFFFF", width=2)),
                        hovertemplate="%{y}<br>" + C.STATUS_LABELS[st] + ": %{x}<extra></extra>")
    fig.update_layout(barmode="stack")
    return _layout(fig, height or max(220, 46 * len(stats) + 60))


def rate_trend(stats: pd.DataFrame, x: str) -> go.Figure:
    stats = stats.sort_values(x)
    fig = go.Figure(go.Scatter(
        x=stats[x], y=stats["rate"], mode="lines+markers", name="Chuyên cần",
        line=dict(color=INK, width=2), marker=dict(size=8, color=INK, line=dict(color="#fff", width=2)),
        customdata=stats[["marked"]], hovertemplate="%{x}<br>Chuyên cần: %{y:.1f}%<br>Đã có kết quả: %{customdata[0]}<extra></extra>"))
    fig.update_yaxes(range=[0, 105], ticksuffix="%")
    return _layout(fig, 300, legend=False)


def status_donut(summary: dict) -> go.Figure:
    labels = [C.STATUS_LABELS[s] for s in ORDER if summary.get(s)]
    values = [summary[s] for s in ORDER if summary.get(s)]
    colors = [C.STATUS_COLORS[s] for s in ORDER if summary.get(s)]
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.62, sort=False,
                           marker=dict(colors=colors, line=dict(color="#fff", width=2)),
                           textinfo="percent", hovertemplate="%{label}: %{value} (%{percent})<extra></extra>"))
    return _layout(fig, 300)


def rate_bars(stats: pd.DataFrame, group_col: str, threshold: float | None = None) -> go.Figure:
    stats = stats.sort_values("rate")
    fig = go.Figure(go.Bar(
        y=stats[group_col], x=stats["rate"], orientation="h", marker=dict(color=INK), name="Chuyên cần",
        text=stats["rate"].map(lambda v: "" if pd.isna(v) else f"{v:.0f}%"), textposition="outside",
        hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
    if threshold:
        fig.add_vline(x=threshold, line=dict(color=C.STATUS_COLORS[C.ABSENT], width=1, dash="dot"),
                      annotation_text=f"Ngưỡng {threshold:.0f}%", annotation_font_color=MUTED)
    fig.update_xaxes(range=[0, 110], ticksuffix="%")
    return _layout(fig, max(220, 40 * len(stats) + 60), legend=False)
