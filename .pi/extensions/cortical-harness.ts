/**
 * Cortical Channel 3 Harness Extension for `pi` (@earendil-works/pi-coding-agent)
 * Copyright 2026 Carlo Cancellieri — Apache-2.0
 *
 * Provides:
 *  - Deterministic Channel 3 pre-send interception (`/private`, `@file` paths) via `cortical intercept`
 *  - On-demand slash commands (`/doctor`, `/ingest`, `/compress`, `/roi`) calling local zero-server CLI
 */

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function resolveCorticalRuntime(): { pythonBin: string; pythonPath: string } {
  const candidates = [
    process.env.CORTICAL_ROOT,
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../.."),
    process.cwd(),
  ].filter(Boolean) as string[];

  for (const root of candidates) {
    const srcDir = path.join(root, "src");
    const venvPy = path.join(root, ".venv", "bin", "python");
    if (existsSync(srcDir)) {
      return {
        pythonBin: process.env.CORTICAL_PYTHON || (existsSync(venvPy) ? venvPy : "python3"),
        pythonPath: process.env.CORTICAL_PYTHONPATH || srcDir,
      };
    }
  }
  return {
    pythonBin: process.env.CORTICAL_PYTHON || "python3",
    pythonPath: process.env.CORTICAL_PYTHONPATH || "./src",
  };
}

function invokeCorticalJSON(args: string[]): Record<string, unknown> {
  const { pythonBin, pythonPath } = resolveCorticalRuntime();
  const out = execFileSync(pythonBin, ["-m", "cortical.cli", ...args], {
    encoding: "utf-8",
    env: { ...process.env, PYTHONPATH: pythonPath },
    timeout: 15000,
  });
  return JSON.parse(out) as Record<string, unknown>;
}

export default function corticalHarness(pi: ExtensionAPI) {
  pi.registerCommand("cortical-doctor", {
    description: "Inspect hardware tier, composed OSS tools, and variable-quant local models",
    handler: async (_args, ctx) => {
      const res = invokeCorticalJSON(["doctor", "--json"]);
      ctx.ui?.notify?.(JSON.stringify(res.hardware, null, 2).slice(0, 1200), "info");
    },
  });

  pi.registerCommand("ingest", {
    description: "Ingest & sanitize a file into Cortical Privacy Vault (/ingest <path> [auto|fail_closed|fail_open])",
    handler: async (args, ctx) => {
      const parts = args.trim().split(/\s+/).filter(Boolean);
      if (parts.length === 0) {
        ctx.ui?.notify?.("Usage: /ingest <path> [auto|fail_closed|fail_open]", "warning");
        return;
      }
      const policy = ["auto", "fail_closed", "fail_open"].includes(parts[1] || "") ? parts[1] : "auto";
      const res = invokeCorticalJSON(["ingest", parts[0], "--policy", policy, "--json"]);
      ctx.ui?.notify?.(`Vault ${String(res.uri)} (${String(res.resolved_policy)}, ${String(res.format_used)})`, "info");
    },
  });

  pi.registerCommand("roi", {
    description: "Show zero-cloud-token Cortical ROI report",
    handler: async (_args, ctx) => {
      const res = invokeCorticalJSON(["roi", "--json"]);
      ctx.ui?.notify?.(JSON.stringify(res, null, 2).slice(0, 1000), "info");
    },
  });

  // Channel 3: Intercept local file attachments on prompts before dispatch to remote LLMs
  pi.on("before_agent_start", async (event, ctx) => {
    const prompt = String((event as { prompt?: string }).prompt || "");
    const attachedPaths = Array.from(prompt.matchAll(/@([^\s,;]+)/g))
      .map((m) => m[1])
      .filter((p) => !p.startsWith("private:") && existsSync(p));

    if (attachedPaths.length === 0) return;

    const cliArgs = ["intercept", "--harness", "pi", "--prompt", prompt];
    for (const f of attachedPaths) cliArgs.push("--file", f);

    const res = invokeCorticalJSON(cliArgs);
    if (res.requires_approval && ctx.ui?.confirm) {
      const aliases = ((res.vault_aliases as string[]) || []).join(", ");
      const ok = await ctx.ui.confirm("Cortical Privacy Vault", `Send sanitized context for @private:${aliases}?`);
      if (!ok) {
        return { cancel: true };
      }
    }
    if (typeof res.proposed_remote_prompt === "string" && res.proposed_remote_prompt.trim()) {
      return { prompt: res.proposed_remote_prompt };
    }
  });
}
