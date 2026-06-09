from __future__ import annotations

import datetime
import json
import os

import pytest

from app.models import Contract

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

EXP_A = datetime.date(2099, 1, 15)
EXP_B = datetime.date(2099, 2, 19)


@pytest.fixture
def mini_chain_raw() -> dict:
    with open(os.path.join(FIXTURE_DIR, "mini_chain.json")) as f:
        return json.load(f)


def mk(cp: str, strike: float, gamma: float = 0.0, oi: int = 0,
       volume: int = 0, delta: float = 0.0, iv: float = 0.2,
       bid: float = 1.0, ask: float = 1.2, last: float = 1.1,
       expiry: datetime.date = EXP_A, root: str = "SPXW") -> Contract:
    return Contract(root=root, expiry=expiry, cp=cp, strike=strike, bid=bid,
                    ask=ask, last=last, iv=iv, oi=oi, volume=volume,
                    delta=delta, gamma=gamma)
