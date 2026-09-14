# Passive Desktop profile-activation diagnosis

## When to use

Use for Desktop “Waking up…” followed by a failed profile open/switch, especially
with concurrent sessions. Separate **local backend activation**, **backend
readiness/connection**, and **provider inference**. A cloud-model profile still
needs a local Hermes backend when its Desktop route is local. Remote/cloud
connection descriptors have no local child and do not consume these slots.

## Prerequisites and safety boundary

Establish diagnosis-only scope before collecting evidence. Use `read_file` and
`search_files` on authorized source files and bounded existing log excerpts;
use `terminal` only for passive metadata or offline calculations. Do not import
Desktop/runtime modules merely to inspect them. Do not switch profiles, open a
new chat, refresh providers, run doctor/setup/inference/health probes, change
settings, load/unload models, reset sessions, reload windows, or restart/kill
processes. Those are separately authorized maintenance actions, not diagnosis.

Do not dump `.env`, auth stores, full configs, process environments, connection
URLs with credentials, or raw logs. Retain only needed lifecycle fields and
redacted excerpts. Even a provider base URL or a process command line can contain
secrets. Replace private profile names, endpoints, paths, and session identifiers
with stable aliases in shared reports.

## Procedure

1. **Resolve the affected surface and route.** From existing launcher/build
   records and narrowly selected process metadata, identify the Desktop build,
   backend checkout, primary app home, and affected profile homes. Do not assume
   the investigating agent's `HERMES_HOME` is Electron's home. Desktop writes
   `logs/desktop.log` under its resolved app `HERMES_HOME`; Python logs belong to
   the corresponding backend/profile home. Identify local versus remote routing
   before applying local pool accounting. Record unknowns rather than guessing.

2. **Bound and normalize the timeline.** Select the incident's launch/time range
   (including relevant rotated logs if authorized), then search for profile
   aliases and the lifecycle markers below. Electron's outer timestamp is
   ISO-8601 UTC (`Z`); Python `%(asctime)s` has no offset and normally uses the
   logging process's local timezone. Verify that process's timezone at the event,
   not the investigator's current timezone. Preserve original stamps and convert
   to UTC programmatically. For a daylight-saving fold or unknown zone/offset,
   report ambiguity; do not silently assign UTC. An outer Electron timestamp on
   captured Python output is receipt time, not necessarily its inner event time.
   Keep bounded evidence with file/line references and explicit timezone basis.

   Offline synthetic example, via `terminal` (reads no logs or runtime state):

   ```python
   terminal(command="python3 -c 'from datetime import datetime, timezone; electron = datetime.fromisoformat(\"2026-01-15T15:00:30+00:00\"); python_log = datetime.fromisoformat(\"2026-01-15T10:00:00-05:00\"); print(python_log.astimezone(timezone.utc).isoformat()); print((electron - python_log).total_seconds())'")
   ```

   Expected: `2026-01-15T15:00:00+00:00`, then `30.0`. The explicit `-05:00`
   is a **fixture assumption**, not an offset to apply to real Python logs.

3. **Classify the earliest failed stage.** Read the sequence, not just errors:

   | Existing marker | What it establishes |
   |---|---|
   | `waiting for a free local slot (N/M busy, Q queued)` | A local start queued behind the coordinator policy; snapshot counts, not model load or active inference counts. |
   | `Local backend start for "…" timed out while waiting for a free slot.` | This attempt never acquired a slot, so its profile backend was not spawned; provider/network timeout changes cannot fix this wait. |
   | `slot wait timed out (background); will retry on the next hydration` or timeout suffix `(background)` | Background hydration exhausted its wait; current builds log it as routine rather than a foreground startup failure. |
   | `Starting Hermes backend for profile` / `failed to start` / `exited` | Start/exit evidence to correlate with queue ownership. A generic startup error alone does not establish saturation. |
   | `Evicting idle profile backend` / `Reaping idle profile backend` | Teardown selected; check subsequent child exit before inferring slot release. |
   | `HERMES_BACKEND_READY` | The child announced its port. Later HTTP/WebSocket readiness or auth can still fail; this is not an inference success. |

   Deduplicate renderer-console/IPC echoes of the same rejection; count distinct
   attempts separately. Pair queue, timeout, eviction/reaping, child exit, and
   subsequent starts/readiness by profile/connection and launch. A later readiness
   marker for that profile supports later progress, not success of the timed-out
   attempt, proof of present health, or proof that no intermittent leak exists.

4. **Explain occupancy using the matching build's policy.** Inspect the source
   map below as text and record the winning preference source from existing
   `[pool-limits]` logs. Defaults are not a measurement of the affected device.

   - Current source defaults: **3 starting/running non-primary local profile
     backends**, not three conversations, provider requests, or loaded LLMs.
     Primary backend and process-less remote descriptors are excluded.
   - With a cap of at least two, background grants are limited to `cap - 1`,
     reserving capacity for foreground requests. At the default cap, **2/3 busy**
     with two background grants can legitimately queue another background start;
     the count alone does not prove their priorities or a slot leak. **3/3 busy**
     can also block a foreground open. Foreground waiters take priority, and a
     queued background request can be promoted by user-open intent.
   - The source slot wait is **30 seconds**, below the renderer's **45-second**
     backend boot budget. Neither is the provider inference timeout.
   - Slots remain held through starting/running and are released on child exit
     or failed-start cleanup. A queued request is not another running child.
     Keepalive-fresh entries are spared LRU eviction; the default freshness
     window is four minutes and the idle reaper uses ten minutes, checked every
     minute. Continued touches can prevent idleness. Occupancy/freshness does
     not prove that each profile was generating. Do not shorten safety windows
     or kill children to test a suspected leak during active work.
   - Saturation consistent with policy is the strongest conclusion when supported
     by the timeline. A leak needs additional evidence of retained ownership
     after exit/cleanup, not simply waiting, absent log lines, or a large pool Map.
     Missing/rotated evidence leaves this unresolved.

5. **Separate historical inference failures.** Only after classifying activation,
   inspect authorized allowlisted fields such as `model.provider`, `model.default`,
   `model.api_mode`, and relevant context settings, redacting endpoints if needed.
   Earlier cloud quota exhaustion or insufficient local-model context describes
   that earlier inference attempt; it does not explain a later pre-spawn slot
   timeout. A saved correction does not establish adoption by an already-running
   model/session. State the event time and stage for each finding.

6. **Report without claiming a fix.** Give the evidenced failure stage, normalized
   timeline, occupancy and priority evidence, source/version and effective-limit
   basis, later progress, unresolved alternatives, and actions deliberately not
   performed. Historical readiness is not current provider health. Stop here in
   diagnosis-only mode.

## Maintenance option — only after separate authorization

**Settings → Advanced → Warm Bot Backends** controls `maxBackends` for this
Desktop device, not a profile `config.yaml` key, even when Advanced also shows an
“Applies to” profile selector. The main process stores it in `pool-limits.json`
under Electron `userData`; do not hand-edit it or put the setting in `.env`.

A readable saved preference takes precedence over legacy
`HERMES_DESKTOP_POOL_MAX` / `HERMES_DESKTOP_POOL_IDLE_MS` startup fallbacks.
Malformed saved JSON parses to defaults; it does not automatically select the
environment overrides. Use the logged winning source rather than assuming a
shell environment controls the GUI. The current count is clamped to 1–64.

Changes apply **live** through the coordinator; raising the count can release
queued starts without restarting Hermes, but consumes additional memory and is
still a runtime change. Lowering it does not revoke granted slots; safe LRU/exit
convergence may leave occupancy temporarily above the new limit. A persisted
file alone is not proof of the in-memory value (persistence can fail).

Plan capacity sizing or wait for genuinely unused backends to exit rather than
interrupting sessions. If a change is authorized, read back the exact applied
preference, then verify profile activation without terminating active sessions.
Exercise provider inference separately only when authorized. Do not declare a
fix based solely on a saved setting or readiness sentinel.

## Regression checklist (offline evidence review; no live reproduction)

- [ ] Saturated foreground: `3/3 busy` then slot timeout is classified before
  spawn/inference; duplicate IPC reports do not inflate attempt counts.
- [ ] Reserved foreground capacity: `2/3 busy` with two background grants and a
  background wait is expected policy, not automatically a leaked slot.
- [ ] Recovery timeline: eviction is distinguished from confirmed exit, and later
  readiness belongs to a later attempt; port readiness is not provider health.
- [ ] Historical inference: quota/context errors stay attached to their earlier
  timestamps and are not offered as causes of the later activation timeout.
- [ ] Timestamp comparison: UTC and verified local offsets normalize correctly;
  unknown timezone/DST ambiguity remains explicit.
- [ ] No settings changes, probes, model reloads, session resets, or restarts were
  performed; current health and untested maintenance outcomes remain unverified.

## Source map and official documentation

Paths below are repository-relative; verify the affected build rather than
copying these defaults into a diagnosis of a different version.

- `apps/desktop/electron/pool-spawn-coordinator.ts` — slot ownership, foreground
  reservation, timeout message, priority promotion, live `setLimit`.
- `apps/desktop/electron/pool-limits.ts` — defaults, clamps, saved JSON parsing.
- `apps/desktop/electron/main.ts` — `DESKTOP_LOG_PATH`, `readPersistedPoolLimits`,
  `POOL_SLOT_WAIT_MS`, `setPoolLimits`, `logPoolSpawnFailure`, local spawn path,
  `evictLruPoolBackends`, `startPoolIdleReaper`, exit and readiness handling.
- `apps/desktop/electron/pool-eviction.ts` — spawned-only LRU accounting and
  awaited child teardown; `apps/desktop/src/lib/with-timeout.ts` — boot budget.
- `apps/desktop/src/app/settings/pool-limits-setting.tsx` and
  `apps/desktop/src/i18n/en.ts` — live device-local UI and exact English label.
- `apps/desktop/electron/desktop-log-line.ts`, `hermes_logging.py`, and
  `agent/redact.py` — timestamp formatting and log redaction boundaries.
- [Official Desktop guide](https://hermes-agent.nousresearch.com/docs/user-guide/desktop)
  — local/remote connections, settings scope, and failing layers.
- [Official documentation index](https://hermes-agent.nousresearch.com/docs/llms.txt)
  — discover the current feature documentation.
- [General troubleshooting](troubleshooting.md) — recovery workflows, subject to
  the diagnosis-only boundary above.
