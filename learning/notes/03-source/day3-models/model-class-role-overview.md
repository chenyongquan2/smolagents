---
created: 2026-05-05
status: active
tags: [smolagents, models, overview, mental-model, source-reading]
---

# Model 类角色概览：先建 mental model，再读实现

> 💡 **术语统一**：本笔记严格使用 [llm-vs-api-server-architecture.md §2](../../02-concepts/llm-vs-api-server-architecture.md) 约定的 4 角色（用户 / agent 框架 / LLM API 服务器 / LLM 模型）。

## 背景 / 动机

读 [models.py](../../../../src/smolagents/models.py) 的 Model 基类（line 452-630，约 180 行）时，**先不要逐行读 `_prepare_completion_kwargs` 的 50 行参数处理**。

按教学宪法（先 mental model 后实现），先回答 4 个问题：

1. Model 类**是干嘛的**？为什么需要这个抽象？
2. 它面对**几类客户**？每类客户用它的什么方法？
3. 它有**哪些关键方法**？分别在**什么时刻**被**谁**调到？
4. 为什么 **Model 基类自己不发请求** —— 共性留基类、差异留子类的边界画在哪？

把这 4 个问题想清楚，再去读 `_prepare_completion_kwargs` 的 50 行实现，你会发现 **"为什么这 50 行长这样"几乎是可以预测的**。

---

## 1. Model 是什么？一句话 + Week 1 闭环

**Model 是 "LLM 调用渠道" 的抽象** —— 同一个 "把 messages 喂给 LLM、拿到 ChatMessage" 的操作，可以走 5 种以上不同的部署方式（HF Inference API / OpenAI / Anthropic / 本地 Transformers / 本地 VLLM / Bedrock / Azure OpenAI / LiteLLM 路由器 …），Model 基类统一接口。

> 💡 这正是 Week 1 [model-and-protocols-overview.md](../../02-concepts/model-and-protocols-overview.md) 早就给出的结论："Model 子类对应的是**调用渠道**，不是模型本身。同一个 Llama-3.3 可以走 5 种调用方式。" Day 3 在源码侧验证：基类只管"拼 body + 接口契约"，渠道差异全在子类。

---

## 2. Model 面对几类客户？

```
                ┌──────────────────┐
                │  一个 Model 实例  │
                └────────┬─────────┘
                         │
       ┌─────────────────┼─────────────────┐
       ▼                 ▼                 ▼
   面对 agent:        面对子类:          面对持久化:
   "拿 ChatMessage"   "复用拼 body"      "保存/恢复配置"
   (generate / __call__)  (_prepare_completion_kwargs)  (to_dict / from_dict)
```

| 角色 | 谁是客户 | Model 提供什么 | 入口方法 |
|---|---|---|---|
| 拿 ChatMessage | agent / `_step_stream` | 输入 messages + tools，返回 ChatMessage | `generate()` / `__call__()` |
| 拼 body | 子类（InferenceClient/OpenAI/VLLM…）| 把 messages + tools + stop 拼成 LLM provider 能吃的 dict | `_prepare_completion_kwargs()` |
| 保存/恢复 | 序列化系统 | 把模型配置变 dict（自动过滤 token/api_key） | `to_dict()` / `from_dict()` |

> 💡 **理解 3 个角色之后能解释**：为什么 `_prepare_completion_kwargs` 是 protected 命名（带下划线）—— 它是给**子类用**的，不是给 agent 用的。agent 应该只调 `generate()`。

---

## 3. 关键成员变量

`__init__` 设的 5 个实例属性（[models.py:484-496](../../../../src/smolagents/models.py#L484)）：

| 成员 | 类型 | 用途 | 谁会用到 |
|---|---|---|---|
| `model_id` | str / None | 模型标识（如 `"Qwen/Qwen2.5-72B-Instruct"`） | 子类发请求时填入 / `to_dict` 序列化 |
| `flatten_messages_as_text` | bool | 控制 message content 是否展平成纯文本 | `_prepare_completion_kwargs` 调 `get_clean_message_list` 时传入 |
| `tool_name_key` | str = `"name"` | LLM 返回纯文本 tool call 时，从 JSON 里取工具名用的 key | `parse_tool_calls` 兜底解析 |
| `tool_arguments_key` | str = `"arguments"` | 同上，取参数用 | `parse_tool_calls` 兜底解析 |
| `kwargs` | dict | 实例化时存下的默认参数（**最高优先级**） | `_prepare_completion_kwargs` 三层合并的最后一步 |

> 💡 **`self.kwargs` 是 Model 类最有意思的设计**：实例化时传的额外 kwargs 会被存下来，每次 `generate` 时**最后一步**覆盖到 completion_kwargs 里 —— 用户实例化时设的 `temperature=0.7` 会**强制盖过**单次调用传进来的同名参数。还可以传哨兵 `REMOVE_PARAMETER` 主动**删字段**（[models.py:441-449](../../../../src/smolagents/models.py#L441)）。

---

## 4. ⭐ 关键方法按角色分 3 组

### 🔹 组 A · 面对 agent（公开接口）

| 方法 | 用途 | 谁来调 |
|---|---|---|
| `generate(messages, stop_sequences, response_format, tools_to_call_from, **kwargs)` ([:553](../../../../src/smolagents/models.py#L553)) | **抽象方法**：基类只 raise NotImplementedError，子类必须实现 | agent 的 `_step_stream` |
| `__call__(*args, **kwargs)` ([:580](../../../../src/smolagents/models.py#L580)) | 转发到 `generate` | 用户/测试代码 |
| `parse_tool_calls(message)` ([:583](../../../../src/smolagents/models.py#L583)) | **兜底**：当 LLM API 服务器返回纯文本（没有结构化 `tool_calls` 字段）时，从 content 解析 JSON | 子类 `generate` 末尾按需调用 |

**关键点**：基类的 `generate` 是 `raise NotImplementedError("This method must be implemented in child classes")` —— 这是软约束（[python-abc-abstract-base-class.md](../python-prep/python-abc-abstract-base-class.md)），和 Tool.forward 一致。**Model 基类自己不会发请求**。

> 💡 `parse_tool_calls` 是为什么存在的？因为不是所有 LLM provider 都返回结构化的 OpenAI `tool_calls` 字段 —— 有些 provider（特别是开源模型 + 自家 API）只返回纯 JSON 字符串塞在 content 里。这时需要用 `tool_name_key`/`tool_arguments_key` 配置去解析。**这是 ToolCallingAgent 兼容多种 API 的关键兜底**。

### 🔹 组 B · 面对子类（共享拼装逻辑）

| 方法 | 用途 | 谁来调 |
|---|---|---|
| `_prepare_completion_kwargs(messages, stop_sequences, response_format, tools_to_call_from, custom_role_conversions, ...)` ([:502](../../../../src/smolagents/models.py#L502)) | ⭐ **拼 body 的核心** | 所有子类的 `generate` 内部首先调它 |

**这一个方法干的 5 件事**（伪代码）：

```
1. messages → get_clean_message_list (合并连续同 role / 处理 image / role 转换)
2. 加 stop_sequences (如果模型支持)
3. 加 response_format (结构化输出)
4. 加 tools = [get_tool_json_schema(tool) for tool in tools_to_call_from]  ← Day 2 段5 伏笔
5. 三层优先级合并：specific 参数 < 调用时 kwargs < self.kwargs
```

> 💡 ⭐⭐ **Day 2 段 5 伏笔回收**：Day 2 [tool-schema-rendering-mental-model.md](../day2-tools/tool-schema-rendering-mental-model.md) 说 HTTP `tools` 字段**不在 Tool 类上**渲染，而是由 [models.py:288 `get_tool_json_schema`](../../../../src/smolagents/models.py#L288) 渲染。Day 3 终于看到它**在哪里被调到** —— [models.py:540](../../../../src/smolagents/models.py#L540) `_prepare_completion_kwargs` 第 ④ 步。**Day 2 → Day 3 闭环完成**。

### 🔹 组 C · 序列化（按需）

| 方法 | 用途 | 何时被调 |
|---|---|---|
| `to_dict()` ([:596](../../../../src/smolagents/models.py#L596)) | 把模型配置序列化成 dict | save / push_to_hub agent 时 |
| `from_dict(model_dictionary)` ([:628](../../../../src/smolagents/models.py#L628)) | 从 dict 恢复模型 | load agent 时 |

**关键点**：`to_dict` **主动过滤 token / api_key 字段** + 打印警告 —— "为安全起见我不导出敏感字段，请你手动导出"。

---

## 5. 一张图把全部时机串起来

```
agent 启动
   │
   ├── model = InferenceClientModel(model_id="Qwen/...", temperature=0.7)
   │       ↓
   │   Model.__init__ 跑                    ← 设 5 个实例属性 + self.kwargs
   │
agent.run("今天天气如何？")
   │
   ├── 第 1 次 ReAct 循环
   │   │
   │   ├── _step_stream 内部:
   │   │   memory_messages = write_memory_to_messages(memory.steps)
   │   │   chat_message = model.generate(
   │   │       memory_messages,
   │   │       tools_to_call_from=[tool1, tool2],
   │   │       stop_sequences=["<end_code>"]
   │   │   )
   │   │       ↓
   │   │   InferenceClientModel.generate:                ← 子类
   │   │       ├── completion_kwargs = self._prepare_completion_kwargs(...)   ← 组 B 共享逻辑
   │   │       │       ├── get_clean_message_list(messages)
   │   │       │       ├── get_tool_json_schema(tool) × 2  ← Day 2 段5 真正发生地
   │   │       │       └── 三层优先级合并
   │   │       ├── response = self.client.chat.completions.create(**completion_kwargs)  ← 真发请求
   │   │       └── return ChatMessage.from_dict(response.choices[0].message)
   │   │
   │   ├── 拿到 ChatMessage 后看 tool_calls 字段:
   │   │   if 没有 tool_calls 字段 (纯文本):
   │   │       message = self.parse_tool_calls(message)  ← 组 A 兜底
   │   │
   │   └── ... (执行 tool / 写回 memory)
   │
   ├── 第 2 次 ReAct 循环 ...
```

---

## 6. 为什么 Model 基类自己不发请求？

| 子类 | 调用方式 | 依赖 |
|---|---|---|
| `InferenceClientModel` | huggingface_hub 的 InferenceClient | HF token + 第三方推理供应商 |
| `OpenAIModel` | openai SDK | OpenAI api_key |
| `LiteLLMModel` | litellm 库（统一封装多家 API）| litellm 库 + 各家 key |
| `TransformersModel` | 本地 transformers + torch | GPU + 模型权重 |
| `VLLMModel` | 本地 vllm | GPU + vllm 服务 |
| `AmazonBedrockModel` | boto3 + Bedrock runtime | AWS 凭证 |

**5 种渠道的"发请求"代码差异巨大**（HTTP 调用 vs 本地推理 vs AWS SDK 调用），但是**"把 messages + tools + 各种参数拼成 LLM provider 能吃的 dict"是它们共有的需求**。

**所以 smolagents 的设计选择**：
- 共性 → 抽到基类 `_prepare_completion_kwargs`
- 差异 → 留给子类各自实现 `generate`

> 💡 这与 Tool 类的 `__call__` vs `forward` 是**同一个设计哲学**：横切关注点（清洗、拼装、模板渲染）交给基类，业务/渠道细节交给子类。Day 2 [tool-class-role-overview.md](../day2-tools/tool-class-role-overview.md) §3 已经讲过这个原则。**smolagents 整体在反复用这个分层。**

---

## 7. 从 ChatMessage 数据契约说起：5 个 role 的去向

`MessageRole` enum（[models.py:111](../../../../src/smolagents/models.py#L111)）有 5 个值：

```python
USER          = "user"
ASSISTANT     = "assistant"
SYSTEM        = "system"
TOOL_CALL     = "tool-call"
TOOL_RESPONSE = "tool-response"
```

但 OpenAI Chat Completion 协议**只认 user/assistant/system/tool**。所以 [models.py:282-285](../../../../src/smolagents/models.py#L282)：

```python
tool_role_conversions = {
    MessageRole.TOOL_CALL:     MessageRole.ASSISTANT,
    MessageRole.TOOL_RESPONSE: MessageRole.USER,
}
```

`get_clean_message_list` 默认套用这个映射 —— smolagents 内部 5 个 role 在喂给 LLM 之前**降维成 3 个**。

> 💡 **Week 1 [chat-message-roles.md](../../02-concepts/chat-message-roles.md) 闭环**：那篇笔记当时讲了"role 是 LLM 行为的方向盘"。Day 3 看到具体实现 —— smolagents 内部用 5 个 role **是为了在 memory 层把"思考-行动-观察"语义保留清楚**，但喂 LLM 时**降维成对方协议认识的几个**（user/assistant/system）。**5 个 role 的存在价值 = 内部表达的清晰度，而不是协议层的字段**。

---

## 8. 这张地图怎么连接已学的和待学的

| 学习段 | 对应的方法 / 概念 | 状态 |
|---|---|---|
| Day 3 段 1 (Model 基类用途、kwargs 优先级、generate 抽象、parse_tool_calls 兜底) | 组 A | ⏳ 当前 |
| Day 3 段 2 (`_prepare_completion_kwargs` 5 件事 + Day 2 闭环) | 组 B ⭐核心 | ⏳ 待写实现笔记 |
| Day 3 段 3 (`InferenceClientModel.generate` 真实拼装一次 HTTP body) | 子类落地 | ⏳ 待读 |
| Day 3 段 4 (实验脚本：抓真实请求体对比) | 跑代码验证 | ⏳ 待写 |
| Day 4 (`MultiStepAgent.run` 外循环) | 组 A 的调用方（agent 框架内部）| 后续 |
| Day 5 (`_step_stream` 内部) | 真正调 `model.generate` 的那行 | 后续 |

---

## 9. 总结表

| 问题 | 答案 |
|---|---|
| Model 类是干嘛的？ | LLM 调用渠道的抽象（让 agent 不关心是 OpenAI/HF/本地） |
| 真正的"灵魂"是什么？ | `_prepare_completion_kwargs` —— 把 agent 的语义（messages + tools + stop）翻译成 LLM provider 协议的 body |
| 为什么 Model 基类自己不发请求？ | 5+ 种调用渠道的"发请求"代码差异巨大，只有"拼 body"是共性 |
| `self.kwargs` 设计的精髓？ | 实例化时存下的默认参数，**最高优先级**覆盖单次调用 + 哨兵 `REMOVE_PARAMETER` 删字段 |
| `parse_tool_calls` 为什么存在？ | 不是所有 LLM 都返回结构化 `tool_calls`，需要从纯文本兜底解析 |
| HTTP `tools` 字段在哪渲染？ | [models.py:540](../../../../src/smolagents/models.py#L540) `_prepare_completion_kwargs` 第 ④ 步调 [models.py:288 `get_tool_json_schema`](../../../../src/smolagents/models.py#L288)（Day 2 → Day 3 闭环）|
| 5 个 role 喂 LLM 时怎么处理？ | `tool_role_conversions` 把 TOOL_CALL/TOOL_RESPONSE 降维成 OpenAI 标准 ASSISTANT/USER |

---

## 相关链接

- 源码：[src/smolagents/models.py](../../../../src/smolagents/models.py)
  - 数据契约：line 95-218（ChatMessage / MessageRole / ToolCall）
  - 辅助函数：line 220-440（get_tool_json_schema / get_clean_message_list / agglomerate_stream_deltas）
  - **Model 基类**：line 452-630
- Week 1 概念笔记（铺垫）：
  - [model-and-protocols-overview.md](../../02-concepts/model-and-protocols-overview.md) — Model 子类 = 调用渠道
  - [chat-message-roles.md](../../02-concepts/chat-message-roles.md) — role 标记的 LLM 训练原理
- Day 2 闭环：
  - [tool-schema-rendering-mental-model.md](../day2-tools/tool-schema-rendering-mental-model.md) — HTTP tools 字段在 Tool 类外渲染（Day 3 验证）
- Day 3 后续实现笔记（待写）：
  - `model-generate-mental-model.md` —— `_prepare_completion_kwargs` 的 5 步逐行解读
  - `inference-client-model-impl.md` —— InferenceClientModel 的 `generate` 真实拼一次 HTTP body
  - `model-self-kwargs-priority.md` —— 三层优先级合并 + REMOVE_PARAMETER 哨兵机制

## 遗留问题

- [ ] `_prepare_completion_kwargs` 的 5 步逐行（待写实现笔记）
- [ ] InferenceClientModel.generate 真实落地（待读 line 1456-1645）
- [ ] 跑实验：抓一次真实 HTTP body 对比源码每个字段来源
- [ ] `agglomerate_stream_deltas` 流式输出聚合（[models.py:220](../../../../src/smolagents/models.py#L220)）—— 第一遍跳过，Day 5 `_step_stream` 时再回来看
