from __future__ import annotations

from app.engine import gex


def _row(strike, net):
    return {"strike": strike, "call_gex": max(net, 0.0),
            "put_gex": min(net, 0.0), "net_gex": net}


def test_flip_interpolation():
    # cum: -100M @5900 -> +300M @5950; zero crossing at 5912.5
    profile = [_row(5900.0, -100e6), _row(5950.0, +400e6)]
    assert gex.find_flip(profile, spot=5920.0) == 5912.5


def test_flip_none_when_one_sided():
    profile = [_row(5900.0, 50e6), _row(5950.0, 60e6)]
    assert gex.find_flip(profile, spot=5920.0) is None


def test_flip_multiple_crossings_picks_nearest_spot():
    # cum: -10 @100, +10 @110 (cross ~105), -10 @120 (cross ~115), +10 @130 (cross ~125)
    profile = [_row(100.0, -10e6), _row(110.0, 20e6),
               _row(120.0, -20e6), _row(130.0, 20e6)]
    flip = gex.find_flip(profile, spot=124.0)
    assert 120.0 < flip < 130.0


def test_walls():
    profile = [_row(7300.0, -80e6), _row(7400.0, 20e6), _row(7500.0, 90e6)]
    call_wall, put_wall = gex.find_walls(profile)
    assert call_wall == 7500.0
    assert put_wall == 7300.0


def test_walls_one_sided():
    profile = [_row(7400.0, 20e6), _row(7500.0, 90e6)]
    call_wall, put_wall = gex.find_walls(profile)
    assert call_wall == 7500.0
    assert put_wall is None


def test_strike_profile_aggregates_and_sorts():
    from tests.conftest import EXP_A, EXP_B, mk
    cs = [mk("C", 7400, gamma=0.001, oi=100, expiry=EXP_A),
          mk("P", 7400, gamma=0.002, oi=100, expiry=EXP_B),
          mk("C", 7300, gamma=0.001, oi=50, expiry=EXP_A)]
    prof = gex.strike_profile(cs, 7400.0)
    assert [r["strike"] for r in prof] == [7300.0, 7400.0]
    r7400 = prof[1]
    assert r7400["net_gex"] == r7400["call_gex"] + r7400["put_gex"]
    assert r7400["put_gex"] < 0

    # Single-expiry filter
    prof_a = gex.strike_profile(cs, 7400.0, expiry=EXP_A)
    assert [r["strike"] for r in prof_a] == [7300.0, 7400.0]
    assert prof_a[1]["put_gex"] == 0.0
