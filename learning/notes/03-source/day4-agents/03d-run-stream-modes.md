---
created: 2026-05-08
status: active
tags: [smolagents, agents, stream, run, decision-guide, day4]
---

# `agent.run()` 实战选型：stream=True 还是 False？什么时候用 RunResult？

> 💡 **本篇定位**：[③ mental-model](03-run-mental-model.md) 讲了 `run()` 内部 9 件事 + 流式/非流式分支。本篇是**实战选型搭子**：你**作为外部调用者**，到底该传什么参数？

> ⚠️ **必读前置**：[③' walkthrough](03b-run-walkthrough-leopard-demo.md)（看过豹子 demo 的事件序列）+ [③'' event-types](03c-stream-event-types.md)（认识 8 种事件类型）

## 一句话决策

| 选哪个 | 含义 | 项目经理类比 |
|---|---|---|
| `stream=False`（默认） | "做完了再回来汇报，中间别打扰我" | 老板让张三"完事再说" |
| `stream=True` | "每完成一步都跟我说一声" | 老板要全程跟进进度 |

> 💡 **80% 场景用默认 `stream=False` 就够了**。除非你有"实时性需求"，否则不用碰 `stream=True`。

---

## 1. 代码层面的差异

### `stream=False`（默认，最常用）

```python
result = agent.run("查北京天气")    # 返回字符串 / 答案
print(result)                       # ← 直接拿到答案
```

**返回类型**：`Any`（最终答案的 output）—— 直接是值。

### `stream=True`

```python
gen = agent.run("查北京天气", stream=True)    # 返回 generator
for event in gen:                              # ← 必须 for 循环
    if isinstance(event, FinalAnswerStep):
        print(event.output)
        break
```

**返回类型**：`Generator[StreamEvent]`（generator 对象）—— **必须迭代**才能拿到事件。

> ⚠️ **常见坑**：`print(agent.run("...", stream=True))` 会打印 `<generator object ...>` 这种垃圾。**你不能直接 print，必须 for 循环**。

---

## 2. ⭐ 5 大场景对照表（什么场景该传啥）

### 该用 `stream=False` 的场景

| 场景 | 理由 |
|---|---|
| **简单脚本 / 命令行工具**（写个查询助手 / 数据分析）| 只要答案，等就等了 |
| **批处理任务**（一次跑 100 个 task） | 用户不在线看，没必要流式 |
| **API 后端**（包成 HTTP /generate 端点）| 客户端就要个 JSON 响应 |
| **单元测试 / 评测**（断言答案对不对）| 测试只关心最终结果 |
| **简单 demo 验证**（豹子 demo 那种）| 跑一次看结果，没必要复杂 |

### 该用 `stream=True` 的场景

| 场景 | 理由 |
|---|---|
| **Web UI 实时展示**（Gradio / 自建前端）| 要给用户看"打字效果" / 步骤卡片 |
| **早停 / 流控**（token 超预算就中断）| 边算边监控才能及时停 |
| **调试 / 实时日志**（看 LLM 思考过程）| 实时打印每个 ToolCall / 错误 |
| **进度条**（长任务给用户进度）| 数 ActionStep 的次数 |
| **流式 API**（SSE / WebSocket 推给前端）| 一边算一边推 |

---

## 3. 项目经理类比延展：两种工作姿势

### `stream=False` 的工作姿势

```
老板（用户）→ "查北京天气"
              ↓
              [等待... 张三关在办公室不出来]
              ↓
              [10 秒后...]
              ↓
张三 → "查完了，是 18°C"
```

老板**整段时间是阻塞的**，不知道张三在干啥。优点：**简单**。缺点：**没法插嘴**。

### `stream=True` 的工作姿势

```
老板（用户）→ "查北京天气"
              ↓
              [for 循环开始]
              ↓
张三 → "我准备调天气工具"           （事件 1）
              ↓
张三 → "调用完了，结果 18°C"        （事件 2）
              ↓
张三 → "Step 1 完整档案给你"        （事件 3）
              ↓
张三 → "全部任务完成，是 18°C"      （事件 4）
              ↓
              [老板在 for 循环里实时处理每个事件]
```

老板**全程跟进**，可以**中途插嘴**（`agent.interrupt()`）。优点：**实时 + 可控**。缺点：**写 dispatch 代码更复杂**。

---

## 4. 4 个实战代码模板

### 模板 A · 简单脚本（90% 入门用户用这个）

```python
from smolagents import CodeAgent, InferenceClientModel

agent = CodeAgent(tools=[], model=InferenceClientModel(...))
answer = agent.run("查北京天气")
print(answer)
```

### 模板 B · Web UI 实时打字效果

```python
agent.stream_outputs = True    # ⭐ 还要打开 token 级流（默认关）

for event in agent.run(task, stream=True):
    if isinstance(event, ChatMessageStreamDelta):
        send_to_frontend_realtime(event.content)    # 一字一字推给前端
    elif isinstance(event, ActionStep):
        send_step_card(event)                        # 步骤卡片
    elif isinstance(event, FinalAnswerStep):
        finish(event.output)
        break
```

> 💡 想看真实代码 → [gradio_ui.py:262](../../../../src/smolagents/gradio_ui.py#L262)（仓库里的 Web UI 实现）

### 模板 C · 超预算自动停

```python
total_tokens = 0
BUDGET = 100_000

for event in agent.run(task, stream=True):
    if isinstance(event, ActionStep) and event.token_usage:
        total_tokens += event.token_usage.input_tokens + event.token_usage.output_tokens
        if total_tokens > BUDGET:
            agent.interrupt()                       # 喊停
            print(f"超预算 ({total_tokens} > {BUDGET})，已中断")
            break
    elif isinstance(event, FinalAnswerStep):
        print(f"完成，用了 {total_tokens} tokens")
        break
```

### 模板 D · 调试时实时打印每步发生啥

```python
for event in agent.run(task, stream=True):
    if isinstance(event, ToolCall):
        print(f"[要调工具] {event.name}({event.arguments})")
    elif isinstance(event, ActionStep) and event.error:
        print(f"[step {event.step_number} 出错] {event.error}")
    elif isinstance(event, FinalAnswerStep):
        print(f"[完成] {event.output}")
        break
```

> 💡 完整 8 种事件 dispatch 模板见 [③'' event-types §6](03c-stream-event-types.md)。

---

## 5. ⭐ 第 3 种姿势：`return_full_result=True`

如果你 `stream=False` 但**还想知道 token 总量 / 状态 / 历史**，传 `return_full_result=True`：

```python
result = agent.run("查北京天气", return_full_result=True)
# ⭐ 不是字符串了，是 RunResult 对象

print(result.output)        # 最终答案
print(result.token_usage)   # 总 token（input + output）
print(result.state)         # "success" / "max_steps_error"
print(result.steps)         # 所有步骤的 dict 列表
print(result.timing)        # 总耗时
```

### 三种返回类型完整对照

| 调用方式 | 返回类型 | 适合场景 |
|---|---|---|
| `agent.run(task)` | 直接是答案（`Any`）| **最简单**，绝大多数初学者 |
| `agent.run(task, return_full_result=True)` | `RunResult` 对象（含 token / state / 历史） | **要做监控但不想流式** |
| `agent.run(task, stream=True)` | `Generator[StreamEvent]`（必须 for 消费） | **要流式 / UI / 流控** |

> 💡 **`stream=True` + `return_full_result=True` 组合**：源码里 `return_full_result` 在流式分支不生效（流式直接返回 generator）。所以这两个**互斥**。

---

## 6. 决策树

```
              你需要"边跑边处理"吗？
              ├─ 否 → stream=False（90% 场景）
              │       ↓
              │       你需要 token 统计 / state / 完整历史吗？
              │       ├─ 否 → return_full_result=False（默认）
              │       │       拿到的是直接答案
              │       └─ 是 → return_full_result=True
              │               拿到 RunResult 对象
              │
              └─ 是 → stream=True
                      ↓
                      用 isinstance 派发处理 8 种事件
                      （参考 ③'' agents-stream-event-types §6 模板）
```

---

## 7. 一句话总结

> **写脚本 / 写测试 / 包 API 后端 → `stream=False`。写 UI / 调试器 / 流控逻辑 → `stream=True`。需要 token 统计 → `return_full_result=True`**。

### 新手提醒

1. **先把 `stream=False` 的简单玩法用熟**（豹子 demo 那种）
2. **等开始写 Web UI 或想做流控时再切到 `stream=True`**
3. **不要一开始就追求 stream** —— 它会让你的代码复杂 3 倍，但 80% 场景用不上
4. **生产 API 后端**：99% 用 `stream=False`，除非你前端真的要 SSE 实时效果

---

## 8. 一张图总览三种姿势

```
                       agent.run(task, ...)
                              │
        ┌─────────────────────┼──────────────────────┐
        │                     │                      │
        ▼                     ▼                      ▼
  默认（最简）        return_full_result=True    stream=True
  返回答案值            返回 RunResult           返回 generator
        │                     │                      │
   answer = ...        result.output           for ev in gen:
   print(answer)       result.token_usage         isinstance(ev, X):
                       result.state                  ...
                       result.steps
                              │
                       ┌──────┴──────┐
                       │             │
                  ↓ 适合           ↓ 适合
           简单脚本                监控 / 统计           Web UI / 流控 / 调试
           豹子 demo               自动评测              进度条 / 早停
           批处理                  长任务后看清单        实时打字效果
           单元测试                 不需要实时
           API JSON 响应
```

---

## 相关链接

- ⚠️ 必读前置：[③ agent-run-mental-model.md](03-run-mental-model.md)、[③' agent-run-walkthrough-leopard-demo.md](03b-run-walkthrough-leopard-demo.md)、[③'' agents-stream-event-types.md](03c-stream-event-types.md)
- 概念基石：[stream-abstraction-explained.md](../../02-concepts/stream-abstraction-explained.md)（流式 vs 非流式 trade-off）
- 真实 consumer 代码：[gradio_ui.py:262](../../../../src/smolagents/gradio_ui.py#L262)
- `RunResult` 定义：[agents.py:196](../../../../src/smolagents/agents.py#L196)
- 源码：[agents.py:436 run](../../../../src/smolagents/agents.py#L436)、[agents.py:494-538 流式 vs 非流式分支](../../../../src/smolagents/agents.py#L494)

## 遗留问题

- [ ] `stream=True` + `return_full_result=True` 同时传会怎样？源码看 `run()` 里 `return_full_result` 只在 `stream=False` 分支用到 —— 即流式时这参数被静默忽略。**这是 bug 还是有意？** Week 3 实战时可以提 issue 验证
- [ ] 多 agent 场景下，父 agent 调子 agent 时（`__call__`）是用 stream=True 还是 False？看 [agents.py:868 `__call__`](../../../../src/smolagents/agents.py#L868) —— Week 4 multi-agent 时再看
