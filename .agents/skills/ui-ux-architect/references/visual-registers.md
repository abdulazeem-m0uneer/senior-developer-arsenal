# Visual Registers: Selection Heuristics and Concrete Rules

Adapted from nextlevelbuilder/ui-ux-pro-max-skill (MIT) `styles.csv`, `products.csv`; taste-skill (MIT) colour.md.

A register is a named, bounded set of CSS decisions. Pick one per product, write it in the brief, and do not blend. Every register still passes the 10 gates; "accessibility risk" below says how much extra contrast and focus work the register demands.

---

## 1. Selection by Product Type

| Product | First choice | Fallback | Do not use |
| :--- | :--- | :--- | :--- |
| SaaS / B2B tools, docs, admin | Swiss Minimal | Flat, Soft Depth | Glass, Neumorphic, Brutalist |
| Data-dense dashboards, fintech, ops | Dense Dashboard (+ Dark Neutral if long sessions) | Swiss Minimal | Bento, Glass, Editorial |
| Government, healthcare, education, legal | Swiss Minimal with AA+ contrast | Flat | Anything with blur, glow, or low-contrast depth |
| Consumer e-commerce | Flat with saturated accents | Bento for feature pages | Dense Dashboard, Brutalist |
| Luxury, fashion, architecture, portfolio | Exaggerated Minimal | Editorial | Flat (reads cheap), Neubrutal |
| Publishing, long-form, blogs | Editorial | E-Ink / Paper | Dense Dashboard, Glass |
| Developer tools, infra, CLI companions | Swiss Minimal or Dark Neutral | Neubrutal (indie) | Organic, Glass |
| Creative agency, youth, events | Neubrutal, Bento | Flat with bold colour | Swiss Minimal (anonymous) |
| Wellness, sustainability, food | Organic | Soft Depth | Dark Neutral, Brutalist |
| Reading / writing / focus apps | E-Ink / Paper | Swiss Minimal | Motion-heavy anything |

Rule: match the register to the audience's tolerance for ornament and the session length. Long daily sessions want quiet (Swiss, Dense, Dark Neutral). One-visit marketing can afford one loud register.

## 2. Register Definitions

Each lists: tokens to set, effects allowed, accessibility risk, and the first thing that goes wrong.

**Swiss Minimal**
- `--radius: 0-4px; --shadow: none; --accent: one hue only; grid 12 col; sans only`.
- Hover 200-250ms colour/opacity. Hierarchy by size and space, not by boxes.
- Risk low. Failure: tidy but anonymous. Fix with one oversized type moment, not with cards.

**Flat**
- `--shadow: none; --gradient: none; --radius: 2-6px; palette 4-6 solid colours`. Transitions 150-200ms.
- Risk low. Failure: affordance loss (buttons that look like labels). Keep input borders at 3:1 and buttons filled.

**Soft Depth** (the usable descendant of neumorphism)
- `--radius: 8-12px; shadow 0 1px 3px rgba(0,0,0,.08) at rest, one step up on float`. 200-300ms motion.
- Risk low if text stays 4.5:1 on the raised surface. Never emboss text or controls (true neumorphism: do not use for anything task-critical).

**Dense Dashboard**
- `--grid-gap: 8px; --card-pad: 12px; --row-h: 36px; --fs-small: 12px; --sidebar: 240px; --header: 56px`.
- Tooltips on hover, row highlight, no entrance motion. See `app-screen-rules.md` for KPI/table/chart detail.
- Risk low. Failure: shrinking type while keeping padding; density is pitch + padding + type moved together.

**Dark Neutral**
- Ground #000/#111/#171719 (true neutrals, never navy or slate); `color-scheme: dark` on root.
- Depth via a lighter surface step, never glow. Lighter font weights than on light. Secondary text >= 4.5:1 (where dark modes fail).
- Risk low. Failure: three greys that read as one; use two, far apart (~#b4b4b4 and ~#949494 on #111).

**Bento**
- `--gap: 16px; --card-radius: 16-24px; page bg #F5F5F7-type; card #FFF; shadow 0 4px 6px rgba(0,0,0,.05)`.
- Varied spans only (hero tile 2x, never an equal 4-up). Hover scale <= 1.02.
- Risk low. Failure: identical tiles with an icon on top each = the AI feature-grid tell. Tiles must be filled with real content at strict sizes.

**Neubrutal**
- `border: 3px solid #000; box-shadow: 4px 4px 0 #000; --radius: 0; weight 700-900; saturated flat colours`. Instant transitions.
- Risk low. Failure: unreadable at scale; keep to marketing and short tasks.

**Exaggerated Minimal**
- `--type-giant: clamp(3rem, 10vw, 12rem); weight 400-900; tracking -0.03 to -0.05em; --space-huge: 8rem; one accent or none`.
- Risk low. Failure: a huge word with nothing to read. Each screen still carries content.

**Editorial**
- Asymmetric columns, serif body (16-19px, leading 1.5-1.6), bold sans or serif display, pull quotes at ~1.5em, `--column-gap: 2rem`.
- Risk low. Failure: broadsheet cosplay (hairlines everywhere, zero radius, tracked caps). Structure from space and tone instead.

**E-Ink / Paper**
- `--bg: #FDFBF7; --ink: #1A1A1A; --muted: #4A4A4A; transition: none; serif reading face`. No fades; hard cuts.
- Risk low. Failure: tinting the ground yellow enough to become "cream + terracotta" (banned pair).

**Organic**
- `--radius: 16-24px` with variation, soft shadow 0 8px 32px rgba(0,0,0,.08), low-chroma greens/browns, flowing SVG shapes used once.
- Risk low-moderate (pale-on-pale text). Measure every green as text: most "success" greens sit under 4.5:1; use ~#247b50 for text, pale pair for pills.

**Glass** (use only for overlays: nav, sheets, modals)
- `backdrop-filter: blur(10-20px); border: 1px solid rgba(255,255,255,.2); surface alpha .15` over a vibrant ground.
- Risk conditional: measure composed contrast on the real background, not the design tool's. Never for content layers or dense reading surfaces; two or more glass panels on one screen is a tell.

## 3. Colour Rules That Hold Across Registers

- One ground (70-90% of pixels), one ink, one accent (< 5% of any screen, on the action and at most one other thing). Headlines are ink, not accent.
- Surfaces separate by a 2-6 lightness-point step; lines and shadows are the fallback, not the default.
- Banned pairs regardless of register: yellow-cream ground + terracotta/rust/clay accent; violet/indigo as the default brand hue. If the brand owns them, keep them and say so in the report.
- Warmth comes from low-chroma stone/bone/putty grounds (saturation < 15%), deep green/brown/oxblood inks, or one full warm field used flat. Warmth is not beige.
- Colour fields: a section may change its whole ground; neighbouring fields differ in lightness, not only hue; each field has its own assigned ink.
- Photographs carry colour: interface stays neutral; text over a photo gets a neutral scrim (30-55%, over the text area only), the one gradient allowed.
