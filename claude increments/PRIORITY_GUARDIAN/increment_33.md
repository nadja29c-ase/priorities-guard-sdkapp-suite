# OAuth Consent Page Fix — Visual + Compliance

## Context

The OAuth consent page for Priority Guardian is served from Jinja2 templates at:
- `backend/templates/oauth_consent_pg_en.html` (English)
- `backend/templates/oauth_consent_pg_de.html` (German)

The page is rendered at `priority-guard.com/oauth/pg/authorize?...` during the ChatGPT → PG OAuth flow.

Three issues to fix across BOTH templates (EN and DE).

---

## 1. Create inverted logo for dark background

The current logo at `backend/static/logo-pg-64.svg` has two SVG path groups:
- Group 1: `fill="#000000"` — the rounded-square outer shape
- Group 2: `fill="#FFFFFF"` — the triangle (play button) inner shape

On the new black background, this logo is invisible (black on black). 

**Create a new file** `backend/static/logo-pg-64-inverted.svg`:
- Copy `logo-pg-64.svg`
- Swap the fill colors: Group 1 becomes `fill="#FFFFFF"`, Group 2 becomes `fill="#000000"`
- Keep everything else identical (viewBox, dimensions, paths)

That's it. No other changes to the SVG.

---

## 2. Dark background + logo reference

In BOTH `oauth_consent_pg_en.html` AND `oauth_consent_pg_de.html`:

**Body background:** Change `background-color: #f1f5f9` → `background-color: #000000`

**Container:** Keep the white card (`background-color: #ffffff`) unchanged. The card sits on the dark background.

**Logo `src`:** Change from `/static/logo-pg.svg` → `/static/logo-pg-64-inverted.svg`

The visual result: black page background, white card in the center, inverted logo (white rounded-square with black triangle) displayed inside the white card.

Wait — on a white card, the inverted logo (white outer shape) would be invisible again. So: use the ORIGINAL `logo-pg-64.svg` (black outer, white triangle) on the white card. The black background only affects the page behind the card.

**Correction:** Change logo `src` to `/static/logo-pg-64.svg` (the 64px version of the original, NOT inverted). The current template references `/static/logo-pg.svg` which is the enormous 7155x6847pt version — that's likely why it fails to render. The `logo-pg-64.svg` has `width="64" height="64"` set explicitly and should render correctly at the intended size.

---

## 3. Privacy Policy AND Terms of Service links

Currently the privacy notice section only links to Privacy Policy. It needs to link to Terms of Service too.

**In `oauth_consent_pg_en.html`**, change the privacy-notice div content to:

```
By authorizing this application, you agree to our
<a href="https://www.priority-guard.com/privacy" target="_blank" rel="noopener noreferrer">Privacy Policy</a>
and
<a href="https://www.priority-guard.com/terms" target="_blank" rel="noopener noreferrer">Terms of Service</a>.
```

**In `oauth_consent_pg_de.html`**, change the equivalent section to:

```
Mit der Autorisierung dieser Anwendung stimmen Sie unserer
<a href="https://www.priority-guard.com/privacy" target="_blank" rel="noopener noreferrer">Datenschutzerklärung</a>
und unseren
<a href="https://www.priority-guard.com/terms" target="_blank" rel="noopener noreferrer">Nutzungsbedingungen</a> zu.
```

---

## 4. Website link with CTA

Add a link to the product website below the privacy notice, above the button group, in BOTH templates.

**In `oauth_consent_pg_en.html`**, add after the privacy-notice div:

```html
<div class="website-link">
    <a href="https://fulfilling-productivity.framer.website/priority-guard" target="_blank" rel="noopener noreferrer">Visit the website →</a>
</div>
```

**In `oauth_consent_pg_de.html`**:

```html
<div class="website-link">
    <a href="https://fulfilling-productivity.framer.website/priority-guard" target="_blank" rel="noopener noreferrer">Website besuchen →</a>
</div>
```

**Add CSS for `.website-link`** (in the `<style>` block of both templates):

```css
.website-link {
    text-align: center;
    margin-bottom: 24px;
}

.website-link a {
    color: #6e6e73;
    font-size: 13px;
    text-decoration: none;
}

.website-link a:hover,
.website-link a:focus {
    text-decoration: underline;
    color: #1d1d1f;
}
```

---

## Files to create

| File | Action |
|------|--------|
| `backend/static/logo-pg-64-inverted.svg` | Create — copy `logo-pg-64.svg`, swap fill colors |

## Files to modify

| File | Changes |
|------|---------|
| `backend/templates/oauth_consent_pg_en.html` | Background black, logo src to `logo-pg-64.svg`, add Terms of Service link, add website CTA |
| `backend/templates/oauth_consent_pg_de.html` | Same changes with German text |

## Acceptance Criteria

1. Page background is black (`#000000`), card remains white
2. Logo renders visibly at 64x64 inside the white card
3. Privacy notice links to BOTH Privacy Policy and Terms of Service
4. Website CTA link is visible and opens in new tab
5. Both EN and DE templates have all changes
6. All links work (test `/privacy`, `/terms`, and the Framer website URL)

## No tests needed

This is a static HTML template change. Visual verification only.