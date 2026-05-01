---
created: 2026-05-01
status: done
tags: [concept, agent, react, week-1]
---

# 什么是 AI agent？它和"调一次 LLM"到底有什么区别？

> 本笔记回答**一个**问题：到底什么样的程序才能叫 agent？
> 阅读来源：[docs/source/zh/conceptual_guides/intro_agents.md](../../../docs/source/zh/conceptual_guides/intro_agents.md)、[react.md](../../../docs/source/zh/conceptual_guides/react.md)
> ReAct 循环的实现细节会写在另一篇 [react-loop.md](react-loop.md)（待写）。

---

## 1. 一句话定义

> AI agent 是 **"LLM 输出控制工作流"** 的程序。

关键词是 **"控制工作流"**——LLM 的输出**决定下一步代码做什么**，而不只是被代码当成一段文本处理。

## 2. Agent 不是 0/1，是连续谱系

官方文档给了一张表（[原文](../../../docs/source/zh/conceptual_guides/intro_agents.md)），我用代码翻译了一遍：

| Agent 级别 | 谁说了算 | 代码长这样 |
|-----------|---------|-----------|
| ☆☆☆ 简单处理器 | LLM 不影响流程 | `result = process(llm_response)` |
| ★☆☆ 路由 | LLM 选 if/else | `if llm_decides(): a() else: b()` |
| ★★☆ 工具调用者 | LLM 选哪个函数+参数 | `run_func(llm_pick_tool, llm_pick_args)` |
| ★★★ 多步 Agent | LLM 决定要不要继续循环 | `while llm_continue(): step()` |
| ★★★+ 多 Agent | Agent 启动 Agent | `if llm_trigger(): agent_b()` |

> 💡 **我的理解**：从 ☆☆☆ 到 ★★★，本质是**把控制权一点点交给 LLM**。下放的越多，灵活性越大、可靠性越低。这是个 trade-off，不是越高级越好。
>
> smolagents 的 `CodeAgent` / `ToolCallingAgent` 都是 **★★★ 多步 Agent**——LLM 自己决定继续循环还是结束（调 `final_answer`）。

## 3. 多步 Agent 的核心代码（5 行就讲完了）

官方文档给的伪代码：

```python
memory = [user_defined_task]
while llm_should_continue(memory):       # ← 多步循环
    action = llm_get_next_action(memory) # ← 工具调用
    observations = execute_action(action)
    memory += [action, observations]
```

> 💡 **我的理解**：本质就是个 **状态机 + LLM 当决策器**。memory 是状态，LLM 看 memory 决定下一步动作，动作产生新观察，更新 memory。
>
> 这跟你刚才跑 `my_first_agent.py` 看到的 4 个 Step 一模一样：
> - Step 1-3：每步 `web_search` 失败 → memory 多一条 "observation: No results"
> - Step 4：LLM 看 memory 觉得搜不到了，改用自身知识 → 调 `final_answer`

**对应到源码**：

| 伪代码 | smolagents 实现位置 |
|--------|--------------------|
| `memory` | [`src/smolagents/memory.py`](../../../src/smolagents/memory.py) 的 `AgentMemory` |
| `while llm_should_continue` | [`src/smolagents/agents.py:540`](../../../src/smolagents/agents.py) `_run_stream()` 里的循环 |
| `llm_get_next_action` | [`src/smolagents/agents.py:1639`](../../../src/smolagents/agents.py) `CodeAgent._step_stream()` |
| `execute_action` | [`src/smolagents/local_python_executor.py`](../../../src/smolagents/local_python_executor.py) |

## 4. 什么时候**不**该用 agent

文档专门强调了这点（很重要，很多人迷信 agent）：

> 如果预定义工作流够用，**直接写 if/else**。100% 可靠，没有 LLM 引入的不确定性。

**判断标准**：你能不能提前枚举出所有用户需求的类别？

- **能**（如：客服查订单/退款/售后 三选一）→ 写规则，别用 agent
- **不能**（如："我周一来但护照可能延误到周三，能不能周二让我和装备一起去冲浪还能买取消险？"）→ 用 agent

> 💡 **我的理解**：agent 的真正价值是处理 **长尾、组合性需求**。简单需求上用 agent 是杀鸡用牛刀（贵、慢、不稳定）。

## 5. 为什么需要"框架"（不能自己撸）

文档列了 5 件事是 agent 框架必须做的：

1. LLM 引擎（适配各种 provider）
2. 工具列表（Tool 抽象）
3. 输出解析器（从 LLM 文本里抽出工具调用）
4. 系统提示（告诉 LLM 输出什么格式）
5. **记忆**（步骤间传递状态）

> 💡 **我的理解**：3 和 4 是**强耦合**的——解析器依赖系统提示规定的格式。如果你自己写，每次改格式就要同步改两处。这就是为什么 smolagents `agents.py` 里 prompt 模板和 parser 是绑在一起的。
>
> 这也解释了为啥别的库（LangChain）抽象做得那么重——**5 件事是相互纠缠的**，硬要解耦反而会让用户接错配置。

## 6. CodeAgent vs ToolCallingAgent

官方做了 ToolCallingAgent 的两个变体：

| | ToolCallingAgent | CodeAgent ⭐ |
|--|------------------|--------------|
| LLM 输出动作的格式 | JSON `{"tool": "x", "args": {...}}` | Python 代码片段 |
| 业内主流 | ✅ OpenAI / Anthropic | smolagents 的招牌 |
| 优势 | 简单、易解析 | 可组合（嵌套调用、循环、变量复用） |

文档引了 3 篇论文证明代码动作更优：[2402.01030](https://huggingface.co/papers/2402.01030)、[2411.01747](https://huggingface.co/papers/2411.01747)、[2401.00812](https://huggingface.co/papers/2401.00812)。

文档里有句话特别精辟：

> 我们专门设计了我们的代码语言，使其成为表达计算机执行动作的最佳方式。如果 JSON 片段是更好的表达方式，JSON 将成为顶级编程语言。

> 💡 **我的理解**：这个 framing 真的醍醐灌顶。JSON 是数据格式，编程语言是动作格式。让 LLM 用 JSON 描述动作，相当于让人用结构化表格写小说——能写但很别扭。
>
> 但要小心：CodeAgent 的代价是**安全风险**（执行 LLM 写的代码！）。这就是为什么 README 反复强调要用沙箱（E2B / Docker / Pyodide）。`LocalPythonExecutor` 自带的限制不是真正的安全边界。

---

## 关键认知清单（总结）

学完这一节，你应该能回答：

- [x] Agent 和普通 LLM 调用的区别 → LLM 输出控制工作流（不只是被代码处理）
- [x] Agent 不是非黑即白 → 5 个级别的连续谱系
- [x] 多步 agent 核心结构 → memory + while + llm_decide + execute
- [x] 什么时候不用 agent → 工作流能预定义就别用
- [x] CodeAgent 为什么比 JSON 工具调用好 → 可组合、对象管理、训练数据更多
- [x] 为什么需要框架 → 5 件事高度耦合，自己拼会一直改

---

## 相关链接

- 上一步：[notes/01-setup/how-to-run.md](../01-setup/how-to-run.md)（已经跑过 demo 见识过 agent）
- 下一步：react-loop.md（待写）— 单 step 内部到底发生了什么
- 源码入口：[src/smolagents/agents.py:436](../../../src/smolagents/agents.py)
- 论文：[ReAct 原论文 (2210.03629)](https://huggingface.co/papers/2210.03629)
- 学习计划：[../../LEARNING_PLAN.md](../../LEARNING_PLAN.md)

## 遗留问题

放进 [questions.md](../questions.md)：

- [ ] **★★★ 多步 agent 怎么知道该停？** —— `llm_should_continue()` 在 smolagents 里是怎么实现的？是看 LLM 是否调用了 `final_answer` 工具吗？还是有别的信号？
- [ ] **memory 不会无限膨胀吗？** —— 如果 agent 跑 50 步，prompt 里塞 50 步的历史，token 不就爆了？smolagents 有 truncation / summarization 机制吗？
- [ ] **CodeAgent 的 prompt 和 parser 具体怎么配合？** —— 想看看实际 prompt 长啥样，下次调试时打 `agent.system_prompt`
