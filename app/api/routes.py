"""API surface: per-symbol snapshots (view slicing) + trinity + health."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, Request

from .. import config, market
from ..engine import snapshot as snapshot_engine
from ..providers.cboe import CboeError

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

VIEWS = {"summary", "heatmap", "strikemap", "flow", "sentiment", "zerodte"}


def _envelope(symbol: str, bundle: dict, cache_meta: dict, views) -> dict:
    meta = dict(bundle["meta"])
    meta.update(cache_meta)
    meta["market"] = market.market_state()
    out_views = {v: bundle[v] for v in views if v in bundle}
    return {"symbol": symbol, "meta": meta,
            "status": bundle["status"], "views": out_views}


async def _get_bundle(request: Request, symbol: str):
    app = request.app
    return await app.state.cache.get(
        symbol,
        lambda: snapshot_engine.build_snapshot(symbol, app.state.client,
                                               app.state.vix_cache),
    )


@router.get("/trinity")
async def trinity(request: Request):
    symbols = list(config.SYMBOLS)
    results = await asyncio.gather(
        *[_get_bundle(request, s) for s in symbols], return_exceptions=True)

    out, errors = {}, {}
    for sym, res in zip(symbols, results):
        if isinstance(res, BaseException):
            log.error("trinity %s failed: %s", sym, res)
            errors[sym] = type(res).__name__
            continue
        bundle, _meta = res
        st = bundle["status"]
        spot = st["spot"] or 1.0

        def pct(level):
            return round((level - spot) / spot * 100.0, 2) if level else None

        sm = bundle["strikemap"]["by_expiry"].get("ALL", {})
        rows = sm.get("rows", [])
        mid = st["spot"]
        near = sorted(rows, key=lambda r: abs(r[0] - mid))[:15]
        near.sort(key=lambda r: r[0], reverse=True)
        out[sym] = {
            "spot": st["spot"],
            "change_pct": st["change_pct"],
            "net_gex_bn": st["total_gex_bn"],
            "regime": st["regime"],
            "flip": st["flip"], "flip_pct": pct(st["flip"]),
            "call_wall": st["call_wall"], "call_wall_pct": pct(st["call_wall"]),
            "put_wall": st["put_wall"], "put_wall_pct": pct(st["put_wall"]),
            "sentiment_score": st["sentiment_score"],
            "sentiment_label": st["sentiment_label"],
            "mini_rows": [[round((r[0] - spot) / spot * 100.0, 2), r[3]] for r in near],
        }

    if not out:
        raise HTTPException(status_code=503, detail="all upstreams unavailable")

    regimes = {v["regime"] for v in out.values()}
    if len(out) == len(symbols) and len(regimes) == 1:
        agreement = {"aligned": True,
                     "label": f"All three in {regimes.pop()} gamma"}
    else:
        agreement = {"aligned": False, "label": "Mixed gamma regimes"}

    return {"symbols": out, "errors": errors, "agreement": agreement,
            "market": market.market_state()}


@router.get("/{symbol}/snapshot")
async def snapshot(request: Request, symbol: str,
                   views: str = Query(default="summary")):
    sym = symbol.upper()
    if sym not in config.SYMBOLS:
        raise HTTPException(status_code=404, detail=f"unknown symbol {symbol}")

    requested = {v.strip() for v in views.split(",") if v.strip()} or {"summary"}
    bad = requested - VIEWS
    if bad:
        raise HTTPException(status_code=400, detail=f"unknown views: {sorted(bad)}")

    try:
        bundle, cache_meta = await _get_bundle(request, sym)
    except CboeError as e:
        log.error("%s snapshot failed: %s", sym, e)
        raise HTTPException(status_code=503, detail="upstream data unavailable")

    return _envelope(sym, bundle, cache_meta, requested - {"summary"})
