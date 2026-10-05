import json
from dataclasses import asdict, dataclass, replace
from typing import Protocol

from redis.asyncio import Redis


@dataclass
class CallState:
    call_id: str
    tenant_id: str
    language: str = "en"
    turn_count: int = 0
    handoff_required: bool = False


class CallStateStore(Protocol):
    async def get(self, tenant_id: str, call_id: str) -> CallState | None: ...

    async def put(self, state: CallState) -> None: ...

    async def delete(self, tenant_id: str, call_id: str) -> None: ...


class InMemoryCallStateStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], CallState] = {}

    async def get(self, tenant_id: str, call_id: str) -> CallState | None:
        state = self._items.get((tenant_id, call_id))
        return replace(state) if state is not None else None

    async def put(self, state: CallState) -> None:
        self._items[(state.tenant_id, state.call_id)] = replace(state)

    async def delete(self, tenant_id: str, call_id: str) -> None:
        self._items.pop((tenant_id, call_id), None)


class RedisCallStateStore:
    def __init__(self, redis: Redis, ttl_seconds: int = 3600) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds

    def _key(self, tenant_id: str, call_id: str) -> str:
        return f"vaani:tenant:{tenant_id}:call:{call_id}"

    async def get(self, tenant_id: str, call_id: str) -> CallState | None:
        payload = await self._redis.get(self._key(tenant_id, call_id))
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return CallState(**json.loads(payload))

    async def put(self, state: CallState) -> None:
        await self._redis.set(
            self._key(state.tenant_id, state.call_id),
            json.dumps(asdict(state)),
            ex=self._ttl_seconds,
        )

    async def delete(self, tenant_id: str, call_id: str) -> None:
        await self._redis.delete(self._key(tenant_id, call_id))


async def record_turn(
    store: CallStateStore,
    tenant_id: str,
    call_id: str,
    language: str,
    handoff_required: bool,
) -> CallState:
    state = await store.get(tenant_id, call_id)
    if state is None:
        state = CallState(call_id=call_id, tenant_id=tenant_id)

    state.language = language
    state.turn_count += 1
    state.handoff_required = state.handoff_required or handoff_required
    await store.put(state)
    return state
