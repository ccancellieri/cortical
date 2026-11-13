---
name: chrome-complex-workflows
description: >
  Execute complex multi-step browser workflows in Google Chrome (job applications,
  social post drafting, multi-tab research, form filling, file uploads) via
  chrome-devtools-mcp and cortical-wiki Chrome tools with human-in-the-loop safety gates.
---

# Complex Chrome Workflows (`chrome-complex-workflows`)

## 1. Initialization & Discovery
1. Call `chrome_ensure_debug()` (from `cortical-wiki` MCP) to verify Chrome CDP `:9222` is active.
2. Use `tool-search` to load `chrome` MCP tools (`list_pages`, `new_page`, `navigate_page`, `take_snapshot`, `click`, `fill`, `fill_form`, `upload_file`, `wait_for`).
3. Never use `curl`, `wget`, or raw HTTP clients to scrape or submit forms (blocked by Cortical Egress Guard). Always drive the live Chrome session on `127.0.0.1:9222`.

## 2. Standard Execution Loop
- **Inspect first**: Call `take_snapshot` before clicking or filling so you use exact element `uid`s.
- **Job applications & forms**: Fill fields with `fill_form` / `fill`, attach CVs with `upload_file`, verify filled values via `take_snapshot`.
- **Social posts & drafts**: Compose content in the editor, verify formatting and links via `take_snapshot`.
- **Multi-tab research**: Open/navigate tabs, extract clean text with `chrome_read_active_page(mode="read")`, and cite exact URLs.

## 3. Mandatory Human-in-the-Loop Safety Gates
- **Pre-Submit Gate**: Stop BEFORE clicking final `Submit`, `Apply`, `Publish`, or `Pay` unless the user explicitly authorized automatic submission in the task prompt. Report `READY_FOR_REVIEW` with a summary of filled fields.
- **No Anti-Bot / Auth Bypass**: If a login, 2FA, payment page, or CAPTCHA appears, stop immediately and ask the user to complete it in the visible Chrome window.
