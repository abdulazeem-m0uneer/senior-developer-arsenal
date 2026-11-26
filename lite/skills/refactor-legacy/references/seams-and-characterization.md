# Seams & Characterization

Techniques follow Michael Feathers, "Working Effectively with Legacy Code", described here in original wording.

## 1. Pinning Methods

| Method | Use when | How |
| :--- | :--- | :--- |
| Characterization test | One function, few outputs | Call with an input, observe the real result, assert it as a literal; write a wrong guess first and let the failure tell you the truth |
| Golden master | Large or structured output (report, HTML, JSON, file) | Run over a wide input set, store the output, diff future runs against it |
| Approval test | Golden master with human sign-off | Reviewer approves the stored output; unapproved diffs fail the run |
| Recorded interaction | Calls to services you cannot run | Record real request and response pairs once, replay in tests |

- Review every captured value before pinning. A snapshot nobody read is not a test.
- Assertions are literals read from the real run, not values recomputed with the code under test.
- Choose inputs for branch coverage: each branch, each boundary, empty, null, maximum, malformed, and one real production sample.
- Keep the golden set small enough to read in a diff; split by scenario, not one giant file.
- Mark each pin with a name that says what it records: `current behaviour: refund over 30 days returns 0`.

## 2. Taming Non-Determinism

| Source | Control |
| :--- | :--- |
| Clock, time zone | Inject a clock; fix the zone in the test environment |
| Randomness | Inject the generator or seed it |
| Generated ids, tokens | Stub the generator, or mask the field before comparing |
| Unordered output (maps, sets, parallel results) | Sort by a stable key before comparing |
| Floating point | Compare with a stated tolerance, or round at the documented place |
| Network, queues, email | Fake at the boundary; assert the request sent, not the live reply |
| Filesystem, environment | Temp directory per test; set and restore variables |
| Database | Real engine with seeded rows, rolled back per test |
| Absolute paths, hostnames, versions in output | Mask before comparing |

## 3. Choosing a Seam

A seam is a place where behaviour can change without editing the code at that place.

| Seam | Mechanism | Prefer when |
| :--- | :--- | :--- |
| Object seam | Pass or override a collaborator through a constructor, parameter, or subclass | Default choice in object-oriented and most dynamic code |
| Link seam | Swap the module, library, or binary the code resolves at build, load, or import time | Static functions, global calls, third-party singletons |
| Preprocessing seam | Textual substitution by macro or build step | Only when the first two are impossible (some C and C++ code) |

## 4. Smallest Safe Moves

| Move | Effect | Watch |
| :--- | :--- | :--- |
| Parameterize constructor | Dependency arrives as an argument; old signature kept as an overload that builds the default | Default must construct exactly what the old code built |
| Parameterize method | Same for a value or collaborator created inside a method | Keep the old call shape working |
| Extract interface | Name the few methods the code needs; production class implements it; tests supply a fake | Interface holds only methods used, not the whole class |
| Extract and override | Pull the awkward call into its own method; a test subclass overrides it | Method must stay overridable (not private or final) |
| Extract function | Move a block into a function whose inputs are explicit | Pass in what it reads; return what it writes |
| Wrap method | Rename the old method; new method with the old name calls it plus new logic | New logic before or after only |
| Sprout method | Write new logic as a new, tested method; one call inserted at the change point | Insert exactly one line in the legacy body |
| Wrap or sprout class | Same, at class level, when the host class cannot be instantiated in a test | Prefer when the host has heavy construction |

- Each move is its own step: edit, build, run the manual smoke path, commit. No other change rides along.
- Moves done before pins exist rely on the compiler or type checker; make them mechanical and few.
- Remove scaffolding (test-only subclasses, widened visibility) when a proper seam replaces it, in a later step.
- If the new logic is the only change needed, sprout or wrap it, test it fully, and leave the legacy body nearly untouched.

## 5. Choosing the Change Point

- List callers first; the best change point is where most paths converge (a pinch point).
- If one narrow function covers all paths, pin there and cover the rest by sampling.
- Test at the highest level that is still fast and deterministic; drop lower only to reach branches the high level cannot.
- If no seam exists within reach, pin from the outside (HTTP, CLI, file in and out) and refactor behind it.
