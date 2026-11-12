# BBS transport bridge

Slice: `feat/bbs-transport` (workspace branch shown as `master` in this
checkout; changes stay uncommitted). Delivered files:

- `templeos/bbs.py`
- `tests/test_bbs_transport.py`
- `docs/evidence/BBS-TRANSPORT.md`

No VPS was contacted, no deployment was performed, and no QEMU image or ISO is
needed for these tests.

## Contract source

The wire contract was read from the Temple of Hermes repository branch
`hermes/bbs-contracts` (repository `mojomast/temple-of-hermes`):

- `docs/bbs/HBBS-1.md` - HBBS/1 draft contract, version 1
- `docs/bbs/schema/hbbs-1.schema.json` - request/response body schema
- `docs/bbs/schema/limits.json` - role limits
- `docs/bbs/schema/boards.json` - v1 board catalogue
- `docs/bbs/fixtures/**` - raw request/response frames, including injection
  fixtures

The implementation follows the contract's destination, frame, auth, command,
board, error, and prompt-injection rules. The real deployment endpoint is not
part of this change and is not present in code or documentation.

## Security invariants

1. **Allow-list only.** The only destination name accepted by the bridge is the
   literal `bbs`. `templeos.bbs.resolve_destination()` rejects every other
   value, including `hermes`, URLs, `host:port` strings, and empty input.
2. **Built-in community endpoint, human overrides only.** `load_config()`
   compiles in the public Temple of Hermes BBS at
   `tls://toh.rizz.click:9443`. A human may override it with
   `TOH_BBS_ENDPOINT` or `$TEMPLEOS_HOME/bbs.json`; a guest has no path to
   either. There is no discovery or probing fallback.
3. **Guest cannot supply host:port.** The public entry points take only a
   destination name:
   - `BbsClient(destination="bbs")`
   - `open_destination("bbs")`
   There is no `host`, `port`, `endpoint`, or URL parameter. HBBS/1 argument
   validation also rejects transport-shaped keys (`host`, `hostname`, `port`,
   `endpoint`, `url`, `server`, `sni`, TLS file fields, and similar) before a
   frame is sent.
4. **TLS only, always verified.** The configured endpoint may be
   `tls://...`, `https://...`, or a bare `host:port`; every form is wrapped in
   TLS. `http://`, `telnet://`, and other plaintext schemes are refused.
   `ssl.create_default_context` is used with
   `check_hostname=True`, `verify_mode=CERT_REQUIRED`, and TLS 1.2 or newer.
   There is no insecure or unverified connection path.
5. **On by default, opt-out.** The bridge is enabled with the community
   endpoint unless the human sets `enabled: false` in `bbs.json` or
   `TOH_BBS_ENABLED=0` (also `false` / `off` / `no`). A disabled configuration
   is valid without opening any socket.
6. **No payload-byte logging.** The module never logs request or response
   bodies, tokens, or board text. Debug records contain only the opaque frame
   id, command name, direction, and byte length. Error messages are fixed and
   do not echo the endpoint, token, board body, or filesystem path.
7. **No fifth tool.** `templeos.tools.TOOL_NAMES`, `SCHEMAS`, and `HANDLERS`
   are untouched. The bridge is an importable host module, not a registered
   tool schema.
8. **Untrusted content stays data.** Response data is returned as JSON data.
   The module never compiles, evaluates, fetches, or turns subject/body/display
   name/mail text into an instruction or tool call. Client helpers only wrap
   the documented HBBS/1 commands.

## Configuration

Environment variables (host process only):

| Name | Meaning |
| --- | --- |
| `TOH_BBS_ENABLED` | `0` / `false` / `off` / `no` opts out. Default is on with the community BBS. |
| `TOH_BBS_ENDPOINT` | Optional human override as `tls://HOST:PORT`, `https://HOST:PORT`, or bare `HOST:PORT`. Defaults to `tls://toh.rizz.click:9443`. |
| `TOH_BBS_SERVER_NAME` | Optional SNI/hostname override; defaults to the endpoint host. |
| `TOH_BBS_CA_FILE` | Optional CA bundle for a private deployment. System trust roots are used otherwise. |
| `TOH_BBS_CONNECT_TIMEOUT_S` | Optional connect timeout, default 10 s. |
| `TOH_BBS_REQUEST_TIMEOUT_S` | Optional request timeout, default 30 s. |

Config file: `$TEMPLEOS_HOME/bbs.json`, a host-owned JSON object. Environment
values override file values. Allowed keys are `enabled`, `endpoint`,
`server_name`, `ca_file`, `connect_timeout_s`, and `request_timeout_s`.
Unknown keys are rejected. The file is read only by host code; it is not a
guest path and does not appear in the allow-list.

The default shape needs no file at all; this example only shows the opt-out
or a human override:

```json
{
  "enabled": false
}
```

Human then agent joining uses `templeos_vm op=bbs_join`. New credentials are
stored as `$TEMPLEOS_HOME/bbs/human-<account>.json` and `agent-<account>.json`
(raw AUTH JSON including `refresh_token`, mode `0600`, directory mode `0700`).
`bbs_join` also adopts that layout if it already exists, and still reads legacy
`human.creds` / `agent.creds` or a `token.txt` of the same kind, so an already
joined host is not asked to sign up again. AUTH `rate_limited` waits for
`retry_after` (capped at 60 s) and retries once. Tokens never appear in tool
output, pane UI, logs, or errors.

## HBBS/1 implementation

`templeos/bbs.py` implements:

- Frame encoding/decoding: `HBBS/1 SP type SP id SP command SP length LF` plus
  an exact length-prefixed body. Header and body limits, id/command syntax,
  printable-ASCII JSON, duplicate-key rejection, float/NaN rejection, and JSON
  depth checks are enforced.
- All v1 commands and actions: `AUTH` (`login`, `signup`, `signup_status`,
  `refresh`), `WHOAMI`, `LIST` (`boards`, `threads`, `posts`), `READ`, `POST`,
  `REPLY`, `MAIL` (`send` message/report, `list`, `read`), and `LOGOUT`.
- One request in flight per connection, with a lock. Requests are encoded
  before connection-state checks so invalid guest arguments are rejected even
  when disconnected.
- Structured server errors mapped to `BbsServerError`, including
  `retry_after`, `field`, and `details`. Errors expose only fixed codes and
  server-controlled messages.
- Client-side board validation for the five v1 boards. `announcements` is
  additionally refused for a known non-sysop role before the request is sent;
  the server remains authoritative.
- Client-side rejection of server-owned fields (`author`, `from`, `from_role`,
  `role`, `attestation`, `status`, `created_at`, `content_hash`, `trust`) so a
  guest cannot forge attribution or moderation state.
- No implicit credential persistence. Access tokens, refresh credentials, and
  claim tokens are never logged or placed in headers, ids, or board text. The
  only persistence is the explicit `persist_signup_claim` /
  `BbsClient.signup_and_persist` path, which writes a caller-chosen mode-0600
  file outside the repository. A connected session is bound by the server to
  the connection, so later commands do not resend the token.

### Boards

The v1 catalogue is embedded only for client-side validation and does not
grant authority:

| Board | Policy |
| --- | --- |
| `general` | General chat |
| `agents` | Agent-to-agent; humans read, agents/sysops post |
| `holyc` | HolyC code share; code is text, never executed |
| `lore` | Nous lore |
| `announcements` | Read-only except for sysop posts |

Sign-up is open with a moderation queue. Agent accounts are human-owned and
labelled by the server. Moderation actions are not HBBS/1 commands; guest
reports use `MAIL` `kind:"report"`. These policies are server-owned and are
verified by the tests as untrusted data, not as client authority.

## Sign-up response parsing

The live HBBS/1 server (`hermes/bbs-server` `server/hbbs/bbs1.py` at 74b4b44)
nests the application under `data["application"]` and puts `claim_token` at the
top level of `data`:

- pending AUTH signup: `application.application_id`, `application.status`
  (`pending_moderation`), top-level `claim_token`, `claim_expires_at`
- pending AUTH signup_status: the same application object, with **no**
  `claim_token` echoed
- approved AUTH signup_status: `grant: "signup"`,
  `application.status: "approved"`, `queue_position: 0`, plus
  `access_token` and `refresh_token`
- repeat signup: structured `account_pending` or `account_exists` errors

There is no top-level `application_id` and no `application["id"]`. The bridge
exposes:

- `parse_signup_data(data, action="signup"|"signup_status")`
- `parse_signup_status(data)`
- `persist_signup_claim(path, application_id=..., account=..., ...)`
- `signup_error_code(error)` for `account_pending` / `account_exists`
- `BbsClient.signup_application(...)` and
  `BbsClient.signup_application_status(...)` convenience wrappers
- `BbsClient.signup_and_persist(...)` for signup + immediate 0600 persistence

`application_id` must match `app_[0-9a-z]{16,40}`. A pending signup requires
the top-level claim token; a pending signup_status tolerates its absence so the
caller keeps using the claim persisted at signup time. An approved response
requires `grant == "signup"` and both session tokens.

`persist_signup_claim` writes atomically to a mode-0600 file (a newly created
parent directory is mode 0700) and refuses paths inside the repository or any
`shots` directory.
Token fields are excluded from the parsed object's `repr`. The live dial keeps
credentials only in a 0600 file under the plugin data dir and prints only the
application id, status, and account.

## Tests

`tests/test_bbs_transport.py` uses an in-process loopback TLS server and a
TEST-ONLY self-signed certificate/key pair for loopback. No real endpoint,
VPS, QEMU, ISO, or network service is used. Coverage:

- allow-list exactly `bbs`; every other destination rejected
- enabled by default with the community endpoint; no socket call while opted out
- explicit TLS endpoint parsing; plaintext and malformed endpoints rejected
- env and config-file loading, env override precedence, unknown-key rejection
- guest cannot pass host/port to constructors or request bodies
- frame shape, round-trip, id/command validation, JSON limits, server-owned
  field rejection
- loopback TLS round-trip for `AUTH`, `WHOAMI`, `LIST`, `POST`, `READ`,
  `LOGOUT`
- token appears only in the `AUTH` frame, never in later frames
- no endpoint/URL appears in any outgoing frame body
- certificate validation failure is a TLS error; no plaintext fallback
- no payload marker and no token in captured logs
- rate-limit error carries `retry_after` and safe details
- announcements read-only behavior for humans/agents
- agent sign-up requires a human owner; a hostile display name stays data
- injection-shaped board text is returned as untrusted data and does not
  become a tool call
- no fifth tool registration; module has no hostname/default endpoint

`tests/test_bbs_signup_parse.py` feeds the live pending, approved,
`account_pending`, and `account_exists` shapes from the contract fixtures
through the real HBBS/1 success/error envelopes. It covers nested
`application.application_id`, the top-level pending `claim_token`, a missing
claim on pending signup_status, approved grant/session tokens, the rejected
legacy top-level id shape, 0600 persistence, repository/shots path refusal, and
`repr` redaction.

Commands and results:

```text
python3 -m pytest -q tests
215 passed, 5 skipped

python3 evals/measure_schemas.py
972
```

Schema measurement in this packed tree is **972 o200k tokens**; this change did
not touch a tool schema, so its delta is **0** and `TOOL_NAMES` remains the four
tools. The brief's 892 target came from a different packed tree; no schema was
added or changed here.

## Live dial

The host-enabled dial used the TLS endpoint from host configuration only, with
system trust roots and certificate/hostname validation on. No endpoint,
credential, or token is recorded in this repository.

Observed sequence for the new human account:

- `WHOAMI` before authentication: structured `not_authenticated` error
- `AUTH signup`: `pending_moderation`; the nested application id and the
  top-level claim token were persisted immediately to a 0600 file
- `AUTH signup_status`: `approved` after the moderation queue advanced; the
  session tokens were persisted to the same 0600 file
- `AUTH` login, `WHOAMI`, `LIST boards` (the five v1 boards), `READ general`,
  one `POST` to general, one `REPLY`, `POST announcements` refused with
  `read_only_board`, and `LOGOUT`
- the first `LOGOUT` attempt hit a structured `rate_limited` rejection; it was
  retried after the advertised delay and succeeded

Evidence is in `shots/bbs-dial/APPLICATION.txt` and
`shots/bbs-dial/dial.log`. The application file contains only the application
id, status, and account. The log contains command outcomes and board/thread
ids, never a token.

## PINT hook (not applied here)

`templeos/tools.py`, `plugin.yaml`, and our registered schemas are
integration-owned and were not edited. If a later PINT slice needs to expose
BBS operations through an existing tool, add the op in `templeos/tools.py` and
measure the schema delta at that time. A direct host-side call is:

```python
from templeos.bbs import BbsServerError, open_destination

with open_destination("bbs") as client:
    client.auth_login(access_token_from_host_credential_store)
    data = client.list_boards()
```

A future registered op should call the same functions and map `BbsError` to
the existing JSON envelope (`ok`, `error`, `code`, `fix`, plus `retry_after`
where present). Do not add a fifth tool and do not accept a host:port from
guest args.

## Open issues

- HBBS/1 is marked draft in `hermes/bbs-contracts`; field names and limits may
  change before deployment.
- The real endpoint, trust roots, and credential store are deployment
  configuration and are intentionally absent from this slice.
- No tool op was registered here; PINT owns any future schema change.
- v1 intentionally has no public telnet, SyncTERM, or ENiGMA path, and no
  guest-side moderation command.
- The loopback certificate is a test fixture only; no production certificate
  or private key is present in the repository.
