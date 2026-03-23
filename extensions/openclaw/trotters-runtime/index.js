import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const DEFAULT_CONFIG = {
  apiBase: "http://research-api:8890",
  opsBridgeBase: "http://ops-bridge:8891",
  runbookPath: "/opt/openclaw-config/trotters-runbook.json",
  runbookHistoryPath: "/home/node/.openclaw/trotters/runbook-history.jsonl",
  catalogRoot: "/runtime/catalog",
  summaryRoot: "/runtime/catalog/agent_summaries",
  actor: "openclaw-supervisor",
  defaultLogTailLines: 200,
};

const DIRECTOR_ACTIONS = ["list", "get", "start", "pause", "resume", "skip_next", "stop"];
const CAMPAIGN_ACTIONS = ["list", "get", "start", "stop"];
const JOB_ACTIONS = ["list", "get", "logs", "artifacts"];
const RUNBOOK_ACTIONS = ["get", "next_work_item", "record_recovery", "record_escalation"];
const SERVICE_ACTIONS = ["list", "restart"];
const REVIEW_PACK_ACTIONS = ["campaign_triage", "candidate_review", "paper_trade_readiness", "failure_postmortem"];
const SUMMARY_ACTIONS = ["latest", "list", "record"];
const SUMMARY_TYPES = ["supervisor_incident_summary", "campaign_triage_summary", "candidate_readiness_summary", "paper_trade_readiness_summary", "failure_postmortem_summary"];
const SUPERVISOR_INCIDENT_SUMMARY_TYPE = "supervisor_incident_summary";
const SUPERVISOR_INCIDENT_COOLDOWN_MINUTES = 30;
const SUPERVISOR_EXHAUSTED_STALE_HOURS = 12;
const SUMMARY_DEFAULT_AGENT_IDS = {
  campaign_triage_summary: "research-triage",
  candidate_readiness_summary: "candidate-review",
  paper_trade_readiness_summary: "paper-trade-readiness",
  failure_postmortem_summary: "failure-postmortem",
};
const SPECIALIST_SUMMARY_RULES = {
  campaign_triage_summary: {
    defaultClassification: "needs_followup",
    allowedClassifications: ["promising", "needs_followup", "dead_end", "blocked"],
    aliases: { needs_more_research: "needs_followup", continue_research: "needs_followup", research_only: "needs_followup", exhausted: "dead_end", no_go: "dead_end" },
    defaultRecommendedActions: { promising: "review_candidate", needs_followup: "continue_research", dead_end: "retire_branch", blocked: "inspect_campaign_inputs" },
  },
  candidate_readiness_summary: {
    defaultClassification: "research_only",
    allowedClassifications: ["ready_for_paper_rehearsal", "research_only", "blocked"],
    aliases: { ready: "ready_for_paper_rehearsal", not_ready: "research_only", needs_followup: "research_only" },
    defaultRecommendedActions: { ready_for_paper_rehearsal: "prepare_paper_rehearsal", research_only: "continue_research", blocked: "resolve_candidate_blocker" },
  },
  paper_trade_readiness_summary: {
    defaultClassification: "not_ready",
    allowedClassifications: ["ready", "not_ready", "blocked"],
    aliases: { ready_for_paper_rehearsal: "ready", research_only: "not_ready", needs_followup: "not_ready" },
    defaultRecommendedActions: { ready: "stage_paper_day", not_ready: "hold_paper_rehearsal", blocked: "resolve_paper_trade_blocker" },
  },
  failure_postmortem_summary: {
    defaultClassification: "unknown",
    allowedClassifications: ["service_health", "campaign_failure", "worker_failure", "unknown", "blocked"],
    aliases: { degraded: "service_health", runtime_failure: "service_health", failed: "campaign_failure", exhausted: "campaign_failure" },
    defaultRecommendedActions: { service_health: "inspect_service_health", campaign_failure: "inspect_failed_campaign", worker_failure: "inspect_worker_pool", unknown: "manual_investigation", blocked: "inspect_postmortem_inputs" },
  },
};
const TERMINAL_STATUSES = new Set(["completed", "exhausted", "failed", "stopped"]);

const plugin = {
  id: "trotters-runtime",
  name: "Trotters Runtime",
  description: "Supervisor tools for the Trotters research runtime.",
  register(api) {
    const cfg = resolvePluginConfig(api.pluginConfig);
    api.registerTool(createOverviewTool(cfg));
    api.registerTool(createDirectorTool(cfg));
    api.registerTool(createCampaignTool(cfg));
    api.registerTool(createJobsTool(cfg));
    api.registerTool(createRunbookTool(cfg));
    api.registerTool(createServiceTool(cfg));
    api.registerTool(createReviewPackTool(cfg));
    api.registerTool(createSummariesTool(cfg));
  },
};

function resolvePluginConfig(rawConfig) {
  return {
    apiBase: textOrDefault(rawConfig?.apiBase, DEFAULT_CONFIG.apiBase),
    opsBridgeBase: textOrDefault(rawConfig?.opsBridgeBase, DEFAULT_CONFIG.opsBridgeBase),
    runbookPath: textOrDefault(rawConfig?.runbookPath, DEFAULT_CONFIG.runbookPath),
    runbookHistoryPath: textOrDefault(rawConfig?.runbookHistoryPath, DEFAULT_CONFIG.runbookHistoryPath),
    catalogRoot: textOrDefault(rawConfig?.catalogRoot, DEFAULT_CONFIG.catalogRoot),
    summaryRoot: textOrDefault(rawConfig?.summaryRoot, DEFAULT_CONFIG.summaryRoot),
    actor: textOrDefault(rawConfig?.actor, DEFAULT_CONFIG.actor),
    defaultLogTailLines: numberOrDefault(rawConfig?.defaultLogTailLines, DEFAULT_CONFIG.defaultLogTailLines),
  };
}

function createOverviewTool(cfg) {
  return {
    name: "trotters_overview",
    label: "Trotters Overview",
    description:
      "Read a compact runtime overview and recent notifications. Use this first before deciding whether the research runtime needs action.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        notificationsLimit: {
          type: "number",
          description: "Optional notification limit. Defaults to 5.",
        },
        includeRaw: {
          type: "boolean",
          description: "Include the full raw overview payload for debugging. Defaults to false.",
        },
      },
    },
    execute: async (_toolCallId, params) => {
      const overview = await callJsonApi({
        baseUrl: cfg.apiBase,
        tokenEnv: "TROTTERS_API_TOKEN",
        actor: cfg.actor,
        path: "/api/v1/runtime/overview",
      });
      return jsonResult(
        summarizeOverviewPayload(cfg, overview, {
          notificationLimit: numberOrDefault(params?.notificationsLimit, 5),
          includeRaw: params?.includeRaw === true,
        }),
      );
    },
  };
}

function createDirectorTool(cfg) {
  return {
    name: "trotters_director",
    label: "Trotters Director",
    description:
      "Inspect and control directors. Start uses an approved runbook plan_id only. Use this to start, pause, resume, skip, or stop research directors safely.",
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["action"],
      properties: {
        action: {
          type: "string",
          enum: DIRECTOR_ACTIONS,
        },
        directorId: {
          type: "string",
        },
        planId: {
          type: "string",
        },
        reason: {
          type: "string",
        },
        stopActiveCampaign: {
          type: "boolean",
        },
      },
    },
    execute: async (_toolCallId, params) => {
      const action = requiredEnum(params, "action", DIRECTOR_ACTIONS);
      if (action === "list") {
        return jsonResult(await callJsonApi({ baseUrl: cfg.apiBase, tokenEnv: "TROTTERS_API_TOKEN", actor: cfg.actor, path: "/api/v1/directors" }));
      }
      if (action === "get") {
        const directorId = requiredString(params, "directorId");
        return jsonResult(
          await callJsonApi({
            baseUrl: cfg.apiBase,
            tokenEnv: "TROTTERS_API_TOKEN",
            actor: cfg.actor,
            path: `/api/v1/directors/${encodeURIComponent(directorId)}`,
          }),
        );
      }
      if (action === "start") {
        const planId = requiredString(params, "planId");
        const runbook = loadRunbook(cfg);
        const workItem = resolveWorkItem(runbook, planId);
        return jsonResult(
          await callJsonApi({
            baseUrl: cfg.apiBase,
            tokenEnv: "TROTTERS_API_TOKEN",
            actor: cfg.actor,
            path: "/api/v1/directors",
            method: "POST",
            payload: {
              director_name: workItem.director_name,
              director_plan_file: workItem.plan_file,
              adopt_active_campaigns: true,
            },
          }),
        );
      }
      const directorId = requiredString(params, "directorId");
      if (action === "pause") {
        return jsonResult(await postDirectorAction(cfg, directorId, "pause", { reason: optionalString(params, "reason") || "supervisor_pause" }));
      }
      if (action === "resume") {
        return jsonResult(await postDirectorAction(cfg, directorId, "resume", { reason: optionalString(params, "reason") || "supervisor_resume" }));
      }
      if (action === "skip_next") {
        return jsonResult(await postDirectorAction(cfg, directorId, "skip-next", { reason: optionalString(params, "reason") || "supervisor_skip" }));
      }
      return jsonResult(
        await postDirectorAction(cfg, directorId, "stop", {
          reason: optionalString(params, "reason") || "supervisor_stop",
          stop_active_campaign: params?.stopActiveCampaign === true,
        }),
      );
    },
  };
}

function createCampaignTool(cfg) {
  return {
    name: "trotters_campaign",
    label: "Trotters Campaign",
    description:
      "Inspect and control campaigns. Start uses an approved config_id only. Use this for manual campaign runs or to stop an unhealthy campaign.",
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["action"],
      properties: {
        action: {
          type: "string",
          enum: CAMPAIGN_ACTIONS,
        },
        campaignId: {
          type: "string",
        },
        configId: {
          type: "string",
        },
        campaignName: {
          type: "string",
        },
        reason: {
          type: "string",
        },
      },
    },
    execute: async (_toolCallId, params) => {
      const action = requiredEnum(params, "action", CAMPAIGN_ACTIONS);
      if (action === "list") {
        return jsonResult(await callJsonApi({ baseUrl: cfg.apiBase, tokenEnv: "TROTTERS_API_TOKEN", actor: cfg.actor, path: "/api/v1/campaigns" }));
      }
      if (action === "get") {
        const campaignId = requiredString(params, "campaignId");
        return jsonResult(
          await callJsonApi({
            baseUrl: cfg.apiBase,
            tokenEnv: "TROTTERS_API_TOKEN",
            actor: cfg.actor,
            path: `/api/v1/campaigns/${encodeURIComponent(campaignId)}`,
          }),
        );
      }
      if (action === "start") {
        const configId = requiredString(params, "configId");
        const runbook = loadRunbook(cfg);
        const configPath = resolveConfigPath(runbook, configId);
        return jsonResult(
          await callJsonApi({
            baseUrl: cfg.apiBase,
            tokenEnv: "TROTTERS_API_TOKEN",
            actor: cfg.actor,
            path: "/api/v1/campaigns",
            method: "POST",
            payload: {
              config_path: configPath,
              campaign_name: optionalString(params, "campaignName") || `${configId}-manual`,
            },
          }),
        );
      }
      const campaignId = requiredString(params, "campaignId");
      return jsonResult(
        await callJsonApi({
          baseUrl: cfg.apiBase,
          tokenEnv: "TROTTERS_API_TOKEN",
          actor: cfg.actor,
          path: `/api/v1/campaigns/${encodeURIComponent(campaignId)}/stop`,
          method: "POST",
          payload: {
            reason: optionalString(params, "reason") || "supervisor_stop",
          },
        }),
      );
    },
  };
}

function createJobsTool(cfg) {
  return {
    name: "trotters_jobs",
    label: "Trotters Jobs",
    description:
      "Inspect jobs, job logs, and artifacts. Use this when a director or campaign failed and you need to inspect the underlying job-level evidence.",
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["action"],
      properties: {
        action: {
          type: "string",
          enum: JOB_ACTIONS,
        },
        jobId: {
          type: "string",
        },
        campaignId: {
          type: "string",
        },
        status: {
          type: "string",
        },
        stream: {
          type: "string",
          enum: ["stdout", "stderr"],
        },
        tail: {
          type: "number",
        },
        artifactType: {
          type: "string",
        },
        limit: {
          type: "number",
        },
      },
    },
    execute: async (_toolCallId, params) => {
      const action = requiredEnum(params, "action", JOB_ACTIONS);
      if (action === "list") {
        const query = [];
        if (optionalString(params, "campaignId")) {
          query.push(`campaign_id=${encodeURIComponent(optionalString(params, "campaignId"))}`);
        }
        if (optionalString(params, "status")) {
          query.push(`status=${encodeURIComponent(optionalString(params, "status"))}`);
        }
        return jsonResult(
          await callJsonApi({
            baseUrl: cfg.apiBase,
            tokenEnv: "TROTTERS_API_TOKEN",
            actor: cfg.actor,
            path: `/api/v1/jobs${query.length ? `?${query.join("&")}` : ""}`,
          }),
        );
      }
      if (action === "get") {
        const jobId = requiredString(params, "jobId");
        return jsonResult(
          await callJsonApi({
            baseUrl: cfg.apiBase,
            tokenEnv: "TROTTERS_API_TOKEN",
            actor: cfg.actor,
            path: `/api/v1/jobs/${encodeURIComponent(jobId)}`,
          }),
        );
      }
      if (action === "logs") {
        const jobId = requiredString(params, "jobId");
        const stream = optionalString(params, "stream") || "stderr";
        const tail = numberOrDefault(params?.tail, cfg.defaultLogTailLines);
        return jsonResult(
          await callJsonApi({
            baseUrl: cfg.apiBase,
            tokenEnv: "TROTTERS_API_TOKEN",
            actor: cfg.actor,
            path: `/api/v1/jobs/${encodeURIComponent(jobId)}/logs?stream=${encodeURIComponent(stream)}&tail=${encodeURIComponent(String(tail))}`,
          }),
        );
      }
      const query = [];
      if (optionalString(params, "jobId")) {
        query.push(`job_id=${encodeURIComponent(optionalString(params, "jobId"))}`);
      }
      if (optionalString(params, "campaignId")) {
        query.push(`campaign_id=${encodeURIComponent(optionalString(params, "campaignId"))}`);
      }
      if (optionalString(params, "artifactType")) {
        query.push(`artifact_type=${encodeURIComponent(optionalString(params, "artifactType"))}`);
      }
      query.push(`limit=${encodeURIComponent(String(numberOrDefault(params?.limit, 100)))}`);
      return jsonResult(
        await callJsonApi({
          baseUrl: cfg.apiBase,
          tokenEnv: "TROTTERS_API_TOKEN",
          actor: cfg.actor,
          path: `/api/v1/artifacts?${query.join("&")}`,
        }),
      );
    },
  };
}

function createRunbookTool(cfg) {
  return {
    name: "trotters_runbook",
    label: "Trotters Runbook",
    description:
      "Read the approved work queue and record recoveries or escalations. Use this to choose the next safe work item and keep a durable supervisor incident history.",
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["action"],
      properties: {
        action: {
          type: "string",
          enum: RUNBOOK_ACTIONS,
        },
        currentPlanId: {
          type: "string",
        },
        planId: {
          type: "string",
        },
        preferFallback: {
          type: "boolean",
        },
        incidentId: {
          type: "string",
        },
        failureClass: {
          type: "string",
        },
        fingerprint: {
          type: "string",
        },
        reason: {
          type: "string",
        },
      },
    },
    execute: async (_toolCallId, params) => {
      const action = requiredEnum(params, "action", RUNBOOK_ACTIONS);
      const runbook = loadRunbook(cfg);
      const queueSummary = await loadRunbookQueueSummary(cfg);
      if (action === "get") {
        return jsonResult({
          runbook,
          queue_summary: queueSummary,
          history: readHistory(cfg),
        });
      }
      if (action === "next_work_item") {
        const currentPlanId = optionalString(params, "currentPlanId") || await inferCurrentPlanIdFromOverview(cfg, runbook);
        const item = nextWorkItem(runbook, {
          currentPlanId,
          preferFallback: params?.preferFallback === true,
        }, queueSummary);
        return jsonResult({
          selected: item,
          current_plan_id: currentPlanId || null,
          blocked_reason: item ? null : summarizeRunbookSelectionBlock(queueSummary),
          queue_summary: queueSummary,
          runbook,
          history: readHistory(cfg),
        });
      }
      const incidentId = optionalString(params, "incidentId") || `incident-${crypto.randomUUID()}`;
      const record = {
        recorded_at_utc: new Date().toISOString(),
        event_type: action,
        plan_id: optionalString(params, "planId"),
        incident_id: incidentId,
        failure_class: optionalString(params, "failureClass"),
        fingerprint: optionalString(params, "fingerprint") || buildRunbookIncidentFingerprint(params, incidentId),
        reason: optionalString(params, "reason"),
      };
      appendHistory(cfg, record);
      const incidentSummary = writeSummaryRecord(cfg, {
        summaryType: SUPERVISOR_INCIDENT_SUMMARY_TYPE,
        agentId: "runtime-supervisor",
        status: action === "record_recovery" ? "recovered" : "escalated",
        classification: optionalString(params, "failureClass") || "runtime_incident",
        recommendedAction: action === "record_recovery" ? "continue_monitoring" : "manual_investigation",
        message: optionalString(params, "reason"),
        incidentId,
        fingerprint: record.fingerprint,
        suppressIfRecent: true,
        dedupeWindowMinutes: 180
      });
      return jsonResult({
        recorded: record,
        incident_summary: incidentSummary.record,
        history: readHistory(cfg),
      });
    },
  };
}
function createServiceTool(cfg) {
  return {
    name: "trotters_service",
    label: "Trotters Service",
    description:
      "List restartable services or request a narrow service restart through ops-bridge. Use this only after confirming a service-health symptom and within the runbook restart policy.",
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["action"],
      properties: {
        action: {
          type: "string",
          enum: SERVICE_ACTIONS,
        },
        service: {
          type: "string",
        },
        reason: {
          type: "string",
        },
        incidentId: {
          type: "string",
        },
      },
    },
    execute: async (_toolCallId, params) => {
      const action = requiredEnum(params, "action", SERVICE_ACTIONS);
      if (action === "list") {
        return jsonResult(await callJsonApi({ baseUrl: cfg.opsBridgeBase, tokenEnv: "TROTTERS_OPS_BRIDGE_TOKEN", actor: cfg.actor, path: "/api/v1/services" }));
      }
      const service = requiredString(params, "service");
      return jsonResult(
        await callJsonApi({
          baseUrl: cfg.opsBridgeBase,
          tokenEnv: "TROTTERS_OPS_BRIDGE_TOKEN",
          actor: cfg.actor,
          path: `/api/v1/services/${encodeURIComponent(service)}/restart`,
          method: "POST",
          payload: {
            reason: optionalString(params, "reason") || "runtime_supervisor_restart",
            incident_id: optionalString(params, "incidentId"),
          },
        }),
      );
    },
  };
}

async function postDirectorAction(cfg, directorId, action, payload) {
  return await callJsonApi({
    baseUrl: cfg.apiBase,
    tokenEnv: "TROTTERS_API_TOKEN",
    actor: cfg.actor,
    path: `/api/v1/directors/${encodeURIComponent(directorId)}/${action}`,
    method: "POST",
    payload,
  });
}

async function callJsonApi({ baseUrl, tokenEnv, actor, path: relativePath, method = "GET", payload = undefined }) {
  const token = requiredEnv(tokenEnv);
  const requestId = crypto.randomUUID();
  const response = await fetch(`${baseUrl}${relativePath}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "X-Request-Id": requestId,
      "X-Trotters-Actor": actor,
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const text = await response.text();
  let parsed = null;
  try {
    parsed = text ? JSON.parse(text) : {};
  } catch {
    parsed = { raw: text };
  }
  if (!response.ok) {
    throw new Error(`${method} ${relativePath} failed with ${response.status}: ${JSON.stringify(parsed)}`);
  }
  return parsed;
}

function loadRunbook(cfg) {
  const text = fs.readFileSync(cfg.runbookPath, "utf-8");
  const payload = JSON.parse(text);
  if (!payload || typeof payload !== "object") {
    throw new Error("Supervisor runbook must be a JSON object");
  }
  return payload;
}

function resolveWorkItem(runbook, planId) {
  const item = (runbook.work_queue || []).find((entry) => entry && entry.plan_id === planId);
  if (!item) {
    throw new Error(`Unknown runbook plan_id '${planId}'`);
  }
  return item;
}

function resolveConfigPath(runbook, configId) {
  const registry = runbook.config_registry || {};
  const pathValue = registry[configId];
  if (!pathValue) {
    throw new Error(`Unknown runbook config_id '${configId}'`);
  }
  return pathValue;
}

function nextWorkItem(runbook, params, queueSummary = null) {
  const queue = Array.isArray(runbook.work_queue) ? runbook.work_queue.filter((entry) => entry?.enabled !== false) : [];
  if (queue.length === 0) {
    return null;
  }
  const governedItem = nextGovernedWorkItem(runbook, params, queueSummary);
  if (governedItem !== undefined) {
    return governedItem;
  }
  const currentPlanId = params.currentPlanId || null;
  if (!currentPlanId) {
    return queue[0];
  }
  const current = queue.find((entry) => entry.plan_id === currentPlanId);
  if (params.preferFallback && current?.fallback_to) {
    const fallback = queue.find((entry) => entry.plan_id === current.fallback_to);
    if (fallback) {
      return fallback;
    }
  }
  const currentIndex = queue.findIndex((entry) => entry.plan_id === currentPlanId);
  if (currentIndex === -1) {
    return null;
  }
  return queue[currentIndex + 1] || null;
}

function nextGovernedWorkItem(runbook, params, queueSummary) {
  if (!queueSummary || typeof queueSummary !== "object") {
    return undefined;
  }
  const entries = Array.isArray(queueSummary.entries) ? queueSummary.entries : [];
  if (!entries.length) {
    return undefined;
  }
  const queue = Array.isArray(runbook.work_queue) ? runbook.work_queue.filter((entry) => entry?.enabled !== false) : [];
  const currentPlanId = params.currentPlanId || null;
  if (params.preferFallback && currentPlanId) {
    const current = queue.find((entry) => entry?.plan_id === currentPlanId);
    const fallbackPlanId = optionalString(current, "fallback_to");
    if (fallbackPlanId) {
      const fallbackEntry = entries.find((entry) => optionalString(entry, "plan_id") === fallbackPlanId);
      if (optionalString(fallbackEntry, "queue_status") === "ready") {
        return resolveWorkItem(runbook, fallbackPlanId);
      }
    }
  }
  const nextPlanId = optionalString(queueSummary, "next_runnable_plan_id");
  if (nextPlanId) {
    return resolveWorkItem(runbook, nextPlanId);
  }
  if (!currentPlanId) {
    const firstReady = entries.find((entry) => optionalString(entry, "queue_status") === "ready");
    const firstReadyPlanId = optionalString(firstReady, "plan_id");
    if (firstReadyPlanId) {
      return resolveWorkItem(runbook, firstReadyPlanId);
    }
  }
  if (optionalString(queueSummary, "recommended_action") || optionalString(queueSummary, "status")) {
    return null;
  }
  return undefined;
}

function summarizeRunbookSelectionBlock(queueSummary) {
  if (!queueSummary || typeof queueSummary !== "object") {
    return "No approved runnable queue item is available.";
  }
  const message = optionalString(queueSummary, "message");
  if (message) {
    return message;
  }
  const recommendedAction = optionalString(queueSummary, "recommended_action");
  if (recommendedAction === "repair_runbook_alignment") {
    return "Supervisor work queue needs alignment repair before the next branch can be started safely.";
  }
  if (recommendedAction === "define_next_research_family") {
    return "No approved runnable research family remains in the supervisor queue.";
  }
  return "No approved runnable queue item is available.";
}

async function loadRunbookQueueSummary(cfg) {
  try {
    return await callJsonApi({
      baseUrl: cfg.apiBase,
      tokenEnv: "TROTTERS_API_TOKEN",
      actor: cfg.actor,
      path: "/api/v1/runtime/runbook-queue",
    });
  } catch {
    return null;
  }
}
async function inferCurrentPlanIdFromOverview(cfg, runbook) {
  try {
    const overview = await callJsonApi({
      baseUrl: cfg.apiBase,
      tokenEnv: "TROTTERS_API_TOKEN",
      actor: cfg.actor,
      path: "/api/v1/runtime/overview",
    });
    const terminalDirector = overview?.most_recent_terminal?.director;
    const planName = optionalString(terminalDirector, "plan_name");
    if (planName) {
      return planName;
    }
    const directorName = optionalString(terminalDirector, "director_name");
    if (!directorName) {
      return null;
    }
    const queue = Array.isArray(runbook?.work_queue) ? runbook.work_queue : [];
    return queue.find((entry) => optionalString(entry, "director_name") === directorName)?.plan_id || null;
  } catch {
    return null;
  }
}

function readHistory(cfg) {
  if (!fs.existsSync(cfg.runbookHistoryPath)) {
    return [];
  }
  const lines = fs.readFileSync(cfg.runbookHistoryPath, "utf-8").split(/\r?\n/).filter(Boolean);
  return lines
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter(Boolean)
    .slice(-100)
    .reverse();
}

function appendHistory(cfg, record) {
  const directory = path.dirname(cfg.runbookHistoryPath);
  fs.mkdirSync(directory, { recursive: true });
  fs.appendFileSync(cfg.runbookHistoryPath, `${JSON.stringify(record)}\n`, "utf-8");
}

function summarizeOverviewPayload(cfg, payload, { notificationLimit, includeRaw }) {
  const safeLimit = Math.max(1, Math.min(20, Math.trunc(numberOrDefault(notificationLimit, 5))));
  const summary = {
    health: pickFields(payload?.health, ["status", "summary", "reason", "healthy", "severity"]),
    counts: pickFields(payload?.status?.counts, ["queued", "running", "completed", "failed", "paused"]),
    workers: summarizeWorkers(payload?.status?.workers),
    active_directors: summarizeEntries(payload?.active_directors, [
      "director_id",
      "director_name",
      "status",
      "current_campaign_id",
      "successful_campaign_id",
      "last_terminal_status",
      "updated_at",
    ]),
    active_campaigns: summarizeEntries(payload?.active_campaigns, [
      "campaign_id",
      "campaign_name",
      "status",
      "phase",
      "director_id",
      "latest_report_path",
      "updated_at",
    ]),
    most_recent_terminal: summarizeMostRecentTerminal(payload?.most_recent_terminal),
    recent_notifications: Array.isArray(payload?.notifications)
      ? payload.notifications.slice(0, safeLimit).map((entry) =>
          summarizeEntry(entry, [
            "campaign_id",
            "campaign_name",
            "event_type",
            "severity",
            "message",
            "recorded_at_utc",
            "payload_path",
          ]),
        )
      : [],
  };
  summary.supervisor_decision = buildSupervisorDecision(cfg, summary);

  if (!includeRaw) {
    return { summary };
  }
  return {
    summary,
    raw: payload,
  };
}

function summarizeMostRecentTerminal(terminalPayload) {
  if (!terminalPayload || typeof terminalPayload !== "object") {
    return {};
  }
  const campaignTerminal =
    terminalPayload?.campaign && typeof terminalPayload.campaign === "object"
      ? terminalPayload.campaign
      : null;
  const directorTerminal =
    terminalPayload?.director && typeof terminalPayload.director === "object"
      ? terminalPayload.director
      : null;
  const legacyFlatTerminal = campaignTerminal || directorTerminal ? null : terminalPayload;
  const primary = campaignTerminal || directorTerminal || legacyFlatTerminal || {};
  return {
    campaign_id: optionalString(campaignTerminal || legacyFlatTerminal, "campaign_id"),
    campaign_name: optionalString(campaignTerminal || legacyFlatTerminal, "campaign_name"),
    director_id: optionalString(directorTerminal || campaignTerminal, "director_id"),
    director_name: optionalString(directorTerminal, "director_name"),
    status:
      optionalString(campaignTerminal || legacyFlatTerminal, "status") ||
      optionalString(directorTerminal, "status") ||
      null,
    director_plan_name:
      optionalString(directorTerminal?.spec, "plan_name") ||
      optionalString(directorTerminal, "plan_name") ||
      null,
    event_type: optionalString(primary, "event_type"),
    severity: optionalString(primary, "severity"),
    message: optionalString(primary, "message"),
    recorded_at_utc:
      optionalString(primary, "recorded_at_utc") ||
      optionalString(primary, "finished_at") ||
      optionalString(primary, "updated_at") ||
      null,
    payload_path: optionalString(primary, "payload_path"),
  };
}

function summarizeWorkers(workers) {
  if (!Array.isArray(workers)) {
    return { count: 0, active: [] };
  }
  return {
    count: workers.length,
    active: workers.slice(0, 10).map((worker) =>
      summarizeEntry(worker, ["worker_id", "hostname", "status", "leased_job_id", "heartbeat_at"]),
    ),
  };
}

function buildSupervisorDecision(cfg, summary) {
  const activeDirectors = Array.isArray(summary?.active_directors) ? summary.active_directors.length : 0;
  const activeCampaigns = Array.isArray(summary?.active_campaigns) ? summary.active_campaigns.length : 0;
  const workerCount = numberOrDefault(summary?.workers?.count, 0);
  const healthStatus = String(summary?.health?.status || "").trim().toLowerCase();
  const terminalStatus = String(summary?.most_recent_terminal?.status || "").trim().toLowerCase();
  const terminalEvent = String(summary?.most_recent_terminal?.event_type || "").trim().toLowerCase();
  const terminalMessage = String(summary?.most_recent_terminal?.message || "").trim().toLowerCase();
  const terminalSeverity = String(summary?.most_recent_terminal?.severity || "").trim().toLowerCase();
  const hasActiveRuntime = activeDirectors > 0 || activeCampaigns > 0;
  const degradedFingerprint = hasActiveRuntime ? buildSupervisorIncidentFingerprint("active_degraded", summary) : null;
  const degradedCooldown = degradedFingerprint ? loadSupervisorIncidentCooldown(cfg, degradedFingerprint, SUPERVISOR_INCIDENT_COOLDOWN_MINUTES) : inactiveIncidentCooldown();
  const exhaustedFingerprint = buildSupervisorIncidentFingerprint("idle_exhausted_ready_for_next", summary);
  const exhaustedRecent = isRecentTerminal(summary?.most_recent_terminal, SUPERVISOR_EXHAUSTED_STALE_HOURS);
  const exhaustedPlanId = optionalString(summary?.most_recent_terminal, "director_plan_name");

  if (hasActiveRuntime) {
    if (healthStatus === "healthy" && workerCount > 0) {
      return {
        classification: "active_healthy",
        recommended_mode: "monitor_only",
        reason: "Directors or campaigns are already active, workers are present, and health is healthy.",
        preferred_tools: [],
        blocked_mutations: ["trotters_director.start", "trotters_campaign.start", "trotters_service.restart"],
        incident_fingerprint: null,
        cooldown_active: false,
        cooldown_remaining_seconds: 0,
        recent_incident: null,
      };
    }
    if (degradedCooldown.active) {
      return {
        classification: "active_degraded_cooldown",
        recommended_mode: "service_health_cooldown",
        reason: "The same degraded runtime incident was already recorded recently; avoid repeating restart or escalation churn until the cooldown expires.",
        preferred_tools: ["trotters_summaries.latest", "trotters_runbook.get"],
        blocked_mutations: [
          "trotters_director.start",
          "trotters_campaign.start",
          "trotters_service.restart",
          "trotters_runbook.record_recovery",
          "trotters_runbook.record_escalation",
        ],
        incident_fingerprint: degradedFingerprint,
        cooldown_active: true,
        cooldown_remaining_seconds: degradedCooldown.remainingSeconds,
        recent_incident: degradedCooldown.record,
      };
    }
    return {
      classification: "active_degraded",
      recommended_mode: "service_health_only",
      reason: "Directors or campaigns are active, but health or worker signals indicate degradation.",
      preferred_tools: ["trotters_service.list", "trotters_service.restart", "trotters_runbook.record_recovery", "trotters_runbook.record_escalation"],
      blocked_mutations: ["trotters_director.start", "trotters_campaign.start"],
      incident_fingerprint: degradedFingerprint,
      cooldown_active: false,
      cooldown_remaining_seconds: 0,
      recent_incident: degradedCooldown.record,
    };
  }

  if (isFailureTerminalState(terminalStatus, terminalEvent, terminalMessage, terminalSeverity)) {
    return {
      classification: "idle_investigate_failure",
      recommended_mode: "investigate_before_action",
      reason: "No active runtime is present and the latest terminal signal indicates a failed or stopped outcome.",
      preferred_tools: ["trotters_review_pack", "trotters_jobs.list", "trotters_jobs.logs", "trotters_runbook.record_escalation"],
      blocked_mutations: ["trotters_director.start", "trotters_campaign.start", "trotters_service.restart"],
      incident_fingerprint: buildSupervisorIncidentFingerprint("idle_investigate_failure", summary),
      cooldown_active: false,
      cooldown_remaining_seconds: 0,
      recent_incident: null,
    };
  }

  if (isExhaustedTerminalState(terminalStatus, terminalEvent, terminalMessage) && exhaustedRecent) {
    return {
      classification: "idle_exhausted_ready_for_next",
      recommended_mode: "advance_runbook",
      reason: "No active runtime is present and the latest terminal signal exhausted cleanly.",
      preferred_tools: ["trotters_runbook.next_work_item", "trotters_director.start", "trotters_runbook.record_recovery"],
      blocked_mutations: [],
      incident_fingerprint: exhaustedFingerprint,
      current_plan_id: exhaustedPlanId,
      cooldown_active: false,
      cooldown_remaining_seconds: 0,
      recent_incident: null,
    };
  }

  if (isExhaustedTerminalState(terminalStatus, terminalEvent, terminalMessage)) {
    return {
      classification: "idle_exhausted_stale_context",
      recommended_mode: "inspect_runbook_or_wait",
      reason: "The last exhausted terminal signal is stale, so do not advance the runbook automatically without fresher context.",
      preferred_tools: ["trotters_runbook.get", "trotters_summaries.latest"],
      blocked_mutations: ["trotters_director.start", "trotters_campaign.start", "trotters_service.restart"],
      incident_fingerprint: exhaustedFingerprint,
      current_plan_id: exhaustedPlanId,
      cooldown_active: false,
      cooldown_remaining_seconds: 0,
      recent_incident: null,
    };
  }

  return {
    classification: "idle_waiting_for_context",
    recommended_mode: "inspect_runbook_or_wait",
    reason: "No active runtime is present and there is no clear recent terminal signal to act on.",
    preferred_tools: ["trotters_runbook.get"],
    blocked_mutations: ["trotters_service.restart"],
    incident_fingerprint: null,
    cooldown_active: false,
    cooldown_remaining_seconds: 0,
    recent_incident: null,
  };
}

function buildSupervisorIncidentFingerprint(classification, summary) {
  const healthStatus = String(summary?.health?.status || "unknown").trim().toLowerCase() || "unknown";
  const workerCount = numberOrDefault(summary?.workers?.count, 0);
  const directorKeys = Array.isArray(summary?.active_directors)
    ? summary.active_directors.map((entry) => String(entry?.director_name || entry?.director_id || "").trim()).filter(Boolean).sort().slice(0, 4)
    : [];
  const campaignKeys = Array.isArray(summary?.active_campaigns)
    ? summary.active_campaigns.map((entry) => String(entry?.campaign_name || entry?.campaign_id || "").trim()).filter(Boolean).sort().slice(0, 4)
    : [];
  const terminal = summary?.most_recent_terminal || {};
  const pieces = [
    `classification=${String(classification || "runtime").trim().toLowerCase() || "runtime"}`,
    `health=${healthStatus}`,
    `workers=${workerCount}`,
    `directors=${directorKeys.join(",") || "-"}`,
    `campaigns=${campaignKeys.join(",") || "-"}`,
    `terminal=${String(terminal?.event_type || "-").trim().toLowerCase() || "-"}`,
    `target=${String(terminal?.campaign_id || terminal?.campaign_name || "-").trim().toLowerCase() || "-"}`,
  ];
  return `supervisor:${pieces.join(":")}`;
}

function loadSupervisorIncidentCooldown(cfg, fingerprint, cooldownMinutes) {
  if (!fingerprint) {
    return inactiveIncidentCooldown();
  }
  const records = loadSummaryRecords(cfg, { summaryType: SUPERVISOR_INCIDENT_SUMMARY_TYPE, limit: 100 });
  const matching = records.find((record) => record && record.fingerprint === fingerprint);
  if (!matching) {
    return inactiveIncidentCooldown();
  }
  const age = ageSeconds(matching.recorded_at_utc);
  const windowSeconds = Math.max(60, Math.trunc(numberOrDefault(cooldownMinutes, SUPERVISOR_INCIDENT_COOLDOWN_MINUTES) * 60));
  if (age === null || age > windowSeconds) {
    return { active: false, remainingSeconds: 0, record: summarizeIncidentRecord(matching) };
  }
  return {
    active: true,
    remainingSeconds: Math.max(0, windowSeconds - age),
    record: summarizeIncidentRecord(matching),
  };
}

function inactiveIncidentCooldown() {
  return { active: false, remainingSeconds: 0, record: null };
}

function summarizeIncidentRecord(record) {
  return pickFields(record, ["summary_id", "status", "classification", "recommended_action", "message", "incident_id", "fingerprint", "recorded_at_utc"]);
}

function isRecentTerminal(terminal, maxAgeHours) {
  const age = ageSeconds(terminal?.recorded_at_utc);
  if (age === null) {
    return false;
  }
  return age <= Math.max(1, Math.trunc(numberOrDefault(maxAgeHours, SUPERVISOR_EXHAUSTED_STALE_HOURS) * 3600));
}

function isFailureTerminalState(eventType, message, severity) {
  if (["error", "critical"].includes(severity)) {
    return true;
  }
  if (eventType.includes("failed") || eventType.includes("stopped")) {
    return true;
  }
  return message.includes("failed") || message.includes("stopped");
}

function isExhaustedTerminalState(eventType, message) {
  if (eventType.includes("finished") || eventType.includes("exhausted") || eventType.includes("promoted")) {
    return true;
  }
  return message.includes("exhaust") || message.includes("promot");
}

function summarizeEntries(entries, keys) {
  if (!Array.isArray(entries)) {
    return [];
  }
  return entries.slice(0, 10).map((entry) => summarizeEntry(entry, keys));
}

function summarizeNotifications(entries, limit) {
  if (!Array.isArray(entries)) {
    return [];
  }
  const safeLimit = Math.max(1, Math.min(20, Math.trunc(numberOrDefault(limit, 5))));
  return entries.slice(0, safeLimit).map((entry) =>
    summarizeEntry(entry, [
      "campaign_id",
      "campaign_name",
      "event_type",
      "severity",
      "message",
      "recorded_at_utc",
      "payload_path",
    ]),
  );
}

function summarizeEntry(value, keys) {
  return pickFields(value, keys);
}

function pickFields(value, keys) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  const result = {};
  for (const key of keys) {
    if (Object.hasOwn(value, key) && value[key] !== undefined && value[key] !== null) {
      result[key] = value[key];
    }
  }
  return result;
}

function createReviewPackTool(cfg) {
  return {
    name: "trotters_review_pack",
    label: "Trotters Review Pack",
    description: "Read compact campaign, candidate, paper-trade, or failure review packs from runtime state and catalog artifacts.",
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["action"],
      properties: {
        action: { type: "string", enum: REVIEW_PACK_ACTIONS },
        campaignId: { type: "string" },
        profileName: { type: "string" },
        limit: { type: "number" }
      }
    },
    execute: async (_toolCallId, params) => {
      const action = requiredEnum(params, "action", REVIEW_PACK_ACTIONS);
      if (action === "campaign_triage") return jsonResult(await buildCampaignTriagePack(cfg, params));
      if (action === "candidate_review") return jsonResult(buildCandidateReviewPack(cfg, params));
      if (action === "paper_trade_readiness") return jsonResult(buildPaperTradeReadinessPack(cfg, params));
      return jsonResult(await buildFailurePostmortemPack(cfg, params));
    }
  };
}

function createSummariesTool(cfg) {
  return {
    name: "trotters_summaries",
    label: "Trotters Summaries",
    description: "Read or record durable agent summary artifacts with duplicate suppression by fingerprint.",
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["action"],
      properties: {
        action: { type: "string", enum: SUMMARY_ACTIONS },
        summaryType: { type: "string", enum: SUMMARY_TYPES },
        limit: { type: "number" },
        agentId: { type: "string" },
        status: { type: "string" },
        classification: { type: "string" },
        recommendedAction: { type: "string" },
        message: { type: "string" },
        evidence: { type: "array", items: { type: "string" } },
        artifactRefs: { type: "array", items: { type: "string" } },
        incidentId: { type: "string" },
        campaignId: { type: "string" },
        directorId: { type: "string" },
        profileName: { type: "string" },
        fingerprint: { type: "string" },
        suppressIfRecent: { type: "boolean" },
        dedupeWindowMinutes: { type: "number" }
      }
    },
    execute: async (_toolCallId, params) => {
      const action = requiredEnum(params, "action", SUMMARY_ACTIONS);
      if (action === "latest") return jsonResult(loadLatestSummaries(cfg, { summaryType: optionalString(params, "summaryType") }));
      if (action === "list") return jsonResult(loadSummaryRecords(cfg, { summaryType: optionalString(params, "summaryType"), limit: numberOrDefault(params?.limit, 20) }));
      return jsonResult(writeSummaryRecord(cfg, {
        summaryType: requiredEnum(params, "summaryType", SUMMARY_TYPES),
        agentId: optionalString(params, "agentId"),
        status: optionalString(params, "status"),
        classification: optionalString(params, "classification"),
        recommendedAction: optionalString(params, "recommendedAction"),
        message: optionalString(params, "message"),
        evidence: optionalStringArray(params, "evidence"),
        artifactRefs: optionalStringArray(params, "artifactRefs"),
        incidentId: optionalString(params, "incidentId"),
        campaignId: optionalString(params, "campaignId"),
        directorId: optionalString(params, "directorId"),
        profileName: optionalString(params, "profileName"),
        fingerprint: optionalString(params, "fingerprint"),
        suppressIfRecent: params?.suppressIfRecent === true,
        dedupeWindowMinutes: numberOrDefault(params?.dedupeWindowMinutes, 360)
      }));
    }
  };
}

async function buildCampaignTriagePack(cfg, params) {
  const limit = Math.max(1, Math.min(20, Math.trunc(numberOrDefault(params?.limit, 5))));
  let detail = null;
  const campaignId = optionalString(params, "campaignId");
  if (campaignId) {
    detail = await callJsonApi({ baseUrl: cfg.apiBase, tokenEnv: "TROTTERS_API_TOKEN", actor: cfg.actor, path: `/api/v1/campaigns/${encodeURIComponent(campaignId)}` });
  } else {
    const overview = await callJsonApi({ baseUrl: cfg.apiBase, tokenEnv: "TROTTERS_API_TOKEN", actor: cfg.actor, path: "/api/v1/runtime/overview" });
    const latest = latestTerminalEntry(overview?.status?.campaigns);
    const id = optionalString(overview?.most_recent_terminal?.campaign, "campaign_id") || latest?.campaign_id;
    if (id) detail = await callJsonApi({ baseUrl: cfg.apiBase, tokenEnv: "TROTTERS_API_TOKEN", actor: cfg.actor, path: `/api/v1/campaigns/${encodeURIComponent(id)}` });
  }
  const campaign = detail?.campaign && typeof detail.campaign === "object" ? detail.campaign : null;
  if (!campaign) return { pack_type: "campaign_triage", status: "missing", reason: "No terminal campaign available." };
  const reportDir = path.dirname(String(campaign.latest_report_path || ""));
  const notifications = await callJsonApi({ baseUrl: cfg.apiBase, tokenEnv: "TROTTERS_API_TOKEN", actor: cfg.actor, path: `/api/v1/notifications?campaign_id=${encodeURIComponent(String(campaign.campaign_id || ""))}&limit=${encodeURIComponent(String(limit))}` });
  return {
    pack_type: "campaign_triage",
    status: "ok",
    campaign: summarizeEntry(campaign, ["campaign_id", "campaign_name", "status", "phase", "director_id", "latest_report_path", "last_error", "updated_at", "finished_at"]),
    final_decision: summarizeFinalDecision(campaign?.state?.final_decision),
    notifications: summarizeNotifications(notifications?.notifications, limit),
    report_artifacts: loadReportArtifacts(reportDir)
  };
}

function buildCandidateReviewPack(cfg, params) {
  const profileArtifacts = loadLatestProfileArtifacts(cfg);
  const profileName = optionalString(params, "profileName") || selectLatestProfileName(profileArtifacts, ["operator_scorecard", "promotion", "promotion_decision"]);
  if (!profileName) return { pack_type: "candidate_review", status: "missing", reason: "No candidate profile artifacts available." };
  const snapshot = profileArtifacts[profileName] || {};
  const promotionPointer = pickArtifactPointer(snapshot, ["promotion", "promotion_decision", "promotion_artifacts"]);
  const scorecardPointer = pickArtifactPointer(snapshot, ["operator_scorecard"]);
  const paperTradePointer = pickArtifactPointer(snapshot, ["paper_trade_decision"]);
  return {
    pack_type: "candidate_review",
    status: "ok",
    profile_name: profileName,
    artifacts: summarizeArtifactPointers({ promotion: promotionPointer, operator_scorecard: scorecardPointer, paper_trade_decision: paperTradePointer }),
    promotion: summarizePromotionDecision(loadPromotionPayload(promotionPointer)),
    operator_scorecard: summarizeOperatorScorecard(readJsonFile(optionalString(scorecardPointer, "primary_path"))),
    paper_trade_decision: summarizePaperTradeDecision(readJsonFile(optionalString(paperTradePointer, "primary_path"))),
    profile_history: readJsonlTail(historyPathForProfile(cfg, profileName), 5).map((entry) => summarizePromotionDecision(entry))
  };
}

function buildPaperTradeReadinessPack(cfg, params) {
  const profileArtifacts = loadLatestProfileArtifacts(cfg);
  const profileName = optionalString(params, "profileName") || selectLatestProfileName(profileArtifacts, ["paper_trade_decision", "operator_scorecard", "promotion"]);
  if (!profileName) return { pack_type: "paper_trade_readiness", status: "missing", reason: "No paper-trade readiness artifacts available." };
  const snapshot = profileArtifacts[profileName] || {};
  const promotionPointer = pickArtifactPointer(snapshot, ["promotion", "promotion_decision", "promotion_artifacts"]);
  const scorecardPointer = pickArtifactPointer(snapshot, ["operator_scorecard"]);
  const paperTradePointer = pickArtifactPointer(snapshot, ["paper_trade_decision"]);
  return {
    pack_type: "paper_trade_readiness",
    status: "ok",
    profile_name: profileName,
    freshness: { promotion: summarizePointerFreshness(promotionPointer), operator_scorecard: summarizePointerFreshness(scorecardPointer), paper_trade_decision: summarizePointerFreshness(paperTradePointer) },
    artifacts: summarizeArtifactPointers({ promotion: promotionPointer, operator_scorecard: scorecardPointer, paper_trade_decision: paperTradePointer }),
    operator_scorecard: summarizeOperatorScorecard(readJsonFile(optionalString(scorecardPointer, "primary_path"))),
    paper_trade_decision: summarizePaperTradeDecision(readJsonFile(optionalString(paperTradePointer, "primary_path")))
  };
}
async function buildFailurePostmortemPack(cfg, params) {
  const limit = Math.max(1, Math.min(20, Math.trunc(numberOrDefault(params?.limit, 5))));
  const overview = await callJsonApi({ baseUrl: cfg.apiBase, tokenEnv: "TROTTERS_API_TOKEN", actor: cfg.actor, path: "/api/v1/runtime/overview" });
  const failedJobs = await callJsonApi({ baseUrl: cfg.apiBase, tokenEnv: "TROTTERS_API_TOKEN", actor: cfg.actor, path: "/api/v1/jobs?status=failed" });
  const notifications = await callJsonApi({ baseUrl: cfg.apiBase, tokenEnv: "TROTTERS_API_TOKEN", actor: cfg.actor, path: `/api/v1/notifications?limit=${encodeURIComponent(String(limit))}` });
  return {
    pack_type: "failure_postmortem",
    status: "ok",
    health: pickFields(overview?.health, ["status", "summary"]),
    most_recent_terminal: overview?.most_recent_terminal || null,
    recent_notifications: summarizeNotifications(notifications?.notifications, limit).filter((record) => ["warning", "error", "critical"].includes(String(record.severity || "").toLowerCase())),
    failed_jobs: Array.isArray(failedJobs?.jobs) ? failedJobs.jobs.slice(0, limit).map((job) => summarizeEntry(job, ["job_id", "campaign_id", "command", "status", "error_message", "updated_at"])) : [],
    prior_postmortems: loadSummaryRecords(cfg, { summaryType: "failure_postmortem_summary", limit })
  };
}

function loadLatestProfileArtifacts(cfg) {
  return readJsonFile(path.join(cfg.catalogRoot, "research_catalog", "latest_profile_artifacts.json")) || {};
}

function selectLatestProfileName(profileArtifacts, preferredTerms) {
  return Object.entries(profileArtifacts || {})
    .map(([profileName, snapshot]) => ({ profileName, pointer: pickArtifactPointer(snapshot, preferredTerms) }))
    .filter((entry) => entry.pointer)
    .sort((left, right) => timestampSortKey(right.pointer?.recorded_at_utc) - timestampSortKey(left.pointer?.recorded_at_utc))[0]?.profileName || null;
}

function pickArtifactPointer(snapshot, terms) {
  if (!snapshot || typeof snapshot !== "object") return null;
  for (const term of terms) {
    const key = `latest_${term}`;
    if (snapshot[key] && typeof snapshot[key] === "object") return snapshot[key];
  }
  const loweredTerms = terms.map((term) => term.toLowerCase());
  for (const [key, value] of Object.entries(snapshot)) {
    if (value && typeof value === "object" && loweredTerms.some((term) => key.toLowerCase().includes(term))) return value;
  }
  return null;
}

function summarizeArtifactPointers(pointers) {
  const result = {};
  for (const [key, value] of Object.entries(pointers)) {
    if (value && typeof value === "object") result[key] = summarizeEntry(value, ["recorded_at_utc", "artifact_type", "artifact_name", "primary_path", "evaluation_status", "strategy_family", "sweep_type"]);
  }
  return result;
}

function summarizeFinalDecision(value) {
  return pickFields(value, ["recommended_action", "reason", "selected_profile_name", "selected_candidate_eligible", "paper_trade_ready"]);
}

function summarizePromotionDecision(value) {
  if (!value || typeof value !== "object") return null;
  const profile = value.profile && typeof value.profile === "object" ? value.profile : {};
  return { profile_name: profile.profile_name || value.profile_name || null, eligible: value.eligible === true, recommended_action: value.recommended_action || null, fail_reasons: Array.isArray(value.fail_reasons) ? value.fail_reasons.slice(0, 8) : [], recorded_at_utc: value.recorded_at_utc || null };
}

function summarizeOperatorScorecard(value) {
  if (!value || typeof value !== "object") return null;
  return { operator_recommendation: value.operator_recommendation || null, campaign_decision: value.campaign_decision || null, summary: value.summary || null, strengths: Array.isArray(value.strengths) ? value.strengths.slice(0, 5) : [], weaknesses: Array.isArray(value.weaknesses) ? value.weaknesses.slice(0, 5) : [], next_steps: Array.isArray(value.next_steps) ? value.next_steps.slice(0, 5) : [] };
}

function summarizePaperTradeDecision(value) {
  if (!value || typeof value !== "object") return null;
  return { profile_name: value.profile_name || null, profile_version: value.profile_version || null, decision: value.decision || value.recommended_action || null, summary: value.summary || null, warnings: Array.isArray(value.warnings) ? value.warnings.slice(0, 8) : [], recorded_at_utc: value.recorded_at_utc || null };
}

function summarizePointerFreshness(pointer) {
  if (!pointer || typeof pointer !== "object") return { present: false, age_seconds: null };
  return { present: true, recorded_at_utc: pointer.recorded_at_utc || null, age_seconds: ageSeconds(pointer.recorded_at_utc) };
}

function loadPromotionPayload(pointer) {
  const primaryPath = optionalString(pointer, "primary_path");
  if (!primaryPath) return null;
  if (primaryPath.endsWith(".jsonl")) return readJsonlTail(primaryPath, 1)[0] || null;
  return readJsonFile(primaryPath);
}

function loadReportArtifacts(reportDir) {
  if (!reportDir || !fs.existsSync(reportDir) || !fs.statSync(reportDir).isDirectory()) return {};
  const refs = {};
  for (const name of ["operator_scorecard.json", "operator_scorecard.md", "candidate_comparison.md", "research_decision.json", "research_decision.md", "promotion_decision.json", "promotion_summary.md", "paper_trade_decision.json", "paper_trade_decision.md"]) {
    const candidate = path.join(reportDir, name);
    if (fs.existsSync(candidate)) refs[name] = candidate;
  }
  return { refs, operator_scorecard: summarizeOperatorScorecard(readJsonFile(refs["operator_scorecard.json"])), research_decision: summarizeFinalDecision(readJsonFile(refs["research_decision.json"])), promotion_decision: summarizePromotionDecision(readJsonFile(refs["promotion_decision.json"])), paper_trade_decision: summarizePaperTradeDecision(readJsonFile(refs["paper_trade_decision.json"])) };
}

function historyPathForProfile(cfg, profileName) { return path.join(cfg.catalogRoot, "profile_history", `${profileName}.jsonl`); }
function readJsonFile(filePath) { const value = typeof filePath === "string" && filePath.trim() ? filePath.trim() : ""; if (!value || !fs.existsSync(value)) return null; try { const parsed = JSON.parse(fs.readFileSync(value, "utf-8")); return parsed && typeof parsed === "object" ? parsed : null; } catch { return null; } }
function readJsonlTail(filePath, limit) { const value = typeof filePath === "string" && filePath.trim() ? filePath.trim() : ""; if (!value || !fs.existsSync(value)) return []; return fs.readFileSync(value, "utf-8").split(/\r?\n/).filter(Boolean).slice(-Math.max(1, Math.trunc(limit))).map((line) => { try { return JSON.parse(line); } catch { return null; } }).filter(Boolean).reverse(); }
function loadLatestSummaries(cfg, { summaryType } = {}) { const latestDir = path.join(cfg.summaryRoot, "latest"); if (!fs.existsSync(latestDir)) return summaryType ? null : {}; if (summaryType) return readJsonFile(path.join(latestDir, `${summaryType}.json`)); const result = {}; for (const type of SUMMARY_TYPES) { const record = readJsonFile(path.join(latestDir, `${type}.json`)); if (record) result[type] = record; } return result; }
function loadSummaryRecords(cfg, { summaryType = undefined, limit = 20 } = {}) { const index = readJsonFile(path.join(cfg.summaryRoot, "index.json")); const records = Array.isArray(index?.records) ? index.records : Array.isArray(index) ? index : []; return records.filter((record) => record && typeof record === "object" && (!summaryType || String(record.summary_type || "") === summaryType)).slice(0, Math.max(1, Math.trunc(limit))); }
function writeSummaryRecord(cfg, input) {
  const normalized = normalizeSummaryInput(cfg, input);
  const summaryType = normalized.summaryType;
  const latestDir = path.join(cfg.summaryRoot, "latest");
  const typeDir = path.join(cfg.summaryRoot, summaryType);
  fs.mkdirSync(typeDir, { recursive: true });
  fs.mkdirSync(latestDir, { recursive: true });
  const existing = loadSummaryRecords(cfg, { limit: 500 });
  if (normalized.suppressIfRecent && normalized.fingerprint) {
    const duplicate = existing.find((record) => record.summary_type === summaryType && record.fingerprint === normalized.fingerprint && ageSeconds(record.recorded_at_utc) !== null && ageSeconds(record.recorded_at_utc) <= numberOrDefault(normalized.dedupeWindowMinutes, 360) * 60);
    if (duplicate) return { suppressed: true, record: duplicate };
  }
  const recordedAt = new Date().toISOString();
  const record = { summary_id: `${summaryType}-${crypto.randomUUID()}`, summary_type: summaryType, agent_id: normalized.agentId, status: normalized.status, classification: normalized.classification, recommended_action: normalized.recommendedAction || null, message: normalized.message || null, evidence: Array.isArray(normalized.evidence) ? normalized.evidence.slice(0, 12) : [], artifact_refs: normalizeArtifactRefs(normalized), incident_id: normalized.incidentId || null, campaign_id: normalized.campaignId || null, director_id: normalized.directorId || null, profile_name: normalized.profileName || null, fingerprint: normalized.fingerprint || null, recorded_at_utc: recordedAt };
  const slug = String(record.incident_id || record.campaign_id || record.director_id || record.profile_name || record.classification || "summary").toLowerCase().replace(/[^a-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 80) || "summary";
  const fileName = `${String(recordedAt).replace(/[:.]/g, "").replace(/\+00:00$/, "Z")}__${slug}.json`;
  fs.writeFileSync(path.join(typeDir, fileName), JSON.stringify(record, null, 2), "utf-8");
  fs.writeFileSync(path.join(latestDir, `${summaryType}.json`), JSON.stringify(record, null, 2), "utf-8");
  fs.writeFileSync(path.join(cfg.summaryRoot, "index.json"), JSON.stringify({ records: [record, ...existing].slice(0, 500) }, null, 2), "utf-8");
  return { suppressed: false, record };
}

function normalizeSummaryInput(cfg, input) {
  const summaryType = requiredEnum({ summaryType: input.summaryType }, "summaryType", SUMMARY_TYPES);
  const rule = SPECIALIST_SUMMARY_RULES[summaryType] || null;
  const classification = normalizeSummaryClassification(summaryType, input.classification);
  return {
    ...input,
    summaryType,
    agentId: input.agentId || SUMMARY_DEFAULT_AGENT_IDS[summaryType] || cfg.actor,
    status: normalizeSummaryStatus(rule, input.status, classification),
    classification,
    recommendedAction: normalizeSummaryRecommendedAction(rule, input.recommendedAction, classification),
  };
}

function normalizeSummaryStatus(rule, status, classification) {
  const value = String(status || "").trim().toLowerCase();
  if (value === "blocked" || classification === "blocked") {
    return "blocked";
  }
  if (!rule) {
    return value || "recorded";
  }
  return "recorded";
}

function normalizeSummaryClassification(summaryType, classification) {
  const rule = SPECIALIST_SUMMARY_RULES[summaryType] || null;
  const value = String(classification || "").trim().toLowerCase();
  if (!rule) {
    return value || "summary";
  }
  if (!value) {
    return rule.defaultClassification;
  }
  if (value in rule.aliases) {
    return rule.aliases[value];
  }
  if (rule.allowedClassifications.includes(value)) {
    return value;
  }
  return value === "blocked" ? "blocked" : rule.defaultClassification;
}

function normalizeSummaryRecommendedAction(rule, recommendedAction, classification) {
  const value = String(recommendedAction || "").trim().toLowerCase();
  if (value) {
    return value;
  }
  const defaults = rule?.defaultRecommendedActions;
  if (defaults && typeof defaults === "object") {
    const fallback = defaults[classification];
    if (typeof fallback === "string" && fallback.trim()) {
      return fallback.trim();
    }
  }
  return null;
}

function normalizeArtifactRefs(input) {
  const provided = Array.isArray(input.artifactRefs) ? input.artifactRefs.filter((value) => typeof value === "string" && value.trim()).map((value) => value.trim()) : [];
  const evidencePaths = Array.isArray(input.evidence) ? input.evidence.filter((value) => typeof value === "string" && /[\/]/.test(value)).map((value) => value.trim()) : [];
  if (!provided.length) {
    return evidencePaths.slice(0, 12);
  }
  if (provided.some((value) => /[\/]/.test(value)) || !evidencePaths.length) {
    return provided.slice(0, 12);
  }
  return evidencePaths.slice(0, 12);
}
function latestTerminalEntry(entries) { if (!Array.isArray(entries)) return null; return entries.filter((entry) => entry && typeof entry === "object" && TERMINAL_STATUSES.has(String(entry.status || "").toLowerCase())).sort((left, right) => timestampSortKey(right.updated_at || right.finished_at) - timestampSortKey(left.updated_at || left.finished_at))[0] || null; }
function timestampSortKey(value) { const text = typeof value === "string" ? value.trim() : ""; if (!text) return 0; const parsed = Date.parse(text); return Number.isFinite(parsed) ? parsed : 0; }
function ageSeconds(value) { const timestamp = timestampSortKey(value); if (!timestamp) return null; const delta = Date.now() - timestamp; return delta >= 0 ? Math.trunc(delta / 1000) : 0; }
function buildRunbookIncidentFingerprint(params, incidentId) {
  const failureClass = optionalString(params, "failureClass") || "runtime_incident";
  const planId = optionalString(params, "planId") || "runtime";
  const reason = optionalString(params, "reason") || "";
  const reasonSlug = reason.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 48) || "none";
  return `runbook:${failureClass}:${planId}:${reasonSlug || incidentId}`;
}

function jsonResult(payload) {
  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(payload, null, 2),
      },
    ],
    details: payload,
  };
}

function requiredEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required`);
  }
  return value;
}

function requiredString(params, key) {
  const value = optionalString(params, key);
  if (!value) {
    throw new Error(`${key} is required`);
  }
  return value;
}

function optionalString(params, key) {
  const value = params?.[key];
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed || undefined;
}

function optionalStringArray(params, key) {
  const value = params?.[key];
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((entry) => typeof entry === "string").map((entry) => entry.trim()).filter(Boolean);
}

function requiredEnum(params, key, allowed) {
  const value = requiredString(params, key);
  if (!allowed.includes(value)) {
    throw new Error(`${key} must be one of: ${allowed.join(", ")}`);
  }
  return value;
}

function textOrDefault(value, defaultValue) {
  return typeof value === "string" && value.trim() ? value.trim() : defaultValue;
}

function numberOrDefault(value, defaultValue) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return defaultValue;
}

export default plugin;
