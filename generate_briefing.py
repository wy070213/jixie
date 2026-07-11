"""
AI+HW 2035 自动化简报生成器（PNG 版）
============================================

一次性流程：
    PDF → 双通道解析 → 语义分块 → LLM Map-Reduce 抽取 → JSON Schema 校验
        → matplotlib 300 DPI 单图海报（briefing.png）

产出物只有一份：`briefing.png`。文件采用科技蓝主色调（RGB 0,82,147）、
一体式四大模块（论文核心摘要 / AI 硬件三层架构 / 三段式技术时间轴 /
行业落地场景），可直接作为课程作业交付。

作者：Backend Engineering
适配环境：Windows + Git Bash + Python 3.13
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import matplotlib
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from jsonschema import Draft7Validator, ValidationError
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle
from openai import OpenAI
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# 使用非交互式后端，避免在 Git Bash 场景下弹出窗口或缺少 GUI 依赖
matplotlib.use("Agg")


# =============================================================================
# 【配置区】所有可调参数集中管理，禁止在函数体内出现硬编码
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent

# --- 输入 / 输出路径 ---
_CANDIDATE_PDFS = [BASE_DIR / "AI+HW2035.pdf", BASE_DIR / "AI+HW 2035.pdf"]
PDF_PATH: Path = next((p for p in _CANDIDATE_PDFS if p.exists()), _CANDIDATE_PDFS[0])
OUTPUT_PNG: Path = BASE_DIR / "briefing.png"
LOG_PATH: Path = BASE_DIR / "error.log"

# --- LLM 参数 ---
LLM_TEMPERATURE: float = 0.0
LLM_TIMEOUT_SEC: float = 60.0
LLM_MAX_TOKENS: int = 2048

# --- 语义分块锚点（章节关键词，非机械字符切分）---
BLOCK_B_MARKERS: list[str] = [
    "architecture", "three-layer", "three layer", "2.2",
    "timeline", "roadmap", "future", "outlook",
    "架构", "三层", "时间轴", "展望", "路线图",
]

# --- 单块字符上限（触发瘦身）---
SINGLE_BLOCK_CHAR_LIMIT: int = 40_000

# --- 视觉规范：科技蓝主色 + 深灰正文 ---
TECH_BLUE = "#005293"     # RGB(0, 82, 147) 主色
DARK_GRAY = "#323232"     # RGB(50, 50, 50) 正文色
ACCENT_BLUE = "#3B7EB5"   # 副强调色
LIGHT_BG = "#EEF3FA"      # 浅蓝底纹
CARD_BG = "#FFFFFF"
DIVIDER = "#D6DEE8"

# --- 画布尺寸 ---
FIG_WIDTH_IN = 14
FIG_HEIGHT_IN = 20
FIG_DPI = 300

# --- JSON Schema（含嵌套字段严格约束）---
BRIEFING_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AI+HW 2035 Briefing",
    "type": "object",
    "required": [
        "core_goal",
        "abstract",
        "definition_1000x",
        "layers",
        "timeline",
        "industry_applications",
    ],
    "additionalProperties": False,
    "properties": {
        "core_goal": {"type": "string", "minLength": 10, "maxLength": 120},
        "abstract": {"type": "string", "minLength": 80, "maxLength": 500},
        "definition_1000x": {"type": "string", "minLength": 20, "maxLength": 400},
        "layers": {
            "type": "object",
            "required": ["chip", "board", "system"],
            "additionalProperties": False,
            "properties": {
                "chip": {"$ref": "#/definitions/layer"},
                "board": {"$ref": "#/definitions/layer"},
                "system": {"$ref": "#/definitions/layer"},
            },
        },
        "timeline": {
            "type": "object",
            "required": ["short_term", "mid_term", "long_term"],
            "additionalProperties": False,
            "properties": {
                "short_term": {"$ref": "#/definitions/phase"},
                "mid_term": {"$ref": "#/definitions/phase"},
                "long_term": {"$ref": "#/definitions/phase"},
            },
        },
        "industry_applications": {
            "type": "array",
            "minItems": 3,
            "maxItems": 4,
            "items": {
                "type": "object",
                "required": ["title", "description"],
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string", "minLength": 2, "maxLength": 20},
                    "description": {"type": "string", "minLength": 15, "maxLength": 220},
                },
            },
        },
    },
    "definitions": {
        "layer": {
            "type": "object",
            "required": ["name", "description", "key_tech"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "minLength": 2, "maxLength": 30},
                "description": {"type": "string", "minLength": 20, "maxLength": 350},
                "key_tech": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 6,
                    "items": {"type": "string", "minLength": 2, "maxLength": 30},
                },
            },
        },
        "phase": {
            "type": "object",
            "required": ["year", "milestone", "description"],
            "additionalProperties": False,
            "properties": {
                "year": {
                    "type": "string",
                    "pattern": r"^[~\-\d\s一-龥/]+$",
                    "minLength": 2,
                    "maxLength": 20,
                },
                "milestone": {"type": "string", "minLength": 3, "maxLength": 40},
                "description": {"type": "string", "minLength": 20, "maxLength": 240},
            },
        },
    },
}


# =============================================================================
# 【异常与日志】
# =============================================================================


class FileParseError(Exception):
    """PDF 双通道解析全部失败。"""


class LLMSchemaError(Exception):
    """LLM 输出经修正重试后仍未通过 Schema 校验。"""


def _init_logger() -> logging.Logger:
    """控制台 INFO + 文件 WARNING+ 的双 handler 日志。"""
    logger = logging.getLogger("briefing")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

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
# 【LLM 客户端】兼容自定义 Header 与本地代理
# =============================================================================


def _build_openai_client() -> tuple[OpenAI, str]:
    """
    从 .env 读取凭据构建 OpenAI 客户端。

    - 中转 Header 通过 httpx.Client(headers=...) 注入；
    - 空 Header 键值一律不发送；
    - 本地代理可选，通过环境变量 LOCAL_PROXY_ENABLE 开关。
    """
    load_dotenv(BASE_DIR / ".env", override=False)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    model_name = os.getenv("MODEL_NAME", "").strip()

    if not api_key or not base_url or not model_name:
        raise RuntimeError(
            "缺少必要环境变量：请在 .env 中设置 OPENAI_API_KEY / OPENAI_BASE_URL / MODEL_NAME"
        )

    header_key = os.getenv("RELAY_HEADER_KEY", "").strip()
    header_val = os.getenv("RELAY_HEADER_VALUE", "").strip()
    extra_headers: dict[str, str] = {}
    if header_key and header_val:
        extra_headers[header_key] = header_val
        LOGGER.info("已启用中转 Header：%s", header_key)
    else:
        LOGGER.info("未配置中转 Header，跳过注入")

    proxy_url: str | None = None
    if os.getenv("LOCAL_PROXY_ENABLE", "").strip().lower() in {"1", "true", "yes"}:
        proxy_url = os.getenv("LOCAL_PROXY_URL", "").strip() or None
        if proxy_url:
            LOGGER.info("已启用本地代理：%s", proxy_url)

    # httpx 0.27+ 用 proxy，旧版本用 proxies——写兼容兜底
    try:
        http_client = httpx.Client(
            headers=extra_headers or None,
            timeout=LLM_TIMEOUT_SEC,
            proxy=proxy_url,  # type: ignore[arg-type]
        )
    except TypeError:
        http_client = httpx.Client(
            headers=extra_headers or None,
            timeout=LLM_TIMEOUT_SEC,
            proxies=proxy_url,  # type: ignore[arg-type]
        )

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=http_client,
        timeout=LLM_TIMEOUT_SEC,
    )
    return client, model_name


# =============================================================================
# 【PDF 加载】双通道降级
# =============================================================================


def load_pdf(path: Path) -> str:
    """
    读取 PDF 全文文本。

    降级链：pdfplumber → PyPDF2 → FileParseError
    """
    if not path.exists():
        raise FileParseError(f"PDF 文件不存在：{path}")

    # 通道 1：pdfplumber
    try:
        import pdfplumber  # noqa: WPS433 - 延迟导入避免顶层耦合

        with pdfplumber.open(path) as pdf:
            pages = [(p.extract_text() or "") for p in pdf.pages]
        text = "\n".join(pages).strip()
        if text:
            LOGGER.info("pdfplumber 提取成功：%d 页 / %d 字符", len(pages), len(text))
            return text
        LOGGER.warning("pdfplumber 返回空文本，尝试 PyPDF2 兜底")
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("pdfplumber 解析失败：%s，尝试 PyPDF2 兜底", exc)

    # 通道 2：PyPDF2
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
        text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
        if text:
            LOGGER.info("PyPDF2 兜底成功：%d 页 / %d 字符", len(reader.pages), len(text))
            return text
        LOGGER.error("PyPDF2 也返回空文本")
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PyPDF2 兜底失败：%s", exc)

    raise FileParseError(f"pdfplumber 与 PyPDF2 均无法解析 PDF：{path}")


# =============================================================================
# 【文本分块】Map-Reduce
# =============================================================================


@dataclass(frozen=True)
class Chunk:
    label: str
    focus: str
    text: str


def _locate_first_marker(text_lower: str, markers: list[str]) -> int:
    positions = [text_lower.find(m) for m in markers]
    positions = [p for p in positions if p >= 0]
    return min(positions) if positions else -1


def split_into_blocks(full_text: str) -> list[Chunk]:
    """
    切成 Block A（愿景/定义）与 Block B（架构/时间轴/应用）两块。

    切点定位：以 Block B 第一个 marker 为界；找不到则退化为等分。
    """
    text_lower = full_text.lower()
    split_pos = _locate_first_marker(text_lower, BLOCK_B_MARKERS)

    if split_pos <= 0:
        LOGGER.warning("未定位到 Block B 章节标记，退化为等分切分")
        split_pos = len(full_text) // 2

    block_a = full_text[:split_pos].strip()
    block_b = full_text[split_pos:].strip()

    LOGGER.info(
        "分块完成：Block A=%d 字符 / Block B=%d 字符（切点 %d）",
        len(block_a), len(block_b), split_pos,
    )

    return [
        Chunk(
            label="Block A：核心目标 / 摘要 / 1000x 定义",
            focus=(
                "重点提取："
                "core_goal（30-90 字中文一句话愿景）、"
                "abstract（100-400 字中文精炼摘要，覆盖论文的问题定义、方法与主要观点）、"
                "definition_1000x（60-200 字，说明 1000× 效率提升在论文中的具体含义与衡量维度）。"
            ),
            text=_shrink_if_needed(block_a, "Block A"),
        ),
        Chunk(
            label="Block B：三层架构 / 时间轴 / 行业应用",
            focus=(
                "重点提取三大字段：\n"
                "1) layers：必须包含 chip（芯片层）、board（板卡层）、system（整机系统）三个键，"
                "  每层给出 name（中文层名）、description（该层职责与范围，30-200 字）、"
                "  key_tech（该层的 2-5 项代表性关键技术）。\n"
                "2) timeline：必须包含 short_term（2025 前后短期）、mid_term（2030 前后中期）、"
                "  long_term（2035 远期）三个键，每期给出 year（如 '2025-2027'）、"
                "  milestone（4-15 字里程碑名）、description（30-150 字补充说明）。\n"
                "3) industry_applications：至少 3 条、最多 4 条行业落地场景，"
                "  每条含 title（中文行业名，如 '自动驾驶'）与 description（30-150 字说明）。"
                "  如果论文未显式列出，可基于论文提到的领域（大模型推理、边缘计算、"
                "  云端 AI、机器人、自动驾驶等）合理推断最相关的场景。"
            ),
            text=_shrink_if_needed(block_b, "Block B"),
        ),
    ]


def _shrink_if_needed(text: str, tag: str) -> str:
    """
    单块超长瘦身，避免 LLM 上下文超限：
      1) 折叠连续空白 → 2) 段落级去重 → 3) 仍超限则头尾各 45% + 中段省略提示。
    """
    if len(text) <= SINGLE_BLOCK_CHAR_LIMIT:
        return text

    LOGGER.warning("%s 长度 %d 超过阈值 %d，启动瘦身",
                   tag, len(text), SINGLE_BLOCK_CHAR_LIMIT)

    compact = re.sub(r"[ \t]+", " ", text)
    compact = re.sub(r"\n{3,}", "\n\n", compact)

    seen: set[str] = set()
    paragraphs: list[str] = []
    for para in compact.split("\n\n"):
        key = para.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        paragraphs.append(key)
    compact = "\n\n".join(paragraphs)

    if len(compact) <= SINGLE_BLOCK_CHAR_LIMIT:
        LOGGER.info("%s 瘦身后 %d 字符，未触发截断", tag, len(compact))
        return compact

    head_len = int(SINGLE_BLOCK_CHAR_LIMIT * 0.45)
    tail_len = SINGLE_BLOCK_CHAR_LIMIT - head_len - 200
    truncated = (
        compact[:head_len]
        + "\n\n[... 中间冗余描述已由预处理器省略，仅保留章节首尾以避免上下文超限 ...]\n\n"
        + compact[-tail_len:]
    )
    LOGGER.warning("%s 触发截断策略，最终 %d 字符", tag, len(truncated))
    return truncated


# =============================================================================
# 【LLM 调用 + 输出清洗】
# =============================================================================

_MD_FENCE_RE = re.compile(r"^```(?:json|JSON)?\s*|\s*```$", re.MULTILINE)


def _strip_markdown_fence(raw: str) -> str:
    """去除 LLM 偶尔在 JSON 外套的 ```json ... ``` 围栏。"""
    cleaned = _MD_FENCE_RE.sub("", raw).strip()
    first, last = cleaned.find("{"), cleaned.rfind("}")
    if first >= 0 and last > first:
        cleaned = cleaned[first : last + 1]
    return cleaned


def _system_prompt() -> str:
    return (
        "你是一名资深技术分析师，擅长将学术论文的关键论点浓缩为结构化 JSON。"
        "你只输出严格合法的 JSON，不解释、不使用 Markdown 代码块。"
        "所有字段都要给出高信息密度、无冗余的中文表述。"
    )


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException, ValueError)),
)
def _call_llm(client: OpenAI, model: str, user_prompt: str) -> dict[str, Any]:
    """单次 LLM 调用，附 tenacity 指数退避重试。"""
    LOGGER.info("→ 调用 LLM（model=%s, prompt=%d 字符）", model, len(user_prompt))
    resp = client.chat.completions.create(
        model=model,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    if not raw:
        raise ValueError("LLM 返回空内容")

    cleaned = _strip_markdown_fence(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        LOGGER.warning("JSON 解析失败：%s\n原文：%s", exc, raw[:500])
        raise ValueError(f"JSON 解析失败：{exc}") from exc


def _prompt_for_block(chunk: Chunk) -> str:
    return (
        f"下面是论文《AI+HW 2035》的一部分文本（{chunk.label}）。\n"
        f"任务：{chunk.focus}\n"
        f"只输出当前块相关的字段，其它字段用 null 或空数组占位。\n"
        f"最终 JSON 必须满足如下 Schema：\n"
        f"{json.dumps(BRIEFING_SCHEMA, ensure_ascii=False)}\n\n"
        f"===== 原文开始 =====\n{chunk.text}\n===== 原文结束 ====="
    )


def _prompt_for_merge(part_a: dict[str, Any], part_b: dict[str, Any]) -> str:
    return (
        "以下是同一篇论文两次分块抽取得到的 JSON 结果。请合并两者并去重，"
        "补齐所有缺失字段，得到最终一份完整 JSON。合并规则：\n"
        "1) 顶层字符串字段（core_goal / abstract / definition_1000x）：两边都有时选信息更完整的一份；\n"
        "2) layers.{chip/board/system}：互补合并，key_tech 去除同义重复项；\n"
        "3) timeline.{short_term/mid_term/long_term}：按年份逻辑填齐三期；\n"
        "4) industry_applications：3-4 条，去除同义或明显重复的场景；\n"
        "5) 输出必须严格符合给定 Schema：\n"
        f"{json.dumps(BRIEFING_SCHEMA, ensure_ascii=False)}\n\n"
        f"===== Part A =====\n{json.dumps(part_a, ensure_ascii=False, indent=2)}\n\n"
        f"===== Part B =====\n{json.dumps(part_b, ensure_ascii=False, indent=2)}"
    )


def extract_info(text_chunks: list[Chunk]) -> dict[str, Any]:
    """Map-Reduce 抽取：单块抽取 → 合并去重。"""
    client, model = _build_openai_client()

    partials: list[dict[str, Any]] = []
    for chunk in text_chunks:
        LOGGER.info("[Map] 抽取 %s", chunk.label)
        try:
            partials.append(_call_llm(client, model, _prompt_for_block(chunk)))
        except RetryError as exc:
            LOGGER.error("[Map] %s 抽取失败（重试耗尽）：%s", chunk.label, exc)
            raise

    if len(partials) == 1:
        return partials[0]

    LOGGER.info("[Reduce] 合并 %d 份抽取结果", len(partials))
    return _call_llm(client, model, _prompt_for_merge(partials[0], partials[1]))


def validate_json(data: dict[str, Any]) -> list[str]:
    """返回所有 Schema 错误路径；空列表 = 通过。"""
    validator = Draft7Validator(BRIEFING_SCHEMA)
    errors: list[ValidationError] = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]


def extract_with_validation(text_chunks: list[Chunk]) -> dict[str, Any]:
    """抽取 + Schema 校验；失败自动触发一次修正重试。"""
    data = extract_info(text_chunks)
    errors = validate_json(data)
    if not errors:
        LOGGER.info("JSON Schema 校验一次通过 ✅")
        return data

    LOGGER.warning("JSON Schema 首次校验失败 %d 条：\n  - %s",
                   len(errors), "\n  - ".join(errors))

    client, model = _build_openai_client()
    fix_prompt = (
        "上一次输出未通过 JSON Schema 校验，请根据下列错误列表修改后重新输出**完整 JSON**。\n"
        "错误列表：\n- " + "\n- ".join(errors) + "\n\n"
        "Schema：\n" + json.dumps(BRIEFING_SCHEMA, ensure_ascii=False) + "\n\n"
        "上次的错误 JSON：\n" + json.dumps(data, ensure_ascii=False, indent=2)
    )
    fixed = _call_llm(client, model, fix_prompt)
    errors2 = validate_json(fixed)
    if errors2:
        LOGGER.error("修正后仍未通过校验：\n  - %s", "\n  - ".join(errors2))
        raise LLMSchemaError("JSON Schema 校验失败（含 1 次修正重试）")
    LOGGER.info("修正后校验通过 ✅")
    return fixed


# =============================================================================
# 【可视化】matplotlib 一体式海报（PNG）
# =============================================================================


def _setup_chinese_font() -> None:
    """
    自动选用系统中可用的中文字体，避免中文渲染为豆腐块。

    Windows 优先 Microsoft YaHei，macOS 优先 PingFang，
    Linux 优先 Noto Sans CJK。若均缺失则记 WARNING，
    但仍保留字体列表让 matplotlib 尽力回退。
    """
    preferred = [
        "Microsoft YaHei", "SimHei", "PingFang SC",
        "Noto Sans CJK SC", "Arial Unicode MS", "DejaVu Sans",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    chosen = next((f for f in preferred if f in available), None)
    if chosen:
        LOGGER.info("使用中文字体：%s", chosen)
        matplotlib.rcParams["font.sans-serif"] = [chosen] + preferred
    else:
        LOGGER.warning("未找到常用中文字体，建议安装 Microsoft YaHei / SimHei")
        matplotlib.rcParams["font.sans-serif"] = preferred
    matplotlib.rcParams["axes.unicode_minus"] = False


# ---- 底层绘图工具 ----------------------------------------------------------


def _visual_wrap(text: str, max_visual_width: int) -> str:
    """
    按“视觉宽度”换行：CJK 字符按 2 计，ASCII 字符按 1 计。

    比 textwrap.fill 更贴合中英混排——textwrap 只按字符数换行，
    会导致中文段落每行过长、英文段落过短。
    """
    if not text:
        return ""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        buf, buf_w = "", 0
        for ch in paragraph:
            w = 2 if ord(ch) > 0x2E80 else 1
            if buf_w + w > max_visual_width and buf:
                lines.append(buf)
                buf, buf_w = ch, w
            else:
                buf += ch
                buf_w += w
        if buf:
            lines.append(buf)
    return "\n".join(lines)


def _draw_section_header(ax, index_tag: str, title: str) -> None:
    """
    在面板顶部绘制章节标题条：科技蓝底 + 白字 + 左侧强调竖条。

    ax 必须是坐标 0..100 × 0..100 的“像画布一样用”的 axes。
    """
    bar_h = 8
    y = 100 - bar_h
    ax.add_patch(Rectangle((0, y), 100, bar_h, facecolor=TECH_BLUE, edgecolor="none"))
    ax.add_patch(Rectangle((0, y), 1.5, bar_h, facecolor=ACCENT_BLUE, edgecolor="none"))
    ax.text(
        2.5, y + bar_h / 2, f"{index_tag}  {title}",
        ha="left", va="center",
        fontsize=17, fontweight="bold", color="white",
    )


def _draw_card(
    ax, *, x: float, y: float, w: float, h: float,
    title: str, body: str,
    body_wrap: int = 60,
    title_size: int = 13, body_size: int = 10,
    bg: str = CARD_BG, border: str = TECH_BLUE,
    title_color: str = TECH_BLUE, body_color: str = DARK_GRAY,
) -> None:
    """通用卡片：圆角矩形 + 标题 + 自动换行的正文。"""
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.05,rounding_size=0.8",
        facecolor=bg, edgecolor=border, linewidth=1.4,
    ))
    ax.text(
        x + 1.5, y + h - 2.2, title,
        ha="left", va="top",
        fontsize=title_size, fontweight="bold", color=title_color,
    )
    if body:
        ax.text(
            x + 1.5, y + h - 6.5, _visual_wrap(body, body_wrap),
            ha="left", va="top",
            fontsize=body_size, color=body_color, linespacing=1.55,
        )


def _panel_axes(fig, gs_cell):
    """把 GridSpec 单元格转成 0..100 × 0..100 无坐标画布。"""
    ax = fig.add_subplot(gs_cell)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_axis_off()
    return ax


# ---- 各面板 ---------------------------------------------------------------


def _draw_header(fig, gs_cell, data: dict[str, Any]) -> None:
    """封面横幅：科技蓝底 + 论文标题 + core_goal 副标题。"""
    ax = _panel_axes(fig, gs_cell)
    ax.add_patch(Rectangle((0, 0), 100, 100, facecolor=TECH_BLUE, edgecolor="none"))
    ax.add_patch(Rectangle((0, 0), 100, 6, facecolor=ACCENT_BLUE, edgecolor="none"))

    ax.text(50, 68, "AI + HW 2035", ha="center", va="center",
            fontsize=40, fontweight="bold", color="white")
    ax.text(50, 40, _visual_wrap(data.get("core_goal", ""), 46),
            ha="center", va="center", fontsize=13, color="white",
            linespacing=1.5)
    ax.text(50, 16, "论文自动化简报 · Auto-generated Briefing",
            ha="center", va="center", fontsize=11, color="#D6E4F2")


def _draw_summary_panel(fig, gs_cell, data: dict[str, Any]) -> None:
    """① 论文核心摘要：一张主卡（abstract） + 一张辅卡（1000× 定义）。"""
    ax = _panel_axes(fig, gs_cell)
    _draw_section_header(ax, "①", "论文核心摘要")

    # 主卡：精炼摘要（占更大空间）
    _draw_card(
        ax, x=1.5, y=48, w=97, h=40,
        title="◆ 精炼摘要",
        body=data.get("abstract", ""),
        body_wrap=78, title_size=14, body_size=11,
        bg=LIGHT_BG,
    )
    # 辅卡：1000× 定义
    _draw_card(
        ax, x=1.5, y=2, w=97, h=42,
        title="◆ 1000× 效率定义",
        body=data.get("definition_1000x", ""),
        body_wrap=78, title_size=14, body_size=11,
        bg=CARD_BG,
    )


def _draw_layers_panel(fig, gs_cell, data: dict[str, Any]) -> None:
    """② AI 硬件三层架构：芯片 / 板卡 / 整机三列并排。"""
    ax = _panel_axes(fig, gs_cell)
    _draw_section_header(ax, "②", "AI 硬件三层架构（芯片 · 板卡 · 整机系统）")

    layers = data.get("layers", {}) or {}
    order = [
        ("chip", "芯片层 Chip"),
        ("board", "板卡层 Board"),
        ("system", "整机系统 System"),
    ]

    # 三等分列
    gap = 2
    col_w = (100 - gap * 4) / 3  # 4 段间距（左 + 中间 2 + 右）
    top = 88
    bottom = 2
    col_h = top - bottom

    for i, (key, cn_name) in enumerate(order):
        layer = layers.get(key, {}) or {}
        x = gap + i * (col_w + gap)

        # 卡片主体
        _draw_card(
            ax, x=x, y=bottom, w=col_w, h=col_h,
            title="",
            body="",
            bg=CARD_BG, border=TECH_BLUE,
        )
        # 顶部色带（层名）
        band_h = 6
        band_y = top - band_h
        ax.add_patch(Rectangle(
            (x, band_y), col_w, band_h,
            facecolor=TECH_BLUE, edgecolor="none",
        ))
        display_name = layer.get("name") or cn_name
        ax.text(x + col_w / 2, band_y + band_h / 2,
                display_name,
                ha="center", va="center",
                fontsize=13, fontweight="bold", color="white")

        # 描述
        ax.text(
            x + 1.5, band_y - 2, "◆ 层职责",
            ha="left", va="top",
            fontsize=11, fontweight="bold", color=TECH_BLUE,
        )
        ax.text(
            x + 1.5, band_y - 6,
            _visual_wrap(layer.get("description", ""), int(col_w * 1.35)),
            ha="left", va="top",
            fontsize=10, color=DARK_GRAY, linespacing=1.55,
        )

        # 关键技术分割线
        divider_y = bottom + 26
        ax.add_patch(Rectangle(
            (x + 1.5, divider_y), col_w - 3, 0.15,
            facecolor=DIVIDER, edgecolor="none",
        ))
        ax.text(
            x + 1.5, divider_y - 1.5, "◆ 关键技术",
            ha="left", va="top",
            fontsize=11, fontweight="bold", color=TECH_BLUE,
        )
        tech_list = layer.get("key_tech", []) or []
        for j, tech in enumerate(tech_list[:5]):
            ax.text(
                x + 2.5, divider_y - 5.5 - j * 3.6,
                f"• {_visual_wrap(tech, int(col_w * 1.3))}",
                ha="left", va="top",
                fontsize=10, color=DARK_GRAY,
            )


def _draw_timeline_panel(fig, gs_cell, data: dict[str, Any]) -> None:
    """③ 三段式技术时间轴：短期 · 中期 · 远期。"""
    ax = _panel_axes(fig, gs_cell)
    _draw_section_header(ax, "③", "技术时间轴（短期 2025 · 中期 2030 · 远期 2035）")

    tl = data.get("timeline", {}) or {}
    phases = [
        ("短期 Short-term", tl.get("short_term", {}) or {}),
        ("中期 Mid-term", tl.get("mid_term", {}) or {}),
        ("远期 Long-term", tl.get("long_term", {}) or {}),
    ]

    # 布局：3 列均分，中间横向箭头贯穿
    gap = 3
    col_w = (100 - gap * 4) / 3
    line_y = 62
    top = 88

    # 时间轴主箭头
    ax.add_patch(FancyArrowPatch(
        (2, line_y), (98, line_y),
        arrowstyle="->", mutation_scale=22,
        color=TECH_BLUE, linewidth=2.5,
    ))

    for i, (phase_name, ph) in enumerate(phases):
        cx = gap + i * (col_w + gap) + col_w / 2

        # 时间轴上的圆点
        ax.add_patch(Circle(
            (cx, line_y), 1.6,
            facecolor=TECH_BLUE, edgecolor="white",
            linewidth=2, zorder=5,
        ))
        # 阶段名
        ax.text(cx, line_y + 6, phase_name,
                ha="center", va="center",
                fontsize=11, color=DARK_GRAY)
        # 年份
        ax.text(cx, line_y + 11, ph.get("year", ""),
                ha="center", va="center",
                fontsize=14, fontweight="bold", color=TECH_BLUE)

        # 里程碑卡
        card_h = line_y - 12
        card_bottom = 4
        _draw_card(
            ax, x=cx - col_w / 2, y=card_bottom, w=col_w, h=card_h,
            title=f"◆ {ph.get('milestone', '')}",
            body=ph.get("description", ""),
            body_wrap=int(col_w * 1.35),
            title_size=12, body_size=10,
            bg=LIGHT_BG,
        )


def _draw_industry_panel(fig, gs_cell, data: dict[str, Any]) -> None:
    """④ 行业落地场景：3-4 个应用卡片自适应布局。"""
    ax = _panel_axes(fig, gs_cell)
    _draw_section_header(ax, "④", "行业落地场景")

    apps = list(data.get("industry_applications", []) or [])[:4]
    if not apps:
        ax.text(50, 45, "（未抽取到行业应用数据）",
                ha="center", va="center",
                fontsize=13, color=DARK_GRAY)
        return

    n = len(apps)
    if n <= 3:
        cols, rows = n, 1
    else:
        cols, rows = 2, 2

    gap = 2.5
    top = 88
    bottom = 3
    total_h = top - bottom
    card_w = (100 - gap * (cols + 1)) / cols
    card_h = (total_h - gap * (rows - 1)) / rows if rows > 1 else total_h - 3

    for idx, app in enumerate(apps):
        row = idx // cols
        col = idx % cols
        x = gap + col * (card_w + gap)
        y = top - (row + 1) * card_h - row * gap

        _draw_card(
            ax, x=x, y=y, w=card_w, h=card_h,
            title=f"◆ {app.get('title', '')}",
            body=app.get("description", ""),
            body_wrap=int(card_w * 1.35),
            title_size=13, body_size=10,
            bg=CARD_BG,
        )


def _draw_footer(fig, gs_cell) -> None:
    """页脚：细蓝条 + 生成说明。"""
    ax = _panel_axes(fig, gs_cell)
    ax.add_patch(Rectangle((0, 40), 100, 20,
                           facecolor=TECH_BLUE, edgecolor="none"))
    ax.text(50, 50, "Generated by AI+HW 2035 Briefing Generator · Python + matplotlib",
            ha="center", va="center",
            fontsize=9, color="white")


# ---- 顶层入口 -------------------------------------------------------------


def create_briefing_png(data: dict[str, Any], output_path: Path) -> None:
    """
    把抽取结果渲染为单张 300 DPI 科技蓝海报。

    版式（自上而下）：
        [封面横幅] → [① 核心摘要] → [② 三层架构] → [③ 时间轴] → [④ 行业应用] → [页脚]
    """
    _setup_chinese_font()

    fig = plt.figure(figsize=(FIG_WIDTH_IN, FIG_HEIGHT_IN), dpi=FIG_DPI)
    fig.patch.set_facecolor("white")

    # 6 行竖排：header / summary / layers / timeline / industry / footer
    gs = fig.add_gridspec(
        nrows=6, ncols=1,
        height_ratios=[1.35, 3.15, 4.60, 3.85, 4.15, 0.30],
        hspace=0.08,
        left=0.035, right=0.965, top=0.99, bottom=0.01,
    )

    _draw_header(fig, gs[0, 0], data)
    _draw_summary_panel(fig, gs[1, 0], data)
    _draw_layers_panel(fig, gs[2, 0], data)
    _draw_timeline_panel(fig, gs[3, 0], data)
    _draw_industry_panel(fig, gs[4, 0], data)
    _draw_footer(fig, gs[5, 0])

    fig.savefig(
        output_path,
        dpi=FIG_DPI,
        facecolor="white",
        bbox_inches="tight",
        pad_inches=0.15,
    )
    plt.close(fig)
    LOGGER.info("PNG 已保存：%s（%.1f×%.1f in @ %d DPI）",
                output_path, FIG_WIDTH_IN, FIG_HEIGHT_IN, FIG_DPI)


# =============================================================================
# 【入口】
# =============================================================================


def main() -> None:
    LOGGER.info("========= AI+HW 2035 简报生成器 启动 =========")
    LOGGER.info("读取 PDF：%s", PDF_PATH)

    # 1) 载入 PDF
    text = load_pdf(PDF_PATH)

    # 2) 分块（Block A / Block B）
    chunks = split_into_blocks(text)

    # 3) LLM 抽取 + Schema 校验（含 1 次修正重试）
    data = extract_with_validation(chunks)

    # 4) 生成 PNG 简报
    create_briefing_png(data, OUTPUT_PNG)

    print(f"✅ PNG 简报生成完成: {OUTPUT_PNG.name}")


if __name__ == "__main__":
    try:
        main()
    except FileParseError as exc:
        LOGGER.error("PDF 解析失败：%s", exc)
        print(f"❌ PDF 解析失败：{exc}")
        sys.exit(2)
    except LLMSchemaError as exc:
        LOGGER.error("LLM 输出校验失败：%s", exc)
        print(f"❌ LLM 输出结构不合法：{exc}")
        sys.exit(3)
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("未预期异常：%s", exc)
        print(f"❌ 未预期异常，详见 error.log：{exc}")
        sys.exit(1)
