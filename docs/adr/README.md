# Cortical Architecture Decision Records (ADRs)

This directory is Cortical's in-repo Architecture Decision Record (ADR) index, synchronized 1:1 with GitHub Issues (`label: adr`) on [`ccancellieri/cortical`](https://github.com/ccancellieri/cortical/issues).

| ID | Title | Scope | Status | GitHub Issue |
| --- | --- | --- | --- | --- |
| [ADR-001](./ADR-001-zero-server-dashboard-hydration.md) | Zero-Server Dashboard State Hydration & Client-Machine Bridge | Canonical Default | Accepted | #20 |
| [ADR-002](./ADR-002-progressive-disclosure-config-diff-rollback.md) | Progressive Disclosure & Safe Config Diff/Rollback UX | Canonical Default | Accepted | #21 |
| [ADR-003](./ADR-003-client-side-service-probing-harness-lifecycle.md) | Client-Side Service Probing & 8-Harness Lifecycle Management | Canonical Default | Accepted | #22 |
| [ADR-004](./ADR-004-unified-repo-github-memory-sync.md) | Unified In-Repo ADR & GitHub Issues Project Memory Sync | Governance | Accepted | #23 |
| [ADR-005](./ADR-005-optional-local-http-control-plane-and-wiki-store.md) | Opt-In Local HTTP Control Plane API & Multi-Tenant Wiki Store | Opt-In `--serve` | Accepted | #10 |
| [ADR-006](./ADR-006-dirty-state-settings-embedding-guardrail-and-async-crawl.md) | Dirty-State Settings Validation, Embedding Guardrail & Async Crawl | Opt-In `--serve` | Accepted | #11 |
| [ADR-007](./ADR-007-workspace-autodiscovery-ide-integration-and-control-plane-ssot.md) | Zero-Friction Workspace Auto-Discovery, IDE Integration & Control Plane SSOT | Core DX / CLI | Accepted | #29 |
| [ADR-008](./ADR-008-atomic-dashboard-plan-and-cortical-apply.md) | Atomic Dashboard Plan Bundle (`cortical-plan/v1`), `cortical apply` & Guided Service Repair | Canonical Default | Accepted | #30 |
| [ADR-010](./ADR-010-composable-control-plane-wedge-and-capability-roadmap.md) | Composable Control Plane Wedge & Top 5 Capability Roadmap | Strategy / Architecture | Accepted | #36 |
| [ADR-011](./ADR-011-mcp-2026-tool-annotations-output-schema-and-registry-standard.md) | MCP 2026 Tool Annotations, Output Schemas, 7-Tool Contract & Registry Metadata Standard | MCP / Protocols | Accepted | #37 |
| [ADR-012](./ADR-012-upstream-ecosystem-hooks-and-contribution-contract.md) | Upstream Ecosystem Hooks & High-Leverage OSS Contribution Contract | Ecosystem / Upstream | Accepted | #38 |
| [ADR-013](./ADR-013-hybrid-local-first-remote-orchestrator-architecture.md) | Hybrid Local-First + Remote Orchestrator Architecture & 8-Harness Mapping | Core / Harnesses | Accepted | #54 |
| [ADR-014](./ADR-014-dynamic-hardware-ceiling-auto-ctx-and-adaptive-timeouts.md) | Dynamic Hardware-Ceiling Context Window (`auto_ctx`) & Adaptive Timeout Sizing | Hardware / Models | Accepted | #55 |
| [ADR-015](./ADR-015-zero-leakage-remote-orchestrator-egress-defense.md) | Zero-Leakage Remote Orchestrator Egress Defense (`fail_closed` Vault + 3-Channel Isolation) | Privacy / Security | Accepted | #56 |
| [ADR-016](./ADR-016-release-readiness-zero-llm-tier-and-multi-runner-standard.md) | Release Readiness Standard — 2-Tier Zero-LLM Stdlib Transparency, Multi-Runner Generalization & Safe `--dry-run` Onboarding | Release / Architecture | Accepted | #58 |
| [ADR-017](./ADR-017-interactive-prompt-elicitor-and-autonomous-loop.md) | Cortical Prompt Studio, Ephemeral Loopback Browser Elicitor (`cortical next`) & 5-Trigger Autonomous Loop | Composers / HCI / Harnesses | Accepted | #60 |
| [ADR-018](./ADR-018-colleague-second-brain-bulk-privatization-and-smart-escalation.md) | Colleague Second Brain, Bulk Disk Privatization, Knowledge Reconciliation & Smart Local-to-Remote Escalation | Privacy / Second Brain / HCI | Accepted | #65 |
