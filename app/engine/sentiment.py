"""Sentiment composite: 8 weighted components scored -100..+100 each, plus
informational metrics (VIX, IV30, max pain, 0DTE share...).

Missing components (e.g. VIX fetch failed, no flip) are dropped and the
remaining weights renormalized, so the composite is always comparable.
"""
from __future__ import annotations

import datetime
from typing import List, Optional

from .. import config
from ..models import ChainData, Contract, VixData
from .gex import BN


def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


def iv_skew_25d(contracts: List[Contract], today: datetime.date) -> Optional[float]:
    """25-delta put IV minus 25-delta call IV (vol points) at the expiry
    closest to 30 DTE. Positive = puts richer (fear)."""
    expiries = sorted({c.expiry for c in contracts})
    if not expiries:
        return None
    target = min(expiries, key=lambda e: abs((e - today).days - config.SKEW_TARGET_DTE))
    puts = [c for c in contracts
            if c.expiry == target and c.cp == "P" and c.iv > 0 and c.oi > 0]
    calls = [c for c in contracts
             if c.expiry == target and c.cp == "C" and c.iv > 0 and c.oi > 0]
    if not puts or not calls:
        return None
    p = min(puts, key=lambda c: abs(c.delta + config.SKEW_TARGET_DELTA))
    c_ = min(calls, key=lambda c: abs(c.delta - config.SKEW_TARGET_DELTA))
    return (p.iv - c_.iv) * 100.0  # option iv is decimal -> vol points


def max_pain(contracts: List[Contract], expiry: datetime.date) -> Optional[float]:
    """Strike minimizing total intrinsic payout to option holders at expiry."""
    chain = [c for c in contracts if c.expiry == expiry and c.oi > 0]
    if not chain:
        return None
    strikes = sorted({c.strike for c in chain})
    best_strike, best_pay = None, None
    for s in strikes:
        pay = 0.0
        for c in chain:
            if c.cp == "C" and s > c.strike:
                pay += c.oi * (s - c.strike)
            elif c.cp == "P" and s < c.strike:
                pay += c.oi * (c.strike - s)
        if best_pay is None or pay < best_pay:
            best_strike, best_pay = s, pay
    return best_strike


def compute_sentiment(chain: ChainData, gex_totals: dict, flip: Optional[float],
                      vix: Optional[VixData], today: datetime.date,
                      zero_dte_share: float) -> dict:
    spot = chain.spot
    components = []

    def add(name: str, label: str, raw, score: Optional[float]):
        if raw is None or score is None:
            return
        components.append({"name": name, "label": label, "raw": raw,
                           "score": round(score, 1),
                           "weight": config.SENTIMENT_WEIGHTS[name]})

    # 1. Gamma regime: how far spot sits above/below the flip, in % of spot.
    if flip is not None and spot:
        dist = (spot - flip) / spot * 100.0
        add("gamma_regime", "Gamma regime (spot vs flip)",
            round(dist, 2), _clamp(dist / 1.5) * 100.0)
    else:
        sign = 1.0 if gex_totals["net_gex"] > 0 else -1.0
        add("gamma_regime", "Gamma regime (net GEX sign)",
            round(gex_totals["net_gex"] / BN, 2), sign * 100.0)

    # 2. Put/Call volume ratio. 1.0 neutral; lower = call-heavy = bullish.
    if gex_totals["call_vol"] > 0:
        pcr_v = gex_totals["put_vol"] / gex_totals["call_vol"]
        add("pcr_volume", "Put/Call ratio (volume)",
            round(pcr_v, 2), _clamp((1.0 - pcr_v) / 0.4) * 100.0)

    # 3. Net delta-exposure tilt.
    denom = gex_totals["call_dex"] + abs(gex_totals["put_dex"])
    if denom > 0:
        tilt = gex_totals["net_dex"] / denom
        add("dex_tilt", "Delta exposure tilt", round(tilt, 3), _clamp(tilt) * 100.0)

    # 4. VIX day change (falling VIX = risk-on).
    if vix is not None:
        add("vix_change", "VIX day change %",
            round(vix.change_pct, 2), _clamp(-vix.change_pct / 5.0) * 100.0)

    # 5. Put/Call OI ratio. Index baseline ~1.2 neutral.
    if gex_totals["call_oi"] > 0:
        pcr_oi = gex_totals["put_oi"] / gex_totals["call_oi"]
        add("pcr_oi", "Put/Call ratio (OI)",
            round(pcr_oi, 2), _clamp((1.2 - pcr_oi) / 0.5) * 100.0)

    # 6. 25-delta IV skew (~30 DTE). ~4 pts is typical for index puts.
    skew = iv_skew_25d(chain.contracts, today)
    if skew is not None:
        add("iv_skew", "25Δ IV skew (pts)",
            round(skew, 2), _clamp((4.0 - skew) / 3.0) * 100.0)

    # 7. Underlying day momentum.
    add("price_momentum", "Price day change %",
        round(chain.change_pct, 2), _clamp(chain.change_pct / 1.0) * 100.0)

    # 8. IV30 day change (vol bid = defensive).
    add("iv30_change", "IV30 day change %",
        round(chain.iv30_change_pct, 2), _clamp(-chain.iv30_change_pct / 8.0) * 100.0)

    wsum = sum(c["weight"] for c in components)
    score = sum(c["score"] * c["weight"] for c in components) / wsum if wsum else 0.0
    for c in components:
        c["contribution"] = round(c["score"] * c["weight"] / wsum, 1) if wsum else 0.0

    if score >= 50:
        label = "Strongly Bullish"
    elif score >= 15:
        label = "Bullish"
    elif score > -15:
        label = "Neutral"
    elif score > -50:
        label = "Bearish"
    else:
        label = "Strongly Bearish"

    nearest = min({c.expiry for c in chain.contracts}) if chain.contracts else None
    mp = max_pain(chain.contracts, nearest) if nearest else None

    return {
        "score": round(score, 1),
        "label": label,
        "components": components,
        "metrics": {
            "vix": round(vix.level, 2) if vix else None,
            "vix_change_pct": round(vix.change_pct, 2) if vix else None,
            "iv30": round(chain.iv30, 2),
            "iv30_change_pct": round(chain.iv30_change_pct, 2),
            "max_pain": mp,
            "max_pain_expiry": nearest.isoformat() if nearest else None,
            "zero_dte_share_pct": zero_dte_share,
            "net_gex_bn": round(gex_totals["net_gex"] / BN, 2),
            "regime": "positive" if gex_totals["net_gex"] >= 0 else "negative",
            "flip": flip,
            "flip_dist_pct": round((spot - flip) / spot * 100.0, 2) if flip and spot else None,
            "pcr_vol": round(gex_totals["put_vol"] / gex_totals["call_vol"], 2)
                       if gex_totals["call_vol"] else None,
            "pcr_oi": round(gex_totals["put_oi"] / gex_totals["call_oi"], 2)
                      if gex_totals["call_oi"] else None,
        },
    }
