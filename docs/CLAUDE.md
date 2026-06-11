  # CLAUDE.md

## Design System
Always read `DESIGN.md` before writing any UI code.

## Agent Rules (enforced)

### Colours
  - ALWAYS use semantic color tokens — never hardcode hex values in widget code
  - ALWAYS implement ThemeData for both light and dark mode
  - ALWAYS resolve colours via Theme.of(context).colorScheme
  - Brand gradient is for splash/hero backgrounds ONLY — never buttons or cards
  - Chart data uses chart-palette colours; UI labels/headings use grey (on-surface-variant)

### Typography
  - ALWAYS use Poppins via google_fonts — never system fonts
  - NEVER hardcode font sizes — use type_scale tokens
  - Logo wordmark MUST be an image asset — never recreate RPM1 as a Text widget

### Layout
  - 12-column grid: 80px columns, 16px gutters, 16px outer margin
  - Max dashboard width: 1200px
  - All spacing in multiples of 8px only
  - ALWAYS use the 12-column grid (80px columns, 16px gutters, 16px outer margin)
  - Max dashboard width: 1200px
  - Header: 95px, KPI row: 88px, content: flexible
  - Important charts always sit top-left
  - Equal horizontal and vertical margins throughout

### Icons
  - Line style only — Light: #000000 | Dark: #FFFFFF
  - Minimum 48dp tap target on all interactive elements
  - Line style only — no filled icons
  - Light: rich-black | Dark: white
  - Minimum 48dp tap target

### Spacing
  - Multiples of 8px only — never magic numbers
  - Equal horizontal and vertical margins
  - No element within 16px of any screen edge

### Logo
  - ALWAYS use logo as an image asset — never render as text
  - NEVER modify, crop, distort, or recolour outside the approved colour list
  - In header bar: horizontal full-logo, left-aligned, 16px left margin

### Dashboard
  - Header: logo left | title centre-left | max 4 global filters right
  - KPI boxes: max 6, below header; if fewer than 6, right-align
  - Header filters are GLOBAL — they override all in-page filters
  - Chart card titles always use chart-heading-color (grey), never brand colour
  
### Gaps
  - If a component is not covered here, match the visual language (sm/md radius,
    brand-blue accents, Poppins, grey labels, outlined borders) and add:
    // DESIGN.md gap: [component name]
