# Agent runbook for recreating a local LiteLLM gateway

Recreate the native Mac gateway defined here using the [manual setup recipe](02-manual-mac-setup.md) and [reference implementation](../reference/). Keep its architecture and operating policy fixed. Prepare all code and dependencies before requesting administrator execution; guide the human through credential entry and dashboard onboarding.

This is a fresh-install runbook for Apple Silicon. The source reflects a working reference installation, but the consolidated fresh-install recipe has not been executed on another Mac. Report checks actually performed on the destination. Do not claim a reboot, provider cost path or restoration procedure was tested merely because this runbook describes it.

## Required result

| Area | Required setting |
| --- | --- |
| Installation | `/Library/Application Support/LiteLLM` |
| OS account | Hidden, locked `_litellm`, non-admin, `/usr/bin/false` shell; unused UID/GID from 450–499 |
| Runtime | Standalone Python and root-owned packages, scripts, configuration and fixed native helpers |
| Gateway | `127.0.0.1:4000`, one worker; client base `/v1`, dashboard `/ui` |
| Database | Dedicated PostgreSQL 16 cluster at `state/postgres`, port 55432, loopback TCP, SCRAM; no Unix socket |
| SQL privileges | App role `litellm`: no superuser, database creation or role creation rights |
| Startup | Exactly one `local.litellm.gateway` LaunchDaemon with native executable **LiteLLM Gateway** |
| Process ownership | Supervisor, PostgreSQL and gateway all run as `_litellm`; ordinary operation does not run as root |
| Controls | Four exact passwordless actions through the root-owned control helper; no general privileged command grant |
| Credential entry | Human enters upstream provider keys and dashboard password; agent receives only an explicitly supplied virtual key |
| Client keys | Exact model allowlist, inference API scope, $5 per day, 60 RPM and concurrency 4 by default; no automatic key-file persistence |
| Logs | Check at startup and hourly inside the gateway; rotate above 5 MiB and keep three older copies |
| Spend records | Disable full prompt/response storage; detailed records retained 30 days, built-in cleanup interval 1 hour |
| Backup | Manual only; one completed private `backups/latest.tar.gz`, atomically replaced after restore verification |

Use this baseline: LiteLLM 1.104.0, Python 3.12.15, PostgreSQL 16.15 from Postgres.app 2.9.6, Node 22.23.3, Prisma Python 0.15.0 / CLI 5.17.0, and uv 0.12.23 during preparation. Check whether a security advisory requires a change before installation, and make any version deviation explicit. Keep a changed runtime pinned and review its compatibility; do not silently substitute the latest packages.

This design uses native processes and a dedicated local TCP database. Preserve it. Docker/Compose, another Docker engine, Redis, a shared development database, a private socket, extra startup jobs, scheduled backups or automatic upgrades are changes to the agreed result, not routine implementation details.

The coding agent's own provider/backend configuration is outside scope. Route only the external model calls made by its tools, agents and evaluation clients.

## Authorization and human handoffs

An explicit request to perform this installation authorizes ordinary preparation and the necessary reviewed installation changes. Respect existing authorization; do not repeatedly request the same permission. macOS authentication and execution-tool approvals still apply.

| Action | How to handle it |
| --- | --- |
| Read supplied source, inspect this service's paths/ports, prepare downloads and compile in the chosen workspace | Proceed within the install request. Explain download size first if bandwidth matters. |
| Create the account, protected tree, LaunchDaemon, client commands and exact sudoers policy | Prepare a concrete reviewed bundle first, explain the permanent changes, then use the human's administrator authentication and required tool approval. |
| Create a missing protected parent directory | Check that it is actually missing; create only the needed root-owned directory through the same approved administrative step. |
| Set dashboard password, paste provider credential, open/use an invitation | Human performs the credential interaction. Keep invitations and authenticated dashboard sessions out of agent output and browser control. |
| Make paid model calls | Require authorization for the call or bounded task, including selected models and spending scope. A key being available is not permission to run unrelated evaluations. |
| Start/stop/restart during authorized setup or maintenance | Use the installed fixed controls. Do not add a broader sudoers grant when a tool approval is needed. |
| Persist a virtual key, provision optional client files, export a backup | Obtain specific authorization for persistence/export; neither follows from creating a GUI key. |
| Change architecture, broaden routes/models/budgets, rotate salt, replace existing services/accounts or restore live data | Treat as a scope change requiring a concrete proposal and authorization. |
| Retry a denied action using another tool | Do not bypass a denial. Use independent permitted evidence where useful and state any remaining gap. |

Never ask for the human's Mac password in chat, read upstream provider keys, print bootstrap JSON, dump the live process environment, or copy protected databases/logs/backups into the ordinary workspace for diagnosis. Privileged diagnostics can read protected data internally and return fixed messages or redacted, relevant results.

If `osascript` with administrator privileges is used, explain that it runs the specific reviewed installer with real administrator rights. Prefer direct human Terminal `sudo` for the manual handoff when practical. Ordinary service controls use a narrow existing rule; they do not authorize arbitrary root commands. Keep human admin commands separate and invalidate cached sudo authorization afterward.

## Execute the fixed installation sequence

### 1 Inspect only the intended installation

Read this runbook, the manual recipe, the supplied source and any applicable local instructions. Confirm Apple Silicon, Command Line Tools, sufficient temporary storage and the selected ordinary account. Discover its username at execution time; do not embed a developer's personal home path in code or documentation.

Check for conflicts with `/Library/Application Support/LiteLLM`, `_litellm`, its group, the exact helper/launchd/sudoers paths, and ports 4000/55432. Do not inventory unrelated development databases or containers unless it is needed and authorized. A port probe is sufficient to establish a collision; do not kill the process using the port or silently adopt its database.

Inspect protected parents for root ownership, group/world write permission and ACLs. A conflict or unsafe shared directory is a stop for review. The installer deliberately refuses adoption and overwrite.

### 2 Prepare without root

The reference is supplied to avoid unnecessary reimplementation. It is not preinstalled on the destination. Review and build it there, or implement the same documented boundaries if a concrete compatibility issue requires adaptation. In particular, preserve the native supervisor and fixed control helper: those pieces keep one startup item and constrain privileged service operations. The Python and promptfoo examples show only client use; they never need a provider credential.

Use `reference/` as the preparation working directory and follow the manual's staging commands exactly. Download the pinned uv, Node and PostgreSQL assets and verify the stated SHA-256 values. Install standalone Python inside `.build`, copy the full interpreter directory into `.build/bundle/python`, and keep the Node and PostgreSQL copies inside the same bundle.

Use the existing Python hash lock; estimate wheel downloads, fetch the cached LiteLLM wheel and other hash-checked wheels, then install them into `.build/bundle/packages` with no index. Do not resolve a new lock as part of an exact reproduction. Keep package install commands unprivileged.

Copy `assets/prisma/package.json` and its lock into the bundle's Prisma directory. Use bundled Node for `npm ci` and generate the Python client through `scripts/build-prisma.py generate`. Package PostgreSQL, relocate native libraries and run the runtime audit. Compile `libexec/control.c` and `libexec/gateway-launcher.c` into `.build/control` and `.build/LiteLLM Gateway`, respectively. Do not define `SUPERVISOR_TEST` for the production binary.

Generate `.build/bundle-manifest.json` after all changes to the staged runtime. Review the installer, production supervisor, control helper, root-facing admin helper, YAML and exact sudoers grant. The manifest covers the runtime copied by the installer; it does not turn untrusted source into trusted source.

The reference folder contains only the fresh-install implementation and its required pins/examples. Credentials, generated runtimes, databases, backups and earlier migration/debug scripts are not part of the repository. Do not fetch or replay historical migrations to recreate the final design. The fresh installer already implements the consolidated service.

### 3 Install the reviewed result

Use the human-authenticated command from the manual:

```sh
sudo /usr/bin/python3 -I scripts/install.py "$USER"
sudo -k
```

Ensure the named user is the intended ordinary Mac account. Clear cached sudo authentication after the attempt, including on failure. The installer verifies the bundle, creates the locked account, copies and seals the runtime, rewrites staging Python entrypoints, generates fresh secrets, initializes only its own database, and writes the single LaunchDaemon and narrowly scoped controls.

The secret directory is root-owned with mode 0750 and the service group; `bootstrap.json` is root-owned with mode 0640 and the service group. Writable state, logs and backups are service-owned with mode 0700. Executable/configuration trees are root-owned and not writable by the client account. Preserve these boundaries when adding files.

Keep the encryption salt stable after initialization. The service clears ambient environment variables, uses isolated Python and fixed protected paths, and selects its prepared Prisma engines. No caller-controlled import path, command path or environment override belongs in the installed privileged helpers.

The startup job uses `RunAtLoad`, `KeepAlive`, a 15-second throttle, a shutdown timeout of 75 seconds, and `_litellm` as user/group. Its sole program is the fixed native **LiteLLM Gateway** supervisor. The supervisor starts PostgreSQL and Python; Python waits for an authenticated database connection. It stops the gateway and its descendants before PostgreSQL, and cleans up both when either exits.

On failure, report the last safe error and partial state. The installer is not an idempotent repair command. It has a narrowly checked recovery marker for its own partially created account, but an existing protected installation still blocks a fresh run. Do not solve that by deleting the installation, resetting a database, editing its recovery marker or adopting an arbitrary account.

### 4 Hand credential steps to the human

Let the installer or `llm-gateway-admin invite` open the one-time invitation directly for the human. The local login identifier is `admin@litellm.local`; it is not a personal email address and sends no email. The human sets the dashboard password and enters the upstream credential. Bootstrap/environment dashboard login stays disabled.

Guide the human to add a provider credential and a model. For OpenRouter, the provider model is `openrouter/` plus the provider's exact ID. Record the public model name actually selected. A retained full name and a custom alias are both valid; match it exactly in client requests and the key's Models list.

Guide virtual-key creation with **AI APIs**, the exact model allowlist, budget/reset and rate limits. Leaving `no-default-models` blocks calls. Do not select all models or management routes to get a failing test to pass. In the pinned release, `default_key_generate_params.allowed_routes` is not applied by the generator: use the GUI's key-type preset or explicitly supply route permissions when provisioning an authorized key.

Default to explicit key handoff. Do not run `llm-gateway-admin clients ...`, create `.key` files, add credentials to shell startup files or configure a credential manager unless the human chooses persistence. The optional helper creates separate viewer-owned agent/promptfoo keys with explicit chat/model-discovery routes, but also persists them; describe that consequence before offering it.

### 5 Check the destination and report honestly

The installer includes local checks that use a disposable provider fixture rather than a paid service. They test ordinary-account access restrictions, ownership, database authentication/SQL role restrictions, inference/management separation, allowlists, streaming and non-streaming local usage capture, tiny-budget rejection, revocation, backup restoration and stop/start controls. They create one initial verified snapshot and can leave synthetic usage records. Review their output rather than rerunning blindly over a live installation.

Confirm that exactly one launch job belongs to the gateway and its children have the service UID. Confirm stop disables the job persistently and stops the dedicated database, then start it and wait for readiness. The installed `status` command only reports whether the job is loaded; it does not establish healthy inference.

Have the human check Login Items and the dashboard. Do not call a denied UI tool again through an alternate automation channel. If the UI cannot be inspected, use permitted job/file metadata and distinguish the visible-name check from the actual startup-job check.

For the first real model test, get authorization for one small chat completion, use the supplied virtual key without printing or saving it, cap output tokens, and report the nonsecret response/status and available cost. Wait for asynchronous usage updates before checking the dashboard. Never turn one-call authorization into a sweep across models/endpoints.

A previous real non-streaming OpenRouter chat response supplied a matching response cost, but live dashboard persistence, live streaming/Responses accounting and a full machine reboot were not all verified in the reference setup. Test the endpoints actually approved for the destination. Cost capture and a correctly configured allowlist are prerequisites to trusting spend limits; synthetic tests alone do not establish every provider billing path.

Conclude with the installed versions, one service name, endpoint, control commands, key persistence choice, checks performed and any unresolved failures. Keep provider/master/database credentials and invitation URLs out of the report.

## Client use after installation

The client needs only the base URL `http://127.0.0.1:4000/v1`, exact public model name and its limited virtual key. Use `llm-call` with a JSON request on stdin or an OpenAI-compatible SDK. Pass the virtual key through the authorized session environment or another explicitly chosen channel; do not put it in command-line arguments, source, traces or saved fixtures. `llm-call` disables ambient HTTP proxies on its local request.

For promptfoo, use `litellm:PUBLIC_MODEL_NAME`, API base `http://127.0.0.1:4000`, and the limited key as `LITELLM_API_KEY`. Evaluation scope must fit the approved budget and model list. The provider and coding agent's own key configuration remain outside this gateway client setup. [promptfoo LiteLLM provider](https://www.promptfoo.dev/docs/providers/litellm/)

OpenRouter responses can carry `usage.cost`; the pinned chat adapter records it in LiteLLM's provider cost metadata. If that information is absent or the endpoint differs, examine the installed accounting path before choosing verified custom pricing. Do not promise that every charge is captured or raise a key limit to hide an accounting problem. [OpenRouter usage schema](https://openrouter.ai/docs/api_reference/overview#responses)

## Problems encountered and fixes to preserve

| Problem | Cause and required response |
| --- | --- |
| Separate account creation or initialization left a partial installation | Use identity-checked recovery for that exact attempt only. Preserve the recorded GUID/UID and inspect partial state; never adopt an unrelated existing `_litellm` account. |
| Runtime launchers referred back to user-writable staging Python | The final installer rewrites Python console entrypoints to invoke the protected interpreter with `-I`; generated Prisma client paths are relocated. Inspect copied launchers after installation. |
| Native libraries expected external or unsuitable paths | Prefer native bundled wheels, including SoundFile, package only needed PostgreSQL dependencies, relocate loader paths, and audit native binaries. Do not repair by adding a Homebrew/user library search path to the service. |
| Prisma tried to use missing tooling or fetch unnecessary engines | Prepare bundled Node, pinned CLI/engines and the generated Python client before sealing. Generate only `native`; runtime selects the prepared engines and offline mode. |
| Administrator invitation failed on a missing creator identity | The admin helper first creates the bootstrap creator's database row without a password/key, then the human dashboard admin and invitation. Do not enable a generic master-key dashboard login as a shortcut. |
| The UI suggested default model access, but calls returned 403 | Models contained `no-default-models`. Select the exact configured public model name and save the key settings. Do not rename a client model to an alias that was never created. |
| Default route YAML looked restrictive but was ignored | The pinned generator does not apply default `allowed_routes`. The GUI key must use **AI APIs**; explicit provisioning must pass the intended route list. Test that management routes remain denied. |
| A service change failed with `launchctl bootstrap` error 5 | Persistent disabled state or a recent job shutdown can prevent bootstrapping. Enable the exact job, wait for it to unload, then use a bounded retry and check readiness. Start with the fixed installed control. If it still fails, inspect protected diagnostics instead of loosening ownership or creating duplicate jobs. |
| Python and the PostgreSQL signer appeared as separate background items | One native launcher named **LiteLLM Gateway** supervises both components under one LaunchDaemon. Retain PostgreSQL's original signature. Do not add a fake publisher association or re-sign the database merely to change the label. |
| Old background-item names remained after consolidation | macOS retained cached legacy metadata even after the old jobs were gone. Check actual jobs and refresh Settings. Do not globally reset background records or disturb unrelated apps. |
| Daily retention was poorly suited to short laptop sessions | The built-in cleanup's first run follows its interval. Use `maximum_spend_logs_retention_interval: 1h` with 30-day detailed retention; do not add another scheduler. |
| Startup-only log cleanup would miss a Mac left on continuously | Keep the hourly log thread inside the existing gateway process. Copy/truncate preserves open log descriptors; keep three rotated files. No separate log daemon. |
| Daily backups added unwanted scheduling and storage | Keep the single manual command. Serialize requests, build privately, verify restoration, then replace `latest.tar.gz`; preserve the previous completed archive on failure. |
| Saving a GUI-created key broadened persistence beyond the requested handoff | GUI key creation does not configure a client key file. Keep explicit handoff as the default; persistence requires a separate human choice. |

The reference implementation incorporates these corrections. Preserve the working behavior; do not recreate the failing intermediate states.

## Storage and maintenance boundaries

All periodic cleanup is inside the gateway: local log checks at startup/hourly and LiteLLM's built-in detailed-spend cleanup. When the service is deliberately stopped, PostgreSQL and both cleanup mechanisms stop too. Sleep suspends availability. Closing a browser tab does not stop the service.

The 30-day rule covers detailed request/spend records and their tool index. Daily usage and gateway-request summaries are deliberately retained: their growth is modest for a laptop with a few stable keys/models, so no custom purge is required. Fixed runtime/cache artifacts and database high-water space are separate from per-request history. Periodic log checks are not hard byte caps. PostgreSQL handles WAL recycling and autovacuum; never delete cluster files manually, and do not add vacuum/shrink/delete schedules without a concrete need and authorization. Current retention docs include newer options that may not exist in the pinned release. [LiteLLM spend retention](https://docs.litellm.ai/docs/proxy/spend_logs_deletion)

`llm-gateway-admin backup` requires the service running and fresh human authentication. Its private archive includes configuration, version metadata, database and bootstrap/encryption secrets; it does not include the complete runtime. Restore verification creates and drops only a random disposable database inside the gateway cluster, never overwrites the live database, and checks the salt. Keep exactly one completed snapshot. Do not export it or implement live restoration without specific authorization.

Build staging can be removed after a successful installation when no longer needed for review, reproduction or update preparation. Retain the clean source and locks. Do not remove staging before confirming the installed runtime has no executable/import dependency on it.

For an update, review current advisories, prepare pinned dependencies unprivileged, create the manual snapshot, preserve the existing runtime/configuration, then perform an approved replacement. Consider schema migrations when preparing rollback; old code alone may not read a migrated database. Keep the same salt with its encrypted database records. Automatic updates and scheduled backups are outside this design.

## Protection and limits

The service account and root-owned runtime protect provider credentials against ordinary-account file reads and code replacement. Virtual keys limit client models, rates and measured spend. The dedicated PostgreSQL cluster avoids collisions and accidental operations on development databases. One native startup job keeps the laptop overhead and controls simple.

This boundary does not withstand host administrator access, dashboard administrator access or a service vulnerability. An agent with a general usable sudo grant can bypass it. Preserve the narrow control rule, keep the authenticated dashboard human-controlled, and keep provider-side spending caps. Do not claim perfect isolation or guarantee that all future provider costs obey an exact hard dollar ceiling.
