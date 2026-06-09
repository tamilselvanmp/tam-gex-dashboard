# Tam-Gamma

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/tamilselvanmp/tam-gex-dashboard)

Free, self-hosted **SPX / SPY / QQQ gamma-exposure dashboard** in the style of
spxgexheatmap.com: GEX heatmap, strike map with walls & gamma flip, 0DTE
roadmap, option flow, a composite sentiment gauge and a Trinity (cross-market)
view. Mobile-friendly with a bottom tab bar, auto-refreshing every 30 s.

- **Data**: free CBOE delayed quotes (`cdn.cboe.com`) — no API key, no cost.
  Quotes are ~15 min delayed; greeks (gamma/delta), IV, OI and volume are
  included per contract, so all GEX math is recomputed server-side on every
  refresh. Open interest updates each morning.
- **Stack**: FastAPI + httpx (async) backend, vanilla JS + Apache ECharts
  frontend. No database, no background workers — built for free hosting.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                  # 39 unit tests
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 (dashboard) and http://localhost:8000/guide.html
(how to read it).

## API

| Endpoint | Description |
|---|---|
| `GET /api/{spx\|spy\|qqq}/snapshot?views=heatmap,strikemap,flow,sentiment,zerodte` | Computed snapshot. `status` + `meta` always included; `views` picks payload slices (gzipped, ~1–6 KB each). |
| `GET /api/trinity` | SPX+SPY+QQQ comparison, walls/flip normalized to % from spot. |
| `GET /healthz` | Liveness — never calls upstream. |

## How it stays free-tier friendly

No polling loop runs server-side. Snapshots are **computed on request** and
cached ~30 s (10 min when the market is closed) with stale-while-revalidate
and per-symbol locks, so a sleeping free instance wakes on the first visit,
fetches once, and every subsequent poll inside the TTL is a cache hit. The
raw ~25 MB CBOE chain is parsed under a semaphore and discarded immediately;
only the ~300 KB computed bundle stays in memory.

## Deploy free on Render

Click the **Deploy to Render** button above (or on
[render.com](https://render.com): **New → Blueprint** → pick this repo).
`render.yaml` provisions the free web service automatically. Free instances
sleep after ~15 min idle; the frontend shows a "waking the free server"
notice and recovers automatically (~30–60 s).

## Formulas (per contract)

- `GEX = ±gamma × OI × 100 × spot² × 0.01` (calls +, puts −; $ per 1% move)
- `DEX = delta × OI × 100 × spot`
- **Call/Put wall** = strike with the max positive / min negative net GEX
- **Gamma flip** = interpolated zero-crossing of the cumulative net-GEX
  profile across strikes (can be absent when one side dominates the chain)
- **Sentiment** = weighted composite of 8 indicators (gamma regime, P/C
  volume & OI, delta-exposure tilt, VIX change, 25Δ IV skew, day momentum,
  IV30 change) — see `app/engine/sentiment.py` and the in-app guide.

## Notes & limitations

- CBOE's top-level snapshot `timestamp` is UTC; per-option `last_trade_time`
  is US/Eastern. Both are handled in `app/providers/cboe.py`.
- Buy/sell flow classification is a quote-rule heuristic on delayed data —
  an estimate, not tape-true aggressor flow.
- Educational market-structure tool. **Not financial advice.**
