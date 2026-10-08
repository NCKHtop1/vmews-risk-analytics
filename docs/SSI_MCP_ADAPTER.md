# SSI MCP - isolated adapter (not enabled by default)

Endpoint: https://mcp.ssi.com.vn/mcp. This adapter calls the official MCP JSON-RPC protocol (tools/list and tools/call), not SSI FastConnect.

## Configuration

- SSI_MCP_ENABLED=1 (off by default)
- SSI_MCP_ACCESS_TOKEN: SSI OAuth-issued access token obtained through a supported authorized SSI client. Never put in HTML, JavaScript, repository or GitHub Pages.
- FINQUERY_SSI_GATE_KEY: independent strong secret used as a server-side administrator gate. Not an SSI token. Do not expose in static frontend code.

The API endpoint is /api/ssi-mcp?symbol=FPT&kind=indicators on a **serverless backend hosting the API directory**. Calling this URL requires an x-finquery-ssi-key header. It **does not work on GitHub Pages**, and is not wired to public Dolphin AI.

The adapter is strictly read-only, uses an explicit tool allowlist, checks the announced tool inputSchema before constructing arguments, returns 'schema_unverified' if required inputs are unknown, enforces max 8 s per call, bounds response sizes, and reports SSI unavailable independently.

## Current release gate

Do NOT set SSI_MCP_ENABLED=1 until a real SSI OAuth login/credential flow, token renewal, actual tool schemas and terms for redisplaying SSI outputs have been verified. Do NOT copy the administrator gate into any public/browser bundle. There is no claim of successful live authenticated SSI response yet.

Only after successful end-to-end authenticated tests and SSI redistribution permissions should the FinQuery research agent consume vetted SSI results as optional evidence with source timestamps. Price, intraday, trading signals, snapshots and production publishers remain untouched.
