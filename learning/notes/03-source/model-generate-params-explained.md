---
created: 2026-05-05
status: active
tags: [smolagents, models, parameters, source-reading, reference]
---

# `_prepare_completion_kwargs` 7 个参数详解

⚠️ **必读前置**：[model-generate-mental-model.md](model-generate-mental-model.md)（5 步流水线 + 三层优先级机制）

> 本笔记是 [model-generate-mental-model.md](model-generate-mental-model.md) 的**参数级补充**。前者讲"流程结构"，本篇讲"每个参数到底控制 LLM 的什么行为"。

> 💡 **术语统一**：本笔记严格使用 [llm-vs-api-server-architecture.md §2](../02-concepts/llm-vs-api-server-architecture.md) 约定的 4 角色（用户 / agent 框架 / LLM API 服务器 / LLM 模型）。

---

## 1. 完整签名

```python
def _prepare_completion_kwargs(
    self,
    messages: list[ChatMessage | dict],            # ① 输入数据
    stop_sequences: list[str] | None = None,       # ② 何时停
    response_format: dict[str, str] | None = None, # ③ 输出格式约束
    tools_to_call_from: list[Tool] | None = None,  # ④ 可调用的工具
    custom_role_conversions: dict | None = None,   # ⑤ role 映射覆写
    convert_images_to_image_urls: bool = False,    # ⑥ 图片编码方式
    tool_choice: str | dict | None = "required",   # ⑦ 工具选择策略
    **kwargs,                                       # ⑧ 兜底透传
) -> dict[str, Any]:
```

源码位置：[models.py:502-512](../../../src/smolagents/models.py#L502)

---

## 2. ⭐ 按"控制 LLM 哪一面"分组

| 维度 | 参数 |
|---|---|
| **看什么** | ① messages + ⑤ custom_role_conversions + ⑥ convert_images_to_image_urls |
| **何时停** | ② stop_sequences |
| **输出什么形状** | ③ response_format |
| **能调什么工具 / 必须调吗** | ④ tools_to_call_from + ⑦ tool_choice |
| **其他兜底** | ⑧ **kwargs |

---

## 3. 逐参数详解

### ① `messages` —— 必传，对话历史

agent memory 翻译来的 `ChatMessage` 列表（也支持 dict 混用）。

将被 [`get_clean_message_list`](../../../src/smolagents/models.py#L332) 在步骤 ① 清洗：deepcopy / role 验证 / role 转换 / image 编码 / **合并连续同 role** / flatten。

详见 [model-generate-mental-model.md §5](model-generate-mental-model.md)、[chat-message-roles.md](../02-concepts/chat-message-roles.md)。

---

### ② `stop_sequences` —— 何时停

LLM 生成的"刹车字符串"列表。OpenAI 协议字段叫 `stop`。

smolagents 典型：
- CodeAgent: `["<end_code>"]`
- PlanningStep: `["<end_plan>"]`
- ToolCallingAgent: 通常不传（依赖结构化 `tool_calls` 自然停）

⚠️ Reasoning 模型（o3/o4/gpt-5/grok）协议禁用此字段，`supports_stop_parameter` 检查兜底。

详见 [model-stop-sequences.md](model-stop-sequences.md)。

---

### ③ `response_format` —— "强制 LLM 输出特定 JSON 结构"

**语义**：告诉 LLM "你的回答必须严格符合这个 schema"。OpenAI 协议字段，叫 **structured output / JSON mode**。

**典型值**：

```python
# 简单：要求输出合法 JSON
response_format = {"type": "json_object"}

# 严格：定义具体 schema
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "weather_report",
        "schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "temp_celsius": {"type": "number"},
            },
            "required": ["city", "temp_celsius"],
        }
    }
}
```

**怎么生效？** LLM 生成时**会被 OpenAI 解码器约束**，**不可能输出不符合 schema 的字符**（不是事后校验，是生成时强制）。

**smolagents 用它吗？**
- CodeAgent / ToolCallingAgent **默认不用**（前者输出代码，后者输出 tool_calls，都不需要约束 content 形状）
- 用户**自定义场景可以传**（如把 LLM 当固定报表生成器）

> 💡 `response_format` vs `tools` 是**两种不同的"结构化输出"机制**：
> - `tools` 让 LLM 选一个函数调（agent 主用）
> - `response_format` 让 LLM 直接吐结构化数据（聊天总结主用）

---

### ④ `tools_to_call_from` —— 可调用的工具列表

`list[Tool]`。每个 Tool 在步骤 ② 被 `get_tool_json_schema` 渲染成 OpenAI function calling JSON：

```python
completion_kwargs["tools"] = [get_tool_json_schema(tool) for tool in tools_to_call_from]
```

**这就是 Day 2 段 5 闭环的真正发生地** —— [tool-schema-rendering-mental-model.md](tool-schema-rendering-mental-model.md) 预言"HTTP tools 字段不在 Tool 类上渲染"，Day 3 验证就在这。

**ToolCallingAgent 必传**（否则 LLM 不知道有什么工具可用）。
**CodeAgent 不传**（工具通过 prompt 文本描述，不走 OpenAI tools 字段，靠 Python 代码块调用）。

---

### ⑤ `custom_role_conversions` —— "覆写默认的 role 降维表"

**默认行为**（[`tool_role_conversions`，models.py:282](../../../src/smolagents/models.py#L282)）：

```python
{
    MessageRole.TOOL_CALL:     MessageRole.ASSISTANT,
    MessageRole.TOOL_RESPONSE: MessageRole.USER,
}
```

—— smolagents 内部 5 个 role 喂 LLM 时降成 OpenAI 协议认的 3 个（[role-overview §7](model-class-role-overview.md)）。

**`custom_role_conversions` 让你换映射表**。比如某些非主流 LLM provider 喜欢把 tool response 当 system 消息：

```python
custom_role_conversions = {
    "tool-call": "assistant",
    "tool-response": "system",   # ← 不要 user，要 system
}
```

源码里：

```python
role_conversions=custom_role_conversions or tool_role_conversions
```

**传了就用你的，没传就用默认**（短路 or 模式）。

> 💡 这是给"接入小众 LLM provider"的开发者准备的逃生口。99% 用户用默认就行。

---

### ⑥ `convert_images_to_image_urls` —— "图片编码方式开关"

LLM API 服务器接收图片有 **2 种编码方式**：

| 取值 | content 长啥样 | 谁用 |
|---|---|---|
| `False`（默认）| `{"type": "image", "image": "<base64 字符串>"}` | 直接塞 base64 到 message |
| `True` | `{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}` | 包成 OpenAI 标准 image_url |

**为什么有这个开关？** 不同 LLM provider 协议不同：
- OpenAI / 大多数主流 → `image_url` 格式
- HuggingFace 一些老接口 / 自定义后端 → 直接吃 base64 字符串

**子类的 `generate` 里按自己 provider 习惯传** `True` / `False`，对 agent 框架的其他部分透明。

> 💡 第一遍读跳过即可。**只有做多模态 agent 才会真正关心**。

---

### ⑦ `tool_choice` —— "LLM 必须调工具吗？调哪个？"

OpenAI 协议字段。控制 LLM 在 `tools` 列表里**怎么选**。4 种取值：

| 值 | 含义 | smolagents 用法 |
|---|---|---|
| `"required"` | **必须**调一个 tool（不能纯文本回答）| ⭐ smolagents 默认 |
| `"auto"` | 模型自己决定调不调 | OpenAI 默认 |
| `"none"` | 禁止调 tool | 需要纯文本回答时 |
| `{"type": "function", "function": {"name": "X"}}` | 强制调指定 tool X | 强制路由 |

**为什么 smolagents 默认 `"required"`？**

ToolCallingAgent 的设计就是"每一步都必须出 tool call" —— 不能让 LLM 偷懒只输出"我觉得应该……"的文字。这一步必须**真有动作**，否则 ReAct 循环就卡住了（没有 tool call → 没有 observation → 模型下一步基于什么决策？）。

> 💡 `tool_choice="required"` 是 smolagents 设计哲学的体现：**强迫 LLM 落地为可执行动作，不允许悬浮在思考层**。

---

### ⑧ `**kwargs` —— 兜底透传

收集"没在形参列表点名的关键字参数"。在步骤 ③ 被 `completion_kwargs.update(kwargs)` 合并到 body（中间优先级，被 self.kwargs 覆盖）。

**典型用途**：caller 单次调用临时调参。

```python
model.generate(messages, temperature=0.3)   # ← temperature 进 **kwargs
```

详见 [python-args-kwargs.md](python-args-kwargs.md)、[model-generate-mental-model.md §4](model-generate-mental-model.md)。

---

## 4. 一图归类

```
                  _prepare_completion_kwargs 的 7 个参数
                              │
       ┌──────────────────────┼──────────────────────┐
       │                      │                      │
   "看什么"                "何时停"               "输出什么形状"
   ─────────              ─────────              ──────────────
   ① messages              ② stop_sequences      ③ response_format
   ⑤ custom_role_conversions                     ④ tools_to_call_from
   ⑥ convert_images_to_image_urls                ⑦ tool_choice

                          + ⑧ **kwargs (兜底透传)
```

---

## 5. "谁传它" 对照表

| 参数 | 必传 vs 可选 | 谁通常传 |
|---|---|---|
| ① messages | 必传 | agent 内部（write_memory_to_messages 翻译） |
| ② stop_sequences | 可选 | agent 内部按 ReAct 步骤需要 |
| ③ response_format | 可选 | 用户自定义场景 |
| ④ tools_to_call_from | 可选（ToolCallingAgent 必传）| agent 内部 |
| ⑤ custom_role_conversions | 可选 | 接入小众 provider 的开发者 |
| ⑥ convert_images_to_image_urls | 可选 | 子类按 provider 习惯固定 |
| ⑦ tool_choice | 默认 `"required"` | agent 内部 |
| ⑧ **kwargs | 可选 | caller 临时调参 |

---

## 6. 速查表（OpenAI 协议字段映射）

| 参数 | OpenAI 协议字段名 | smolagents 默认 | 哪步处理 |
|---|---|---|---|
| `messages` | `messages` | 必传 | 步骤 ① 清洗 |
| `stop_sequences` | `stop` | None | 步骤 ② |
| `response_format` | `response_format` | None | 步骤 ② |
| `tools_to_call_from` | `tools` | None | 步骤 ② 调 `get_tool_json_schema` |
| `custom_role_conversions` | （内部用，不发出去）| None → fallback `tool_role_conversions` | 步骤 ① 传给 `get_clean_message_list` |
| `convert_images_to_image_urls` | （影响 content 结构）| False | 步骤 ① 传给 `get_clean_message_list` |
| `tool_choice` | `tool_choice` | `"required"` | 步骤 ② |
| `**kwargs` | 各种（temperature/top_p/...）| 空 dict | 步骤 ③ update |

---

## 7. 总结表

| 问题 | 答案 |
|---|---|
| 7 个参数最关键的分组维度？ | "控制 LLM 哪一面"：看什么 / 何时停 / 输出形状 / 调工具 |
| `messages` 之外哪 3 个影响"LLM 看什么"？ | ⑤ custom_role_conversions（role 降维）+ ⑥ convert_images_to_image_urls（图片编码）|
| `response_format` vs `tools` 区别？ | 前者约束 content 输出 JSON 结构；后者让 LLM 选函数调（agent 主用 tools）|
| `tool_choice="required"` 为什么是默认？ | 强迫 LLM 出 tool call，防止它停在思考层让 ReAct 循环卡住 |
| `custom_role_conversions` 一般谁会传？ | 接入小众 LLM provider 时；99% 默认即可 |
| `convert_images_to_image_urls` 一般谁会传？ | 子类按自己 provider 习惯固定，普通用户不用关心 |
| **kwargs 进哪一步？什么优先级？ | 步骤 ③，中间优先级（被 self.kwargs 覆盖）|

---

## 相关链接

- 必读前置：
  - [model-generate-mental-model.md](model-generate-mental-model.md) — 5 步流水线 + 三层优先级（讲流程）
- 子参数深入：
  - [model-stop-sequences.md](model-stop-sequences.md) — `stop_sequences` 详解 + 双保险
  - [tool-schema-rendering-mental-model.md](tool-schema-rendering-mental-model.md) — `tools_to_call_from` 渲染机制（Day 2）
  - [chat-message-roles.md](../02-concepts/chat-message-roles.md) — `messages` / `custom_role_conversions` 的 role 系统
  - [python-args-kwargs.md](python-args-kwargs.md) — `**kwargs` 语法
- 源码：
  - [models.py:502-551](../../../src/smolagents/models.py#L502) — `_prepare_completion_kwargs` 完整实现
  - [models.py:282](../../../src/smolagents/models.py#L282) — `tool_role_conversions` 默认表
  - [models.py:288](../../../src/smolagents/models.py#L288) — `get_tool_json_schema`
  - [models.py:332](../../../src/smolagents/models.py#L332) — `get_clean_message_list`

## 遗留问题

- [ ] OpenAI structured output（`response_format=json_schema`）的实际严格性如何？—— 留作 Week 3-4 实战时跑实验
- [ ] CodeAgent 真的不传 `tools_to_call_from` 吗？—— 待 Day 4-5 读 `agents.py` 时验证
- [ ] `tool_choice` 为函数对象（`{"type": "function", ...}`）时的实际行为 —— 留作多 agent 路由实战时探索
