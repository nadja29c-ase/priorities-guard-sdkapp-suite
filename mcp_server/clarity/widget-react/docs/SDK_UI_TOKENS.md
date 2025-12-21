# OpenAI Apps SDK UI - Complete Design Tokens Reference

**Extracted from:** `@openai/apps-sdk-ui@0.2.1`  
**Purpose:** Clarity widget migration reference

---

## 1. BREAKPOINTS

```css
--breakpoint-xs: 380px;
--breakpoint-sm: 576px;
--breakpoint-md: 768px;
--breakpoint-lg: 1024px;
--breakpoint-xl: 1280px;
--breakpoint-2xl: 1536px;
```

**Tailwind usage:** `xs:`, `sm:`, `md:`, `lg:`, `xl:`, `2xl:`

---

## 2. FONT FAMILIES

```css
--font-sans: ui-sans-serif, -apple-system, system-ui, "Segoe UI", "Noto Sans", "Helvetica", "Arial", "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", sans-serif;
--font-mono: ui-monospace, "SFMono-Regular", "SF Mono", "Menlo", "Monaco", "Consolas", "Liberation Mono", "DejaVu Sans Mono", "Courier New", monospace;
```

**Tailwind usage:** `font-sans`, `font-mono`

---

## 3. FONT WEIGHTS

```css
--font-weight-normal: 400;
--font-weight-medium: 500;
--font-weight-semibold: 600;
--font-weight-bold: 700;
```

**Tailwind usage:** `font-normal`, `font-medium`, `font-semibold`, `font-bold`

---

## 4. BORDER RADIUS

```css
--radius-2xs: 0.125rem;  /* 2px */
--radius-xs: 0.25rem;    /* 4px */
--radius-sm: 0.375rem;   /* 6px */
--radius-md: 0.5rem;     /* 8px */
--radius-lg: 0.625rem;   /* 10px */
--radius-xl: 0.75rem;    /* 12px */
--radius-2xl: 1rem;      /* 16px */
--radius-3xl: 1.25rem;   /* 20px */
--radius-4xl: 1.5rem;    /* 24px */
--radius-full: 9999px;
```

**Tailwind usage:** `rounded-2xs`, `rounded-xs`, `rounded-sm`, `rounded-md`, `rounded-lg`, `rounded-xl`, `rounded-2xl`, `rounded-3xl`, `rounded-4xl`, `rounded-full`

---

## 5. SPACING

```css
--spacing: 0.25rem;  /* 4px base unit */
```

**Tailwind usage:** Standard spacing scale (e.g., `p-4` = 16px, `gap-2` = 8px)

---

## 6. PRIMITIVE COLORS

### Gray Scale (Light Mode → Dark Mode inverts)

| Token | Light Mode | Dark Mode |
|-------|------------|-----------|
| `--gray-0` | #ffffff | #0d0d0d |
| `--gray-25` | #fcfcfc | #101010 |
| `--gray-50` | #f9f9f9 | #131313 |
| `--gray-75` | #f3f3f3 | #161616 |
| `--gray-100` | #ededed | #181818 |
| `--gray-150` | #dfdfdf | #1c1c1c |
| `--gray-200` | #cdcdcd | #212121 |
| `--gray-250` | #b9b9b9 | #282828 |
| `--gray-300` | #afafaf | #303030 |
| `--gray-350` | #9f9f9f | #393939 |
| `--gray-400` | #8f8f8f | #414141 |
| `--gray-450` | #767676 | #4f4f4f |
| `--gray-500` | #5d5d5d | #5d5d5d |
| `--gray-550` | #4f4f4f | #767676 |
| `--gray-600` | #414141 | #8f8f8f |
| `--gray-700` | #303030 | #afafaf |
| `--gray-800` | #212121 | #cdcdcd |
| `--gray-900` | #181818 | #ededed |
| `--gray-1000` | #0d0d0d | #ffffff |

### Color Palettes (Same in both modes)

**Green:**
```css
--green-400: #04b84c;  /* Primary green */
--green-500: #00a240;
--green-600: #008635;
--green-700: #00692a;
```

**Red:**
```css
--red-400: #fa423e;   /* Primary red */
--red-500: #e02e2a;
--red-600: #ba2623;
--red-700: #911e1b;
```

**Blue:**
```css
--blue-400: #0285ff;  /* Primary blue */
--blue-500: #0169cc;
--blue-600: #004f99;
--blue-700: #003f7a;
```

**Orange:**
```css
--orange-400: #fb6a22;
--orange-500: #e25507;
--orange-600: #b9480d;
--orange-700: #923b0f;
```

**Yellow:**
```css
--yellow-400: #ffc300;
--yellow-500: #e0ac00;
--yellow-700: #916f00;
```

**Purple:**
```css
--purple-400: #924ff7;
--purple-500: #8046d9;
--purple-600: #6b3ab4;
```

### Alpha Transparencies

```css
--alpha-02: 2%
--alpha-04: 4%
--alpha-05: 5%
--alpha-06: 6%
--alpha-08: 8%
--alpha-10: 10%
--alpha-12: 12%
--alpha-15: 15%
--alpha-16: 16%
--alpha-20: 20%
--alpha-25: 25%
```

**Note:** Alpha uses `color-mix(in oklab, var(--alpha-base) X%, transparent)` where `--alpha-base` is #0d0d0d (light) or #ffffff (dark)

---

## 7. SEMANTIC COLORS

### Text Colors

| Token | Tailwind Class | Light | Dark |
|-------|----------------|-------|------|
| `--color-text` | `text-default` | gray-1000 | gray-1000 |
| `--color-text-inverse` | `text-inverse` | gray-0 | gray-0 |
| `--color-text-secondary` | `text-secondary` | gray-500 | gray-700 |
| `--color-text-tertiary` | `text-tertiary` | gray-400 | gray-600 |
| `--color-text-disabled` | `text-disabled` | gray-400 | gray-500 |

### Surface & Background Colors

| Token | Tailwind Class | Light | Dark |
|-------|----------------|-------|------|
| `--color-surface` | `bg-surface` | gray-0 | gray-200 |
| `--color-surface-secondary` | `bg-surface-secondary` | gray-50 | gray-100 |
| `--color-surface-tertiary` | `bg-surface-tertiary` | gray-75 | gray-50 |
| `--color-surface-elevated` | `bg-surface-elevated` | gray-0 | gray-300 |

### Border Colors

| Token | Tailwind Class | Light | Dark |
|-------|----------------|-------|------|
| `--color-border-subtle` | `border-subtle` | alpha-05 | alpha-06 |
| `--color-border` | `border-default` | alpha-10 | alpha-12 |
| `--color-border-strong` | `border-strong` | alpha-15 | alpha-20 |

---

## 8. SHADOWS

```css
--shadow-sm: elevation-100  /* 0 1px 2px -1px */
--shadow-md: elevation-200  /* 0 2px 4px -1px */
--shadow-lg: elevation-300  /* 0 4px 8px -2px */
--shadow-xl: elevation-400  /* 0 8px 16px -4px */
```

**Tailwind usage:** `shadow-sm`, `shadow-md`, `shadow-lg`, `shadow-xl`

---

## 9. TYPOGRAPHY UTILITIES

### Heading Classes

```css
heading-5xl  /* 4.5rem, semibold, tight tracking */
heading-4xl  /* 3.75rem */
heading-3xl  /* 3rem */
heading-2xl  /* 2.25rem */
heading-xl   /* 2rem */
heading-lg   /* 1.5rem */
heading-md   /* 1.25rem */
heading-sm   /* 1.125rem */
heading-xs   /* 1rem */
```

### Text Size Classes

| Class | Size | Line Height |
|-------|------|-------------|
| `text-lg` | 1.125rem | 1.8125rem |
| `text-base` | 1rem | 1.5rem |
| `text-sm` | 0.875rem | 1.25rem |
| `text-xs` | 0.75rem | 1.125rem |
| `text-2xs` | 0.625rem | 0.875rem |
| `text-3xs` | 0.5rem | 0.75rem |

---

## 10. BADGE COMPONENT

### Colors (via `color` prop)

- `secondary` - Gray/neutral (USE THIS FOR PRIORITY BADGES)
- `success` - Green
- `warning` - Orange
- `danger` - Red
- `info` - Blue
- `discovery` - Purple

### Variants (via `variant` prop)

- `soft` - Transparent background with tinted color
- `solid` - Solid background color
- `outline` - Border only

### Sizes (via `size` prop)

- `sm` - Small
- `md` - Medium (default)
- `lg` - Large

### Usage Example

```jsx
import { Badge } from "@openai/apps-sdk-ui"

// Priority badges - use neutral color, differentiate by label
<Badge color="secondary" variant="solid" size="sm">P1</Badge>
<Badge color="secondary" variant="solid" size="sm">P2</Badge>
<Badge color="secondary" variant="solid" size="sm">P3</Badge>

// Tags - use soft variant
<Badge color="secondary" variant="soft" size="sm">decide</Badge>
```

---

## 11. BUTTON COMPONENT

### Colors (via `color` prop)

- `primary` - Primary action (use for Save button)
- `secondary` - Secondary action (use for Cancel)
- `danger` - Destructive action

### Variants (via `variant` prop)

- `solid` - Filled background
- `outline` - Border only
- `ghost` - No background or border

### Usage Example

```jsx
import { Button } from "@openai/apps-sdk-ui"

<Button color="primary" variant="solid">Save</Button>
<Button color="secondary" variant="outline">Cancel</Button>
```

---

## 12. THEME HANDLING

### SDK Hooks (preferred for React)

```typescript
import { useDocumentTheme, getDocumentTheme, applyDocumentTheme } from "@openai/apps-sdk-ui";

// In React component - auto-updates on theme change
function App() {
  const theme = useDocumentTheme(); // Returns "light" | "dark"
}

// Outside React - one-time read
const theme = getDocumentTheme();

// Apply theme (if needed for initial setup)
applyDocumentTheme("dark");
```

**Important:** Do not manually set `data-theme` attribute. The SDK hook manages theme reactively via MutationObserver.

### How It Works

The `useDocumentTheme` hook:
1. Reads `data-theme` attribute from `document.documentElement`
2. Falls back to checking for `.dark` class
3. Observes attribute changes via MutationObserver
4. Auto-updates component on theme change

---

## 13. CSS SETUP

```css
/* main.css */
@import "tailwindcss";
@import "@openai/apps-sdk-ui/css";
@source "../node_modules/@openai/apps-sdk-ui";
```

```jsx
// main.tsx - import CSS FIRST
import "./main.css"
import { createRoot } from "react-dom/client"
```

---

## 14. MOTION/TRANSITIONS

```css
--duration-basic: 150ms
--ease-basic: ease-out
--ease-cubic-enter: cubic-bezier(0, 0, 0.2, 1)
--ease-cubic-exit: cubic-bezier(0.4, 0, 1, 1)
--ease-cubic-move: cubic-bezier(0.4, 0, 0.2, 1)
```

---

## CLARITY WIDGET MIGRATION MAPPING

| Current CSS | SDK UI Equivalent |
|-------------|-------------------|
| `--text-primary` | `text-default` |
| `--text-secondary` | `text-secondary` |
| `--bg-primary` | `bg-surface` |
| `--bg-secondary` | `bg-surface-secondary` |
| `--bg-card` | `bg-surface` |
| `--border-color` | `border-default` |
| `.cluster-card` | `rounded-2xl border border-default bg-surface shadow-md p-4` |
| `.subcluster-card` | `rounded-lg border border-subtle bg-surface-secondary p-3` |
| `.priority-badge` | `<Badge color="secondary" variant="solid" size="sm">` |
| `.tag-pill` | `<Badge color="secondary" variant="soft" size="sm">` |
| `.item-count` | `<Badge color="secondary" variant="outline" size="sm">` |
| `.save-btn` | `<Button color="primary" variant="solid">` |
| `.modal-btn-cancel` | `<Button color="secondary" variant="outline">` |
