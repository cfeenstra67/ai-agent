import asyncio
from typing import List

import openai
from ai_agent.modular_agent import Chatter, AgentMessage


class ChatGPTChatter(Chatter):
    """
    """
    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
        temperature: float = 1.0,
    ) -> None:
        self.model = model
        self.temperature = temperature

    async def chat(self, messages: List[AgentMessage]) -> str:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: openai.ChatCompletion.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": message.actor, "content": message.message}
                    for message in messages
                ],
            ),
        )

        return response["choices"][0]["message"]["content"]
