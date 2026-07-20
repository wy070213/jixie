#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI+HW 2035 论文自动化简报生成器 · 最优综合版（Path 2 · PNG）
================================================================
一份脚本，同时满足：
    ① 任务书 Prompt Engineering + API 调用 + JSON Schema + 自修正
    ② 任务书三层语义（Hardware / Algorithm / Application）
    ③ 任务书时间轴二分（近期 2-5 年 / 远期 6-10 年）
    ④ 离线兜底：无 API Key / 无网络也能出图（内容硬编码）
    ⑤ Windows GBK 终端安全（io.TextIOWrapper 兜底）
    ⑥ 视觉商务简约：16:9 · 300 DPI · 蓝主色 + 双色时间轴

产出物：
    - briefing.png          最终 PNG 海报
    - extracted_info.json   LLM 成功抽取时的中间产物
    - error.log             WARNING 级以上日志
"""

# ---------------------------------------------------------------------------
# Windows GBK 终端兼容 —— 放在最顶部，早于任何 print
# ---------------------------------------------------------------------------
import sys
import io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

import matplotlib
matplotlib.use("Agg")

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle

# ---- 可选依赖：装了就用 LLM 模式，没装/没配就自动走离线兜底 -----------------
try:
    import httpx
except ImportError:
    httpx = None

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):  # noqa: D401
        return False

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# =============================================================================
# 配置
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
_PDF_CANDIDATES = [BASE_DIR / "AI+HW2035.pdf", BASE_DIR / "AI+HW 2035.pdf"]
DEFAULT_PDF: Path = next((p for p in _PDF_CANDIDATES if p.exists()), _PDF_CANDIDATES[0])
OUTPUT_PNG = BASE_DIR / "briefing.png"
EXTRACTED_JSON = BASE_DIR / "extracted_info.json"
LOG_PATH = BASE_DIR / "error.log"

# 画布 16:9 · 300 DPI
FIG_W_IN, FIG_H_IN, FIG_DPI = 16.0, 9.0, 300

# 商务简约配色
C_PRIMARY = "#1F3A5F"
C_ACCENT = "#3B7EB5"
C_TEXT = "#333333"
C_SUBTLE = "#6B7280"
C_BORDER = "#B8C2CC"
C_ZEBRA = "#F5F7FA"
C_CARD = "#FFFFFF"
C_NEAR_BG = "#D6E6F5"
C_FAR_BG = "#FCE5CD"
C_FAR_TEXT = "#B05A00"
C_AXIS = "#4A4A4A"

# LLM 参数
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS = 2048
LLM_TIMEOUT_SEC = 60.0
LLM_MAX_ATTEMPTS = 3


# =============================================================================
# 离线兜底内容（LLM 不可用时使用；同时也是 few-shot 语义示范）
# =============================================================================

FALLBACK_DATA: dict[str, Any] = {
    "paper_title": "AI + HW 2035",
    "core_vision": "面向 2035 的 AI 硬件融合，实现算力规模 1000× 提升",
    "abstract": (
        "论文提出未来十年 AI 与硬件深度协同的愿景：通过芯片、编译与模型全栈联动，"
        "把每焦耳能量所提供的智能算力（Intelligence per Joule）相较 2020 年基线"
        "提升 1000 倍，支撑下一代通用智能落地。"
    ),
    "definition_1000x": (
        "1000× 效率提升以 Intelligence per Joule 为核心度量：每焦耳能量所交付的"
        "有效智能算力，覆盖训练与推理，跨越器件-架构-算法-系统四层协同。"
    ),
    "layers": {
        "hardware": {
            "name": "底层硬件层",
            "description": "面向 AI 负载的高能效硬件基础设施，为上层算法提供算力底座。",
            "key_tech": ["存算一体芯片", "3D 堆叠存储", "低功耗专用 NPU"],
        },
        "algorithm": {
            "name": "中间编译调度层",
            "description": "打通算法到硬件的软硬件协同栈，最大化硬件利用率。",
            "key_tech": ["算子硬件适配", "异构算力调度", "内存带宽优化"],
        },
        "application": {
            "name": "上层 AI 模型层",
            "description": "面向应用的高效 AI 模型与训练/推理范式。",
            "key_tech": ["轻量化大模型", "混合精度训练", "分布式推理"],
        },
    },
    "timeline": {
        "near_term": {
            "period": "2025 - 2030",
            "label": "近期技术",
            "items": ["成熟存算一体", "通用异构加速", "轻量化模型落地"],
        },
        "long_term": {
            "period": "2030 - 2035",
            "label": "远期技术",
            "items": ["全光 AI 硬件", "类脑计算", "全域 1000× 算力达成"],
        },
    },
}


# =============================================================================
# 日志（双 handler：文件 WARNING+ / 控制台 INFO+）
# =============================================================================

def _init_logger() -> logging.Logger:
    logger = logging.getLogger("briefing")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setLevel(logging.WARNING)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


LOGGER = _init_logger()


# =============================================================================
# JSON Schema 手写校验器（避免 jsonschema 依赖，逻辑清晰可控）
# =============================================================================

def validate_briefing(data: Any) -> list[str]:
    """返回错误列表；空列表 = 通过。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["顶层必须是对象"]

    for k in ["paper_title", "core_vision", "abstract", "definition_1000x"]:
        v = data.get(k)
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{k} 缺失或不是非空字符串")

    layers = data.get("layers")
    if not isinstance(layers, dict):
        errors.append("layers 必须是对象")
    else:
        for lkey in ["hardware", "algorithm", "application"]:
            layer = layers.get(lkey)
            if not isinstance(layer, dict):
                errors.append(f"layers.{lkey} 缺失或不是对象")
                continue
            if not isinstance(layer.get("name"), str) or not layer["name"].strip():
                errors.append(f"layers.{lkey}.name 缺失")
            if not isinstance(layer.get("description"), str) or not layer["description"].strip():
                errors.append(f"layers.{lkey}.description 缺失")
            kt = layer.get("key_tech")
            if not isinstance(kt, list) or len(kt) < 2 or not all(isinstance(x, str) and x for x in kt):
                errors.append(f"layers.{lkey}.key_tech 必须为 >=2 个非空字符串数组")

    tl = data.get("timeline")
    if not isinstance(tl, dict):
        errors.append("timeline 必须是对象")
    else:
        for tkey in ["near_term", "long_term"]:
            phase = tl.get(tkey)
            if not isinstance(phase, dict):
                errors.append(f"timeline.{tkey} 缺失或不是对象")
                continue
            if not isinstance(phase.get("period"), str) or not phase["period"].strip():
                errors.append(f"timeline.{tkey}.period 缺失")
            items = phase.get("items")
            if not isinstance(items, list) or len(items) < 2 or not all(isinstance(x, str) and x for x in items):
                errors.append(f"timeline.{tkey}.items 必须为 >=2 个非空字符串数组")
    return errors


# =============================================================================
# PDF 加载（可选，双通道降级）
# =============================================================================

def load_pdf(path: Path) -> Optional[str]:
    """读取 PDF；失败返回 None（由上层决定是否走兜底）。"""
    if not path.exists():
        LOGGER.warning("PDF 不存在: %s", path)
        return None

    # 通道 1：pdfplumber
    try:
        import pdfplumber  # type: ignore
        with pdfplumber.open(path) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages).strip()
        if text:
            LOGGER.info("pdfplumber 提取成功 (%d 字符)", len(text))
            return text
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("pdfplumber 失败: %s", exc)

    # 通道 2：pypdf
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(str(path))
        text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
        if text:
            LOGGER.info("pypdf 提取成功 (%d 字符)", len(text))
            return text
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("pypdf 失败: %s", exc)

    return None


# =============================================================================
# LLM 客户端与调用（带重试）
# =============================================================================

def _build_llm_client() -> Optional[tuple[Any, str]]:
    """构建 OpenAI 兼容客户端；缺条件时返回 None，交给上层兜底。"""
    if OpenAI is None:
        LOGGER.warning("openai 库未安装，跳过 LLM 模式")
        return None
    load_dotenv(BASE_DIR / ".env", override=False)
    api_key = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or ""
    ).strip()
    base_url = (os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or "").strip() or None
    model = (os.getenv("MODEL_NAME") or os.getenv("LLM_MODEL") or "deepseek-chat").strip()
    if not api_key:
        LOGGER.warning("未检测到 API Key，跳过 LLM 模式")
        return None

    http_client = None
    if httpx is not None:
        trust_env = os.getenv("LLM_TRUST_ENV", "").lower() == "true"
        try:
            http_client = httpx.Client(
                timeout=LLM_TIMEOUT_SEC,
                trust_env=trust_env,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("httpx.Client 构建失败，使用默认: %s", exc)

    kwargs = {"api_key": api_key, "timeout": LLM_TIMEOUT_SEC}
    if base_url:
        kwargs["base_url"] = base_url
    if http_client is not None:
        kwargs["http_client"] = http_client
    return OpenAI(**kwargs), model


def _retry(fn: Callable[[], Any], attempts: int = LLM_MAX_ATTEMPTS,
           base_delay: float = 1.5) -> Any:
    """指数退避重试。"""
    last_exc: Optional[Exception] = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if i < attempts:
                delay = base_delay * (2 ** (i - 1))
                LOGGER.warning("第 %d 次尝试失败: %s；%.1fs 后重试", i, exc, delay)
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc


_MD_FENCE = re.compile(r"^```(?:json|JSON)?\s*|\s*```$", re.MULTILINE)


def _strip_and_extract_json(raw: str) -> str:
    """去 Markdown 围栏、抽取首个完整 JSON 对象。"""
    cleaned = _MD_FENCE.sub("", raw).strip()
    l, r = cleaned.find("{"), cleaned.rfind("}")
    if l >= 0 and r > l:
        cleaned = cleaned[l:r + 1]
    return cleaned


SYSTEM_PROMPT = (
    "你是一名资深技术分析师，擅长将学术论文的关键论点浓缩为结构化 JSON。"
    "严格按要求输出合法 JSON，不解释、不使用 Markdown 代码块、不添加额外字段。"
)


def _build_extract_prompt(paper_text: str) -> str:
    schema_hint = json.dumps({
        "paper_title": "string",
        "core_vision": "string, 30-90 字, 突出 1000× 或 Intelligence per Joule",
        "abstract": "string, 80-220 字, 覆盖问题定义与主要主张",
        "definition_1000x": "string, 60-200 字, 阐述 1000× 效率提升的具体含义与度量维度",
        "layers": {
            "hardware": {"name": "中文层名", "description": "30-120 字", "key_tech": ["3-5 项关键技术"]},
            "algorithm": {"name": "中文层名", "description": "30-120 字", "key_tech": ["3-5 项关键技术"]},
            "application": {"name": "中文层名", "description": "30-120 字", "key_tech": ["3-5 项关键技术"]},
        },
        "timeline": {
            "near_term": {"period": "如 '2025-2030'", "label": "如 '近期技术'", "items": ["3 项技术趋势"]},
            "long_term": {"period": "如 '2030-2035'", "label": "如 '远期技术'", "items": ["3 项技术趋势"]},
        },
    }, ensure_ascii=False, indent=2)

    return (
        "请阅读下面论文《AI+HW 2035: Shaping the Next Decade》文本，"
        "按任务书要求提取三大维度：\n"
        "① 核心目标：论文提出的 1000× 效率提升定义（Intelligence per Joule）；\n"
        "② 三大层级：Hardware（硬件层）/ Algorithm（算法层）/ Application（应用层）"
        "  的中文层名、职责描述、关键技术；\n"
        "③ 时间轴：近期（2-5 年，约 2025-2030）与 远期（6-10 年，约 2030-2035）"
        "  的关键技术趋势（如 3D Integration, Photonics 等）。\n\n"
        "严格按以下 JSON 结构输出（字段类型见示意）：\n"
        f"{schema_hint}\n\n"
        f"===== 原文开始 =====\n{paper_text}\n===== 原文结束 =====\n"
        "只输出 JSON，不要任何其他文字。"
    )


def _build_fix_prompt(bad_data: dict, errors: list[str]) -> str:
    return (
        "上一次输出未通过 JSON Schema 校验，请根据下列错误重新输出**完整合法 JSON**。\n"
        "错误列表：\n- " + "\n- ".join(errors) + "\n\n"
        "错误 JSON：\n" + json.dumps(bad_data, ensure_ascii=False, indent=2) + "\n\n"
        "只输出修正后的完整 JSON，不要任何其他文字。"
    )


def _call_llm(client: Any, model: str, user_prompt: str) -> dict:
    def _do() -> dict:
        LOGGER.info("调用 LLM (model=%s, prompt=%d 字符)", model, len(user_prompt))
        resp = client.chat.completions.create(
            model=model,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if not raw:
            raise ValueError("LLM 返回空内容")
        cleaned = _strip_and_extract_json(raw)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 解析失败: {exc}") from exc

    return _retry(_do)


def extract_via_llm(paper_text: str) -> Optional[dict]:
    """LLM 抽取 + Schema 校验 + 1 次自修正；任何环节失败返回 None（走兜底）。"""
    ctx = _build_llm_client()
    if ctx is None:
        return None
    client, model = ctx

    try:
        data = _call_llm(client, model, _build_extract_prompt(paper_text))
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("LLM 首次抽取失败: %s", exc)
        return None

    errs = validate_briefing(data)
    if not errs:
        LOGGER.info("LLM 抽取 + Schema 校验一次通过")
        return data

    LOGGER.warning("Schema 校验失败 %d 条，触发自修正: %s", len(errs), errs[:3])
    try:
        data = _call_llm(client, model, _build_fix_prompt(data, errs))
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("LLM 自修正调用失败: %s", exc)
        return None
    errs2 = validate_briefing(data)
    if errs2:
        LOGGER.warning("自修正后仍未通过: %s", errs2[:3])
        return None
    LOGGER.info("自修正后 Schema 校验通过")
    return data


def get_briefing_data(pdf_path: Path, use_llm: bool) -> tuple[dict, str]:
    """
    统一入口：优先 LLM 抽取，失败时兜底为 FALLBACK_DATA。
    返回 (data, source_tag)，source_tag ∈ {"llm", "fallback"}。
    """
    if use_llm:
        text = load_pdf(pdf_path)
        if text:
            data = extract_via_llm(text)
            if data is not None:
                try:
                    EXTRACTED_JSON.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    LOGGER.info("中间产物已保存: %s", EXTRACTED_JSON.name)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("extracted_info.json 保存失败: %s", exc)
                return data, "llm"
        LOGGER.warning("LLM 链路不可用，使用离线兜底内容")
    else:
        LOGGER.info("已通过 --no-llm 显式跳过 LLM，使用离线兜底内容")
    return FALLBACK_DATA, "fallback"


# =============================================================================
# 字体
# =============================================================================

def setup_chinese_font() -> None:
    preferred = [
        "Microsoft YaHei", "SimHei", "PingFang SC",
        "Noto Sans CJK SC", "Arial Unicode MS", "DejaVu Sans",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    chosen = next((f for f in preferred if f in available), None)
    if chosen:
        LOGGER.info("使用中文字体: %s", chosen)
        matplotlib.rcParams["font.sans-serif"] = [chosen] + preferred
    else:
        LOGGER.warning("未找到常用中文字体，建议安装 Microsoft YaHei")
        matplotlib.rcParams["font.sans-serif"] = preferred
    matplotlib.rcParams["axes.unicode_minus"] = False


# =============================================================================
# 视觉工具
# =============================================================================

def _visual_wrap(text: str, max_visual_width: int) -> str:
    """按视觉宽度换行：CJK=2、ASCII=1，避免中英混排换行不齐。"""
    if not text:
        return ""
    lines: list[str] = []
    for para in text.split("\n"):
        buf, w = "", 0
        for ch in para:
            cw = 2 if ord(ch) > 0x2E80 else 1
            if w + cw > max_visual_width and buf:
                lines.append(buf)
                buf, w = ch, cw
            else:
                buf += ch
                w += cw
        if buf:
            lines.append(buf)
    return "\n".join(lines)


def _panel(fig, gs_cell):
    """把 GridSpec 单元转成 0..100 × 0..100 无坐标画布。"""
    ax = fig.add_subplot(gs_cell)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_axis_off()
    return ax


def _card(ax, *, x, y, w, h, bg=C_CARD, border=C_BORDER, radius=0.6, lw=1.0):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.02,rounding_size={radius}",
        facecolor=bg, edgecolor=border, linewidth=lw,
    ))


# =============================================================================
# 区域 A — 标题
# =============================================================================

def draw_header(fig, gs_cell, data: dict) -> None:
    ax = _panel(fig, gs_cell)
    ax.text(
        99, 92, "AI + HW 2035 Briefing · Vision Report",
        ha="right", va="top", fontsize=10, color=C_SUBTLE,
    )
    ax.text(
        50, 62, data.get("paper_title", "AI + HW 2035"),
        ha="center", va="center",
        fontsize=42, fontweight="bold", color=C_PRIMARY,
    )
    ax.text(
        50, 24, data.get("core_vision", ""),
        ha="center", va="center",
        fontsize=14, color=C_TEXT,
    )
    ax.add_patch(Rectangle((14, 5), 72, 0.7, facecolor=C_ACCENT, edgecolor="none"))


# =============================================================================
# 区域 B — 摘要 + 1000× 定义双卡
# =============================================================================

def draw_info_banner(fig, gs_cell, data: dict) -> None:
    ax = _panel(fig, gs_cell)

    gap = 2.0
    card_w = (100 - gap * 3) / 2
    y, h = 4, 92  # 尽量占满 Zone B

    # 左卡：摘要
    left_x = gap
    _card(ax, x=left_x, y=y, w=card_w, h=h, bg=C_ZEBRA, border=C_BORDER)
    ax.text(
        left_x + 1.8, y + h - 6, "◆ 论文摘要",
        ha="left", va="top", fontsize=11, fontweight="bold", color=C_PRIMARY,
    )
    ax.text(
        left_x + 1.8, y + h - 22,
        _visual_wrap(data.get("abstract", ""), int(card_w * 1.65)),
        ha="left", va="top", fontsize=8.5, color=C_TEXT, linespacing=1.45,
    )

    # 右卡：1000× 定义
    right_x = gap * 2 + card_w
    _card(ax, x=right_x, y=y, w=card_w, h=h, bg=C_CARD, border=C_PRIMARY, lw=1.4)
    ax.text(
        right_x + 1.8, y + h - 6, "◆ 1000× 效率定义（Intelligence per Joule）",
        ha="left", va="top", fontsize=11, fontweight="bold", color=C_PRIMARY,
    )
    ax.text(
        right_x + 1.8, y + h - 22,
        _visual_wrap(data.get("definition_1000x", ""), int(card_w * 1.65)),
        ha="left", va="top", fontsize=8.5, color=C_TEXT, linespacing=1.45,
    )


# =============================================================================
# 区域 C — 三层级 3 列表格
# =============================================================================

def draw_layers_table(fig, gs_cell, data: dict) -> None:
    ax = _panel(fig, gs_cell)

    layers = data.get("layers", {})
    order = [
        ("hardware", "Hardware · 硬件层"),
        ("algorithm", "Algorithm · 算法层"),
        ("application", "Application · 应用层"),
    ]

    left, right, top, bottom = 2.0, 98.0, 96.0, 3.0
    n = 3
    col_w = (right - left) / n
    header_h = 8.0

    for i, (key, fallback_label) in enumerate(order):
        layer = layers.get(key, {}) or {}
        x = left + i * col_w

        # 卡片主体
        _card(ax, x=x + 0.4, y=bottom, w=col_w - 0.8, h=top - bottom,
              bg=C_CARD, border=C_BORDER, lw=1.0)

        # 表头深蓝带
        ax.add_patch(Rectangle(
            (x + 0.4, top - header_h), col_w - 0.8, header_h,
            facecolor=C_PRIMARY, edgecolor="none",
        ))
        cn_name = layer.get("name") or fallback_label
        ax.text(
            x + col_w / 2, top - header_h / 2, cn_name,
            ha="center", va="center",
            fontsize=15, fontweight="bold", color="white",
        )

        # 层职责
        desc_y = top - header_h - 2
        ax.text(
            x + 2, desc_y, "◆ 层职责",
            ha="left", va="top", fontsize=10.5, fontweight="bold", color=C_PRIMARY,
        )
        ax.text(
            x + 2, desc_y - 4.5,
            _visual_wrap(layer.get("description", ""), int(col_w * 1.4)),
            ha="left", va="top", fontsize=9.5, color=C_TEXT, linespacing=1.5,
        )

        # 分隔线
        divider_y = bottom + 42
        ax.add_patch(Rectangle(
            (x + 2, divider_y), col_w - 4, 0.18,
            facecolor=C_BORDER, edgecolor="none",
        ))
        ax.text(
            x + 2, divider_y - 2, "◆ 关键技术",
            ha="left", va="top", fontsize=10.5, fontweight="bold", color=C_PRIMARY,
        )
        for j, tech in enumerate(layer.get("key_tech", [])[:5]):
            ax.text(
                x + 3, divider_y - 7.5 - j * 6.5,
                "•  " + _visual_wrap(str(tech), int(col_w * 1.3)),
                ha="left", va="top", fontsize=11, color=C_TEXT,
            )


# =============================================================================
# 区域 D — 时间轴（近浅蓝 / 远浅橙 · 双侧上下错落）
# =============================================================================

def draw_timeline(fig, gs_cell, data: dict) -> None:
    ax = _panel(fig, gs_cell)
    tl = data.get("timeline", {})
    near = tl.get("near_term", {}) or {}
    far = tl.get("long_term", {}) or {}

    # 背景色块
    ax.add_patch(Rectangle((2, 10), 47, 82, facecolor=C_NEAR_BG, edgecolor="none"))
    ax.add_patch(Rectangle((51, 10), 47, 82, facecolor=C_FAR_BG, edgecolor="none"))

    # 阶段标签
    near_label = f"{near.get('label', '近期技术')}  {near.get('period', '2025 - 2030')}"
    far_label = f"{far.get('label', '远期技术')}  {far.get('period', '2030 - 2035')}"
    ax.text(25.5, 86, near_label, ha="center", va="center",
            fontsize=14, fontweight="bold", color=C_PRIMARY)
    ax.text(74.5, 86, far_label, ha="center", va="center",
            fontsize=14, fontweight="bold", color=C_FAR_TEXT)

    # 主轴
    axis_y = 48
    ax.add_patch(FancyArrowPatch(
        (3, axis_y), (97, axis_y),
        arrowstyle="->", mutation_scale=26,
        color=C_AXIS, linewidth=2.4, shrinkA=0, shrinkB=0,
    ))
    # 中央分界虚线
    ax.vlines(50, ymin=12, ymax=90, colors=C_PRIMARY, linewidth=1.1, linestyles="dashed")

    def _node(x: float, text: str, above: bool) -> None:
        ax.add_patch(Circle(
            (x, axis_y), 1.2,
            facecolor=C_PRIMARY, edgecolor="white", linewidth=1.6, zorder=5,
        ))
        if above:
            ax.plot([x, x], [axis_y + 1.4, axis_y + 6], color=C_AXIS, linewidth=0.9)
            ax.text(x, axis_y + 10, text, ha="center", va="center",
                    fontsize=11.5, color=C_TEXT)
        else:
            ax.plot([x, x], [axis_y - 1.4, axis_y - 6], color=C_AXIS, linewidth=0.9)
            ax.text(x, axis_y - 10, text, ha="center", va="center",
                    fontsize=11.5, color=C_TEXT)

    near_xs = [10.5, 25.5, 40.5]
    far_xs = [59.5, 74.5, 89.5]
    for x, item in zip(near_xs, near.get("items", [])[:3]):
        _node(x, str(item), above=True)
    for x, item in zip(far_xs, far.get("items", [])[:3]):
        _node(x, str(item), above=False)


# =============================================================================
# 顶层：装配 & 保存
# =============================================================================

def build_briefing(data: dict, output_path: Path, source_tag: str) -> None:
    setup_chinese_font()

    fig = plt.figure(figsize=(FIG_W_IN, FIG_H_IN), dpi=FIG_DPI)
    fig.patch.set_facecolor("white")

    gs = fig.add_gridspec(
        nrows=4, ncols=1,
        height_ratios=[1.4, 1.9, 4.0, 2.7],
        hspace=0.08,
        left=0.03, right=0.97, top=0.98, bottom=0.03,
    )
    draw_header(fig, gs[0, 0], data)
    draw_info_banner(fig, gs[1, 0], data)
    draw_layers_table(fig, gs[2, 0], data)
    draw_timeline(fig, gs[3, 0], data)

    # 页脚水印（右下角）
    footer = "Generated by AI+HW 2035 Briefing Generator · " + (
        "LLM-extracted" if source_tag == "llm" else "offline-fallback"
    )
    fig.text(0.97, 0.008, footer, ha="right", va="bottom",
             fontsize=7, color=C_SUBTLE)

    fig.savefig(
        output_path, dpi=FIG_DPI, facecolor="white",
        bbox_inches="tight", pad_inches=0.15,
    )
    plt.close(fig)


# =============================================================================
# 入口
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="AI+HW 2035 简报生成器（最优综合版）")
    parser.add_argument("--input", "-i", type=Path, default=DEFAULT_PDF,
                        help=f"输入 PDF 路径（默认: {DEFAULT_PDF.name}）")
    parser.add_argument("--output", "-o", type=Path, default=OUTPUT_PNG,
                        help=f"输出 PNG 路径（默认: {OUTPUT_PNG.name}）")
    parser.add_argument("--no-llm", action="store_true",
                        help="跳过 LLM，直接用离线兜底内容")
    args = parser.parse_args()

    LOGGER.info("========= AI+HW 2035 简报生成器 · 最优综合版 =========")
    LOGGER.info("输入 PDF: %s", args.input)
    LOGGER.info("输出 PNG: %s", args.output)

    data, source = get_briefing_data(args.input, use_llm=not args.no_llm)

    errs = validate_briefing(data)
    if errs:
        LOGGER.warning("最终数据仍有 Schema 问题: %s", errs[:3])

    build_briefing(data, args.output, source)
    LOGGER.info("briefing.png 已生成: %s (数据来源: %s)", args.output, source)
    print("briefing.png 已生成至项目根目录，数据来源: " + source)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("未预期异常: %s", exc)
        print("生成失败，详见 error.log: " + str(exc))
        sys.exit(1)
