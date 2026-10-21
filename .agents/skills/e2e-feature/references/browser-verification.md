# Browser Verification: Scripted Checks Against a Running Web App

Adapted from anthropics/skills `webapp-testing` (Apache-2.0).

---

## 1. When a Script Beats a Test Suite

The permanent end-to-end tests belong to `test-strategy` (role locators, web-first assertions, no fixed sleeps). This reference is for the *throwaway* check an agent runs once to prove a feature works in a real browser: a short headless script, a screenshot, the console log, exit. It must not be committed as a test, and it must not replace the suite.

---

## 2. Decision Tree

```text
Static HTML file?
  yes → read the file, pick selectors from the markup, drive it over file://
        selectors not findable → treat as dynamic
  no  → is the server already running?
        no  → start it with a launcher that waits for the port, runs the script, then stops the server
        yes → reconnaissance, then action
```

Reconnaissance, then action:
1. Open the page and wait for the network to go idle. Inspecting the DOM before that on a client-rendered app returns an empty shell; this is the one mistake that produces every "element not found" report.
2. Take a full-page screenshot or dump the rendered markup; list the buttons, links, and inputs with their visible text, `href`, `name`, and `type`.
3. Choose selectors from what was rendered (role and text first, then test ids, then stable ids). Never guess selectors from source files for a dynamic app.
4. Run the actions; capture a screenshot after each state change and at the end.

---

## 3. Script Skeleton (Playwright, synchronous)

```python
from playwright.sync_api import sync_playwright

logs = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)          # always headless in an agent session
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))
    page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
    page.goto("http://localhost:5173")
    page.wait_for_load_state("networkidle")              # before any inspection or click
    # reconnaissance
    for b in page.locator("button").all():
        print("button:", b.inner_text() if b.is_visible() else "[hidden]")
    # action
    page.get_by_role("button", name="Save").click()
    page.wait_for_selector("text=Saved")                 # a condition, not a timeout
    page.screenshot(path="<scratch>/after-save.png", full_page=True)
    browser.close()
print("\n".join(logs))
```

Rules:
- Wait for a condition (`wait_for_selector`, `wait_for_url`, `expect(...)`) instead of a fixed timeout; a timeout that passes locally fails in CI.
- Capture console and page errors from before navigation; an error that fires during load is otherwise lost.
- Write screenshots and logs to the scratch directory, never into the repository.
- Close the browser in every path; a leaked browser keeps the dev server's port busy.

---

## 4. Server Launcher

A launcher starts one or more servers, polls each port until it accepts a connection (bounded timeout, about 30 s), runs the script, and terminates the servers whether the script passed or failed. Shape:

```text
with_server --server "npm run dev" --port 5173 \
            --server "python api.py" --port 3000 \
            -- python check.py
```

Treat the launcher as a black box: run its `--help`, do not read its source into context. If the project has no launcher, write one once under the scratch directory from this shape.

---

## 5. What to Report

One line per check: the route, the action, the observed state, and the screenshot path. Console errors and page errors are listed verbatim (they are evidence), warnings are counted. A run with a page error is a failed check even when the screenshot looks right.

```text
/orders → click "Save" → "Saved" toast visible, row count 4→5 → <scratch>/after-save.png
console: 0 errors, 2 warnings (deprecation)
```

---
