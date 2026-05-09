---
created: 2026-05-07
status: active
tags: [smolagents, agents, naming, stream, generator, mental-model, day4]
---

# 为什么叫 `_run_stream` / `_step_stream`？stream 在这里指什么

> ⚠️ **必读前置**：本笔记假定你已读过 [stream-abstraction-explained.md](../../02-concepts/stream-abstraction-explained.md)（通用 stream 概念）+ [python-generators-yield.md](../python-prep/python-generators-yield.md)（Python `yield`）。如果没读，先去那两篇建立直觉。

## 背景 / 动机

读 Day 4 [agents.py](../../../../src/smolagents/agents.py) 时，第一眼看到这两个方法名会直觉性地疑问：

- 为什么叫 `_run_stream` 而不是 `_run`？
- 为什么叫 `_step_stream` 而不是 `_step`？
- 这里的 "stream" 是 LLM 那种"逐字蹦出"的流吗？

本笔记一次性回答清楚 5 个问题：

1. `stream` 在这两个方法名里**到底指什么流**？
2. 命名规律是什么？是否成对出现？
3. **流式版 vs 非流式版**怎么互相包装？
4. smolagents 里**有几层 stream 同时存在**？容易混淆的是什么？
5. `_` 前缀 + `_stream` 后缀的命名约定为什么这样设计？

---

## 1. 一句话答案

> `_run_stream` / `_step_stream` 里的 `stream` = **"事件流（event stream）"** —— 一边跑一边 yield 出 ReAct 循环的步骤事件。**它们是 Python 生成器函数（generator）**，用 `yield` 实现 stream 抽象。

注意：**这里的 stream 和 LLM token stream 不是同一层东西**（细节见 §5）。

---

## 2. 直接看签名（事实证据）

[agents.py:540 `_run_stream`](../../../../src/smolagents/agents.py#L540)：

```python
def _run_stream(
    self, task: str, max_steps: int, images: list["PIL.Image.Image"] | None = None
) -> Generator[ActionStep | PlanningStep | FinalAnswerStep | ChatMessageStreamDelta]:
    self.step_number = 1
    returned_final_answer = False
    while not returned_final_answer and self.step_number <= max_steps:
        ...
        yield element       # ← 它在 yield，不是 return
        ...
        yield action_step
        ...
    yield final_answer_step
```

[agents.py:772 `_step_stream`](../../../../src/smolagents/agents.py#L772)：

```python
def _step_stream(
    self, memory_step: ActionStep
) -> Generator[ChatMessageStreamDelta | ToolCall | ToolOutput | ActionOutput]:
    """
    Perform one step in the ReAct framework: the agent thinks, acts, and observes the result.
    Yields ChatMessageStreamDelta during the run if streaming is enabled.
    """
    raise NotImplementedError("This method should be implemented in child classes")
```

**两个方法的返回类型都是 `Generator[...]`** —— 这呼应 [python-generators-yield.md](../python-prep/python-generators-yield.md)：**带 `yield` 的函数 = 生成器，被调用时不立即执行，每次 `next` 才往下走一段**。

> 💡 **所以"stream" 在这里就是 Python 生成器实现的事件流**。和 [stream-abstraction-explained.md §3](../../02-concepts/stream-abstraction-explained.md) 4 个核心特征对照：
> - ✅ 有顺序：step 1 → step 2 → step 3
> - ✅ 逐步到达：每次 yield 一个事件
> - ✅ 生产-消费解耦：用户 for 循环消费，agent 内部按自己节奏 yield
> - ✅ 长度可能未知：要跑多少步取决于 LLM，最多 `max_steps`

---

## 3. ⭐ 命名规律：流式 / 非流式成对设计

smolagents 在 ReAct 的**外循环**和**内一步**两个层级，都做了"流式 + 非流式"两个版本。

### 配对清单

| 流式版（generator，带 `_*_stream`）| 非流式包装（普通方法） | 包装关系 |
|---|---|---|
| `_run_stream` ([:540](../../../../src/smolagents/agents.py#L540)) | `run` ([:436](../../../../src/smolagents/agents.py#L436)) | `run(stream=False)` 内部：[`steps = list(self._run_stream(...))`](../../../../src/smolagents/agents.py#L499) |
| `_step_stream` ([:772](../../../../src/smolagents/agents.py#L772)) | `step` ([:782](../../../../src/smolagents/agents.py#L782)) | `step` 实现就一行：[`return list(self._step_stream(memory_step))[-1]`](../../../../src/smolagents/agents.py#L787) |

### 包装关系图

```
                         用户脚本
                            │
              ┌─────────────┴──────────────┐
              ▼                            ▼
       run(stream=True)              run(stream=False)
              │                            │
              │  直接返回 generator         │  内部 list() 收集
              │  给用户消费                 │  只取 final_answer
              ▼                            ▼
                       _run_stream()           ◄── 真正的核心实现（generator）
                            │
                            │  while 循环里调用
                            ▼
                       _step_stream()          ◄── 子类实现的 generator
                            │
                            │  step() 是其非流式包装
                            ▼
                  list(_step_stream())[-1]
```

> 💡 **设计哲学**：**核心实现写流式版**（`yield` 一段一段吐），**非流式版只是 `list()` 收集** —— 一份代码两种用法。这就是 [stream-abstraction-explained.md §5](../../02-concepts/stream-abstraction-explained.md) 末尾说的"流式核心 + 非流式包装"模式。

> 💡 **跟 Day 3 Model 类对比**：Model 那边流式 / 非流式是**两个独立方法**（`generate` vs `generate_stream`，未来可能合一）。agents.py 这边**直接用一个 generator 做核心**，外层加 `stream` 参数控制是否 `list()` —— 更优雅的架构。

---

## 4. 为什么需要"流式"？设计动机

**关键场景：用户想看"这一步发生了什么"，不想等全部跑完**。

| 场景 | 不流式的痛 | 流式的解 |
|---|---|---|
| 调试 agent | 跑 20 步要 5 分钟，错了不知道哪步崩 | 每步打日志 + 实时看 memory 变化 |
| Web UI 实时显示 | 用户盯着空白屏幕等几分钟 | 每出一个 step 立即推到前端（gradio_ui.py 就这么用）|
| 提前中断 | 已经跑了 10 步发现走偏了，没法停 | 消费方看到走偏立即 break 出循环 |
| 流式 token 显示 | 用户得等 LLM 生成完整回答才能看 | LLM 一吐 token 就传出去 |

如果不用生成器写法，你就得**在 `run()` 里准备一个回调列表 / 队列 / 全局状态**才能让外面看到中间步骤 —— 而 `yield` 让"边跑边吐"成了**语言原生支持的一行写法**。

> 💡 **这是 Python `yield` 比回调（callback）更优雅的关键场景**：流的生产者和消费者都在同一个进程时，`yield` 比"注册回调 + 异步触发"代码量少一个量级，而且控制流是"自然的"（看代码就知道执行顺序）。

---

## 5. ⭐⭐ smolagents 里其实有**两层 stream** 同时存在

这是最容易混淆的地方。回看签名你会注意到：

```python
_run_stream  -> Generator[ActionStep | PlanningStep | FinalAnswerStep | ChatMessageStreamDelta]
                          └─────── 步骤流 ────────┘   └─── token 流 ───┘
_step_stream -> Generator[ChatMessageStreamDelta | ToolCall | ToolOutput | ActionOutput]
                          └─── token 流 ───┘   └─────── 子事件流 ───────┘
```

**返回类型联合里同时出现两类事件** —— 这反映了 smolagents 同一个 generator **同时承载两层 stream**。

### 两层对比

| 层级 | 粒度 | 类型 | 何时启用 | 时间尺度 |
|---|---|---|---|---|
| **外层 · 步骤流** | 一整个 step | `ActionStep` / `PlanningStep` / `FinalAnswerStep` / `ToolCall` / `ToolOutput` / `ActionOutput` | **永远启用**（`_run_stream` / `_step_stream` 本身就是 generator） | 秒 |
| **内层 · token 流** | LLM 一个 token delta | `ChatMessageStreamDelta` | 仅当 [`agent.stream_outputs = True`](../../../../src/smolagents/agents.py#L352) | 毫秒 |

### 嵌套关系（呼应 [stream-abstraction-explained.md §6](../../02-concepts/stream-abstraction-explained.md)）

```
┌──────────────────────────────────────────────────────┐
│  Layer 3 · agent 步骤流（_run_stream / _step_stream）  │
│   yield: ActionStep / PlanningStep / FinalAnswerStep  │
│   粒度: 一整步 (秒级)                                  │
└────────────────────┬─────────────────────────────────┘
                     │ 子类 _step_stream 内部调
                     │ model.generate(stream=True)
                     ▼
┌──────────────────────────────────────────────────────┐
│  Layer 2 · LLM token 流（HTTP SSE）                    │
│   yield: ChatMessageStreamDelta                       │
│   粒度: 一个 token (毫秒级)                             │
└──────────────────────┬───────────────────────────────┘
                       │ HTTP chunked
                       ▼
┌──────────────────────────────────────────────────────┐
│  Layer 1 · TCP 字节流                                  │
└──────────────────────────────────────────────────────┘
```

### 关键观察

> 💡 **`_step_stream` 既是 L3 的生产者，也是 L2 的消费者**：
> - 当外面用 `for ev in agent.run(stream=True)` 消费时，`_step_stream` 在生产 L3 步骤事件
> - 当 `_step_stream` 内部调 `model.generate(stream=True)` 时，它在消费 L2 token 事件
> - **smolagents 把 L2 收到的每个 `ChatMessageStreamDelta` 直接 yield 出去**（透传到 L3），让用户既能看 step 粒度也能看 token 粒度
> - **一份代码同时支持两种粒度**的消费

> 💡 **这解释了为什么 `_step_stream` 的返回类型联合里要包含 `ChatMessageStreamDelta`** —— 它不是 `_step_stream` 自己产生的，是从下层 `model.generate` 透传上来的。

---

## 6. 命名拆解：`_run_stream` 这 11 个字符在传达什么

| 部分 | 含义 |
|---|---|
| `_` 前缀 | **protected**：给框架内部用，**用户不应该直接调**。Python 没有真正的 private，靠命名约定 |
| `run` 主词 | 跟公开方法 `run` 是同一概念（"跑一个 task"） |
| `_stream` 后缀 | **这是个生成器**，返回 `Generator[...]`，需要 `for` / `list` / `next` 消费 |

### 对照其他命名

| 命名 | 信号 | 例 |
|---|---|---|
| `foo` | 公开方法，普通返回值 | `run`、`step` |
| `_foo` | 内部方法，普通返回值 | `_validate_name`、`_setup_tools` |
| `_foo_stream` | 内部方法，**返回 generator** | `_run_stream`、`_step_stream` |
| `foo_stream` | 公开方法，返回 generator（少见） | （smolagents 里没有，约定都内部化）|

> 💡 **命名就是契约**。看到 `_run_stream` 应该立刻心里冒出：
> 1. "这不是给我调的，给我调的是 `run()`"
> 2. "它返回的不是普通值，是个流，得 `for` 才能消费"
> 3. "如果我直接调它，不 `for` / `list` 就完全不会执行"（generator 特性）

这种**命名即契约**的写法在 smolagents 处处可见：
- Day 1 `_validate_arguments` —— `_` 前缀
- Day 3 `_prepare_completion_kwargs` —— `_` 前缀
- Day 4 `_run_stream` / `_step_stream` —— `_` 前缀 + `_stream` 后缀

---

## 7. 实战速查表

| 你想做的事 | 应该调什么 |
|---|---|
| 跑一个 task，只要最终答案 | `agent.run(task)` |
| 跑一个 task，实时看每一步 | `for step in agent.run(task, stream=True):` |
| 跑一个 task，**还要看 token 一个个蹦出来** | 先 `agent.stream_outputs = True`，再 `agent.run(task, stream=True)`，遍历时检测 `isinstance(ev, ChatMessageStreamDelta)` |
| 单跑一步（调试用）| `agent.step(action_step)` |
| 单跑一步要看子事件流 | `for ev in agent._step_stream(action_step):`（不推荐，框架契约） |

---

## 8. 关键启示

| 启示 | 含义 |
|---|---|
| **stream 在这里 = 事件流，不是 token 流**（默认情况下） | 命名容易误导初学者 |
| **流式核心 + 非流式包装** = smolagents 优雅设计 | 一份代码两种用法 |
| **`_*_stream` 命名 = generator 契约** | 看到就知道要 `for` 消费 |
| **两层 stream 同时存在 + 透传** | `_step_stream` 既生产 L3 又消费/透传 L2 |
| **`yield` 是 stream 在同进程的实现手段** | 跨网络的 stream 用 SSE / WebSocket，编程模型一致 |

---

## 相关链接

- ⚠️ 必读前置 1：[stream-abstraction-explained.md](../../02-concepts/stream-abstraction-explained.md) — 通用 stream 概念
- ⚠️ 必读前置 2：[python-generators-yield.md](../python-prep/python-generators-yield.md) — Python `yield` / generator
- 上游 Day 4：[smolagents-package-overview.md](00-package-overview.md) — Day 4 包级鸟瞰
- 上游 Day 4：[multi-step-agent-role-overview.md](01-multi-step-agent-role-overview.md) — MultiStepAgent 类角色
- 下游 Day 4：`agent-run-mental-model.md`（待写） — 用本笔记建立的 stream 心智模型读 `run` + `_run_stream` 的具体控制流
- 源码：[agents.py:540 `_run_stream`](../../../../src/smolagents/agents.py#L540)、[agents.py:772 `_step_stream`](../../../../src/smolagents/agents.py#L772)

## 遗留问题

- [ ] `_run_stream` 内部嵌套 `_generate_planning_step`（也是 generator）—— Day 4 后续笔记里看 generator 嵌套的传递机制（`yield from` 还是手动 `for ... yield`）
- [ ] CodeAgent / ToolCallingAgent 各自的 `_step_stream` 在哪里 yield `ChatMessageStreamDelta`（透传 L2 token 流的具体位置）—— Day 5 验证
- [ ] `stream_outputs` 在 `_run_stream` 流程里的具体作用点 —— Day 5 看 `_step_stream` 实现时验证
