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
 *    - Evaluates whether the work produced a reusable pattern and compiles a new `.agents/skills/learned-<slug>/SKILL.md`.
 *    - Archives the compact trace and purges bulky temporary logs.
 * 4. Task Deletion (`/task-delete <id>`) & Skills Inspector (`/skills`).
 */

import { execFileSync, spawn } from "node:child_process";
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
    const agentsSkillsDir = path.join(root, ".agents", "skills");
    const legacySkillsDir = path.join(root, ".pi", "skills");
    const skillsDir = existsSync(agentsSkillsDir) ? agentsSkillsDir : legacySkillsDir;
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
    skillsDir: existsSync("./.agents/skills") ? "./.agents/skills" : "./.pi/skills",
  };
}

function resolveEnvWithPath(extra: Record<string, string> = {}): NodeJS.ProcessEnv {
  const curPath = process.env.PATH || "/usr/bin:/bin:/usr/sbin:/sbin";
  const prefix = ["/opt/homebrew/bin", "/usr/local/bin"].filter((p) => !curPath.split(":").includes(p));
  return {
    ...process.env,
    PATH: [...prefix, curPath].join(":"),
    ...extra,
  };
}

function resolvePiExecutable(): string {
  const candidates = ["/opt/homebrew/bin/pi", "/usr/local/bin/pi", "pi"];
  return candidates.find((c) => c === "pi" || existsSync(c)) || "pi";
}

interface SubagentRunResult {
  role: string;
  model: string;
  status: "completed" | "error";
  toolsExecuted: number;
  tokens: number;
  summary: string;
}

async function runPiWorkerAsync(
  role: string,
  goal: string,
  enhancementText: string,
  modelId = "qwen3:8b",
  timeoutMs = 120000
): Promise<SubagentRunResult> {
  const piBin = resolvePiExecutable();
  const harnessPath = fileURLToPath(import.meta.url);
  const { pythonPath } = resolveCorticalPaths();
  const workerCwd = path.resolve(pythonPath, "..");
  const prompt = [
    `Ruolo assegnato: ${role}`,
    `Obiettivo specifico: ${goal}`,
    "Usa i tool reali (read, bash, edit, write), non inventare risultati e rispondi in italiano conciso.",
    enhancementText ? `\n[CONTESTO WIKI/SKILL]\n${enhancementText.slice(0, 800)}` : "",
  ]
    .filter(Boolean)
    .join("\n");

  const args = [
    "-p", "--mode", "json", "--no-session", "--approve",
    "--no-extensions", "-e", harnessPath,
    "--no-skills", "--no-prompt-templates", "--no-themes",
    "--thinking", "off", "--provider", "ollama", "--model", modelId,
    "--tools", "read,bash,edit,write",
    prompt,
  ];

  return new Promise((resolve) => {
    const child = spawn(piBin, args, {
      cwd: existsSync(workerCwd) ? workerCwd : process.cwd(),
      env: resolveEnvWithPath({ PI_CORTICAL_WORKER: "1", PI_CORTICAL_FAST: "1" }),
      stdio: ["ignore", "pipe", "pipe"],
    });
    let finalText = "";
    let stderrBuf = "";
    let toolsExecuted = 0;
    let tokens = 0;
    let buf = "";

    const timer = setTimeout(() => {
      child.kill("SIGTERM");
    }, timeoutMs);

    child.stdout?.on("data", (chunk: Buffer) => {
      buf += chunk.toString("utf-8");
      let nl = buf.indexOf("\n");
      while (nl >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        nl = buf.indexOf("\n");
        if (!line.startsWith("{")) continue;
        try {
          const evt = JSON.parse(line) as Record<string, unknown>;
          if (evt.type === "tool_execution_end") toolsExecuted += 1;
          if (evt.type === "turn_end" || evt.type === "message_end") {
            const msg = (evt.message || {}) as Record<string, unknown>;
            if (msg.role === "assistant") {
              const parts = Array.isArray(msg.content) ? msg.content : [];
              const txt = parts
                .map((p: unknown) => (typeof p === "object" && p && (p as Record<string, unknown>).type === "text" ? String((p as Record<string, unknown>).text || "") : ""))
                .join("\n")
                .trim();
              if (txt) finalText = txt;
              const usage = msg.usage as Record<string, unknown> | undefined;
              if (evt.type === "turn_end" && usage) {
                tokens += Number(usage.totalTokens || Number(usage.input || 0) + Number(usage.output || 0));
              }
            }
          }
        } catch {
          // Ignore non-JSON lines
        }
      }
    });

    child.stderr?.on("data", (c: Buffer) => {
      stderrBuf += c.toString("utf-8");
    });

    child.on("close", (code) => {
      clearTimeout(timer);
      const ok = Boolean(finalText || toolsExecuted > 0) && (code === 0 || code === null);
      resolve({
        role,
        model: modelId,
        status: ok ? "completed" : "error",
        toolsExecuted,
        tokens,
        summary: (finalText || stderrBuf || `Exit code ${code}`).slice(0, 1200),
      });
    });

    child.on("error", (err) => {
      clearTimeout(timer);
      resolve({ role, model: modelId, status: "error", toolsExecuted, tokens, summary: String(err) });
    });
  });
}

function invokeCorticalCLI(args: string[]): Record<string, unknown> {
  const { pythonBin, pythonPath, skillsDir } = resolveCorticalPaths();
  const out = execFileSync(
    pythonBin,
    ["-m", "cortical.cli", "--skills-dir", skillsDir, ...args],
    {
      encoding: "utf-8",
      env: resolveEnvWithPath({ PYTHONPATH: pythonPath }),
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
    norm.includes("temperatura") ||
    norm.includes("weather") ||
    norm.includes("forecast") ||
    norm.includes("temperature")
  );
}

function isPageReadQuery(text: string): boolean {
  const norm = text.toLowerCase();
  const hasPage =
    norm.includes("pagina") ||
    norm.includes("scheda") ||
    norm.includes("articolo") ||
    norm.includes("aperta") ||
    norm.includes("aperto") ||
    norm.includes("page") ||
    norm.includes("article") ||
    norm.includes("tab") ||
    norm.includes("open page");
  if (!hasPage) return false;
  return (
    norm.includes("leggi") ||
    norm.includes("leggimi") ||
    norm.includes("riassumi") ||
    norm.includes("sintetizza") ||
    norm.includes("concetti") ||
    norm.includes("spiega") ||
    norm.includes("read") ||
    norm.includes("summarize") ||
    norm.includes("summary") ||
    norm.includes("concepts") ||
    norm.includes("explain")
  );
}

function isBrowserSearchQuery(text: string): boolean {
  const norm = text.toLowerCase();
  return (
    norm.includes("apri il browser") ||
    norm.includes("apri chrome") ||
    norm.includes("vai in wikipedia") ||
    norm.includes("vai su wikipedia") ||
    norm.includes("cerca su wikipedia") ||
    norm.includes("cerca su google") ||
    norm.includes("fai una ricerca") ||
    norm.includes("open the browser") ||
    norm.includes("open chrome") ||
    norm.includes("go to wikipedia") ||
    norm.includes("search wikipedia") ||
    norm.includes("search google") ||
    norm.includes("do a search") ||
    norm.includes("search for")
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
    norm.includes("orchestra un sottoagente") ||
    norm.includes("create a task") ||
    norm.includes("create task") ||
    norm.includes("open a task") ||
    norm.includes("new task") ||
    norm.includes("orchestrate a subagent")
  );
}

export default function corticalHarnessExtension(pi: ExtensionAPI) {
  const g = globalThis as Record<string, unknown>;
  if (g.__CORTICAL_HARNESS_REGISTERED__) {
    return;
  }
  g.__CORTICAL_HARNESS_REGISTERED__ = true;

  let pendingGroundedAnswer: string | null = null;
  let activeTask: ActiveTaskState | null = null;
  const executedToolSignatures = new Map<string, number>();

  // Register Cortical Multi-Agent & Adaptive Skill Slash Commands in `pi`
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

  pi.registerCommand?.("gateway", {
    description: "Stato o configurazione del Gateway Remoto opzionale (/gateway status|invite <email>)",
    handler: async (args, ctx) => {
      const parts = args.trim().split(/\s+/).filter(Boolean);
      const action = parts[0] || "status";
      try {
        const cliArgs = ["gateway", action === "invite" ? "invite" : "status"];
        if (action === "invite" && parts[1]) cliArgs.push("--email", parts[1]);
        const res = invokeCorticalCLI(cliArgs);
        ctx.ui?.notify?.(JSON.stringify(res, null, 2), "info");
      } catch (err) {
        ctx.ui?.notify?.(`Gateway error: ${String(err)}`, "warning");
      }
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

  pi.registerCommand?.("attach", {
    description: "Allega file, cartella, skill o plugin al contesto della chat/task (/attach <file|folder|skill|plugin> <percorso_o_nome>)",
    handler: async (args, ctx) => {
      const parts = args.trim().split(/\s+/);
      if (parts.length < 2) {
        ctx.ui?.notify?.("Uso: /attach <file|folder|skill|plugin> <percorso_o_nome>", "warning");
        return;
      }
      const itemType = parts[0].toLowerCase();
      const itemRef = parts.slice(1).join(" ");
      const scopeId = activeTask?.episodeId || "chat";
      const res = invokeCorticalCLI([
        "context-attach",
        "--scope-id",
        scopeId,
        "--item-type",
        itemType,
        "--item-ref",
        itemRef,
      ]);
      ctx.ui?.notify?.(
        `📎 Allegato [${itemType}] '${res.label}' aggiunto al contesto '${scopeId}' (ID: ${res.attachment_id})`,
        "info"
      );
    },
  });

  pi.registerCommand?.("detach", {
    description: "Rimuove un allegato dal contesto della chat/task (/detach <attachment_id>)",
    handler: async (args, ctx) => {
      const attId = args.trim();
      if (!attId) {
        ctx.ui?.notify?.("Uso: /detach <attachment_id>", "warning");
        return;
      }
      invokeCorticalCLI(["context-detach", "--attachment-id", attId]);
      ctx.ui?.notify?.(`🧹 Allegato ${attId} rimosso dal contesto.`, "info");
    },
  });

  pi.registerCommand?.("context", {
    description: "Mostra file, cartelle, skill e plugin allegati alla chat o al task corrente",
    handler: async (_args, ctx) => {
      const scopeId = activeTask?.episodeId || "chat";
      const res = invokeCorticalCLI(["context-list", "--scope-id", scopeId]);
      const list = (res.attachments || []) as Array<Record<string, unknown>>;
      if (list.length === 0) {
        ctx.ui?.notify?.(`📎 Nessun elemento allegato al contesto '${scopeId}'. Usa /attach <file|folder|skill|plugin> <ref>`, "info");
        return;
      }
      const summary = list.map((a) => `${a.attachment_id}:${a.item_type}(${a.label})`).join(", ");
      ctx.ui?.notify?.(`📎 Contesto '${scopeId}' (${list.length}): ${summary}`, "info");
    },
  });

  pi.registerCommand?.("private", {
    description: "Interroga o allega in modo riservato file/cartelle senza esporli al cloud (/private <alias> <domanda>)",
    handler: async (args, ctx) => {
      const parts = args.trim();
      if (!parts) {
        ctx.ui?.notify?.("Uso: /private <nome_file_o_cartella> [domanda] (es. /private omniroute analisi)", "warning");
        return;
      }
      const res = invokeCorticalCLI(["local-loop", `/private ${parts} /local`, "--json"]);
      const ans = String(res.local_answer || res.distilled_insight || JSON.stringify(res));
      ctx.ui?.notify?.(`🔒 [Cortical Locale Privato]\n${ans.slice(0, 700)}`, "info");
    },
  });

  // 1. Pre-Flight Grounding + Parallel 3+1 Memory & Skill Enhancement Hook
  pi.on("before_agent_start", (event, ctx) => {
    pendingGroundedAnswer = null;
    executedToolSignatures.clear();
    try {
      const userPrompt =
        "prompt" in event && typeof event.prompt === "string" ? event.prompt : "";
      if (!userPrompt) return undefined;

      // A. Deterministic Weather & Visual Chrome Grounding (only for short direct user turns, never long/harness tasks)
      const isHarnessOrTaskPrompt =
        Boolean(activeTask) ||
        userPrompt.length > 260 ||
        userPrompt.includes("=== CORTICAL HARNESS") ||
        userPrompt.includes("Obiettivo Task");
      if (!isHarnessOrTaskPrompt && isWeatherQuery(userPrompt)) {
        const res = invokeCorticalCLI([
          "weather",
          "--query",
          userPrompt,
          "--open-chrome",
        ]);
        const groundedSummary = String(res.summary_it || JSON.stringify(res));
        pendingGroundedAnswer = groundedSummary;
        ctx.ui?.notify?.(`[Cortical Grounding] ${groundedSummary}`, "info");
      } else if (!isHarnessOrTaskPrompt && isPageReadQuery(userPrompt)) {
        const mode = userPrompt.toLowerCase().includes("leggi") && !userPrompt.toLowerCase().includes("riassumi")
          ? "read"
          : "summarize";
        const res = invokeCorticalCLI(["chrome-read", "--mode", mode]);
        const groundedSummary = String(res.summary_it || JSON.stringify(res));
        pendingGroundedAnswer = groundedSummary;
        ctx.ui?.notify?.(`[Cortical Chrome Reader] ${groundedSummary}`, "info");
      } else if (!isHarnessOrTaskPrompt && isBrowserSearchQuery(userPrompt)) {
        const res = invokeCorticalCLI(["chrome-search", "--prompt", userPrompt]);
        const groundedSummary = String(res.summary_it || JSON.stringify(res));
        pendingGroundedAnswer = groundedSummary;
        ctx.ui?.notify?.(`[Cortical Visual Chrome] ${groundedSummary}`, "info");
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
    } catch {
      // Continue normally if CLI is unreachable
    }
    return undefined;
  });

  // 1b. Direct Provider Payload Grounding (ensures small local models 1.5B-4B reply accurately in Italian)
  pi.on("before_provider_request", (event) => {
    try {
      const payload = (event as unknown as Record<string, unknown>).payload as
        | { messages?: Array<{ role: string; content: unknown }> }
        | undefined;
      if (!payload || !Array.isArray(payload.messages)) return undefined;

      let lastUserText = "";
      for (let i = payload.messages.length - 1; i >= 0; i--) {
        const m = payload.messages[i];
        if (m.role === "user") {
          if (typeof m.content === "string") {
            lastUserText = m.content;
          } else if (Array.isArray(m.content)) {
            lastUserText = m.content
              .map((p: Record<string, unknown>) => (typeof p?.text === "string" ? p.text : ""))
              .join(" ");
          }
          break;
        }
      }
      if (!lastUserText) return undefined;
      const norm = lastUserText.toLowerCase().trim();
      const now = new Date();
      const timeStr = now.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
      const dateStr = now.toLocaleDateString("it-IT", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      });

      // Deterministic Clock / Date Grounding
      if (
        norm.includes("che ore sono") ||
        norm.includes("che ora è") ||
        norm.includes("che ora e") ||
        norm.includes("che giorno")
      ) {
        const clockAnswer = `Sono le ${timeStr} di ${dateStr}.`;
        pendingGroundedAnswer = clockAnswer;
        return {
          ...payload,
          temperature: 0.0,
          messages: [
            {
              role: "system",
              content: "Rispondi in italiano riportando fedelmente l'orario e la data indicati.",
            },
            {
              role: "user",
              content: `Ripeti esattamente questa frase in italiano: "${clockAnswer}"`,
            },
          ],
        };
      }

      // Deterministic Weather & Chrome Grounding
      if (pendingGroundedAnswer || isWeatherQuery(lastUserText)) {
        let grounded = pendingGroundedAnswer;
        if (!grounded) {
          const res = invokeCorticalCLI(["weather", "--query", lastUserText, "--open-chrome"]);
          grounded = String(res.summary_it || JSON.stringify(res));
          pendingGroundedAnswer = grounded;
        }
        return {
          ...payload,
          temperature: 0.0,
          messages: [
            {
              role: "system",
              content:
                "Sei Cortical. Rispondi in italiano perfetto riportando fedelmente i dati meteo reali già verificati e confermando di aver aperto Chrome.",
            },
            {
              role: "user",
              content: `Ecco i dati meteo verificati da riportare fedelmente all'utente in italiano:\n\n"${grounded}"\n\nRiporta esattamente questa previsione in italiano chiaro.`,
            },
          ],
        };
      }

      // Parallel 3+1 Memory + Adaptive Skill Enhancement (only on fresh user turns without prior Python enhancement)
      const lastMsgRole = payload.messages[payload.messages.length - 1]?.role;
      const alreadyEnhanced =
        lastUserText.includes("=== CORTICAL HARNESS") ||
        lastUserText.includes("[CONTESTO SKILL/WIKI]") ||
        process.env.PI_CORTICAL_WORKER === "1";
      const modelStr = String((payload as Record<string, unknown>).model || "").toLowerCase();
      const effortRaw = String(process.env.PI_EFFORT || "medium").toLowerCase();
      const effort = effortRaw === "low" || effortRaw === "high" ? effortRaw : "medium";
      const effortReasoning = effort === "high" ? "low" : "none";
      const effortMaxTokens = effort === "low" ? 900 : effort === "high" ? 4096 : 2048;
      const isLocalFast =
        process.env.PI_CORTICAL_FAST === "1" ||
        modelStr.includes("qwen") ||
        modelStr.includes("ollama");
      const dynCtx = Number(process.env.CORTICAL_DYNAMIC_NUM_CTX || "0") || 16384;
      const basePatch = isLocalFast
        ? {
            ...payload,
            think: effort === "high",
            reasoning_effort:
              (payload as Record<string, unknown>).reasoning_effort ?? effortReasoning,
            max_tokens:
              (payload as Record<string, unknown>).max_tokens ?? effortMaxTokens,
            options: {
              ...(((payload as Record<string, unknown>).options as Record<string, unknown>) || {}),
              num_ctx: dynCtx,
            },
          }
        : payload;
      const hasCorticalRefs = /@(?:private|vault|wiki|node|concept|skill|insight|root):|\/private\b|cortical:\/\//i.test(lastUserText);
      if (lastMsgRole === "user" && !alreadyEnhanced && (activeTask || hasCorticalRefs || lastUserText.split(/\s+/).length >= 6)) {
        const enh = invokeCorticalCLI(["enhance-prompt", "--prompt", lastUserText]);
        const enhancedSys = String(enh.enhanced_system_instructions || "").slice(0, 1200);
        if (enhancedSys) {
          return {
            ...basePatch,
            messages: [
              {
                role: "system",
                content: `Data e ora locale: ${dateStr}, ${timeStr}.\n\n${enhancedSys}`,
              },
              ...payload.messages,
            ],
          };
        }
      }
      if (basePatch !== payload) {
        return basePatch;
      }
    } catch {
      // Ignore if CLI not reachable
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
    const cmdStr = toolName === "bash" ? String(toolArgs.command || toolArgs.cmd || "").trim() : "";
    const normPath = String(toolArgs.path || toolArgs.file_path || "")
      .replace(/^\/Users\/[^/]+\/work\/code\/cortical\/?/, "")
      .replace(/^\.\//, "")
      .trim();
    const sigKey =
      toolName === "bash" && cmdStr
        ? `bash:${cmdStr}`
        : toolName === "read"
          ? `read:${normPath}`
          : ["grep", "find", "ls"].includes(toolName)
            ? `${toolName}:${normPath}:${toolArgs.pattern ?? ""}`
            : "";
    const priorRuns = sigKey ? (executedToolSignatures.get(sigKey) || 0) : 0;
    const isSilentOpen = /^open\b/i.test(cmdStr) || cmdStr.includes(" open ");
    if (
      sigKey &&
      ((isSilentOpen && priorRuns >= 1) ||
        (toolName === "read" && priorRuns >= 1) ||
        priorRuns >= 2)
    ) {
      return {
        block: true,
        reason:
          "[Cortical Anti-Loop] This exact target was already inspected/executed in this turn. Do NOT repeat the same read/command; move forward to edit/write/verification or finish with STATUS: DONE.",
      };
    }
    const recordExecutedTool = () => {
      if (sigKey) {
        executedToolSignatures.set(sigKey, (executedToolSignatures.get(sigKey) || 0) + 1);
      }
    };

    if (activeTask) {
      activeTask.steps.push({
        type: "tool_call",
        title: `Tool: ${toolName}`,
        detail: JSON.stringify(toolArgs).slice(0, 260),
      });
    }

    const reportSecurityBlock = (source: string, targetHost: string, reason: string) => {
      try {
        const base = process.env.CORTICAL_BASE_URL || "http://127.0.0.1:8765";
        void fetch(`${base}/api/security/egress`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: process.env.PI_ACTIVE_SESSION_ID || activeTask?.episodeId || "",
            role: process.env.PI_ACTIVE_ROLE || "agent",
            model: process.env.PI_ACTIVE_MODEL || "",
            source,
            method: toolName,
            target_host: targetHost,
            target_url: String(toolArgs.command || toolArgs.path || "").slice(0, 320),
            payload_excerpt: JSON.stringify(toolArgs).slice(0, 500),
            verdict: "blocked",
            reason,
          }),
        }).catch(() => {});
      } catch {
        // ignore telemetry errors
      }
    };

    try {
      const decision = invokeCorticalCLI([
        "check-permission",
        "--tool",
        toolName,
        "--args-json",
        JSON.stringify(toolArgs),
      ]) as unknown as PermissionVerdict;

      if (decision.verdict === "deny") {
        reportSecurityBlock("harness_gate", decision.normalized_pattern, decision.reason);
        ctx.ui?.notify?.(
          `[Cortical Gate] BLOCKED ${decision.normalized_pattern}: ${decision.reason}`,
          "error"
        );
        return {
          block: true,
          reason: `[Cortical Hard Guardrail] ${decision.reason}`,
        };
      }

      const hasInteractiveUI = Boolean((ctx as Record<string, unknown>).hasUI) && Boolean(ctx.ui?.confirm);
      if (decision.verdict === "ask") {
        if (hasInteractiveUI && ctx.ui?.confirm) {
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
        } else {
          // Headless worker: route through ApprovalBroker so user can approve/deny inline in UI
          const base = process.env.CORTICAL_BASE_URL || "http://127.0.0.1:8765";
          const sid = process.env.PI_ACTIVE_SESSION_ID || activeTask?.episodeId || "chat";
          try {
            const reqResp = await fetch(`${base}/api/approvals/request`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                session_id: sid,
                tool: toolName,
                args: toolArgs,
                role: process.env.PI_ACTIVE_ROLE || "agent",
                model: process.env.PI_ACTIVE_MODEL || "",
              }),
            });
            if (reqResp.ok) {
              const reqData = (await reqResp.json()) as Record<string, unknown>;
              if (reqData.decision === "deny") {
                return { block: true, reason: String(reqData.reason || "Blocked by Cortical Gate") };
              }
              if (reqData.decision === "pending" && reqData.approval_id) {
                const aid = String(reqData.approval_id);
                const deadline = Date.now() + 600_000;
                while (Date.now() < deadline) {
                  const waitResp = await fetch(
                    `${base}/api/approvals/wait?id=${encodeURIComponent(aid)}&timeout=25`
                  );
                  if (!waitResp.ok) break;
                  const waitData = (await waitResp.json()) as Record<string, unknown>;
                  if (waitData.status !== "pending") {
                    if (waitData.decision === "allow") {
                      recordExecutedTool();
                      return undefined;
                    }
                    return {
                      block: true,
                      reason: `User denied ${decision.normalized_pattern}${waitData.feedback ? `: ${waitData.feedback}` : ""}`,
                    };
                  }
                }
                return {
                  block: true,
                  reason: `Approval timeout for ${decision.normalized_pattern}`,
                };
              }
              if (reqData.decision === "allow") {
                recordExecutedTool();
                return undefined;
              }
            }
          } catch {
            // Fallback if live HTTP server is unreachable
          }
          if (decision.risk_score >= 0.75) {
            return {
              block: true,
              reason: `High-risk pattern requires interactive confirmation: ${decision.normalized_pattern}`,
            };
          }
        }
      }
    } catch {
      // Fail-open only for non-destructive commands if CLI env is initializing
    }
    recordExecutedTool();
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

  // 3b. Visual Chrome Navigation, Form Filling & Search Submission Tool for `pi`
  pi.registerTool?.({
    name: "chrome_search",
    label: "Visual Chrome Navigate & Search (Focus)",
    description:
      "Porta Google Chrome in primo piano, apre un sito (es. Wikipedia, Google), compila il form di ricerca nel DOM e invia la ricerca.",
    parameters: {
      type: "object",
      properties: {
        site: { type: "string", default: "wikipedia" },
        query: { type: "string" },
        url: { type: "string" },
        focus: { type: "boolean", default: true },
      },
      required: [],
    } as any,
    execute: async (_toolCallId, params) => {
      const args = (params || {}) as Record<string, unknown>;
      const cliArgs = ["chrome-search"];
      if (args.site) cliArgs.push("--site", String(args.site));
      if (args.query) cliArgs.push("--query", String(args.query));
      if (args.url) cliArgs.push("--url", String(args.url));
      if (args.focus === false) cliArgs.push("--background");
      const res = invokeCorticalCLI(cliArgs);
      return {
        content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
        details: res,
      };
    },
  });

  // 3c. Active Chrome Page Reader & Concept Summarizer Tool for `pi`
  pi.registerTool?.({
    name: "chrome_read_page",
    label: "Read / Summarize Open Chrome Tab",
    description:
      "Legge o riassume i concetti principali della scheda attualmente aperta e attiva su Google Chrome.",
    parameters: {
      type: "object",
      properties: {
        mode: { type: "string", enum: ["read", "summarize"], default: "summarize" },
      },
      required: [],
    } as any,
    execute: async (_toolCallId, params) => {
      const args = (params || {}) as Record<string, unknown>;
      const mode = args.mode === "read" ? "read" : "summarize";
      const res = invokeCorticalCLI(["chrome-read", "--mode", mode]);
      return {
        content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
        details: res,
      };
    },
  });

  // 3d. Extract URL Text, Links & Form Fields (works with Chrome CDP :9222 or Playwright/HTTP fallback)
  pi.registerTool?.({
    name: "chrome_extract_page",
    label: "Extract Web Page & Form Fields",
    description:
      "Apre un URL e ne estrae testo leggibile, link (es. offerte di lavoro) e tutti i campi dei form (<input>/<textarea>/<select>) senza bisogno di configurazioni manuali.",
    parameters: {
      type: "object",
      properties: {
        url: { type: "string", description: "URL completo della pagina o modulo da analizzare (https://...)" },
      },
      required: ["url"],
    } as any,
    execute: async (_toolCallId, params) => {
      const args = (params || {}) as Record<string, unknown>;
      const res = invokeCorticalCLI(["chrome-extract", "--url", String(args.url || "")]);
      return {
        content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
        details: res,
      };
    },
  });

  // 3e. Fill Web Form Fields & Optional CV Upload
  pi.registerTool?.({
    name: "chrome_fill_form",
    label: "Fill Web Form & Upload CV",
    description:
      "Compila automaticamente i campi di un form web (per nome/id/placeholder/label), carica un eventuale file (es. CV .pdf/.docx) e opzionalmente invia il modulo.",
    parameters: {
      type: "object",
      properties: {
        url: { type: "string", description: "URL del form di candidatura" },
        fields: { type: "object", description: "Mappa campo -> valore (es. {\"email\": \"ccancellieri@hotmail.com\", \"name\": \"Carlo Cancellieri\"})" },
        upload_file: { type: "string", description: "Path locale opzionale del CV da allegare" },
        submit: { type: "boolean", default: false, description: "Invia solo se richiesto esplicitamente" },
      },
      required: ["url", "fields"],
    } as any,
    execute: async (_toolCallId, params) => {
      const args = (params || {}) as Record<string, unknown>;
      const cliArgs = ["chrome-fill", "--url", String(args.url || ""), "--fields-json", JSON.stringify(args.fields || {})];
      if (args.upload_file) cliArgs.push("--upload", String(args.upload_file));
      if (args.submit === true) cliArgs.push("--submit");
      const res = invokeCorticalCLI(cliArgs);
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
          description: "Se true, compila una nuova Skill (.agents/skills/learned-.../SKILL.md) dalle lezioni apprese.",
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

  // 5. Real Parallel Orchestrator Subagent Spawners (Ollama Zero-Cost)
  async function executeDelegatedTask(
    role: string,
    goal: string,
    model = "qwen3:8b"
  ): Promise<SubagentRunResult> {
    let enhText = "";
    try {
      const enh = invokeCorticalCLI(["enhance-prompt", "--prompt", goal]);
      enhText = String(enh.enhanced_system_instructions || "");
    } catch {
      enhText = "";
    }
    const res = await runPiWorkerAsync(role, goal, enhText, model);
    if (activeTask) {
      activeTask.steps.push({
        type: "subagent",
        title: `Subagente ${res.role} (${res.model} · ${res.toolsExecuted} tools · ${res.tokens} tok)`,
        detail: res.summary.slice(0, 320),
      });
    }
    return res;
  }

  pi.registerTool?.({
    name: "delegate_subagent",
    label: "Delegate Cortical Multi-Agent Role (Live Execution)",
    description:
      "Esegue davvero in background un sottoagente specializzato locale su Ollama (`arch_analyst`, `code_implementer`, `reviewer`, `web_researcher`) iniettando il livello 3+1 della Wiki MCP e le Skill.",
    parameters: {
      type: "object",
      properties: {
        role: {
          type: "string",
          enum: ["arch_analyst", "code_implementer", "reviewer", "web_researcher"],
        },
        goal: { type: "string" },
        model: { type: "string", default: "qwen3:8b" },
      },
      required: ["role", "goal"],
    } as any,
    execute: async (_toolCallId, params) => {
      const args = (params || {}) as Record<string, unknown>;
      const res = await executeDelegatedTask(
        String(args.role || "code_implementer"),
        String(args.goal || ""),
        String(args.model || "qwen3:8b")
      );
      return {
        content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
        details: res,
      };
    },
  });

  pi.registerTool?.({
    name: "delegate_parallel_swarm",
    label: "Run Parallel Local Subagents Swarm",
    description:
      "Avvia fino a 3 sottoagenti locali in parallelo reale su Ollama/pi e raccoglie i risultati verificati.",
    parameters: {
      type: "object",
      properties: {
        tasks: {
          type: "array",
          items: {
            type: "object",
            properties: {
              role: { type: "string" },
              goal: { type: "string" },
              model: { type: "string" },
            },
            required: ["role", "goal"],
          },
        },
      },
      required: ["tasks"],
    } as any,
    execute: async (_toolCallId, params) => {
      const rawTasks = Array.isArray((params as Record<string, unknown>)?.tasks)
        ? ((params as Record<string, unknown>).tasks as Array<Record<string, unknown>>).slice(0, 3)
        : [];
      const results = await Promise.all(
        rawTasks.map((t) =>
          executeDelegatedTask(
            String(t.role || "code_implementer"),
            String(t.goal || ""),
            String(t.model || "qwen3:8b")
          )
        )
      );
      return {
        content: [{ type: "text", text: JSON.stringify({ swarm_results: results }, null, 2) }],
        details: { swarm_results: results },
      };
    },
  });

  // 6. Optional Modular Remote Gateway Tool (Key Auth, Account Cap, Tunnel & Invite)
  pi.registerTool?.({
    name: "manage_remote_gateway",
    label: "Manage Optional Cortical Remote Gateway",
    description:
      "Inspect, configure, expose, or send account password invites for Cortical's optional Remote Gateway (compatible via CLI/MCP with pi, OpenCode, OpenClaw, Codex, Claude, DeepSeek).",
    parameters: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["status", "config", "invite", "duckdns"],
          default: "status",
        },
        email: { type: "string", default: "ccancellieri@hotmail.com" },
        max_users: { type: "integer" },
        auth_enabled: { type: "boolean" },
        rotate_key: { type: "boolean", default: false },
      },
    } as any,
    execute: async (_toolCallId, params) => {
      const args = (params || {}) as Record<string, unknown>;
      const action = String(args.action || "status");
      const cliArgs = ["gateway", action];
      if (action === "invite" && args.email) cliArgs.push("--email", String(args.email));
      if (action === "config") {
        if (typeof args.max_users === "number") cliArgs.push("--max-users", String(args.max_users));
        if (typeof args.auth_enabled === "boolean") cliArgs.push("--auth-enabled", String(args.auth_enabled));
        if (args.rotate_key) cliArgs.push("--rotate-key");
      }
      const res = invokeCorticalCLI(cliArgs);
      return {
        content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
        details: res,
      };
    },
  });

  // Compress oversized read/bash/grep tool outputs (>3800 chars) to protect local KV cache window
  pi.on("tool_result", (event) => {
    try {
      const tname = String((event as unknown as Record<string, unknown>).toolName || "");
      if (!["read", "bash", "grep", "find", "ls"].includes(tname)) return undefined;
      const ev = event as unknown as { content?: Array<{ type?: string; text?: string }> };
      if (!Array.isArray(ev.content)) return undefined;
      let changed = false;
      const nextContent = ev.content.map((part) => {
        if (part?.type === "text" && typeof part.text === "string" && part.text.length > 3800) {
          changed = true;
          const omitted = part.text.length - 3000;
          const compact =
            part.text.slice(0, 1800) +
            `\n\n...[CORTICAL COMPACTION: ${omitted} caratteri omessi per proteggere il contesto locale. Usa read con offset/limit mirati o grep per sezioni specifiche.]...\n\n` +
            part.text.slice(-1200);
          return { ...part, text: compact };
        }
        return part;
      });
      if (changed) return { content: nextContent };
    } catch {
      // ignore compression error
    }
    return undefined;
  });
}
