---
created: 2026-05-01
status: done
tags: [setup, run, venv, env]
---

# 如何把 smolagents 项目跑起来

> 本文回答一个问题：**从零到看到 agent 输出**，需要做哪些事？
> 调试相关请看 [vscode-debugging.md](vscode-debugging.md)。
> 代理踩坑请看 [proxy-issue.md](proxy-issue.md)。

---

## 0. 当前已就绪状态（参考）

| 项 | 状态 | 备注 |
|----|------|------|
| Python | ✅ 3.12.1 | 项目要求 ≥ 3.10 |
| 虚拟环境 | ✅ `.venv/` | 在项目根目录 |
| smolagents | ✅ 1.25.0.dev0 (editable) | 源码改动立即生效 |
| HF_TOKEN | ✅ 已配 | 在 `.env` |
| HTTPS_PROXY | ✅ 已配 `127.0.0.1:7897` | 在 `.env`，国内必须 |
| Demo 脚本 | ✅ `my_first_agent.py` | 在项目根目录 |

如果你是从零搭，按下面 1 → 2 → 3 → 4 走。

---

## 1. 准备虚拟环境（一次性）

```bash
cd C:/workspace/smolagents

# 创建 venv
python -m venv .venv

# 验证
.venv/Scripts/python.exe --version   # 应输出 Python 3.12.x
```

> **为什么用虚拟环境**：smolagents 可选依赖一大堆（torch、selenium、e2b…），装到全局 Python 会污染别的项目。

---

## 2. 可编辑模式安装（一次性）

```bash
.venv/Scripts/python.exe -m pip install -e ".[toolkit]"
```

参数解释：
- `-e` = **editable**，源码改动立即生效（学习场景必须）
- `.` = 当前目录的 `pyproject.toml`
- `[toolkit]` = 装 `WebSearchTool`、`VisitWebpageTool` 等常用工具

**安装时间**：1-3 分钟，看网速。

**如果以后要装更多可选依赖**：

```bash
.venv/Scripts/python.exe -m pip install -e ".[toolkit,vision,litellm,mcp]"
```

可选项见 [pyproject.toml](../../../pyproject.toml) 里的 `[project.optional-dependencies]`。

---

## 3. 配置 `.env`（一次性）

项目根目录的 `.env` 文件应该包含：

```bash
# 代理（国内必须；端口看你 Clash Verge 的设置）
HTTPS_PROXY=http://127.0.0.1:7897
HTTP_PROXY=http://127.0.0.1:7897

# HuggingFace token（去 https://huggingface.co/settings/tokens 申请）
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxx
```

> **关键点**：Python 的 httpx **不会**自动读 Windows 系统代理。必须显式给环境变量，并且代码里 `load_dotenv()` 要在 import 网络库**之前**调用。
>
> 详见 [proxy-issue.md](proxy-issue.md)。

---

## 4. 跑起来：3 种方式任选

### 方式 A：直接命令行运行（最简单）

```bash
cd C:/workspace/smolagents
.venv/Scripts/python.exe my_first_agent.py
```

> Windows bash / PowerShell 都行。**必须用 `.venv/Scripts/python.exe`**，不要用全局 `python`，否则不在虚拟环境里。

### 方式 B：先激活 venv 再 `python xxx.py`

```bash
# bash (Windows Git Bash)
source .venv/Scripts/activate
python my_first_agent.py

# PowerShell
.venv\Scripts\Activate.ps1
python my_first_agent.py
```

激活后命令行前面会出现 `(.venv)` 前缀，之后直接用 `python` 就是 venv 里的。

### 方式 C：smolagents CLI（不写代码也能跑）

```bash
.venv/Scripts/smolagent.exe "帮我算一下 9.9 和 9.11 哪个大"
```

可加参数：

```bash
.venv/Scripts/smolagent.exe "Plan a trip to Tokyo" \
  --model-type InferenceClientModel \
  --model-id Qwen/Qwen3-Next-80B-A3B-Thinking \
  --tools web_search
```

---

## 5. 跑通后看到的输出长这样

```
┌── New run ─────────────────────────────────┐
│ 豹子全速跑过巴黎艺术桥需要几秒？           │
└── InferenceClientModel - Qwen/Qwen3...─────┘
━━━━━━━━━━━━━━━━ Step 1 ━━━━━━━━━━━━━━━━━━
Thought: I need to find the length of the bridge ...
─ Executing parsed code: ────────────────
  bridge_info = web_search("Pont des Arts length")
─────────────────────────────────────────
[Step 1: Duration 26.19s | Tokens: 2096/4395]
━━━━━━━━━━━━━━━━ Step 2 ━━━━━━━━━━━━━━━━━━
... (继续若干步)
Final answer: 9.24
```

> 💡 **观察重点**：每个 Step 都包含 `Thought` → `Executing code` → `Step duration`。这就是 ReAct 循环的可视化。这是 agent 区别于普通 LLM 调用的关键——**多轮思考、失败重试**。

---

## 6. 常见错误速查

| 报错 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError: smolagents` | 没装 / 解释器不对 | 走第 2 步，或在 VS Code 选 `.venv` 解释器 |
| `WinError 10061 目标计算机积极拒绝` | 代理没起来 / 端口错 | 看 [proxy-issue.md](proxy-issue.md) |
| `httpx.ConnectError: timed out` | 没配代理 | 给 `.env` 加 `HTTPS_PROXY` |
| `Authentication required` | HF_TOKEN 错或没读到 | 检查 `.env` 文件、`load_dotenv()` 调用顺序 |
| `No results found!` (web_search) | DDG 在代理下不稳 | 不影响，agent 会用模型自身知识；学习阶段忽略 |

---

## 相关链接

- [LEARNING_PLAN.md](../../LEARNING_PLAN.md) — 4 周学习计划
- [vscode-debugging.md](vscode-debugging.md) — 单步调试
- [proxy-issue.md](proxy-issue.md) — 代理问题完整排查过程
- 源码入口：[src/smolagents/agents.py:436](../../../src/smolagents/agents.py)
