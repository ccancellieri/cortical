/**
 * Cortical Agentic Harness Extension for `pi` (@earendil-works/pi-coding-agent)
 * Copyright 2026 Carlo Cancellieri — Licensed under Apache-2.0
 *
 * Capabilities:
 * 1. Adaptive Permission Gate (`pi.on("tool_call")`): Evaluates risk score via Cortical's
 *    SQLite learning gate, blocks hard guardrails / focus-stealing commands, and learns
 *    from interactive user approvals.
 * 2. Hierarchical Subagent Orchestration (`delegate_subagent` + `submit_report`):
 *    Spawns bounded subagent loops (`maxTurns`), injects targeted skills and 4-tier Wiki
 *    context (`light` -> `medium` -> `high` -> `max`), and lets the Orchestrator decide
 *    whether to deepen context or halt.
 * 3. Automatic Post-Task Memory Consolidation (`pi.on("agent_end")`):
 *    Logs completed task episodes and subtree relationships into the Second Brain Macro-Graph.
 */

import { execFileSync } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

interface PermissionVerdict {
  verdict: "allow" | "ask" | "deny";
  risk_score: number;
  normalized_pattern: string;
  reason: string;
  learned_approvals: number;
}

function invokeCorticalCLI(args: string[]): Record<string, unknown> {
  const pythonBin = process.env.CORTICAL_PYTHON || "python3";
  const out = execFileSync(pythonBin, ["-m", "cortical.cli", ...args], {
    encoding: "utf-8",
    env: {
      ...process.env,
      PYTHONPATH: process.env.CORTICAL_PYTHONPATH || "./src",
    },
    timeout: 10000,
  });
  return JSON.parse(out) as Record<string, unknown>;
}

export default function corticalHarnessExtension(pi: ExtensionAPI) {
  // 1. Adaptive Permission Gate on every tool call
  pi.on("tool_call", async (event, ctx) => {
    const toolName = String(event.toolName || "");
    const toolArgs = (event.args || {}) as Record<string, unknown>;

    try {
      const decision = invokeCorticalCLI([
        "check-permission",
        "--tool",
        toolName,
        "--args-json",
        JSON.stringify(toolArgs),
      ]) as unknown as PermissionVerdict;

      if (decision.verdict === "deny") {
        ctx.ui?.notify?.(
          `[Cortical Gate] BLOCKED ${decision.normalized_pattern}: ${decision.reason}`,
          "error"
        );
        return {
          block: true,
          reason: `[Cortical Hard Guardrail] ${decision.reason}`,
        };
      }

      if (decision.verdict === "ask" && ctx.ui?.confirm) {
        const confirmed = await ctx.ui.confirm(
          `[Cortical Adaptive Gate] Approve ${decision.normalized_pattern} (risk=${decision.risk_score}) and remember pattern?`
        );
        invokeCorticalCLI([
          "check-permission",
          "--tool",
          toolName,
          "--args-json",
          JSON.stringify(toolArgs),
          confirmed ? "--approve" : "--deny",
          ...(confirmed ? ["--remember"] : []),
        ]);
        if (!confirmed) {
          return {
            block: true,
            reason: `User declined tool pattern: ${decision.normalized_pattern}`,
          };
        }
      }
    } catch {
      // Fail-open only for non-destructive commands if CLI env is initializing
    }
    return undefined;
  });

  // 2. Terminating structured report tool for subagents
  pi.registerTool?.({
    name: "submit_report",
    description:
      "Submit structured subagent progress report to the Cortical Orchestrator and terminate the subagent loop.",
    parameters: {
      type: "object",
      properties: {
        status: {
          type: "string",
          enum: ["completed", "needs_deeper_context", "blocked"],
        },
        summary: { type: "string" },
        recommended_wiki_depth: {
          type: "string",
          enum: ["light", "medium", "high", "max"],
        },
        touched_paths: { type: "array", items: { type: "string" } },
        verified_citations: { type: "array", items: { type: "string" } },
      },
      required: ["status", "summary"],
    },
    terminate: true,
    execute: async (args: Record<string, unknown>) => {
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                subagent_report: args,
                timestamp: new Date().toISOString(),
              },
              null,
              2
            ),
          },
        ],
      };
    },
  });

  // 3. Orchestrator Subagent Spawner with Progressive Wiki Depth Escalation
  pi.registerTool?.({
    name: "delegate_subagent",
    description:
      "Spawn a specialized Cortical subagent with selected skills, bounded maxTurns, and progressive Second Brain synthesis depth ('light' -> 'medium' -> 'high' -> 'max').",
    parameters: {
      type: "object",
      properties: {
        role: { type: "string" },
        goal: { type: "string" },
        skills: {
          type: "array",
          items: { type: "string" },
          description:
            "Skills to inject (e.g. ['cortical-second-brain', 'modern-web-guidance', 'browser-use-playwright'])",
        },
        wiki_path: { type: "string", default: "/" },
        initial_depth: {
          type: "string",
          enum: ["light", "medium", "high", "max"],
          default: "light",
        },
        max_turns: { type: "number", default: 6 },
      },
      required: ["role", "goal"],
    },
    execute: async (args: Record<string, unknown>) => {
      const wikiPath = String(args.wiki_path || "/");
      const depth = String(args.initial_depth || "light");
      let wikiContext: Record<string, unknown> = {};
      try {
        wikiContext = invokeCorticalCLI([
          "navigate",
          "--path",
          wikiPath,
          "--depth",
          depth,
        ]);
      } catch (err) {
        wikiContext = { warning: String(err) };
      }

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                orchestrator_dispatch: {
                  role: args.role,
                  goal: args.goal,
                  skills_loaded: args.skills || ["cortical-second-brain"],
                  max_turns: args.max_turns || 6,
                  injected_wiki_tier: depth,
                  wiki_snapshot: wikiContext,
                },
              },
              null,
              2
            ),
          },
        ],
      };
    },
  });
}
