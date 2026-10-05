import pytest

from app.storage.call_state import CallState, InMemoryCallStateStore, record_turn


@pytest.mark.asyncio
async def test_in_memory_call_state_round_trip() -> None:
    store = InMemoryCallStateStore()
    state = CallState(
        call_id="call-1",
        tenant_id="demo-clinic",
        language="hinglish",
        turn_count=2,
        handoff_required=True,
    )

    await store.put(state)
    loaded = await store.get("demo-clinic", "call-1")

    assert loaded == state

    await store.delete("demo-clinic", "call-1")
    assert await store.get("demo-clinic", "call-1") is None


@pytest.mark.asyncio
async def test_call_state_is_tenant_scoped() -> None:
    store = InMemoryCallStateStore()
    await store.put(CallState(call_id="same", tenant_id="alpha", turn_count=1))
    await store.put(CallState(call_id="same", tenant_id="beta", turn_count=3))

    assert (await store.get("alpha", "same")).turn_count == 1  # type: ignore[union-attr]
    assert (await store.get("beta", "same")).turn_count == 3  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_record_turn_accumulates_handoff() -> None:
    store = InMemoryCallStateStore()

    first = await record_turn(store, "demo-clinic", "call-2", "en", False)
    second = await record_turn(store, "demo-clinic", "call-2", "hinglish", True)
    third = await record_turn(store, "demo-clinic", "call-2", "en", False)

    assert first.turn_count == 1
    assert second.turn_count == 2
    assert third.turn_count == 3
    assert third.handoff_required is True
