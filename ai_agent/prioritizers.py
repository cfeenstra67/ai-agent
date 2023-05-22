import inspect
from typing import List

from ai_agent.agent import EventPrioritizer
from ai_agent.event_bus import QueuedEvent


def chain_prioritizers(*prioritizers: List[EventPrioritizer]) -> EventPrioritizer:

    async def prioritize(events):
        for item in prioritizers:
            if not events:
                break
            events = item(events)
            if inspect.isawaitable(events):
                events = await events
        return events
    
    return prioritize


def priority_handler(events: List[QueuedEvent]) -> List[QueuedEvent]:
    max_priority = max(event.priority for event in events)
    out = []
    for event in events:
        if event.priority == max_priority:
            out.append(event)
    return out


def single_thread_agent_handler(events: List[QueuedEvent]) -> List[QueuedEvent]:
    seen_agents = set()
    out = []
    for event in events:
        if event.type != "agent":
            out.append(event)
            continue
        if event.destination in seen_agents:
            continue
        seen_agents.add(event.destination)
        out.append(event)
    return out


default_prioritizer = chain_prioritizers(
    priority_handler,
    single_thread_agent_handler,
)
