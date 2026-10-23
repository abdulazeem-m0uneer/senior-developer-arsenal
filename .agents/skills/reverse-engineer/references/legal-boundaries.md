# Legal Boundaries and the Authorization Gate

Read this before Step 1 when the target is commercial software, the feature touches authentication, payment, licensing or DRM, or the user intends to ship the rebuild.

---

## 1. The Gate

The run starts only when all three lines are written at the top of the evidence log:

| Line | Acceptable | Not acceptable |
| :--- | :--- | :--- |
| **Authorization** | "I own a licensed copy", "my employer owns it", "open source under <license>", "I was engaged by the vendor" | "it is on my machine", "everyone does it", silence |
| **License terms** | The EULA or license clause that permits (or does not forbid) analysis, cited by section; interoperability exceptions where the jurisdiction grants them | A guess that it is probably fine |
| **Purpose** | Interoperability, security research on authorized targets, education, preservation, migration of the user's own data | Cloning the product, defeating a protection, reselling the result |

"Interoperability is valid; cloning a product is not": a file format, a protocol, a plugin interface, a sync behaviour can be rebuilt to work *with* the original. A product whose selling point is the feature, rebuilt to replace the original, is cloning and stops at the gate.

---

## 2. Stop List

The run ends in one sentence, with no partial help, when the feature or the request involves:

- License checks, activation, trial limits, or DRM of any kind.
- Authentication, session tokens, or authorization decisions of the target.
- Paywalls, entitlement checks, or premium gating.
- Extracting API keys, signing keys, certificates, credentials, or any user data from the target.
- Cracked tooling: REA grants no license for IDA, Hopper, or JEB; stolen keys and license bypasses are outside the gate.

A feature adjacent to one of these (a settings screen that also shows the license state) can proceed when the trace stops at the boundary and the boundary hop is recorded as "not traced: gated".

---

## 3. Clean-Room Rule

The evidence log and the behaviour spec are the only artifacts that cross from analysis to implementation.

- Decompiled code, pseudocode, source maps, bundled source, and strings are read to write the spec and are never pasted, transliterated, or kept beside the rebuild.
- Names, icons, fonts, copy, colours, and other brand assets stay with the original. The rebuild carries the user's own.
- A spec line that could only have come from reading one function is fine; a spec line that *is* that function (its structure, variable names, constants that are not formats) is a port, not a rebuild.
- When a second person is available, the strongest form is two roles: one writes the spec from the evidence, another implements from the spec without seeing the evidence. Record which form was used.

---

## 4. Data Policy

REA runs its analyzers locally, but the agent's model provider sees whatever the agent sends it. Before the run, confirm that sending decompiled output, strings, and captures of the target to the model provider is within the target's license and the user's own data policy. When it is not, the surface map and trace stay in local notes and the agent works from the user's summaries.
