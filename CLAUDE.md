# shopify-blade-mcp — Development Boot

Shopify Admin API MCP server. 44 tools, async httpx GraphQL client, FastMCP framework.

## Architecture

- **src/shopify_blade_mcp/server.py** — FastMCP server with 44 `@mcp.tool` functions
- **src/shopify_blade_mcp/client.py** — Async ShopifyClient (httpx), GraphQL query fragments, error hierarchy, cost tracking, webhook HMAC verification
- **src/shopify_blade_mcp/formatters.py** — Token-efficient output: pipe-delimited lists, detail views, pagination hints
- **src/shopify_blade_mcp/models.py** — GID helpers, write/confirm gates, env config, money formatting, secret scrubbing
- **src/shopify_blade_mcp/auth.py** — BearerAuthMiddleware for HTTP transport

## Key patterns

- **Write gate**: `require_write()` checks `SHOPIFY_WRITE_ENABLED=true`
- **Confirm gate**: `require_confirm(confirm, action)` for destructive ops (delete, cancel)
- **Lazy client**: `_get_client()` singleton, constructed on first tool call
- **GID normalisation**: `normalize_id(id, resource_type)` accepts numeric, string, or full GID
- **Error handling**: All tools catch `ShopifyError` and return `f"Error: {e}"`
- **Credential scrubbing**: `scrub_secrets()` masks `shpat_*`, `shpca_*`, `shpss_*`, Bearer tokens
- **Cost tracking**: `client.last_cost` captures GraphQL query cost from `extensions.cost`

## Build & test

```bash
make install-dev    # uv sync --group dev --group test
make test           # pytest (171 tests)
make check          # ruff check + ruff format --check + mypy
make run            # SHOPIFY_MCP_TRANSPORT=stdio (default)
```

## Contract

Implements `ecommerce-v1` (40 operations: 8 required, 11 recommended, 7 optional, 14 gated).
Registered in sidereal-plugin-registry as `plugins/tools/shopify-blade-mcp.json`.
