# Increment: Condensed cluster row shows a subtree-priority accent line

**Product:** MindSort — **Claude connector only** (widget lives in `mcp_server/mindsort_claude/widget-react/`). This is a Claude/Anthropic SDK app; do not touch the OpenAI variant.
**Type:** Widget (React). Single-file change in `App.tsx` plus tests. **Widget rebuild + cache-bust required** (server-only handler increments don't need this; a widget change does).
**Scope discipline:** Copy and Adjust, Never Rewrite. The change is: (1) the `borderLeft` computation in `ClusterRowToggle`, (2) a small **sr-only span** inside that same row button (required for accessibility — see §3/§4), and (3) a **comment-only** correction to `utils.ts:62`. Do not restructure `ClusterRowToggle`, do not touch the badge logic, do not touch `types.ts`, `main.css`, the fullscreen components, or any handler. The only permitted `utils.ts` touch is the one-line comment fix in §3 — no code change to `utils.ts`.

---

## 1. Problem (confirmed from source, root cause established)

In the **condensed inline board view** (the accordion widget, not fullscreen), a cluster row shows a coloured left-edge accent line **only when the cluster itself has an own priority** (`cluster.priority.rank`). When the priority actually lives on a **subcluster or a thought item inside a collapsed cluster**, the parent cluster row shows the default grey border — so there is no signal at the top level that a priority lives inside. The user only sees the badge after expanding the cluster.

Root cause, in `ClusterRowToggle` (`App.tsx`):

```tsx
const hasPriority = !!cluster.priority?.rank
const rank = cluster.priority?.rank
const colors = rank ? RANK_COLORS[rank] : null
// ...
borderLeft: hasPriority && colors
  ? `3px solid ${colors.border}`
  : `var(--border-width-regular, 0.5px) solid var(--color-border-tertiary, #E0DFDB)`,
```

The border is driven by the cluster's **own** rank only. Nested priority is invisible at the collapsed row. This is currently documented as intentional ("Badge shows OWN rank only, not effective rank") — that intent is being **partially** revised by this increment: see §3 for exactly what changes and what does NOT.

---

## 2. Desired behaviour (from product owner, exact)

- In the **condensed view only**, the collapsed cluster row gets a coloured **left-edge accent line** whenever a priority exists **anywhere in the cluster's subtree** (own rank, or any subcluster/item rank).
- The line colour **matches the priority badge colour** for the rank being surfaced. Colour choice is not otherwise constrained.
- When the subtree contains **mixed ranks**, the line shows the **highest-priority** rank present (P1 over P2 over P3). This is already how the cluster is ordered, so the accent and the sort agree.
- The **priority badge stays at the level where the priority was actually set** (subcluster/item/cluster). The badge is **NOT** promoted to the cluster header. A cluster containing a nested P1 gets a **red accent line but no P1 badge on its header**; the P1 badge appears at its true level when the user expands.
- **Accessibility (required, not optional):** because the accent line is the *only* signal for the nested case, and colour alone is not an accessible signal, the row must also carry a **screen-reader-only text alternative** for the inherited-priority case (see §3 and §4/M2). This adds no visible UI and does not touch the badge.
- **Fullscreen is out of scope.** Do not change any fullscreen component.

---

## 3. Technical facts you need (all verified against the committed widget source)

**The machinery already exists — do not build new logic.**

- `utils.ts` already exports `getEffectiveRank(cluster: Cluster): Rank | null`. It computes `min(own rank, best subcluster effective rank, best direct thought-item rank)` and returns the highest-priority rank anywhere in the subtree, or `null` if none. It is already used by `sortClustersForOverview`. It is **not currently imported** into `App.tsx` — you will add it to the existing `./utils` import.
- `RANK_COLORS[rank].border` gives the matching accent colour per rank (P1 `--color-border-danger`, P2 `--color-border-warning`, P3 `--color-border-info`), with hex fallbacks. This is the same map the badge already uses, so "line matches badge colour" is automatic.
- `Rank = 'P1' | 'P2' | 'P3'`. `getEffectiveRank` returns `Rank | null`.

**What to change — `ClusterRowToggle` in `App.tsx`, border computation ONLY:**

- Keep the existing `rank = cluster.priority?.rank` and the existing `colors` binding **for the badge** exactly as they are.
- Add an effective-rank value used **only** for the border, e.g.:
  - `const effectiveRank = getEffectiveRank(cluster)`
  - `const borderColors = effectiveRank ? RANK_COLORS[effectiveRank] : null`
- Change the `borderLeft` so the coloured `3px solid` branch triggers on `effectiveRank`/`borderColors` instead of `hasPriority`/`colors`. Keep the width at **3px** (the current own-priority width — do not change it). Keep the default grey fallback exactly as-is for the no-priority-anywhere case.
- **Do NOT touch the badge block** (`{hasPriority && rank && colors && ( ... {rank} ... )}`). It must keep rendering off `cluster.priority?.rank` so inherited priority still shows no header badge.

**Add a screen-reader text alternative (required — closes the M2 gap, see §4):**

- The accent line is colour-only, which fails WCAG's text-alternative requirement for the nested case. Add an **`sr-only` span inside the row button**, using the **exact pattern already in this file** for the count pill at `App.tsx:1820` and `App.tsx:2157` (a visually-hidden span). Do not invent a new mechanism or CSS class — reuse the existing `sr-only` pattern.
- The span text reflects the **effective** rank being surfaced, e.g. `contains {effectiveRank} priority` (→ "contains P1 priority"). This gives the screen-reader user the same information the sighted user gets from the line.
- **Gate it precisely** so the accessible output is clean in all three cases:
  - **own rank set** → render **nothing** extra; the badge already carries the rank as text (don't double-announce).
  - **no own rank but `effectiveRank` non-null** (the genuinely-inherited case) → render the `sr-only` span.
  - **`effectiveRank` null** → render nothing.
  Concretely: render the span only when `effectiveRank && !cluster.priority?.rank`.
- This keeps the row's **visible** text identical and does not touch the badge block.

**Comment-only correction to `utils.ts:62` (permitted, required):**

- The design-intent comment there reads *"Effective rank affects ORDER only. Badges and accents show OWN rank."* — it names **accents** explicitly. After this change that sentence is **false** for the condensed-row accent, and a comment that contradicts the code is exactly how the next person reverts the accent back to own-rank. Correct it to say that the condensed inline cluster-row **accent** now reflects **effective** rank (subtree-wide), while **badges** still reflect **own** rank only. This is a **comment change only — no code change to `utils.ts`**. (The badge comment at `App.tsx:1084-1087` stays accurate and needs no edit.)

**Regression reasoning (already checked, stated so you can confirm, not rediscover):**
- A cluster with its **own** rank: `getEffectiveRank` returns that own rank (own rank is a candidate), so the line colour and the badge agree exactly as today. No visual change for own-priority clusters.
- A cluster with **no priority anywhere**: `getEffectiveRank` returns `null` → grey fallback, exactly as today.
- The only changed case is **nested priority**: previously grey, now a coloured line at the highest nested rank, with the header badge still absent.

---

## 4. Compliance — verify before you finalise (do not skip)

The "own-rank badge only" behaviour is documented as an intentional OpenAI-parity decision and is pinned by a test (see §5). This increment does **not** violate it: the badge logic is unchanged; only a coloured **line** (not a badge) is added. But you must confirm two things against the source, and report the result:

1. **Read `mcp_server/mindsort_claude/` widget code + the Claude/Anthropic connector compliance master** (the "Anthropic/Claude Compliance for connectors" artifact, e.g. `doc/claude_compliance*.md` / project KB `claude_compliance_updated_may2026_v2.md`) and confirm **no rule constrains the left-edge accent to reflect own-rank only**. The accent is a colour cue, not a text badge, not a fixed-width element, not navigation. If any rule says otherwise, STOP and report it — do not implement.
2. Confirm **no existing test asserts "no border/accent for inherited rank."** (Author has already checked `App.test.tsx` and found none — the only inherited-rank test asserts no *badge text*, see §5. Re-verify against the working tree at your HEAD in case it changed.)

If either check fails, report and hold. Do not reinterpret the requirement to make it pass.

---

## 5. Tests

Separate **unit** from **integration** as usual.

**Must-still-pass (do not modify):** In `src/test/App.test.tsx`, the test **`'cluster with no own rank but P1 thought sorts first AND shows no badge'`** asserts `expect(screen.queryByText('P1')).not.toBeInTheDocument()` — i.e. no P1 **badge text** for a cluster whose P1 lives on a nested thought. This test **must still pass unchanged**: your change adds a coloured *line* to that cluster's row, not a badge, so the badge-text assertion is unaffected. Do **not** edit this test to accommodate the line. If you believe the line makes this test fail, STOP — that means you changed the badge block, which is out of scope.

**New unit/DOM test(s) to add** (component-level, same mock/`setupInline` harness the file already uses):
- **Nested priority surfaces an accent line on the collapsed cluster row.** Seed a cluster with no own rank but a nested P1 (thought or subcluster). Assert the collapsed cluster row's `border-left` is the coloured `3px` accent using the P1 border token, AND assert **no `P1` badge text** renders on that row (badge stays suppressed). State in a comment which bug each half catches (accent-missing regression; badge-promotion regression).
- **Mixed nested ranks show the highest.** Seed a cluster with both a nested P3 and a nested P1. Assert the row's accent uses the **P1** border token, not P3.
- **Own-priority cluster unchanged.** Seed an own-P2 cluster. Assert the row's accent is the P2 border token AND the P2 badge still renders — proving no regression to the own-rank path.
- **No priority anywhere → grey default.** Seed a plain cluster. Assert the row's `border-left` is the grey `--color-border-tertiary` fallback, not a coloured accent.
- **sr-only text alternative for the inherited case.** Seed a cluster with no own rank but a nested P1. Assert a screen-reader-only element announcing the inherited priority (e.g. text matching `/contains P1 priority/i`) is present in that row. Then seed an **own-P2** cluster and assert that **no** such sr-only "contains … priority" span is added (the badge already carries the text — don't double-announce). Comment: this test would still pass a colour-only implementation only if the sr-only span were wrongly rendered for own-rank clusters too, which the second assertion catches.

For each test, in a one-line comment state **what bug would still pass it** (e.g. "would still pass if the line read own-rank only and the seed happened to have own rank" — so make the seeds have NO own rank where nested-detection is the thing under test).

**Do not** add fullscreen tests — fullscreen is untouched. **Do not** weaken or delete any existing inc 1–7 test.

---

## 6. Build, deploy, verification (widget change → cache-bust required)

- This is a **widget** change: after implementing, **rebuild the widget** (Vite build for `mcp_server/mindsort_claude/widget-react/`) and ensure the built asset that the server serves (`mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html` and/or its bundled JS) is updated. A server-only handler increment would not need this; this one does.
- **Locate and bump the widget cache-bust / version mechanism** that the MindSort-Claude server uses to force Claude to re-fetch the widget (the equivalent of the `WIDGET_VERSION` bump used on prior widget increments — find the actual constant/mechanism in the MindSort-Claude server/discovery/resource layer; do not assume a value). Report the old and new value. If no such mechanism is found, report that explicitly — do not silently skip it.
- **Before deploying, read `doc/OPERATIONS_PREDEPLOY.md` and check for additional pre-deploy tasks.** This increment's brief does not override that checklist.
- **`committed ≠ live`.** After deploy, verify on the real Claude host (`mindsort-mcp.priority-guard.com`): a board where a P1 lives on a subcluster/item inside a collapsed cluster shows a coloured left line on the parent cluster row, the badge does NOT appear on the header, and expanding reveals the badge at its true level. Confirm own-priority clusters look unchanged.

---

## 7. Report requirements (end of implementation)

1. **Commit hash** for the reviewed round (reviews verify against `git show <hash>:<path>`, never the working tree). If you don't provide it, review cannot proceed.
2. The **exact diff** of `ClusterRowToggle` (border computation + the new import), so the reviewer can confirm the badge block is untouched.
3. Result of the **§4 compliance check** — which compliance file(s) you read, and the specific confirmation that no rule constrains the accent to own-rank only.
4. Confirmation that **`'cluster with no own rank but P1 thought sorts first AND shows no badge'`** still passes, plus the new tests, with `pytest`/`vitest` output.
5. The **widget cache-bust/version** mechanism you found and the old→new value (or an explicit statement that none exists).
6. An explicit **"what I did NOT verify"** list.

---

## Deferred / out of scope (do NOT do here)
- Any fullscreen accent change (fullscreen already shows the nested detail; not requested).
- Promoting the badge to the cluster header (explicitly rejected — badge stays at the set level).
- Changing the accent **width** or introducing rank-specific widths.
- Any change to `getEffectiveRank`, `RANK_COLORS`, sorting, or the data model.
