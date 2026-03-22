#!/bin/sh
set -eu
umask 022

OPENCLAW_HOME="${HOME:-/home/node}"
STATE_ROOT="${OPENCLAW_HOME}/.openclaw"
CONFIG_TARGET="${STATE_ROOT}/openclaw.json"
CRON_JOB_NAME="trotters-runtime-supervisor"
SUPERVISOR_AGENT_ID="runtime-supervisor"
SOURCE_AUTH_AGENT_ID="${OPENCLAW_SUPERVISOR_AUTH_SOURCE_AGENT:-dev}"
TARGET_AUTH_DIR="${STATE_ROOT}/agents/${SUPERVISOR_AGENT_ID}/agent"
TARGET_AUTH_FILE="${TARGET_AUTH_DIR}/auth-profiles.json"
SOURCE_AUTH_FILE="${STATE_ROOT}/agents/${SOURCE_AUTH_AGENT_ID}/agent/auth-profiles.json"
SUPERVISOR_SESSIONS_FILE="${STATE_ROOT}/agents/${SUPERVISOR_AGENT_ID}/sessions/sessions.json"
INSTALLED_PLUGIN_DIR="${STATE_ROOT}/extensions/trotters-runtime"
PLUGIN_STAGE_ROOT="$(mktemp -d /tmp/trotters-runtime-plugin.XXXXXX)"
PLUGIN_STAGE_DIR="${PLUGIN_STAGE_ROOT}/trotters-runtime"

mkdir -p "${STATE_ROOT}" "${STATE_ROOT}/trotters" "${TARGET_AUTH_DIR}"
cp /opt/openclaw-config/openclaw.json "${CONFIG_TARGET}"

# The supervisor runs in isolated cron sessions, so stale session metadata only
# pins old providers/models and should not survive gateway restarts.
rm -f "${SUPERVISOR_SESSIONS_FILE}"

if [ ! -f "${TARGET_AUTH_FILE}" ] && [ -f "${SOURCE_AUTH_FILE}" ]; then
  cp "${SOURCE_AUTH_FILE}" "${TARGET_AUTH_FILE}"
fi

if [ ! -f "${TARGET_AUTH_FILE}" ] && [ -z "${ANTHROPIC_API_KEY:-}${OPENAI_API_KEY:-}${OPENROUTER_API_KEY:-}${GOOGLE_API_KEY:-}${XAI_API_KEY:-}${XIAOMI_API_KEY:-}" ]; then
  echo "OpenClaw runtime-supervisor has no model auth configured. Set a provider API key env var or add auth-profiles.json for the runtime-supervisor agent." >&2
fi

cp -R /opt/openclaw-extensions/trotters-runtime "${PLUGIN_STAGE_DIR}"
chmod -R u=rwX,go=rX "${PLUGIN_STAGE_DIR}"
find "${PLUGIN_STAGE_DIR}" -type d -exec chmod 755 {} \;
find "${PLUGIN_STAGE_DIR}" -type f -exec chmod 644 {} \;
rm -f "${PLUGIN_STAGE_DIR}/index.test.js"
mkdir -p "${STATE_ROOT}/extensions"
chmod 755 "${STATE_ROOT}/extensions"
rm -rf "${INSTALLED_PLUGIN_DIR}"
openclaw plugins install "${PLUGIN_STAGE_DIR}" >/dev/null
chmod -R u=rwX,go=rX "${INSTALLED_PLUGIN_DIR}"
find "${INSTALLED_PLUGIN_DIR}" -type d -exec chmod 755 {} \;
find "${INSTALLED_PLUGIN_DIR}" -type f -exec chmod 644 {} \;
rm -rf "${PLUGIN_STAGE_ROOT}"

node dist/index.js gateway --bind "${OPENCLAW_GATEWAY_BIND}" --port "${OPENCLAW_GATEWAY_PORT}" --allow-unconfigured --dev &
GATEWAY_PID=$!

ATTEMPTS=0
until openclaw cron list --json >/tmp/openclaw-cron-list.json 2>/dev/null; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if ! kill -0 "${GATEWAY_PID}" 2>/dev/null; then
    wait "${GATEWAY_PID}"
    exit 1
  fi
  if [ "${ATTEMPTS}" -ge 30 ]; then
    echo "OpenClaw gateway did not become ready for cron bootstrap" >&2
    wait "${GATEWAY_PID}"
    exit 1
  fi
  sleep 1
done

EXISTING_IDS=$( 
  node -e '
const fs = require("node:fs");
const parsed = JSON.parse(fs.readFileSync(process.argv[1], "utf-8"));
const entries = Array.isArray(parsed) ? parsed : Array.isArray(parsed.jobs) ? parsed.jobs : [];
const targetName = process.argv[2];
for (const entry of entries) {
  if (entry && entry.name === targetName && typeof entry.id === "string" && entry.id) {
    console.log(entry.id);
  }
}
' /tmp/openclaw-cron-list.json "${CRON_JOB_NAME}"
)

for job_id in ${EXISTING_IDS}; do
  openclaw cron remove "${job_id}" >/dev/null 2>&1 || true
done

SUPERVISOR_MESSAGE="$(tr '\n' ' ' < /opt/openclaw-bootstrap/runtime-supervisor-message.txt)"

openclaw cron add \
  --name "${CRON_JOB_NAME}" \
  --description "Autonomous Trotters runtime supervisor loop" \
  --agent runtime-supervisor \
  --every 2m \
  --session isolated \
  --no-deliver \
  --light-context \
  --thinking low \
  --timeout-seconds 120 \
  --message "${SUPERVISOR_MESSAGE}" \
  >/dev/null

wait "${GATEWAY_PID}"
