from app.llm.agent import agent

if __name__ == "__main__":
    result = agent.run_sync("Say hi in one short sentence.")
    print("OUTPUT:", result.output)
