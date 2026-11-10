---
name: browser-use-playwright
description: >
  Optional Bash-invoked headless/background browser automation fallback using Playwright / browser-use
  when Chrome DevTools MCP is unavailable or when isolated headless sessions are required.
---

# Browser-Use / Playwright Skill (`browser-use-playwright`)

## Usage via Bash Tool
When isolated headless navigation, form extraction, or screenshot verification is required outside the active Chrome session, run the bundled helper script:

```bash
.venv/bin/python .pi/skills/browser-use-playwright/scripts/playwright_runner.py \
  --url "https://example.com" \
  --action "snapshot"
```

## Supported Actions
- `snapshot`: Extracts clean semantic markdown + interactive selectors (`[role]`, `input`, `button`, `a`) without noise.
- `eval`: Executes a deterministic JS snippet in an isolated headless context and returns JSON.
