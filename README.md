# AI + HW 2035 论文自动化简报生成器

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Git%20Bash-blue)
![Output](https://img.shields.io/badge/Output-briefing.png%20%40%20300DPI-005293)
![LLM](https://img.shields.io/badge/LLM-OpenAI%20Compatible-10B981)
![License](https://img.shields.io/badge/Use-Coursework-8A4FFF)

> **作业归属**：大一《大一考核任务书：论文简报生成器》
> **课题原文**：《AI+HW 2035》（10 页，PDF）
> **交付形态**：一份 300 DPI 科技蓝一体式 PNG 简报（`briefing.png`）
> **适配环境**：Windows + Git Bash + Python 3.13（统一走 `python3` / `pip3`）

---

## 目录

- [一、项目定位](#一项目定位)
- [二、优秀档达成说明（对标任务书评分细则）](#二优秀档达成说明对标任务书评分细则)
- [三、环境部署](#三环境部署)
- [四、项目结构清单](#四项目结构清单)
- [五、运行流程](#五运行流程)
- [六、设计思路（技术亮点）](#六设计思路技术亮点)
- [七、PNG 简报输出优秀标准 & 交付校验清单](#七png-简报输出优秀标准--交付校验清单)
- [八、报错 FAQ 专区](#八报错-faq-专区)
- [九、提交规范（贴合任务书）](#九提交规范贴合任务书)

---

## 一、项目定位

一键把 10 页的《AI+HW 2035》论文压缩成一张**印刷级 PNG 海报**，包含：

1. 论文核心浓缩摘要；
2. AI 硬件三层架构（芯片 / 板卡 / 整机系统）；
3. 三段式技术时间轴（短期 2025 · 中期 2030 · 远期 2035）；
4. 至少 3 个行业落地场景。

所有内容由 LLM 自动抽取、`jsonschema` 严格校验后，通过 `matplotlib` 绘制为
单张 `briefing.png`。

---

## 二、优秀档达成说明（对标任务书评分细则）

| 任务书评分要点 | 本项目落实位置 | 是否达标 |
| --- | --- | :---: |
| PDF 内容成功解析 | `load_pdf()` 双通道：`pdfplumber` → `PyPDF2` → `FileParseError` | ✅ |
| 调用 LLM 提取关键信息 | `extract_info()` 采用 Map-Reduce（两块抽取 + 一次合并） | ✅ |
| 结构化输出、格式规范 | `BRIEFING_SCHEMA` 使用 Draft-07，嵌套 `$ref` 严格约束子字段 | ✅ |
| 简报视觉规范 | 300 DPI、科技蓝主色 `#005293`、深灰正文 `#323232`、统一版式 | ✅ |
| 简报内容完整 | 四大模块（摘要 / 三层架构 / 时间轴 / 行业应用）全部落地 | ✅ |
| 异常处理与日志 | 三级自定义异常 + `error.log`；`tenacity` 指数退避重试 | ✅ |
| 密钥安全 | 全部走 `.env`，源码零硬编码；仓库仅提交 `.env.example` | ✅ |
| 代码可维护性 | 顶部集中配置区 + 模块化函数 + 详细注释 | ✅ |
| 文档完整度 | 目录 / 环境部署 / 设计说明 / 交付清单 / FAQ / 提交规范齐全 | ✅ |
| 一次运行即成 | `python3 generate_briefing.py` 单命令跑通全流程 | ✅ |

---

## 三、环境部署

### 3.1 前置自检（一条命令验证环境）

```bash
# 1) Python 版本自检（要求 3.10+，实际 3.13）
python3 --version

# 2) pip 通道自检
pip3 --version

# 3) 语法自检（不需要执行也能验证代码可加载）
python3 -c "import ast; ast.parse(open('generate_briefing.py',encoding='utf-8').read()); print('syntax OK')"
```

### 3.2 安装依赖

```bash
pip3 install -r requirements.txt
```

`requirements.txt` 分为三类，全部为运行时必备：

```
pdfplumber>=0.10.0      # PDF 解析主通道
PyPDF2>=3.0.1           # PDF 解析兜底通道
openai>=1.30.0          # LLM 客户端
httpx>=0.27.0           # 用于注入自定义 Header / 本地代理
python-dotenv>=1.0.1    # 读取 .env
tenacity>=8.2.3         # 指数退避重试
jsonschema>=4.21.1      # 结构化输出校验
matplotlib>=3.8.0       # PNG 简报绘制
```

### 3.3 配置密钥（`.env`）

首次运行前拷贝模板并填入真实值：

```bash
cp .env.example .env
```

`.env` 字段说明：

```ini
# --- 必填：OpenAI 协议兼容三要素 ---
OPENAI_API_KEY=sk-xxxx               # 密钥；国内可用 Krill / SiliconFlow / OpenRouter / 通义等中转
OPENAI_BASE_URL=https://xxx/v1       # API 根地址；末尾保留 /v1
MODEL_NAME=gpt-4o-mini               # 建议 gpt-4o-mini / qwen2.5-72b / deepseek-chat 等强 JSON 能力模型

# --- 可选：本地代理（clash / mihomo）---
LOCAL_PROXY_ENABLE=False
LOCAL_PROXY_URL=http://127.0.0.1:7890

# --- 可选：中转站要求的额外 Header ---
# 任意一项为空则完全不注入，避免上游 400/401
RELAY_HEADER_KEY=
RELAY_HEADER_VALUE=
```

**国内大模型密钥配置示例**（三选一即可）：

| 提供方 | `OPENAI_BASE_URL` | 推荐 `MODEL_NAME` |
| --- | --- | --- |
| Krill AI 中转 | `https://api-slb.krill-ai.com/v1` | `gpt-4o-mini` |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-72B-Instruct` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |

### 3.4 密钥有效性自检

```bash
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
k = os.getenv('OPENAI_API_KEY','')
b = os.getenv('OPENAI_BASE_URL','')
m = os.getenv('MODEL_NAME','')
assert k and b and m, '.env 三要素缺一不可'
print('env OK:', b, '/', m, 'key=', k[:6]+'***')
"
```

---

## 四、项目结构清单

```
hw2035_project/
├── generate_briefing.py       # 主程序（PDF 解析 / LLM 抽取 / PNG 绘制）
├── requirements.txt           # 依赖清单
├── README.md                  # 本文件
├── .env.example               # 配置模板（入库）
├── .env                       # 本地配置（不入库）
├── AI+HW2035.pdf              # 输入论文
├── briefing.png               # ★ 唯一输出：300 DPI 科技蓝海报
└── error.log                  # 运行日志（不入库）
```

`briefing.png` 生成规则：

- 由 `create_briefing_png(data, OUTPUT_PNG)` 一次性写出；
- 画布 14 × 20 inches @ 300 DPI（约 4200 × 6000 像素）；
- 版式自上而下：`封面横幅 → ① 核心摘要 → ② 三层架构 → ③ 时间轴 → ④ 行业应用 → 页脚`。

---

## 五、运行流程

```bash
python3 generate_briefing.py
```

成功后终端仅打印一条：

```
✅ PNG 简报生成完成: briefing.png
```

完整日志例：

```
2026-07-12 ... | INFO | briefing | ========= AI+HW 2035 简报生成器 启动 =========
2026-07-12 ... | INFO | briefing | 读取 PDF: .../AI+HW2035.pdf
2026-07-12 ... | INFO | briefing | pdfplumber 提取成功：10 页 / 24391 字符
2026-07-12 ... | INFO | briefing | 分块完成：Block A=... / Block B=... （切点 ...）
2026-07-12 ... | INFO | briefing | [Map] 抽取 Block A：核心目标 / 摘要 / 1000x 定义
2026-07-12 ... | INFO | briefing | [Map] 抽取 Block B：三层架构 / 时间轴 / 行业应用
2026-07-12 ... | INFO | briefing | [Reduce] 合并 2 份抽取结果
2026-07-12 ... | INFO | briefing | JSON Schema 校验一次通过 ✅
2026-07-12 ... | INFO | briefing | 使用中文字体：Microsoft YaHei
2026-07-12 ... | INFO | briefing | PNG 已保存：.../briefing.png（14.0×20.0 in @ 300 DPI）
✅ PNG 简报生成完成: briefing.png
```

---

## 六、设计思路（技术亮点）

### 6.1 语义分块 + Map-Reduce 抽取

论文 10 页看似不长，但一次性丢给 LLM 存在三大隐患：
（1）单请求 token 成本高；（2）多字段并抽注意力被稀释；（3）失败重试代价高。
所以按 **章节语义** 切成两块：

| 块 | 覆盖章节 | 抽取字段 |
| --- | --- | --- |
| Block A | Abstract / Introduction / 1000× 定义 | `core_goal` / `abstract` / `definition_1000x` |
| Block B | 三层架构 / Timeline / 应用 | `layers` / `timeline` / `industry_applications` |

**Map** 阶段：分别聚焦抽取；**Reduce** 阶段：再来一次 LLM 调用合并去重、
补齐缺失字段。切点通过对 `architecture / three-layer / 时间轴 / 展望` 等关键词
自动定位。

### 6.2 JSON Schema 嵌套约束

- `layers.{chip|board|system}` 每层强制含 `name / description / key_tech(2-6 项)`；
- `timeline.{short_term|mid_term|long_term}` 每期强制 `year / milestone / description`；
- `industry_applications` 强制 3-4 条，每条 `title / description`；
- **所有对象** 都设 `additionalProperties: False`，杜绝无关字段。

**校验失败自动触发 1 次修正**：把 Schema 错误路径拼进 prompt 让 LLM 一次改齐。
仍不通过则抛 `LLMSchemaError`。

### 6.3 稳定性三板斧

| 场景 | 方案 |
| --- | --- |
| 网络抖动 / 5xx / 超时 | `tenacity` 指数退避 `2s → 4s → 8s`（封顶 10s，最多 3 次） |
| PDF 解析失败 | `pdfplumber → PyPDF2` 双通道；均失败抛 `FileParseError` |
| 上下文超限 | `_shrink_if_needed`：折叠空白 → 段落去重 → 头尾各 45% 截取（保留章节首尾） |

### 6.4 中转 Header / 本地代理无侵入注入

不去魔改 `openai` SDK 内部字段，改在外层构造 `httpx.Client`：

```python
http_client = httpx.Client(headers=extra_headers or None,
                           proxy=proxy_url, timeout=60)
client = OpenAI(api_key=..., base_url=..., http_client=http_client)
```

**空 Header 一律传 `None`**（而非 `{}`），防止上游对空 Header key 严格校验。
同时兼容 `httpx` 新旧版本 `proxy` / `proxies` 参数名差异。

### 6.5 Markdown Fence 正则清洗

即便设置 `response_format={"type": "json_object"}`，部分兼容 API 仍会外包
```` ```json ... ``` ````。所以 `_strip_markdown_fence` 做两级兜底：
先剥围栏，再截取第一个 `{` 到最后一个 `}` 之间的内容。

### 6.6 matplotlib 一体式海报绘制

- `plt.figure(figsize=(14, 20), dpi=300)` 生成印刷级画布；
- `GridSpec` 竖切 6 行：`header / summary / layers / timeline / industry / footer`；
- 每个面板转为 `0..100 × 0..100` 相对坐标画布，用 `Rectangle / FancyBboxPatch /
  Circle / FancyArrowPatch` 手绘卡片、连接线、时间轴箭头；
- 自研 `_visual_wrap()` 按 CJK=2、ASCII=1 的视觉宽度换行，避免中英混排断行错乱；
- 自动选用 `Microsoft YaHei → SimHei → PingFang SC → Noto Sans CJK` 中文字体链。

---

## 七、PNG 简报输出优秀标准 & 交付校验清单

### 7.1 输出规格

| 项 | 值 |
| --- | --- |
| 文件名 | `briefing.png`（**且仅此一份**） |
| 分辨率 | 300 DPI 印刷级 |
| 画布尺寸 | 14 × 20 inches ≈ 4200 × 6000 px |
| 主色 | 科技蓝 `#005293` (RGB 0, 82, 147) |
| 正文色 | 深灰 `#323232` (RGB 50, 50, 50) |
| 副强调色 | `#3B7EB5`（时间轴 / 装饰条） |
| 底纹色 | 浅蓝 `#EEF3FA`（辅助卡片） |
| 字体 | Microsoft YaHei 优先，缺失时自动回退 |

### 7.2 硬性内容规范（**缺一项无法评优秀**）

| # | 模块 | 内容硬指标 |
| :---: | --- | --- |
| ① | 论文核心摘要 | 精炼摘要 80-500 字 + 1000× 效率定义 20-400 字，两卡分栏 |
| ② | 三层分层架构 | 芯片 / 板卡 / 整机系统三列并排，每列含层名色带 + 层职责 + 2-5 项关键技术 |
| ③ | 三段式时间轴 | 短期 · 中期 · 远期，横向箭头 + 圆点串联，年份粗体、里程碑独立卡片 |
| ④ | 行业落地场景 | ≥ 3 个（本项目最多 4 个）应用卡片，每卡含 title + 20-220 字描述 |

### 7.3 交付自查清单（提交前逐项 ✅）

- [ ] `briefing.png` 已生成，大小 > 500 KB（低于此值通常是空图 / 字体缺失）
- [ ] 打开图片：**四大模块**全部可见，且四个 ①②③④ 章节标题条清晰
- [ ] 中文无豆腐块（无 `□` `?` `.notdef`）
- [ ] 芯片 / 板卡 / 整机三列内容互不重复，各自含 ≥ 2 项关键技术
- [ ] 时间轴 short/mid/long 三段年份清晰 → 短期含 2025、远期含 2035
- [ ] 行业应用卡数量 ≥ 3
- [ ] 卡片文字均未被右边框截断（如有截断按 7.4 调整 `body_wrap`）
- [ ] `error.log` 无 `ERROR` 级别记录（`INFO/WARNING` 可忽略）
- [ ] `python3 -c "import ast; ast.parse(open('generate_briefing.py',encoding='utf-8').read()); print('syntax OK')"` 输出 `syntax OK`
- [ ] 仓库中**不存在** `.env` 与 `error.log`（见 §9 提交规范）

### 7.4 绘图常见问题快速修复

| 症状 | 触发原因 | 一键修复 |
| --- | --- | --- |
| 中文显示为方块 / `.notdef` | 系统缺少 `Microsoft YaHei` / `SimHei` | Win 一般自带；若为精简系统可安装「微软雅黑」字体，重启 Git Bash 后重跑 |
| 卡片文字溢出边框 | 单块文本过长，`body_wrap` 偏大 | 减小对应 `_draw_*_panel` 里 `body_wrap` 参数（默认 60-78） |
| 生成图片为空白 / 全白 | matplotlib 后端错误 | 检查脚本顶部 `matplotlib.use("Agg")` 是否被覆盖，重启终端重跑 |
| 生成图片非常小（KB 级） | LLM 抽取失败但脚本未终止 | 查 `error.log`；schema 校验失败会直接抛 `LLMSchemaError`，不会静默出错 |
| 生成时报 `MemoryError` | 系统内存不足 | 将 `FIG_WIDTH_IN / FIG_HEIGHT_IN` 由 14×20 调低至 12×17，或 `FIG_DPI` 300 → 200 |
| 配色错乱、蓝色偏灰 | 系统色彩管理干扰 | 图片本身颜色正确；用 Windows 自带「照片」或 VSCode 打开验证 |

---

## 八、报错 FAQ 专区

### FAQ-1 `Exit code 49`（Windows 弹出微软商店）

**根因**：Git Bash 里执行 `python` 触发了 Windows 的「App Execution Alias」，
把命令导向 Microsoft Store 安装桩。

**修复**：本项目所有命令一律使用 `python3` / `pip3`，禁用 `python` / `pip` / `py`：

```bash
python3 generate_briefing.py                          # ✅
pip3    install -r requirements.txt                   # ✅
python  generate_briefing.py                          # ❌ 会触发 Exit 49
```

### FAQ-2 `Exit code 127`（command not found: py）

**根因**：`py` 启动器是 Windows 原生 `cmd/PowerShell` 提供的，Git Bash 不识别。

**修复**：全部改用 `python3`。同上。

### FAQ-3 PDF 解析失败 / `FileParseError`

**根因**：PDF 被加密、损坏、或使用了非标准嵌入字体。

**修复**：

```bash
# 1) 检查文件是否存在
ls -la AI+HW2035.pdf

# 2) 尝试用 PyPDF2 单独解析，看是否被加密
python3 -c "from PyPDF2 import PdfReader; r=PdfReader('AI+HW2035.pdf'); print('pages=', len(r.pages), 'encrypted=', r.is_encrypted)"

# 3) 若确实加密，先在本地用 PDF 阅读器 → 另存为一份新 PDF，再重跑
```

### FAQ-4 LLM 返回不合法 JSON / `LLMSchemaError`

**根因**：模型对 `response_format=json_object` 支持不完整；或字段命名幻觉。

**修复**：

```bash
# 1) 查看首次抽取的原文（打开 error.log 找 "JSON 解析失败" 段落）
tail -n 80 error.log

# 2) 切换到 JSON 能力更强的模型
#    编辑 .env → MODEL_NAME=gpt-4o-mini  或  deepseek-chat  或  qwen2.5-72b-instruct

# 3) 重跑
python3 generate_briefing.py
```

`extract_with_validation()` 已内置一次「修正重试」，若仍失败请按以上顺序处理。

### FAQ-5 matplotlib 报 `MemoryError` / 生成图尺寸异常

**根因**：单张 300 DPI 大图在低内存机器上可能超限。

**修复**：编辑 `generate_briefing.py` 顶部：

```python
FIG_WIDTH_IN = 12       # 14 → 12
FIG_HEIGHT_IN = 17      # 20 → 17
FIG_DPI = 200           # 300 → 200（视觉几乎无损）
```

### FAQ-6 中文全部变方块

**根因**：matplotlib 找不到中文字体。日志会明确输出
`未找到常用中文字体，建议安装 Microsoft YaHei / SimHei`。

**修复**：

```bash
# Windows：控制面板 → 字体 → 确认「微软雅黑 Microsoft YaHei」已安装
# 如已安装但仍失败：清理字体缓存
python3 -c "import matplotlib; import shutil, os; c=matplotlib.get_cachedir(); print('cache:', c); shutil.rmtree(c, ignore_errors=True)"
python3 generate_briefing.py
```

---

## 九、提交规范（贴合任务书）

### 9.1 GitHub 上传清单（**必须**包含）

- [x] `generate_briefing.py`
- [x] `requirements.txt`
- [x] `README.md`（本文件）
- [x] `.env.example`（配置模板，字段留占位符）
- [x] `AI+HW2035.pdf`（源论文）
- [x] `briefing.png`（生成后的成品简报）

### 9.2 上传黑名单（**禁止提交**）

| 文件 | 原因 |
| --- | --- |
| `.env` | 含真实 API Key，泄漏后可能被恶意刷额度 |
| `error.log` | 含调试信息，可能包含 prompt / API 报错细节 |
| `__pycache__/` `*.pyc` | Python 字节码，与代码运行无关 |
| `.claude/` `.vscode/` | 编辑器/工具的本地配置 |

建议 `.gitignore`：

```gitignore
.env
error.log
__pycache__/
*.pyc
.claude/
.vscode/
```

### 9.3 作业命名 & 仓库结构

| 项 | 规范 |
| --- | --- |
| 仓库名 | `hw2035-briefing-<学号>` 或 `paper-briefing-hw2035` |
| 主分支 | `main` |
| 提交信息 | 中英文均可；建议 `feat/fix/docs` 前缀 |

### 9.4 提交步骤（Git Bash 内）

```bash
# 首次
cd /d/杂/hw2035_project
git init -b main
git add generate_briefing.py requirements.txt README.md .env.example AI+HW2035.pdf briefing.png .gitignore
git commit -m "feat: AI+HW 2035 briefing generator (PNG output)"
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main

# 后续更新
git add -A
git commit -m "docs: refine README / fix wrap width"
git push
```

### 9.5 验收标准（教师视角一分钟看完）

1. `git clone` → `cp .env.example .env` → 填 Key → `pip3 install -r requirements.txt`
   → `python3 generate_briefing.py` **能一次跑通**；
2. 生成的 `briefing.png` **包含全部四大模块**、中文无豆腐块；
3. README 完整覆盖：环境部署、设计思路、交付清单、FAQ、提交规范；
4. 无密钥泄漏、无日志文件入库。
