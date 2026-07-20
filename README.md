# AI + HW 2035 论文自动化简报生成器

> 大一考核项目 · 路径 2（PNG 版）
>
> 输入论文《AI+HW 2035: Shaping the Next Decade》(https://arxiv.org/abs/2603.05225)，
> 通过 LLM 抽取核心信息，用 matplotlib 生成一张 16:9 / 300 DPI 的信息海报 `briefing.png`。

---

## 一、代码运行环境

| 项目 | 说明 |
|---|---|
| 操作系统 | Windows 11（在 Git Bash 下开发测试；macOS / Linux 同样可跑） |
| Python 版本 | Python 3.10+（推荐 3.13） |
| 终端编码 | 脚本顶部已通过 `sys.stdout = io.TextIOWrapper(...)` 兜底适配 Windows GBK |

### 依赖库

**必需**（无这个跑不了）：
- `matplotlib` — 绘制 PNG 海报

**可选**（走 LLM 模式时才需要，全部缺失时脚本自动降级为离线兜底）：
- `openai` — 调用 LLM（DeepSeek / OpenAI / 千问 兼容协议）
- `httpx` — HTTP 客户端 / 超时控制
- `python-dotenv` — 读取 `.env` 环境变量
- `pdfplumber`、`pypdf` — PDF 文本解析（双通道降级）

一键安装：
```bash
pip install matplotlib openai httpx python-dotenv pdfplumber pypdf
```

---

## 二、文件结构

```
hw2035_project/
├── generate_briefing_final.py   # ★ 推荐入口：LLM + 离线兜底 双模最优版
├── generate_briefing.py         # 初版：LLM + 竖版 PNG 海报
├── generate_briefing_new.py     # 精简版：无 LLM、内容硬编码
├── AI+HW2035.pdf                # 输入论文
├── briefing.png                 # 输出：最终简报（16:9 · 300 DPI）
├── extracted_info.json          # 输出：LLM 抽取的结构化 JSON（仅 LLM 模式生成）
├── error.log                    # 输出：WARNING 级以上日志
├── requirements.txt
└── README.md
```

---

## 三、快速开始

### 1. LLM 模式（完整流程，覆盖任务书 4 大考核点）

在项目根目录建 `.env`：
```env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1     # 或 https://api.openai.com/v1
MODEL_NAME=deepseek-chat                        # 或 gpt-4o-mini 等
```

运行：
```bash
python generate_briefing_final.py
```

流程：**PDF 双通道解析 → LLM 抽取 → JSON Schema 校验 → 失败自修正 1 次 → 生成 PNG**

### 2. 离线兜底模式（无 API Key 也能出图）

```bash
python generate_briefing_final.py --no-llm
```

或者 `.env` 未配置 / 网络不通时，脚本会自动降级为离线兜底并在页脚水印中标注 `offline-fallback`。

### 3. 自定义路径

```bash
python generate_briefing_final.py --input paper.pdf --output my_briefing.png
```

---

## 四、Prompt 设计思路

### 4.1 System Prompt —— 定角色 + 定输出协议

```
你是一名资深技术分析师，擅长将学术论文的关键论点浓缩为结构化 JSON。
严格按要求输出合法 JSON，不解释、不使用 Markdown 代码块、不添加额外字段。
```

- 明确「资深技术分析师」角色 → LLM 会倾向于抽象层级归纳而不是抄原文
- 强制「只输出 JSON、不加 Markdown」 → 配合 `response_format={"type":"json_object"}` 双重保险

### 4.2 User Prompt —— 分解任务 + 给出 Schema 示范

Prompt 里显式列出任务书要求的三大维度：
1. 核心目标：`1000× 效率提升` 的定义（Intelligence per Joule）
2. 三大层级：`Hardware / Algorithm / Application` 的中文层名 + 职责 + 关键技术
3. 时间轴：`近期 2-5 年` vs `远期 6-10 年` 的技术趋势

同时把目标 JSON 结构以「字段:类型说明」形式贴进 Prompt（不是空模板，而是带字数/数量约束的示意），这样 LLM 输出的字段数量、层级、类型都很稳定：

```json
{
  "core_vision": "string, 30-90 字, 突出 1000× 或 Intelligence per Joule",
  "layers": {
    "hardware": {"name": "中文层名", "description": "30-120 字", "key_tech": ["3-5 项关键技术"]},
    ...
  },
  "timeline": {
    "near_term": {"period": "如 '2025-2030'", "items": ["3 项技术趋势"]},
    ...
  }
}
```

### 4.3 自修正 Prompt —— 失败反馈式修正

Schema 校验不过时，把「错误列表 + 上次错误 JSON」一起送回 LLM，让它针对性修改：

```
上一次输出未通过 JSON Schema 校验，请根据下列错误重新输出完整合法 JSON。
错误列表：
- layers.hardware.key_tech 必须为 >=2 个非空字符串数组
...
错误 JSON：
{ ... }
```

大部分「字段缺失 / 数量不够 / 类型不对」的场景一次就能修好。

---

## 五、遇到的主要问题与解决方案

### 问题 1：LLM 偶尔输出 Markdown 代码块 / 多余解释

**现象**：即使 system prompt 说"只输出 JSON"，模型偶尔仍会包一层 ```` ```json ```` 或加一句"以下是提取结果："。

**解决**：
1. API 调用加 `response_format={"type": "json_object"}` 强制 JSON 输出（DeepSeek / OpenAI 支持）；
2. 后端加正则清洗：`re.sub(r"^```(?:json|JSON)?\s*|\s*```$", "", raw)`；
3. 再用括号计数法抽出首个完整 `{...}` 对象。

### 问题 2：JSON 结构不合规（字段缺失 / 层级键错）

**现象**：任务书要求三层为 `Hardware / Algorithm / Application`，LLM 有时会输出 `chip / board / system` 或只有 2 层。

**解决**：手写 `validate_briefing()` 校验器（不依赖 `jsonschema` 库），错误路径全部收集后一次性反馈给 LLM 自修正。修正后仍失败才降级兜底。

### 问题 3：PDF 解析失败

**现象**：论文 PDF 排版复杂，单一解析库有时提取为空字符串。

**解决**：双通道降级 `pdfplumber → pypdf`，任一成功即返回；全部失败则日志 WARNING 并走离线兜底。

### 问题 4：Windows 终端 GBK 编码报错

**现象**：脚本里的 emoji 或中文特殊符号在 Windows CMD / Git Bash 下打印时抛 `UnicodeEncodeError: 'gbk' codec can't encode character`。

**解决**：脚本顶部（早于任何 `print`）加一句：
```python
import sys, io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass
```
同时清理所有 `print` 里的 emoji，只保留纯中英文。

### 问题 5：中文字体渲染成豆腐块

**现象**：matplotlib 默认字体不含 CJK，中文渲染为方块。

**解决**：`setup_chinese_font()` 按优先级探测系统可用中文字体（`Microsoft YaHei → SimHei → PingFang SC → Noto Sans CJK`），命中即用；同时设 `axes.unicode_minus = False` 避免负号显示异常。

### 问题 6：中英文混排换行不齐

**现象**：`textwrap.fill` 按字符数换行，一个中文和一个英文占的视觉宽度差 2 倍，中文段落易撑破卡片。

**解决**：手写 `_visual_wrap()` 按"视觉宽度"换行（CJK 计 2，ASCII 计 1），中英混排段落宽度一致。

### 问题 7：API 不可用时脚本完全失败

**现象**：老师本地评审时可能没有 API Key，脚本直接崩了就没有 PNG 交付。

**解决**：LLM 抽取失败 / API 未配置 / 网络异常，自动降级为 `FALLBACK_DATA`（硬编码符合任务书语义的示范内容），继续生成 PNG，并在页脚水印中标注 `offline-fallback`。评审可以一眼看出这次跑的是哪个模式。

---

## 六、输出说明

- `briefing.png` —— 16:9 · 300 DPI · 单张海报，包含：
  - **顶部标题区**：论文标题 + 核心愿景（含 1000× 关键词）
  - **摘要 / 1000× 定义 双卡区**：论文摘要 + Intelligence per Joule 定义
  - **三层级表格区**：Hardware / Algorithm / Application 各列含层职责 + 关键技术
  - **双色时间轴区**：近期（浅蓝 2025-2030）vs 远期（浅橙 2030-2035）各 3 个节点，主线带箭头
  - **页脚水印**：数据来源（`LLM-extracted` / `offline-fallback`）
- `extracted_info.json` —— LLM 模式成功时保存的结构化数据，方便评审复核抽取质量
- `error.log` —— WARNING 及以上级别日志

---

## 七、与任务书对应

| 任务书要求 | 本项目实现位置 |
|---|---|
| 模块 1：文档加载与预处理 / Chunking | `load_pdf()` 双通道 → LLM 上下文直接送入完整论文 |
| 模块 2：LLM 智能信息提取（强制 JSON） | `extract_via_llm()` + `response_format=json_object` + `validate_briefing()` 手写校验 + 一次自修正 |
| 模块 3：自动化 infograph 生成（路径 2 PNG） | `build_briefing()` + `draw_header / draw_info_banner / draw_layers_table / draw_timeline` |
| 核心目标（1000× / Intelligence per Joule） | Zone A 副标题 + Zone B 右卡专项定义 |
| 三大层级（Hardware / Algorithm / Application） | Zone C 三列表格，Schema 键名与任务书语义一致 |
| 时间轴（近期 2-5 年 vs 远期 6-10 年） | Zone D 双色时间轴，`near_term` / `long_term` 两段严格对齐 |
