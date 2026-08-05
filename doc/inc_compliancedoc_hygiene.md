# Briefing — Rewrite `claude_connectors_compliance_master.md`

**Increment:** Compliance-Docs-01
**Scope:** One file — `doc/Claude_Compliance/claude_connectors_compliance_master.md`.
**Deliverable:** The master, accurate against the 11 captured sources, with every known-false claim removed.

---

## 0. Non-goals — read before starting

This increment changes **documentation only**.

- **No code changes.** None. Not annotations, not CSS, not widget files.
- **No tool description changes.** Standing rule: descriptions are shared with the live ChatGPT app and are not touched. This includes the `inspect_adapt` §2B mismatch — it is **recorded as a finding**, not fixed.
- **No PG remediation.** PG findings enter the master as *recorded status*. They do not become work items in this increment.
- **No new source fetches.** Work from the 11 files in `sources_raw/` and nothing else.

If you find yourself editing anything outside the master, stop.

---

## 1. Source status — state this in the header

**Captured (11):** design-guidelines · authentication · transparent-theming · instance-supersession · cross-compatibility · external-links · troubleshooting · review-criteria · submission · software-directory-policy · software-directory-terms

**Provenance per file** — carry into the header, three categories:
- *Paste* — Nadja's copy, carries publication date where the source has one
- *Fetch, paste-corroborated* — bytes match a paste
- *Fetch, relay-corroborated* — N facts confirmed via the review chat; **does not recover the publication date**
- *Fetch only* — `review-criteria` is the sole remaining case

**Uncaptured but relevant (4):** `building/testing` · `building/lazy-authentication` · `building/directory-vs-custom` · `building/managing-your-listing`

**Binding documents outside `llms.txt` (5):** Trademark Guidelines (Terms T-10) · Usage Policy · Universal Usage Standards · High-Risk Use Case requirements · supported-countries policy (all four via policy §1A)

The header must make clear the master is current against 11 sources and silent on 9.

---

## 2. Corrections — every known-false claim, with its source

### §2 Submission Types
- `clau.de/mcp-directory-submission` is **dead** for remote MCPs. Replace with the portal: `claude.ai/admin-settings/directory/submissions/new`
- **New prerequisite:** Team or Enterprise organization; admin settings are unavailable on individual plans. Owners and Primary Owners by default. Enterprise can delegate via a custom role (**Directory management** or **Libraries**); Team plans have no custom roles.
- MCPB form unchanged: `clau.de/desktop-extention-submission`
- Skills are **not** a standalone submission type — bundle in a plugin

### §4C OAuth — largest section of work
1. **DELETE the `static_bearer` line.** It is false. Replace with `static_headers`: fixed credential entered by an **organization administrator** as a request header, **shared by the organization** rather than pasted per user, availability **Beta**.
2. CIMD selection requires **both** `"client_id_metadata_document_supported": true` **and** `"none"` in `token_endpoint_auth_methods_supported` — the second because Claude's CIMD client authenticates as a public client. If either is missing, Claude falls back to DCR.
3. DCR-at-scale: prefer CIMD or `oauth_anthropic_creds` for directory-bound connectors.
4. Latency: 10 s discovery/registration/token, 30 s refresh — plus the operational half: return headers and body without buffering behind upstream work; check no reverse proxy, gateway or WAF holds the response.
5. Parser split: `/token` must accept `application/x-www-form-urlencoded`; `/register` uses `application/json`. Do not assume one parser serves both.
6. `offline_access` is appended automatically when AS metadata lists it in `scopes_supported`.
7. Enterprise Managed Auth exists — SSO orgs connect without interactive consent via an IdP-signed identity assertion. Linked page uncaptured; record as a known gap.
8. Microsoft Entra ID conditional MUST — register the MCP server URL as an Application ID URI or the token request fails `AADSTS9010010`.
9. `oauth_anthropic_creds` credentials are bound to the issuing AS; email `mcp-review@anthropic.com` before migrating.
10. Claude Managed Agents uses a **separate credential set** — an eighth surface. §1 currently lists six platforms.
11. Claude Code's CIMD is published at `https://claude.ai/oauth/claude-code-client-metadata`.
12. `resource_metadata` need not be on the MCP server's origin — any HTTPS location serving the JSON.
13. **A18** — the MCP authorization spec requires authorization servers to display the redirect URI hostname on the consent screen, and recommends an extra warning when only loopback URIs are registered. **Spec-inherited. Absent from both `review-criteria` and the binding policy. NOT a directory gate.** Record as an open security item, post-submission.

**Do NOT re-add** proactive 5-minute refresh as new — it is already documented.

### §4F Documentation
- **"Required sections" is an inflation.** The submission guide says *Recommended sections*.
- The actual obligation set: policy §3A (privacy policy link) · §3B (verified contact and support channels) · §3C (document how it works, purpose, troubleshooting) · §3D (test account with sample data) · §3E (**at least three working examples** — genuinely required). Plus review-criteria: public documentation **by publish date**, blog post or help-centre article sufficient, may be shared privately during review.

### §4K Design guidelines / widget domain
- Delete the 500px hedging paragraph. Constraint is: **auto-fits to content, no nested vertical scroll.** Host caps and clips; **no pixel value is published.** Cite the *Scrolling and gestures* section as the mechanism.
- Mobile fullscreen **is** supported.
- Token reference: add `ghost`, `disabled`, `border-inverse`, the full **ring** group, and the heading size scale with line-heights — or drop the word "Complete".
- Add `baseUriDomains` to the CSP example.
- `prefersBorder`: set true or false explicitly. **If unspecified: borderless on web, bordered on mobile.** Borderless means edge-to-edge with no host padding, so honouring `safeAreaInsets` becomes essential.
- Safe areas apply on **web and desktop**, not only mobile — the composer can overlay an inline app.
- Add inline carousel constraints.
- **`_meta.ui.domain` is NOT mandatory.** Delete *"required on every `ui://` resource. Without it the widget will not render."* Correct: setting it opts the app into a **stable sandbox origin, needed if the app runs its own OAuth flow**. Without it, Claude derives the origin per conversation and connector.
- Domain value: `sha256(<full connector URL>)[:32] + ".claudemcpcontent.com"`. **Hash the exact string configured in Settings > Connectors, including path and any trailing slash.** Record the computation, never a bare hash. Local stdio connectors have no URL — remove the field.

### §4L External links
- **"Rejected during review" is wrong** and matches neither source. Two distinct, both silent: malformed entries are **ignored**; unowned entries are **removed during review**.
- Every origin and scheme **must be owned by the submitting organization**.
- HTTPS origin: scheme and hostname only — paths, ports, query strings ignored. **Subdomains are not implied**; list each.
- Custom scheme: scheme only.
- The reserved-scheme list is **open-ended** ("This includes…"), not closed.
- A bypassed `ui/open-link` resolves once the open is attempted — **not** confirmation the user reached the destination.
- Custom and local connectors **always** show the modal.
- The field is optional.

### §4M Instance supersession
- **State at the top: this page creates no directory obligation.** All language is optional.
- `App` class is **recommended** for production, not required. Fix the heading too.
- Add: tie-break chain `createdAt` → `seq` → instance ID · the `keyFinalized` guard · the `hello`/`born` handshake · post-timeout adoption with recompute and re-announce (may flip back to live) · guard `sendMessage` as well as `updateModelContext`.
- Cross-reference `cross-compatibility#domain-handling`.

### §4N Transparent theming
- `styles.variables` full list: `--color-background-*`, `--color-text-*`, `--color-border-*`, `--color-ring-*`, `--font-*`, `--border-radius-*`, `--border-width-*`. Drop the "etc."
- Add: **register the `hostcontextchanged` listener before `connect()`**.
- State that §4N is the mechanism for discharging **M1** (light and dark themes, never hardcode colours), a genuine MUST recorded in §4K — not optional polish.

### §4O Troubleshooting
- Dev-mode path **Help > Troubleshooting > Enable Developer Mode is correct** — close the conflict with get-started, which describes editing the config file, a different subject.
- **iOS `Referer`:** WebKit omits `Referer` on cross-origin subresource requests. Servers or WAFs gating on it reject iOS traffic while working elsewhere. Allowlist on **`Origin`**, which carries `{hash}.claudemcpcontent.com`, and return a matching `Access-Control-Allow-Origin`.
- **MCP tool calls are proxied through Claude's backend** and egress from Anthropic's IP ranges, **not the user's device.** This reconciles §4E's IP allowlist with the client-side `Origin` rule — two traffic paths, two controls.
- iOS debugging via Safari Web Inspector from a connected Mac.

### §5 Submission form — replace entirely
The old field list is superseded by an eleven-step portal: Introduction · Connection · Tools · Listing · Use cases · Company · Authentication · Data handling · Test & launch · Compliance · Review.

Add:
- Listing limits: name ≤100, tagline ≤55, description ≤2000 characters; 1–5 categories; **slug permanent once published**
- Tools step syncs annotations automatically and groups un-annotated tools separately
- Test & launch includes an attestation: **you confirm you have run every tool yourself**, via MCP Inspector or as a custom connector
- **Compliance step — seven acknowledgments, all required.** Map each to the section it acknowledges, because Terms T-3 makes every one a warranty:
  directory guidelines → §3H · first-party API → §3F · financial → §4A · AI media → §4B · prompt injection → §2D–§2G · conversation data → §1D/§1F · public documentation → §3A/B/C/E
- Screenshots: PNG, ≥1000px wide, 3–5 images, cropped to the app response with **the prompt not in the image**, prompts supplied separately, **any aspect ratio**, **no video or GIF**, one batch covers all surfaces. Figma carousel template available.
- **Remove "Optional: Skills & Plugins."**
- Progress saves in-browser between steps within a session.

### §6 Policy
Verified identical to the captured source. Add **April 15, 2026** plus the capture date.

### NEW §6b — Anthropic Software Directory Terms (March 16, 2026)
Never previously in the repo. Policy §3H makes agreeing to it mandatory. Record:
- **T-3** — *"any information you give us will be accurate and up-to-date"*: a **warranty over every portal field**
- **T-4** — provide **and adhere to** a privacy policy; provide **all applicable third-party privacy policies**; policies must clearly and accurately describe what you **and third parties** collect, use and share
- **T-9** — implement and maintain a **mechanism for receiving security vulnerability reports from Anthropic and third parties**, and investigate with reasonable care. Distinct from §3B's user support channel.
- **T-10** — no statement suggesting partnership, sponsorship or endorsement without prior written approval; comply with **Trademark Guidelines** (uncaptured)
- **T-8** — ongoing duty to maintain standards consistent with the policy **as updated**
- T-5/6/7 — indemnity; licences over descriptions, docs, name, logos; authorisation to review, test, and collect and share functional metadata

### §8 Pre-submission checklist
- Fix the **three-way URL match** — it currently names two. The same exact string must agree across: PRM `resource` field · the URL entered in the portal · the string hashed for `_meta.ui.domain`.
- Add the tool-exercise attestation as a checklist item, marked as a T-3 warranty.
- Note `building/testing` exists and is uncaptured.

### NEW §12 — Post-publication
- Tool changes: **deploy to the server. No resubmission, no scheduled re-review.** Claude picks up the new surface on next connection.
- Caveat: policy states Anthropic conducts **ongoing** reviews, and T-8 obliges continued compliance. "No scheduled re-review" is not "never reviewed".
- Listing edits via the submissions dashboard; `managing-your-listing` (uncaptured) covers what needs review.
- Slug permanent: `https://claude.ai/directory/connectors/SLUG`
- Delist by emailing `mcp-review@anthropic.com`

### §9 PG status — record only, no work items
- A18: open, spec-inherited, **not a directory gate**
- Tool counts: **20 registry / 8 public on Claude's served surface**. `create_priority` carries `destructive_hint=False` in the shared registry and is overridden to `True` for Claude in `tools_list_dupl.py`. **Audit the Claude serving path, not the shared registry.**
- `ui.domain` decision: kept because PG's widget runs its own OAuth flow and needs a stable sandbox origin. Cost: cross-conversation `BroadcastChannel` scope, making a server-minted scope key a precondition if supersession is ever built.
- `inspect_adapt` description/handler mismatch: **recorded as a finding. Not fixed. Descriptions are not touched.**

### §11 Changelog
New dated entry covering this rewrite. Do not edit historical entries — they are a record of what was believed then, including the `static_bearer` row.

---

## 3. Standing checks to record in the master

These came out of the audit and belong in the document, not only in `doc/README.md`:

1. **State the obligation level the source states, and cite where it says so.** Silence is not evidence of absence; emphasis is not evidence of obligation. *(Six instances of soft language being hardened were found in one pass, plus one of the mirror.)*
2. **A negative claim must state the scope it was proved over.** "No match for X in file Y", not "nowhere".
3. **Name the surface a claim describes.** The shared registry is not the Claude serving path.
4. **Never a bare hash.** Record the computation, or the hash together with the URL it derives from.
5. **Relative timestamps are worse than none** — in a committed file they silently re-anchor to whenever the reader looks.

---

## 4. Verification requirements

- Every claim traces to a line in `sources_raw/`. Cite the file. If it cannot be traced, it does not go in.
- Every PG status claim traces to a file and declaration in the codebase, read fresh — not recalled.
- Sections sourced from `review-criteria` (§4B, §7) carry a **fetch-only** marker until that page is paste-corroborated.
- Sections with no captured source (Enterprise Managed Auth, Trademark Guidelines, the four §1A documents) are marked **uncaptured**, not omitted.
- Header, §11 entry and section content are updated **in the same commit**. This has been the failure point three times.
- Report ends with a commit hash and an explicit list of what was **not** verified.

---

## 5. Not in scope, tracked elsewhere

Team/Enterprise organisation requirement · Art. 28 characterisation in the privacy policy · exercising the eight public tools · T-9 mechanism · documentation page · screenshots · widget `max-width` declarations · tool description review.

None of these are documentation work. They belong on the delivery backlog, not in this increment.