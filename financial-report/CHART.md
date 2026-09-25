# Financial Report chart

The existing SVG renderer in `frontend/market.js` is replaced by vendored TradingView Lightweight Charts 5.0.9. Other dashboards are not replaced. Entry URL and `?symbol=MBB&mode=quarter` remain unchanged. No React is used.

## Files and build

- `frontend/chart-engine.js`: one chart instance, series, panes, viewport, history cache and WebSocket lifecycle.
- `frontend/chart-math.js`: OHLC aggregation and SMA/EMA/RSI/MACD/Bollinger/volume MA.
- `frontend/chart-config.json`: historical API and normalized streaming gateway configuration.
- `frontend/vendor/`: pinned library with license; no runtime dependency on an external chart CDN.
- `frontend/market.js`: existing prices, watchlist, news and symbol integration.
- `scripts/refresh_market.py`: daily (up to 1600 sessions) and minute historical snapshots (up to 1600 bars). Actual coverage depends on the source; no missing bars are fabricated.

Run `python financial-report/scripts/build_cdn.py` to rebuild the standalone entry. Run `python -m unittest discover -s financial-report/tests -v` and `node --test financial-report/tests/chart_math.test.cjs`. Serve repository root with `python -m http.server 8080`; open `/financial-report/?symbol=MBB&mode=quarter`. GitHub Pages uses the existing Pages workflow.

## Current production data boundary

Historical JSON snapshots are supported immediately. They are historical, not a live feed. An empty `websocketUrl` deliberately shows “Chưa kết nối nguồn WebSocket”. No timer polls the historical API; history loads on symbol/timeframe change, explicit refresh, and recovery after a broken WebSocket. News/board retain explicit refresh. Reconnection timers and the no-message timer do not poll an API.

A real market-data subscription/gateway is required to enable live quotes. GitHub Pages cannot run a WebSocket server or hide provider keys. Do not put a provider secret in this config or browser code. This repository currently contains no verified streaming endpoint or credentials for that gateway. The frontend transport does not by itself provide market data.

Configure `websocketUrl` with your authenticated server's `wss://` endpoint. The server must connect to a permitted upstream **stream**, normalize it to the protocol below, enforce entitlement/rate limits, and replay/supply authoritative current bars. Do not implement REST polling behind this WebSocket. Keep provider credentials on that server. If your server also provides history, set `historyBase` to its HTTPS base ending in `/`; the client calls `history?symbol=MBB&interval=1m` or `1d`. Empty historyBase uses existing same-origin Pages snapshots.

## finquery-candles-v1

Client sends `{ "type":"subscribe", "symbols":["MBB","FPT"], "intervals":["1m","1d"] }` on connect and symbol/watchlist changes. Each subscription replaces the previous one. The gateway should cap subscriptions and send market-session status, including holiday and closed-session state. Client replies `{ "type":"pong" }` to `{ "type":"ping" }`.

Server candle (complete OHLCV for a base interval; volume is cumulative **within that candle**, never per-tick or whole-day volume for minute bars):

```json
{"type":"candle","symbol":"MBB","interval":"1m","unit":"VND","bar":{"time":"2026-09-25T02:15:00Z","open":20000,"high":20100,"low":19950,"close":20050,"volume":12300}}
```

Numbers above are protocol examples, not production data. Use ISO timestamps/UTC seconds for 1m and `YYYY-MM-DD` Vietnam trading dates for 1d. Stream all minute/daily base bars in order; same timestamp replaces current candle and newer timestamp appends. Earlier bars are ignored; after reconnect, history is refetched once to fill gaps. Server must supply corrected historical bars through history. Browser buffers messages during history load, then replays them; no simulated prices or gap interpolation.

Quote: `{ "type":"quote", "symbol":"MBB", "price":20050, "reference":20000, "changePct":0.25, "volume":1230000, "sourceTime":"2026-09-25T02:15:03Z" }`.

Status: `{ "type":"status", "message":"Nghỉ trưa · tiếp tục lúc 13:00" }`.

The gateway should send heartbeat while open but quiet. The client reconnects with exponential backoff (max 30 seconds), resubscribes, reports disconnect/staleness and retains the last valid data.

## Indicators and rendering

SMA and volume MA use arithmetic rolling means. EMA is seeded by the first available close. RSI uses Wilder smoothing with an initial average of the first N price differences. MACD uses EMA fast minus EMA slow, with EMA signal. Bollinger uses population standard deviation. Inputs are bounded; MACD fast must be less than slow. Warm-up history affects indicator values.

Timeframes 1/5/15/30/60 minutes aggregate minute bars using Vietnam time; day/week/month use daily bars. 3 months/1 year/5 years are visible ranges, not fabricated candle intervals. No empty trading sessions are invented. On a stream message, only the latest aggregate bucket and indicator point are recalculated and `series.update()` is called; `setData()` is used only for initial load or user-driven configuration changes. Symbol/base-history cache is bounded to 24 entries. Volume, RSI and MACD share the same chart time scale in separate panes.

Lightweight Charts™ Copyright (c) 2025 TradingView, Inc. https://www.tradingview.com/ . Apache License 2.0; see vendor license.
