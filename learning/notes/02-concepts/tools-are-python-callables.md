---
created: 2026-05-10
status: active
tags: [smolagents, concepts, tools, abstraction, codeagent, toolcallingagent, day5]
---

# 两种 agent 调用的工具，本质都是 Python callable

> ⚠️ **必读前置**：
> - Day 2 ① [tool-class-role-overview](../03-source/day2-tools/tool-class-role-overview.md) — Tool 类的 3 个客户角色
> - Day 5 ⓪ [step-stream-role-overview §3-5](../03-source/day5-step-stream/00-step-stream-role-overview.md) — 5 步骨架 + 2 个分歧点
>
> 本笔记不长 —— 把 Day 2 + Day 5 已经"零散讲过"的一个核心洞察**单独抽出来集中讲**，方便未来 Week 3 自定义工具 / Week 4 接 MCP 时回头查。

---

## 1. 一句话定调

不管 `CodeAgent` 还是 `ToolCallingAgent`，**最终调用工具的那一行代码**都是 Python 函数调用：

```python
tool(**args)           # ← Python callable
```

**Tool 类是 smolagents 整个系统的"通用插槽"** —— 异构来源的工具（本地函数 / MCP 远程协议 / Gradio Space / HF Hub 工具 / managed sub-agent）在边界处全都被**规范成 Python callable**，进入 agent 内部后看起来都一样。

两种 agent 的差异**不在工具本质**，在"谁解析参数 + 谁触发调用"。

---

## 2. 同一条调用链

```
                   ┌────────────────────────────────────┐
                   │   Tool 实例（Python callable）     │
                   │   ──────────────────────────────  │
                   │   Tool.__call__(**args, sanitize=True)│  ← 框架包装层（Day 2 ②）
                   │       ↓                             │
                   │   Tool.forward(**args)             │  ← 你写的业务逻辑
                   └────────────────────────────────────┘
                          ▲                  ▲
                          │                  │
       ┌──────────────────┘                  └──────────────────┐
       │                                                          │
ToolCallingAgent 第 4b 幕                          CodeAgent 第 4 幕
execute_tool_call(name, args):                     python_executor(code) 内部：
  tool = self.tools[name]                            代码字符串里写 get_temperature("Beijing")
  tool(**args, sanitize_inputs_outputs=True)         沙箱解析 → 调 Python 函数
       ↑                                                   ↑
   framework 解析 JSON 后直接调                       沙箱解析代码后调
```

最终入口都是 **`Tool.__call__` → `Tool.forward(**args)`** —— 一个 Python 函数调用，无差异。

---

## 3. 差异不在工具本质，在"谁解析参数 + 谁触发调用"

| 维度 | ToolCallingAgent | CodeAgent |
|---|---|---|
| LLM 输出格式 | JSON `tool_calls` | Python 代码字符串 |
| 谁解析参数 | **agent framework**（`parse_json_if_needed`）| **沙箱**（AST 解析）|
| 谁触发调用 | agent framework 第 4b 幕 `execute_tool_call` | 沙箱执行 `get_temperature("Beijing")` 这行代码 |
| 工具本身 | 同一个 Tool 实例 | 同一个 Tool 实例 |

**这就是 Day 5 mental model §3 ⭐⭐ "2 个分歧点"的本质**：

- 分歧点 1（动作 ③ parse output）= **"怎么从 LLM 输出抠出'要调什么'"** 的差异
- 分歧点 2（动作 ④ execute action）= **"谁来安排这次调用 + 在哪里调"** 的差异

**两个分歧点都不在"工具长什么样"** —— 工具一直都是 Python callable。

---

## 4. 异构来源都被规范成 Python callable

任何能进 smolagents agent 的工具，**不管原始形态多么不同**，最终都得包装成 `Tool` 实例：

| 来源 | 怎么进 agent | 最终是 |
|---|---|---|
| 本地 Python 函数 | `@tool` 装饰器 / `Tool` 子类 | Python callable |
| MCP 远程协议工具 | `MCPClient` 包装 | Python callable（背后发 RPC）|
| Gradio Space | `Tool.from_space(...)` | Python callable（背后发 HTTP）|
| HF Hub 工具 | `Tool.from_hub(...)` | Python callable |
| LangChain 工具 | `Tool.from_langchain(...)` | Python callable |
| managed_agent（子 agent）| 实现了 `__call__` 接口 | Python callable |

> 💡 **这是 Tool 类作为"统一抽象层"的真正价值**：让 agent 内部代码**只需关心"调 Python callable"**，不必为每种来源写一套适配。Day 2 ① [3 个客户角色](../03-source/day2-tools/tool-class-role-overview.md#3-tool-类的-3-个客户角色)就是这个统一抽象的具体体现。

---

## 5. 一个微妙的边界：CodeAgent + 远程沙箱

当 `CodeAgent(executor_type="e2b" / "docker" / "modal" / "wasm" / "blaxel")` 时：

- 代码在**远程进程 / 容器 / WebAssembly** 里跑
- Tool 函数被 [`PythonExecutor.send_tools()`](../../../src/smolagents/local_python_executor.py#L1679) 序列化（pickle / source 重建）发送到远程
- 远程沙箱里仍然是 **Python callable 调用** —— 只是不在你本地 Python 进程

```python
# PythonExecutor 抽象类（local_python_executor.py:1677）
class PythonExecutor(ABC):
    @abstractmethod
    def send_tools(self, tools: dict[str, Tool]) -> None: ...        # ⭐ 把 Tool 送到沙箱
    @abstractmethod
    def send_variables(self, variables: dict[str, Any]) -> None: ...
    @abstractmethod
    def __call__(self, code_action: str) -> CodeOutput: ...
```

**统一抽象在边界处仍然成立** —— 跨进程 / 跨容器只是"调用的物理位置"变了，**接口契约不变**（Tool callable）。这是 Day 6 沙箱深度笔记会详讲的内容。

---

## 6. 这个统一抽象为什么是设计胜利

如果 smolagents 不做这个统一：

| 反例：每种工具来源各管各 | 实际：统一 Tool 抽象 |
|---|---|
| `agent` 要维护 N 个适配器：本地函数走 a 路径，MCP 走 b 路径，Gradio 走 c 路径... | `agent` 只需要 `tool(**args)` |
| ToolCallingAgent + MCP / CodeAgent + Gradio 等组合**都要单独适配** | 任意 agent × 任意 tool 来源都开箱即用 |
| 自定义新工具来源 = 改 agent 核心代码 | 自定义新工具来源 = 只需写一个新 Tool 子类（继承 Tool, 实现 forward）|

**这是 smolagents 整个生态扩展性的根** —— 也是 Week 3 你能轻易写自定义 tool 的原因（继承 Tool → 实现 forward → 整个 agent 体系自动认）。

---

## 7. 跟 Week 1 / Day 2 / Day 5 的闭环

| 笔记 | 闭环点 |
|---|---|
| **Week 1** [codeagent-vs-toolcallingagent](codeagent-vs-toolcallingagent.md) | "动作格式不同（JSON vs 代码）"现在更精确：不是工具不同，是 LLM 输出格式不同 → 框架/沙箱解析路径不同 |
| **Week 1** [tool-creation-decorator-vs-subclass](tool-creation-decorator-vs-subclass.md) | 不管 `@tool` 还是 `Tool` 子类，产出都是 callable 实例 |
| **Week 1** [codeagent-how-it-works](codeagent-how-it-works.md) Q1 工具传递路径 | prompt 文本 vs OpenAI tools 字段只是 LLM 看到的形态不同；工具本身（Python callable）是同一个 |
| **Day 2** ① [tool-class-role-overview](../03-source/day2-tools/tool-class-role-overview.md) | 3 个客户角色（agent / Tool 自己 / 序列化）都通过统一接口访问 |
| **Day 2** ② [tool-lifecycle-checks-mental-model](../03-source/day2-tools/tool-lifecycle-checks-mental-model.md) | `__call__` vs `forward` 分层 = "框架包装层 + 业务层"统一接口的实现 |
| **Day 5** [00 step-stream-role-overview §3-5](../03-source/day5-step-stream/00-step-stream-role-overview.md) | 5 步骨架 + 2 分歧点：本笔记是"为什么这两个分歧点都不动工具本质"的深度解释 |
| **Day 5** [01 toolcalling-walkthrough 第 4b 幕](../03-source/day5-step-stream/01-toolcalling-walkthrough.md) | `tool(**args, sanitize_inputs_outputs=True)` 这一行代码 |
| **Day 5** [02 codeagent-walkthrough 第 4 幕](../03-source/day5-step-stream/02-codeagent-walkthrough.md) | `python_executor(code)` 内部最终也是 `tool(**args)` |

---

## 自检（学完本笔记应能）

- [ ] 一句话回答"CodeAgent 和 ToolCallingAgent 调用的工具有没有本质区别"
- [ ] 默画两种 agent 的调用链最后都汇到 `Tool.__call__ → Tool.forward(**args)`
- [ ] 列出 4 种异构工具来源（本地 / MCP / Gradio / HF Hub），解释为什么 agent 内部不需要为它们写适配器
- [ ] 解释远程沙箱（e2b / docker）下"Tool 仍然是 Python callable"的精确含义
- [ ] 用"Tool 统一抽象"解释 Week 3 你能轻易写自定义 tool 的原因
