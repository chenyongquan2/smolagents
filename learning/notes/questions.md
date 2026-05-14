---
created: 2026-05-01
status: active
tags: [questions, todo]
---

# 学习路上的问题清单

> 学习中遇到不懂的、好奇的、暂时不深究的，全都丢这里。**不要在脑子里反复纠结同一个问题**。
>
> 状态：`[ ]` 待解 / `[x]` 已解（保留答案备查）

## 当前未解

### 🔬 Day 5 待实证（HF 暂访问不了，调试推迟）

01b [toolcalling-walkthrough.md](03-source/day5-step-stream/01-toolcalling-walkthrough.md) 三个"我推演但没实证"的点：

- [ ] **第 2 幕 · `arguments` 字段类型**：断点 [agents.py:1320](../../src/smolagents/agents.py#L1320) 时，`chat_message.tool_calls[0].function.arguments` 是 **str (`'{"city": "Beijing"}'`)** 还是 **dict**？
  - 假设：是 str，所以第 3 幕需要 `parse_json_if_needed` 转 dict
  - 验证方法：跑 compare_agents.py ToolCallingAgent，断点 B 看类型
- [ ] **第 4d 幕 · `memory_step.tool_calls` 写回时机**：断点 [agents.py:1436](../../src/smolagents/agents.py#L1436) 命中时，`memory_step.tool_calls` 是 `None` 还是已经是 list？
  - 假设：是 `None`（这一行才赋值）
- [ ] **state 储物柜闭环（番外 3）**：跨步骤传 `AgentImage` 时，LLM 真能在下一轮输出 `{"image_path": "image.png"}` 触发 `_substitute_state_variables` 替换吗？
  - 验证方法：写个返回 `AgentImage` 的假 tool + 后续问 LLM "describe this image"，跑两步看 messages

- [ ] **★★★ 多步 agent 怎么知道该停？** —— `llm_should_continue()` 在 smolagents 里是怎么实现的？是看 LLM 是否调用了 `final_answer` 工具吗？还是有别的信号？
  - 来源：[02-concepts/what-is-agent.md](02-concepts/what-is-agent.md)
  - 准备查：`src/smolagents/agents.py:540` `_run_stream` 的循环条件

- [ ] **memory 不会无限膨胀吗？** —— 如果 agent 跑 50 步，prompt 里塞 50 步的历史，token 不就爆了？smolagents 有 truncation / summarization 机制吗？
  - 来源：[02-concepts/what-is-agent.md](02-concepts/what-is-agent.md)
  - 已知背景：每幕固定追加 3 条 message（详见 [codeagent-vs-toolcallingagent.md § 8.4 规律 3](02-concepts/codeagent-vs-toolcallingagent.md)），所以增长是线性的
  - 准备查：`src/smolagents/memory.py`，搜 `truncate` / `compact` / `summary_mode`

- [ ] **CodeAgent 的 prompt 和 parser 具体怎么配合？** —— 想看实际 prompt 长啥样
  - 准备查：调试时打 `agent.system_prompt` 和 `src/smolagents/prompts/*.yaml`

- [ ] **CodeAgent 的 `parse_code_blobs()` 怎么实现的？支持嵌套代码块吗？**
  - 准备查：[src/smolagents/utils.py](../../src/smolagents/utils.py)

- [ ] **ToolCallingAgent 万一遇到 LLM 不支持 native function calling 怎么办？fallback 是什么？**
  → 部分已解：[agents.py:1329](../../src/smolagents/agents.py) 有 `model.parse_tool_calls(chat_message)` 兜底，从 content 文本里抠 JSON。但如果 provider 直接 400 拒回（比如 thinking 模型），fallback 救不了，要换模型。完整结论待 Week 2 精读 `parse_tool_calls`。

## 暂不深究（存档备用）

> 这些是学习路上"顺着好奇心问出来"的内容，但**超出了当前学习计划阶段**。先存档，时机到了再回来看。

- [ ] **不同 LLM 厂商协议的细节差异**（OpenAI / Anthropic / Gemini / Bedrock 字段、能力、语义、流式格式都不同）
  → 已存档到 [05-advanced/llm-protocols-deep-dive.md](05-advanced/llm-protocols-deep-dive.md)。**何时回看**：Week 4 进阶 / 真的要跨厂商接 LLM / 调跨协议 bug。

- [ ] **OpenAI Responses API、MCP 协议是干嘛的**
  → 都是为 agent 场景设计的新协议。MCP 已在 [LEARNING_PLAN.md](../LEARNING_PLAN.md) Week 4 计划里。Responses API 暂不必。

- [ ] **CodeAgent 的 `_use_structured_outputs_internally` 模式什么时候用**
  → [agents.py:1705-1707](../../src/smolagents/agents.py)。让 LLM 用 JSON Schema 强制输出 `{"code": "..."}`。属于优化项，主线不必关心。

## 已解（带答案）

- [x] **跑 compare_agents.py 实际观察到的步数差是多少？**（2026-05-01 实测）
  → `len(agent.memory.steps)`：**ToolCallingAgent = 5，CodeAgent = 2**。两者答案都是 86.0（30°C → 86°F）。
  → 拆解：`memory.steps` 包含 1 个 `TaskStep`（开场把 task 包成 message）+ N 个 `ActionStep`（每轮 ReAct）。
   - ToolCallingAgent：1 TaskStep + 4 ActionStep（Beijing/Tokyo/Singapore 各 1 步 + final_answer 1 步）= 5
   - CodeAgent：1 TaskStep + 1 ActionStep（一段 Python 同时完成 3 次查询 + max + 换算 + final_answer）= 2
  → **真正反映 ReAct 轮数的是 ActionStep 数量：4 vs 1**，与预期完全一致。源码证据：[agents.py:488](../../src/smolagents/agents.py)（TaskStep append）、[agents.py:602](../../src/smolagents/agents.py)（ActionStep append）。

- [x] **ToolCallingAgent 跑 compare_agents.py 报 400 Bad Request**（2026-05-01）
  → 默认模型 `Qwen/Qwen3-Next-80B-A3B-Thinking` 是 thinking 模型，HF Router 上对应 provider 不支持 `tools` 字段。换成 `Qwen/Qwen2.5-72B-Instruct` 解决。详见 [02-concepts/codeagent-vs-toolcallingagent.md § 5.5](02-concepts/codeagent-vs-toolcallingagent.md)。

- [x] **smolagents 内部是怎么把 Tool 转成 LLM 能理解的格式的？**
  → ToolCallingAgent 路线：[models.py:288 `get_tool_json_schema`](../../src/smolagents/models.py) 把 `Tool` 转 OpenAI function calling schema，再通过 `tools=[...]` 字段下发。CodeAgent 路线：不做转换，工具说明写进 system prompt（[prompts/code_agent.yaml](../../src/smolagents/prompts/code_agent.yaml)），靠 LLM 听话能力 + 客户端正则解析。

- [x] **为什么 my_first_agent.py 跑出来的 web_search 一直返回空？**
  → DuckDuckGo 在国内 + 代理环境下经常无结果，不是代码问题。学习阶段不影响（agent 会用模型自身知识 fallback）。第 3 周可以换 SerpAPI/Brave 工具。

- [x] **浏览器能上 HF 但 Python 不能？**
  → Python 不读 Windows 系统代理。要在 `.env` 里写 `HTTPS_PROXY`。详见 [01-setup/proxy-issue.md](01-setup/proxy-issue.md)。
