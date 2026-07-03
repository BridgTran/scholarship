# OysterMatch Design System

> Extracted from `static/scholarship_search.html` and `static/scholarship_detail.html`.
> Reference this document when building new pages so the visual language stays consistent.

---

## 1. FONTS

### Font Family
No custom font is imported. Both pages use **Tailwind CSS's default system font stack**:

```
ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
"Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans",
sans-serif, "Apple Color Emoji", "Segoe UI Emoji"
```

There are no `<link>` tags to Google Fonts, no `@font-face` declarations, and no `font-family` overrides anywhere in either file.

### Font Sizes in Use

| Role | Tailwind class | Approx size |
|---|---|---|
| Hero heading (H1) | `text-4xl sm:text-5xl lg:text-6xl` | 36 → 48 → 60px |
| Page section heading (H2) | `text-xl` or `text-2xl` | 20–24px |
| Card title (H3) | `text-lg` | 18px |
| Body / description | `text-sm` | 14px |
| Small body | `text-xs` | 12px |
| Micro / badge text | `text-[10px]` or `text-[11px]` | 10–11px (arbitrary value) |
| Label / uppercase tags | `text-xs font-semibold uppercase tracking-wider` | 12px |
| Nav / button text | `text-sm font-medium` or `text-sm font-semibold` | 14px |

### Font Weights in Use
`font-medium` (500) · `font-semibold` (600) · `font-bold` (700)

---

## 2. COLOURS

No raw hex values appear anywhere. Every colour is a Tailwind utility class.
Hex values below are from the **Tailwind v3 default palette**.

### Primary — Blue (brand colour, buttons, links, focus rings)

| Tailwind class | Hex | Usage |
|---|---|---|
| `blue-50` | `#eff6ff` | Chip/filter panel backgrounds |
| `blue-100` | `#dbeafe` | Eligibility panel border, rings |
| `blue-200` | `#bfdbfe` | Filter pill borders, compare button border |
| `blue-500` | `#3b82f6` | Focus rings, input ring, live indicator dot |
| `blue-600` | `#2563eb` | Primary CTA buttons, logo, spinner, badge bg, links |
| `blue-700` | `#1d4ed8` | Text on blue tinted backgrounds, drawer counter |

### Secondary — Cyan (always paired with blue in gradients)

| Tailwind class | Hex | Usage |
|---|---|---|
| `cyan-50` | `#ecfeff` | Chip background (paired with blue-50) |
| `cyan-100` | `#cffafe` | Background blur blob |
| `cyan-400` | `#22d3ee` | Spinner border accent |
| `cyan-500` | `#06b6d4` | Gradient end — all CTA buttons and logo |

### Backgrounds

| Tailwind class | Hex | Usage |
|---|---|---|
| `white` | `#ffffff` | Cards, inputs, buttons |
| `gray-50` | `#f9fafb` | Page body gradient start, input bg |
| `blue-50/30` | `#eff6ff` at 30% | Hero background tint (overlay) |
| `purple-50/30` | `#faf5ff` at 30% | Hero background tint (overlay) |
| `blue-100/40` | `#dbeafe` at 40% | Decorative blur blob |
| `purple-100/40` | `#f3e8ff` at 40% | Decorative blur blob |
| `cyan-100/30` | `#cffafe` at 30% | Decorative blur blob |
| `white/80` | `#ffffff` at 80% | Glassmorphism cards |
| `white/90` | `#ffffff` at 90% | State panels (loading, empty, error) |
| `black/30` | `#000000` at 30% | Drawer backdrop |
| `black/50` | `#000000` at 50% | Modal backdrop |

### Text

| Tailwind class | Hex | Usage |
|---|---|---|
| `gray-900` | `#111827` | Primary headings, main content text |
| `gray-800` | `#1f2937` | Eligibility item text, comparison cell text |
| `gray-700` | `#374151` | Button text, semi-prominent labels |
| `gray-600` | `#4b5563` | Body copy, descriptions, metadata |
| `gray-500` | `#6b7280` | Muted labels, secondary info, timestamps |
| `gray-400` | `#9ca3af` | Icon fills, placeholder text, empty states |
| `white` | `#ffffff` | Text on coloured/gradient backgrounds |
| `blue-600` | `#2563eb` | Links, amounts in saved drawer |
| `blue-700` | `#1d4ed8` | Badge text on blue tinted bg |
| `green-600` | `#16a34a` | Apply link in comparison modal |

### Borders

| Tailwind class | Hex | Usage |
|---|---|---|
| `gray-100` | `#f3f4f6` | Inner dividers, card section separators |
| `gray-200` | `#e5e7eb` | Standard card/input borders |
| `gray-200/60` | `#e5e7eb` at 60% | Subtle card borders (glassmorphism) |
| `gray-300` | `#d1d5db` | Hover border on secondary buttons |
| `blue-100` | `#dbeafe` | Filter panel border, eligibility panel |
| `blue-200` | `#bfdbfe` | Filter pill borders |
| `slate-200` | `#e2e8f0` | "Open intake" / "Closed" badge borders |
| `dashed border-gray-300` | `#d1d5db` | Active filters empty state area |

### Badges & Pills

| Colour group | Background | Border | Text | Usage |
|---|---|---|---|---|
| Blue | `bg-blue-50` | `border-blue-100` | `text-blue-700` | Residency (International), active filter pills |
| Green | `bg-green-50` | `border-green-100` | `text-green-700` | Domestic/citizen residency, "Low Competition" |
| Purple | `bg-purple-50` | `border-purple-100` | `text-purple-700` | Degree level badges |
| Slate | `bg-slate-50` | `border-slate-200` | `text-slate-600` | Location badges, "Open intake" / "Closed" |
| Amber | `bg-amber-50` | `border-amber-100` | `text-amber-700` | Merit-Based type, "Competitive" |
| Rose | `bg-rose-50` | `border-rose-200` | `text-rose-700` | Urgency ≤7 days |
| Orange | `bg-orange-50` | `border-orange-200` | `text-orange-700` | Urgency ≤30 days |

### Status Colours

| Status | Tailwind classes | Hex values | Usage |
|---|---|---|---|
| Error | `bg-red-50 border-red-200 text-red-600` | `#fef2f2 / #fecaca / #dc2626` | Error state panels |
| Warning (deadline) | `bg-amber-50 border-amber-200 text-amber-600` | `#fffbeb / #fde68a / #d97706` | Deadline alert banner |
| Urgent ≤7 days | `text-rose-600 bg-rose-50 border-rose-200` | `#e11d48 / #fff1f2 / #fecdd3` | Deadline countdown |
| Urgent ≤30 days | `text-orange-600 bg-orange-50 border-orange-200` | `#ea580c / #fff7ed / #fed7aa` | Deadline countdown |
| Expired/closed | `text-slate-500 bg-white border-slate-200` | `#64748b / #ffffff / #e2e8f0` | Closed badges |
| Success/money | `text-emerald-600 bg-emerald-50 border-emerald-100` | `#059669 / #ecfdf5 / #d1fae5` | Funding amount display |
| Saved/bookmarked | `text-amber-500 bg-amber-50 border-amber-200` | `#f59e0b / #fffbeb / #fde68a` | Bookmark active state |
| Comparison diff | `bg-amber-50 text-amber-700` | `#fffbeb / #b45309` | Differing rows in comparison table |

---

## 3. CSS FRAMEWORK

### Tailwind CSS — Play CDN (runtime)

```html
<script src="https://cdn.tailwindcss.com"></script>
```

- **Version:** Tailwind CSS v3 (Play CDN, latest at load time)
- **CDN type:** Runtime — classes are generated on-the-fly in the browser. No build step.
- **Custom config:** None. There is no `tailwind.config` script block in either page.
- **Arbitrary values used:** `text-[10px]`, `text-[11px]` (micro badge text)

> **For new pages:** Add the same `<script>` tag in `<head>`. If you need custom colours or fonts later, add a config block directly after it:
> ```html
> <script>
>   tailwind.config = {
>     theme: {
>       extend: {
>         colors: { /* custom additions here */ }
>       }
>     }
>   }
> </script>
> ```

---

## 4. COMPONENTS

### 4.1 Primary Button

Used for: "Find Scholarships", "Apply for This Scholarship", "Reset All Filters"

```html
<button class="inline-flex items-center justify-center rounded-lg
               bg-gradient-to-r from-blue-600 to-cyan-500
               px-8 py-4
               text-sm font-semibold text-white
               shadow-lg shadow-blue-500/25
               transition-all
               hover:shadow-xl hover:shadow-blue-500/30
               focus-visible:outline focus-visible:outline-2
               focus-visible:outline-offset-2 focus-visible:outline-blue-600
               disabled:opacity-70 disabled:cursor-not-allowed">
  Find Scholarships
</button>
```

**With leading icon:**
```html
<button class="inline-flex items-center justify-center rounded-lg
               bg-gradient-to-r from-blue-600 to-cyan-500
               px-8 py-4 text-sm font-semibold text-white
               shadow-lg shadow-blue-500/25 transition-all
               hover:shadow-xl hover:shadow-blue-500/30">
  <svg class="mr-2 h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>
  Find Scholarships
</button>
```

---

### 4.2 Secondary Button

**Outline style** (used for "Retry Search", "Back to Search", nav items):
```html
<button class="inline-flex items-center justify-center rounded-xl
               border border-gray-300 bg-white
               px-6 py-3.5
               text-sm font-medium text-gray-700
               shadow-sm
               transition-all hover:bg-gray-50 hover:shadow-md">
  Retry Search
</button>
```

**Small outline style** (used in header nav, filter toggles):
```html
<a href="/page" class="rounded-lg border border-gray-200 bg-white
                        px-4 py-2
                        text-sm font-medium text-gray-700
                        shadow-sm transition-all
                        hover:border-gray-300 hover:shadow-md">
  Explore Scholarships
</a>
```

**Ghost / text style** (used for "Clear all filters", "read more"):
```html
<button class="inline-flex items-center gap-1.5 rounded-lg
               border border-gray-200 bg-white
               px-3 py-1.5
               text-xs font-semibold text-gray-500
               transition-colors
               hover:border-red-200 hover:bg-red-50 hover:text-red-600">
  ✕ Clear all filters
</button>
```

---

### 4.3 Scholarship Card

The core list item. Includes a coloured left-accent bar, hover ring, and action row.

```html
<div class="group relative overflow-hidden rounded-xl
            border border-gray-200/60 bg-white
            p-6
            transition-all duration-200
            hover:border-gray-300 hover:shadow-lg
            backdrop-blur-sm
            cursor-pointer">

  <!-- Left accent bar (decorative, non-interactive) -->
  <div class="absolute left-0 top-0 bottom-0 w-1
              bg-gradient-to-b from-blue-500/20 to-cyan-400/20">
  </div>

  <div class="relative pl-4">

    <!-- Title + org row -->
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div class="space-y-2">
        <h3 class="text-lg font-semibold text-gray-900
                   transition-colors group-hover:text-blue-600">
          Scholarship Title
        </h3>
        <div class="inline-flex items-center gap-1.5 text-sm font-medium text-gray-800">
          Organisation Name
        </div>
        <!-- Badge row (see Section 4.4) -->
        <div class="mt-2 flex flex-wrap gap-1">
          <!-- badges here -->
        </div>
      </div>
      <!-- Award amount -->
      <div class="text-right">
        <p class="text-xs font-medium text-gray-900">$10,000</p>
        <p class="text-xs text-gray-500">Award</p>
      </div>
    </div>

    <!-- Description (2-line clamp) -->
    <p class="mt-3 text-sm text-gray-700 leading-relaxed
              overflow-hidden"
       style="display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;">
      Scholarship description goes here...
    </p>

    <!-- Metadata row -->
    <div class="mt-4 flex flex-wrap items-center gap-4 text-xs text-gray-500">
      <div class="flex items-center gap-1.5">
        <!-- calendar icon -->
        <span class="font-medium">Apply by:</span> 01 September 2025
      </div>
    </div>

    <!-- Bottom action row -->
    <div class="mt-4 flex items-center justify-between pt-4 border-t border-gray-100">
      <!-- Urgency badge (see Section 4.4) -->
      <div class="flex items-center gap-2">
        <!-- urgency badge here -->
      </div>
      <!-- Action buttons -->
      <div class="flex items-center gap-3">
        <!-- Bookmark -->
        <button class="inline-flex items-center justify-center rounded-lg
                       border border-gray-200 bg-white p-2
                       text-gray-400 transition-colors
                       hover:bg-amber-50 hover:text-amber-500
                       active:bg-amber-100">
          <!-- bookmark icon -->
        </button>
        <!-- Compare -->
        <button class="inline-flex min-w-[88px] items-center justify-center gap-1 rounded-lg
                       border border-blue-200 bg-white
                       px-3 py-2 text-xs font-medium text-blue-600
                       transition-colors hover:bg-blue-50 active:bg-blue-100">
          + Compare
        </button>
        <!-- View -->
        <button class="group/view inline-flex items-center gap-1 rounded-lg
                       border border-gray-300 bg-white
                       px-3 py-2 text-xs font-medium text-gray-700
                       transition-colors hover:bg-gray-50 active:bg-gray-100">
          View
          <!-- chevron-right icon -->
        </button>
      </div>
    </div>

  </div>

  <!-- Hover ring overlay (pointer-events-none so it never blocks clicks) -->
  <div class="pointer-events-none absolute inset-0 rounded-xl
              ring-1 ring-blue-500/10
              opacity-0 transition-opacity duration-200
              group-hover:opacity-100">
  </div>

</div>
```

---

### 4.4 Badges & Pills

**Eligibility badge (inline, coloured by type):**
```html
<!-- Blue — residency/international -->
<span class="inline-flex items-center gap-0.5 rounded-full border
             bg-blue-50 border-blue-100 text-blue-700
             px-2 py-0.5 text-[10px] font-medium">
  🌏 International
</span>

<!-- Purple — degree level -->
<span class="inline-flex items-center gap-0.5 rounded-full border
             bg-purple-50 border-purple-100 text-purple-700
             px-2 py-0.5 text-[10px] font-medium">
  🎓 Undergrad
</span>

<!-- Amber — merit-based / competitive -->
<span class="inline-flex items-center gap-0.5 rounded-full border
             bg-amber-50 border-amber-100 text-amber-700
             px-2 py-0.5 text-[10px] font-medium">
  🏆 Merit-Based
</span>

<!-- Green — domestic / low competition -->
<span class="inline-flex items-center gap-0.5 rounded-full border
             bg-green-50 border-green-100 text-green-700
             px-2 py-0.5 text-[10px] font-medium">
  🇦🇺 Domestic
</span>

<!-- Slate — location, "open intake", "closed" -->
<span class="inline-flex items-center gap-0.5 rounded-full border
             bg-slate-50 border-slate-200 text-slate-600
             px-2 py-0.5 text-[10px] font-medium">
  📍 NSW
</span>
```

**Urgency deadline badge:**
```html
<!-- ≤7 days — rose -->
<span class="inline-flex items-center gap-2 rounded-full border
             border-rose-200 bg-rose-50
             px-3 py-1 text-xs font-semibold text-rose-700">
  ⚠ 3 days left
</span>

<!-- ≤30 days — orange -->
<span class="inline-flex items-center gap-2 rounded-full border
             border-orange-200 bg-orange-50
             px-3 py-1 text-xs font-semibold text-orange-700">
  ⚠ 18 days left
</span>

<!-- >30 days or open — slate -->
<span class="inline-flex items-center gap-2 rounded-full border
             border-slate-200 bg-white
             px-3 py-1 text-xs font-semibold text-slate-600">
  45 days left
</span>

<!-- Open intake / no deadline -->
<span class="inline-flex items-center gap-2 rounded-full border
             border-slate-200 bg-white
             px-3 py-1 text-xs font-semibold text-slate-500">
  Open intake
</span>
```

**Active filter pill (removable):**
```html
<span class="inline-flex items-center gap-1 rounded-full border
             border-blue-200 bg-blue-50
             pl-3 pr-1.5 py-1
             text-[11px] font-semibold text-blue-700 shadow-sm">
  <span>Level: Undergraduate</span>
  <button type="button"
          class="ml-0.5 inline-flex h-3.5 w-3.5 items-center justify-center
                 rounded-full text-blue-400
                 transition-colors hover:bg-blue-200 hover:text-blue-800">
    ×
  </button>
</span>
```

**Hero label pill (section announcer):**
```html
<div class="inline-flex items-center rounded-full
            bg-gradient-to-r from-blue-50 to-cyan-50
            px-4 py-2
            text-xs font-semibold uppercase tracking-wider text-blue-700
            ring-1 ring-inset ring-blue-100">
  Premium Scholarship Platform
</div>
```

---

### 4.5 Input Field

**Search bar (with icon prefix):**
```html
<div class="relative flex-1">
  <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
    <svg class="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  </div>
  <input
    type="text"
    placeholder="Try 'engineering scholarships'..."
    class="block w-full rounded-lg border-0 bg-gray-50
           py-4 pl-12 pr-4
           text-gray-900
           shadow-sm ring-1 ring-inset ring-gray-200
           placeholder:text-gray-400
           focus:ring-2 focus:ring-inset focus:ring-blue-500
           sm:text-sm"
  />
</div>
```

**Checkbox (filter option):**
```html
<input
  type="checkbox"
  class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
/>
```

**Industry checkbox (slate variant):**
```html
<input
  type="checkbox"
  class="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-900"
/>
```

---

### 4.6 Dropdown / Select

```html
<select class="block w-full rounded-lg border-gray-200 bg-white
               py-3 pl-4 pr-10
               text-sm text-gray-900
               shadow-sm ring-1 ring-inset ring-gray-200
               focus:ring-2 focus:ring-blue-500">
  <option value="">Any amount</option>
  <option value="1000-5000">$1,000 – $5,000</option>
</select>
```

**Smaller variant (advanced filters, results header sort):**
```html
<select class="block w-full rounded-lg border-gray-200 bg-white
               py-2.5 pl-4 pr-10
               text-sm text-gray-900
               shadow-sm ring-1 ring-inset ring-gray-200
               focus:ring-2 focus:ring-blue-500">
  <option>All types</option>
</select>
```

---

### 4.7 Section / Panel Headings

**Page hero H1 with gradient accent:**
```html
<h1 class="mt-6 text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl lg:text-6xl">
  Discover Your<br class="hidden sm:block" />
  <span class="bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">
    Funding Future
  </span>
</h1>
```

**Results section H2 with gradient word:**
```html
<h2 class="text-xl font-bold tracking-tight text-gray-900">
  Your <span class="bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">
    Personalised
  </span> Results
</h2>
```

**Card section H2 (plain):**
```html
<h2 class="text-xl font-bold text-gray-900">About This Scholarship</h2>
```

**Uppercase section label (used above selects and filter groups):**
```html
<label class="mb-2 block text-xs font-semibold uppercase tracking-wider text-gray-500">
  Funding Amount
</label>
```

---

### 4.8 Page Layout Wrapper

Copy this shell for any new page:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Page Title</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-b from-gray-50 to-white text-gray-900 antialiased">

  <div class="relative min-h-screen overflow-hidden bg-gradient-to-b from-gray-50 to-white">

    <!-- Tinted background overlay -->
    <div class="absolute inset-0 bg-gradient-to-br from-blue-50/30 via-transparent to-purple-50/30"></div>

    <!-- Decorative blur blobs -->
    <div class="absolute inset-0 overflow-hidden">
      <div class="absolute -top-40 -right-40 h-80 w-80 rounded-full bg-blue-100/40 blur-3xl"></div>
      <div class="absolute top-60 -left-20 h-72 w-72 rounded-full bg-purple-100/40 blur-3xl"></div>
      <div class="absolute bottom-0 right-1/4 h-64 w-64 rounded-full bg-cyan-100/30 blur-3xl"></div>
    </div>

    <div class="relative">

      <!-- Header (glassmorphism, sticky) -->
      <header class="sticky top-0 z-50 border-b border-gray-200/50 bg-white/80 backdrop-blur-xl">
        <div class="mx-auto max-w-7xl px-6 lg:px-8">
          <div class="flex h-16 items-center justify-between">
            <!-- Logo -->
            <div class="flex items-center space-x-3">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg
                          bg-gradient-to-br from-blue-600 to-cyan-500">
                <!-- icon -->
              </div>
              <span class="text-lg font-semibold text-gray-900">OysterMatch</span>
            </div>
            <!-- Nav actions -->
            <div class="flex items-center gap-3">
              <!-- nav buttons here -->
            </div>
          </div>
        </div>
      </header>

      <!-- Main content area -->
      <main class="mx-auto max-w-7xl px-6 py-12 lg:px-8">
        <!-- page content here -->
      </main>

    </div>
  </div>

</body>
</html>
```

**Narrower content width** (used on detail page for reading-focused layouts):
```html
<main class="mx-auto max-w-4xl px-6 py-12 lg:px-8">
```

---

### 4.9 Content Card / Panel

Used for the search form wrapper, loading state, empty state:

```html
<div class="rounded-2xl border border-gray-200/60 bg-white/80
            p-8 lg:p-10
            shadow-xl backdrop-blur-sm">
  <!-- card content -->
</div>
```

**Coloured filter panel (blue tint):**
```html
<div class="rounded-lg border border-blue-100 bg-blue-50/40 p-6">
  <!-- content -->
</div>
```

**Toast notification:**
```html
<div class="fixed bottom-24 left-1/2 z-50 -translate-x-1/2">
  <div class="flex items-center gap-2 rounded-xl bg-gray-900
              px-4 py-2.5 text-sm font-medium text-white shadow-xl">
    <span>⚠️</span>
    <span>Notification message here.</span>
  </div>
</div>
```

---

## 5. SPACING & LAYOUT

### Container Max Widths

| Context | Class | Pixel width |
|---|---|---|
| Full-width pages (search, index) | `max-w-7xl` | 1280px |
| Reading-focused pages (detail) | `max-w-4xl` | 896px |
| Modals / drawers | `max-w-5xl` | 1024px |
| Drawer panel | `max-w-sm` | 384px |

### Horizontal Padding Pattern

All containers use responsive horizontal padding:
```
px-6 lg:px-8   →   24px (mobile) → 32px (lg+)
```

### Vertical Padding Pattern

| Element | Class | Value |
|---|---|---|
| Page top/bottom | `py-12` | 48px |
| Card padding (standard) | `p-6` | 24px |
| Card padding (large) | `p-8` | 32px |
| Card padding (xl, lg breakpoint) | `lg:p-10` | 40px |
| Header height | `h-16` | 64px |
| Section bottom margin | `mb-12` | 48px |
| Section bottom margin (cards) | `mb-16` | 64px |

### Gap Patterns

| Usage | Class | Value |
|---|---|---|
| Tight (badge rows, icon+text) | `gap-1`, `gap-1.5`, `gap-2` | 4–8px |
| Standard (button groups, metadata) | `gap-3`, `gap-4` | 12–16px |
| Form field groups | `gap-6` | 24px |
| Major sections (cards stacked) | `gap-8`, `space-y-8` | 32px |
| Filter grid columns | `grid-cols-1 sm:grid-cols-2 lg:grid-cols-5` | responsive |
| Advanced filter grid | `grid-cols-1 md:grid-cols-3` | responsive |

### Z-Index Layers

| Element | Class | Value |
|---|---|---|
| Comparison tray | `z-40` | 40 |
| Drawer backdrop | `z-40` | 40 |
| Sticky header | `z-50` | 50 |
| Drawer panel | `z-50` | 50 |
| Toast notification | `z-50` | 50 |
| Modal | `z-50` | 50 |

---

## 6. GRADIENT RECIPES

These gradient combinations are used throughout and define the brand feel:

```
/* Primary CTA button */
bg-gradient-to-r from-blue-600 to-cyan-500

/* Logo icon */
bg-gradient-to-br from-blue-600 to-cyan-500

/* Hero text accent (clip-text) */
bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent

/* Page background */
bg-gradient-to-b from-gray-50 to-white

/* Background tint overlay */
bg-gradient-to-br from-blue-50/30 via-transparent to-purple-50/30

/* Card left accent bar */
bg-gradient-to-b from-blue-500/20 to-cyan-400/20

/* Hero banner (detail page) */
bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-600

/* Error state icon bg (search page) */
bg-gradient-to-r from-red-50 to-pink-50
```

---

## 7. INTERACTION PATTERNS

### Hover Effects
- Cards: `hover:border-gray-300 hover:shadow-lg` — border darkens, shadow appears
- Cards: `group-hover:text-blue-600` — title shifts to brand blue
- Primary buttons: `hover:shadow-xl hover:shadow-blue-500/30` — shadow intensifies
- Secondary buttons: `hover:bg-gray-50 hover:shadow-md`
- Icon buttons: `hover:bg-amber-50 hover:text-amber-500` (bookmark)
- Links: `hover:text-white`, `hover:text-blue-700`

### Transitions
- General: `transition-all` or `transition-colors` (Tailwind default 150ms)
- Card hover: `transition-all duration-200`
- Drawer/tray slide: `transition: transform 0.3s ease` (inline style)
- Toggle icon rotate: `transition-transform duration-200`

### Focus Styles
```
focus:ring-2 focus:ring-inset focus:ring-blue-500        /* inputs/selects */
focus-visible:outline focus-visible:outline-2
focus-visible:outline-offset-2 focus-visible:outline-blue-600  /* buttons */
```

### Disabled State
```
disabled:opacity-70 disabled:cursor-not-allowed
```
