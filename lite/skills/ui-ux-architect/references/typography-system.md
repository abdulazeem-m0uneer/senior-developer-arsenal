# Typography System: Scale, Display Setting, Pairing

Adapted from Leonxlnx/taste-skill (MIT) type.md, copy.md; nextlevelbuilder/ui-ux-pro-max-skill (MIT) typography.csv; anthropic-skills/frontend-design (Apache-2.0).

The DTCG reference ships a 1.25 modular scale for product UI. That scale is right for app screens and wrong for marketing pages, where the main lever is size contrast. Use this file to decide which scale applies and how to set it.

---

## 1. Two Scales, Chosen by Surface

| Surface | Scale | Ceiling | Display:body ratio |
| :--- | :--- | :--- | :--- |
| App screens, dashboards, forms | `dtcg-tokens.md` 1.25 scale (12/14/16/20/25/31) | h1 18-32px; no figure >= 48px | 1.5-2.5x |
| Marketing / landing / editorial pages | Few sizes, far apart (below) | 5 sizes total | >= 4x on desktop |

An app screen with a 50px title or a 76px balance reads as a landing page. A landing page with nine sizes between 16 and 32 reads as mush. Do not cross them.

## 2. Page Scale (few sizes, far apart)

```css
:root {
  --step-small:   clamp(0.8125rem, 0.79rem + 0.1vw, 0.875rem);  /* 13-14px captions */
  --step-body:    clamp(1.0625rem, 1rem + 0.25vw, 1.1875rem);   /* 17-19px paragraphs */
  --step-lead:    clamp(1.25rem, 1.1rem + 0.7vw, 1.625rem);     /* 20-26px supporting line */
  --step-head:    clamp(2rem, 1.3rem + 3.2vw, 4rem);            /* 32-64px section headings */
  --step-display: clamp(3rem, 1rem + 9vw, 9rem);                /* hero; bounded on phones and ultrawide */
}
```

- If two sizes look almost the same, make them the same. No "subheading" size per card.
- One size dominates per screen; section headings sit well below the hero.
- Weight is not the lever: half of strong heroes are regular weight. Scale and spacing make type confident. Bold everywhere = nothing emphasised.

## 3. Display Setting (anything over 40px)

```css
.display {
  line-height: 0.95;            /* 0.85-1.05; tighter for caps and condensed */
  letter-spacing: -0.035em;     /* -0.02 to -0.05em; scales with size; set per step, never once for all headings */
  font-kerning: normal;
  text-wrap: balance;
  max-width: 14ch;              /* author the break */
  margin-left: -0.05em;         /* optical alignment for round/diagonal first letters */
}
```

- All caps: open tracking 0 to +0.03em, leading ~0.9, never longer than three words.
- Leading under 1.0: check descender/ascender collisions on two-line headlines by eye.
- Never text-shadow, outline stroke, or gradient fill on display type.
- Headline length is arithmetic, decide it in copy first: `chars per line ~= line width px / (font px * k)`, k = 0.40 condensed, 0.50 most grotesks/serifs at display size, 0.58 wide faces or caps. About 32 characters survives two lines at every width at a confident size; a phone at 390px with a 44px headline holds ~16 per line.
- Every h1-h6 fits two lines or fewer at 1440, 768, and 390. Cut words, then widen the measure, size last. Never fix a long headline by shrinking it.
- Avoid one orphan word on line two; rebalance by cutting a word, not nudging width.

## 4. Text Setting

```css
body { font-size: var(--step-body); line-height: 1.5; font-kerning: normal; text-rendering: optimizeLegibility; }
p    { max-width: 62ch; text-wrap: pretty; }
.lead { font-size: var(--step-lead); line-height: 1.35; max-width: 40ch; }
a    { text-underline-offset: 0.18em; text-decoration-thickness: 0.07em; }
h1, h2, h3 { hyphens: none; }
.num { font-variant-numeric: tabular-nums; }   /* prices, tables, timers, anything that updates */
```

- Measure 45-75 characters (mobile 35-60). Leading 1.45-1.6 body, 1.3-1.4 lead; serif body gets slightly more leading and may run slightly longer.
- Secondary text: same face, softer ink (`--muted`, still >= 4.5:1), never a lighter weight and never under 13px.
- Space above a heading >= 2x the space below it.
- No centred paragraphs over three lines. No justified text. No weight change on hover (reflow).
- Light-on-dark looks heavier: drop one weight step or add 0.01em tracking, raise leading slightly.
- Verify the face has real tabular figures: `tabular-nums` must change digit widths; if it does not, pick another face.
- `font-display: swap` plus a metric-compatible fallback of the same class (sans for sans, serif for serif). Request only the 2-3 weights used.

## 5. Pairing Rules

- One family is the default and the safest coherent choice. Two at most, each with one fixed job (display vs everything else); never swap them, never mix two faces in one headline, never a third face for labels, numbers, or quotes.
- If two, make them clearly distinct in class (serif + sans, or display + text), not two similar grotesks.
- Monospace only inside real code, IDs, or as one deliberate decision for every figure. Not as a "technical" voice for labels and captions.
- Italic for titles of works and real emphasis inside paragraphs; never as decoration, never for one accent word in a headline.
- Pick the face from the subject and register, not from habit. Do not default to the same family on every project (Inter on every page is itself a tell).

### Pairings that work, by job (Google Fonts, all importable)

| Job | Display + Text | Note |
| :--- | :--- | :--- |
| Enterprise / dashboard / docs | Inter alone, or IBM Plex Sans alone | Single family, weights 400/500/600; Plex has strong tabular figures |
| Trust-heavy (finance, legal, gov) | EB Garamond + Lato; Lexend + Source Sans 3 | Lexend built for readability |
| Tech / developer | Space Grotesk + DM Sans; JetBrains Mono (code only) + IBM Plex Sans | Keep mono inside code blocks |
| Editorial / publishing | Newsreader or Libre Bodoni + Public Sans; Cormorant Garamond + Libre Baskerville | Serif body wants 1.55-1.6 leading |
| Luxury / fashion / architecture | Cormorant + Montserrat; Playfair Display + Inter | Display face at 400 weight, very large |
| Wellness / organic | Lora + Raleway; Figtree alone | Low contrast between faces |
| Playful / children / consumer | Fredoka + Nunito; Varela Round + Nunito Sans | Rounded terminals in both |
| Bold marketing / agency | Syne + Manrope; Outfit + Rubik; Bebas Neue (headline only) + Source Sans 3 | Display face for headlines only, never body |
| Multilingual | Noto family of the script (Sans/Serif JP, KR, SC/TC, Arabic Naskh + Sans, Thai, Hebrew) | One Noto family per script; confirm RTL mirroring for Arabic/Hebrew |

## 6. Micro-typography (set once, globally)

- Curly quotes and apostrophes, a real ellipsis, en dash for ranges (9-5 as en dash). Avoid the em dash as a habit (see anti-slop gate 8).
- `&nbsp;` between a number and its unit, and before the last short word of a headline that would orphan.
- `::selection` and `:focus-visible` take the accent so browser states belong to the design.
- `overflow-wrap: anywhere` plus `min-inline-size: 0` on the flex/grid child for URLs, IDs, and user content; never `word-break: break-all` on prose.
