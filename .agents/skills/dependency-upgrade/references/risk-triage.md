# Upgrade Risk Triage

How to rank candidates, read SemVer honestly, check licences and supply chain, and record the plan and rollback.

---

## 1. Priority Order

| Rank | Candidate | Why first | Deadline |
| :---: | :--- | :--- | :--- |
| 1 | Vulnerability reachable in a production code path, fix available | Exploitable now | Days |
| 2 | Runtime, framework, or base image at or near end of life | No more security fixes; later jump is larger | Before the end-of-life date |
| 3 | Unmaintained or deprecated package | No fix will come; plan a replacement | Next planning cycle |
| 4 | Licence outside the allowlist | Legal exposure grows with each release shipped | Before the next release |
| 5 | Major version behind | Migration cost compounds with every skipped major | Scheduled, one at a time |
| 6 | Minor and patch drift | Small, cheap, keeps the next major short | Weekly batch |

A vulnerability in a development-only tool that never handles untrusted input ranks with routine drift. Prove reachability before treating an advisory as rank 1: is the affected function called, with attacker-controlled input?

---

## 2. Risk Triage Table

| Signal | Low risk | Raise the risk when | Extra verification |
| :--- | :--- | :--- | :--- |
| SemVer distance | Patch, or minor of a stable (1.0+) package | Major; any bump of a `0.x` package (minor may break); calendar-versioned packages | Read every release note in the range |
| Blast radius | Imported in one module, behind an adapter | Imported across the codebase; a framework, ORM, or serialiser | Full suite plus real start plus a smoke run |
| Position | Development or build tool | Runtime path handling requests, money, auth, or stored data | Staged rollout, watch error rate and latency |
| Data and wire formats | None touched | Serialisation, hashing, encryption, cache keys, session or token formats, database driver | Old and new versions read each other's output; test a rollback |
| Changed defaults | None listed | Timeouts, retries, TLS settings, strictness, time zones, rounding | Pin the old default explicitly, change it in a separate commit |
| Peer and runtime needs | Unchanged | New minimum runtime, new peer major, dropped platform | Upgrade the prerequisite first, as its own change |
| Transitive tree | Same packages, new versions | Many new packages, a new native build, a new install script | Section 4 checks |
| Test coverage of call sites | Covered by tests that exercise the library for real | Calls are mocked everywhere | Add an integration test before upgrading |
| Maintainer signal | Regular releases, signed, provenance attached | New maintainer, long silence then a sudden release, repository moved | Wait out a release-age delay; read the diff |

Two or more raised signals: the upgrade gets its own change, a written plan, and a second reviewer.

---

## 3. Licence Check

- [ ] Checked at the target version, not the current one; licences change between releases.
- [ ] Compared against an explicit allowlist (commonly MIT, ISC, Apache 2.0, BSD-2-Clause, BSD-3-Clause, 0BSD, Zlib, CC0).
- [ ] A dual-licence expression (`MIT OR <other>`) passes when one option is allowed.
- [ ] Missing or unrecognised licence fails: unknown is not allowed.
- [ ] Strong copyleft and source-available licences (GPL, AGPL, SSPL family) fail for distributed or hosted proprietary code unless legal review says otherwise.
- [ ] Every exception is one named package with its licence, the reason it is acceptable, who approved, and the date; never a wildcard.
- [ ] The check runs in CI after install, so a transitive change is caught without anyone looking.

---

## 4. Supply-Chain Check

| Check | Question | How |
| :--- | :--- | :--- |
| Name | Is this the package the docs name, not a look-alike? | Follow the link from the official site or repository; compare download counts and age |
| Publisher | Did the publishing account or organisation change? | Registry metadata for the previous and target version |
| Provenance | Is the artefact tied to a source commit and build? | Registry provenance or signature verification; a missing attestation on a package that used to have one is a red flag |
| Install scripts | Does the version add or change a pre- or post-install script? | Read the script before the first install; install with scripts disabled when unsure |
| Tree | Which packages are new in the lockfile? | Diff the lockfile; explain each new transitive dependency |
| Release age | Is the release older than the team's delay (for example 7 days)? | Publish date; compromised releases are usually pulled within days |
| Source match | Does the published artefact match the tagged source? | Compare for high-risk packages or any raised signal |
| Integrity | Do lockfile hashes verify on a clean install? | Frozen or locked install in CI from an empty cache |

---

## 5. Upgrade Plan Template

```markdown
## Upgrade: <package> <current> -> <target>

- Type: direct | transitive, runtime | development
- Reason: <advisory id, end of life, feature, routine>
- Notes read: <links to changelog and migration guide, versions covered>
- Breaking changes that apply: <each one, with the call sites>
- Path: <current> -> <next major> -> <target>, green at each step
- Licence at target: <licence> (allowlisted: yes | exception recorded)
- New transitive packages: <list or "none">
- Verification: clean install, lint, typecheck, full suite, real start, <extra checks from triage>
- Rollback: revert <commit>; data or format caveats: <none | details>
```

---

## 6. Worked Example: Two Majors Behind

| Step | Action | Gate |
| :---: | :--- | :--- |
| 1 | Read migration guides for major 3 and major 4; list 6 breaking changes, 2 apply | Call sites identified |
| 2 | On the current major, fix every deprecation warning the library prints | Suite green, zero warnings |
| 3 | Raise the runtime to the minimum that major 4 needs, as a separate change | Suite green, application starts |
| 4 | Upgrade to the last release of major 3; apply its 1 breaking change | Suite green, application starts |
| 5 | Upgrade to the target release of major 4; apply its 1 breaking change | Suite green, application starts, smoke run |
| 6 | Licence and supply-chain checks on the final lockfile diff | No new unknowns |
| 7 | Release behind a staged rollout; watch error rate and latency for one window | Promote or revert the single commit |
