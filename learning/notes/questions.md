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

- [ ] **★★★ 多步 agent 怎么知道该停？** —— `llm_should_continue()` 在 smolagents 里是怎么实现的？是看 LLM 是否调用了 `final_answer` 工具吗？还是有别的信号？
  - 来源：[02-concepts/what-is-agent.md](02-concepts/what-is-agent.md)
  - 准备查：`src/smolagents/agents.py:540` `_run_stream` 的循环条件

- [ ] **memory 不会无限膨胀吗？** —— 如果 agent 跑 50 步，prompt 里塞 50 步的历史，token 不就爆了？smolagents 有 truncation / summarization 机制吗？
  - 来源：[02-concepts/what-is-agent.md](02-concepts/what-is-agent.md)
  - 准备查：`src/smolagents/memory.py`，搜 `truncate` / `compact`

- [ ] **CodeAgent 的 prompt 和 parser 具体怎么配合？** —— 想看实际 prompt 长啥样
  - 准备查：调试时打 `agent.system_prompt` 和 `src/smolagents/prompts/*.yaml`

- [ ] **跑 compare_agents.py 实际观察到的步数差是多少？** —— 和预期 4 vs 1 一致吗？
  - 来源：[02-concepts/codeagent-vs-toolcallingagent.md](02-concepts/codeagent-vs-toolcallingagent.md)

- [ ] **CodeAgent 的 `parse_code_blobs()` 怎么实现的？支持嵌套代码块吗？**
  - 准备查：[src/smolagents/utils.py](../../src/smolagents/utils.py)

- [ ] **ToolCallingAgent 万一遇到 LLM 不支持 native function calling 怎么办？fallback 是什么？**

## 已解（带答案）

- [x] **为什么 my_first_agent.py 跑出来的 web_search 一直返回空？**
  → DuckDuckGo 在国内 + 代理环境下经常无结果，不是代码问题。学习阶段不影响（agent 会用模型自身知识 fallback）。第 3 周可以换 SerpAPI/Brave 工具。

- [x] **浏览器能上 HF 但 Python 不能？**
  → Python 不读 Windows 系统代理。要在 `.env` 里写 `HTTPS_PROXY`。详见 [01-setup/proxy-issue.md](01-setup/proxy-issue.md)。
