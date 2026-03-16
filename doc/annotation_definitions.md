# MCP Tool Annotation Definitions — Interpretation

**Date last updated:** 2026-03-16

---

## Purpose

This document defines how MCP tool annotations are applied, the rationale behind each value, and the authoritative source definitions. It serves as the canonical reference for any future tool additions or annotation reviews.

---

## Spec Definition

The MCP specification defines four boolean annotation hints plus a `title` string. All are optional hints — they do not enforce behavior at the protocol level, but clients (including ChatGPT) use them to determine UX treatment, approval flows, and tool categorization.

| Field | Type | MCP Default | Description |
|---|---|---|---|
| `title` | string | — | Human-readable display name |
| `readOnlyHint` | bool | `false` | If `true`, tool does not modify its environment (user-visible state) |
| `destructiveHint` | bool | `true` | If `true`, tool may perform irreversible destructive updates |
| `idempotentHint` | bool | `false` | If `true`, repeated calls with same args have no additional effect |
| `openWorldHint` | bool | `true` | If `true`, tool interacts with external systems (APIs, web, OAuth) |

Sources: [MCP Spec](https://modelcontextprotocol.io/legacy/concepts/tools), [OpenAI Apps SDK](https://developers.openai.com/apps-sdk/plan/tools/)

---

## Key Interpretations

### `readOnlyHint`

**Definition:** Tool does not mutate user-visible environment state.

**Critical nuance:** "Environment" means what the user or client is aware of — not internal backend bookkeeping. Invisible side effects (background snapshot writes, transparent token refresh) do **not** make a tool non-read-only. Only state the user can observe or that the client needs approval for counts.

**Practical impact:** ChatGPT dev mode shows tools with `readOnlyHint=false` as "write tools," which can trigger approval UI and affect how the model decides to call them. Real-world fix confirmed: developers corrected this by annotating read-only endpoints with `readOnlyHint=true`.

**Decision rule for PG:** A tool is read-only if its primary purpose is fetching and returning data, regardless of whether internal bookkeeping writes happen as a side effect.

### `destructiveHint`

**Definition:** Tool may perform irreversible or destructive updates — data the user cannot recover.

**Only meaningful when `readOnlyHint=false`.** A read-only tool is by definition non-destructive.

**Critical distinction — overwrite vs. delete:**
`destructiveHint=true` applies to **permanent removal** of data (delete operations, access revocation requiring re-authorization). It does NOT apply to update/overwrite operations, even when the previous field values are lost. An update that replaces a value leaves the record intact and the user can change it again — that is not destructive. Only use `destructiveHint=true` when the previous state cannot be recovered at all.

### `openWorldHint`

**Definition:** Tool interacts with external systems outside the PG backend — third-party APIs, OAuth providers, the web.

**For PG:** Any tool that ultimately triggers a Google Calendar API call (even indirectly via the backend) is `openWorldHint=true`. Tools that only interact with the PG database are `openWorldHint=false`.

### `idempotentHint`

**Definition:** Calling the tool repeatedly with identical arguments produces no additional effect beyond the first call.

**Status in PG:** `idempotentHint` is not currently a field on `ToolDefinition` and is therefore never emitted. Not a submission blocker. Future addition if needed.


---


## Decision Rule for New Tools

When adding a new tool, answer these three questions:

1. **Does it write user-visible state?** (creates, updates, deletes records the user sees) → `readOnly=false`. If only invisible bookkeeping → `readOnly=true`.
2. **Is the write irreversible?** (delete, revoke, permanent change) → `destructive=true`.
3. **Does it call an external system?** (Google API, any third-party API, OAuth provider) → `openWorld=true`.
