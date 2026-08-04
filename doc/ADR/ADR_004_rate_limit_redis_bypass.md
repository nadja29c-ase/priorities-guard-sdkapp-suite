# ADR 004 — Rate Limiting: Redis Unavailability Bypass

**Date:** 2026-03-05  
**Status:** Accepted  
**Author:** Nadja Carabulea

---

## Context

The OAuth endpoints (`/authorize`, `/token`, `/revoke`, `/register`) use Redis-backed sliding window rate limiting to prevent brute force attacks. Redis is a required infrastructure dependency for this feature.

The question arose: what should happen when Redis is unavailable?

---

## Decision

When Redis is unavailable, rate limiting is **bypassed** and the request proceeds normally. A structured warning log is emitted (`rate_limit.bypassed`, reason: `redis_unavailable`).

Rate limiting is **not** a hard gate on request processing.

---

## Rationale

- Priority Guardian is a solo-operated product. A Redis outage that also takes down the OAuth flow means users cannot connect their Google Calendar — a complete service failure more damaging than the risk of a burst attack during the outage window.
- Render (Frankfurt) provides infrastructure-level DDoS and flood protection that acts as a first line of defense independently of application rate limiting.
- Redis outages are rare and typically short-lived. The exposure window is small.
- The warning log ensures the bypass is always observable in Better Stack.

Availability-over-security is the correct tradeoff at this scale and deployment model.

---

## Consequences

- **Known risk:** During a Redis outage, the `/token` endpoint (limit: 5/min/client) is unprotected at the application layer. An attacker aware of the outage could attempt brute force against `code_verifier` or `refresh_token` values.
- **Mitigation:** PKCE `code_verifier` is 43–128 chars of high-entropy random — brute force is computationally infeasible regardless of rate limiting. Refresh tokens are equally high-entropy.
- **Monitoring:** Redis connectivity issues surface immediately in Better Stack via the `rate_limit.bypassed` log event.

---

## Alternatives Considered

**Fail closed (reject all requests when Redis is down)**  
Rejected. Converts a Redis infrastructure issue into a full OAuth outage. Disproportionate for the threat model.

**In-memory fallback rate limiter**  
Rejected. In-memory state is per-process and doesn't survive restarts or scale horizontally. Would give false confidence without real protection.
