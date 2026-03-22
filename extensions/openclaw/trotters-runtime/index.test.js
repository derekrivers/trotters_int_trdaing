import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import plugin from "./index.js";

function registerTools(pluginConfig = {}) {
  const tools = new Map();
  plugin.register({
    pluginConfig,
    registerTool(tool) {
      tools.set(tool.name, tool);
    },
  });
  return Object.fromEntries(tools);
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function withEnv(overrides, callback) {
  const previous = new Map();
  for (const [key, value] of Object.entries(overrides)) {
    previous.set(key, process.env[key]);
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
  return Promise.resolve()
    .then(callback)
    .finally(() => {
      for (const [key, value] of previous.entries()) {
        if (value === undefined) {
          delete process.env[key];
        } else {
          process.env[key] = value;
        }
      }
    });
}

async function withRunbookFixture(payload, callback) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "trotters-runtime-"));
  const runbookPath = path.join(root, "trotters-runbook.json");
  const historyPath = path.join(root, "runbook-history.jsonl");
  fs.writeFileSync(runbookPath, JSON.stringify(payload, null, 2), "utf-8");
  try {
    return await callback({ runbookPath, historyPath });
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

async function runTest(name, callback) {
  try {
    await callback();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    console.error(error);
    process.exitCode = 1;
  }
}

await runTest("overview requests include auth and actor headers", async () => {
  await withEnv({ TROTTERS_API_TOKEN: "api-token" }, async () => {
    const calls = [];
    const originalFetch = global.fetch;
    global.fetch = async (url, options) => {
      calls.push({ url, options });
      return jsonResponse({
        status: {
          counts: { queued: 3, completed: 9 },
          workers: [{ worker_id: "worker-1", status: "idle" }],
        },
        active_directors: [{ director_id: "director-1", director_name: "broad-operability-director", status: "running" }],
        active_campaigns: [{ campaign_id: "campaign-1", campaign_name: "broad-operability-primary", status: "running" }],
        notifications: [
          { message: "note-1", severity: "info", recorded_at_utc: "2026-03-22T15:00:00Z" },
          { message: "note-2", severity: "warning", recorded_at_utc: "2026-03-22T15:01:00Z" },
        ],
        health: { status: "healthy" },
      });
    };

    try {
      const tools = registerTools({
        apiBase: "https://research.example.test",
        actor: "runtime-supervisor",
      });
      const result = await tools.trotters_overview.execute("call-1", { notificationsLimit: 1 });

      assert.equal(calls.length, 1);
      assert.equal(calls[0].url, "https://research.example.test/api/v1/runtime/overview");
      assert.equal(calls[0].options.headers.Authorization, "Bearer api-token");
      assert.equal(calls[0].options.headers["X-Trotters-Actor"], "runtime-supervisor");
      assert.equal(typeof calls[0].options.headers["X-Request-Id"], "string");
      assert.deepEqual(result.details.summary.health, { status: "healthy" });
      assert.deepEqual(result.details.summary.counts, { queued: 3, completed: 9 });
      assert.equal(result.details.summary.workers.count, 1);
      assert.deepEqual(result.details.summary.recent_notifications, [
        { message: "note-1", severity: "info", recorded_at_utc: "2026-03-22T15:00:00Z" },
      ]);
      assert.equal(result.details.raw, undefined);
    } finally {
      global.fetch = originalFetch;
    }
  });
});

await runTest("overview classifies a healthy active runtime as monitor only", async () => {
  await withEnv({ TROTTERS_API_TOKEN: "api-token" }, async () => {
    const originalFetch = global.fetch;
    global.fetch = async () =>
      jsonResponse({
        status: {
          counts: { queued: 2, running: 4, completed: 18 },
          workers: [{ worker_id: "worker-1", status: "running", heartbeat_at: "2026-03-22T18:25:00Z" }],
        },
        active_directors: [{ director_id: "director-1", director_name: "broad-operability-director", status: "running" }],
        active_campaigns: [{ campaign_id: "campaign-1", campaign_name: "broad-operability-primary", status: "running" }],
        notifications: [],
        health: { status: "healthy", summary: "All services green." },
      });

    try {
      const tools = registerTools({
        apiBase: "https://research.example.test",
        actor: "runtime-supervisor",
      });
      const result = await tools.trotters_overview.execute("call-healthy", {});
      const decision = result.details.summary.supervisor_decision;

      assert.equal(decision.classification, "active_healthy");
      assert.equal(decision.recommended_mode, "monitor_only");
      assert.deepEqual(decision.preferred_tools, []);
      assert.deepEqual(decision.blocked_mutations, [
        "trotters_director.start",
        "trotters_campaign.start",
        "trotters_service.restart",
      ]);
    } finally {
      global.fetch = originalFetch;
    }
  });
});

await runTest("overview classifies an active degraded runtime as service-health only", async () => {
  await withEnv({ TROTTERS_API_TOKEN: "api-token" }, async () => {
    const originalFetch = global.fetch;
    global.fetch = async () =>
      jsonResponse({
        status: {
          counts: { queued: 9, running: 1, completed: 18 },
          workers: [],
        },
        active_directors: [{ director_id: "director-1", director_name: "broad-operability-director", status: "running" }],
        active_campaigns: [{ campaign_id: "campaign-1", campaign_name: "broad-operability-primary", status: "running" }],
        notifications: [{ message: "workers missing", severity: "warning", recorded_at_utc: "2026-03-22T18:28:00Z" }],
        health: { status: "degraded", summary: "Workers missing." },
      });

    try {
      const tools = registerTools({
        apiBase: "https://research.example.test",
        actor: "runtime-supervisor",
      });
      const result = await tools.trotters_overview.execute("call-degraded", {});
      const decision = result.details.summary.supervisor_decision;

      assert.equal(decision.classification, "active_degraded");
      assert.equal(decision.recommended_mode, "service_health_only");
      assert.ok(decision.preferred_tools.includes("trotters_service.restart"));
      assert.ok(decision.preferred_tools.includes("trotters_runbook.record_escalation"));
      assert.deepEqual(decision.blocked_mutations, ["trotters_director.start", "trotters_campaign.start"]);
      assert.match(decision.incident_fingerprint, /^supervisor:/);
      assert.equal(decision.cooldown_active, false);
    } finally {
      global.fetch = originalFetch;
    }
  });
});

await runTest("overview suppresses repeated degraded runtime actions inside the incident cooldown", async () => {
  await withRunbookFixture(
    {
      work_queue: [
        {
          plan_id: "broad_operability",
          plan_file: "configs/directors/broad_operability.json",
          director_name: "broad-operability-director",
        },
      ],
    },
    async ({ runbookPath, historyPath }) => {
      const summaryRoot = path.join(path.dirname(historyPath), "agent_summaries");
      await withEnv({ TROTTERS_API_TOKEN: "api-token" }, async () => {
        const originalFetch = global.fetch;
        global.fetch = async () =>
          jsonResponse({
            status: {
              counts: { queued: 6, running: 1, completed: 18 },
              workers: [],
            },
            active_directors: [{ director_id: "director-1", director_name: "broad-operability-director", status: "running" }],
            active_campaigns: [{ campaign_id: "campaign-1", campaign_name: "broad-operability-primary", status: "running" }],
            notifications: [{ message: "workers missing", severity: "warning", recorded_at_utc: "2026-03-22T18:28:00Z" }],
            health: { status: "degraded", summary: "Workers missing." },
          });

        try {
          const tools = registerTools({
            apiBase: "https://research.example.test",
            runbookPath,
            runbookHistoryPath: historyPath,
            summaryRoot,
            actor: "runtime-supervisor",
          });
          const initial = await tools.trotters_overview.execute("call-degraded-first", {});
          const fingerprint = initial.details.summary.supervisor_decision.incident_fingerprint;
          const record = await tools.trotters_runbook.execute("call-record-escalation", {
            action: "record_escalation",
            planId: "broad_operability",
            incidentId: "incident-repeat-1",
            failureClass: "service_health",
            fingerprint,
            reason: "workers missing",
          });
          const repeated = await tools.trotters_overview.execute("call-degraded-repeat", {});
          const decision = repeated.details.summary.supervisor_decision;

          assert.equal(record.details.recorded.fingerprint, fingerprint);
          assert.equal(decision.classification, "active_degraded_cooldown");
          assert.equal(decision.recommended_mode, "service_health_cooldown");
          assert.equal(decision.cooldown_active, true);
          assert.ok(decision.cooldown_remaining_seconds > 0);
          assert.ok(decision.blocked_mutations.includes("trotters_service.restart"));
          assert.equal(decision.recent_incident.fingerprint, fingerprint);
        } finally {
          global.fetch = originalFetch;
        }
      });
    },
  );
});

await runTest("overview treats stale exhausted context as wait-or-inspect instead of advancing the runbook", async () => {
  await withEnv({ TROTTERS_API_TOKEN: "api-token" }, async () => {
    const originalFetch = global.fetch;
    global.fetch = async () =>
      jsonResponse({
        status: {
          counts: { queued: 0, running: 0, completed: 24 },
          workers: [],
        },
        active_directors: [],
        active_campaigns: [],
        notifications: [],
        most_recent_terminal: {
          campaign_id: "campaign-9",
          event_type: "campaign_finished",
          severity: "info",
          message: "campaign exhausted cleanly",
          recorded_at_utc: "2026-03-21T00:00:00Z",
        },
        health: { status: "healthy", summary: "Idle overnight." },
      });

    try {
      const tools = registerTools({
        apiBase: "https://research.example.test",
        actor: "runtime-supervisor",
      });
      const result = await tools.trotters_overview.execute("call-idle-stale", {});
      const decision = result.details.summary.supervisor_decision;

      assert.equal(decision.classification, "idle_exhausted_stale_context");
      assert.equal(decision.recommended_mode, "inspect_runbook_or_wait");
      assert.ok(decision.blocked_mutations.includes("trotters_director.start"));
    } finally {
      global.fetch = originalFetch;
    }
  });
});

await runTest("supervisor drill harness advances the runbook only after an exhausted idle runtime", async () => {
  await withRunbookFixture(
    {
      work_queue: [
        {
          plan_id: "broad_operability",
          plan_file: "configs/directors/broad_operability.json",
          director_name: "broad-operability-director",
        },
      ],
    },
    async ({ runbookPath }) => {
      await withEnv({ TROTTERS_API_TOKEN: "api-token" }, async () => {
        const originalFetch = global.fetch;
        global.fetch = async () =>
          jsonResponse({
            status: {
              counts: { queued: 0, running: 0, completed: 24 },
              workers: [],
            },
            active_directors: [],
            active_campaigns: [],
            notifications: [
              {
                campaign_id: "campaign-9",
                event_type: "campaign_finished",
                severity: "info",
                message: "campaign exhausted cleanly",
                recorded_at_utc: "2026-03-22T18:29:00Z",
              },
            ],
            most_recent_terminal: {
              campaign_id: "campaign-9",
              event_type: "campaign_finished",
              severity: "info",
              message: "campaign exhausted cleanly",
              recorded_at_utc: "2026-03-22T18:29:00Z",
            },
            health: { status: "healthy", summary: "Idle after clean completion." },
          });

        try {
          const tools = registerTools({
            apiBase: "https://research.example.test",
            runbookPath,
            actor: "runtime-supervisor",
          });
          const overview = await tools.trotters_overview.execute("call-idle-exhausted", {});
          const nextItem = await tools.trotters_runbook.execute("call-next-item", { action: "next_work_item" });

          assert.equal(overview.details.summary.supervisor_decision.classification, "idle_exhausted_ready_for_next");
          assert.equal(overview.details.summary.supervisor_decision.recommended_mode, "advance_runbook");
          assert.equal(nextItem.details.selected.plan_id, "broad_operability");
          assert.equal(nextItem.details.selected.director_name, "broad-operability-director");
        } finally {
          global.fetch = originalFetch;
        }
      });
    },
  );
});

await runTest("supervisor drill harness requires investigation before acting on failed idle runtime", async () => {
  await withEnv({ TROTTERS_API_TOKEN: "api-token" }, async () => {
    const calls = [];
    const originalFetch = global.fetch;
    global.fetch = async (url) => {
      calls.push(url);
      if (url === "https://research.example.test/api/v1/runtime/overview") {
        return jsonResponse({
          status: {
            counts: { queued: 0, running: 0, failed: 3 },
            workers: [],
          },
          active_directors: [],
          active_campaigns: [],
          notifications: [
            {
              campaign_id: "campaign-11",
              event_type: "campaign_failed",
              severity: "error",
              message: "campaign failed due to runtime error",
              recorded_at_utc: "2026-03-22T18:31:00Z",
            },
          ],
          most_recent_terminal: {
            campaign_id: "campaign-11",
            event_type: "campaign_failed",
            severity: "error",
            message: "campaign failed due to runtime error",
            recorded_at_utc: "2026-03-22T18:31:00Z",
          },
          health: { status: "degraded", summary: "Recent failed campaign." },
        });
      }
      if (url === "https://research.example.test/api/v1/jobs?status=failed") {
        return jsonResponse({
          jobs: [
            {
              job_id: "job-99",
              campaign_id: "campaign-11",
              command: "backtest",
              status: "failed",
              error_message: "disk i/o error",
              updated_at: "2026-03-22T18:31:04Z",
            },
          ],
        });
      }
      if (url === "https://research.example.test/api/v1/notifications?limit=3") {
        return jsonResponse({
          notifications: [
            {
              campaign_id: "campaign-11",
              event_type: "campaign_failed",
              severity: "error",
              message: "campaign failed due to runtime error",
              recorded_at_utc: "2026-03-22T18:31:00Z",
            },
          ],
        });
      }
      throw new Error(`Unexpected fetch url: ${url}`);
    };

    try {
      const tools = registerTools({
        apiBase: "https://research.example.test",
        actor: "runtime-supervisor",
      });
      const overview = await tools.trotters_overview.execute("call-idle-failed", {});
      const postmortem = await tools.trotters_review_pack.execute("call-postmortem", {
        action: "failure_postmortem",
        limit: 3,
      });

      assert.equal(overview.details.summary.supervisor_decision.classification, "idle_investigate_failure");
      assert.equal(overview.details.summary.supervisor_decision.recommended_mode, "investigate_before_action");
      assert.ok(overview.details.summary.supervisor_decision.preferred_tools.includes("trotters_jobs.logs"));
      assert.deepEqual(postmortem.details.failed_jobs, [
        {
          job_id: "job-99",
          campaign_id: "campaign-11",
          command: "backtest",
          status: "failed",
          error_message: "disk i/o error",
          updated_at: "2026-03-22T18:31:04Z",
        },
      ]);
      assert.equal(calls.filter((url) => url === "https://research.example.test/api/v1/runtime/overview").length, 2);
    } finally {
      global.fetch = originalFetch;
    }
  });
});

await runTest("director start resolves approved plan_id from the runbook", async () => {
  await withRunbookFixture(
    {
      work_queue: [
        {
          plan_id: "broad_operability",
          plan_file: "configs/directors/broad_operability.json",
          director_name: "broad-operability-director",
        },
      ],
    },
    async ({ runbookPath }) => {
      await withEnv({ TROTTERS_API_TOKEN: "api-token" }, async () => {
        const calls = [];
        const originalFetch = global.fetch;
        global.fetch = async (url, options) => {
          calls.push({ url, options });
          return jsonResponse({ director_id: "director-1" });
        };

        try {
          const tools = registerTools({
            apiBase: "https://research.example.test",
            runbookPath,
          });
          await tools.trotters_director.execute("call-2", {
            action: "start",
            planId: "broad_operability",
          });

          assert.equal(calls.length, 1);
          assert.equal(calls[0].url, "https://research.example.test/api/v1/directors");
          assert.equal(calls[0].options.method, "POST");
          assert.deepEqual(JSON.parse(calls[0].options.body), {
            director_name: "broad-operability-director",
            director_plan_file: "configs/directors/broad_operability.json",
            adopt_active_campaigns: true,
          });
        } finally {
          global.fetch = originalFetch;
        }
      });
    },
  );
});

await runTest("campaign start resolves approved config_id from the runbook", async () => {
  await withRunbookFixture(
    {
      config_registry: {
        broad_primary: "configs/eodhd_momentum_broad.toml",
      },
    },
    async ({ runbookPath }) => {
      await withEnv({ TROTTERS_API_TOKEN: "api-token" }, async () => {
        const calls = [];
        const originalFetch = global.fetch;
        global.fetch = async (url, options) => {
          calls.push({ url, options });
          return jsonResponse({ campaign_id: "campaign-1" });
        };

        try {
          const tools = registerTools({
            apiBase: "https://research.example.test",
            runbookPath,
          });
          await tools.trotters_campaign.execute("call-3", {
            action: "start",
            configId: "broad_primary",
            campaignName: "manual-broad-primary",
          });

          assert.equal(calls.length, 1);
          assert.equal(calls[0].url, "https://research.example.test/api/v1/campaigns");
          assert.equal(calls[0].options.method, "POST");
          assert.deepEqual(JSON.parse(calls[0].options.body), {
            config_path: "configs/eodhd_momentum_broad.toml",
            campaign_name: "manual-broad-primary",
          });
        } finally {
          global.fetch = originalFetch;
        }
      });
    },
  );
});

await runTest("service restart surfaces non-allowlisted rejection from ops-bridge", async () => {
  await withEnv({ TROTTERS_OPS_BRIDGE_TOKEN: "ops-token" }, async () => {
    const calls = [];
    const originalFetch = global.fetch;
    global.fetch = async (url, options) => {
      calls.push({ url, options });
      return jsonResponse({ error: "Service 'dashboard' is not in the allowed restart list" }, 400);
    };

    try {
      const tools = registerTools({
        opsBridgeBase: "https://ops.example.test",
        actor: "runtime-supervisor",
      });
      await assert.rejects(
        () =>
          tools.trotters_service.execute("call-4", {
            action: "restart",
            service: "dashboard",
            reason: "investigate",
            incidentId: "incident-1",
          }),
        /allowed restart list/,
      );

      assert.equal(calls.length, 1);
      assert.equal(calls[0].url, "https://ops.example.test/api/v1/services/dashboard/restart");
      assert.equal(calls[0].options.headers.Authorization, "Bearer ops-token");
      assert.equal(calls[0].options.headers["X-Trotters-Actor"], "runtime-supervisor");
      assert.deepEqual(JSON.parse(calls[0].options.body), {
        reason: "investigate",
        incident_id: "incident-1",
      });
    } finally {
      global.fetch = originalFetch;
    }
  });
});

await runTest("review pack summarizes campaign notifications for triage agents", async () => {
  await withEnv({ TROTTERS_API_TOKEN: "api-token" }, async () => {
    const calls = [];
    const originalFetch = global.fetch;
    global.fetch = async (url, options) => {
      calls.push({ url, options });
      if (url === "https://research.example.test/api/v1/campaigns/campaign-1") {
        return jsonResponse({
          campaign: {
            campaign_id: "campaign-1",
            campaign_name: "broad-operability-primary",
            status: "exhausted",
            phase: "finalized",
            director_id: "director-1",
            latest_report_path: "/tmp/reports/campaign-1/promotion_summary.md",
            finished_at: "2026-03-22T16:59:32Z",
            state: {
              final_decision: {
                recommended_action: "promote",
                selected_profile_name: "candidate-alpha",
                paper_trade_ready: true,
              },
            },
          },
        });
      }
      if (url === "https://research.example.test/api/v1/notifications?campaign_id=campaign-1&limit=2") {
        return jsonResponse({
          notifications: [
            {
              campaign_id: "campaign-1",
              event_type: "campaign_finished",
              severity: "info",
              message: "campaign exhausted cleanly",
              recorded_at_utc: "2026-03-22T16:59:32Z",
              payload_path: "runtime/notifications/campaign-1.json",
              ignored_field: "ignored",
            },
            {
              campaign_id: "campaign-1",
              event_type: "promotion_ready",
              severity: "warning",
              message: "candidate needs manual review",
              recorded_at_utc: "2026-03-22T17:00:00Z",
            },
          ],
        });
      }
      throw new Error(`Unexpected fetch url: ${url}`);
    };

    try {
      const tools = registerTools({
        apiBase: "https://research.example.test",
        actor: "research-triage",
      });
      const result = await tools.trotters_review_pack.execute("call-7", {
        action: "campaign_triage",
        campaignId: "campaign-1",
        limit: 2,
      });

      assert.equal(calls.length, 2);
      assert.equal(result.details.pack_type, "campaign_triage");
      assert.equal(result.details.status, "ok");
      assert.deepEqual(result.details.notifications, [
        {
          campaign_id: "campaign-1",
          event_type: "campaign_finished",
          severity: "info",
          message: "campaign exhausted cleanly",
          recorded_at_utc: "2026-03-22T16:59:32Z",
          payload_path: "runtime/notifications/campaign-1.json",
        },
        {
          campaign_id: "campaign-1",
          event_type: "promotion_ready",
          severity: "warning",
          message: "candidate needs manual review",
          recorded_at_utc: "2026-03-22T17:00:00Z",
        },
      ]);
      assert.equal(result.details.final_decision.recommended_action, "promote");
    } finally {
      global.fetch = originalFetch;
    }
  });
});

await runTest("summary records normalize specialist agent defaults and contract fields", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "trotters-summaries-"));
  try {
    const tools = registerTools({
      summaryRoot: root,
      actor: "openclaw-supervisor",
    });
    const result = await tools.trotters_summaries.execute("call-8", {
      action: "record",
      summaryType: "campaign_triage_summary",
      status: "exhausted",
      classification: "needs_more_research",
      message: "candidate needs more work",
      evidence: ["/runtime/catalog/example/operator_scorecard.json"],
      artifactRefs: ["operator_scorecard.json"],
      campaignId: "campaign-2",
    });

    assert.equal(result.details.record.agent_id, "research-triage");
    assert.equal(result.details.record.status, "recorded");
    assert.equal(result.details.record.classification, "needs_followup");
    assert.equal(result.details.record.recommended_action, "continue_research");
    assert.deepEqual(result.details.record.artifact_refs, ["/runtime/catalog/example/operator_scorecard.json"]);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

await runTest("summary records tolerate missing status and classification for specialist defaults", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "trotters-summaries-defaults-"));
  try {
    const tools = registerTools({
      summaryRoot: root,
      actor: "openclaw-supervisor",
    });
    const result = await tools.trotters_summaries.execute("call-9", {
      action: "record",
      summaryType: "failure_postmortem_summary",
      message: "runtime issue captured",
      evidence: ["worker heartbeats missing"],
    });

    assert.equal(result.details.record.status, "recorded");
    assert.equal(result.details.record.classification, "unknown");
    assert.equal(result.details.record.recommended_action, "manual_investigation");
    assert.equal(result.details.record.agent_id, "failure-postmortem");
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

await runTest("runbook history records recoveries and escalations", async () => {
  await withRunbookFixture(
    {
      work_queue: [
        {
          plan_id: "broad_operability",
          plan_file: "configs/directors/broad_operability.json",
          director_name: "broad-operability-director",
        },
      ],
    },
    async ({ runbookPath, historyPath }) => {
      const summaryRoot = path.join(path.dirname(historyPath), "agent_summaries");
      const tools = registerTools({
        runbookPath,
        runbookHistoryPath: historyPath,
        summaryRoot,
      });

      await tools.trotters_runbook.execute("call-5", {
        action: "record_recovery",
        planId: "broad_operability",
        incidentId: "incident-1",
        failureClass: "service_health",
        reason: "worker restart",
      });
      const result = await tools.trotters_runbook.execute("call-6", {
        action: "record_escalation",
        planId: "broad_operability",
        incidentId: "incident-2",
        failureClass: "campaign_failure",
        reason: "manual investigation required",
      });

      const historyLines = fs.readFileSync(historyPath, "utf-8").trim().split("\n");
      assert.equal(historyLines.length, 2);
      assert.equal(result.details.history[0].incident_id, "incident-2");
      assert.equal(result.details.history[0].event_type, "record_escalation");
      assert.equal(result.details.history[1].incident_id, "incident-1");
      assert.equal(result.details.history[1].event_type, "record_recovery");
    },
  );
});

if (process.exitCode && process.exitCode !== 0) {
  process.exit(process.exitCode);
}



