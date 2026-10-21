# Custom domains

Kitchen owners open **Settings → Domains** from their workspace, or **Domains**
from the management sidebar. The route is
`/platform/workspaces/<kitchen-slug>/domains/`. Only that kitchen's owners and
platform superusers can manage domains. Manager/staff memberships do not grant
this permission.

## Development and launch

`DOMAIN_CONNECTIONS_ENABLED` defaults to `0`. This is intentional: adding or
verifying a domain must not cut over Annam's existing live website. Preparation
creates a separate pending claim, not a `TenantDomain` routing entry. Existing
Annam domain records and DNS are not changed by this release.

An owner can add their domain, copy a random ownership TXT record and verify it.
At launch they update website DNS at their registrar/provider and explicitly
choose **Connect website**. TXT verification is independent of the website's
A/AAAA/CNAME records, so ownership can be prepared before moving traffic.
Keep the TXT record afterward. DNS checks use Cloudflare's public DNS-over-HTTPS
resolver; propagation and resolver outages are reported without pretending the
domain is connected. Allow 15 seconds between checks.

Each address is separate: `www.example.com` and `example.com` require separate
claims, DNS verification and a working HTTPS route. Add the desired primary
address first. Some hosting providers automatically register/redirect its
counterpart; those provider redirects must be compatible with the chosen
primary. The app does not claim automatic control over registrar DNS, email/MX
records or an external CDN/proxy.

## Platform configuration (server environment only)

| Variable | Purpose |
| --- | --- |
| `DOMAIN_CONNECTIONS_ENABLED` | Keep `0` for preparation. Set `1` only for the production cutover workflow. |
| `DOMAIN_CNAME_TARGET` | Actual public hostname of the serving edge. On Render defaults to `RENDER_EXTERNAL_HOSTNAME`. No scheme, port or wildcard. |
| `DOMAIN_APEX_IPV4` | Optional public root-domain A record supplied by your hosting provider. Do not guess an IP. |
| `DOMAIN_HOSTING_PROVIDER` | `render` (default), `caddy`, or `manual`. |
| `RENDER_API_KEY` | Platform operator's Render API credential; never exposed to kitchen owners. Required for Render automation. |
| `RENDER_SERVICE_ID` | The exact Render web service that runs this app. Required for Render automation. |

For a subdomain the page displays a CNAME. For a root domain it explains
ALIAS/ANAME/CNAME flattening and, when configured, the provider's A record.
Owners must use the DNS record-name convention of their own DNS provider;
the page shows full names to avoid silently assuming a registrar.

The production host allowlist remains in place. A request-local admission
middleware additionally accepts only exact verified custom hosts with an
explicit connection request, or hosts already connected through this workflow.
It never adds a global `*`, mutates `ALLOWED_HOSTS`, or trusts a browser session
as a tenant selection. Same-origin CSRF checks continue to work on these hosts.
Keep the central platform and original hosting addresses in `ALLOWED_HOSTS`.
The platform host itself still must be explicitly configured.

### Render

The adapter reconciles existing service custom domains, registers the verified
hostname if necessary, and requests Render verification. Later checks reuse the
stored provider identifier rather than registering another domain. Render
provisions the certificate; the app independently checks the real HTTPS route.
Until then the UI displays **Waiting for hosting & HTTPS**. Provider errors
are sanitized and do not expose API tokens or response bodies.

The operator configures the Render credential and service once for the platform;
owners do not receive the Render API key. Hosting-plan domain limits, provider
validation delays and costs still apply. This is not a bypass of provider limits.
Render API, DNS and certificate operations are covered with test doubles;
no live customer domain was registered or moved during development. Verify the
adapter with a staging domain in the actual hosting account before enabling
production customer cutovers.

### Caddy

The future shared-server deployment can use Caddy's on-demand TLS. Its `ask`
endpoint is:

```
https://<platform-host>/platform/domains/allow-certificate/
```

Caddy adds `?domain=<hostname>` to that URL. Only claims with successful ownership
and destination checks plus an explicit connection request get HTTP 200.
Unclaimed domains, preparation mode and other hosting modes get HTTP 403.
Configure the public DNS destination, Caddy on-demand TLS, persistent Caddy
certificate storage and the upstream app before enabling this mode. For example:

```caddyfile
{
    on_demand_tls {
        ask https://platform.example.com/platform/domains/allow-certificate/
    }
}

platform.example.com {
    reverse_proxy 127.0.0.1:8000
}

https:// {
    tls {
        on_demand
    }
    reverse_proxy 127.0.0.1:8000
}
```

Replace these sample hosts and upstream addresses with actual deployment values.
This file is guidance; no running proxy configuration is changed by this release.

### Manual hosting

`manual` supports another edge/provider: an operator registers the hostname and
provisions HTTPS there. The app still requires ownership, destination and HTTPS
proof before routing it. A DNS match alone never activates it.

## Verification and activation

1. A unique pending claim reserves the hostname. Wildcards, URLs, ports, IPs,
   local addresses, platform hosts and provider-assigned Render hostnames cannot
   be claimed as customer domains.
2. The TXT value must match this kitchen's random claim token.
3. Website DNS must point to the configured target or its public addresses.
   Private, loopback, link-local and mixed public/private results are rejected.
4. An explicit production connection permits the public HTTPS proof endpoint
   at `/.well-known/seerkitchen-domain`. Pending domains serve no storefront.
5. A certificate-verified HTTPS probe connects to a checked public IP while
   retaining hostname verification/SNI. It does not resolve the customer hostname
   again or follow redirects. A fresh nonce and server HMAC prove that the
   response came from this app. Probes are bounded to one IPv4 and one IPv6
   address; DNS/hosting requests have timeouts and response size limits.
6. Only after that succeeds is the tenant routing entry created. The domain
   becomes **HTTPS active**, but the previous primary remains unchanged.
7. **Make primary** is another explicit action, requiring production mode and
   a successful HTTPS check within the previous 24 hours. Public GET/HEAD pages
   on other mapped addresses redirect to it, preserving path/query. Admin,
   billing, platform, webhook, cart, media and POST requests are not redirected.

Claim/primary mutations are transactional and audited. Pending ownership proofs
are not public routing entries. Live routes are preserved if a later check
fails, with a visible **Connection needs attention** state, so a temporary
resolver outage does not delete a customer's website.

Owners can remove pending or non-primary managed domains, with a separate
confirmation. Render domains are detached from hosting before their database
route is removed; an external API failure leaves the connection intact for
retry. A primary domain must be replaced by another connected primary first.
Original deployment/domain mappings are displayed but cannot be deleted through
this page. Keep platform administration on its own stable hostname when
production tenant domains are introduced.

## Deployment and validation

Migration `tenancy.0007_customdomain` only adds the pending-claim table. It does
not rewrite existing tenant domains. The existing startup migration step applies
it. No external service credentials are required to use preparation mode.

Automated checks cover owner permissions and cross-tenant requests, duplicate
claims, CSRF, ownership/destination failures, preparation mode, HTTPS proof,
provider errors/retries, primary changes, preserved staff/webhook routes,
disconnection and safe host admission. Browser checks cover adding/removing a
domain and readable DNS instructions at 320, 390, 768 and 1440 pixels.

The pre-feature code is preserved at Git tag `pre-custom-domains-2026-10-21`
(commit `3328d25`). A code rollback can leave the additive claim table in place.
If real domains have since been connected, coordinate hosting and routing before
rolling back; code tags do not reverse external DNS/provider changes or restore
a production database.
