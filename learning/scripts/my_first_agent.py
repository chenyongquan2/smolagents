"""
第一个 smolagents demo：让 agent 上网查信息并做计算。

运行方式（在项目根目录）：
  .venv/Scripts/python.exe learning/scripts/my_first_agent.py
"""

from dotenv import find_dotenv, load_dotenv

from smolagents import CodeAgent, InferenceClientModel, WebSearchTool


# find_dotenv() 自动从当前文件位置往上找 .env，不依赖 cwd
load_dotenv(find_dotenv())

# agent = CodeAgent(
#     tools=[WebSearchTool()],
#     model=InferenceClientModel(),
#     stream_outputs=True,  # 关键！亲眼看 agent 一步步思考
# )

# agent.run("豹子全速跑过巴黎艺术桥（Pont des Arts）需要几秒？")

agent = CodeAgent(
    tools=[],                      # ⭐ 不带工具（除 final_answer 兜底）
    model=InferenceClientModel(),
    max_steps=4,                   # ⭐ 设小一点
    stream_outputs=False,          # ⭐ 关闭 token 流（剧本是非流式版本）
)

result = agent.run("What is the result of 2 power 3.7384?")  # ⭐ 用剧本里的同一个任务
print(f"\n=== 最终结果: {result} ===")
