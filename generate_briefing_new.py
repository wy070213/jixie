#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI+HW 2035 论文自动化简报生成器（Path 2 · matplotlib PNG 版）
================================================================
产出物：项目根目录 briefing.png（16:9, 300 DPI, 单图海报）

版式（自上而下 3 大区域）：
    A. 顶部标题区   —— 论文标题 + 核心愿景（1000×）
    B. 中部 3 列表格 —— 三大层级 × 关键技术
    C. 底部时间轴   —— 近期 2025-2030 vs 远期 2030-2035

不依赖 LLM / API / 网络，仅需 matplotlib。
"""

# ---------------------------------------------------------------------------
# Windows GBK 终端兼容：把 stdout 包一层 UTF-8，避免中文/符号编码报错
# ---------------------------------------------------------------------------
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle


# =============================================================================
# 配置区
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PNG = BASE_DIR / "briefing.png"

# 画布：16:9，高清 300 DPI
FIG_W_IN = 16.0
FIG_H_IN = 9.0
FIG_DPI = 300

# 商务简约配色
COLOR_PRIMARY = "#1F3A5F"      # 主深蓝（标题 / 表头）
COLOR_TEXT = "#333333"         # 正文深灰
COLOR_SUBTLE = "#6B7280"       # 副文本灰
COLOR_BORDER = "#B8C2CC"       # 表格线
COLOR_ZEBRA = "#F5F7FA"        # 表格斑马纹
COLOR_NEAR_BG = "#D6E6F5"      # 近期时间段浅蓝
COLOR_FAR_BG = "#FCE5CD"       # 远期时间段浅橙
COLOR_AXIS = "#4A4A4A"         # 时间轴主线
COLOR_ACCENT = "#3B7EB5"       # 强调色（分隔线等）


# 论文内容（按用户规范硬编码 —— 无需 LLM）
PAPER_TITLE = "AI + HW 2035"
CORE_VISION = "面向 2035 的 AI 硬件融合，实现算力规模 1000× 提升"

TABLE_HEADERS = ["底层硬件层", "中间编译调度层", "上层 AI 模型层"]
# 按行组织：TABLE_CONTENT[r][c] = 第 r 行第 c 列的技术
# 列 0=底层硬件层 / 列 1=中间编译调度层 / 列 2=上层 AI 模型层
TABLE_CONTENT = [
    ["存算一体芯片", "算子硬件适配", "轻量化大模型"],
    ["3D 堆叠存储", "异构算力调度", "混合精度训练"],
    ["低功耗专用 NPU", "内存带宽优化", "分布式推理"],
]

TIMELINE_NEAR = {
    "label": "近期技术  2025 - 2030",
    "items": ["成熟存算一体", "通用异构加速", "轻量化模型落地"],
}
TIMELINE_FAR = {
    "label": "远期技术  2030 - 2035",
    "items": ["全光 AI 硬件", "类脑计算", "全域 1000× 算力达成"],
}


# =============================================================================
# 字体：自动挑选可用的中文字体，避免豆腐块
# =============================================================================

def setup_chinese_font() -> None:
    preferred = [
        "Microsoft YaHei", "SimHei", "PingFang SC",
        "Noto Sans CJK SC", "Arial Unicode MS", "DejaVu Sans",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    chosen = next((f for f in preferred if f in available), None)
    if chosen:
        print("使用中文字体：" + chosen)
        matplotlib.rcParams["font.sans-serif"] = [chosen] + preferred
    else:
        print("未找到常用中文字体，建议安装 Microsoft YaHei 或 SimHei")
        matplotlib.rcParams["font.sans-serif"] = preferred
    matplotlib.rcParams["axes.unicode_minus"] = False


# =============================================================================
# 通用工具：把 GridSpec 单元转成 0..100 × 0..100 无坐标画布
# =============================================================================

def make_panel(fig, gs_cell):
    ax = fig.add_subplot(gs_cell)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_axis_off()
    return ax


# =============================================================================
# 区域 A —— 顶部标题区
# =============================================================================

def draw_header(fig, gs_cell) -> None:
    ax = make_panel(fig, gs_cell)

    # 右上角小字
    ax.text(
        99, 90, "核心愿景 · Vision Briefing",
        ha="right", va="top",
        fontsize=11, color=COLOR_SUBTLE,
    )

    # 主标题
    ax.text(
        50, 60, PAPER_TITLE,
        ha="center", va="center",
        fontsize=44, fontweight="bold", color=COLOR_PRIMARY,
    )

    # 副标题（核心愿景）
    ax.text(
        50, 25, CORE_VISION,
        ha="center", va="center",
        fontsize=15, color=COLOR_TEXT,
    )

    # 底部分隔条
    ax.add_patch(Rectangle(
        (10, 6), 80, 0.6,
        facecolor=COLOR_ACCENT, edgecolor="none",
    ))


# =============================================================================
# 区域 B —— 中部 3 列表格
# =============================================================================

def draw_table(fig, gs_cell) -> None:
    ax = make_panel(fig, gs_cell)

    # 表格区域参数（都在 0..100 的画布坐标下）
    left = 4.0
    right = 96.0
    top = 96.0
    n_cols = 3
    n_rows_body = len(TABLE_CONTENT)

    col_w = (right - left) / n_cols
    header_h = 12.0
    body_h = (top - 4.0 - header_h) / n_rows_body

    # ---- 表头（深蓝底 + 白字） -------------------------------------------
    for c, title in enumerate(TABLE_HEADERS):
        x = left + c * col_w
        ax.add_patch(Rectangle(
            (x, top - header_h), col_w, header_h,
            facecolor=COLOR_PRIMARY, edgecolor=COLOR_PRIMARY, linewidth=1.0,
        ))
        ax.text(
            x + col_w / 2, top - header_h / 2, title,
            ha="center", va="center",
            fontsize=17, fontweight="bold", color="white",
        )

    # ---- 表体（斑马纹 + bullet 文字） -------------------------------------
    for r, row in enumerate(TABLE_CONTENT):
        y = top - header_h - (r + 1) * body_h
        row_bg = COLOR_ZEBRA if r % 2 == 0 else "white"
        for c, cell_text in enumerate(row):
            x = left + c * col_w
            ax.add_patch(Rectangle(
                (x, y), col_w, body_h,
                facecolor=row_bg, edgecolor="none",
            ))
            ax.text(
                x + col_w / 2, y + body_h / 2,
                "•  " + cell_text,
                ha="center", va="center",
                fontsize=14, color=COLOR_TEXT,
            )

    # ---- 表格外框 + 内部横竖线 -------------------------------------------
    table_top = top
    table_bottom = top - header_h - n_rows_body * body_h

    # 外框
    ax.add_patch(Rectangle(
        (left, table_bottom),
        right - left, table_top - table_bottom,
        facecolor="none", edgecolor=COLOR_BORDER, linewidth=1.4,
    ))
    # 横线：表头下 + 每行下
    ax.hlines(
        [top - header_h] + [top - header_h - (r + 1) * body_h for r in range(n_rows_body - 1)],
        xmin=left, xmax=right,
        colors=COLOR_BORDER, linewidth=1.0,
    )
    # 竖线：两根内部竖线
    ax.vlines(
        [left + col_w, left + 2 * col_w],
        ymin=table_bottom, ymax=table_top,
        colors=COLOR_BORDER, linewidth=1.0,
    )


# =============================================================================
# 区域 C —— 底部时间轴
# =============================================================================

def draw_timeline(fig, gs_cell) -> None:
    ax = make_panel(fig, gs_cell)

    # 背景色块：近期左半 / 远期右半
    ax.add_patch(Rectangle(
        (2, 12), 47, 80,
        facecolor=COLOR_NEAR_BG, edgecolor="none",
    ))
    ax.add_patch(Rectangle(
        (51, 12), 47, 80,
        facecolor=COLOR_FAR_BG, edgecolor="none",
    ))

    # 阶段标签（色块顶部）
    ax.text(
        25.5, 86, TIMELINE_NEAR["label"],
        ha="center", va="center",
        fontsize=15, fontweight="bold", color=COLOR_PRIMARY,
    )
    ax.text(
        74.5, 86, TIMELINE_FAR["label"],
        ha="center", va="center",
        fontsize=15, fontweight="bold", color="#B05A00",
    )

    # 时间轴主线（贯穿两段，箭头指向未来）
    axis_y = 50
    ax.add_patch(FancyArrowPatch(
        (3, axis_y), (97, axis_y),
        arrowstyle="->", mutation_scale=28,
        color=COLOR_AXIS, linewidth=2.5,
        shrinkA=0, shrinkB=0,
    ))

    # 近/远期分界虚线
    ax.vlines(
        50, ymin=14, ymax=90,
        colors=COLOR_PRIMARY, linewidth=1.2, linestyles="dashed",
    )

    # 节点：3 近 + 3 远，均匀分布在各自色块中
    near_xs = [10.5, 25.5, 40.5]
    far_xs = [59.5, 74.5, 89.5]

    def _draw_node(x: float, y: float, text: str, above: bool) -> None:
        # 圆点
        ax.add_patch(Circle(
            (x, y), 1.3,
            facecolor=COLOR_PRIMARY, edgecolor="white",
            linewidth=1.8, zorder=5,
        ))
        # 文字位置：上方 / 下方
        if above:
            ax.text(
                x, y + 8, text,
                ha="center", va="center",
                fontsize=12, color=COLOR_TEXT,
            )
            ax.plot(
                [x, x], [y + 1.5, y + 5.5],
                color=COLOR_AXIS, linewidth=0.9,
            )
        else:
            ax.text(
                x, y - 8, text,
                ha="center", va="center",
                fontsize=12, color=COLOR_TEXT,
            )
            ax.plot(
                [x, x], [y - 1.5, y - 5.5],
                color=COLOR_AXIS, linewidth=0.9,
            )

    # 近期：3 个节点上方
    for x, txt in zip(near_xs, TIMELINE_NEAR["items"]):
        _draw_node(x, axis_y, txt, above=True)

    # 远期：3 个节点下方（避免与上方冲撞，形成上下错落）
    for x, txt in zip(far_xs, TIMELINE_FAR["items"]):
        _draw_node(x, axis_y, txt, above=False)

    # 底部脚注
    ax.text(
        50, 4, "Path 2 - briefing.png 信息海报  |  Generated by matplotlib",
        ha="center", va="center",
        fontsize=9, color=COLOR_SUBTLE,
    )


# =============================================================================
# 主入口
# =============================================================================

def build_briefing(output_path: Path) -> None:
    setup_chinese_font()

    fig = plt.figure(figsize=(FIG_W_IN, FIG_H_IN), dpi=FIG_DPI)
    fig.patch.set_facecolor("white")

    gs = fig.add_gridspec(
        nrows=3, ncols=1,
        height_ratios=[1.1, 3.4, 2.5],
        hspace=0.06,
        left=0.03, right=0.97, top=0.97, bottom=0.03,
    )

    draw_header(fig, gs[0, 0])
    draw_table(fig, gs[1, 0])
    draw_timeline(fig, gs[2, 0])

    fig.savefig(
        output_path,
        dpi=FIG_DPI,
        facecolor="white",
        bbox_inches="tight",
        pad_inches=0.2,
    )
    plt.close(fig)


def main() -> int:
    print("============================================================")
    print("AI+HW 2035 简报生成器 (Path 2 - PNG)")
    print("============================================================")
    try:
        build_briefing(OUTPUT_PNG)
    except Exception as exc:
        print("生成失败：" + str(exc))
        return 1
    print("briefing.png 已生成至项目根目录")
    return 0


if __name__ == "__main__":
    sys.exit(main())
