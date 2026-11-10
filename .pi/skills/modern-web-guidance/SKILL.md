---
name: modern-web-guidance
description: >
  Resilient modern web automation, DOM inspection, SPA/React synthetic event handling,
  accessibility-first selector strategy, and strict zero-focus-stealing browser execution
  using Chrome DevTools MCP (`chrome-devtools-mcp`).
---

# Modern Web Guidance Skill (`modern-web-guidance`)

## 1. Zero Focus-Stealing Rule (Background Execution Only)
- **NEVER** bring the browser window to the foreground (`AXRaise`, `set frontmost to true`, or `window.focus()`) while the user is working.
- Operate exclusively on background tabs via `chrome-devtools-mcp` or headless/background sessions.

## 2. 3-Strategy Interaction Resilience (Never Loop on the Same Failure)
When automating modern SPAs (React, Next.js, Workday, Oracle, custom portals), never repeat a failing click/fill action identically:
- **Attempt 1 — Semantic Accessibility / DOM Snapshot:** Use `take_snapshot` + `click` / `fill` on ARIA roles (`role="button"`, `aria-label`, `name`).
- **Attempt 2 — React Synthetic Value Setter (`evaluate_script`):** Use `Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(el, val)` followed by `new Event('input', { bubbles: true })` and `new Event('change', { bubbles: true })`.
- **Attempt 3 — Sequenced Keyboard Navigation:** Dispatch `focus` + `press_key` (`Tab`, `Space`, `ArrowDown`, `Enter`).
- **Hard Stop at Attempt 3:** If the element still fails validation, stop immediately and report to the Orchestrator via `submit_report(status="blocked")`.
