# 踩坑记录

> 每踩一次坑，记一笔。下次同一块石头别绊两次。
> 
> 这份文件是 `AGENTS.md` 的专项补充——AGENTS.md 保持简洁，LESSONS.md 存踩坑经验。
> 符合 Codex 官方推荐的「AGENTS.md 引用独立 markdown」模式。

---

## 🔴 致命级（不解决就跑不了）

### 1. Windows akshare V8 引擎崩溃

**现象：** `py_mini_racer` 报 `SystemError` 或直接闪退。

**原因：** akshare 内置 V8 JS 引擎与 Windows 多进程冲突。

**正确姿势：**
```bash
# ✅ Bash（Git Bash）—— 环境变量和命令必须在同一行
PYMINIRACER_V8_SINGLE_THREAD=1 PYMINIRACER_DISABLE_CONFIGURE_POOL=1 .venv/Scripts/python.exe run_single.py 000012
```

**注意：** `run_single.py` 内部有 `os.environ.setdefault` 兜底，但 `run_batch.py` 启动子进程时**必须手动传这两个环境变量**。

### 2. akshare 并行互斥锁

**现象：** 两个 akshare 进程同时启动，后一个卡住不动。

**原因：** akshare 全局连接锁。

**正确姿势：** 默认串行跑（最安全）。并行用 `--parallel`，每只间隔 **10 秒**启动（`run_batch.py` 已实现）。

---

## 🟡 警告级（不影响跑但影响体验）

### 3. Shell 选错导致编码/路径问题

| 场景 | 用什么 |
|------|--------|
| 文件查找/读写、中文路径、curl、git | **Bash（Git Bash）** |
| Windows 软件安装（MSI）、环境变量、注册表 | **PowerShell** |

### 4. 次新股技术指标 N/A

上市时间短、数据不足，技术分析部分显示 "N/A"。**不是 bug，关注基本面即可。**

### 5. 海外数据源 404（Reddit/StockTwits）

这些平台只覆盖美股，A/港股无数据。忽略即可，v0.2.5 已做 fallback。

### 6. DeepSeek Structured Output 偶发 None

已有自动 fallback（降级为自由文本解析），不影响最终报告。

---

## 🔧 已修复（记下来防止回退）

### 7. `_extract_first` IndexError

**修复：** commit `1a65e86`（2026-06-04）—— 正则失败时返回默认值。

**教训：** 给 LLM 输出写正则提取，永远加 try/except + fallback。LLM 的输出格式不可靠。

---

## 📊 运行参数速查

| 指标 | 数值 |
|------|------|
| 单次耗时 | **10-25 分钟** |
| Input tokens | **50-100 万** |
| 辩论轮数 | 1-3 轮（茅台 1 轮，紫金/招行 3 轮） |

**为什么这么久：** 12 个 Agent 串行调用：4 分析师 → 多空辩论（1-3轮）→ 研究经理 → 交易员 → 3 人风控 → 组合经理。DeepSeek V4 Pro 深度思考模型，辩论轮数越多上下文越长。

**加速手段：** `--debate 1` 强制只辩 1 轮；非关键 Agent 可切 V4 Flash。

---

## 🗂️ 关键路径速查

| 什么 | 在哪 |
|------|------|
| 报告输出 | `reports/<代码>_<日期>/` |
| 关注列表 | `.watchlist.json`（gitignore） |
| 中文字体 | `C:\Windows\Fonts\simhei.ttf` |
| Python | `.venv/Scripts/python.exe`（3.12.3） |
| gh | `~/.local/bin/gh.exe` |
| pandoc | `~/.local/bin/pandoc.exe` |
| LibreOffice | `C:\Program Files\LibreOffice\program\soffice.exe` |

---

## 🐍 Python 装包

`py` → Python 3.12.3，装包必须 `py -m pip install <包名>`（不能直接用 `pip`）。

---

## 💡 新坑模板

```markdown
### N. [标题]

**现象：**

**原因：**

**正确姿势：**

**教训：**
```

---

> 最后更新：2026-06-06 | 来源：AGENTS.md + git log + 实际运行经验 + Codex 官方文档


---

## 微信资料卡（文字版 + 图像版）

### 文字版

把分析报告的核心结论以文字卡片形式分享到微信。文字版可以复制粘贴、修改内容、不需要生成工具。

### 格式规范

```text
🔴/🟡 评级色块 + 股票名称 + 代码

━━━━━━━━━━（分隔线用 ━，不用 —，微信不会截断）
 日期  当前价  目标价  时间维度
━━━━━━━━━━

 最终评级

━━━━━━━━━━
 一句话结论
━━━━━━━━━━

 好的一面

✅ 要点一
✅ 要点二

 坏的一面

🔻 要点一
🔻 要点二

 执行方案

🔴/🔵 持仓者：xxxxx
   缩进补充说明

 建仓信号 / 入场条件

1️⃣ 条件一
2️⃣ 条件二
3️⃣ 条件三

 止损线：¥xx.00
```

### 排版要点

- **宽度控制**：每行不超过 30 个中文字符，确保微信不换行错位
- **分隔线**：用 `━`（U+2501），六个一组 `━━━━━━`，微信不会渲染成乱码
- **评级色块**：🔴=减持/卖出，🟡=持有，🟢=买入
- **要点前缀**：✅ 正面，🔻 负面，🔴 持仓操作，🔵 空仓操作
- **缩进**：操作方案的第二行用两个空格缩进，区分主操作和补充说明
- **空行**：每个大段之间一个空行，段内紧凑

### 数据来源

从每份报告的「组合经理最终裁决」中提取：
- 评级、当前价、目标价、时间维度
- 一句话结论
- 好的一面（核心数据 3-4 条）
- 坏的一面（核心风险 3-4 条）
- 执行方案（持仓/空仓分别给出）
- 入场条件或建仓信号
- 止损线

### 图像版

图像版采用 `render_card_html.py`（Markdown→HTML）+ `render_card_image.py`（HTML→PNG，headless Chrome/Edge 截图）自动生成。详见 `AGENTS.md` 的「资料卡生成规范」和 `.codex/资料卡模板.md`。

```bash
py scripts/render_card_image.py reports/<代码>_<日期>/<股票名>_资料卡.md
```
