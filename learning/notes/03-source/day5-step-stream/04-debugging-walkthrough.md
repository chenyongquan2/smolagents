---
created: 2026-05-14
status: active
tags: [smolagents, agents, step-stream, debugging, walkthrough, day5]
---

# Day 5 单步调试操作手册：把 01 / 02 演出版变成肌肉记忆

> ⚠️ **必读前置**：
> - [00 mental model 骨架](00-step-stream-role-overview.md) — 知道 5 步是什么
> - [01 ToolCallingAgent 演出版](01-toolcalling-walkthrough.md) — 知道每幕变量值剧本
> - [02 CodeAgent 演出版](02-codeagent-walkthrough.md) — 知道沙箱接口
> - [03 差异对比](03-impl-diff-deep-dive.md) — 知道两子类 9 个差异维度
> - Day 4 ⑥ [agent-run-debugging-walkthrough](../day4-agents/06-run-debugging-walkthrough.md) — 单步调试操作肌肉记忆已练过

本笔记是 **Day 5 验收 ③ 的兑现**：「拿 compare_agents.py 单步走，每个分歧点都知道源码位置」。

不是"教你怎么调试"（Day 4 ⑥ 已练）—— 是**给你一份精准的"断点 + Watch + 预期值"清单**，按清单跑就能把 01 / 02 演出版的每幕**亲眼对照源码**。

---

## 1. 一句话定调

跑完本笔记的调试流程，你应能：

- 默写 ToolCallingAgent 4 步串行 ReAct 循环的每幕变量值（呼应 01 演出版 10 幕）
- 默写 CodeAgent 1 步沙箱执行的每幕变量值（呼应 02 演出版 8 幕）
- 闭眼说出 **5 步骨架的源码行号定位**（[agents.py:1276 / 1639](../../../../src/smolagents/agents.py)）
- 把 [questions.md "Day 5 待实证"](../../questions.md) 里的 3 个推测点**实测验证**（如果你愿意单点跑）

---

## 2. 准备阶段（5 分钟）

### 2.1 确认环境

| 检查项 | 怎么验证 |
|---|---|
| 代理可达 | `curl -x $HTTPS_PROXY https://huggingface.co` 应返回 `200` |
| `.env` 配置 | `HTTPS_PROXY` / `HF_TOKEN` 都有值（详见 [proxy-issue.md](../../01-setup/proxy-issue.md)）|
| launch.json `justMyCode: false` | 否则 step into 进不了 smolagents 源码（Day 4 ⑥ 已配过）|

如果代理还有问题：见 [proxy-issue.md §4 "代理软件可能只暴露 SOCKS5"](../../01-setup/proxy-issue.md) 兜底（含 ToLine 实测经验）。

### 2.2 调试目标脚本

[compare_agents.py](../../../scripts/compare_agents.py) —— 顺序跑两遍：

1. **ToolCallingAgent** 跑"查 3 城市最高温转华氏"任务 → ~4 步
2. **CodeAgent** 跑同任务 → ~1 步

模型默认 `Qwen/Qwen2.5-72B-Instruct`（不支持 parallel function calling，Day 5 03 §10 已讲）。

---

## 3. 第一组断点：4 个核心（验证 mental model）

这 4 个断点能覆盖 5 步骨架 + 3 个红色推测点（[questions.md](../../questions.md)）。**只打这 4 个就够第一次跑通**。

### 3.1 ToolCallingAgent 必打 4 个

| # | 文件:行 | 应命中哪一幕（01 演出版）| 验证什么 |
|---|---|---|---|
| **B** | [agents.py:1320](../../../../src/smolagents/agents.py#L1320) | 第 2 幕末 | 🔴 红色点 1：`chat_message.tool_calls[0].function.arguments` 是 **str** 还是 **dict** |
| **D** | [agents.py:1379](../../../../src/smolagents/agents.py#L1379) | 第 4a 幕 | 🔴 红色点 3：阶段 A `yield ToolCall` 那一刻；**应命中 4 次** |
| **F** | [agents.py:1423](../../../../src/smolagents/agents.py#L1423) | 第 4c 幕 | 🔴 红色点 3：阶段 B `yield ToolOutput`；**应命中 4 次** |
| **G** | [agents.py:1436](../../../../src/smolagents/agents.py#L1436) | 第 4d 幕 | 🔴 红色点 2：写 `memory_step.tool_calls` 那一刻；**命中时该字段应为 `None`** |

### 3.2 CodeAgent 必打 4 个

| # | 文件:行 | 应命中哪一幕（02 演出版）| 验证什么 |
|---|---|---|---|
| **B'** | [agents.py:1699](../../../../src/smolagents/agents.py#L1699) | 第 2 幕末 | `output_text` 是含 `<code>...</code>` 的自由文本（**不是 JSON**），`chat_message.tool_calls` **为 None** |
| **D'** | [agents.py:1711](../../../../src/smolagents/agents.py#L1711) | 第 3 幕末 | 写 `memory_step.code_action` 后；`code_action` 是抠出来的 Python 代码字符串 |
| **E'** | [agents.py:1721](../../../../src/smolagents/agents.py#L1721) | 第 3 幕末 yield ToolCall | `tool_call.name == "python_interpreter"` ⭐ 合成的 |
| **F'** | [agents.py:1727](../../../../src/smolagents/agents.py#L1727) | 第 4 幕进沙箱前 | `code_action` 准备塞给 `python_executor` |

---

## 4. Watch 表达式（5 个）

通用一组（两边都能用）：

```python
chat_message.tool_calls
chat_message.tool_calls[0].function.arguments        # ⭐ ToolCallingAgent 关键
type(chat_message.tool_calls[0].function.arguments)  # ⭐ 看类型（str vs dict）
memory_step.tool_calls
memory_step.observations
```

CodeAgent 额外一组：

```python
code_action                                          # ⭐ 抠出来的代码字符串
memory_step.code_action
code_output                                          # 第 4 幕沙箱执行后
```

---

## 5. ToolCallingAgent 跑通操作流程

### 5.1 启动

1. 打开 [compare_agents.py](../../../scripts/compare_agents.py)
2. **暂时注释掉 CodeAgent 部分**（注释行 88-99）—— 只看 ToolCalling，CodeAgent 留作下一节
3. F5 启动调试

> ⚠️ 调完别忘了 `git checkout learning/scripts/compare_agents.py` 恢复，commit 时不要把临时注释带进去。

### 5.2 应亲眼验证的 5 件事（按命中顺序）

#### Step 1（第一次 LLM 调用）

**断点 B 命中**：
- ✅ Watch `chat_message.tool_calls` 应非空，长度 = 1（Qwen2.5 不 parallel）
- 🔴 看 `type(chat_message.tool_calls[0].function.arguments)`：是 `str` 还是 `dict`？记下来对照笔记
- ✅ `chat_message.tool_calls[0].function.name` 应是 `"get_temperature"`

**继续到断点 D 命中（第 1 次）**：
- ✅ `parallel_calls` 累积 1 个 ToolCall
- ✅ Console 已 yield 出 ToolCall 事件

**断点 F 命中（第 1 次）**：
- ✅ `tool_output.output` ≈ `25.0`（Beijing 温度，假数据）
- ✅ `tool_output.is_final_answer == False`

**断点 G 命中（第 1 次）**：
- 🔴 命中时 `memory_step.tool_calls` 是 `None` 还是已有值？记下来

**断点 H（动作 5）跳过即可**（Day 5 mental model § 5 已讲）

#### Step 2-4（重复 Step 1 模式）

LLM 第 2 / 3 / 4 次调用，断点 B/D/F/G 各重复命中：

- Step 2: Beijing 已查 → LLM 决定查 Tokyo
- Step 3: Beijing + Tokyo 已查 → LLM 决定查 Singapore
- Step 4: 3 城市都查完 → LLM 心算 max + 转华氏 → 调 `final_answer(86.0)`

**Step 4 的断点 F 关键**：
- ✅ `tool_output.is_final_answer == True` ⭐
- ✅ `tool_output.output == 86.0`

#### 跑完后总命中次数

| 断点 | 应命中次数 | 实际命中 |
|---|---|---|
| B | 4 | __ |
| D | 4 | __ |
| F | 4 | __ |
| G | 4 | __ |

如果某个不是 4，说明哪步 LLM 行为意外（比如 parallel / 提前 final）—— 反过来证实"模型决定调用模式"（Day 5 03 §10 已讲）。

---

## 6. CodeAgent 跑通操作流程

### 6.1 启动

1. 恢复 ToolCallingAgent 部分（如果上节注释了 → 取消注释 / `git checkout`）
2. **可选**：注释掉 ToolCallingAgent 部分让脚本只跑 CodeAgent —— 节省时间
3. 把第 5 节的 4 个断点禁用 / 删除
4. 设第 3.2 节的 4 个 CodeAgent 断点（B' / D' / E' / F'）
5. F5

### 6.2 应亲眼验证的 4 件事（1 步搞定）

**断点 B' 命中**：
- ✅ `chat_message.tool_calls` 应为 `None` 或 `[]` ⭐⭐ **跟 ToolCallingAgent 完全相反**
- ✅ `output_text` 是字符串，包含 `<code>...</code>` 包裹
- ✅ `output_text` 内 Python 代码大概长这样：
  ```
  thoughts: ...
  <code>
  temps = [get_temperature("Beijing"), get_temperature("Tokyo"), get_temperature("Singapore")]
  final_answer(max(temps) * 1.8 + 32)
  </code>
  ```

**断点 D' 命中**：
- ✅ `code_action` 是抠出来的纯代码（**不含 `<code>` 标签**，parse_code_blobs 已把外壳去掉）
- ✅ `memory_step.code_action` 应已被赋值

**断点 E' 命中**：
- ✅ `tool_call.name == "python_interpreter"` ⭐ 合成的，不是 LLM 给的
- ✅ `tool_call.arguments` 是上面的代码字符串

**断点 F' 命中**（进沙箱前）：
- ✅ `code_action` 准备塞给 `python_executor`
- F10 单步过去 → 看 `code_output.is_final_answer == True` 且 `code_output.output == 86.0`

### 6.3 跟 ToolCallingAgent 的对照

跑完 CodeAgent 后回头看：

| 维度 | ToolCallingAgent 实测 | CodeAgent 实测 |
|---|---|---|
| memory.steps 数 | 5（1 Task + 4 Action）| **2**（1 Task + 1 Action）|
| LLM 调用次数 | 4 | **1** |
| 断点命中总数 | 4 × 4 = 16 | 4 × 1 = 4 |
| 老板对讲机响 | 3 + 3 + 3 + 3 = 12 次（4 步 × 3 事件）| 2 次（1 ToolCall + 1 ActionOutput）|

---

## 7. 进阶：完整 8 个断点（可选）

如果你想看完整 10 幕 / 8 幕剧本的每一幕，加上这 4 个辅助断点：

### ToolCallingAgent 完整 8 个

| # | 文件:行 | 第 N 幕 |
|---|---|---|
| A | [agents.py:1284](../../../../src/smolagents/agents.py#L1284) | 第 1 幕（动作 ① 入口）|
| B | [agents.py:1320](../../../../src/smolagents/agents.py#L1320) | 第 2 幕末 ⭐ |
| C | [agents.py:1336](../../../../src/smolagents/agents.py#L1336) | 第 4 幕入口 |
| D | [agents.py:1379](../../../../src/smolagents/agents.py#L1379) | 第 4a 幕 ⭐ |
| E | [agents.py:1390](../../../../src/smolagents/agents.py#L1390) | 第 4b 幕（execute_tool_call 入口）|
| F | [agents.py:1423](../../../../src/smolagents/agents.py#L1423) | 第 4c 幕 ⭐ |
| G | [agents.py:1436](../../../../src/smolagents/agents.py#L1436) | 第 4d 幕 ⭐ |
| H | [agents.py:1356](../../../../src/smolagents/agents.py#L1356) | 第 5 幕 |

### CodeAgent 完整 8 个

| # | 文件:行 | 第 N 幕 |
|---|---|---|
| A' | [agents.py:1647](../../../../src/smolagents/agents.py#L1647) | 第 1 幕（动作 ① 入口）|
| B' | [agents.py:1699](../../../../src/smolagents/agents.py#L1699) | 第 2 幕末 ⭐ |
| C' | [agents.py:1709](../../../../src/smolagents/agents.py#L1709) | 第 3 幕（parse_code_blobs 后）|
| D' | [agents.py:1711](../../../../src/smolagents/agents.py#L1711) | 第 3 幕末 ⭐ |
| E' | [agents.py:1721](../../../../src/smolagents/agents.py#L1721) | 第 3 幕末 yield ⭐ |
| F' | [agents.py:1727](../../../../src/smolagents/agents.py#L1727) | 第 4 幕进沙箱前 ⭐ |
| G' | [agents.py:1755](../../../../src/smolagents/agents.py#L1755) | 第 4 幕末（写 observations）|
| H' | [agents.py:1765](../../../../src/smolagents/agents.py#L1765) | 第 5 幕 yield ActionOutput |

---

## 8. 常见坑速查

| 现象 | 原因 | 解决 |
|---|---|---|
| 断点不命中 | `justMyCode: true` | 改 launch.json → `false` |
| `WinError 10061 目标计算机积极拒绝` | 代理软件没启 / 端口对不上 | [proxy-issue.md §"扩展认知 4"](../../01-setup/proxy-issue.md) |
| F5 直接跑完没停 | 没设断点 / 断点设错文件 | 确认断点是 [src/smolagents/agents.py](../../../../src/smolagents/agents.py) 不是别的 |
| Step Into 跳到 generator 内部直接跑完 | 用 F11 才能进 generator | 用 F11 不是 F10 |
| `chat_message.tool_calls is None` ToolCalling 也这样 | LLM 没返回 tool_calls（thinking 模型 / 协议不支持）| 换非 thinking 模型；[questions.md "已解" 第 2 条](../../questions.md)|
| LLM 报 400 | 同上 | 同上 |

---

## 9. 快捷键速查（VS Code）

| 快捷键 | 动作 |
|---|---|
| F5 | 启动 / 继续 |
| F10 | Step Over（不进函数）|
| F11 | Step Into（进 generator / 子函数）|
| Shift+F11 | Step Out（退出当前函数）|
| Ctrl+Shift+F5 | 重启调试 session |
| Shift+F5 | 停止调试 |
| F9 | 在当前行加/取消断点 |

---

## 10. ⚠️ 实证状态说明（诚实标记）

本笔记的"预期值"全部来自**笔记 01 / 02 / 03 的源码推演**，**不是单点实测**。

| 实证状态 | 说明 |
|---|---|
| ✅ 已知通过 | 整体跑通（compare_agents.py 能跑出结果），代理 / 模型 / 环境都验证可用 |
| 🔴 待单点实证 | [questions.md "Day 5 待实证"](../../questions.md) 3 条：① arguments 类型 ② memory_step.tool_calls 写回时机 ③ state 储物柜闭环 |
| 📋 调试操作清单 | 本笔记（你需要时按清单跑）|

**未来如果发现实际值跟笔记不符**：当场修笔记 + 在 questions.md 标已实证。Day 4 self-check Q11 那种实证修正就是这么来的。

---

## 11. Day 5 闭合宣告

跑完本笔记 + 看完 00-03 笔记 = **Day 5 验收三项全部 ✓**：

| 验收 | 内容 | 兑现笔记 |
|---|---|---|
| ① | 默写 `_step_stream` 的 5 步伪代码 | [00 mental model](00-step-stream-role-overview.md) §3 |
| ② | 对比 CodeAgent vs ToolCallingAgent 在解析输出和执行动作两环节的代码差异 | [03 差异对比](03-impl-diff-deep-dive.md) §4 + §5 |
| ③ | 拿 compare_agents.py 单步走，每个分歧点都知道源码位置 | **本笔记**（断点对照表 + 行号速查）|

**Day 5 完成度 = 100%**（除了 questions.md 3 个红色推测点的单点实证 —— 调试环境已通，你想跑随时能跑）。

---

## 关联阅读

- 上游 [00 mental model](00-step-stream-role-overview.md) — 5 步骨架认知
- [01 ToolCallingAgent 演出版](01-toolcalling-walkthrough.md) — 每幕变量值剧本
- [02 CodeAgent 演出版](02-codeagent-walkthrough.md) — 沙箱接口
- [03 差异对比](03-impl-diff-deep-dive.md) — 9 个差异维度
- Day 4 [⑥ debugging-walkthrough](../day4-agents/06-run-debugging-walkthrough.md) — 同源调试操作模板
- 下游 [self-check.md](self-check.md) — Day 5 自查闭合
