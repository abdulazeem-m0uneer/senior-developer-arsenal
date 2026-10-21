# App Screen Rules: Dashboards, Admin, Analytics, Settings

Adapted from Leonxlnx/taste-skill (MIT) references/app-screens.md (study of 23 production product screens).

Gate 9 ("hero metric >= 2.5x body, asymmetric bento") was written for marketing surfaces. On a working screen it produces the generated-dashboard look. These rules replace it for any screen people work in daily.

---

## 1. Decide Before Building

- **One question per screen.** Write it ("Which deploy broke?", "Did today's sales come in?"). The biggest block answers it; the largest figure answers the title row's sentence; nothing else on the screen is larger.
- **One finding.** The fact in today's data that needs attention, placed under the title or as the headline figure's subline, next to the action it drives. Never in a 14px caption at the bottom of a card.
- **Blocks are answers to next questions**, one line each. A block with no question is deleted. This avoids the stock order of KPI row, big chart, two small charts, table.
- **Everything the brief names shows on the first screen** at 1440x900: header plus first rows or figure. Headline block 200-360px tall; lists capped at 4-6 rows with "View all"; time-sensitive blocks before long tables.
- **The most frequent job is one click away**: a primary button in the title row, an action on the row that needs it. A screen with no control for its job is a report, not a tool.
- **Name the product** in the shell (mark, name, workspace scope). A screen that could belong to anyone fails.

## 2. Shell and Canvas

- Sidebar on the page ground, never dark or saturated on a light screen. Active item: neutral grey pill or text colour change. No coloured left bar by default.
- No hero header, no "Welcome back" greeting. Page title is a noun at 18-32px (median 24, weight 500-600).
- Top bar only when it carries something (search, scope switcher, object name). Export/Share/date-picker clustered by the title only when real.
- One left edge and one right edge for the whole canvas; every card's content starts on the same inner line.
- Colour on data, not chrome: coloured pixels ~3% of the screen; accent on the main data element plus at most one control; primary button near-black or no filled primary at all.

## 3. KPIs

- No tile per KPI by default: one container split by 1px dividers into equal columns, or bare label-over-value text.
- Value 16-40px (median 24-26), weight 400-600; label 12-14px grey, sentence case, above the value. Value ~1.7x label. Units as a smaller grey suffix ("5 /10", "2 m 24 s").
- The answer figure is 30-36px and >= 1.3x its siblings (18-24px). Three equal 24px figures leave no lead.
- No icon in a tinted circle, no sparkline, no tinted tile, no 48px+ figures. An info glyph beside the label is fine.
- One figure, one place: a KPI strip whose every cell names a panel below is dropped; lead each panel with its number instead.
- KPIs may double as the chart's series tabs: selected cell gets a 2px rule or active fill and ink label; others keep grey label and ink value. Never grey the values of unselected tabs (reads as disabled).

### Deltas
- Optional. 10-15px, never larger than the label. Window in words: "vs prior 30 days".
- Colour the number only, or set the whole delta grey.
- **Colour says good or bad, not up or down.** Latency, errors, cost, churn: a rise is `--negative`. Falls in a good direction are `--positive` or grey.
- Zero or undefined change is grey; from zero write "+4 (new)"; nothing to compare is a grey dash. No green "+100%" pills grown from zero, no ">999%".

## 4. Charts

| Question | Form |
| :--- | :--- |
| Moving over time? | One straight-segment line, 2px; area fill <= 15% or none; no point markers |
| How much per period? | Square-cornered columns (max 4px top radius) |
| Who ranks? | Sorted horizontal bar list, or row fill as the bar in a one-figure list |
| What share? | Thin ring or 100% stacked bar with 2px seams; five parts max; never labels on slices |
| How far to target? | Progress bar, both ends labelled, fill at the true ratio, no stub at zero |
| Drift from target? | One row per part, current share as bar, 1px tick at target |

- One series per chart (three max). Switch metrics with a control, do not overlay lines.
- Gridlines: 3-5 horizontal, 1px, ~#e5e5e5 light / ~#2b2b2b dark. No y-axis line; baseline is the one heavier line. Dashed lines only here and in empty slots.
- Y ticks: 4-7, 11-13px grey, round even steps, top tick above the max, zero baseline for counts. Never a chart without a scale. Axis text never larger than the data.
- X labels: 4-8, flat, never rotated, one step that lands on the end.
- One hue per chart; one subject keeps one hue across the screen; four hues max on a screen. No legend for a single series; otherwise <= 5 items, swatch = the mark scaled down, never a series with no data.
- Annotate the event that matters: 1px marker, 12px label naming the cause. Reference lines 1px dashed, label at the end. Forecasts dashed after today with the end value labelled.
- A series flat except one event gets <= 2/3 width and ~140px height, or a capped range with the off-scale peak labelled.
- Empty chart: draw the zero line and missing bars, no "No data" illustration. A lone point does not get the largest plot.

## 5. Tables and Lists

- Rows 36-53px single-line (median 45); 56-92px with media; two-line pitch >= 40-44px or sublines collide.
- Header 12px grey sentence case, regular weight, no fill band, no rule under it (or one rule as the strongest line). Sort glyph on the active column only.
- No zebra. Dividers 1px, 3-7% darker than the surface, one extent per screen.
- **Numbers right-aligned in tabular figures**; headers flush with their values. Fixed decimals per metric (money 2, % 1-2, counts 0); thousands separators; sign on every change; no space after a currency sign.
- Identity column widest (1/3 to 1/2) and never the one truncated; shorten names editorially first.
- Only identity and key number in primary ink; the rest grey. Missing value = grey dash; real zero printed.
- Status: one mark per row; pale tint with dark text of the same hue (#dcfae5/#04250e, #ffedea/#831c1e); saturated fill with white text only for one rare call to action (< 1/5 of visible rows). Chips `flex: none; white-space: nowrap`.
- No pagination under an overview: cap rows, "View all", state the total. Full list screens: sticky header row, range shown ("1-50 of 1,284").
- Row actions: none, or one kebab at the far right, or one ink text action in a fixed trailing column at the same pitch for every row. Never stacked under the amount.
- Selected row in a list that drives a detail pane takes the nav's `--active` fill, distinct from hover and focus.

## 6. States

- **Loading**: final layout with each value replaced by a flat grey bar at its real size; labels and headers shown at once; no shimmer gradient; zero layout shift on arrival. A refresh keeps old values and updates the freshness stamp.
- **Error**: inside the block that failed, never a full-screen banner. One sentence with what failed and when data was last good, plus a Retry text button.
- **Empty section**: keeps frame and header; one sentence spanning the block (`grid-column: 1 / -1`); 1px dashed box ~38px tall, or a bordered box with an add link.
- **First run**: keep frame and title; put the first action where the data will appear; setup progress at its true percentage.
- **Counts follow the view**: tabs, KPI counts, and sublines recompute on every filter switch.
- Red is a signal, not a texture: one red mark per object at most.

## 7. Tokens (defaults, greys lifted to 4.5:1)

```css
:root {
  --ground:#f9fafb; --surface:#fff; --raised:#f9f9f9; --active:#eee;
  --border:#e8e8e8; --rule:#f2f2f2; --control:#d1d5db;
  --text:#111; --muted:#5f6368; --faint:#6b6b6b;      /* placeholders use --faint */
  --primary:#1d1f20;                                   /* near-black fill */
  --positive:#247b50; --negative:#c4242a; --grid:#e5e5e5;
  --radius-card:8px; --radius-control:6px; --radius-chip:4px;   /* soft register: 20/14/999 */
  --gap:16px; --card-pad:20px; --control-height:32px; --row-height:48px;
  --fs-title:24px; --fs-section:16px; --fs-kpi:24px; --fs-body:14px; --fs-small:12px;
}
:root[data-theme="dark"] {
  --ground:#000; --surface:#111; --raised:#222; --active:#222;
  --border:#1a1a1a; --rule:#161616; --control:#444;
  --text:#fff; --muted:#b4b4b4; --faint:#949494; --primary:#fff;
  --positive:#3fc07a; --negative:#e5566f; --grid:#2b2b2b;
}
```

- Radius is bimodal: tight 4-8px or soft 16-24px, chosen once; controls follow cards; nested radii step down. More than three panel radii is a defect.
- A border or a shadow on a card, never both. Real shadows only for what floats (menu, popover, dialog).
- Density = row pitch + padding + type size moved together: sparse (20-24px pad, 56-92px rows, 14-16px), medium (16-24px, 44-56px), dense (13px body, 28-42px rows, with generous outer gutters).

## 8. Generated-Dashboard Tells (fail on sight)

Dark/tinted sidebar with coloured active pill; "Welcome back, Alex" with a wave; four KPI cards with icons in tinted circles; green "+12.5%" pill on every KPI; sparkline on every KPI; KPI values at 36-48px bold in brand colour; gradient area chart with smoothed spline and a dot per point; rainbow palette; gridlines every 20px with a legend for one series; fat donut with slice labels and a big total in the hole; cards with 16-24px radius plus border plus large shadow; zebra table under uppercase tracked headers with checkbox, avatar, chip, and kebab on every row; left-aligned proportional numbers; saturated status chips with white text; accent on every button and tab; pagination under a five-row list; equal 4-up grid with orphan cells; Inter on #f8f8f8 with white 12px cards and no hue on the data; coloured icon per category in a list; illustration plus "No data yet" in an empty chart; lorem/Acme/John Doe; totals that do not sum from the rows.
