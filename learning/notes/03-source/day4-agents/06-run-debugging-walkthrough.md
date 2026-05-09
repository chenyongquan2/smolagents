---
created: 2026-05-09
status: active
tags: [smolagents, agents, debugging, day4, walkthrough, hands-on]
---

# Day 4 ⑥ 单步调试：把剧本变成肌肉记忆

> 💡 **本篇定位**：Day 4 的最后一公里。前面 11 篇笔记把 mental model 和剧本都建好了，本篇是**用 VS Code 调试器亲眼验证剧本**的实操手册。

> ⚠️ **必读前置**：
> 1. [③' agent-run-walkthrough-leopard-demo](03b-run-walkthrough-leopard-demo.md)（12 幕剧本 —— 你要验证它）
> 2. [vscode-debugging.md](../../01-setup/vscode-debugging.md)（VS Code 调试基础）
> 3. [③ agent-run-mental-model](03-run-mental-model.md)（控制流骨架）

## 背景 / 动机

[LEARNING_PLAN.md Day 4 验收标准](../../../LEARNING_PLAN.md) 第 3 项：**"在 `run()` 设断点跟一个完整 task"**。

为什么这一步不可跳过：

1. **抽象代码 + generator + 错误处理**叠加，光看笔记很难有"代码动画"感
2. **walkthrough 笔记里 LLM 的"假设输出"和实际可能不同** —— 实证才能校准
3. ABC 软约束实证那次（[abc_soft_constraint_demo.py](../../../scripts/abc_soft_constraint_demo.py)）已经验证：**实证一次能修正几处笔记错误**
4. 调试肌肉记忆 = Day 5 看 1000 行 `_step_stream` 子类时不会迷路

**全程预计 30-45 分钟**。

---

## 1. 准备阶段（5 分钟）

### 1.1 简化 `my_first_agent.py`（推荐，便于精确对照剧本）

[my_first_agent.py](../../../scripts/my_first_agent.py) 当前是：

```python
agent = CodeAgent(
    tools=[WebSearchTool()],
    model=InferenceClientModel(),
    stream_outputs=True,
)
agent.run("豹子全速跑过巴黎艺术桥（Pont des Arts）需要几秒？")
```

调试时会有 3 个不便：

| 问题 | 影响 |
|---|---|
| WebSearchTool 网搜等待 | 容易让你失去节奏感 |
| 步数不确定（3-7 步）| 断点命中次数不可控 |
| `stream_outputs=True` | 多出大量 ChatMessageStreamDelta 事件，干扰断点 |

**临时改成**（精确对照 [③' walkthrough](03b-run-walkthrough-leopard-demo.md) 的剧本）：

```python
from dotenv import find_dotenv, load_dotenv
from smolagents import CodeAgent, InferenceClientModel

load_dotenv(find_dotenv())

agent = CodeAgent(
    tools=[],                      # ⭐ 不带工具（除 final_answer 兜底）
    model=InferenceClientModel(),
    max_steps=4,                   # ⭐ 设小一点
    stream_outputs=False,          # ⭐ 关闭 token 流（剧本是非流式版本）
)

result = agent.run("What is the result of 2 power 3.7384?")  # ⭐ 用剧本里的同一个任务
print(f"\n=== 最终结果: {result} ===")
```

> 💡 **跑完调试可以改回原任务**（豹子艺术桥），那次跑用来体验真实 demo。

### 1.2 检查 launch.json

按 [vscode-debugging.md](../../01-setup/vscode-debugging.md) 确认 [.vscode/launch.json](../../../.vscode/launch.json) 有：

```json
"justMyCode": false
```

**必须**！否则 step into 不进 smolagents 源码，只能在你自己的脚本里走。

### 1.3 双屏布局

```
┌────────────────────────────┬────────────────────────────┐
│  左屏: VS Code 调试器       │  右屏: walkthrough 笔记     │
│  ├─ Variables 面板          │  ③' §3-7 (12 幕剧本)        │
│  ├─ Watch 面板              │  ③' §15 (断点对照表)        │
│  ├─ Call Stack 面板         │                             │
│  └─ Debug Console           │  对照 "应该看到什么"         │
└────────────────────────────┴────────────────────────────┘
```

---

## 2. ⭐ 第一组断点（4 个核心）

打开 [agents.py](../../../../src/smolagents/agents.py)，按行号设断点（行号左侧空白点一下出现红圆点）：

| # | 行号 | 代码 | 应命中 | 看什么 |
|---:|---:|---|---|---|
| ① | **436** | `def run(...)` | 第 0→1 幕 | task=None, memory.steps=[] |
| ② | **488** | `memory.steps.append(TaskStep(...))` | 第 1 幕末尾 | 笔记本即将多一行 |
| ③ | **571** | `action_step = ActionStep(...)` | 第 3 / 6 幕 | 13 字段从全 None 出生 |
| ④ | **582** | `if isinstance(output, ActionOutput) and output.is_final_answer` | 第 7 幕 ⭐ | 转折瞬间 |

---

## 3. ⭐ Watch 表达式（5 个）

打开右上角 **Watch 面板**（Run → Add to Watch 或点 `+` 号），加这 5 个：

```
self.step_number
returned_final_answer
action_step.is_final_answer
len(self.memory.steps)
final_answer
```

> 💡 **`final_answer` 在第 7 幕之前显示 `NameError`** —— 正常。这是变量"诞生时刻"的可视化。

---

## 4. ⭐ 操作流程（按顺序跟着走）

### Step 1 · 启动调试（F5）

- 顶部下拉选 **"Debug my_first_agent.py"**
- 按 `F5` 启动

**预期**：debug 面板亮起，控制台开始输出，最后**停在断点 ① ([agents.py:436](../../../../src/smolagents/agents.py#L436))**。

### Step 2 · 命中 ①（第 0→1 幕）

**看什么**（Variables 面板找 `self`）：

| 字段 | 应该是 |
|---|---|
| `self.task` | `None`（还没接单）|
| `self.memory.steps` | `[]`（笔记本空）|
| `self.step_number` | `0` |

**操作**：按 `F5` 继续 → 应停在断点 ②。

### Step 3 · 命中 ②（第 1 幕末尾）

行：`self.memory.steps.append(TaskStep(task=self.task, task_images=images))`

**看什么**：

1. Variables 找 `self.memory.steps` —— 此时**还是 `[]`**（这一行还没执行）
2. 按 `F10`（step over）执行这一行
3. 再看 `self.memory.steps` —— **变成 `[TaskStep(task='What is the result of 2 power 3.7384?', ...)]`**

> ⭐ **亲眼验证现象 1**：笔记本第一次"长长" 0 → 1。

**操作**：按 `F5` 继续 → 应停在断点 ③（Step 1 开始）。

### Step 4 · 命中 ③ 第 1 次（第 3 幕：Step 1 建空白记录）

行：`action_step = ActionStep(step_number=self.step_number, ...)`

**看什么**：

1. Watch 面板：`self.step_number = 1` ✅
2. 按 `F10` 执行这一行
3. Variables 面板找 `action_step`，看 13 字段：

| 字段 | 应该是 |
|---|---|
| `step_number` | `1` |
| `model_output` | `None` |
| `tool_calls` | `None` |
| `code_action` | `None` |
| `observations` | `None` |
| `action_output` | `None` |
| `is_final_answer` | `False` |
| `error` | `None` |
| `token_usage` | `None` |

**几乎全是 None** ✅

> ⭐ **亲眼验证现象 2**：ActionStep 13 字段从全 None 出生。

**操作**：按 `F5` 继续。

### Step 5 · 命中 ④ 第 1 次（is_final=False）

行：`if isinstance(output, ActionOutput) and output.is_final_answer:`

**预期**：第一次命中时，`output.is_final_answer = False`（Step 1 LLM 还没调 final_answer）。

**看什么**：

1. 把 `output` 加进 Watch
2. 应该是 `ActionOutput(output=None, is_final_answer=False)` 或类似
3. 按 `F10` 执行检查 → **不进 if 内部**（条件 False）

> 💡 **如果第一次命中 ④ 时就是 True**：说明 LLM 选择直接调 `final_answer(2 ** 3.7384)`（一步到位）。这也是合理剧本，只是和 walkthrough 假设的 2 步不同。**记下来**。

**操作**：按 `F5` 继续 → 应停在 ③（Step 2 开始）或 ④（Step 1 的 finally 后）。

### Step 6 · ⭐ 命中 ④ 关键转折（第 7 幕）

**这一刻**：`output.is_final_answer = True`

**看什么**（在按 `F10` 执行 if 内部代码**前**）：

| Watch | 当前值 |
|---|---|
| `returned_final_answer` | `False` |
| `final_answer` | `<NameError: name 'final_answer' is not defined>` |
| `output.output` | `13.166094...`（或类似值）|

**按 `F10` 一步步走过 if 内部**：

| step over 后 | 关键变化 |
|---|---|
| 第 1 次 | `final_answer = 13.166094...` —— **变量"诞生"瞬间** ⭐ |
| 第 2 次 | `returned_final_answer = True` —— 标志位翻 |
| 第 3 次 | `action_step.is_final_answer = True` |

> ⭐ **亲眼验证现象 3**：`final_answer` 局部变量从 NameError 突然有值。
>
> ⭐ **亲眼验证现象 4**：`returned_final_answer` 标志位从 False 翻成 True 的瞬间。

**操作**：按 `F5` 继续 → 程序应该正常结束（退出 while → yield FinalAnswerStep → `run()` 返回）。

### Step 7 · 程序结束

控制台应该打印：

```
=== 最终结果: 13.166094... ===
```

调试结束。

---

## 5. 5 个亲眼验证的现象（汇总）

| # | 现象 | 在哪验证 |
|---:|---|---|
| 1 | **memory.steps 长度演进** 0 → 1 → 2 → 3 | 在 ②/③/④ 断点处看 Watch `len(self.memory.steps)` |
| 2 | **action_step 13 字段从全 None 到被填满** | ③ 断点 step over 几次 |
| 3 | **final_answer 变量诞生** | ④ 第二次命中（is_final=True 时）step over |
| 4 | **returned_final_answer 翻位** | 同上 |
| 5 | **try-finally 执行顺序**：先在 try 内翻位 → 才进 finally | ④ 之后继续 F5，会先在 try 里走完，再到 finally yield |

---

## 6. 进阶（可选 · 第二组断点）

如果第一组都顺利，再加这 4 个看更深细节：

| # | 行号 | 含义 | 看什么 |
|---:|---:|---|---|
| ⑤ | **601** | finally 块 `_finalize_step` | 每步必经的"档案归档" |
| ⑥ | **609** | `FinalAnswerStep(handle_agent_output_types(...))` | 必发的终结事件 |
| ⑦ | **499** | `steps = list(self._run_stream(...))` | 非流式版本的 list 收集 |
| ⑧ | **758** | `write_memory_to_messages` | 翻译器实际产出的 messages |

### ⭐ 特别推荐 ⑧

在 `_step_stream` 内部第一次调 `write_memory_to_messages` 时停下，**直接在 Debug Console 里**输入：

```python
messages = self.write_memory_to_messages()
for msg in messages:
    print(f"[{msg.role}] {str(msg.content)[:100]}...")
```

**亲眼看 LLM 实际收到什么** —— 这是 [⑤ write-memory-to-messages-deep-dive Q3](05-write-memory-to-messages-deep-dive.md) 提到的"最有价值的一行代码"。

会看到：

```
[MessageRole.SYSTEM] [{'type': 'text', 'text': 'You are an expert assistant...
[MessageRole.USER] [{'type': 'text', 'text': 'New task:\nWhat is the result...
```

**对照** [⑤ §6 不变量 1+2](05-write-memory-to-messages-deep-dive.md) —— 应该完全一致。

---

## 7. 跑完后汇报模板

跑完用这个模板记录**哪些和剧本不符** + **跑了几步**：

```markdown
## 调试结果记录（YYYY-MM-DD）

### 1. 实际步数
- N = ?（剧本预期 2 步）

### 2. Step 1 的 LLM 输出（前 100 字）
> action_step.model_output[:100]
"..."

### 3. Step 2 的 LLM 输出（如果有）
> "..."

### 4. final_answer 实际值
> 13.166094... (或别的)

### 5. 亲眼验证现象核对
- [✅/❌] 现象 1: memory.steps 长度演进 0→1→2→3
- [✅/❌] 现象 2: action_step 13 字段全 None 出生
- [✅/❌] 现象 3: final_answer 变量诞生
- [✅/❌] 现象 4: returned_final_answer 翻位
- [✅/❌] 现象 5: try-finally 执行顺序

### 6. write_memory_to_messages 的意外发现
- ...

### 7. 和剧本不符的地方
- ...

### 8. 修正笔记的建议
- 笔记 ③' 第 X 幕需要更新：...
```

---

## 8. 常见坑速查

| 坑 | 解决 |
|---|---|
| 启动后没停在断点 | 检查 launch.json 有 `"justMyCode": false`；删 `.pyc` 重启 |
| 命中断点但 Variables 面板空 | 选 `Locals` tab 而不是 `Globals` |
| F11 step into 进了 `<frozen importlib>` | 按 `Shift+F11` step out 出来，下次用 F10 |
| `__main__` 的 print 一直没输出 | 调试模式下 stdout 可能被缓冲，正常 |
| Step into `_step_stream` 太深 | 按 `Shift+F11` step out，回到 `_run_stream`（Day 4 不深入子类）|
| 断点没触发（红点变空心）| 文件没被加载到调试进程；重启调试 |
| LLM 报 401 / 网络错误 | 检查 `.env` 是否加载 `HF_TOKEN`，参考 [proxy-issue.md](../../01-setup/proxy-issue.md) |

---

## 9. 调试器快捷键速查

| 快捷键 | 作用 | 用在哪 |
|---|---|---|
| `F5` | 继续到下一个断点 | 跨断点跳跃 |
| `F10` | Step over（执行当前行，不进入函数）| 行级精度跟踪 |
| `F11` | Step into（进入函数内部）| 想看函数怎么实现 |
| `Shift+F11` | Step out（跳出当前函数）| 跑深了想回来 |
| `Ctrl+Shift+F5` | 重启调试 | 改了代码 / 想从头再走 |
| `Shift+F5` | 停止调试 | 提前结束 |

---

## 10. 关键启示

| 启示 | 含义 |
|---|---|
| **简化任务 = 精确对照剧本** | 改用 `2**3.7384` + `tools=[]` 比直接跑豹子 demo 更适合首次单步 |
| **Watch 5 个变量 = 实时跟踪状态机** | step_number / returned_final_answer / final_answer 是控制流核心 |
| **`final_answer` NameError 是诞生信号** | 第一次有值瞬间 = 第 7 幕转折点 |
| **进阶 ⑧ 是金矿** | 在 Debug Console 调 `write_memory_to_messages()` 看真实 LLM 输入 |
| **跑完汇报模板 = 反向校准笔记** | 实际剧本 vs 假设剧本 → 修笔记（呼应教学宪法实证循环）|

---

## 11. Day 4 闭合宣告

跑完本笔记 + 填好 §7 汇报模板 = Day 4 验收 3/3 全部通过：

- ✅ 默写 `run()` 伪代码（[③ §3](03-run-mental-model.md)）
- ✅ 解释 `agent.run(stream=True)` 区别（[③''' agent-run-stream-modes](03d-run-stream-modes.md)）
- ✅ **在 `run()` 设断点跟一个完整 task**（本笔记）

**Day 4 完整闭合 ✅**，可以进 Day 5。

---

## 相关链接

- ⚠️ 必读前置：[③' agent-run-walkthrough-leopard-demo.md](03b-run-walkthrough-leopard-demo.md)、[vscode-debugging.md](../../01-setup/vscode-debugging.md)、[③ agent-run-mental-model.md](03-run-mental-model.md)
- 同系列实证：[abc_soft_constraint_demo.py](../../../scripts/abc_soft_constraint_demo.py)（ABC 约束实证 → 修正了 ① + ④ 笔记）
- 上游 Day 1：[action-step-anatomy.md](../day1-memory/action-step-anatomy.md)（ActionStep 13 字段）
- 配套自查：[day4-self-check.md](self-check.md)（12 道题）
- Day 4 全部笔记：见 [README.md Day 4 系列](../../README.md)

## 遗留问题

- [ ] 跑完后实际步数和"假设的 2 步"差距多大？记入 §7
- [ ] LLM 实际输出的 `model_output` 跟剧本里的"假设输出"差距多大？
- [ ] `write_memory_to_messages` 输出的 messages 长什么样？
