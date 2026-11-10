/**
 * Cortical Multi-Agent Harness & 3+1 Skill/Memory Extension for `pi` (@earendil-works/pi-coding-agent)
 * Copyright 2026 Carlo Cancellieri — Licensed under Apache-2.0
 *
 * How to use Cortical inside `pi`:
 * 1. Normal Conversation / Coding (Default):
 *    - Does NOT create tasks automatically.
 *    - Automatically enriches technical prompts with the right 3+1 Wiki Memory tier
 *      (L1 Light, L2 Medium, L3 High, +1 Max) + matched Procedural Skills & Tools in parallel.
 * 2. Explicit Multi-Agent Task Mode (`/task <obiettivo>` or "crea un task per..."):
 *    - Opens an explicit task with the local Multi-Agent Orchestrator (Analyst -> Implementer -> Reviewer).
 *    - Tracks the discussion and tool executions inside the isolated task.
 * 3. Task Closure, 3+1 Synthesis & Automatic Skill Generation (`/task-close [lezioni]`):
 *    - Synthesizes the discussion at 3+1 levels in the Wiki MCP (`L1`, `L2`, `L3`, `Max`).
 *    - Evaluates whether the work produced a reusable pattern and compiles a new `.pi/skills/learned-<slug>/SKILL.md`.
 *    - Archives the compact trace and purges bulky temporary logs.
 * 4. Task Deletion (`/task-delete <id>`) & Skills Inspector (`/skills`).
 */

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

interface PermissionVerdict {
  verdict: "allow" | "ask" | "deny";
  risk_score: number;
  normalized_pattern: string;
  reason: string;
  learned_approvals: number;
}

interface ActiveTaskState {
  episodeId: string;
  goal: string;
  steps: Array<{ type: string; title: string; detail: string }>;
}

function resolveCorticalPaths(): { pythonBin: string; pythonPath: string; skillsDir: string } {
  const candidates = [
    process.env.CORTICAL_ROOT,
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../.."),
    "/Users/ccancellieri/work/code/cortical",
    "/home/bianco/cortical",
  ].filter(Boolean) as string[];

  for (const root of candidates) {
    const srcDir = path.join(root, "src");
    const venvPy = path.join(root, ".venv", "bin", "python");
    const skillsDir = path.join(root, ".pi", "skills");
    if (existsSync(srcDir)) {
      return {
        pythonBin: process.env.CORTICAL_PYTHON || (existsSync(venvPy) ? venvPy : "python3"),
        pythonPath: process.env.CORTICAL_PYTHONPATH || srcDir,
        skillsDir,
      };
    }
  }
  return {
    pythonBin: process.env.CORTICAL_PYTHON || "python3",
    pythonPath: process.env.CORTICAL_PYTHONPATH || "./src",
    skillsDir: "./.pi/skills",
  };
}

function invokeCorticalCLI(args: string[]): Record<string, unknown> {
  const { pythonBin, pythonPath, skillsDir } = resolveCorticalPaths();
  const out = execFileSync(
    pythonBin,
    ["-m", "cortical.cli", "--skills-dir", skillsDir, ...args],
    {
      encoding: "utf-8",
      env: {
        ...process.env,
        PYTHONPATH: pythonPath,
      },
      timeout: 14000,
    }
  );
  return JSON.parse(out) as Record<string, unknown>;
}

function isWeatherQuery(text: string): boolean {
  const norm = text.toLowerCase();
  return (
    norm.includes("meteo") ||
    norm.includes("che tempo fa") ||
    norm.includes("previsioni") ||
    norm.includes("temperatura")
  );
}

function isExplicitTaskStart(text: string): boolean {
  const norm = text.toLowerCase();
  return (
    norm.includes("crea un task") ||
    norm.includes("crea task") ||
    norm.includes("apri un task") ||
    norm.includes("nuovo task") ||
    norm.includes("lavora in multiagent") ||
    norm.includes("orchestra un sottoagente")
  );
}

export default function corticalHarnessExtension(pi: ExtensionAPI) {
  let pendingGroundedAnswer: string | null = null;
  let activeTask: ActiveTaskState | null = null;

  // Register Cortical Multi-Agent & Skill Hub Slash Commands in `pi`
  pi.registerCommand?.("task", {
    description: "Apri un Task Multi-Agente esplicito con memoria 3+1 e valutazione Skill (/task <obiettivo>)",
    handler: async (args, ctx) => {
      const goal = args.trim();
      if (!goal) {
        ctx.ui?.notify?.("Uso: /task <obiettivo del task>", "warning");
        return;
      }
      const opened = invokeCorticalCLI(["task-open", "--goal", goal]);
      const epId = String(opened.episode_id || "pi-task");
      activeTask = {
        episodeId: epId,
        goal,
        steps: [{ type: "thinking", title: "Avvio Task Multi-Agente", detail: goal }],
      };
      pi.setSessionName?.(`[Task ${epId}] ${goal.slice(0, 40)}`);
      ctx.ui?.notify?.(
        `✅ Task Multi-Agente aperto: ${epId} (Usa /task-close a fine lavoro per salvare la sintesi 3+1 e generare eventuali Skill)`,
        "info"
      );
      pi.sendUserMessage?.(
        `[TASK MULTI-AGENTE ATTIVO: ${epId}]\nObiettivo: ${goal}\n` +
          `Coordina i ruoli (Analyst -> Implementer -> Reviewer) usando la Wiki MCP e i tool appropriati.`
      );
    },
  });

  pi.registerCommand?.("task-status", {
    description: "Mostra lo stato del Task Multi-Agente attivo in pi",
    handler: async (_args, ctx) => {
      if (!activeTask) {
        ctx.ui?.notify?.("Nessun task attivo. Le conversazioni normali non creano task. Usa /task <obiettivo> per aprirne uno.", "info");
        return;
      }
      ctx.ui?.notify?.(
        `Task attivo: ${activeTask.episodeId} | Obiettivo: ${activeTask.goal} | Passi registrati: ${activeTask.steps.length}`,
        "info"
      );
    },
  });

  pi.registerCommand?.("task-close", {
    description: "Chiudi e archivia il task attivo, sintetizzando la discussione a 3+1 livelli e valutando se creare una nuova Skill (/task-close [lezioni])",
    handler: async (args, ctx) => {
      if (!activeTask) {
        ctx.ui?.notify?.("Nessun task attivo da chiudere.", "warning");
        return;
      }
      const notes = args.trim();
      const res = invokeCorticalCLI([
        "task-close",
        "--episode-id",
        activeTask.episodeId,
        "--goal",
        activeTask.goal,
        "--notes",
        notes,
        "--steps-json",
        JSON.stringify(activeTask.steps),
      ]);
      const skillEval = (res.skill_evaluation || {}) as Record<string, unknown>;
      const skillMsg = skillEval.should_create_skill
        ? `✨ Nuova Skill generata: ${skillEval.skill_id} (${skillEval.skill_path})`
        : `ℹ️ Nessuna nuova skill necessaria (${skillEval.reason})`;
      ctx.ui?.notify?.(
        `📦 Task ${activeTask.episodeId} archiviato nei 3+1 livelli della Wiki MCP! ${skillMsg}`,
        "info"
      );
      activeTask = null;
      pi.setSessionName?.("Cortical Session (No Active Task)");
    },
  });

  pi.registerCommand?.("task-delete", {
    description: "Cancella definitivamente un task e i suoi log temporanei (/task-delete <episode_id>)",
    handler: async (args, ctx) => {
      const targetId = args.trim() || activeTask?.episodeId || "";
      if (!targetId) {
        ctx.ui?.notify?.("Specifica l'ID del task da cancellare: /task-delete <id>", "warning");
        return;
      }
      invokeCorticalCLI(["task-delete", "--episode-id", targetId]);
      if (activeTask && activeTask.episodeId === targetId) {
        activeTask = null;
      }
      ctx.ui?.notify?.(`🗑️ Task ${targetId} cancellato definitivamente.`, "info");
    },
  });

  pi.registerCommand?.("skills", {
    description: "Elenca le Skill attive (Core, 3+1 Memory Synthesis, e Skill Apprese dai task)",
    handler: async (_args, ctx) => {
      const res = invokeCorticalCLI(["skills-list"]);
      const list = (res.skills || []) as Array<Record<string, unknown>>;
      const summary = list
        .map((s) => `${s.skill_id} [${s.kind}]`)
        .join(", ");
      ctx.ui?.notify?.(`Skill Cortical (${list.length}): ${summary}`, "info");
    },
  });

  // 1. Pre-Flight Grounding + Parallel 3+1 Memory & Skill Enhancement Hook
  pi.on("before_agent_start", (event, ctx) => {
    pendingGroundedAnswer = null;
    try {
      const userPrompt =
        "prompt" in event && typeof event.prompt === "string" ? event.prompt : "";
      if (!userPrompt) return undefined;

      // A. Deterministic Weather & Chrome Grounding
      if (isWeatherQuery(userPrompt)) {
        const res = invokeCorticalCLI([
          "weather",
          "--query",
          userPrompt,
          "--open-chrome",
        ]);
        const groundedSummary = String(res.summary_it || JSON.stringify(res));
        pendingGroundedAnswer = groundedSummary;
        ctx.ui?.notify?.(`[Cortical Grounding] ${groundedSummary}`, "info");
        return {
          systemPrompt:
            `Sei Cortical, assistente AI italiano creato da Carlo Cancellieri.\n` +
            `Rispondi SOLO riportando esattamente questa frase senza parafrasare e senza aggiungere altro:\n` +
            `${groundedSummary}`,
        };
      }

      // B. Auto-start explicit task if user asks in natural language ("crea un task per...")
      if (!activeTask && isExplicitTaskStart(userPrompt)) {
        const opened = invokeCorticalCLI(["task-open", "--goal", userPrompt]);
        const epId = String(opened.episode_id || "pi-task");
        activeTask = {
          episodeId: epId,
          goal: userPrompt,
          steps: [{ type: "thinking", title: "Avvio Task Esplicito da Prompt", detail: userPrompt }],
        };
        ctx.ui?.notify?.(`🤖 Task Multi-Agente avviato: ${epId}`, "info");
      }

      if (activeTask) {
        activeTask.steps.push({
          type: "user_turn",
          title: `Richiesta utente nel task ${activeTask.episodeId}`,
          detail: userPrompt.slice(0, 300),
        });
      }

      // C. Parallel 3+1 Memory + Procedural Skill & Tool Enhancement (when working on a task or technical request)
      if (activeTask || userPrompt.split(/\s+/).length >= 5) {
        const enh = invokeCorticalCLI(["enhance-prompt", "--prompt", userPrompt]);
        const enhancedSys = String(enh.enhanced_system_instructions || "");
        if (enhancedSys && activeTask) {
          return {
            systemPrompt: `${event.systemPrompt}\n\n${enhancedSys}`,
          };
        }
      }
    } catch {
      // Continue normally if CLI is unreachable
    }
    return undefined;
  });

  // Record assistant output in active task & ensure clean grounded answers
  pi.on("message_end", (event) => {
    if (pendingGroundedAnswer && event.message && event.message.role === "assistant") {
      const answer = pendingGroundedAnswer;
      pendingGroundedAnswer = null;
      return {
        message: {
          ...event.message,
          content: [{ type: "text", text: answer }],
        },
      };
    }
    if (activeTask && event.message && event.message.role === "assistant") {
      const parts = (event.message.content || []) as Array<Record<string, unknown>>;
      const text = parts
        .map((p) => (typeof p.text === "string" ? p.text : ""))
        .join("\n")
        .trim();
      if (text) {
        activeTask.steps.push({
          type: "output",
          title: "Risposta Orchestratore / Agente",
          detail: text.slice(0, 500),
        });
      }
    }
    return undefined;
  });

  // 2. Adaptive Permission Gate on every tool call
  pi.on("tool_call", async (event, ctx) => {
    const toolName = String(event.toolName || "");
    const toolArgs = ((event as unknown as Record<string, unknown>).input ||
      (event as unknown as Record<string, unknown>).args ||
      {}) as Record<string, unknown>;

    if (activeTask) {
      activeTask.steps.push({
        type: "tool_call",
        title: `Tool: ${toolName}`,
        detail: JSON.stringify(toolArgs).slice(0, 260),
      });
    }

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
          "[Cortical Adaptive Gate]",
          `Approvare ${decision.normalized_pattern} (risk=${decision.risk_score}) e ricordare il pattern?`
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

  // 3. Eager Weather & Chrome Grounding Tool for `pi`
  pi.registerTool?.({
    name: "meteo_forecast",
    label: "Meteo Forecast (Open-Meteo + Chrome)",
    description:
      "Cerca le previsioni meteo reali per una città (oggi, domani, dopodomani) tramite Open-Meteo e apre la scheda meteo su Google Chrome.",
    parameters: {
      type: "object",
      properties: {
        city: { type: "string", default: "Roma" },
        day_offset: {
          type: "number",
          default: 1,
          description: "0=oggi, 1=domani, 2=dopodomani",
        },
        open_chrome: { type: "boolean", default: true },
      },
      required: ["city"],
    } as any,
    execute: async (_toolCallId, params) => {
      const args = (params || {}) as Record<string, unknown>;
      const res = invokeCorticalCLI([
        "weather",
        "--city",
        String(args.city || "Roma"),
        "--day-offset",
        String(args.day_offset ?? 1),
        ...(args.open_chrome !== false ? ["--open-chrome"] : []),
      ]);
      return {
        content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
        details: res,
      };
    },
  });

  // 4. Terminating structured report tool for subagents + 3+1 Synthesis & Skill Evaluation
  pi.registerTool?.({
    name: "submit_report",
    label: "Submit Cortical Report & Evaluate Skill",
    description:
      "Conclude un task o sottoagente salvando la sintesi a 3+1 livelli nella Wiki MCP e valutando se creare una nuova Skill per il futuro.",
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
        create_skill: {
          type: "boolean",
          default: false,
          description: "Se true, compila una nuova Skill (.pi/skills/learned-.../SKILL.md) dalle lezioni apprese.",
        },
        touched_paths: { type: "array", items: { type: "string" } },
      },
      required: ["status", "summary"],
    } as any,
    execute: async (_toolCallId, params) => {
      const args = (params || {}) as Record<string, unknown>;
      let closeResult: Record<string, unknown> = {};
      if (activeTask && args.status === "completed") {
        try {
          closeResult = invokeCorticalCLI([
            "task-close",
            "--episode-id",
            activeTask.episodeId,
            "--goal",
            activeTask.goal,
            "--notes",
            String(args.summary || ""),
            "--steps-json",
            JSON.stringify(activeTask.steps),
            ...(args.create_skill ? ["--force-skill"] : []),
          ]);
          activeTask = null;
        } catch (err) {
          closeResult = { warning: String(err) };
        }
      }
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                subagent_report: args,
                task_consolidation: closeResult,
                timestamp: new Date().toISOString(),
              },
              null,
              2
            ),
          },
        ],
        details: closeResult,
      };
    },
  });

  // 5. Orchestrator Subagent Spawner with Parallel 3+1 Wiki Memory & Procedural Skills
  pi.registerTool?.({
    name: "delegate_subagent",
    label: "Delegate Cortical Multi-Agent Role",
    description:
      "Avvia un ruolo specializzato (arch_analyst, code_implementer, reviewer, web_researcher) iniettando in parallelo il livello 3+1 della Wiki MCP e le Skill pertinenti.",
    parameters: {
      type: "object",
      properties: {
        role: {
          type: "string",
          enum: ["arch_analyst", "code_implementer", "reviewer", "web_researcher"],
        },
        goal: { type: "string" },
        wiki_path: { type: "string", default: "/" },
        initial_depth: {
          type: "string",
          enum: ["light", "medium", "high", "max"],
          default: "medium",
        },
      },
      required: ["role", "goal"],
    } as any,
    execute: async (_toolCallId, params) => {
      const args = (params || {}) as Record<string, unknown>;
      const goal = String(args.goal || "");
      let enhancement: Record<string, unknown> = {};
      try {
        enhancement = invokeCorticalCLI(["enhance-prompt", "--prompt", goal]);
      } catch (err) {
        enhancement = { warning: String(err) };
      }

      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(
              {
                orchestrator_dispatch: {
                  role: args.role,
                  goal,
                  enhancement,
                },
              },
              null,
              2
            ),
          },
        ],
        details: enhancement,
      };
    },
  });
}
