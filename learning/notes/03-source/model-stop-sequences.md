---
created: 2026-05-05
status: active
tags: [smolagents, models, stop-sequences, prompt-protocol, source-reading]
---

# `stop_sequences`：LLM 生成的"刹车字符串" + agent prompt 协议的硬截断

⚠️ **必读前置**：[model-generate-mental-model.md](model-generate-mental-model.md)（`_prepare_completion_kwargs` 步骤 ② 把 stop_sequences 写进 HTTP body）

---

## 1. 一句话角色

`stop_sequences` 是传给 **LLM API 服务器**的**字符串列表**。LLM 模型**逐 token 生成**输出时，**一旦输出里出现列表中任意一个字符串，LLM API 服务器就立刻停止生成**（即使还没说完、即使还没到 `max_tokens` 上限）。

> 💡 术语统一：本笔记从 §3 起严格使用 [llm-vs-api-server-architecture.md §2](../02-concepts/llm-vs-api-server-architecture.md) 约定的 4 角色（用户 / agent 框架 / LLM API 服务器 / LLM 模型）。

OpenAI Chat Completion 协议里这个字段叫 `stop`：

```python
client.chat.completions.create(
    model="...",
    messages=[...],
    stop=["<end_code>", "<end_plan>"],   # ← 任一出现就停
)
```

> 💡 **smolagents 内部用 `stop_sequences`，发出去前改名 `stop`** —— 协议字段名 vs 内部语义命名的区分。改名发生在 [`_prepare_completion_kwargs` 步骤 ②](../../../src/smolagents/models.py#L534)：`completion_kwargs["stop"] = stop_sequences`。

---

## 2. 普通对话用不上 vs Agent 必须有

| 场景 | 需要 stop_sequences 吗？ | 为什么 |
|---|---|---|
| 普通 ChatGPT 对话 | 不需要 | LLM 模型自己生成 EOS（end-of-sequence）token 就停 |
| Agent / Function Calling | **必须** | agent 框架用 prompt 协议约定 LLM 模型输出格式 —— 出现某特定字符串 = "我说完了，下一步该 agent 框架接管" |

---

## 3. ⭐ stop 是谁给谁的？—— 厘清三方关系

⚠️ **必读**：[llm-vs-api-server-architecture.md](../02-concepts/llm-vs-api-server-architecture.md)（LLM 模型 vs LLM API 服务器是两层）

很多人会困惑："stop 是用户传给大模型用的吗？"答：**不是**。三方关系：

```
┌──────────┐         ┌──────────────┐         ┌──────────────┐         ┌────────┐
│   用户    │  task→  │ smolagents   │  HTTP→  │ LLM API 服务器 │  token→ │ LLM 模型 │
│  (你)    │  ←答案  │  agent 框架   │ ← JSON  │              │  ←概率  │        │
└──────────┘         └──────────────┘         └──────────────┘         └────────┘
                          ↑
                     stop 在这里产生
                     发给 LLM API 服务器
                     ⚠️ LLM 模型完全不知道 stop 字段存在
```

### stop 的生命周期

1. **agent 框架启动**：CodeAgent 内部约定 `stop_sequences = ["<end_code>"]` —— 用户没参与
2. **每次调 LLM API 服务器**：agent 框架把 stop 写进 HTTP body 的 `stop` 字段
3. **HTTP 发出**：`_prepare_completion_kwargs` 步骤 ② 写入字段 → HTTP 发给 LLM API 服务器
4. **LLM API 服务器干活**：边监控 LLM 模型每 token 输出边检查后缀，命中 stop 就掐断 LLM 模型
5. **LLM 模型本身**：只在某一刻被 LLM API 服务器**强制中断**，不知道为什么停 —— **它从来没看到过 stop 字段**

### 用户在不同场景下的角色

| 场景 | 用户角色 | 用户碰 stop 吗？ |
|---|---|---|
| 直接用 ChatGPT 网页 | 终端用户 | ❌ 完全看不到这个字段 |
| 用 OpenAI SDK 自己调 API | 开发者 | ✅ 可能直接传 stop |
| 用 smolagents 跑 agent | agent 用户 | ❌ 99% 不接触，agent 框架内部决定 |
| 给 smolagents 写自定义 Model 子类 | 高级开发者 | ✅ 需要理解 stop 怎么翻译给底层 LLM API 服务器 |

### 为什么"prompt 给 LLM 看 / stop 给服务器看"是双保险

```
HTTP body:
{
    "messages": [
        {"role": "system",
         "content": "End your code with <end_code>"},   ← 经 tokenize 进入模型输入
        ...
    ],
    "stop": ["<end_code>"]                              ← 留在服务器手里，不进模型
}
```

**两条信息送到不同主体**（详见 [llm-vs-api-server-architecture.md §6](../02-concepts/llm-vs-api-server-architecture.md)）：

- **LLM 模型**（神经网络）看到 system content，"自觉"输出 `<end_code>` —— **主动**写出停止标记
- **LLM API 服务器**（HTTP 服务）拿着 stop 列表监控模型输出 —— **被动**检测到就强制截断

**双保险的"双"指 LLM 模型 + LLM API 服务器两个不同主体协同**。既不是"用户保险 + 框架保险"，也不是"客户端保险 + 服务端保险"。

### stop 在哪一层"生效"？

**stop 必须送到 LLM API 服务器**，由它在生成循环内截断。**不是 agent 框架自己用的**。

```
agent 框架（smolagents）           LLM API 服务器              LLM 模型
─────────────────────             ─────────────────           ──────────
1. 拼 HTTP body：
   {"messages": [...],
    "stop": ["<end_code>"]}
2. 发 HTTP 请求 ──────────────→  3. 收到请求
                                  4. 解析 JSON，把 stop 拿出来
                                  5. tokenize messages →  ─→ 6. 生成 token
                                                          ←─    输出 token
                                  7. 检查 stop 命中？
                                     - 没命中 → 把 token   ─→ 8. 继续生成
                                       拼回去喂模型        ←─
                                     - 命中 → break
                                  9. 包响应回 HTTP
10. agent 收到 ←──────────────
    response
```

**为什么不是"agent 收到完整响应后自己截断"？**
1. ❌ 浪费 token（按 token 计费，已生成的部分要付钱）
2. ❌ 浪费时间（要等完整生成才能拿到结果）
3. ❌ 占用 rate limit 配额

**Fallback 例外**：当 LLM API 服务器不支持 stop 字段时（reasoning 模型协议禁用），smolagents 会**降级**用应用层后处理截断 —— 详见 [inference-client-model-impl.md §4.5](inference-client-model-impl.md)。

---

## 4. ⭐⭐ EOS / stop / max_tokens：三种停止机制互补

⚠️ **必读前置**：[llm-vs-api-server-architecture.md §2 术语约定](../02-concepts/llm-vs-api-server-architecture.md)（4 角色：用户 / agent 框架 / LLM API 服务器 / LLM 模型）

### 4.1 LLM 本质上停不下来

LLM 是**逐 token 预测下一个 token 概率**的纯数学过程，理论上**只要不告诉它停就一直生成**。物理上有 context window / GPU 显存上限，但在那之前模型不会"自觉"停 —— 它没有"我说完了"的内在概念。

### 4.2 三种"让 LLM 停下来"的机制

| 机制 | 谁产生信号 | 谁消费信号 | 何时停 |
|---|---|---|---|
| **EOS token** | LLM 模型生成的（训练时学到）| LLM API 服务器看到模型输出 EOS → 终止生成循环 | 模型自觉觉得"语义完成了" |
| **stop_sequences** | agent 框架写进 HTTP body | LLM API 服务器对照模型每 token 输出 → 命中就终止 | agent 框架规定的中断点 |
| **max_tokens** | agent 框架写进 HTTP body / 服务器默认上限 | LLM API 服务器自己计数 → 到上限就终止 | 物理上限保险 |

> 💡 **三个机制的"消费者"都是 LLM API 服务器**。区别在于**谁产生信号**。

### 4.3 ChatGPT 生成代码为什么不胡编？答：靠 EOS

ChatGPT 训练时喂了几百万段对话数据：

```
[用户消息]
[助手消息（含代码块 + 解释）]
<|im_end|>   ← 训练数据里的对话结束标记
```

模型学到："看到用户问编程问题 → 输出代码 + 解释 → 输出 `<|im_end|>`"。

```
用户：写个 hello world
ChatGPT 生成：
   "好的，这是一个简单的 hello world 示例：
   ```python
   print('Hello, World!')
   ```
   这段代码会输出 ..." <|im_end|>
                        ↑
                   LLM API 服务器看到这个 token → 停止
```

**ChatGPT 不需要 stop**，因为它是"普通对话"语义 —— 模型说完一段完整答案后**自觉**输出 EOS。

### 4.4 ⭐⭐ 既然 EOS 这么强，为什么还需要 stop？

**因为 EOS 表达"完整结束"，stop 表达"中间暂停" —— 它们是两种不同语义**。

| 标记 | 比喻 | 语义 | 触发位置 |
|---|---|---|---|
| EOS | 句号 `.` | "整段话说完了" | 模型觉得自然结束的位置 |
| stop | 逗号 / 分号 `,` `;` | "暂停一下，等会儿继续" | agent 框架定义的边界 |

#### 关键场景：Agent ReAct 循环里的"中途暂停"

```
LLM 在 agent ReAct 循环里写完代码块：

Thought: 我要查天气
Code:
```py
result = get_weather("Beijing")
```<end_code>   ← agent 框架希望停在这里
```

**LLM 模型自己怎么想？**
- "我写完代码块了，但**还没回答用户的问题**啊（因为还没看到执行结果）"
- "对话还没结束，我应该继续往下写 Observation 然后给最终答案"
- → **不会输出 EOS**，会继续生成（自我幻觉 Observation）

**这就是为什么靠 EOS 等不来停止信号**：LLM 模型按对话语义认为"还没说完"，但 agent 框架认为"该让我接管了"。

EOS 和 stop **解决完全不同的问题**：

| 场景 | 谁需要停 | 哪个机制管用 |
|---|---|---|
| 普通对话："1+1 等于多少？" | 模型说完答案 | EOS（模型自觉）|
| ChatGPT 生成代码："写个 hello world" | 模型说完代码 + 解释 | EOS |
| Agent："查北京天气" | 模型写完**单步代码块**（完整答案要等多轮 ReAct）| **stop**（EOS 不触发）|

### 4.5 三种机制是互补关系（不是替代）

| 缺失机制 | 后果 |
|---|---|
| 缺 EOS | 普通对话里模型不知道何时收尾，可能一直生成 garbage 直到撞 max_tokens |
| 缺 stop | **Agent 退化成 LLM 模型自言自语**，工具系统失效（最严重的功能性后果）|
| 缺 max_tokens | 万一 EOS 失效会跑死 GPU 显存 / 永久卡住 |

**实际系统三种全都有**，按场景叠加使用：

```
       LLM 模型自觉 ────── agent 框架主动 ─────── LLM API 服务器兜底
           EOS                  stop                    max_tokens
            │                    │                        │
       "我说完了"           "你这里给我停"           "无论如何都不能再生成"
            │                    │                        │
            ↓                    ↓                        ↓
   普通对话靠它            Agent 协议必备             防失控保险
   ChatGPT 靠它            高级流式控制               所有场景都开
```

---

## 5. ⭐ smolagents 里的真实用法

### 5.1 CodeAgent

LLM 被 prompt 模板要求输出形如：

```
Thought: 我要查天气
Code:
```py
result = get_weather("Beijing")
print(result)
```<end_code>
```

agent 框架传 `stop_sequences=["<end_code>"]` —— LLM 模型一打出 `<end_code>` 立刻被 LLM API 服务器掐断。

**为什么需要？** 防止 LLM 模型**继续幻想 `Observation: ...` 自己编造工具执行结果**。agent 框架要的是 "LLM 模型写完代码就停 → agent 框架去真正执行 Python → 把真实结果作为下一轮的 observation 喂回"。**绝对不能让 LLM 模型自己脑补 observation**。

### 5.2 PlanningStep

[planning_demo.py](../scripts/planning_demo.py) 实证过：当 agent 让 LLM **重新规划**时，传 `stop_sequences=["<end_plan>"]`。LLM 输出"4 段更新计划"后打出 `<end_plan>` 立刻停 —— 防止它继续往下"顺便把第一步执行了"。

> 💡 **Day 1 [planning-mechanics.md](planning-mechanics.md)** 早就提到："prompt 工程是双向控制：YAML 模板规定结构 + stop_sequences 强制截断 LLM 跑题"。本笔记是这条结论的源码侧验证。

### 5.3 ToolCallingAgent

通常**不传** stop_sequences —— 因为它依赖 OpenAI 协议的结构化 `tool_calls` 字段，LLM 模型输出 tool call JSON 后 LLM API 服务器自己会停。**结构化协议本身就是停止信号**。

---

## 6. ⭐ 双保险机制：模板指令 + stop_sequences

很多人会问："prompt 里不是已经写了 `End your code with <end_code>` 吗？为什么还要 stop_sequences？"

**因为 LLM 不可靠**。

| 防线 | 谁负责检查 | 失败模式 |
|---|---|---|
| 第 1 层：prompt 指令 | LLM 模型自觉遵守 | LLM 模型**忘记**写 `<end_code>` / 写完了**继续往下编造** Observation |
| 第 2 层：`stop_sequences` | LLM API 服务器逐 token 硬检查 | （几乎不会失败）|

**双保险**：
- prompt 教 LLM 模型**倾向于**输出停止标记 → 让 LLM 模型在自然位置写出来
- LLM API 服务器一旦看到立刻**强制截断** → 即使 LLM 模型想越界也截死

> 💡 **设计哲学**：永远不要单独信任 LLM 的"意愿"。**给它提示 + 给它硬约束** = "苦口婆心 + 锁死大门"。这条原则在 smolagents 多处出现（如 Tool 类的 `__init_subclass__` wrap 校验 + 用户文档教导双保险）。

---

## 7. ⭐⭐ 关键澄清：stop 是"被动检测"，prompt 才是"主动控制"

⚠️ **这一节解决的是初学者最容易卡住的疑问**："LLM API 服务器既然能 stop，为什么不直接强制 LLM 模型在某个位置输出 stop 字符串呢？"

**答**：LLM API 服务器对 stop 是**被动检测**，不是**主动控制**。它**不能强迫 LLM 模型输出**任何特定 token —— 它只能**等模型自己输出，然后抓到了就截断**。

### 7.1 重新画清"谁负责什么"

```
┌────────────────────────────────────────────────────────────┐
│ agent 框架（smolagents）同时做 2 件事：                       │
│                                                            │
│ ① prompt 里教 LLM 模型："写完代码后输出 <end_code>"           │
│    ↓ ACTIVE 主动机制（影响模型 token 分布，让它"倾向" 输出）  │
│                                                            │
│ ② HTTP body 里写 stop=["<end_code>"]                        │
│    ↓ PASSIVE 被动机制（等模型输出后由 LLM API 服务器抓）      │
└────────────────────────────────────────────────────────────┘
                ↓
┌────────────────────────────────────────────────────────────┐
│ LLM API 服务器：拿着 stop 列表 + 启动 LLM 模型生成循环         │
└────────────────────────────────────────────────────────────┘
                ↓
┌────────────────────────────────────────────────────────────┐
│ LLM 模型：根据 prompt 指令 + 训练习惯，决定输出什么 token       │
│                                                            │
│ 如果 prompt 教得好 → 模型在代码后输出 <end_code> token        │
│ 如果 prompt 没教 → 模型不会输出这个奇怪字符串 → stop 永不触发  │
└────────────────────────────────────────────────────────────┘
                ↓
┌────────────────────────────────────────────────────────────┐
│ LLM API 服务器：边收 token 边检查输出后缀                      │
│   - 模型输出了 <end_code> → 字符串匹配命中 → break            │
│   - 模型没输出 → 一直等到 max_tokens 兜底                     │
└────────────────────────────────────────────────────────────┘
```

**核心**：LLM API 服务器是个"监工"，不是"指挥官"。

### 7.2 反证：单独传 stop 不教 prompt 会怎样？

```python
# 假想场景：只传 stop，不在 prompt 教
messages = [{"role": "user", "content": "查北京天气"}]   # 没教
stop = ["<end_code>"]

response = openai.chat.completions.create(messages=messages, stop=stop)
```

LLM 模型按训练习惯生成：

```
"我没有实时天气数据，建议查询天气网站..." <|im_end|>
                                          ↑
                                      自己 EOS 停了
                                      根本没输出 "<end_code>"
```

**结果**：模型**永远不会**输出 `<end_code>` 这个奇怪字符串组合（不是英语自然词汇）→ stop 检测**永不触发** → stop 等于白传。

### 7.3 双保险的"双"真正含义

| 层 | 机制 | 性质 | 没有它会怎样 |
|---|---|---|---|
| Prompt 教 | 让 LLM 模型**想**输出 stop 字符串 | **主动**（影响 token 分布）| 模型根本不会输出这个怪字符串 |
| Server 截 | 检测到就立刻断 | **被动**（监听不干预生成）| 模型输出了之后会**继续**编造 Observation |

**两层强依赖**：
- 没有第 1 层 → 第 2 层永远不触发
- 没有第 2 层 → 第 1 层即使生效（模型写了 stop），模型也会继续编造下文

它们不是独立两道防线，而是**主动 + 被动协同**。

### 7.4 LLM API 服务器有"主动控制" 模型的能力吗？

**有**，叫 **constrained decoding（约束解码）/ grammar-constrained sampling**：

| 控制方式 | 用途 | 怎么实现 | stop 用吗？ |
|---|---|---|---|
| 被动检测 | 检测到字符串就停 | 字符串后缀匹配 | ✅ stop 用这个 |
| 主动约束 | 强制输出符合 schema 的 JSON | 服务器在每个采样步骤**屏蔽不合法 token** | ❌ stop 不用 |
| 主动约束 | 强制走 tool_calls 路径 | 同上，约束首个 token 必须是 tool_call 触发标记 | ❌ stop 不用 |

**为什么 stop 不用主动约束？** 因为 stop 的语义是"模型自然结束的位置"，强制输出会破坏自然性 —— 比如模型还在写代码中间就被强制吐出 `<end_code>` → 输出垃圾。

**stop 设计哲学**：让模型按自己节奏写，写到 prompt 教它输出 stop 的位置自然停 —— 这才合理。

> 💡 [model-generate-params-explained.md](model-generate-params-explained.md) 讲的 `response_format` / `tool_choice="required"` 才是主动约束。它们和 stop 解决不同问题。

### 7.5 token 边界细节

LLM 模型输出的不是字符，是 token。`<end_code>` 这串字符串可能被 tokenizer 切成多个 token：

```
"<end_code>" → tokenizer → ["<end", "_code", ">"]    （示例）
```

LLM API 服务器**逐 token 增量检查**累积字符串后缀：

```
模型输出：[token1="<end"]   → 累积："<end"          → 不匹配
模型输出：[token2="_code"]  → 累积："<end_code"     → 不匹配
模型输出：[token3=">"]      → 累积："<end_code>"    → ✅ 匹配 → break
```

**所以 stop 字符串可以横跨任意 token 边界，但应选有语义的标记**（模型才可能自然输出）。

### 7.6 总结：被动检测 vs 主动控制

| 问题 | 答案 |
|---|---|
| LLM API 服务器能强制 LLM 模型输出 stop 字符串吗？ | ❌ 不能 |
| 模型怎么知道要输出 stop 字符串？ | ⭐ 靠 **prompt 指令教育** |
| 单独传 stop 不写 prompt 会怎样？ | 模型不输出 → 检测永不触发 → 白传 |
| 单独写 prompt 不传 stop 会怎样？ | 模型输出 stop 后会**继续编造 Observation** |
| 双保险真正含义？ | prompt（主动让模型输出）+ server 检测（被动抓住）= 主动 + 被动协同 |
| 服务器有主动约束能力吗？ | 有：`response_format` / `tool_choice` 用 constrained decoding。但 stop **不用** |

---

## 8. 在 smolagents 源码里走的完整路径

```
agents.py 的 prompt 模板 (toolcalling_agent.yaml / code_agent.yaml)
   │ 模板里写 "End your code with <end_code>"
   │ 同时 agent 框架代码里定义 self.stop_sequences = ["<end_code>"]
   ↓
agent._step_stream() 内调:
   model.generate(messages, stop_sequences=["<end_code>"], ...)
   ↓
Model._prepare_completion_kwargs (line 502):
   步骤 ②:
     if stop_sequences is not None and self.supports_stop_parameter:
         completion_kwargs["stop"] = stop_sequences   ← ⚠️ 改名 stop_sequences → stop
   ↓
HTTP body: {"stop": ["<end_code>"], ...}
   ↓
LLM API 服务器：每生成一个 token 检查输出后缀，命中就 break
   ↓
返回的 text **不含** "<end_code>"（LLM API 服务器主动剪掉触发停止的那部分）
```

> 💡 **LLM API 服务器主动剪掉停止字符串** —— 这是 OpenAI 协议规定。否则 agent 框架还要自己 strip 一次，更脏。

---

## 9. ⚠️ 协议兼容性坑：`supports_stop_parameter`

[models.py:418-438](../../../src/smolagents/models.py#L418) 有个函数 `supports_stop_parameter(model_id)` —— **不是所有模型都支持 `stop` 参数**。

```python
def supports_stop_parameter(model_id: str) -> bool:
    """
    Not supported with reasoning models openai/o3, openai/o4-mini, and
    the openai/gpt-5 series (and their versioned variants).
    """
    model_name = model_id.split("/")[-1]
    if model_name == "o3-mini":
        return True
    # o3*/o4*/grok-*/gpt-5* 都不支持
    openai_model_pattern = r"(o3(?:$|[-.].*)|o4(?:$|[-.].*)|gpt-5.*)"
    grok_model_pattern = r"([A-Za-z][A-Za-z0-9_-]*\.)?grok-[A-Za-z0-9][A-Za-z0-9_.-]*"
    pattern = rf"^({openai_model_pattern}|{grok_model_pattern})$"
    return not re.match(pattern, model_name)
```

`_prepare_completion_kwargs` 步骤 ② 写 `stop` 字段前先查这个：

```python
if stop_sequences is not None and self.supports_stop_parameter:
    completion_kwargs["stop"] = stop_sequences
```

不支持就**静默跳过**写入（不会报错，但也少了硬截断的兜底）。

### 9.1 ⭐ 为什么有些 provider 不支持 stop？根本原因 3 类

#### 原因 ① Reasoning 模型保护"思考过程"完整性（最主要）

**o3 / o4-mini / gpt-5 / grok 不支持 stop**，因为它们是 **reasoning 模型**：

```
普通模型生成过程：
  user 提问 → assistant 回答 → done
                    ↑
              用户可以 stop 截断到这里

reasoning 模型生成过程：
  user 提问 → [internal thinking 过程：5000 tokens 思考链] → final answer
                              ↑
                  如果允许用户 stop 截断到这里 → 推理链被打断 → 模型崩坏
```

**OpenAI 协议层面禁了**：因为允许 `stop` 截断 reasoning 模型的思考过程，会让模型在思考一半时被强制吐出 token —— **输出质量极度退化**，产生不完整的推理链。OpenAI 觉得"防止用户搬石头砸自己的脚"比"功能完整性"重要，所以协议层就禁。

> 💡 **设计取舍**：对普通用户友好（避免输出垃圾），但对 agent 框架不友好（少一道防线）。这是 reasoning 模型 + agent 协议**根本性不兼容**的来源。

#### 原因 ② tokenizer / 解码层不支持任意字符串匹配

LLM 是**逐 token 生成**，但用户指定的 stop 是**任意字符串**。实现 stop 需要：每生成一个新 token，**反向检查最近输出的字符序列后缀**是否包含任一停止字符串。

某些 provider 的推理引擎（特别是自研、定制化的）**没实现这个检查机制** —— 比如纯本地推理引擎只暴露 EOS token 截断，不支持任意字符串匹配。这种 provider 也会"不支持" stop。

#### 原因 ③ 协议字段名不一致（不是真不支持，是叫法不同）

不是所有 LLM API 都用 OpenAI 协议：

| Provider | stop 字段叫什么 |
|---|---|
| OpenAI | `stop` |
| Anthropic | `stop_sequences`（巧合和 smolagents 内部命名一致）|
| Cohere | `stop_sequences` |
| 某些自研 | 完全没这字段 |

**所以"不支持"也可能是"用了别的名字"**，需要在适配层翻译。smolagents 各子类的 `generate` 实现就在做这种翻译（[OpenAIModel](../../../src/smolagents/models.py#L1646) / [LiteLLMModel](../../../src/smolagents/models.py#L1205) 等各自处理）。

### 9.2 smolagents 的 3 道兜底

| 防线 | 实现 | 行为 | 适用场景 |
|---|---|---|---|
| ① 静默跳过写入 | [`_prepare_completion_kwargs`](../../../src/smolagents/models.py#L534) 步骤 ②：`if self.supports_stop_parameter` | 不支持就**不传** stop 字段 | agent 框架默认行为 |
| ② Python 后处理截断 | [`InferenceClientModel.generate`](../../../src/smolagents/models.py#L1578) 第 ⑤ 件：`remove_content_after_stop_sequences` | LLM 模型生成完后，agent 框架**用 Python 字符串截断** stop 后的内容兜底 | reasoning 模型 |
| ③ 用户主动删字段 | `Model(stop=REMOVE_PARAMETER)` （详见 [python-sentinel-pattern.md](python-sentinel-pattern.md)） | 用户显式让 body 里**根本没有** stop 字段 | 已知 provider 不接受 stop 字段（连 null 也不行） |

> 💡 **三道兜底是同一问题的层级化解决**：
> - 防线 ① **预防**：知道不支持就别传
> - 防线 ② **治疗**：传不进去，事后清理
> - 防线 ③ **用户精确控制**：连"传 null"都不行的极端情况

**对 smolagents 的影响**：用 reasoning 模型跑 agent 时主要靠防线 ②（Python 后处理）+ prompt 指令兜底，**不太理想但能跑**。

> 💡 **Week 1 [codeagent-vs-toolcallingagent.md](../02-concepts/codeagent-vs-toolcallingagent.md) 的踩坑**记录过："Thinking 模型 + ToolCallingAgent → 400"。stop 不支持只是 thinking 模型 + agent 协议不友好的**冰山一角**：还有 `tools` / `tool_choice` / `temperature` 等字段都可能被 reasoning 模型协议禁掉。

### 9.3 ⭐ agent 框架怎么知道哪些 LLM API 服务器支持 stop？

**没有"协议查询"机制**。HTTP 没有标准方式问"你支持什么字段"。所以 smolagents 只能靠 **3 种知识来源**：

#### 来源 ① 硬编码先验知识 ⭐

[`supports_stop_parameter(model_id)`](../../../src/smolagents/models.py#L418) **根据 `model_id` 字符串模式匹配**判断。本质是 smolagents 维护者**手工查 OpenAI 文档**得出的知识，**烧死在代码里**。

📝 **意味着什么？**
- OpenAI 出新 reasoning 模型 → smolagents 维护者要更新这个函数
- 用户用了**没在白名单**的 reasoning 模型 → smolagents 不知道 → 还是会传 `stop` → LLM API 服务器返回 400 → agent 报错

#### 来源 ② 用户主动声明（哨兵）

如果 smolagents 默认知识不准（如新出的模型），用户可以**用 `REMOVE_PARAMETER` 哨兵主动告诉框架**："我这个模型别传 stop"：

```python
from smolagents.models import REMOVE_PARAMETER

model = InferenceClientModel(
    model_id="some-new-reasoning-model",
    stop=REMOVE_PARAMETER,   # ← 用户告诉 agent 框架："这个模型别传 stop 字段"
)
```

详见 [python-sentinel-pattern.md](python-sentinel-pattern.md)。

#### 来源 ③ 失败重试（smolagents **不做**）

理论上可以：发请求 → 收到 400 错误 → 检测错误信息含 "unsupported stop" → 去掉 stop 字段重发。

**但 smolagents 不做这个**，因为：
- 浪费一次失败请求的 token / 时间
- 错误信息格式不标准化
- 不如靠先验知识 + 用户声明

#### 协议碎片化挑战

| 维度 | 例子 | 谁定义 |
|---|---|---|
| **字段名** | OpenAI 用 `stop`，Anthropic 用 `stop_sequences`，Cohere 用 `stop_sequences`...... | LLM API 服务器协议规定 |
| **字段值** | `["<end_code>"]` 或随便什么字符串 | agent 框架自由选 |
| **是否被支持** | 普通模型 ✅；reasoning 模型 ❌ | LLM API 服务器协议规定 |

**字段名必须严格一致**（OpenAI 服务器只认 `stop`，传 `stop_sequences` 会 400）。**这就是为什么 smolagents 各子类的 `generate` 内部要"翻译"** —— 把内部 `stop_sequences` 改名成各 provider 协议要求的字段名。

```python
# 内部统一用 stop_sequences
agent → model.generate(stop_sequences=["<end_code>"])

# 各子类发 HTTP 时改名
OpenAIModel:    body["stop"] = stop_sequences            # OpenAI 协议
AnthropicModel: body["stop_sequences"] = stop_sequences  # Anthropic 协议
```

> 💡 **协议碎片化是 smolagents 写多个子类的根本原因** —— 没有统一发现机制，每家 provider 协议字段名 + 支持范围 + 限制都不一样，必须靠库维护者**逐家适配**。

---

## 10. 与 Day 1 / Day 2 / Day 3 的网状关联

| 关联点 | 在哪里出现 | 链接 |
|---|---|---|
| PlanningStep 用 `<end_plan>` 兜底 | Day 1 实证实验 | [planning-mechanics.md](planning-mechanics.md) |
| prompt 模板严格规定结构 | Day 1 段 4 洞察 | [planning-mechanics.md](planning-mechanics.md) |
| Thinking 模型 + agent 协议不兼容 | Week 1 实战踩坑 | [codeagent-vs-toolcallingagent.md](../02-concepts/codeagent-vs-toolcallingagent.md) |
| `_prepare_completion_kwargs` 步骤 ② 把 stop_sequences 写进 body | Day 3 段 2 | [model-generate-mental-model.md](model-generate-mental-model.md) |
| `self.supports_stop_parameter` 走 `self.kwargs` 时也能被覆盖 | Day 3 段 2 三层优先级 | [model-generate-mental-model.md](model-generate-mental-model.md) §4 |

---

## 11. 总结表

| 问题 | 答案 |
|---|---|
| `stop_sequences` 是什么？ | LLM 生成时遇到就强制停止的字符串列表 |
| OpenAI 协议字段名？ | `stop`（smolagents 内部叫 `stop_sequences`，发请求前改名）|
| stop 是被动检测还是主动控制？ | **被动检测** —— LLM API 服务器只能等 LLM 模型自己输出，不能强制 |
| 模型怎么知道要输出 stop 字符串？ | 靠 **prompt 教** —— 主动机制；服务器只是被动抓 |
| 单独传 stop 不教 prompt？ | 模型不输出 → 检测永不触发 → 白传 |
| agent 框架怎么知道哪些服务器不支持 stop？ | ① 硬编码白名单（`supports_stop_parameter` 正则匹配 model_id）② 用户用 `REMOVE_PARAMETER` 主动声明 ③ smolagents 不做 400 重试 |
| 字段名 vs 字段值哪个要对齐？ | 字段名（`stop` vs `stop_sequences`）必须严格匹配协议；字段值任意 |
| smolagents 怎么处理字段名差异？ | 各子类的 `generate` 内部"翻译" —— 内部统一 `stop_sequences`，发出去时按协议改名 |
| stop 谁产生 / 谁消费？ | **agent 框架**产生（写进 HTTP body）→ **LLM API 服务器**消费（生成循环内截断）—— LLM 模型完全不知道它存在 |
| stop 在哪一层生效？ | **LLM API 服务器**（生成中即时截断）；fallback 模式才在 agent 框架做应用层后处理 |
| 普通对话用得上吗？ | 用不上，LLM 模型自己输出 EOS 就停（如 ChatGPT）|
| 既然 EOS 这么强，为什么 agent 还要 stop？ | EOS = 句号（语义完成）；stop = 逗号（中间暂停）—— agent 协议要求停的位置 EOS **永远不会触发** |
| Agent 缺 stop 会怎样？ | LLM 模型自我幻觉整个 ReAct 循环（编造 Observation / 编造下一步），工具系统失效 |
| 三种停止机制（EOS / stop / max_tokens）关系？ | **互补**：EOS（LLM 模型自觉）+ stop（agent 框架自定义）+ max_tokens（LLM API 服务器兜底）一起用 |
| smolagents 里的典型值？ | CodeAgent: `["<end_code>"]`；PlanningStep: `["<end_plan>"]`；ToolCallingAgent: 通常不用 |
| 为什么不只靠 prompt 指令？ | LLM 模型不可靠会忘 / 会越界，**双保险**：prompt 教 LLM 模型 + LLM API 服务器硬截断 |
| 返回的 text 包含停止字符串吗？ | 不包含，LLM API 服务器主动剪掉 |
| 哪些模型不支持？ | o3/o4-mini/gpt-5*/grok* 系列（reasoning 模型）|
| 为什么不支持？3 类原因 | ① 保护 reasoning 模型思考链不被截断（最主要）② 推理引擎不支持任意字符串匹配 ③ 协议字段叫别的名字（Anthropic/Cohere `stop_sequences`）|
| smolagents 三道兜底？ | ① 静默跳过写入（防线 ①）② Python 后处理截断 `remove_content_after_stop_sequences`（防线 ②）③ `REMOVE_PARAMETER` 用户主动删字段（防线 ③）|
| 在源码哪里写入 body？ | [`_prepare_completion_kwargs` 步骤 ②，line 534](../../../src/smolagents/models.py#L534) |

---

## 相关链接

- 必读前置：[model-generate-mental-model.md](model-generate-mental-model.md)
- 源码：
  - [models.py:418-438](../../../src/smolagents/models.py#L418) — `supports_stop_parameter` 兼容性检查
  - [models.py:534](../../../src/smolagents/models.py#L534) — `stop` 字段写入 body
- 关联 Day 1：
  - [planning-mechanics.md](planning-mechanics.md) — `<end_plan>` 在 PlanningStep 的实证
- 关联 Week 1：
  - [codeagent-vs-toolcallingagent.md](../02-concepts/codeagent-vs-toolcallingagent.md) — Thinking 模型踩坑
  - [chat-message-roles.md](../02-concepts/chat-message-roles.md) — chat template 与协议字段的关系
- 关联 Day 3：
  - [python-sentinel-pattern.md](python-sentinel-pattern.md) — `REMOVE_PARAMETER` 哨兵机制（防线 ③ 的实现基础）
  - [inference-client-model-impl.md](inference-client-model-impl.md) §4.5 — `remove_content_after_stop_sequences` Python 后处理（防线 ②）

## 遗留问题

- [ ] 看 toolcalling_agent.yaml 和 code_agent.yaml 里 `<end_code>` / `<end_plan>` 的具体声明位置（待 Day 4-5 读 agents.py 时回查）
- [ ] o3 不支持 stop 时，agent 实际运行表现如何（LLM 真的会幻想 Observation 吗）—— 留作 Week 3-4 实战时跑实验
