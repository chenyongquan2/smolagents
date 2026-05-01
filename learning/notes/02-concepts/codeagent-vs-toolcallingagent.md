---
created: 2026-05-01
status: done
tags: [concept, code-agent, tool-calling-agent, week-1]
---

# CodeAgent vs ToolCallingAgent — 同样的 ReAct，不同的"动作格式"

> 本笔记回答**一个**问题：smolagents 提供的两种 agent 实现，到底差在哪？什么时候选哪个？
> 前置：[what-is-agent.md](what-is-agent.md)
> 阅读来源：[docs/source/zh/conceptual_guides/intro_agents.md](../../../docs/source/zh/conceptual_guides/intro_agents.md) 第 89-107 行
> 对比 demo：[../../compare_agents.py](../../scripts/compare_agents.py)

---

## 1. 一句话区别

> 同一个 LLM 决策，**用不同格式表达**——ToolCallingAgent 让 LLM 输出 JSON，CodeAgent 让 LLM 输出 Python 代码。

但这一点点格式差异，带来了**能力上的指数级差距**。

## 2. LLM 输出长啥样（最直观对比）

任务：查 Beijing/Tokyo/Singapore 的温度，找最热的，换算成华氏度。

### ToolCallingAgent — JSON 风格

LLM 一步只能调一个工具，**至少 4 轮**：

```json
// Step 1
{"name": "get_temperature", "arguments": {"city": "Beijing"}}     // → 25
// Step 2
{"name": "get_temperature", "arguments": {"city": "Tokyo"}}       // → 30
// Step 3
{"name": "get_temperature", "arguments": {"city": "Singapore"}}   // → 28
// Step 4
{"name": "final_answer", "arguments": {"answer": 86}}             // 30 * 1.8 + 32
```

### CodeAgent — Python 代码

LLM 一步内**写完整段逻辑**，**1 轮**搞定：

```python
cities = ["Beijing", "Tokyo", "Singapore"]
temps = {city: get_temperature(city) for city in cities}
hottest = max(temps.values())
final_answer(hottest * 1.8 + 32)
```

> 💡 **直观感受**：CodeAgent 像让一个会编程的人完成任务（用变量、循环、表达式）。ToolCallingAgent 像让一个**只会指令一个一个下**的人，每次还得等结果回来才能下下一个指令。

**论文实验**：CodeAgent 平均**比 ToolCallingAgent 少 30% 步数**。

---

## 3. 能力差异（这才是关键）

| 能力 | ToolCallingAgent | CodeAgent |
|------|------------------|-----------|
| 一步调多个工具 | ❌ 一次只能 1 个 | ✅ 想调几个调几个 |
| 工具输出做计算 | ❌ 必须存 memory 下一步处理 | ✅ 当场用 Python 算 |
| 用循环/条件 | ❌ 只能让 LLM 多轮重新决策 | ✅ `for`/`if` 一步搞定 |
| 中间变量复用 | ❌ 没有变量概念 | ✅ Python 变量自由用 |
| 错误处理 | ❌ 失败只能再让 LLM 决策 | ✅ `try/except` 捕获 |
| 训练数据契合度 | 中（JSON 工具调用是新格式） | 高（互联网海量 Python 代码） |

> 💡 **本质洞察**：JSON 是**数据描述语言**，Python 是**动作描述语言**。
>
> 让 LLM 用 JSON 表达"做什么"，相当于让人用 Excel 表格写小说——勉强能写，但极其别扭。
> 这也就是为什么[官方文档](../../../docs/source/zh/conceptual_guides/intro_agents.md)第 95 行说："如果 JSON 片段是更好的表达方式，JSON 将成为顶级编程语言。"

---

## 4. 源码层面的差异

两者都继承 `MultiStepAgent`，只是 `_step_stream` 实现不同：

| 类 | 文件:行 | 关键差异 |
|----|---------|---------|
| `ToolCallingAgent._step_stream` | [agents.py:1276](../../../src/smolagents/agents.py) | 调 `model.generate(..., tools_to_call_from=tools)`，走 LLM provider 的 native function calling 协议 |
| `CodeAgent._step_stream` | [agents.py:1639](../../../src/smolagents/agents.py) | LLM 输出**纯文本**，自己用 `parse_code_blobs()`(行 1709) 抽出 \`\`\`python ... \`\`\` 代码块；丢给 `python_executor` 执行(行 1727) |

**关键观察**：

```python
# ToolCallingAgent (agents.py:1296)
output_stream = self.model.generate_stream(
    input_messages,
    stop_sequences=["Observation:", "Calling tools:"],
    tools_to_call_from=self.tools_and_managed_agents,  # ← 走原生工具协议
)

# CodeAgent (agents.py:1661)
output_stream = self.model.generate_stream(
    input_messages,
    stop_sequences=stop_sequences,
    # ← 没有 tools_to_call_from！LLM 当成普通文本生成
)
```

> 💡 **架构设计的精妙处**：CodeAgent 不依赖 LLM provider 提供 function calling，**任何**能写 Python 的 LLM 都能用。这是为啥 smolagents 强调"模型无关"。

---

## 5. CodeAgent 的代价（天下没有免费的午餐）

1. **安全风险** ⚠️：执行 LLM 写的代码！README 反复强调要用沙箱（E2B / Docker / Pyodide）。`LocalPythonExecutor` 不是真正的安全边界。
2. **对模型要求高**：弱模型容易写错语法。GPT-3.5 / 早期 Claude Instant 跑 CodeAgent 效果差。现代模型（GPT-4o、Claude 4、DeepSeek-V3、Qwen3）都很稳。
3. **错误更隐蔽**：JSON 错只是 schema 错，明显；代码错可能是逻辑 bug，跑出来"答案看似合理但算错了"，更难发现。

---

## 6. 选型决策表

| 场景 | 选 | 理由 |
|------|----|----|
| 学习 / 研究 / 个人项目 | **CodeAgent** ⭐ | 能力强、步数少、便宜 |
| 强模型可用 | **CodeAgent** | 能力压制 |
| 弱模型 / 低成本 | **ToolCallingAgent** | 不容易代码错乱 |
| 严格安全合规（金融/医疗） | **ToolCallingAgent** | JSON 调用边界清晰，不执行任意代码 |
| 多模态/工具调用本身就是 LLM 训过的 | **ToolCallingAgent** | 走原生协议更稳 |

> 💡 **学习阶段直接用 CodeAgent**。等你做生产项目再考虑 ToolCallingAgent 的安全性优势。

---

## 7. 上手 demo

我做了一个对比脚本：[compare_agents.py](../../scripts/compare_agents.py)

```bash
.venv/Scripts/python.exe compare_agents.py
```

**它做了什么**：
- 同一个任务（查 3 城气温 → 找最热 → 换算华氏度）
- 同一个模型（HF Inference）
- 同一个工具（假的 `get_temperature`，不依赖网络，结果可重复）
- 跑 ToolCallingAgent 和 CodeAgent 各一次
- 最后打印步数对比

**预期观察**：
- ToolCallingAgent：4 步（3 次查询 + 1 次 final_answer）
- CodeAgent：1-2 步（一段代码同时完成查询 + max + 换算）
- 两个 agent 答案应该一致（86°F），但 LLM 调用次数差好几倍

**官方对比 demo**（更简单的版本）：[examples/agent_from_any_llm.py](../../../examples/agent_from_any_llm.py)
> 只问"巴黎天气"，单个工具调用，差异不明显，但代码更短可以参考。

**配套 examples**（同样涉及两种 agent 切换）：
- [examples/multiple_tools.py](../../../examples/multiple_tools.py) — 货币兑换 + 时间查询多工具，注释里展示了如何在两种 agent 间切换
- [examples/rag_using_chromadb.py](../../../examples/rag_using_chromadb.py) — RAG 例子，注释展示两种切换

---

## 关键认知清单

学完这一节，你应该能回答：

- [x] 两种 agent 的本质区别（动作格式：JSON vs Python）
- [x] 为什么 CodeAgent 通常更省步数（一步多工具 + 计算）
- [x] CodeAgent 不依赖 provider 的 function calling（"模型无关"）
- [x] CodeAgent 的代价（安全、模型要求）
- [x] 学习阶段优先选哪个（CodeAgent）

---

## 相关链接

- [what-is-agent.md](what-is-agent.md) — 什么是 agent（前置概念）
- [compare_agents.py](../../scripts/compare_agents.py) — 对比 demo（自己做的）
- [examples/agent_from_any_llm.py](../../../examples/agent_from_any_llm.py) — 官方简版对比
- 源码：
  - [agents.py:1276 ToolCallingAgent._step_stream](../../../src/smolagents/agents.py)
  - [agents.py:1639 CodeAgent._step_stream](../../../src/smolagents/agents.py)
- 论文：
  - [Executable Code Actions Elicit Better LLM Agents (2402.01030)](https://huggingface.co/papers/2402.01030)
  - [TaskBench (2411.01747)](https://huggingface.co/papers/2411.01747)

## 遗留问题

放进 [questions.md](../questions.md)：

- [ ] 跑 `compare_agents.py` 实际观察到的步数差是多少？和预期 4 vs 1 一致吗？如果不一致，是哪个模型表现不同？
- [ ] CodeAgent 的代码解析器 `parse_code_blobs()` 在 [src/smolagents/utils.py](../../../src/smolagents/utils.py) 里，怎么实现的？支持嵌套代码块吗？
- [ ] ToolCallingAgent 走的是 LLM 的 native function calling，但万一 LLM 不支持（比如老的 Llama）怎么办？fallback 是什么？
