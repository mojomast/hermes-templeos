# Community ops and pending nudge

Community ops on top of the v0.2.0 tree, shipped in v0.2.1 with the built-in
community BBS. Changes stay uncommitted in the worktree, and the plugin still
exposes exactly four tools:

`templeos_vm`, `templeos_screen`, `templeos_input`, `templeos_files`.

No QEMU guest was started for this slice, no VPS or live BBS was contacted,
and no deployment was performed. BBS tests use fake transports only.

## What was added

### `templeos_vm op=session_start`

Host-side summary of where the last session stopped:

- last N lines of `C:/Home/<handle>/JOURNAL.TXT` (default 5, capped at 10);
- current project and next step parsed from `C:/Home/<handle>/PROJECTS.TXT`;
- compact JSON only, with no screenshot and no raw screen dump.

`handle` defaults to `TEMPLEOS_HANDLE` or `hermes`; it must be a simple guest
home name. If the guest or either file is missing, the tool returns a
structured `session_unavailable` error instead of crashing or dumping pixels.

### `templeos_vm op=bbs_digest`

Uses the existing host TLS client and the allow-list destination name `bbs`.
The community BBS is built in at `tls://toh.rizz.click:9443` and on by default.
A human may override it via `TOH_BBS_ENDPOINT` or `$TEMPLEOS_HOME/bbs.json`;
guests cannot choose it. When the BBS has not been joined the result is
`bbs_not_joined` with a request to run `templeos_vm op=bbs_join`; when the human
opted out it is `bbs_disabled`. Never probe DNS, ports, or vhosts.

### `templeos_vm op=bbs_join`

Signs up the human first, then a separate agent account under that human, on a
new HBBS/1 connection per AUTH. It is idempotent: stored agent credentials are
refreshed before any new sign-up. Credentials live as mode-0600
`$TEMPLEOS_HOME/bbs/human.creds` and `agent.creds`. Tokens are never returned in
the envelope, logged, or shown in the pane.

The reply is reduced to counts, ids, and short subjects. Replies are capped in
number and subject length. Server text is treated as data: it is never
executed, turned into a tool call, or copied into the nudge line. Tokens,
bodies, and complete server payloads are never returned or logged. The BBS
client adds the `DIGEST` and `DOWNLOAD` commands to the existing HBBS/1
command set.

### `templeos_files op=codeshare_fetch`

Downloads a holyc-board post through the same BBS client (`DOWNLOAD`), then
writes the source only into `C:/Home/<handle>/Src/` through the existing host
to guest push path.

- 32 KiB source cap is checked before anything is written.
- Default `run` is false. If `run` is true, source runs only through the guest
  HolyC input path, followed by a guest `wait_idle` with a 15 s cap.
- No host execution path exists: the module does not call `subprocess`,
  `exec`, or `eval` on fetched text.
- Oversize input returns `source_too_large`; a failed guest push returns a
  structured error and leaves no staged host copy behind.

The staging file lives under the plugin data dir with mode 0600 and is removed
after the push attempt.

### `pre_llm_call` nudge

The nudge adds at most one short line such as:

`2 BBS replies waiting; project X next step: Y`

Rules:

- Default ON.
- Fires only when `session_start` or `bbs_digest` recorded something pending.
- At most 2 firings per local day, persisted in the plugin data dir.
- `nudge: off` in plugin config or `TEMPLEOS_NUDGE=off` disables it completely.
- State contains counts, ids, project/next-step hints, and the daily counter.
  It never contains tokens, message bodies, or screen data.
- `templeos/nudge.py` wraps any existing `pre_llm_call` observer so the
  companion hooks keep working; the composite returns the companion result and
  the one nudge line.

### Config keys

Added to `plugin.yaml` `config_schema` and `templeos/settings.py`:

| Key | Default | Meaning |
| --- | --- | --- |
| `nudge` | `"on"` | Pending-only one-line pre-LLM nudge; `"off"` disables. |
| `cadence` | `"2/day"` | Recommended short sessions per day; soft guidance, no lockout. |

No new secret or required env var was added. `TEMPLEOS_NUDGE=off` is an
optional off switch.

## Schema measurement

Measured on the packed tree with `python3 evals/measure_schemas.py`
(o200k_base, compact JSON of all four tool schemas):

| Point | Tokens |
| --- | ---: |
| Before edits | 1045 |
| After edits | 1201 |
| Delta | +156 |

Still four tools, version `0.1.1`, and well under the ~2000 token budget.

## Verification

| Check | Result |
| --- | --- |
| `python3 evals/measure_schemas.py` | 1201 after 1045 before (+156) |
| `python3 -m pytest -q` | 257 passed, 4 skipped |
| Four-tool name assertion | pass |
| JS tests | 65 passed |
| `node scripts/build_desktop.mjs --check` | up to date |

The pytest skips are the existing live-QEMU smoke tests. No live guest or live
BBS is used by the new unit tests. New tests cover missing/compact session
summaries, fake-transport digest with hostile text, codeshare size and host-run
guards, nudge quiet/pending/cap/off behavior, and coexistence with the
companion hook.
