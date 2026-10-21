# Screenshot Critique: Passes, Score, Caps, Fix Order

Adapted from Leonxlnx/taste-skill (MIT) critique.md.

The 10 gates are pass/fail on code and measurable values. A page can pass every gate and still be anonymous. This procedure judges the rendered result. Judge only the pictures: if a problem is visible in a screenshot it is real whatever the code says; the author reads intentions into code, never into pixels.

Capture at 1440, 768, and 390 (fold plus full page) with whatever browser tool is available. If none, say so in the report and skip the score.

---

## 1. Fourteen Passes (each on its own; do not blend)

1. **One second, then five.** Glance away. What did you see? One answer expected (a word, an image, an object). "A website" = no focal point. Then five seconds as a stranger: what is this, who is it for, what do I do next? A title that only makes sense after scrolling is not a title.
2. **Squint.** Text becomes grey bars. The page should reduce to two or three large masses with clear size differences. Many similar masses = everything is medium.
3. **Cover the logo.** Could this first screen belong to a competitor or another industry? Does the idea reach pricing, FAQ, and footer, or does the page turn into stock blocks after the fold?
4. **Edges.** Count distinct x positions of text-block left edges down the page. Two or three, reused = composed. Six = placed one at a time.
5. **Space and frame.** Related close, unrelated far? Section gap clearly larger than any gap inside a section? Any hole (empty by accident) vs rest (empty by decision)? Equal left/right page margins? Any section with text in one half and nothing in the other? Any blank stretch taller than half a screen?
6. **Type.** Body-to-headline jump decisive (>= 3x)? More than five sizes? Orphan word on a headline's last line? Paragraph over ~75 characters or centred over three lines?
7. **Colour.** Name the proportions: which holds most of the surface, which supports, where is the accent? An accent in ten places means nothing.
8. **Images.** Count real pictures; is every one doing a job (showing the thing, setting the place, proving the claim)? Shared crop ratios? Any grey box, stretched photo, or fake screen of bars? One light and one grade, or a stock mix?
9. **Sameness.** One word per section layout (split, list, full-bleed, grid, statement, index). Same word twice in a row, or three times on the page = template.
10. **Phone.** Its own composition with its own crop and line breaks, or the desktop squeezed? First screen still one clear thing?
11. **Fullness.** Each desktop screen a composed poster, or a narrow column of small text with dead ground either side? Austere is not restrained: if it could be mistaken for a wireframe, it is underbuilt.
12. **Substance.** Does every section the brief asked for deliver its information completely at a readable size? Would a visitor leave knowing what they came for? Is the primary action a real button on the first screen?
13. **Collisions.** Anything over a headline, statement, or button at any scroll position? Anything off the phone edge? A row that scrolls sideways on the phone reads as cut off.
14. **Competitor and the live thing.** Put the competitor's name on the page: does the idea still hold? Name the one thing a visitor can do or that differs per visit. Weak answers here outrank any detail.

## 2. Score (Awwwards weighting)

`overall = 0.4 design + 0.3 usability + 0.2 creativity + 0.1 content`, each 1-10.

- **Design**: 9-10 every screen holds as a poster; 8 confident, one or two soft spots; 7 clean system, little tension; 6 tidy but anonymous, reads as a kit; <= 5 weak hierarchy, accidental spacing, default type.
- **Usability**: 9-10 oriented without scrolling, flawless on phone; 8 minor friction; 7 one real problem (contrast, cramped phone); <= 6 you have to hunt or something breaks.
- **Creativity**: 9-10 a concept specific to this subject; 8 one memorable move; 7 tasteful known approach; <= 6 the category default.
- **Content**: 9-10 every line could only be about this subject; 7-8 concrete with some generic lines; <= 6 slogans, filler, stock.

Calibration: real award-winning pages land 7.5-8.0. An honest 8.5 is rare. If your first score for your own work is 9, score again as the juror who did not build it.

## 3. Caps (override the arithmetic)

| Condition | Cap |
| :--- | :--- |
| Any failing gate from anti-slop-gates.md | overall <= 6.0 |
| Headline of 3+ lines at any width; eyebrow; mono labels; 01/02/03; decorative gradient; resting shadow; decorative hairline | overall <= 6.5 |
| Pass 3 fails (could belong to anyone) | creativity <= 6 |
| Idea passes for the nearest competitor | creativity <= 7 |
| No live thing | creativity <= 7.5 |
| Any placeholder (grey box, lorem, "Image here") | content <= 5 |
| Section the brief asked for missing or reduced to a few words | content <= 6 |
| Two or more mostly-empty desktop screens, or running text small and grey | design <= 6.5 |
| Unequal page margins, half-empty section, blank stretch > half a screen | design <= 6.5 |
| Motion is one identical fade on every block | design <= 7 |
| No real primary button on the first screen | usability <= 7 |
| Section of running text with no heading | usability <= 7 |
| Five-second pass fails (no clear title) | usability <= 6 |
| Anything covering a headline at any scroll position | usability <= 6 |
| Blank band from a reveal that did not fire, or content clipped off-screen | usability <= 5 |

## 4. Critique Record (exact shape, so rounds compare)

```
ROUND n
Seen in one second: ...
Idea (one sentence): ...
Live thing: ...
Layout words by section: hero=... / ...=... / ...
Scores: design _ . usability _ . creativity _ . content _ -> overall _._
Caps applied: ...
Top three problems (most visible first), each with the screenshot and the fix:
1. ...
2. ...
3. ...
```

Name problems as to a colleague: "supporting paragraph starts 40px left of the headline edge", "testimonial is the third split layout in a row", "phone hero crops the bottle out of frame". "Could be more polished" is not a finding.

## 5. Fix Order (later items cannot rescue earlier ones)

1. The idea (pass 3 fails: change the hero concept, not details).
2. Hierarchy: one dominant element per screen; bigger big thing, fewer small things.
3. Composition: shared edges, section spacing, layout variety, holes.
4. Typography: scale contrast, line breaks, measure, leading.
5. Imagery: replace weak pictures, unify crops and grade.
6. Colour: proportion and accent discipline.
7. Detail: states, focus, alignments, mobile refinements.
8. Motion, last.

When removing something leaves a gap, do not refill it with ornament: close the gap, enlarge what remains, or let a picture or colour field take it.

## 6. When to Stop

Three rounds maximum: critique, fix the top three, re-run gates, critique. Stop early when a round finds nothing a stranger would notice. If round three still scores under 7.5, say so plainly with the remaining problems listed; do not round up.
