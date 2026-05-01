---
created: 2026-05-01
status: done
tags: [setup, debug, vscode]
---

# 用 VS Code 单步调试 my_first_agent.py

> 本文回答：**怎么用 VS Code 一步步走进 smolagents 内部**，看每个变量、每行代码怎么执行。
> 跑起来的方法见 [how-to-run.md](how-to-run.md)。

---

## 为什么必须调试

agent 的 ReAct 循环是**动态**的——`memory` 一轮轮变、模型每次输出不同、`local_python_executor` 在做 AST 解析。**只看代码看不出运行时状态**。

最高性价比的理解方式：在 `agents.py` 的 `MultiStepAgent.run()` 第一行打断点，按 F10/F11 一步步走，看每个变量怎么变。

---

## 准备工作（一次性）

### 1. 装 VS Code 插件

- 在扩展市场搜 **Python**（Microsoft 官方），点装。
- 它会自动带上 `Pylance` 和 `Python Debugger`（即 `debugpy`）。

### 2. 打开项目

```
File → Open Folder → C:\workspace\smolagents
```

### 3. 选解释器

左下角状态栏应显示 `Python 3.12.1 ('.venv': venv)`。

如果不是：
1. `Ctrl+Shift+P`
2. 输入 `Python: Select Interpreter`
3. 选 `.venv\Scripts\python.exe`

### 4. 配置文件已就绪

项目根目录的 `.vscode/` 里已经有：
- [`launch.json`](../../../.vscode/launch.json) — 3 个调试配置
- [`settings.json`](../../../.vscode/settings.json) — 默认解释器、UTF-8、隐藏 cache

---

## 启动调试

### Step 1 — 打断点

打开 `my_first_agent.py`，**第 23 行**（`agent.run(...)` 这一行），点行号左侧空白。出现红圆点就是断点。

### Step 2 — F5 启动

- 顶部下拉选 **"Debug my_first_agent.py"**
- 按 **F5**（或点绿色三角）
- 程序运行到断点会停下来

### Step 3 — 单步进入源码

在断点处按 **F11**，会跳到：

```
src/smolagents/agents.py:436  →  def run(self, task, ...)
```

继续 F11 / F10 走，会一路深入：

```
my_first_agent.py:agent.run("...")
  ↓ F11
agents.py:436          def run(self, task, ...)
  ↓ F11
agents.py:540          def _run_stream(...)              ← 主循环
  ↓ F11（在循环体内）
agents.py:1639         def _step_stream(...)             ⭐ ReAct 单步
  ↓ F11
models.py:generate_stream(...)                           ← LLM 调用
  ↓ F11
local_python_executor.py:execute(...)                    ← 执行 LLM 输出的代码
  ↓ F11
memory.py:add(...)                                       ← 记忆更新
```

---

## 调试快捷键速查

| 键 | 作用 |
|----|------|
| **F5** | 继续到下一个断点（continue） |
| **F10** | 单步**跳过**（不进入函数）— next |
| **F11** | 单步**进入**（进入函数内部）— step into ⭐ |
| **Shift+F11** | 跳出当前函数 — step out |
| **Ctrl+Shift+F5** | 重启调试 |
| **Shift+F5** | 停止调试 |

---

## 调试时最关键的设置：`justMyCode: false`

`launch.json` 里我设了：

```json
"justMyCode": false
```

| 值 | 行为 |
|----|------|
| `true`（VS Code 默认） | F11 **不会**进入第三方包源码（包括 smolagents），只在你的 .py 里跳 |
| `false`（学习用） | F11 **可以**一路步入 smolagents 内部 ⭐ |

> 💡 如果你 F11 跳过了 `agent.run()`，第一时间检查这个设置。学习阶段一定要 `false`。

---

## 推荐的断点组合（读源码用）

打开这几个文件，分别在这几行打断点：

| 文件 | 行 | 位置 | 看什么 |
|------|----|------|--------|
| [my_first_agent.py](../../scripts/my_first_agent.py) | 23 | `agent.run(...)` | 入口 |
| [src/smolagents/agents.py](../../../src/smolagents/agents.py) | 436 | `def run` | task 怎么进 memory |
| [src/smolagents/agents.py](../../../src/smolagents/agents.py) | 540 | `def _run_stream` | step 一轮一轮怎么转 |
| [src/smolagents/agents.py](../../../src/smolagents/agents.py) | 1639 | `CodeAgent._step_stream` | ⭐ agent 一步内做了什么 |
| [src/smolagents/models.py](../../../src/smolagents/models.py) | `generate_stream` 任一处 | 发给 LLM 的 messages 长啥样 |

按 F5 一次 = 走完一步。每步停下来看 `self.memory.steps` 怎么变。

---

## 调试时一定要做的两件事

### 1. 在 DEBUG CONSOLE 里查变量

VS Code 底部的 DEBUG CONSOLE 是个**实时 Python REPL**，能看当前作用域所有东西：

```python
self.memory.steps           # 看当前所有 step
len(self.memory.steps)      # 跑到第几步了
self.model                  # 用的什么模型
type(self.memory)           # memory 是什么类型
[s.observations for s in self.memory.steps]   # 提取每步的 observation
```

### 2. 用 WATCH 面板长期盯几个表达式

左侧 WATCH 面板里加：

- `len(self.memory.steps)` — 看 step 数变化
- `self.memory.steps[-1] if self.memory.steps else None` — 看最新 step
- `self.step_number` — 当前是第几轮

每次断点命中，这些值会自动刷新。

---

## 推荐的"读源码 + 调试"流程

1. 第一遍**只用 F10**（跳过函数），走完一遍 `_step_stream`，建立全局印象
2. 第二遍**针对感兴趣的子调用 F11**（步入），深入看
3. 看完一轮按 F5 进下一轮，对比两轮的 `memory` 差异

> 💡 不要第一次就 F11 到底，会迷失在调用栈里。先全局，后局部。

---

## 不用 IDE 的备选方案

### `breakpoint()` + pdb

在源码任何地方插一行：

```python
breakpoint()
```

直接 `python my_first_agent.py` 跑，到断点会进入 pdb 交互式调试器。

| pdb 命令 | 作用 |
|----------|------|
| `n` | next（≈ F10） |
| `s` | step into（≈ F11） |
| `c` | continue（≈ F5） |
| `r` | step out |
| `l` | 看当前位置周围代码 |
| `p 变量` | 打印 |
| `pp 变量` | 美化打印 |
| `w` | 调用栈 |
| `q` | 退出 |

### print 大法

源码是可编辑安装的，直接在 `agents.py` 里加 `print(f"DEBUG: ...")`，立即生效。学完用 `git checkout` 还原。

---

## 常见问题

**Q：F5 报 `ModuleNotFoundError: smolagents`**
A：解释器没选对。`Ctrl+Shift+P` → `Python: Select Interpreter` → 选 `.venv\Scripts\python.exe`。

**Q：F11 进不去 smolagents 源码**
A：`launch.json` 里 `justMyCode` 必须是 `false`。

**Q：调试器卡很久**
A：第一次启动 debugpy 慢正常。如果一直卡，是 LLM API 调用慢——agent 思考一轮要 10-30 秒。

**Q：断点不命中**
A：检查文件路径是不是源码文件（`src/smolagents/...`），别打到了 `.venv/Lib/site-packages/smolagents/...`（虽然 editable 模式下两者应该是同一个文件——可以用 `Ctrl+点函数名` 跳转后再打断点）。

---

## 相关链接

- [how-to-run.md](how-to-run.md) — 跑项目（前置条件）
- [`launch.json`](../../../.vscode/launch.json) — 调试配置文件
- [VS Code Python Debugging 官方文档](https://code.visualstudio.com/docs/python/debugging)
