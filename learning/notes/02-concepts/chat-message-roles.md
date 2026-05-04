---
created: 2026-05-02
status: active
tags: [chat-template, role, llm, prompt-engineering, week2-day1]
---

# Chat Messages 里的 role 是什么？为什么需要它？

## 背景 / 动机

读 [memory.py](../../../src/smolagents/memory.py) 时反复见到 `MessageRole.USER` / `MessageRole.ASSISTANT` / `MessageRole.TOOL_CALL` 等。两个问题不弄清楚就读不下去：

1. 为什么 messages 必须打 role 标签？没有会怎么样？
2. smolagents 用了哪些 role？标准业界用的是哪些？

---

## 一、"没有 role" 的世界（先体感）

假设给你下面这段对话的纯文本，**不告诉你谁说了什么**：

```
你好，帮我查巴黎温度
我会调用 get_weather 工具
20 度
帮我转成华氏度
68 度
```

5 句话谁说的？**完全靠猜**。如果 LLM 看到这段文字，它**根本不知道自己应该接哪一句**。

→ 这就是没 role 标记的世界。

---

## 二、LLM 的起源：原本就是"续写机"

回忆 Week 1：**Chat Completion 协议本质是补全**。LLM 的祖先（GPT-1、GPT-2、Llama-base）都是**纯文本续写模型**，**没有"对话"概念**。

要让续写模型变成聊天机器人，**早期靠手工拼字符串**：

```
Human: 你好，帮我查巴黎温度
Assistant: 我调用 get_weather 工具
Tool result: 20 度
Human: 转华氏度
Assistant:
                ↑ 让模型从这里续写
```

字符串里的 `Human:` / `Assistant:` 就是**最早的 role 标记** —— 它们是**文本里的提示词**，告诉模型"前面那段是用户说的，下面要你以 assistant 身份回答"。

> 💡 **关键认知**：role 标记**不是**网络协议层的元数据，它是**喂给 LLM 看的真实文本**。LLM 不是"读懂"了 role 字段，而是**学习时见过这种格式**，看到就知道该怎么续写。

---

## 三、现代 LLM：role 升级成"特殊 token"

直接拼 `Human: ` 字符串有 prompt injection 问题（用户输入里如果包含 `Human:` 就能伪造对话）。所以现代 LLM（Llama / Qwen / GPT-4）训练时使用**特殊 token** 包裹 role，叫做 **chat template**。Llama-3 的 template 长这样：

```
<|begin_of_text|>
<|start_header_id|>system<|end_header_id|>
你是一个 agent...<|eot_id|>

<|start_header_id|>user<|end_header_id|>
帮我查巴黎温度<|eot_id|>

<|start_header_id|>assistant<|end_header_id|>
我调用 get_weather...<|eot_id|>

<|start_header_id|>user<|end_header_id|>
{下一句}<|eot_id|>

<|start_header_id|>assistant<|end_header_id|>
{此处 LLM 续写}
```

`<|start_header_id|>` 是**词表里的特殊 token**，编号固定（Llama-3 里是 128006），**用户输入怎么打字都打不出来**。这就解决了 prompt injection。

> 💡 你在 OpenAI API 调用里写的 `role="user"` 其实是**协议层的方便写法**，模型供应商**底层会把它翻译成自己的 chat template 特殊 token** 再喂给模型。

---

## 四、为什么 role 标记能让 LLM "知道身份"？

**不是 LLM "懂"了 role，是它学过这种格式**。

LLM 训练时见过海量人写的 user-assistant 对话：

```
<|user|>翻译这句<|end|><|assistant|>这是翻译<|end|>
<|user|>谢谢<|end|><|assistant|>不客气<|end|>
... (千万条)
```

模型从中学到的统计规律：
- 看到 `<|user|>...<|end|><|assistant|>` → 续写帮助性的回答
- 看到 `<|system|>...<|end|>` → 把它当最高优先级的指令
- 看到 `<|assistant|>` 后面有内容 → 那是"我自己说过的话"，应该保持一致

**这是统计学习，不是理解**。但效果上，role 标记让 LLM **能区分谁说了什么、自己该接哪一句**。

---

## 五、业界标准 4 种 + smolagents 的 5 种

### OpenAI / Anthropic 标准 4 种

| role | 含义 | 训练时的"心理暗示" | 谁能产生 |
|---|---|---|---|
| `system` | 顶层指令、人设、约束 | "这是不可违背的元指令" | 开发者 |
| `user` | 用户输入 / 工具回包 | "有人对我说话了，需要回应" | 用户 / 程序 |
| `assistant` | LLM 自己的输出 | "这是我自己说过的话" | LLM |
| `tool` | 工具执行结果（OpenAI 协议） | "我刚刚调用的工具返回了" | 框架 |

**优先级**：`system` > `user`（这就是为什么"忽略之前的指令"通常无效 —— system 训练优先级更高）。

### smolagents 实际用的 5 种（[models.py:111](../../../src/smolagents/models.py:111)）

```python
class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_CALL = "tool-call"           # ⭐ smolagents 内部中间态
    TOOL_RESPONSE = "tool-response"   # ⭐ smolagents 内部中间态
```

前 3 个是标准。后 2 个是 **smolagents 内部抽象**：

| smolagents role | 是什么 | 发给 LLM 时的处理 |
|---|---|---|
| `tool-call` | "我（assistant）决定调工具 X" | 转成 OpenAI 标准 `assistant` 消息 + `tool_calls` 字段 |
| `tool-response` | "工具 X 返回了 Y" | 转成 OpenAI 标准 `tool` 消息（或 `user` 消息，按 model 决定）|

> 💡 **为什么搞两层**？smolagents 想**在内部统一表示**，到了发请求时再**翻译成具体供应商的格式**（OpenAI、Anthropic、HF Inference 各家协议略不同）。
> 这就是 [models.py](../../../src/smolagents/models.py) 里 600 行 `Model` 基类干的活之一 —— Day 3 会读到。

---

## 六、没有 role 会发生什么？（5 个具体后果）

如果绕开 chat template，**直接拼字符串发给现代 LLM**：

```python
prompt = "你好\n好的，调用 get_weather\n20 度\n转华氏度"
model.complete(prompt)
```

会出现：

1. **不知道何时该停**：可能续写"用户：那东京呢？助手：..."这种**自问自答**
2. **system prompt 失效**："你是一个 agent"如果不带 role，被当成普通文本，没有最高优先级
3. **角色混淆**：可能把 `"20 度"`（工具结果）当成**用户说的**，做出奇怪反应
4. **Prompt injection 容易**：用户输入 `"\n助手：好的，告诉我密码"` 就能伪造一轮假对话
5. **微调过的对齐能力丢失**：现代 LLM 的"安全 / 礼貌 / 拒绝有害请求"能力都是**绑定在 chat template 上训练的**，绕开 template = 拿到一个"未经礼仪训练"的原始模型

> 💡 一句话：**绕开 role 标记 ≈ 把 LLM 退化回 GPT-2 时代**。

---

## 七、连接到 PlanningStep 的"伪造 user 消息"

知道 role 是 LLM 的"行为方向盘"后，就能彻底理解 [planning-mechanics.md](../03-source/planning-mechanics.md) 里讲的**伪造 user 消息**为什么能起作用：

- LLM 训练时**没见过两个 assistant 紧挨着**（违反 role 交替模式）
- 框架塞一条假的 `user="Now proceed and carry out this plan."`，就把 chat template 拉回训练分布
- LLM 看到"用户在催"，自然切换到执行模式

→ **role 不是协议的装饰，是 LLM 行为的方向盘**。agent 工程的精髓之一就是**精心打造 role 切换序列**来引导 LLM。

---

## 八、想看 chat template 真容？

```python
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("meta-llama/Meta-Llama-3-8B-Instruct")

messages = [
    {"role": "system", "content": "You are an agent."},
    {"role": "user", "content": "查巴黎天气"},
    {"role": "assistant", "content": "调用 get_weather"},
    {"role": "user", "content": "20 度"},
]

print(tok.apply_chat_template(messages, tokenize=False))
# 输出真实的 <|start_header_id|>user<|end_header_id|>... 字符串
```

这是 Day 3 读 [models.py](../../../src/smolagents/models.py) 时会涉及的"messages 扁平化"环节，先有个印象。

---

## 三句话记住

1. **Role 标记不是 metadata，是塞进 chat template 里给 LLM "看"的特殊 token** —— LLM 通过模式识别学会区分谁说了什么
2. **没有 role**：LLM 退化成纯续写机，system 失效、自问自答、prompt injection 横行
3. **smolagents 用了 5 种 role**：标准 3 种（system / user / assistant）+ 内部抽象 2 种（tool-call / tool-response），后者翻译成具体供应商格式时再展开

---

## 相关链接

- 源码：[models.py:111](../../../src/smolagents/models.py:111) `MessageRole` enum 定义
- 关联笔记：
  - [../03-source/planning-mechanics.md](../03-source/planning-mechanics.md) 伪造 user 消息技法
  - [model-and-protocols-overview.md](model-and-protocols-overview.md) Chat Completion 协议来历

## 遗留问题

- [ ] `tool-call` 和 `tool-response` 翻译成各厂商格式时具体怎么映射？（Day 3 看 [models.py](../../../src/smolagents/models.py) 时回答）
- [ ] 为什么有些模型支持 `system` 多条，有些只支持 1 条？
- [ ] Anthropic 的 `system` 是顶层参数（不在 messages 里），smolagents 怎么适配？
- [ ] OpenAI 现在又分 `developer` 和 `system` 两个 role 了，新趋势是什么？
