# Epistemic Hygiene & Sanity Checklist

Use before declaring an investigation complete or making high-stakes code alterations.

---

### Phase A: Observation & Belief Calibration
- [ ] **Distinguished fact from belief**: Every assertion is backed by a concrete file line or command output, not a "probably".
- [ ] **Noticed confusion**: Did any test output surprise you? If yes, stop and update your mental model before writing fixes.
- [ ] **No "should" traps**: Have you purged all reasoning based on *"this should work"*? Ground reasoning strictly in observed reality.
- [ ] **Line of retreat open**: Have you checked if "I don't know" is the most honest current status?

---

### Phase B: Hypothesis Rigor
- [ ] **5+ hypotheses formulated**: Did you consider at least 5 distinct failure modes before selecting one?
- [ ] **Discriminative tests run**: Did each test isolate a single hypothesis, rather than shotgun multi-changes?
- [ ] **Failed loudly**: Are there any silent fallbacks (`or {}`, empty `catch`, default `null`) that were masking the problem?

---

### Phase C: Modification & Safety
- [ ] **Chesterton's Fence satisfied**: Can you articulate exactly why the original code was written before altering it?
- [ ] **Second-order effects traced**: What other modules or queries depend on this function/table/contract?
- [ ] **Autonomy gate passed**: Is this reversible? If high blast-radius, has the user confirmed?
- [ ] **Batch size $\le 3$**: Has every change been empirically verified before moving to the next?
