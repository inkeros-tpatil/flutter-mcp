name: RPM1 Design System
version: 1.0.0
brand: RPM1 — Reps. Payments. Management.
platform: Flutter
theme_modes: [light, dark]
design_token_format: Flutter ThemeData + ColorScheme
grid: 12-column
max-width: 1200px

logo:
  name: RPM1
  tagline: "REPS. PAYMENTS. MANAGEMENT."
  style: "Bold italic condensed wordmark — all caps"
  superscript: "¹ — styled as part of the wordmark, not a footnote"

  variants:
    full-logo:   "RPM1 wordmark + tagline below"
    logo-only:   "RPM1 wordmark without tagline"

  approved-colors:
    - black on gradient background
    - white on gradient background
    - white on black background
    - brand-blue (#0877fa) on white
    - brand-yellow (#f9e960) on white
    - steel-blue (#699dd6) on white
    - mint (#9fe8bf) on white
    - lime (#d4e670) on white

  incorrect-use:
    - do not crop the logo
    - do not distort or stretch
    - do not rescale individual components independently
    - do not change letterforms or fonts
    - do not overprint elements on top of logo
    - do not use logo as background pattern
    - do not place on photographic background without sufficient contrast
    - do not place logo inline within body text
    - do not use unofficial or unapproved color combinations
    - always use the logo as a complete lockup — never recreate it in code

  clear-space: "Maintain clear space equal to the height of the R on all sides"

primitives:
  brand-blue:       "#0877FA"   # Primary — electric blue
  steel-blue:       "#699DD6"   # Secondary blue — softer
  mint:             "#9FE8BF"   # Green-mint accent
  lime-yellow:      "#D4E670"   # Yellow-green accent
  solar-yellow:     "#F9E960"   # Bright yellow accent
  rich-black:       "#000000"   # CMYK 60/40/40/100
  white:            "#FFFFFF"

  brand-gradient: "linear-gradient(135deg, #0877FA 0%, #9FE8BF 50%, #F9E960 100%)"

  neutral-50:       "#F9FAFB"
  neutral-100:      "#F3F4F6"
  neutral-200:      "#E5E7EB"
  neutral-300:      "#D1D5DB"
  neutral-400:      "#9CA3AF"
  neutral-500:      "#6B7280"
  neutral-600:      "#4B5563"
  neutral-700:      "#374151"
  neutral-800:      "#1F2937"
  neutral-900:      "#111827"
  neutral-950:      "#0A0F1A"

light:
  background:             "#FFFFFF"
  surface:                "#FFFFFF"
  surface-variant:        "#F3F4F6"
  surface-tint:           "#EBF4FF"

  on-background:          "#000000"
  on-surface:             "#111827"
  on-surface-variant:     "#6B7280"
  on-surface-disabled:    "#D1D5DB"

  primary:                "#0877FA"
  primary-container:      "#EBF4FF"
  on-primary:             "#FFFFFF"
  on-primary-container:   "#003580"

  secondary:              "#699DD6"
  secondary-container:    "#DDEEFF"
  on-secondary:           "#FFFFFF"
  on-secondary-container: "#1A3A5C"

  accent-mint:            "#9FE8BF"
  accent-lime:            "#D4E670"
  accent-yellow:          "#F9E960"

  error:                  "#EF4444"
  error-container:        "#FEE2E2"
  on-error:               "#FFFFFF"
  on-error-container:     "#B91C1C"

  success:                "#22C55E"
  success-container:      "#DCFCE7"
  on-success:             "#FFFFFF"
  on-success-container:   "#15803D"

  warning:                "#F9E960"
  warning-container:      "#FEFCE8"
  on-warning:             "#000000"
  on-warning-container:   "#713F12"

  outline:                "#E5E7EB"
  outline-variant:        "#F3F4F6"
  section-divider:        "#0877FA"

  scrim:                  "rgba(0, 0, 0, 0.32)"
  shadow:                 "rgba(8, 119, 250, 0.08)"

  header-background:      "#FFFFFF"
  sidebar-background:     "#FFFFFF"
  kpi-box-background:     "#F3F4F6"
  chart-heading-color:    "#6B7280"
  page-heading-color:     "#374151"

dark:
  background:             "#000000"
  surface:                "#0A0F1A"
  surface-variant:        "#111827"
  surface-tint:           "#001A3D"

  on-background:          "#FFFFFF"
  on-surface:             "#F3F4F6"
  on-surface-variant:     "#9CA3AF"
  on-surface-disabled:    "#4B5563"

  primary:                "#4DA3FF"
  primary-container:      "#003580"
  on-primary:             "#000000"
  on-primary-container:   "#BFD9FF"

  secondary:              "#8BB8E8"
  secondary-container:    "#1A3A5C"
  on-secondary:           "#000000"
  on-secondary-container: "#DDEEFF"

  accent-mint:            "#9FE8BF"
  accent-lime:            "#D4E670"
  accent-yellow:          "#F9E960"

  error:                  "#F87171"
  error-container:        "#7F1D1D"
  on-error:               "#000000"
  on-error-container:     "#FECACA"

  success:                "#4ADE80"
  success-container:      "#14532D"
  on-success:             "#000000"
  on-success-container:   "#BBF7D0"

  warning:                "#F9E960"
  warning-container:      "#3D3000"
  on-warning:             "#000000"
  on-warning-container:   "#FEF08A"

  outline:                "#374151"
  outline-variant:        "#1F2937"
  section-divider:        "#0877FA"

  scrim:                  "rgba(0, 0, 0, 0.64)"
  shadow:                 "rgba(8, 119, 250, 0.16)"

  header-background:      "#000000"
  sidebar-background:     "#0A0F1A"
  kpi-box-background:     "#111827"
  chart-heading-color:    "#9CA3AF"
  page-heading-color:     "#D1D5DB"

# Use in this order for multi-series charts
chart-palette:
  1: "#0877FA"   # brand-blue
  2: "#9FE8BF"   # mint
  3: "#D4E670"   # lime-yellow
  4: "#F9E960"   # solar-yellow
  5: "#699DD6"   # steel-blue

rules:
  - Chart data colours must be vibrant and stand out against background
  - Chart headings, axis labels: use on-surface-variant (grey)
  - Never use unofficial colours in charts

fonts:
  primary:  "Poppins"
  fallback: ["Helvetica Neue", "Arial", "sans-serif"]
  package:  "google_fonts"
  weights:
    light:   300
    regular: 400
    bold:    700
    black:   900

  logo-font:
    description: "RPM1 wordmark uses a custom condensed italic typeface. DO NOT replicate in UI code. Always use the logo image asset."

type_scale:

  display-large:
    font: Poppins
    size: 48
    weight: 700
    line-height: 56
    letter-spacing: -0.5
    usage: "Hero screens, splash"

  display-medium:
    font: Poppins
    size: 36
    weight: 700
    line-height: 44
    letter-spacing: -0.25
    usage: "Dashboard hero headings"

  headline-large:
    font: Poppins
    size: 28
    weight: 700
    line-height: 36
    usage: "Screen-level titles"

  headline-medium:
    font: Poppins
    size: 24
    weight: 700
    line-height: 32
    usage: "Section titles, modal headers"

  headline-small:
    font: Poppins
    size: 20
    weight: 700
    line-height: 28
    usage: "Card titles, KPI values"

  title-large:
    font: Poppins
    size: 18
    weight: 700
    line-height: 28
    usage: "AppBar titles"

  title-medium:
    font: Poppins
    size: 16
    weight: 700
    line-height: 24
    letter-spacing: 0.15
    usage: "Dashboard name, page title in header bar"

  title-small:
    font: Poppins
    size: 14
    weight: 700
    line-height: 20
    letter-spacing: 0.1
    usage: "Tab labels, chart page titles"

  body-large:
    font: Poppins
    size: 16
    weight: 400
    line-height: 24
    letter-spacing: 0.5
    usage: "Primary body text, table content"

  body-medium:
    font: Poppins
    size: 14
    weight: 400
    line-height: 20
    letter-spacing: 0.25
    usage: "Secondary body, list items, filter labels"

  body-small:
    font: Poppins
    size: 12
    weight: 400
    line-height: 16
    letter-spacing: 0.4
    usage: "Captions, helper text"

  label-large:
    font: Poppins
    size: 14
    weight: 700
    line-height: 20
    letter-spacing: 0.1
    usage: "Button labels, KPI labels"

  label-medium:
    font: Poppins
    size: 12
    weight: 700
    line-height: 16
    letter-spacing: 0.5
    usage: "Tags, badge text, filter labels"

  label-small:
    font: Poppins
    size: 10
    weight: 300
    line-height: 14
    letter-spacing: 0.5
    usage: "Timestamps, axis ticks, fine print"

  tagline:
    font: Poppins
    size: 11
    weight: 700
    line-height: 16
    letter-spacing: 2.0
    transform: uppercase
    usage: "REPS. PAYMENTS. MANAGEMENT. — brand display only"

# Base unit: 8px
spacing:
  0:   0
  1:   8     # xs
  2:   16    # sm — default padding, filter margin
  3:   24    # md — card padding
  4:   32    # lg — outer margin bottom
  5:   40
  6:   48
  8:   64
  10:  80
  12:  96

layout:
  max-width:              1200    # px
  header-height:          95      # px
  kpi-row-height:         88      # px
  content-height:         700     # px flexible
  outer-margin-bottom:    32      # px
  outer-margin-sides:     16      # px
  column-width:           80      # px — 1 of 12 columns
  column-count:           12
  column-gutter:          16      # px
  card-padding:           16      # px
  section-gap:            16      # px between chart cards

radius:
  none: 0
  xs:   2      # table highlights
  sm:   4      # KPI boxes, filter dropdowns, buttons
  md:   8      # cards, chart containers
  lg:   12     # modals, bottom sheets
  xl:   16     # large feature cards
  full: 9999   # status dots, avatar indicators only

elevation:
  0:
    shadow: none
    usage: "flat — KPI boxes, table rows"
  1:
    shadow: "0 1px 3px {shadow}"
    usage: "cards, chart containers"
  2:
    shadow: "0 2px 8px {shadow}"
    usage: "dropdowns, filter menus"
  3:
    shadow: "0 4px 16px {shadow}"
    usage: "header bar scrolled"
  4:
    shadow: "0 8px 24px {shadow}"
    usage: "modals, dialogs"

grid:
  columns:       12
  column-width:  80px
  gutter:        16px
  outer-margin:  16px
  max-width:     1200px

  component-width-formula: "(columns × 80) + ((columns - 1) × 16)"
  examples:
    3-col:  272px
    6-col:  560px
    12-col: 1136px

  rules:
    - All box elements use widths that are multiples of 1 column (80px) + gutter
    - All charts must be aligned vertically and horizontally
    - Keep horizontal and vertical margins equal

dashboard:

  header-bar:
    height: 95px
    background: header-background
    layout: "logo LEFT | title CENTER-LEFT | global-filters RIGHT"
    logo:
      position: left
      variant: horizontal-full-logo (image asset)
      left-margin: 16px
    title:
      style: title-medium
      color: on-surface
      line1: "Dashboard Name"
      line2: "Page Title"
    filters:
      count-max: 4
      type: dropdown
      alignment: right
      right-margin: "same px as logo left margin"
      note: "GLOBAL — override all in-page filters"

  kpi-boxes:
    position: "below header, above chart area"
    height: 88px
    count-max: 6
    alignment: "fewer than 6 → right-align for sidebar balance"
    background: kpi-box-background
    border: "1dp solid outline"
    radius: sm
    padding: 16
    label-style: label-medium
    label-color: on-surface-variant
    value-style: headline-small
    value-color: on-surface
    note: "top-level dashboards only"

  chart-area:
    height: flexible
    card:
      background: surface
      border: "1dp solid outline"
      radius: md
      padding: 16
      elevation: 1
      title-style: title-small
      title-color: chart-heading-color
    rules:
      - Important charts sit top-left (noticed first)
      - Distribute visual weight — do not cluster heavy charts
      - All charts aligned vertically and horizontally

  sidebar:
    background: sidebar-background
    border-right: "1dp solid outline"
    item-style: body-medium
    item-border: "1dp solid outline"
    item-radius: sm
    item-padding: "12 16"
    filter-label-style: label-medium

section-heading:
  text-style: label-large
  text-transform: uppercase
  color: on-surface
  letter-spacing: 1.5
  underline:
    color: "#0877FA"    # brand-blue — both modes
    height: 2dp
    width: "~30% of heading width"
    margin-top: 4dp

icons:
  style: "Line icons — clean minimal stroke"
  color-light: "#000000"
  color-dark:  "#FFFFFF"
  sizes:
    sm: 16
    md: 20
    lg: 24
    xl: 32
  min-tap-target: 48dp
  rules:
    - Use line (not filled) icons consistently
    - Light mode: rich-black; Dark mode: white
    - Never mix icon styles

buttons:

  primary:
    background: primary
    foreground: on-primary
    border: none
    radius: sm
    padding: "12 24"
    text-style: label-large
    height: 48
    disabled:
      background: "on-surface @ 12% opacity"
      foreground: "on-surface @ 38% opacity"

  secondary:
    background: transparent
    foreground: primary
    border: "1.5dp solid primary"
    radius: sm
    padding: "12 24"
    text-style: label-large
    height: 48
    disabled:
      border: "on-surface @ 12% opacity"
      foreground: "on-surface @ 38% opacity"

  ghost:
    background: transparent
    foreground: primary
    border: none
    radius: sm
    padding: "12 16"
    text-style: label-large
    height: 48

  filter-dropdown:
    background: surface
    foreground: on-surface
    border: "1dp solid outline"
    radius: sm
    height: 36
    padding: "0 12"
    trailing-icon: "chevron-down 16dp"
    text-style: label-medium
    focused-border: "1.5dp solid primary"

gradients:
  brand-gradient:
    value: "linear-gradient(135deg, #0877FA 0%, #9FE8BF 50%, #F9E960 100%)"
    approved-for:
      - Splash screen background
      - Hero / onboarding backgrounds
      - Logo carrier backgrounds
    never-use-for:
      - Button backgrounds
      - Card backgrounds in dashboard
      - Text fills (no gradient text)

motion:
  duration:
    fast:     150ms
    standard: 250ms
    moderate: 350ms
    slow:     500ms

  easing:
    enter:    Curves.easeOut
    exit:     Curves.easeIn
    standard: Curves.easeInOut

  transitions:
    page:     fade-through, standard
    modal:    slide-up + fade, moderate
    dropdown: fade + scale 0.95→1.0, fast
    kpi:      count-up on first load, slow

  rules:
    - Always check MediaQuery.disableAnimations — skip all animations if true
    - Charts animate in on first load only, not on every filter change

accessibility:
  min-tap-target:    48dp
  min-contrast-text: 4.5
  min-contrast-ui:   3.0
  focus-color:       primary
  focus-width:       2dp
  text-scale-max:    1.3
  reduce-motion:     respect MediaQuery.disableAnimations

breakpoints:
  compact:   "0 – 599dp"     # Mobile — bottom-nav
  medium:    "600 – 1199dp"  # Tablet — nav-rail
  expanded:  "1200dp+"       # Desktop — sidebar (primary dashboard target)

compact:
  columns: 4
  margin: 16
  kpi: horizontal scroll

medium:
  columns: 8
  margin: 16
  kpi: 2-column grid

expanded:
  columns: 12
  margin: 16
  max-width: 1200px
  kpi: full-width row max 6

