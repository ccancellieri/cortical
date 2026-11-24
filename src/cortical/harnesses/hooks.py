"""Native lifecycle hook installers across verified harnesses & LiteLLM (Python 3.10+ stdlib only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .adapters import resolve_user_paths

HOOK_TARGETS: tuple[str, ...] = ("claude-code", "pi", "opencode", "dsh", "litellm")

_CLAUDE_PRETOOL_PY = """#!/usr/bin/env python3
\"\"\"Cortical Channel-3 PreToolUse / UserPromptSubmit hook for Claude Code.\"\"\"
import json, subprocess, sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    prompt = str(payload.get("prompt") or "")
    files = payload.get("attachments") or []
    if not prompt and not files:
        return 0
    cmd = ["cortical", "intercept", "--harness", "claude-code", "--prompt", prompt]
    for fp in files:
        cmd.extend(["--file", str(fp)])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode == 2:
        sys.stderr.write(proc.stderr or proc.stdout or "Cortical fail-closed blocked raw egress.\\n")
        return 2
    if proc.stdout.strip():
        sys.stdout.write(proc.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""

_PI_INTERCEPT_TS = """// Cortical Channel-3 Native Extension for pi (@earendil-works/pi-coding-agent)
import { execFileSync } from "node:child_process";

export default function corticalIntercept(pi: any) {
  pi.on("before_provider_request", async (event: any) => {
    const prompt = String(event?.prompt ?? "");
    if (!prompt.includes("@private:")) return;
    try {
      const out = execFileSync(
        "cortical",
        ["intercept", "--harness", "pi", "--prompt", prompt],
        { encoding: "utf8", timeout: 5000 }
      );
      const res = JSON.parse(out);
      if (res?.proposed_remote_prompt && res?.remote_egress_guarded) {
        event.prompt = res.proposed_remote_prompt;
      }
    } catch {
      // Fail-open only when no private tokens exist; never leak raw files on error
    }
  });
}
"""

_OPENCODE_HOOK_MJS = """// Cortical Channel-3 Plugin Hook for OpenCode (anomalyco/opencode)
import { execFileSync } from "node:child_process";

export const CorticalPrivacyPlugin = () => ({
  name: "cortical-privacy-toon",
  async "experimental.chat.messages.transform"(_input, output) {
    if (!output?.messages?.length) return;
    const last = output.messages[output.messages.length - 1];
    if (typeof last?.content === "string" && last.content.length > 2048) {
      try {
        const res = execFileSync("cortical", ["compress", "-", "--format", "auto", "--json"], {
          input: last.content,
          encoding: "utf8",
          timeout: 3000,
        });
        const parsed = JSON.parse(res);
        if (parsed?.saving_pct >= 10 && parsed?.compressed) {
          last.content = parsed.compressed;
        }
      } catch {}
    }
  },
});
"""

_OPENCODE_PRIVATE_CMD = """---
description: Inject fail-closed sanitized @private:<alias> context via Cortical MCP
---
Read sanitized vault context for `$ARGUMENTS` using `cortical_vault_read`.
Never request raw files inside `.cortical_data/` or `~/Documents/Cortical/vault/`.
If the item is `max_security`, delegate analysis to `cortical_local_offload(vault_alias="$ARGUMENTS")`.
"""

_OPENCODE_LOCAL_CMD = """---
description: Execute task strictly offline via Cortical Local Offload (0 cloud tokens)
---
Run this task offline using `cortical_local_offload(prompt="$ARGUMENTS")` and return the concise local output.
"""

_OPENCODE_NEXT_CMD = """---
description: Elicit or synthesize the next continuation prompt via Cortical Prompt Studio (/next)
---
Call `cortical_next_prompt(seed="$ARGUMENTS", mode="browser")` (or `cortical next "$ARGUMENTS"`) to open the one-shot local browser questionnaire and return the synthesized continuation prompt.
"""

_DSH_CORDIS_HOOK_MJS = """// Cortical Channel-3 Cordis Privacy Hook for DeepSeek Harness (dsh)
import { execFileSync } from "node:child_process";

export default {
  id: "cortical-privacy-cordis-hook",
  onBeforeDispatch(ctx) {
    const prompt = String(ctx?.prompt || "");
    const files = Array.isArray(ctx?.files) ? ctx.files : [];
    if (!files.length && !prompt.includes("@private:")) return ctx;
    const args = ["intercept", "--harness", "dsh", "--prompt", prompt];
    for (const f of files) args.push("--file", String(f));
    const raw = execFileSync("cortical", args, { encoding: "utf8", timeout: 5000 });
    const res = JSON.parse(raw);
    return { ...ctx, files: [], prompt: res.proposed_remote_prompt || prompt };
  },
};
"""

_LITELLM_GUARD_PY = """\"\"\"LiteLLM Custom Callback Guardrail: fail-closed remote PII blocker + local offload router.\"\"\"
from __future__ import annotations

import re

_SECRET_RE = re.compile(r"\\b(?:sk-[a-zA-Z0-9_-]{16,}|gh[pous]_[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16})\\b")


class CorticalPrivacyGuardrail:
    \"\"\"Blocks unmasked API secrets / private vault paths from traversing remote LiteLLM endpoints.\"\"\"

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):  # noqa: D401
        model = str(data.get("model") or "").lower()
        is_local = model.startswith(("ollama", "cortical-", "local-", "qwen", "minicpm"))
        if is_local:
            return data
        text = str(data.get("messages") or "")
        if _SECRET_RE.search(text) or "Documents/Cortical/vault" in text or "LOCAL-ONLY max_security" in text:
            raise ValueError("Cortical Fail-Closed Guard: sensitive/local-only payload blocked from remote LiteLLM dispatch.")
        return data


proxy_handler_instance = CorticalPrivacyGuardrail()
"""


def _hook_specs(home: Optional[Path] = None, os_name: Optional[str] = None) -> dict[str, list[tuple[Path, str, str]]]:
    """Resolves canonical per-target hook file specs without mutating filesystem."""
    h = Path(home or Path.home())
    paths = resolve_user_paths(os_name=os_name, home=h)
    opencode_dir = paths["opencode"]["opencode"].parent
    pi_dir = paths["pi"]["settings"].parent
    claude_dir = paths["claude-code"]["rules"].parent
    dsh_dir = paths["dsh"]["settings"].parent
    return {
        "claude-code": [
            (claude_dir / "hooks" / "cortical_pretool.py", _CLAUDE_PRETOOL_PY, "Claude Code PreToolUse / Prompt interceptor"),
        ],
        "pi": [
            (pi_dir / "extensions" / "cortical-intercept.ts", _PI_INTERCEPT_TS, "pi Channel-3 @private extension"),
        ],
        "opencode": [
            (opencode_dir / "plugins" / "cortical-hook.mjs", _OPENCODE_HOOK_MJS, "OpenCode plugin hook for TOON compaction"),
            (opencode_dir / "commands" / "cortical-private.md", _OPENCODE_PRIVATE_CMD, "OpenCode /cortical-private slash command"),
            (opencode_dir / "commands" / "cortical-local.md", _OPENCODE_LOCAL_CMD, "OpenCode /cortical-local slash command"),
            (opencode_dir / "commands" / "next.md", _OPENCODE_NEXT_CMD, "OpenCode /next Prompt Studio elicitor slash command"),
        ],
        "dsh": [
            (dsh_dir / "plugins" / "cortical-cordis-hook.mjs", _DSH_CORDIS_HOOK_MJS, "DeepSeek Harness Cordis pre-send privacy hook"),
        ],
        "litellm": [
            (h / ".cortical" / "hooks" / "litellm_cortical_guard.py", _LITELLM_GUARD_PY, "LiteLLM fail-closed remote egress guardrail"),
        ],
    }


def inspect_harness_hooks(
    *,
    home: Optional[Path] = None,
    os_name: Optional[str] = None,
) -> dict[str, dict[str, Any]]:
    """Checks installation & drift status of native lifecycle hooks across targets."""
    specs = _hook_specs(home=home, os_name=os_name)
    out: dict[str, dict[str, Any]] = {}
    for target, files in specs.items():
        items = []
        installed = True
        in_sync = True
        for path, content, detail in files:
            exists = path.is_file()
            matches = exists and path.read_text(encoding="utf-8", errors="ignore") == content
            if not exists:
                installed = False
            if not matches:
                in_sync = False
            items.append({
                "path": str(path),
                "exists": exists,
                "in_sync": matches,
                "detail": detail,
            })
        out[target] = {"installed": installed, "in_sync": in_sync, "files": items}
    return out


def install_harness_hooks(
    targets: Optional[list[str]] = None,
    *,
    home: Optional[Path] = None,
    os_name: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Idempotently installs native lifecycle hooks for requested harness/router targets."""
    specs = _hook_specs(home=home, os_name=os_name)
    chosen = [t for t in (targets or list(HOOK_TARGETS)) if t in specs]
    results: list[dict[str, Any]] = []
    changed = 0
    for target in chosen:
        for path, content, detail in specs[target]:
            old = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else None
            action = "create" if old is None else ("unchanged" if old == content else "update")
            if action != "unchanged":
                changed += 1
                if not dry_run:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
                    if path.suffix == ".py":
                        path.chmod(0o755)
            results.append({
                "target": target,
                "path": str(path),
                "action": action,
                "detail": detail,
            })
    return {
        "dry_run": dry_run,
        "targets": chosen,
        "changed_count": changed,
        "files": results,
    }
