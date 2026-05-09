---
created: 2026-05-05
status: active
tags: [smolagents, models, mental-model, source-reading, request-body]
---

# `_prepare_completion_kwargs`：把 agent 语义翻译成 LLM 协议 body

⚠️ **必读前置**：[model-class-role-overview.md](model-class-role-overview.md)

> 本篇是 Day 3 实现层笔记。先看 role-overview 建立 Model 类的角色框架（3 类客户、方法分组、为什么基类不发请求），再回来读这一篇 —— 你会发现 `_prepare_completion_kwargs` 长这样几乎是**可推导的**。

> 💡 **术语统一**：本笔记严格使用 [llm-vs-api-server-architecture.md §2](../../02-concepts/llm-vs-api-server-architecture.md) 约定的 4 角色（用户 / agent 框架 / LLM API 服务器 / LLM 模型）。

---

## 1. 一句话定位

`_prepare_completion_kwargs` ([models.py:502-551](../../../../src/smolagents/models.py#L502)) 是 **Model 基类的核心方法** —— 把 **agent 语义**（memory 翻译来的 messages + 工具列表 + 停止序列）翻译成 **LLM provider 协议**能吃的 dict（OpenAI Chat Completion 风格）。

```
agent 语义                                      LLM provider body
─────────────                                   ──────────────────
list[ChatMessage]               ──┐
list[Tool]                        │              ┌────────────────────────┐
stop_sequences=[...]              ├──→  翻译  ──→│ {                      │
response_format={...}             │              │   "messages": [...],   │
custom_role_conversions={...}     │              │   "stop": [...],       │
self.kwargs={"temp": 0.7,...}     │              │   "tools": [...],      │
**kwargs                          │              │   "temperature": 0.7,  │
                                 ─┘              │   ...                  │
                                                 │ }                      │
                                                 └────────────────────────┘
```

**子类 `generate` 拿到这个 dict，直接喂给 HTTP / SDK / 本地推理引擎**。

---

## 2. 输入侧：4 路汇入 + 1 个数据契约

`_prepare_completion_kwargs` 接收 4 类语义不同的输入：

| 输入路径 | 来源 | 例子 |
|---|---|---|
| **messages** | agent 的 memory 翻译来 | `[ChatMessage(role=SYSTEM, ...), ChatMessage(role=USER, ...)]` |
| **specific params**（命名形参）| agent 单次调用按需传 | `stop_sequences=["<end_code>"]`, `response_format=...`, `tools_to_call_from=[tool1]` |
| **caller `**kwargs`** | agent 单次调用透传 | `generate(..., temperature=0.5)` |
| **`self.kwargs`** | 实例化时存下的默认 | `Model(model_id="...", temperature=0.7, top_p=0.9)` |

> 💡 4 路汇入的差异在 **优先级**（见 §4）和 **谁负责传**（agent vs 用户）。理解这点能解释为什么有 `**kwargs` 还要单独把 `stop_sequences` / `tools_to_call_from` 列成形参 —— 这些是**框架知道协议字段名怎么映射**的"半结构化"参数。

---

## 3. ⭐ 5 步流水线

伪代码角度看 `_prepare_completion_kwargs` 一共干 5 件事：

```python
def _prepare_completion_kwargs(self, messages, stop_sequences=None, ..., **kwargs):
    # 步骤 ①：清洗 messages (调 get_clean_message_list)
    messages_as_dicts = get_clean_message_list(
        messages,
        role_conversions=custom_role_conversions or tool_role_conversions,
        ...
    )
    completion_kwargs = {"messages": messages_as_dicts}

    # 步骤 ②：specific 参数（最低优先级，先放）
    if stop_sequences is not None and self.supports_stop_parameter:
        completion_kwargs["stop"] = stop_sequences
    if response_format is not None:
        completion_kwargs["response_format"] = response_format
    if tools_to_call_from:
        completion_kwargs["tools"] = [get_tool_json_schema(t) for t in tools_to_call_from]  # ⭐ Day 2 段5 闭环
        if tool_choice is not None:
            completion_kwargs["tool_choice"] = tool_choice

    # 步骤 ③：caller 调用时传的 kwargs（中间优先级，覆盖 ②）
    completion_kwargs.update(kwargs)

    # 步骤 ④：self.kwargs（最高优先级，覆盖一切）
    for k, v in self.kwargs.items():
        if v is REMOVE_PARAMETER:
            completion_kwargs.pop(k, None)   # 哨兵：主动删字段
        else:
            completion_kwargs[k] = v

    # 步骤 ⑤：返回（子类拿去发请求）
    return completion_kwargs
```

> 💡 **整个方法没发任何请求** —— 它纯粹是个"翻译器"。这是 Model 基类不发请求设计哲学的具体体现（详见 [role-overview §6](model-class-role-overview.md)）。

---

## 4. ⭐ 三层优先级合并：从低到高

| 优先级 | 来源 | 何时被覆盖 | 典型用途 |
|---|---|---|---|
| 🥉 最低 | specific 参数（步骤 ②）| 被步骤 ③ ④ 覆盖 | agent 框架按协议规则填的字段 |
| 🥈 中间 | caller `**kwargs`（步骤 ③）| 被步骤 ④ 覆盖 | 单次调用临时调参 |
| 🥇 最高 | `self.kwargs`（步骤 ④）| 不被覆盖 | 实例化时存下的默认配置 |

### 为什么 `self.kwargs` 是最高？

逻辑：**用户实例化 Model 时给的默认值，应该"压住" agent 框架自己的临时决定**。

举例：

```python
model = OpenAIModel(model_id="gpt-4", temperature=0.0)   # 用户希望确定性输出
agent = CodeAgent(model=model, ...)
agent.run("...")
# agent 内部某些路径可能调 model.generate(..., temperature=0.7) 想要更有创意
# 但 self.kwargs={"temperature": 0.0} 在步骤 ④ 强制覆盖回 0.0 ✅ 用户意图保住
```

> 💡 **设计取舍**：让用户配置成为"压舱石" —— agent 框架的默认行为永远屈服于用户的显式选择。这是非常合理的库设计。

### `REMOVE_PARAMETER` 哨兵：主动删字段的需求从哪来？

[models.py:441-449](../../../../src/smolagents/models.py#L441) 定义了一个哨兵单例：

```python
class _ParameterRemove:
    def __repr__(self):
        return "REMOVE_PARAMETER"

REMOVE_PARAMETER = _ParameterRemove()
```

**为什么需要"删字段"？**

某些 LLM provider **不接受**某些字段。比如 OpenAI 的 o3-mini **不支持 `stop` 参数**（[supports_stop_parameter](../../../../src/smolagents/models.py#L418) 就是查这个）。如果 agent 默认填了 `stop`，子类需要把它**移除**而不是覆盖成别的值。

```python
model = SomeModel(model_id="o3-mini", stop=REMOVE_PARAMETER)
# self.kwargs = {"stop": REMOVE_PARAMETER}
# 步骤 ④ 时：检测到哨兵 → completion_kwargs.pop("stop")
```

> 💡 **为什么不用 `None`？**`None` 在 JSON body 里有合法语义（"该字段为空"），但"该字段根本不存在" ≠ "该字段为 None"。所以需要一个**唯一的哨兵对象**，用 `is` 严格比较（而不是 `== None`）。这是 Python 单例哨兵的标准设计模式。

---

## 5. 步骤 ① 详解：`get_clean_message_list` 做了 5 件事

[models.py:332-397](../../../../src/smolagents/models.py#L332) 这个辅助函数是 messages 清洗管线，做 5 件事：

| 子步骤 | 做什么 | 为什么 |
|---|---|---|
| (a) `deepcopy` 整个列表 | 防止修改原始 memory | memory.steps 持久化通道不能被请求拼装污染 |
| (b) 验证 role 合法性 | role 必须在 `MessageRole.roles()` 5 个值内 | 防御性编程，避免 typo 沉默通过 |
| (c) **role 转换** | `TOOL_CALL → ASSISTANT`, `TOOL_RESPONSE → USER` | OpenAI 协议没有这两个 role —— smolagents 内部 5 role 在喂 LLM 模型时**降维成 3 个** |
| (d) 处理 image 内容 | base64 编码 / 转 image_url | LLM API 服务器接收的是字符串/URL，不是 PIL Image 对象 |
| (e) ⭐ **合并连续同 role 消息** | `output[-1].role == current.role` 时 append content 而非新增 message | OpenAI 协议**严格要求 role 交替**（user/assistant/user/...），连续两条 assistant 会报错 |

### (e) 合并机制是隐藏的关键

agent 一轮 ReAct 可能产生**多条** assistant 消息（PlanningStep + ActionStep 的 model_output + tool_calls 等）。如果直接发，OpenAI 会拒绝："不允许连续 assistant 消息"。

`get_clean_message_list` 自动把连续同 role 的内容**合并到一条**：

```
原始：
  [SYSTEM, USER, ASSISTANT(plan), ASSISTANT(thought), ASSISTANT(tool_call)]
                               ↑↑↑ 3 条连续 assistant

清洗后：
  [SYSTEM, USER, ASSISTANT(plan + thought + tool_call)]   ← 合并成 1 条
```

> 💡 **Week 1 [chat-message-roles.md](../../02-concepts/chat-message-roles.md) 闭环**：那篇笔记当时讲了"role 是 LLM 行为的方向盘 + chat template 严格要求 role 交替"。Day 3 终于看到具体实现 —— role 转换 + 连续合并都在这一个 `get_clean_message_list` 函数里。

### `flatten_messages_as_text` 的开关

| 模式 | content 格式 | 适合谁 |
|---|---|---|
| `False`（默认）| `[{"type": "text", "text": "..."}]` 多模态结构 | OpenAI / 多模态模型 |
| `True` | 纯字符串 | 老旧的纯文本模型、本地 Transformers chat template |

`Model.__init__` 的 `flatten_messages_as_text` 参数就在控制这个 —— **不同 LLM 后端的 message content 协议不同**。

---

## 6. 步骤 ② 详解：⭐ Day 2 → Day 3 闭环回收

```python
if tools_to_call_from:
    completion_kwargs["tools"] = [get_tool_json_schema(tool) for tool in tools_to_call_from]
```

**这一行就是 Day 2 段 5 埋下的伏笔的真正发生地**。

回顾 Day 2 [tool-schema-rendering-mental-model.md](../day2-tools/tool-schema-rendering-mental-model.md) §4 讲的：HTTP `tools` 字段不是 `Tool.to_tool_calling_prompt` 渲染的，是由 [models.py:288 `get_tool_json_schema`](../../../../src/smolagents/models.py#L288) 渲染的。**Day 3 看到它在哪里被调到** —— 就是这里，line 540。

### 为什么 `get_tool_json_schema` 写在 Tool 类外？

因为 **schema 渲染依赖外部协议**（OpenAI function calling JSON 格式）—— 这是模型调用层的关注点，不是工具自身的关注点。

| 渲染产出 | 渲染位置 | 谁触发 |
|---|---|---|
| CodeAgent prompt 文字 | `Tool.to_code_prompt` ([tools.py:258](../../../../src/smolagents/tools.py#L258)) | system prompt 拼装 |
| ToolCallingAgent prompt 文字 | `Tool.to_tool_calling_prompt` ([tools.py:289](../../../../src/smolagents/tools.py#L289)) | system prompt 拼装 |
| **HTTP tools JSON** | **`get_tool_json_schema`**（独立函数） | **`_prepare_completion_kwargs`**（本方法）|

> 💡 这是 Day 2 → Day 3 **完整闭环**：Day 2 写 mental-model 时已预言"HTTP tools 字段不在 Tool 类上渲染"，Day 3 在 _prepare_completion_kwargs 段第二步看到它**被谁、在哪里、怎么调** —— **理论建在 Day 2，验证落在 Day 3**。

### `tool_choice` 是什么？

[OpenAI 协议字段](https://platform.openai.com/docs/api-reference/chat/create#chat-create-tool_choice)：
- `"required"`（smolagents 默认）：**必须**调一个工具
- `"auto"`：模型自己决定
- `"none"`：禁止调工具
- `{"type": "function", "function": {"name": "..."}}`：强制调指定工具

ToolCallingAgent 默认 `"required"` 是因为**这一步必须出 tool call**（否则 ReAct 循环没法继续）—— 不能让模型偷懒只输出文字。

---

## 7. 一图把全流程串起来

```
agent._step_stream() 内部
   │
   ├── memory_messages = write_memory_to_messages(memory.steps)
   │
   ├── chat_message = model.generate(
   │       messages=memory_messages,
   │       tools_to_call_from=[tool1, tool2],
   │       stop_sequences=["<end_code>"],
   │       custom_role_conversions=None,
   │   )
   │       ↓
   │   InferenceClientModel.generate (子类):
   │       │
   │       ├─→ completion_kwargs = self._prepare_completion_kwargs(...)
   │       │       │
   │       │       ├── ① get_clean_message_list(messages)
   │       │       │     ├─ deepcopy
   │       │       │     ├─ role 转换 (TOOL_CALL→ASSISTANT, TOOL_RESPONSE→USER)
   │       │       │     ├─ image 编码
   │       │       │     ├─ ⭐ 合并连续同 role
   │       │       │     └─ flatten_messages_as_text 开关
   │       │       │
   │       │       ├── ② specific 参数 (低优先级)
   │       │       │     ├─ "stop": stop_sequences
   │       │       │     ├─ "response_format": response_format
   │       │       │     ├─ "tools": [get_tool_json_schema(t) for t in tools_to_call_from]  ⭐ Day 2 闭环
   │       │       │     └─ "tool_choice": tool_choice
   │       │       │
   │       │       ├── ③ caller kwargs (中优先级)
   │       │       │     completion_kwargs.update(kwargs)
   │       │       │
   │       │       ├── ④ self.kwargs (最高优先级)
   │       │       │     ├─ 普通值：覆盖
   │       │       │     └─ REMOVE_PARAMETER 哨兵：删字段
   │       │       │
   │       │       └── ⑤ return completion_kwargs
   │       │
   │       ├─→ response = self.client.chat.completions.create(**completion_kwargs)  ← 真发请求
   │       │
   │       └─→ return ChatMessage.from_dict(response.choices[0].message)
   │
   └── 拿到 ChatMessage 继续 ReAct 循环
```

---

## 8. 为什么这 5 步分工成这样？—— 设计逻辑

| 步骤 | 限制条件 | 必须放在这层 |
|---|---|---|
| ① 清洗 messages | messages 比较"重"（含 image / 长文本），早做能避免后面重复处理 | 协议层固定操作（去重 / 编码） |
| ② specific 参数 | 框架知道字段名映射 | 把"语义" → "协议字段名" 翻译 |
| ③ caller kwargs | 调用时透传，灵活但低优先级 | 单次临时调整 |
| ④ self.kwargs | 实例化时已知，固定有效 | "压舱石"，最后压一次保住用户配置 |
| ⑤ return | 子类自己发请求 | Model 基类不发请求 |

**核心原则**：**"知道得越早，覆盖得越晚"**。
- 步骤 ② 框架最先知道（创建时就有），所以最早写入，但也最容易被后面覆盖。
- 步骤 ④ 用户实例化时给的，最早就存下了，但**留到最后才生效** —— 因为它代表用户最强烈的意图，应该最后压一次盖死所有别的。

> 💡 这个 "**最早知道 → 最先写入 → 最容易被覆盖**" 的反直觉设计，其实是表达"**用户意图最高 vs 框架默认最低**"的优先级哲学。Day 2 [tool-class-role-overview.md](../day2-tools/tool-class-role-overview.md) §5 讲的"每件事尽可能放在能做它的最早时机"是**写入时机**层面；这里 §4 的优先级是**覆盖关系**层面，**两者互不冲突**。

---

## 9. 总结表

| 问题 | 答案 |
|---|---|
| `_prepare_completion_kwargs` 是干嘛的？ | 把 agent 语义翻译成 LLM provider body |
| 输入有几路？ | 4 路：messages + specific 参数 + caller kwargs + self.kwargs |
| 输出是什么？ | 一个 dict，子类直接 `**` 拆给底层调用 |
| 5 步流水线？ | ① 清洗 messages → ② 写 specific 参数 → ③ 合并 caller kwargs → ④ 压 self.kwargs → ⑤ 返回 |
| 三层优先级排序？ | 步骤 ② 最低 < ③ 中间 < ④ 最高（self.kwargs 是压舱石） |
| `REMOVE_PARAMETER` 是什么？ | 哨兵单例，让 self.kwargs 主动**删字段**（针对 o3-mini 不支持 stop 之类） |
| 为什么 `get_clean_message_list` 要合并连续同 role？ | OpenAI 协议要求 role 交替，连续两条 assistant 会报错 |
| HTTP `tools` 字段在哪渲染？ | 步骤 ②：`get_tool_json_schema(tool)` 给每个工具渲染（Day 2 段 5 闭环）|
| Model 基类发请求吗？ | 不发，只拼 body；发请求是子类的事 |

---

## 相关链接

- 必读前置：[model-class-role-overview.md](model-class-role-overview.md)
- 源码：
  - [models.py:441-449](../../../../src/smolagents/models.py#L441) — `REMOVE_PARAMETER` 哨兵
  - [models.py:502-551](../../../../src/smolagents/models.py#L502) — **本笔记主角**
  - [models.py:332-397](../../../../src/smolagents/models.py#L332) — `get_clean_message_list`
  - [models.py:288-329](../../../../src/smolagents/models.py#L288) — `get_tool_json_schema`
- Day 2 闭环：
  - [tool-schema-rendering-mental-model.md](../day2-tools/tool-schema-rendering-mental-model.md) — Day 2 预言"HTTP tools 字段在 Tool 类外渲染"
- Week 1 闭环：
  - [chat-message-roles.md](../../02-concepts/chat-message-roles.md) — role 交替要求 + chat template 原理
- Python 预习：
  - [python-args-kwargs.md](../python-prep/python-args-kwargs.md) — 三层 kwargs 合并依赖的语法基础
- Day 3 后续：
  - InferenceClientModel.generate 真实落地（line 1456-1645，待写）
  - HTTP body trace 实验脚本（待写）

## 遗留问题

- [ ] `agglomerate_stream_deltas` 流式输出聚合（[models.py:220](../../../../src/smolagents/models.py#L220)）—— Day 5 `_step_stream` 时再回来看
- [ ] `parse_tool_calls` 兜底解析的具体场景（哪些 LLM API 服务器不返回结构化 tool_calls？）—— 留到 InferenceClientModel 实现笔记里看
- [ ] `convert_images_to_image_urls` vs `flatten_messages_as_text` 的开关组合（多模态相关，第一遍跳过）
