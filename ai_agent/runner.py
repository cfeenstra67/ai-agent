import asyncio
import logging
from typing import List

from sqlalchemy.ext.asyncio import AsyncEngine

from ai_agent.event_bus import EventBus, ScopedEventBus
from ai_agent.service import Service, Commands, Context, MessageProviders


LOGGER = logging.getLogger(__name__)


class Runner:
    """
    """
    def __init__(
        self,
        services: List[Service],
        engine: AsyncEngine,
        event_bus: EventBus,
    ) -> None:
        self.services = services
        self.commands = Commands(services)
        self.message_providers = MessageProviders(services)
        self.engine = engine
        self.event_bus = event_bus

    async def run(self) -> None:

        async def create_task(command, event, ctx):
            LOGGER.info("Running command %s", command.name)
            task = asyncio.create_task(command.run(event, ctx))
            try:
                await task
            except Exception:
                pass
            return event, command, ctx, task

        while True:
            events = await self.event_bus.get_queued_events()
            if not events:
                sleep_time = 1.
                LOGGER.info("No pending tasks found, sleeping for %.2fs", sleep_time)
                await asyncio.sleep(sleep_time)
                continue

            tasks = []
            for event in events:
                command, service = self.commands.get_command(event.command)
                ctx = Context(
                    event_bus=ScopedEventBus(
                        self.event_bus,
                        service.name,
                        event,
                    ),
                    commands=self.commands,
                    message_providers=self.message_providers,
                    engine=self.engine
                )

                tasks.append(asyncio.create_task(create_task(command, event, ctx)))
            
            done, pending = [], tasks
            while pending:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    event, command, ctx, inner_task = task.result()
                    try:
                        inner_task.result()
                    except Exception as err:
                        LOGGER.exception("Error encountered while running %s", command.name)
                        try:
                            await command.handle_error(err, event, ctx)
                        except Exception:
                            LOGGER.exception("Error handling error for %s", command.name)
                    finally:
                        await self.event_bus.ack_event(
                            event_id=event.event_id,
                            command=event.command,
                            service=event.service,
                        )
                        LOGGER.info("Acknowledged event %d", event.event_id)
