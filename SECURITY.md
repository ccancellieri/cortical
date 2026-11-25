# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| `0.3.x` (`main`) | Yes |
| `0.2.x` (`legacy-v0.2`) | No (archived) |

## Security Architecture & Guarantees

Cortical is engineered around a **zero-dependency, fail-closed, local-first** security posture:

1. **Zero External Runtime Dependencies:** `pyproject.toml` declares `dependencies = []` (Python 3.10+ standard library only). There are no third-party runtime packages, no transitive supply-chain tree, and no external CDN scripts in `docs/settings.html`.
2. **Fail-Closed Privacy Vault:** Documents classified as `max_security` or `fail_closed` are blocked from leaving the machine to remote cloud LLMs. Deterministic PII, secret, and OOXML/PDF metadata redaction runs offline in Python stdlib with a SHA-256 audit ledger.
3. **Zero Persistent Background Daemons:** The default MCP transport is `stdio`. Interactive Prompt Studio sessions (`cortical next`) bind an ephemeral `127.0.0.1:0` loopback socket protected by a 256-bit single-use token (`secrets.token_urlsafe(32)`), strict `Host`/`Origin` validation against DNS rebinding, and immediate `server_close()` on submission or timeout.
4. **No Secret Exfiltration in Containerized Inspection:** `python3 -m cortical.mcp_server` boots cleanly without any API keys, credentials, or outbound network calls.

## Reporting a Vulnerability

Please **do not** open a public GitHub Issue for security vulnerabilities.

1. Use [GitHub Private Vulnerability Reporting](https://github.com/ccancellieri/cortical/security/advisories/new) on `ccancellieri/cortical`.
2. Include reproduction steps, affected file or tool name, and expected vs. observed behavior.
3. Initial acknowledgement target: **within 48 hours**. Confirmed critical or privacy-leakage issues are prioritized for immediate patch and release notes disclosure.
