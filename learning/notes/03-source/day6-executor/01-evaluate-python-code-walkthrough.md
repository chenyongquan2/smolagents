---
created: 2026-05-14
status: active
tags: [smolagents, executor, sandbox, walkthrough, day6, source-reading]
---

# 代码助手老沙的内部：`evaluate_python_code` 5 幕剧本

> ⚠️ **必读前置**：[00 sandbox-role-overview](00-sandbox-role-overview.md) — 沙箱角色 + 3 层防御
>
> 本笔记延续 Day 5 02 [CodeAgent 演出版第 4 幕](../day5-step-stream/02-codeagent-walkthrough.md)：第 4 幕用一句话带过 `python_executor(code)` 的内部，**本篇就是这句话的展开** —— 同一个任务、同一段代码、zoom into 沙箱内部。

---

## 1. 本场戏的设定

延续 Day 5 02 同任务（"查 3 城市最高温转华氏"），假设李四从 LLM 拿到的代码字符串是：

```python
temps = [get_temperature("Beijing"), get_temperature("Tokyo"), get_temperature("Singapore")]
max_temp = max(temps)
final_answer(max_temp * 1.8 + 32)
```

**调用**（接 Day 5 02 第 4 幕）：

```python
code_output = self.python_executor(code_action)
```

`python_executor` 是 `LocalPythonExecutor` 实例，[__call__ 方法](../../../../src/smolagents/local_python_executor.py#L1747) 把活转给 [evaluate_python_code(...)](../../../../src/smolagents/local_python_executor.py#L1583)。**本笔记 zoom 范围就是这个函数的 ~85 行**。

---

## 2. 老沙桌上有什么（入参 4 件）

```python
def evaluate_python_code(
    code: str,                                          # 上面那段代码
    static_tools: dict[str, Callable] | None = None,    # ← 注册工具 + BASE_PYTHON_TOOLS（不可覆盖）
    custom_tools: dict[str, Callable] | None = None,    # ← 用户在沙箱内自己 def 的函数（可覆盖）
    state: dict[str, Any] | None = None,                # ← 变量 namespace（跨步骤共享，Day 5 02 番外 4）
    authorized_imports: list[str] = BASE_BUILTIN_MODULES,
    max_print_outputs_length: int = DEFAULT_MAX_LEN_OUTPUT,
    timeout_seconds: int | None = MAX_EXECUTION_TIME_SECONDS,
)
```

**4 件道具的真实内容**：

| 道具 | 实际值 |
|---|---|
| `code` | `"temps = [...]; final_answer(...)"` |
| `static_tools` | `{"get_temperature": Tool 实例, "final_answer": Tool 实例, **BASE_PYTHON_TOOLS}` |
| `custom_tools` | `{}` 空（用户没在前面步骤 def 过函数）|
| `state` | `{"__name__": "__main__"}` 初始；执行后会塞 `temps`、`max_temp`、`_print_outputs`、`_operations_count` 等 |
| `authorized_imports` | `["collections", "datetime", "itertools", "math", "queue", "random", "re", "stat", "statistics", "time", "unicodedata"]`（默认）|
| `timeout_seconds` | `30` |

---

## 3. 第 1 幕 · 语法解析（[code:1614-1621](../../../../src/smolagents/local_python_executor.py#L1614)）

**老沙视角**：拿到一坨代码字符串，先用 Python 内置 `ast.parse()` 把它解析成**抽象语法树（AST）**：

```python
try:
    expression = ast.parse(code)
except SyntaxError as e:
    raise InterpreterError(f"Code parsing failed on line {e.lineno} ...")
```

**这一幕变了什么**：

| 变量 | 之前 | 之后 |
|---|---|---|
| `expression` | — | `ast.Module(body=[Assign, Assign, Expr])` ← 3 个语句的 AST 树 |

**例子里 expression.body 长这样**（简化）：

```python
[
    Assign(targets=[Name('temps')], value=List(elts=[Call('get_temperature', 'Beijing'), Call('get_temperature', 'Tokyo'), Call('get_temperature', 'Singapore')])),
    Assign(targets=[Name('max_temp')], value=Call('max', [Name('temps')])),
    Expr(value=Call('final_answer', BinOp(...))),
]
```

> 💡 **语法错就死在这里**：如果 LLM 写了不合法的 Python（比如忘了 `:`），第 1 幕直接抛 `InterpreterError` —— Day 5 02 第 3 幕的 `parse_code_blobs` 已经包过这层错误了，但 `parse_code_blobs` 只抠代码不检查语法，**语法检查留给本幕**。

---

## 4. 第 2 幕 · 初始化执行环境（[code:1623-1628](../../../../src/smolagents/local_python_executor.py#L1623)）

**老沙视角**：在桌上摊开几本"账本"，准备记录执行过程：

```python
if state is None:
    state = {}
static_tools = static_tools.copy() if static_tools is not None else {}
custom_tools = custom_tools if custom_tools is not None else {}
state["_print_outputs"] = PrintContainer()        # ⭐ print 输出存这
state["_operations_count"] = {"counter": 0}       # ⭐ 操作数计数（防过多）
```

**这一幕变了什么**：

| state 里多了 | 用途 |
|---|---|
| `_print_outputs` | `PrintContainer` 实例，沙箱内 `print()` 的输出累积到这里 → 最终成为 `CodeOutput.logs` |
| `_operations_count` | 防止超过 `MAX_OPERATIONS=10_000_000` 的兜底（30 秒 timeout 才是主要防线，这只是辅助）|

`static_tools` 是**复制一份**（避免污染外部传入的 dict）。`custom_tools` **不复制**（用户在 LLM 代码里 def 新函数会写进 custom_tools，需要可变）。

---

## 5. 第 3 幕 · 包装 `final_answer`（[code:1630-1636](../../../../src/smolagents/local_python_executor.py#L1630)）

**老沙视角**：这一幕是沙箱设计的精髓。我把 LLM 给的 `final_answer` 工具**偷梁换柱** —— 替换成一个新函数：

```python
if "final_answer" in static_tools:
    previous_final_answer = static_tools["final_answer"]
    
    def final_answer(*args, **kwargs):
        raise FinalAnswerException(previous_final_answer(*args, **kwargs))
    
    static_tools["final_answer"] = final_answer
```

**这一幕变了什么**：

- LLM 代码里 `final_answer(86.0)` 这一行不再"正常返回值"
- 它会 **抛 `FinalAnswerException(86.0)`** —— 立即中断当前正在执行的 AST 遍历

**为什么这样设计**（设计意图核心点）：

LLM 写的代码可能是这样：

```python
temps = [...]
max_temp = max(temps)
final_answer(86.0)
some_more_code_that_should_not_run()    # ⚠️ LLM 可能错放在 final_answer 后面
print("debug...")
```

如果 final_answer 只是"普通返回值"，**`some_more_code` 还会被执行** —— 浪费资源 + 可能产生副作用。

用 **`raise FinalAnswerException`** 强制中断 → 后面的代码**根本不跑** → 立即跳到第 5 幕的捕获逻辑 → 返回 final_answer 的值 + `is_final_answer=True`。

> 💡 **`FinalAnswerException` 继承 `BaseException` 而非 `Exception`**（[code:1572](../../../../src/smolagents/local_python_executor.py#L1572)）—— 这样 LLM 写的 `try: ... except Exception:` **抓不到**它，保证 final_answer 的中断**穿透所有用户 try-except**。这是细致的防御设计。

---

## 6. 第 4 幕 · ⭐⭐ 遍历 AST 节点逐个 evaluate（核心戏！[code:1639-1648](../../../../src/smolagents/local_python_executor.py#L1639)）

**老沙视角**：开始干活！按顺序读 AST 树的每一个语句节点，每读一个就交给 [`evaluate_ast`](../../../../src/smolagents/local_python_executor.py#L1417)（AST 节点分发器）—— 它会按节点类型转给对应的 `evaluate_xxx` 函数。

```python
def _execute_code():
    result = None
    try:
        for node in expression.body:                    # ⭐ 逐个节点
            result = evaluate_ast(node, state, static_tools, custom_tools, authorized_imports)
        state["_print_outputs"].value = truncate_content(...)
        return result, False                            # is_final_answer = False
    except FinalAnswerException as e:                   # ⭐ 第 3 幕埋下的雷
        state["_print_outputs"].value = truncate_content(...)
        return e.value, True                            # is_final_answer = True
    except Exception as e:
        raise InterpreterError(f"Code execution failed at line '...': {type(e).__name__}: {e}")

if timeout_seconds is not None:
    _execute_code = timeout(timeout_seconds)(_execute_code)

return _execute_code()
```

**用我们的例子追踪 evaluate_ast 调用链**：

### 子幕 4.1 · 处理 `temps = [get_temperature(...), get_temperature(...), get_temperature(...)]`

```
evaluate_ast(Assign 节点)
  ↓ 分发到 evaluate_assign
  ↓ 先 evaluate 右侧表达式 List(...)
  ↓ List 里 3 个 Call 节点
  ↓ 每个 Call 都走 evaluate_call:
    - 查名："get_temperature" 在 static_tools 里？✅
    - 调用：static_tools["get_temperature"]("Beijing") → 25.0
    - 同理拿到 30.0, 28.0
  ↓ List 返回 [25.0, 30.0, 28.0]
  ↓ evaluate_assign 把这个值赋给 state["temps"]
```

**state 变化**：

```python
state["temps"] = [25.0, 30.0, 28.0]
```

### 子幕 4.2 · 处理 `max_temp = max(temps)`

```
evaluate_ast(Assign)
  ↓ evaluate_assign
  ↓ 右侧是 Call("max", [Name("temps")])
  ↓ evaluate_call:
    - 查名："max" 在 static_tools 里？✅（BASE_PYTHON_TOOLS 包含）
    - 解析参数：evaluate_name("temps") → state["temps"] = [25.0, 30.0, 28.0]
    - 调用：max([25.0, 30.0, 28.0]) → 30.0
  ↓ state["max_temp"] = 30.0
```

### 子幕 4.3 · 处理 `final_answer(max_temp * 1.8 + 32)`

```
evaluate_ast(Expr)
  ↓ evaluate_call
  ↓ 解析参数：BinOp(BinOp(max_temp * 1.8) + 32)
    - evaluate_binop: 30.0 * 1.8 = 54.0
    - evaluate_binop: 54.0 + 32 = 86.0
  ↓ 查名："final_answer" 在 static_tools 里？✅
  ↓ 调用：static_tools["final_answer"](86.0)
       ↑ 但这是第 3 幕替换过的版本！
       ↓
       raise FinalAnswerException(86.0)    ← ⭐⭐ 异常爆发
```

**异常爆出 evaluate_call → evaluate_assign → for 循环 → _execute_code 的 try → 被 `except FinalAnswerException` 捕获**：

```python
return e.value, True
   ↑ 86.0    ↑ is_final_answer=True
```

> 💡 **30+ evaluate_xxx 函数对应每种 AST 节点类型**（Assign / BinOp / For / While / If / Try / Lambda / FunctionDef / ClassDef / Import / ...）。**Day 6 不要求看每个细节**。结构上就是"按节点类型分发 → 子函数处理 → 递归"标准 visitor 模式。

---

## 7. 第 5 幕 · 返回 `CodeOutput`（[code:1747-1758](../../../../src/smolagents/local_python_executor.py#L1747)）

回到 [`LocalPythonExecutor.__call__`](../../../../src/smolagents/local_python_executor.py#L1747)：

```python
def __call__(self, code_action: str) -> CodeOutput:
    output, is_final_answer = evaluate_python_code(...)
    logs = str(self.state["_print_outputs"])
    return CodeOutput(output=output, logs=logs, is_final_answer=is_final_answer)
```

**最终返回**：

```python
CodeOutput(
    output=86.0,
    logs="",                # 我们例子里没 print 任何东西
    is_final_answer=True,
)
```

—— **这就是 Day 5 02 第 4 幕末尾 `code_output` 拿到的对象**。剧本回到 CodeAgent 主线（[第 5 幕 yield ActionOutput](../day5-step-stream/02-codeagent-walkthrough.md)）。

---

## 8. 🎬 一图压缩 5 幕剧本

```
李四把 code_action 字符串塞给老沙 (python_executor(code))
  ↓
┌─ evaluate_python_code (~85 行) ──────────────────────────┐
│                                                            │
│ ① ast.parse(code) → AST 树                                 │
│    语法错 → InterpreterError 立刻出                       │
│                                                            │
│ ② 初始化 state 加 _print_outputs / _operations_count       │
│                                                            │
│ ③ 包装 final_answer = lambda: raise FinalAnswerException   │
│    ⭐ 让"调 final_answer" 中断执行而不是正常返回           │
│                                                            │
│ ④ ⭐⭐ 遍历 AST 节点：                                    │
│    for node in expression.body:                            │
│        result = evaluate_ast(node, ...)                    │
│        ↓ 按节点类型分发到 30+ evaluate_xxx                 │
│        ↓ 每个 evaluator 自己检查 + 执行                    │
│        ↓ 危险操作 → InterpreterError                       │
│        ↓ 不在白名单 import → InterpreterError              │
│                                                            │
│ ⑤ 捕获异常：                                               │
│    FinalAnswerException → (output, is_final=True)          │
│    其他 Exception      → 包成 InterpreterError 抛          │
│    都没抛            → (result, is_final=False)            │
│                                                            │
│ ⑥ timeout 装饰器把整个 _execute_code 包一层超时保护       │
└────────────────────────────────────────────────────────────┘
  ↓ 返回 (output, is_final_answer)
LocalPythonExecutor.__call__:
  ↓ 包装 logs
  ↓ 返回 CodeOutput(output, logs, is_final_answer)

李四拿到 CodeOutput → 写 memory_step.action_output → yield ActionOutput
```

---

## 9. 跟 Day 5 02 的接缝对照

| Day 5 02 第 4 幕的描述 | Day 6 01 的真实细节 |
|---|---|
| "进沙箱小屋（Day 6 详讲）" | 本笔记 §3-§6 全部 |
| "AST 解析 → 检查每个语句是否安全" | 第 1 幕 + 第 4 幕（每个 evaluator 内部检查）|
| "在受限 namespace 跑 `get_temperature("Beijing")` → `25.0`" | 子幕 4.1 evaluate_call 调用 static_tools["get_temperature"]("Beijing") |
| "继续跑 → `final_answer(86.0)` → 抛 `FinalAnswerException(86.0)` 被沙箱捕获 → `is_final_answer = True`" | 第 3 幕包装 + 子幕 4.3 异常爆发 + 第 5 幕捕获 |
| 沙箱报告 `CodeOutput(output=86.0, logs="", is_final_answer=True)` | 第 5 幕 + LocalPythonExecutor.__call__ |

**Day 5 02 第 4 幕的"沙箱"黑盒，现在被本笔记完全打开**。

---

## 10. 自检（学完本笔记应能）

- [ ] 默写 evaluate_python_code 的 5 幕骨架（每一幕一句话）
- [ ] 解释为什么第 3 幕要"包装 final_answer 让它抛异常"，不直接当普通函数处理（提示：后面的代码不该跑）
- [ ] 解释为什么 `FinalAnswerException` 继承 `BaseException` 而非 `Exception`（提示：用户 try-except）
- [ ] 用我们的例子追踪 `final_answer(max_temp * 1.8 + 32)` 怎么变成 `FinalAnswerException(86.0)` 的（AST 节点路径）
- [ ] 解释 `_print_outputs` / `_operations_count` 在 state 里的作用
- [ ] 说出 `static_tools` vs `custom_tools` 的差异（提示：能否被覆盖）

---

## 关联阅读

- 上游 [00 sandbox-role-overview](00-sandbox-role-overview.md) — 沙箱角色 + 3 层防御
- 同源剧本 Day 5 02 [CodeAgent 演出版第 4 幕](../day5-step-stream/02-codeagent-walkthrough.md) — 接缝对照
- 下游 [self-check.md](self-check.md) — Day 6 自查闭合
- 源码 [evaluate_python_code](../../../../src/smolagents/local_python_executor.py#L1583)
