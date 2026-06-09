from __future__ import annotations

import asyncio

import pytest

from app.cache import SnapshotCache


@pytest.mark.asyncio
async def test_cold_start_single_flight():
    cache = SnapshotCache()
    calls = {"n": 0}

    async def builder():
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return {"v": calls["n"]}

    results = await asyncio.gather(*[cache.get("SPX", builder) for _ in range(10)])
    assert calls["n"] == 1
    assert all(bundle == {"v": 1} for bundle, _ in results)
    _, meta = results[0]
    assert meta["stale"] is False


@pytest.mark.asyncio
async def test_stale_while_revalidate():
    cache = SnapshotCache()
    calls = {"n": 0}

    async def builder():
        calls["n"] += 1
        return {"v": calls["n"]}

    await cache.get("SPX", builder)
    cache._entries["SPX"].fetched_at -= 100000  # force staleness

    bundle, meta = await cache.get("SPX", builder)
    assert bundle == {"v": 1}          # stale value served immediately
    assert meta["stale"] is True and meta["refreshing"] is True

    await cache._entries["SPX"].task   # let the background refresh finish
    bundle2, meta2 = await cache.get("SPX", builder)
    assert bundle2 == {"v": 2}
    assert meta2["stale"] is False
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_refresh_failure_keeps_stale_data():
    cache = SnapshotCache()
    state = {"fail": False}

    async def builder():
        if state["fail"]:
            raise RuntimeError("upstream down")
        return {"v": "good"}

    await cache.get("SPX", builder)
    cache._entries["SPX"].fetched_at -= 100000
    state["fail"] = True

    bundle, _ = await cache.get("SPX", builder)
    assert bundle == {"v": "good"}
    await cache._entries["SPX"].task

    bundle2, meta2 = await cache.get("SPX", builder)
    assert bundle2 == {"v": "good"}           # still serving the old data
    assert meta2["error"] is not None or meta2["refreshing"]


@pytest.mark.asyncio
async def test_cold_failure_raises():
    cache = SnapshotCache()

    async def builder():
        raise RuntimeError("upstream down")

    with pytest.raises(RuntimeError):
        await cache.get("SPX", builder)
