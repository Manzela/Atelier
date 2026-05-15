# Logging Convention

All Atelier services emit structured JSON logs to stdout. The OTel collector ships them to Cloud Logging (production) or local files (development).

OTel GenAI semantic conventions (`gen_ai.*` spans + events) are auto-extracted by Cloud Trace.

## Format

Every log line is a single JSON object:

```json
{
  "ts": "2026-05-15T18:32:11.234Z",
  "level": "info",
  "service": "atelier-agent",
  "phase": "1",
  "env": "staging",
  "tenant_id": "tnt_abc123",
  "user_id": "usr_def456",
  "project_id": "prj_ghi789",
  "session_id": "ses_jkl012",
  "campaign_id": "cmp_mno345",
  "surface_id": "srf_pqr678",
  "trace_id": "...",
  "span_id": "...",
  "event": "node.complete",
  "node": "n3a_generator",
  "iteration": 2,
  "candidate_id": "cnd_stu901",
  "duration_ms": 1247.3,
  "success": true,
  "msg": "Generator produced 6 candidates"
}
```

## Required fields

- `ts` — RFC 3339 UTC
- `level` — `debug` | `info` | `warning` | `error` | `critical`
- `service` — service name matching OTel `service.name` resource attribute
- `event` — short snake_case event name (corresponds to OTel span name when applicable)
- `msg` — human-readable summary

## Optional fields by event class

- `tenant_id`, `user_id`, `project_id`, `session_id` — for any agent-loop event
- `campaign_id`, `surface_id` — for campaign-level events
- `node`, `iteration`, `candidate_id` — for DAG node events
- `axis`, `score`, `confidence_interval` — for axis-scoped events
- `cost_usd`, `tokens_in`, `tokens_out`, `model_id` — for `model.call` events
- `trace_id`, `span_id` — automatically injected by OTel context
- `error.type`, `error.message`, `error.stack` — when `level=error|critical`
- `decision`, `gate_axis`, `judge_axis` — for gate / judge events

## Severity levels

| Level | When to use | Routes to |
|---|---|---|
| `debug` | Verbose internals; off by default in prod | Local files only |
| `info` | Normal operational events (turn started, tool dispatched, candidate generated) | Local + Cloud Logging |
| `warning` | Degraded behavior, retries, fallbacks (per fail-soft trichotomy) | Local + Cloud Logging |
| `error` | Operation failed but service is still up | Local + Cloud Logging + alert if rate exceeds threshold |
| `critical` | Service is down or security boundary crossed (per fail-loud trichotomy) | Local + Cloud Logging + immediate Telegram alert |

## What to NEVER log

- **Plaintext secrets** — use the scrubber even on log strings; pre-commit `detect-secrets` catches violations in source
- **Full conversation contents** — log session_id + turn_id; the persisted BigQuery trajectory has the content
- **User PII** without explicit need (and never in `info` level)
- **Full DOM of generated UI** — log artifact_id; the artifact is in GCS

## What to ALWAYS log

- Every node entry + completion (with `success` + `duration_ms`)
- Every model call with token + cost telemetry (`gen_ai.usage.*`)
- Every approval-gate decision (allow/deny/timeout)
- Every scrubber hit (separate log file `secret-leak-attempts.log` for audit)
- Every restart, panic, snapshot, recovery event
- Every Phase 3+ trajectory shipment outcome
- Every Phase 4 RL preflight, approval, run lifecycle event
- Every cost-budget threshold crossing
- Every calibration drift alert

## Local dev rotation

Per `limits.yaml § local_logs_dev`:
- `rotate_size_mb: 100`
- `keep_files: 5`

Logs at `logs/` are gitignored.

## Production retention

Per `limits.yaml § log_retention`:
- Cloud Logging hot: 30 days
- GCS coldline after 30 days: another 11 months
- Hard delete after 365 days
- Trace head-sample 100% (low volume); tail-sample on errors and slow-p99

## OTel GenAI span attributes (canonical)

Every span carries:

- `gen_ai.system` = `"atelier"`
- `gen_ai.operation.name` = `generate_candidate` | `judge_axis` | `gate_check` | `mutator_apply` | `consensus_vote` | `final_render` | `pip_question` | `coherence_check`
- `gen_ai.request.model` = e.g., `gemini-3-1-pro`, `atelier-judge-brand-v3-loraN`
- `gen_ai.usage.input_tokens` / `output_tokens` / `cost_usd`

Plus Atelier-specific:

- `atelier.tenant_id`, `atelier.project_id`, `atelier.session_id`, `atelier.campaign_id`, `atelier.surface_id`
- `atelier.node`, `atelier.iteration`, `atelier.candidate_id`
- `atelier.axis` (for axis-scoped spans)
- `atelier.decision`, `atelier.score`, `atelier.confidence_interval`

These exact attributes power Cloud Trace + Cloud Monitoring + Atelier Dashboard + the public `calibration.atelier.dev` dashboard.
