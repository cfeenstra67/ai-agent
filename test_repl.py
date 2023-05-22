import asyncio
import json
import sys

import aiohttp


async def main() -> None:
    socket_path = "./agent.sock"
    agent_name = sys.argv[1]
    if not agent_name:
        raise ValueError("socket_path and agent_name must be provided")

    connector = aiohttp.UnixConnector(path=socket_path)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.ws_connect(f"http://runner/agents/{agent_name}/chat", timeout=0.5) as ws:
            print("Connected")
            async for message in ws:
                if message.type == aiohttp.WSMsgType.TEXT:
                    response = json.loads(message.data)
                    if response["type"] == "locked":
                        print("Another client is already connected")
                        break

                    if response["type"] == "message":
                        msg_str = "\n\n".join(
                            f"{msg['actor']}:\n{msg['message']}"
                            for msg in response["messages"]
                        )
                        print("MESSAGE")
                        print(msg_str)
                        result = input("Your response: ")
                        if result.strip() == "exit":
                            print("Exiting")
                            break

                        await ws.send_json({"message": result})
                        continue

                    print("Unhandled message type", response["type"])
                elif message.type == aiohttp.WSMsgType.CLOSE:
                    print("CLOSING", message)
                    break
                elif message.type == aiohttp.WSMsgType.ERROR:
                    print("ERROR", message)
                    break


if __name__ == "__main__":
    asyncio.run(main())
