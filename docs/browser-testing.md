# Browser Testing

Browser testing in the Development Harness is not a separate CI step. It runs inside the agent's verification loop so the agent sees frontend failures and self-corrects. The goal: the agent tests its own UI changes so the developer does not have to click buttons manually.

---

## How It Works

1. The agent writes frontend code (React components, CSS, HTML templates, etc.).
2. A post-tool hook detects that UI files changed.
3. The browser observer triggers the `BrowserTestRunner`.
4. The runner launches headless Chromium via Playwright.
5. It navigates to the specified URL and executes step-by-step interactions.
6. Screenshots are saved as artifacts. Console errors and DOM snapshots are captured.
7. Results are structured as `BrowserTestResult` and injected into agent context.
8. If a test fails, the agent sees exactly what went wrong: the failing step, the console error, and a text representation of the page DOM.

---

## Prerequisites

Install the browser testing dependencies:

```bash
pip install devharness[browser]
playwright install
```

This installs Playwright and downloads Chromium. The harness uses headless Chromium for all browser tests.

---

## Defining Test Flows

Browser test flows are YAML files that describe step-by-step interactions with a web page. Place them in `.devharness/browser_tests/`:

```
.devharness/
  browser_tests/
    login_flow.yaml
    signup_flow.yaml
    checkout_flow.yaml
```

### Flow Structure

```yaml
name: login_flow
url: http://localhost:3000/login
viewport_width: 1280
viewport_height: 720
steps:
  - action: fill
    selector: "input[name='email']"
    value: "test@example.com"
  - action: fill
    selector: "input[name='password']"
    value: "testpass123"
  - action: click
    selector: "button[type='submit']"
  - action: wait_for
    selector: ".dashboard"
    timeout: 5000
  - action: screenshot
    name: "after_login"
assertions:
  - type: url_contains
    value: "/dashboard"
  - type: element_visible
    selector: ".welcome-message"
  - type: no_console_errors
```

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | Yes | | Flow identifier |
| `url` | Yes | | Starting URL |
| `viewport_width` | No | `1280` | Browser viewport width |
| `viewport_height` | No | `720` | Browser viewport height |
| `steps` | No | `[]` | Ordered interaction steps |
| `assertions` | No | `[]` | Post-flow assertions |

---

## Step Actions

Each step has an `action` and optional parameters.

### fill

Fill an input field with a value. Clears existing content first.

```yaml
- action: fill
  selector: "input[name='email']"
  value: "test@example.com"
  timeout: 5000
```

### click

Click an element.

```yaml
- action: click
  selector: "button[type='submit']"
  timeout: 5000
```

### type

Type text character by character (useful for inputs with debounce handlers or autocomplete).

```yaml
- action: type
  selector: "#search-input"
  value: "query text"
```

### wait_for

Wait for an element to appear in the DOM.

```yaml
- action: wait_for
  selector: ".dashboard-content"
  timeout: 10000
```

### screenshot

Capture a screenshot and save it as an artifact.

```yaml
- action: screenshot
  name: "after_login"
```

### navigate

Navigate to a different URL.

```yaml
- action: navigate
  value: "http://localhost:3000/settings"
```

### select

Select an option in a `<select>` dropdown.

```yaml
- action: select
  selector: "#country"
  value: "US"
```

### hover

Hover over an element (useful for tooltips and dropdown menus).

```yaml
- action: hover
  selector: ".user-menu"
```

### wait

Wait for a fixed duration. Use sparingly -- prefer `wait_for` with a selector.

```yaml
- action: wait
  timeout: 2000
```

---

## Assertions

Assertions run after all steps complete. If any assertion fails, the flow is marked as failed.

### url_contains

Check that the current URL contains a substring.

```yaml
- type: url_contains
  value: "/dashboard"
```

### element_visible

Check that an element exists and is visible.

```yaml
- type: element_visible
  selector: ".welcome-message"
```

### no_console_errors

Check that no console errors were logged during the flow.

```yaml
- type: no_console_errors
```

### text_contains

Check that an element's text content contains a substring.

```yaml
- type: text_contains
  selector: "h1"
  value: "Welcome"
```

---

## Test Results

Each flow execution produces a `BrowserTestResult`:

```python
class BrowserTestResult(BaseModel):
    flow_name: str              # Name of the flow
    passed: bool                # Overall pass/fail
    steps_completed: int        # How many steps succeeded
    steps_total: int            # Total number of steps
    failure_step: int | None    # Index of the failing step (if any)
    failure_reason: str | None  # Why the step failed
    screenshots: list[str]     # Artifact IDs for captured screenshots
    console_errors: list[str]  # Console errors captured during the flow
    dom_snapshot: str | None    # Text-rasterized DOM (max 5000 chars)
    duration_ms: float          # Total execution time
```

### What the Agent Sees

When a browser test fails, the agent receives context like:

```
Browser test failed: login_flow
Step 3/5: Click "button[type='submit']"
Error: Element not found after 5000ms timeout
Console errors:
  - TypeError: Cannot read property 'email' of undefined
DOM snapshot: Login Page Welcome back Please enter your credentials Email Password Submit ...
```

This gives the agent enough information to diagnose the issue (the submit button is missing or has a different selector, and there is a JavaScript error in the form handler) and fix it without human intervention.

---

## Running Browser Tests

### From CLI

```bash
harness browser-test
```

### From a Hook

Trigger browser tests after UI file changes:

```json
{
    "name": "browser_test_after_ui_change",
    "event": "post_tool_call",
    "on_tools": ["file_write"],
    "script": "if git diff --name-only | grep -qE '\\.(jsx|tsx|css|html)$'; then python -m devharness.browser_testing.runner; fi && exit 0 || exit 2",
    "timeout": 120
}
```

### Programmatically

```python
from devharness.browser_testing.runner import BrowserTestRunner

runner = BrowserTestRunner(
    workspace_root="/path/to/project",
    artifacts_dir="/path/to/project/.devharness/artifacts",
)

# Run a single flow
result = await runner.run_flow(flow)

# Run from a YAML file
result = await runner.run_flow_from_file(".devharness/browser_tests/login_flow.yaml")
```

### Loading All Flows from a Directory

```python
from devharness.browser_testing.flows import load_flows_from_directory

flows = load_flows_from_directory(".devharness/browser_tests/")
for flow in flows:
    result = await runner.run_flow(flow)
    print(f"{flow.name}: {'PASS' if result.passed else 'FAIL'}")
```

---

## Screenshots and Artifacts

Screenshots are saved to the artifacts directory (default: `.devharness/artifacts/`):

```
.devharness/artifacts/
  login_flow_after_login.png
  login_flow_final.png
  signup_flow_failure_step_2.png
```

A final screenshot is captured after all steps complete (if the flow succeeds). On failure, a screenshot is captured at the point of failure.

Screenshots are referenced by path in the `BrowserTestResult.screenshots` field.

---

## DOM Snapshots

When a step fails, the runner captures the current page HTML and converts it to a text representation:

1. Strip `<script>` and `<style>` tags entirely.
2. Replace remaining HTML tags with spaces.
3. Collapse whitespace.
4. Truncate to 5000 characters.

This "rasterized" DOM gives the agent a text view of the page state at failure time, sufficient to understand layout and content without the full HTML noise.

---

## Console Error Capture

The runner captures all console warnings and errors during the flow:

```python
page.on("console", lambda msg: (
    console_errors.append(f"{msg.type}: {msg.text}")
    if msg.type in ("error", "warning")
    else None
))
page.on("pageerror", lambda err: console_errors.append(f"PageError: {err}"))
```

Console errors are included in the test result and injected into agent context on failure.

---

## Writing Effective Browser Tests

### Start Simple

Begin with a smoke test that just loads the page and checks for console errors:

```yaml
name: homepage_smoke
url: http://localhost:3000/
assertions:
  - type: element_visible
    selector: "body"
  - type: no_console_errors
```

### Test Critical Paths

Focus on the flows that matter most: login, signup, checkout, key CRUD operations.

### Use Reasonable Timeouts

The default timeout is 5000ms per step. Increase for slow-loading pages or network requests:

```yaml
- action: wait_for
  selector: ".data-loaded"
  timeout: 15000
```

### Name Your Screenshots

Named screenshots create readable artifact files:

```yaml
- action: screenshot
  name: "step_3_form_filled"
```

### Test Responsive Layouts

Create multiple flow files for different viewport sizes:

```yaml
# login_flow_mobile.yaml
name: login_flow_mobile
url: http://localhost:3000/login
viewport_width: 375
viewport_height: 812
steps:
  # same steps as desktop
```
