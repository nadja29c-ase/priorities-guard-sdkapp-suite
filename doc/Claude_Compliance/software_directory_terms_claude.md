# Anthropic Software Directory Terms — the binding contract

**Source:** `https://support.claude.com/en/articles/13145338-anthropic-software-directory-terms`
**Dated:** 16 March 2026. **Fetched:** 2026-08-04.
**Raw source committed:** `sources_raw/software-directory-terms.raw.md` (14 lines, HTTP 200, 4,457 bytes).
**Feeds:** a **new** master section, alongside §6 (which reproduces the Policy).

> ⚠️ **This document had NO repo copy of any kind before 2026-08-04.** The master reproduces the
> Policy in full and has never mentioned the Terms — while **Policy §3H makes agreeing to them
> mandatory.** This is a first capture, so there is nothing to diff against.

---

## Why this is not a formality

The Policy says what the Software must do. **The Terms are what you warrant when you submit.**
Two of them make the rest of this audit contractually load-bearing rather than merely tidy:

| # | Obligation | Verbatim |
|---|---|---|
| **T-3** | **Accuracy warranty** | *"any information you give us will be **accurate and up-to-date**"* |
| **T-4** | **Privacy policy warranty, including third parties** | *"you will provide and adhere to a privacy policy for your Software, **provide all applicable third-party privacy policies**, and ensure all such policies **clearly and accurately describe** to users what user information you and third parties collect and how you and third parties **use and share** such information"* |

**T-3 covers every field on the submission form.** A wrong URL, a stale domain hash, an inflated
capability claim — each is a warranty defect, not a typo.

---

## Part 1 — Obligations (10)

| # | Obligation | Actionable for PG? |
|---|---|---|
| T-1 | Have and maintain all necessary rights to provide the Software and grant the rights in these terms | recorded |
| T-2 | Software and its ordinary intended use complies with all applicable laws and does not violate the Software Directory Policy *"as may be updated from time to time"* | recorded |
| **T-3** | **All information given to Anthropic accurate and up-to-date** | ✅ **YES** |
| **T-4** | **Provide and adhere to a privacy policy; provide ALL APPLICABLE THIRD-PARTY privacy policies; all such policies must clearly and accurately describe what you AND THIRD PARTIES collect, use and share** | ✅ **YES** |
| T-5 | Indemnify and hold Anthropic harmless from claims arising from the Software or users' interactions with it | recorded |
| T-6 | Grant Anthropic non-exclusive, royalty-free, worldwide licences to reproduce/display/distribute Software descriptions and documentation, and to display name, trademarks, logos and branding in Directories | recorded |
| T-7 | Authorise Anthropic to review and test the Software, **collect and use functional metadata** to improve Anthropic Services, and **share that metadata with users** | recorded |
| **T-8** | **Continue implementing and maintaining quality and security standards consistent with the Policy, as updated.** Failure may result in removal | ✅ makes this audit **repeatable, not one-off** |
| **T-9** | **"implement and maintain a mechanism for receiving reports of security vulnerabilities from Anthropic AND FROM THIRD PARTIES, and to investigate such reports with a reasonable standard of care"** | ✅ **YES — appears unimplemented** |
| **T-10** | **No statement suggesting partnership, sponsorship or endorsement by Anthropic without prior written approval; comply at all times with Anthropic's Trademark Guidelines** | ✅ **YES — constrains launch copy** |

**Also recorded:** Anthropic has **no obligation** to include the Software, and may remove it **at
any time for any reason** without liability. Terms may be **modified without prior notice**, and
continued maintenance of the Software constitutes acceptance.

---

## Part 2 — The four that change the critical path

### T-9 — a security-vulnerability reporting mechanism. Distinct from §3B.

Policy §3B requires *"verified contact information and support channels for users with product or
security concerns."* **T-9 is not the same obligation.** It names **Anthropic** and **third
parties** as reporters — not users — and adds a **duty of care**: reports must be *investigated*
to a reasonable standard.

**Nothing in this audit shows such a mechanism exists.** A `security.txt`, a documented intake
address, and a stated triage commitment would discharge it. **Small, and currently missing.**

### T-4 — third-party privacy policies must be *provided*, not merely disclosed

**PG connects to Google Calendar.** T-4 therefore requires:

1. Google's applicable privacy policy **provided** to Anthropic, and
2. PG's own policy to **accurately describe what Google collects, uses and shares** — not only
   what PG does.

The retention record's §10 claims disclosure exists. **Providing a third-party policy link is a
separate obligation** and has not been checked.

### The Art. 28 error is now a warranty defect, not legal hygiene

Privacy policy **v3.2 characterises Anthropic as an Art. 28 data processor**, which is incorrect.

Carried until now as tidy-up. **Under T-3 and T-4 it is neither.** Submitting with a privacy
policy that **misstates Anthropic's own role** is:

- a **T-3** breach — information given to Anthropic that is not accurate, and
- a **T-4** breach — a policy that does not *"clearly and accurately describe"* the third-party
  relationship.

**It moves from "should fix" to "fix before the form goes in."** It is cheap, and it is the one
document Anthropic is guaranteed to read closely.

### T-10 — constrains `fulfilling-productivity.com` launch copy

No wording may suggest partnership, sponsorship or endorsement without **prior written approval**.
*"Works with Claude"* framing needs review against the **Trademark Guidelines**.

⚠️ **The Trademark Guidelines are a second referenced binding document and are NOT in the repo.**
`https://www.anthropic.com/legal/trademark-guidelines` — the `.md` suffix returns **404**, and the
HTML is a Next.js bundle with no clean extraction. **Needs a paste.** Recorded as an obligation
whose *content is unknown*, which is the honest state.

---

## Part 3 — New pre-submission items

| # | Item | Size |
|---|---|---|
| 1 | **Art. 28 correction** in the privacy policy | small, **do first** |
| 2 | **Security-vulnerability reporting mechanism** (T-9) — intake + stated triage | small |
| 3 | **Third-party privacy policy links** (T-4) — Google's, provided and accurately described | small |
| 4 | **Fetch/paste the Trademark Guidelines**, then review launch copy (T-10) | small |
| 5 | **§2B/§2E pass on all 8 public tool descriptions** — now **policy MUSTs**, not review criteria | medium |

**Net effect on the critical path: +2 real items (T-9, Art. 28), −1 (A18 is not a gate).**
Good trade, and both new items are small.

---

## Part 4 — §2B / §2E are policy MUSTs, which upgrades the R6 concern

This was raised as a `review-criteria` R6 issue. It is stronger than that:

- **Policy §2B** — *"descriptions must **precisely match actual functionality**"*
- **Policy §2E** — *"must not attempt to **interfere with Claude calling tools from other
  software**"*

PG's descriptions use *"Call this tool: … **Do NOT call this tool**: …"*, and some steer **away**
from PG toward other behaviour (*"when the user wants to plan, break down, or organize tasks"*).

Whether that constitutes interference under §2E is a real question, not a soft one — and
**Policy §2C** adds that descriptions must not *"create confusion or conflict with other Software
in our Directories"*, which is directly live given PG and MindSort ship from the same developer
with adjacent purposes.

**All 8 public descriptions need a pass against §2B, §2C and §2E. Not done.**
