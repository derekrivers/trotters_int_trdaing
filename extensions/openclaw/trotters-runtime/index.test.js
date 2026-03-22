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



