"""
🐞 实验：MultiStepAgent 的 ABC 软约束验证

回答的问题：
- ① role-overview §6 笔记说："MultiStepAgent 用了 class MultiStepAgent(ABC) 但 _step_stream 是 raise NotImplementedError
   （不是 @abstractmethod）。所以理论上能直接 MultiStepAgent(...) 实例化，只在调 _step_stream 时才崩 —— 软约束。"
- 软约束是真的吗？真能直接实例化基类吗？什么时候会崩？

跑这个脚本一次性验证 4 个事实：
  ① 直接实例化 MultiStepAgent(...) 能成吗？
  ② 实例化成功后调 .run() 会怎样？
  ③ initialize_system_prompt 在 __init__ 阶段会被调到吗？
  ④ 对比 @abstractmethod 真硬约束（用 ABC + @abstractmethod 写一个对照类）
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from abc import ABC, abstractmethod

# ────────────────────────────────────────────────────────
# 实验 1 · 模拟 smolagents 写法（软约束）
# ────────────────────────────────────────────────────────

class SoftAbstract(ABC):
    """模拟 MultiStepAgent：用 raise NotImplementedError 而不是 @abstractmethod"""

    def __init__(self, name: str):
        self.name = name
        # 注意：这里没调 initialize_system_prompt，所以软约束可以撑过 __init__

    def initialize_system_prompt(self) -> str:
        """模拟 MultiStepAgent.initialize_system_prompt：基类是 ... (相当于 pass，返回 None)"""
        ...

    def _step_stream(self):
        """模拟 MultiStepAgent._step_stream：用 raise NotImplementedError"""
        raise NotImplementedError("This method should be implemented in child classes")


print("=" * 60)
print("实验 1 · 软约束（raise NotImplementedError）")
print("=" * 60)

print("\n[尝试] 直接实例化 SoftAbstract（模拟 MultiStepAgent）...")
try:
    obj = SoftAbstract(name="test")
    print(f"  ✅ 成功！实例化完成：{obj.name}")
except Exception as e:
    print(f"  ❌ 失败：{type(e).__name__}: {e}")

print("\n[尝试] 调 obj.initialize_system_prompt()...")
try:
    result = obj.initialize_system_prompt()
    print(f"  ✅ 没崩。返回值：{result}（注意：是 None，因为基类是 `...`）")
except Exception as e:
    print(f"  ❌ 崩了：{type(e).__name__}: {e}")

print("\n[尝试] 调 obj._step_stream()...")
try:
    obj._step_stream()
except NotImplementedError as e:
    print(f"  ⚠️ 软约束触发：NotImplementedError: {e}")

# ────────────────────────────────────────────────────────
# 实验 2 · @abstractmethod 硬约束对照
# ────────────────────────────────────────────────────────

class HardAbstract(ABC):
    """用 @abstractmethod 真硬约束"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def _step_stream(self):
        """这次用 @abstractmethod 标记"""
        ...


print("\n" + "=" * 60)
print("实验 2 · 硬约束（@abstractmethod）")
print("=" * 60)

print("\n[尝试] 直接实例化 HardAbstract...")
try:
    obj = HardAbstract(name="test")
    print(f"  ✅ 成功：{obj.name}")
except TypeError as e:
    print(f"  ❌ 实例化阶段就崩了：TypeError: {e}")
    print(f"     （这就是 @abstractmethod 比 raise NotImplementedError 强的地方）")

# ────────────────────────────────────────────────────────
# 实验 3 · 用真的 MultiStepAgent 验证（来自 smolagents）
# ────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("实验 3 · 真的 MultiStepAgent 实例化")
print("=" * 60)

try:
    from smolagents import MultiStepAgent
    from smolagents.models import Model

    # 造一个最简的 dummy Model（不真发请求）
    class DummyModel(Model):
        def generate(self, *args, **kwargs):
            from smolagents.models import ChatMessage, MessageRole
            return ChatMessage(role=MessageRole.ASSISTANT, content="dummy")

    print("\n[尝试] MultiStepAgent(tools=[], model=DummyModel())...")
    try:
        agent = MultiStepAgent(tools=[], model=DummyModel())
        print(f"  ✅ 实例化成功！agent_name = {agent.agent_name}")
        print(f"     说明软约束在实际仓库里真的成立")
    except Exception as e:
        print(f"  ❌ 实例化阶段崩了：{type(e).__name__}: {e}")
        print(f"     （这种情况说明 __init__ 中某一步触发了 initialize_system_prompt 调用）")

    # 如果实例化成了，试着调 run（应该会在 _step_stream 阶段崩）
    if 'agent' in locals():
        print("\n[尝试] agent.run('test') ...")
        try:
            agent.run("test")
            print(f"  ⚠️ 居然没崩？")
        except NotImplementedError as e:
            print(f"  ⚠️ 触发了 NotImplementedError（在 _step_stream 调用时）")
            print(f"     {e}")
        except Exception as e:
            print(f"  ⚠️ 崩了：{type(e).__name__}: {e}")

except ImportError as e:
    print(f"  ⚠️ 不在 smolagents 环境运行：{e}")
    print(f"     这是预期的。在 venv 里 'C:/workspace/smolagents/.venv/Scripts/python.exe' 运行可看完整结果")

# ────────────────────────────────────────────────────────
# 总结
# ────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("✨ 结论")
print("=" * 60)
print("""
1. raise NotImplementedError = 软约束
   → 类可以实例化，调到那个方法时才崩
   → 优点：留了"绕过去"的口子
   → 缺点：错误延迟到运行时才暴露

2. @abstractmethod = 硬约束
   → 类根本不能实例化（实例化就 TypeError）
   → 优点：错误最早暴露
   → 缺点：没法"部分实现"

3. ⭐ 实证发现：MultiStepAgent 其实是**硬+软混合约束**
   → initialize_system_prompt 用了 @abstractmethod（硬约束）✅
   → _step_stream 用了 raise NotImplementedError（看起来是软约束）
   → 但因为 initialize_system_prompt 已经硬约束，整个类无法实例化
   → 所以**事实上是硬约束**（实例化阶段就 TypeError）

4. 这次实证修正了 ① role-overview §6 + ④ agent-init-setup-flow §⑧
   的错误描述："软约束 + 理论上能实例化"是错的。实测如下：
   TypeError: Can't instantiate abstract class MultiStepAgent
              without an implementation for abstract method 'initialize_system_prompt'

5. 设计哲学：
   → 用 initialize_system_prompt 当"守门员"（硬约束 = 子类必须实现）
   → _step_stream 即使没标 @abstractmethod 也无所谓
     因为子类已经被 initialize_system_prompt 强迫继承
   → 这种"一硬一软"的混合是**允许子类灵活但仍强制核心契约**的优雅做法

""")
