# Verification Checklist and Drift Control

Read this at Step 6 before declaring parity, and again whenever the target application updates.

---

## 1. Oracle Tests

Each oracle case from Step 2 becomes one test against the rebuild. The test is written from the *observation*, not from the evidence log, so a wrong trace cannot pass its own test.

- [ ] Every oracle case has a test with the observed input, the observed output, and the observed side effect (file, rows, request).
- [ ] At least one case covers a failure path (bad input, offline, empty state) and asserts the observed error behaviour, not a nicer one.
- [ ] Where the original can be driven (CLI, API, scripted UI), the same inputs were run against it in this session and the outputs recorded beside the rebuild's.
- [ ] Formats are asserted byte-for-byte or schema-for-schema where interoperability is the purpose (a file the original must read back; a request the original's server must accept).
- [ ] A failing case was sent back to the trace: the contradicted rows were downgraded and re-traced before the test or the rebuild was touched.

---

## 2. Rebuild Hygiene

- [ ] No decompiled output, pseudocode, bundled source, asset, string table, or brand element exists under the rebuild's path (`git grep` for the original's product name, bundle identifiers, and distinctive constants that are not formats).
- [ ] Every spec line maps to code or to a documented omission; every probable row has its marker comment in the code.
- [ ] The rebuild follows the project's rules (`minimal-change`, `test-every-change`, stack standards) and is as simple as the oracle cases allow.
- [ ] The rebuild does not depend on the original being installed, except where interoperability requires its files or endpoints.

---

## 3. Drift Control

A finding is tied to one version of the target. Record and check:

- [ ] Target version and build or file hash are in the evidence-log header and in the rebuild's README.
- [ ] A one-line drift check exists: which rows are probable, which strings, IPC channels, routes, or offsets the trace depends on, and the command to re-run the surface map.
- [ ] On a target update: re-run the surface map, diff the dependent strings and channels, downgrade probable rows to assumed, re-run the oracle tests against the new original, re-trace only the chains whose rows moved.

---

## 4. Final Self-Audit

Answer each in one line in the report's Unknowns section; an honest "not checked" is a valid answer.

- What is missing from the call chain, and what was searched to find it?
- Which rows rest on pseudocode alone, and what runtime evidence would promote them?
- Did any hop get graded by how plausible it looked rather than by what was seen?
- Would the rebuild pass the oracle tests if the original's next version changed the thing this trace depends on most?
- Is every artifact under the rebuild's path the user's own work?
- Does the run still sit inside the authorization, license, and purpose lines written at the gate?
- What single piece of evidence would most change the conclusion?
