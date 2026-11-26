# Test Audit: What Each Finding Means

Read in Step 6 of the test-strategy skill. The script is `scripts/test_audit.py`, standard library only: Python is parsed with `ast`, and the other languages (JavaScript/TypeScript, C#, Java, Kotlin, Go, Rust, PHP, Ruby) with regexes.

| Kind | What it found | Fix |
| :--- | :--- | :--- |
| `no-assertion` | A test that can only fail by crashing. | Assert on the observable outcome. A helper that asserts must be named `assert*`, `expect*`, `verify*`, `check*`, `should*`, `must*` or `ensure*`, so readers and the audit both see it. |
| `skipped` | An unconditional skip (`@pytest.mark.skip`, `@unittest.skip`, a first-statement `pytest.skip()`, `xit`, `it.skip`, `[Fact(Skip=...)]`, `@Disabled`, `t.Skip`, `#[ignore]`, `markTestSkipped`). | Fix and un-skip it, or delete it. A skip that waits on a ticket names the ticket. |
| `focused` | `.only`, `fit`, `fdescribe`, `focus: true`. Every other test in the run silently stops running. | Remove the focus marker before committing. |
| `duplicate` | The same normalized body as an earlier test (at least 40 characters). | Merge them into one table-driven test (`it.each`, `[Theory]`, `@pytest.mark.parametrize`), or make each one test what its name says. |
| `source-grep` | The test reads a source-code file, asserts on containment, and calls nothing else. | Call the code and assert on its behaviour. A wiring check on generated output (configs, manifests) is not reported. |

## What Counts as an Assertion

- The language's own forms: `assert`, `expect(`, `Assert.`, `.Should()`, `assertThat`, `t.Error`/`t.Fatal`, testify `assert.`/`require.`, `assert!`/`assert_eq!`, `#[should_panic]`, `$this->assert*`, `expect`/`assert`/`refute` in Ruby.
- Any call whose name starts with `assert`, `expect`, `verify`, `check`, `should`, `must` or `ensure`, or is `raises` or `fail`.
- Python: a `raise` statement, and a call made with `check=True` (`subprocess.run` raises on failure).
- Rust: `unwrap()` and `expect(`, because a panic fails the test.

A helper that asserts under any other name is reported as `no-assertion`. That false positive is deliberate: rename the helper.

## Limits

- Ruby blocks are read by indentation (`it ... do` up to the `end` at the same indentation), and one-line `it { ... }` blocks are not read.
- A JavaScript test with a concise arrow body (`it("x", () => expect(a).toBe(1))`) is read up to its `;`.
- Conditional skips (`skipIf`, `skipUnless`, a skip inside an `if`) run on some platform and are not reported.
