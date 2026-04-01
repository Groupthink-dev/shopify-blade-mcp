# shopify-blade-mcp

Shopify Admin API MCP server for Claude and other LLM agents. Token-efficient, security-first, Sidereal-native.

44 tools covering products, orders, customers, inventory, collections, fulfillment, discounts, metafields, webhooks, and analytics — all via GraphQL Admin API.

## Why another Shopify MCP?

Shopify has three official MCPs (Storefront, Customer Accounts, Dev MCP) but **none expose the Admin API** — the API merchants actually use to manage their stores. Community MCPs fill the gap but lack security fundamentals:

- **SecOps** -- Write gating, confirm gate for destructive operations (delete product, cancel order), credential scrubbing in all error paths. No community MCP gates writes at the operation level
- **Token efficiency** -- Pipe-delimited lists, cursor-based pagination hints, human-readable money, null-field omission — not raw GraphQL JSON dumps that burn 10-50x more tokens
- **Sidereal ecosystem** -- `ecommerce-v1` contract with 40 operations across 4 tiers, plugin manifest, webhook HMAC verification for future dispatch integration

## Comparison

| Capability | shopify-blade-mcp | @anthropic/shopify-dev-mcp | cob-shopify-mcp | Shopify Storefront MCP |
|---|---|---|---|---|
| API surface | Admin GraphQL (full) | Dev tooling only | Admin REST (59 tools) | Storefront only (buyer) |
| Token-efficient responses | Pipe-delimited, null omission | N/A (dev tools) | Raw JSON | Raw JSON |
| Write gating | Per-op env var gate | N/A | None -- all writes open | Read-only |
| Destructive op confirmation | `confirm=true` required | N/A | None | N/A |
| Credential scrubbing | `shpat_*`, `shpss_*`, Bearer | Unknown | None | None |
| GraphQL (post-REST deprecation) | Yes (native) | N/A | No (REST, deprecated Oct 2024) | Yes |
| Webhook HMAC verification | Built-in tool | No | No | No |
| Cost tracking | Per-query cost in responses | N/A | No | No |
| GID normalisation | Auto (numeric, string, or full GID) | N/A | Manual | N/A |
| Analytics (ShopifyQL) | Built-in tool | No | No | No |
| Metafield CRUD | Full (namespace filtering) | No | Partial | No |
| Tests | 171 unit tests | Unknown | Unknown | Unknown |
| Sidereal integration | ecommerce-v1 contract | None | None | None |
| Runtime | Python (uv) | Node.js (npx) | Node.js (npx) | Node.js (npx) |

### Token efficiency: before and after

**Typical community MCP** (raw GraphQL JSON, ~1200 tokens):
```json
{"data":{"products":{"edges":[{"node":{"id":"gid://shopify/Product/123","title":"Classic T-Shirt","handle":"classic-t-shirt","status":"ACTIVE","productType":"Shirts","vendor":"TestBrand","tags":["summer","cotton"],"createdAt":"2026-03-15T10:00:00Z","updatedAt":"2026-03-20T14:30:00Z","totalInventory":150,"tracksInventory":true,"priceRangeV2":{"minVariantPrice":{"amount":"29.99","currencyCode":"USD"},"maxVariantPrice":{"amount":"39.99","currencyCode":"USD"}}},"cursor":"abc123"}],"pageInfo":{"hasNextPage":true}}}}
```

**shopify-blade-mcp** (pipe-delimited, ~80 tokens):
```
Classic T-Shirt | classic-t-shirt | ACTIVE | Shirts | TestBrand | $29.99-$39.99 USD | 150 in stock | tags: summer, cotton
... 24 more (pass after="abc123" to continue)
```

## Quick start

```bash
# Install
uv tool install shopify-blade-mcp

# Configure (stdio mode -- default)
export SHOPIFY_STORE_DOMAIN="my-store.myshopify.com"
export SHOPIFY_ACCESS_TOKEN="shpat_..."

# Run
shopify-blade-mcp
```

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "shopify": {
      "command": "uvx",
      "args": ["shopify-blade-mcp"],
      "env": {
        "SHOPIFY_STORE_DOMAIN": "my-store.myshopify.com",
        "SHOPIFY_ACCESS_TOKEN": "shpat_..."
      }
    }
  }
}
```

### HTTP transport (remote/tunnel access)

```bash
export SHOPIFY_MCP_TRANSPORT="http"
export SHOPIFY_MCP_HOST="127.0.0.1"
export SHOPIFY_MCP_PORT="8770"
export SHOPIFY_MCP_API_TOKEN="your-bearer-token"  # optional, enables auth
shopify-blade-mcp
```

## Security model

### Write gate

All mutating operations require `SHOPIFY_WRITE_ENABLED=true`. Without it, the server is read-only -- safe for analytics, auditing, and exploration.

### Confirm gate

Destructive operations that are difficult or impossible to reverse require `confirm=true`:
- Delete product
- Cancel order
- Delete discount
- Delete metafield
- Delete webhook

### Credential scrubbing

Shopify tokens (`shpat_*`, `shpca_*`, `shpss_*`) and Bearer tokens are scrubbed from all error messages. Credentials never leak through tool responses.

### Bearer auth (HTTP transport)

When `SHOPIFY_MCP_API_TOKEN` is set, every HTTP request must include a matching `Authorization: Bearer <token>` header. Constant-time comparison via `secrets.compare_digest`.

### GID normalisation

All tools accept flexible resource identifiers -- numeric IDs (`123`), plain strings, or full Shopify GIDs (`gid://shopify/Product/123`). Normalised automatically.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `SHOPIFY_STORE_DOMAIN` | Yes | Store domain (`my-store.myshopify.com`) |
| `SHOPIFY_ACCESS_TOKEN` | Yes | Admin API access token (`shpat_...`) |
| `SHOPIFY_API_VERSION` | No | API version (default `2025-04`) |
| `SHOPIFY_WRITE_ENABLED` | No | Set to `true` to enable write operations |
| `SHOPIFY_WEBHOOK_SECRET` | No | Webhook signing secret for HMAC verification |
| `SHOPIFY_MCP_TRANSPORT` | No | `stdio` (default) or `http` |
| `SHOPIFY_MCP_HOST` | No | HTTP host (default `127.0.0.1`) |
| `SHOPIFY_MCP_PORT` | No | HTTP port (default `8770`) |
| `SHOPIFY_MCP_API_TOKEN` | No | Bearer token for HTTP transport auth |

## Tools (44)

### Meta (2)

| Tool | R/W | Description |
|---|---|---|
| `shopify_info` | R | Configuration status, connectivity, API version |
| `shopify_shop` | R | Store details (name, plan, domain, currency, timezone) |

### Locations (1)

| Tool | R/W | Description |
|---|---|---|
| `shopify_locations` | R | Warehouse and retail locations with fulfillment capabilities |

### Products (5)

| Tool | R/W | Description |
|---|---|---|
| `shopify_products` | R | List/search products (status, type, vendor, query filters) |
| `shopify_product` | R | Product detail with variants, images, SEO, options |
| `shopify_create_product` | W | Create product with variants |
| `shopify_update_product` | W | Update product fields |
| `shopify_delete_product` | W+C | Delete product (confirm required) |

### Orders (7)

| Tool | R/W | Description |
|---|---|---|
| `shopify_orders` | R | List orders (status, financial/fulfillment status filters) |
| `shopify_order` | R | Order detail with line items, addresses, transactions |
| `shopify_search_orders` | R | Search by order name (#1001) or query string |
| `shopify_update_order_note` | W | Update order note |
| `shopify_add_order_tags` | W | Add tags to order |
| `shopify_close_order` | W | Close order |
| `shopify_cancel_order` | W+C | Cancel order (confirm required) |

### Fulfillment (3)

| Tool | R/W | Description |
|---|---|---|
| `shopify_order_fulfillments` | R | List fulfillment orders for an order |
| `shopify_create_fulfillment` | W | Create fulfillment with tracking |
| `shopify_update_tracking` | W | Update tracking info on existing fulfillment |

### Customers (5)

| Tool | R/W | Description |
|---|---|---|
| `shopify_customers` | R | List customers (query filter) |
| `shopify_customer` | R | Customer detail with addresses, orders, spend |
| `shopify_search_customers` | R | Search by email, name, or phone |
| `shopify_create_customer` | W | Create customer |
| `shopify_update_customer` | W | Update customer fields |

### Inventory (3)

| Tool | R/W | Description |
|---|---|---|
| `shopify_inventory` | R | Inventory levels by location |
| `shopify_adjust_inventory` | W | Relative inventory adjustment (+/-) |
| `shopify_set_inventory` | W | Set absolute inventory quantity |

### Collections (4)

| Tool | R/W | Description |
|---|---|---|
| `shopify_collections` | R | List collections (smart + custom) |
| `shopify_collection` | R | Collection detail with products |
| `shopify_create_collection` | W | Create custom collection |
| `shopify_collection_add_products` | W | Add products to collection |

### Discounts (3)

| Tool | R/W | Description |
|---|---|---|
| `shopify_discounts` | R | List discount codes and automatic discounts |
| `shopify_create_discount` | W | Create basic discount code |
| `shopify_delete_discount` | W+C | Delete discount (confirm required) |

### Metafields (3)

| Tool | R/W | Description |
|---|---|---|
| `shopify_metafields` | R | List metafields (owner, namespace filters) |
| `shopify_set_metafield` | W | Set metafield value |
| `shopify_delete_metafield` | W+C | Delete metafield (confirm required) |

### Webhooks (3)

| Tool | R/W | Description |
|---|---|---|
| `shopify_webhooks` | R | List webhook subscriptions |
| `shopify_create_webhook` | W | Create webhook subscription |
| `shopify_delete_webhook` | W+C | Delete webhook (confirm required) |

### Analytics (1)

| Tool | R/W | Description |
|---|---|---|
| `shopify_analytics` | R | Run ShopifyQL queries for sales, traffic, and inventory analytics |

### Verification (1)

| Tool | R/W | Description |
|---|---|---|
| `shopify_verify_webhook` | R | HMAC-SHA256 webhook signature verification |

**R/W legend:** R = read, W = write (`SHOPIFY_WRITE_ENABLED=true`), W+C = write + confirm (`confirm=true`)

## Development

```bash
make install-dev    # Install with dev + test dependencies
make test           # Run tests (171 tests)
make check          # Lint + format check + type check
make run            # Run server (stdio)
```

## Sidereal integration

This MCP implements the `ecommerce-v1` service contract with full conformance (8/8 required, 11/11 recommended, 7/7 optional, 14/14 gated operations). Registered in the [Sidereal Plugin Registry](https://github.com/groupthink-dev/sidereal-plugin-registry) as a certified plugin.

## Licence

MIT
