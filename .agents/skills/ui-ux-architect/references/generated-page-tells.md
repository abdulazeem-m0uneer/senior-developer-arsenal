# Generated-Page Tells: Dated Registry (extends Gates 8 and 9)

Adapted from Leonxlnx/taste-skill (MIT) tells.md, copy.md, motion.md; anthropic-skills/frontend-design (Apache-2.0).

The 10 gates cover emoji, em-dashes, buzzwords, equal cards, pure black, generic shadows, rainbow accents. This registry adds the waves the gates do not name. A tell is a device produced by default, everywhere, without a reason. The registry is dated because each published "use this instead" list becomes the next wave; replacements here are procedures, not products.

---

## 1. Layout and Chrome Tells

| Tell | Status | Do instead |
| :--- | :--- | :--- |
| Eyebrow / kicker: tiny tracked uppercase label above every heading | fail | Fold the information into the heading or first sentence, or delete |
| Pill badge above the hero headline ("New", "Beta", "Introducing") | fail | Say it in the supporting sentence |
| Index numbering as ornament: 01 / 02 / 03, (001), "Step 02" | fail | Order by position, scale, or words; a real `<ol>` when order matters |
| Hairline dividers, 1px outlined boxes, ruled grids, crosshairs, crop marks, dashed guides | fail on marketing; allowed in tables, forms, and app screens | Space, a tone step, a filled shape, a thick (>= 4px) bar if a bar is the idea |
| Monospace micro-labels, mono captions, mono as a "technical voice" | fail | The text face; tabular figures for data; mono only inside real code and IDs |
| Agency micro-meta: local time, coordinates, weather, version stamps, "(c)2026 - Scroll", middle-dot strings | fail | Remove |
| Glass panels (backdrop blur) as content surfaces; floating pill navigation with blur | warn (2+ = fail) | Opaque surfaces one tone step from the ground; a plain bar: wordmark, 3-5 links, one action |
| Broadsheet cosplay: hairlines everywhere, zero radius, dense columns, regardless of subject | fail | Structure from space and tone |
| SaaS card kit: identical rounded cards, one radius on everything, same soft shadow under each | fail | Hierarchy by radius and elevation; most content does not need a box |
| Three identical feature cards each with an icon in a rounded square | fail | A composed section with real content; icons only where they disambiguate |
| One medium radius (12-16px) on everything | warn | Square or fully round, chosen once; nested radii step down |
| Everything centred | warn over ~70% | Left-anchored; one centred moment per page |
| Headline as a full sentence over three or four lines | fail | ~5 words / ~32 chars, two lines max at 1440, 768, 390 |
| Stock section order: hero, logos, features, testimonial, pricing, CTA | warn | Order of the argument; delete sections with no claim |
| Every section the same layout family | warn (same word twice in a row) | Name each section's layout in one word; neighbours must differ |
| Fake dashboard hero built from grey bars and donut charts | fail | A real interface fragment with real data, or no image |
| Grey box, lorem, "Image here" placeholders | fail | A real picture, a drawing for this subject, or a design that needs none |
| "->" appended to every link and button | warn | At most one arrow, on the primary action, if the register uses arrows |
| One accent word in a headline (italic, serif, coloured, underlined, in a pill) | warn | One face, one colour; the words carry the emphasis |
| Decorative pulsing status dot ("Available for work") | fail | Remove |

## 2. Palette Tells

| Tell | Status | Do instead |
| :--- | :--- | :--- |
| Yellow-cream ground + terracotta / rust / clay accent | fail together; terracotta warn alone | Low-chroma stone/bone ground, deep ink, or one flat warm field |
| Violet / indigo gradients on hero, buttons, glows | fail | Flat colour from the register's palette |
| Near-black ground + one neon accent + glow | fail | True neutral darks, lightness steps, colour on the data |
| Gradient-filled headline text; gradient blobs; gradient buttons | fail | Solid ink; flat fills; a neutral scrim over a photo is the one gradient |
| Tinted near-black (#0B0B0B, #111) presented as "black" by reflex | warn | Choose the ink deliberately per register; off-black is fine when chosen |

## 3. Copy Tells (extend Gate 8 wordlist)

- Genre verbs/adjectives: unlock, unleash, supercharge, elevate, empower, streamline, seamless, effortless, robust, cutting-edge, next-generation, world-class, all-in-one, blazing fast.
- Headline shapes: the mad-lib ("The AI-powered platform for modern teams"); the tricolon ("Plan. Build. Ship."); the correction ("Not just X, it's Y", "More than a..."); "X, reimagined / redefined / made simple"; "Welcome to..."; "Meet..."; a question nobody asked; a headline that needs its colon ("Ledgerly: invoicing for freelancers").
- Performative section labels: "Field notes", "The details", "Our philosophy", "Quietly trusted by", "On our desks". A section can be called "Pricing".
- Button labels "Get started" and "Learn more" as defaults; name the action or the thing instead ("Book a table", "See the plans").
- Explainer captions that narrate the design ("A clean, minimal layout for...").
- Three parallel items everywhere (three features, three stats, three steps). Use the number the content has.
- Invented proof: customers, quotes from named people, press logos, user counts, ratings, "10,000+ teams". Use facts from the brief; if a proof section is required and none exists, label sample content plainly and list it in the report.

Shapes that work: the name set large; what it is in one specific word; a claim a competitor could not sign; verb-first instruction; the place or moment. Sentence case. Supporting line <= 22 words, never a paraphrase of the headline.

## 4. Motion Tells

- The same fade-up on every block; a dozen staggered hero entrances; hover lift or zoom on every card and image.
- Bounce, elastic, or overshoot easing on interface elements.
- Infinite loops that mean nothing: pulsing dots, floating shapes, shimmer text, rotating badges, grain with no off switch.
- Preloaders and counters; enter/sound/age gates; scroll hijacking; custom cursors; scramble and typewriter headlines.
- Content held at zero opacity until scroll settles; a reveal that never fires and leaves a blank band.

## 5. Removal Is Not Enough

A page with every tell removed and nothing in its place is an empty page with good manners, and that is a tell too. Fill the space with scale (the main thing larger), with full content at real density, with a picture made for this subject, or with a field of flat colour. Leave it empty on purpose at most once per page.
