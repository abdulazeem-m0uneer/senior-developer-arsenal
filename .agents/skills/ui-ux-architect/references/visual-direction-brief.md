# Visual Direction Brief (Pre-Build Decision Record)

Adapted from anthropic-skills/frontend-design (Apache-2.0) and Leonxlnx/taste-skill (MIT).

Write this brief before any markup. Step 1 of the runbook currently picks "mood" from four words; this file makes the choice concrete and checkable.

---

## 1. Subject Inventory (8-12 lines, before any styling)

List what belongs to this product and to no competitor. Each line is a source of a layout, colour, or copy decision:
- Name and what it means. Place (street, city, climate, light).
- Numbers in the brief (seats, SLAs, price, year, batch size).
- The constraint it lives with (one release a month, closed in winter, regulated).
- Materials, trade vocabulary, printed artefacts of its world (ticket, invoice, label, manifest).
- What imagery truly exists: own photos, real product UI, an image tool, or nothing. Never plan around pictures you do not have.

**Competitor test**: write "On this page, [thing from the inventory] becomes [the layout device]." Swap in the nearest competitor's name. If the sentence still holds, the idea belongs to the category, not the client. Rewrite.

## 2. The Brief (commit in writing)

```
Subject:      <one concrete product/audience/job>
Density:      enterprise-dense | consumer-spacious   (already in SKILL.md Step 1)
Register:     <one from visual-registers.md>
Palette:      4-6 named hex values, with the role of each (ground, ink, accent, field)
Type:         1 family (default) or 2 with distinct jobs (display vs text); never 3
Layout:       one-sentence concept + ASCII wireframe of hero and one section; alignment stated (left default)
Hero opener:  the most characteristic thing in the subject's world (headline, image, live demo, real UI fragment)
One live thing: what a visitor can do or what differs per visit, built from real content, works with a thumb, has a no-script fallback
Principles:   3 lines stating what makes this page unlike the category default
```

## 3. Default-Check Pass (run before building)

Ask: "If I were handed a similar brief for a different client, would I produce this same plan?" Any axis where the answer is yes is a default, not a choice. Revise it and record what changed.

Known generated-page clusters (all legitimate when the brief asks; never spend free axes on them):
1. Warm cream ground (~#F4F1EA) + high-contrast serif display + terracotta/clay accent (~#D97757).
2. Near-black ground + one acid-green or vermilion accent + glow.
3. Broadsheet cosplay: hairline rules everywhere, zero radius, dense newspaper columns.
4. SaaS card kit: identical rounded cards, one radius on everything, same soft grey shadow, gradient washes.
5. Template chrome regardless of subject: tracked ALL-CAPS eyebrow above every heading, middle-dot meta strings, "WORD - fragment" labels, tinted near-black (#0B0B0B) as "black", monospace for small data labels, "->" appended to every link.

Rule: where the brief pins a direction, follow it exactly, including one of the above. Where it leaves an axis free, do not fill it with a default.

## 4. Boldness Budget

- Spend boldness in one place. One memorable element per page; everything around it quiet.
- Structural devices (borders, numbering, eyebrows, dividers) must encode information. 01/02/03 markers only when the content is a sequence.
- Non-user-triggered motion: one orchestrated moment per page (load or one reveal). Fade-and-slide on every section and hover lift on every card are the generated default.
- Before shipping, remove one decoration. If nothing can go, the page is probably underbuilt rather than restrained: add scale, full content, or a real picture, never another ornament.

## 5. Quality Floor (ship silently, never announce)

Responsive to 280px, visible focus, reduced motion respected, contrast per anti-slop-gates.md, one h1 naming the thing on the first screen, a heading on every section, equal outer margins at every width.

## 6. CSS Hygiene Reminder

Watch selector specificity when a type selector (`.section`) and an element selector (`.cta`) both set spacing; cancelling padding/margin rules between sections is the commonest self-inflicted layout bug in generated pages. Set section rhythm in one place (a `--section-gap` token) and nowhere else.
