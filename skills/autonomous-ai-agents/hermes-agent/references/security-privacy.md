# Security & Privacy Toggles

For repeated command or script prompts, start with [read-only approval diagnosis](#diagnose-repeated-prompts-before-changing-anything). Observe the active profile before proposing any change. Other security/privacy controls below have their own restart requirements; approval config is read through the live config cache.

### Secret redaction in tool output

Secret redaction is **on by default** — tool output (terminal stdout, `read_file`, web content, subagent summaries, etc.) is scanned for strings that look like API keys, tokens, and secrets before it enters the conversation context and logs. Leave it enabled for normal use:

```bash
hermes config set security.redact_secrets true       # keep enabled globally
```

**Restart required.** `security.redact_secrets` is snapshotted at import time — toggling it mid-session (e.g. via `export HERMES_REDACT_SECRETS=false` from a tool call) will NOT take effect for the running process. Tell the user to change it in config from a terminal, then start a new session. This is deliberate — it prevents an LLM from flipping the toggle on itself mid-task.

Disable only when you deliberately need raw credential-like strings for debugging or redactor development:
```bash
hermes config set security.redact_secrets false
```

### PII redaction in gateway messages

Separate from secret redaction. When enabled, the gateway hashes user IDs and strips phone numbers from the session context before it reaches the model:

```bash
hermes config set privacy.redact_pii true    # enable
hermes config set privacy.redact_pii false   # disable (default)
```

### Command approval prompts

#### Diagnose repeated prompts before changing anything

Start with the **active profile's configured mode and effective Hermes home**, not
an assumption that manual mode is enabled. This is read-only diagnosis, not a
request to disable security or a claim of an approval-runtime bug.

1. **Identify the affected session and home.** Record its surface (CLI, desktop,
   messaging, or unattended job) and selected profile. In the affected tool
   environment, use `terminal` to inspect only the home variable, not the entire
   environment:
   ```python
   terminal(command="python -c \"import os; print('HERMES_HOME=' + os.environ.get('HERMES_HOME', '<unset>'))\"")
   ```
   This observes the child process environment, not the backend's contextvars.
   `get_hermes_home()` resolves a context-local home override first, then
   `HERMES_HOME`, then the platform default. A routed gateway turn can therefore
   use a different home from its process environment. An unset value is not proof
   that the affected session uses the default profile. Do not substitute another
   terminal's sticky profile or hardcode `~/.hermes`.
2. **Read the selected profile's mode.** Replace `PROFILE` with the confirmed
   profile name (including `default` when that is the actual target):
   ```python
   terminal(command="hermes --profile PROFILE config get approvals.mode")
   ```
   The CLI resolves the explicit profile before loading config. Confirm that it
   targets the same home/backend as the reported prompt; a local CLI does not
   inspect a remote desktop backend. This reads configuration, not the running
   turn's complete effective policy. If the result is `false`, YAML may have
   parsed bare `off` as a boolean: the approval normalizer treats `False` as `off`.
   Unknown/invalid modes fall back to `manual`; do not silently rewrite them.
3. **Classify the actual prompt.** Capture the tool name, sanitized prompt text,
   session identifier, and timing. Ordinary terminal approval covers flagged
   commands; `execute_code` has a whole-script gate in gateway/ask contexts.
   “Allow this hook to run?” is separate shell-hook registration consent, not
   ordinary script execution approval. For that branch, use
   `terminal(command="hermes --profile PROFILE hooks list")` to inspect configured
   hooks and allowlist status without executing them. Its output can include
   commands and webhook URLs: inspect privately and redact before sharing. Do not
   run `hooks test`, accept hooks, or clear allowlists as a diagnostic probe.
4. **Reconcile policy and transport.** Both shell and execute-code guards consult
   the effective approval mode before prompting. The desktop/TUI backend's
   `HERMES_EXEC_ASK=1` routes approval requests through gateway callbacks; it does
   **not** force a prompt when the effective mode is `off`. Check the affected
   turn's routed profile and any hosted-room execution policy (which overrides
   the configured approval mode). Separately account for launch-time `--yolo` /
   `HERMES_YOLO_MODE` and session-scoped YOLO state; a new config query cannot
   reveal those. Do not toggle `/yolo` to inspect it. For cron, one-shot `-q`, or
   unattended API/webhook work, inspect the matching `approvals.cron_mode`,
   `approvals.single_query_mode`, or `approvals.unattended_mode` with the same
   profile-qualified `config get`; each defaults to `deny`. These context policies
   apply after the ordinary guard's YOLO/`off` early return, not as forced prompts.
5. **Report observation, not mutation.** Say “The selected profile reports mode
   `off`; no setting was changed,” only when that is what the query returned.
   Do not say “I disabled prompts.” If ordinary approval still appears with
   effective `off`, preserve a sanitized reproduction and source/version details;
   label unresolved context/transport differences as unknown. Do not promise all
   dialogs will disappear, repeat generic assurances, or lower security to hide
   the symptom.

#### What the modes control

- `smart` — the normal config default; auxiliary risk assessment can approve a
  low-risk flagged command once, deny high-risk commands, or escalate uncertainty.
- `manual` — prompt for flagged actions requiring approval, not every command.
- `off` — bypass the ordinary command/code approval layer, like YOLO; **not** all
  security checks or all consent dialogs.

Shell-hook consent uses its own allowlist and opt-ins (`--accept-hooks`,
`HERMES_ACCEPT_HOOKS`, `hooks_auto_accept`), independent of `approvals.mode`.
Hardline command blocks and user-defined `approvals.deny` rules remain enforced;
secret redaction is independent too. Do not change any of these during diagnosis.

Source anchors for checking a different installed version: `hermes_constants.py`
(`get_hermes_home`), `hermes_cli/main.py` (`_apply_profile_override`),
`hermes_cli/config_defaults.py` (`approvals`), `tools/approval_context.py`
(`_get_approval_mode`, `_normalize_approval_mode`), `tools/approval.py`
(`check_all_command_guards`, `check_execute_code_guard`, `_yolo_active`),
`tui_gateway/server.py` (`_enable_gateway_prompts`), and `agent/shell_hooks.py`
(`allowlist_path`, `_prompt_and_record`, `_resolve_effective_accept`).

### "Reset permissions" / "make Hermes ask again"

First complete the diagnosis above and clarify whether the user means ordinary
action approval, shell-hook consent, or a separate file-write/confirmation guard.
Resetting stored consent is a state change, not a troubleshooting prerequisite.

Only on an explicit reset request, identify the intended store: `command_allowlist`
in the affected profile config holds permanent ordinary approvals;
`shell-hooks-allowlist.json` under its effective Hermes home holds shell-hook
consent. Do not clear both indiscriminately or delete a default-profile file while
working in a named profile. Session approvals and YOLO state are separate again.

### Shell hooks allowlist

Shell-hook registration requires consent for an unseen event/command pair unless
an explicit hook-accept opt-in applies. Consent is stored in
`get_hermes_home() / "shell-hooks-allowlist.json"`, not necessarily the default
profile. A non-TTY registration without consent skips the hook; ordinary approval
mode `off` does not grant hook consent.

### Disabling the web/browser/image-gen tools

To keep the model away from network or media tools entirely, open `hermes tools` and toggle per-platform. Takes effect on next session (`/reset`). See `references/configuration.md` for the toolset list.

