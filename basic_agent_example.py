# llama-index-llms-ollama
# llama-index-embeddings-huggingface
# workflow
import asyncio
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.ollama import Ollama


def multiply(a: float, b: float) -> float:
    return a * b


agent = FunctionAgent(
    tools=[multiply],
    llm=Ollama(model="llama3.2:3b", request_timeout=360.0),
    system_prompt="You are a helpful assistant that can multiply two numbers.",
)


async def main():
    # Run the agent
    response = await agent.run("What is 1550 * 78945?")
    print(str(response))


# Run the agent
if __name__ == "__main__":
    asyncio.run(main())