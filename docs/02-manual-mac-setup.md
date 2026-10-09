# Set up a local LiteLLM gateway on a Mac

Follow these Terminal and browser steps yourself to reproduce a native gateway with protected provider credentials. The [reference source](../reference/) implements the service account, fixed service controls and single startup item. No agent is required to perform the installation.

This recipe targets an **Apple Silicon Mac**, using the version baseline below. It was derived from a working installation; the complete fresh-install recipe has not been rehearsed on a second Mac. Review the reference source before granting administrator access. The version pins describe this baseline, rather than a promise that they remain the newest releases.

## What you need

- A local macOS administrator account and permission to install services on the Mac.
- Apple's Command Line Tools, including `/usr/bin/python3`, `clang`, `otool` and `install_name_tool`.
- A clone or downloaded copy of this repository, including its `reference/` folder. That folder contains the fresh-install source, configuration, client examples and dependency locks.
- Roughly **0.5–0.7 GB of downloads**, about **1 GB for the installed runtime**, and several GB of temporary workspace space. Command Line Tools, if missing, are an additional download. No model weights are downloaded.

Place the repository in an ordinary folder you own. Open Terminal and type `cd ` with a trailing space, drag the repository folder from Finder into Terminal, then press Return. Enter the reference folder:

```sh
cd reference
```

All relative paths in the setup commands below start inside `reference/`. Run one block at a time and stop if a step fails.

Check the prerequisites:

```sh
uname -m
xcode-select -p
/usr/bin/python3 --version
clang --version
```

`uname -m` must say `arm64`. If Command Line Tools are missing, install them using `xcode-select --install`, finish the installation, and reopen Terminal. For an Intel Mac, obtain a separately reviewed adaptation; the bundled engine names and download choices are specific to Apple Silicon.

## The final layout

| Component | Setting |
| --- | --- |
| Protected installation | `/Library/Application Support/LiteLLM` |
| Service account | `_litellm`, hidden, locked and without an interactive login |
| Dashboard | `http://127.0.0.1:4000/ui` |
| Client API base | `http://127.0.0.1:4000/v1` |
| Dedicated PostgreSQL | `127.0.0.1:55432`, database `litellm` |
| Startup job | `local.litellm.gateway`, displayed as **LiteLLM Gateway** |
| Service commands | `/usr/local/bin/llm-gateway`, `llm-gateway-admin`, `llm-call` |

The service uses loopback TCP. It has no LAN listener and no PostgreSQL Unix socket. It runs its own database cluster and does not use an existing development database, Docker engine or Homebrew installation.

| Software | Baseline version |
| --- | --- |
| LiteLLM proxy | 1.104.0 |
| Standalone Python | 3.12.15 |
| PostgreSQL | 16.15, from Postgres.app 2.9.6 |
| Node.js | 22.23.3 |
| Prisma Python / CLI | 0.15.0 / 5.17.0 |
| Build tool uv | 0.12.23, used only during preparation |

The runtime uses one gateway worker, a database pool of four, PostgreSQL shared buffers of 64 MB and a maximum of 25 database connections. Combined resident memory observed on the reference installation was roughly 350–650 MiB, varying with activity; shared PostgreSQL pages can be counted more than once in process totals.

## Prepare the workspace without administrator rights

Create the staging folders:

```sh
mkdir -p .build/downloads .build/bundle
```

Download the pinned build tool, Node.js and PostgreSQL distribution from their publishers:

```sh
curl -fL --retry 2 -o .build/downloads/uv.tar.gz \
  https://github.com/astral-sh/uv/releases/download/0.12.23/uv-aarch64-apple-darwin.tar.gz
curl -fL --retry 2 -o .build/downloads/node.tar.gz \
  https://nodejs.org/dist/v22.23.3/node-v22.23.3-darwin-arm64.tar.gz
curl -fL --retry 2 -o .build/downloads/postgres.dmg \
  https://github.com/PostgresApp/PostgresApp/releases/download/v2.9.6/Postgres-2.9.6-16.dmg
```

Calculate their hashes:

```sh
shasum -a 256 .build/downloads/uv.tar.gz
shasum -a 256 .build/downloads/node.tar.gz
shasum -a 256 .build/downloads/postgres.dmg
```

Compare each result exactly with this table **before extracting or running it**. A mismatch means stop, rather than bypass the check.

| File | SHA-256 |
| --- | --- |
| `uv.tar.gz` | `50487ae565ccd96e499056b4674d438f4c53170202617b4c759defe0c6a1b544` |
| `node.tar.gz` | `23b25245dcfb9af7262f8ff142e9e2e0af025368117329e7a7458a51e5922f53` |
| `postgres.dmg` | `2689dc64d6a02e0a66e4585616919060d8fbf5bb06886fccc05b7f87638bf081` |

The uv and PostgreSQL files are the publisher's [uv 0.12.23](https://github.com/astral-sh/uv/releases/tag/0.12.23) and [Postgres.app 2.9.6](https://github.com/PostgresApp/PostgresApp/releases/tag/v2.9.6) release assets. Obtain changed versions through a reviewed update to the pins, locks and instructions.

Extract uv and install Python only into this workspace:

```sh
tar -xzf .build/downloads/uv.tar.gz -C .build
.build/uv-aarch64-apple-darwin/uv python install 3.12.15 \
  --install-dir .build/python --no-bin --cache-dir .build/uv-cache
cp -R .build/python/cpython-3.12.15-macos-aarch64-none .build/bundle/python
.build/bundle/python/bin/python3.12 --version
```

The last command must report Python 3.12.15. uv obtains standalone Python distributions from Astral's Python build project. Copy the complete interpreter directory; do not retain a symlink to a user-managed Python. The installer will relocate console-script launchers before the runtime can read protected credentials. [uv Python installation](https://docs.astral.sh/uv/guides/install-python/)

Extract Node.js:

```sh
mkdir -p .build/bundle/node
tar -xzf .build/downloads/node.tar.gz -C .build/bundle/node --strip-components=1
.build/bundle/node/bin/node --version
```

The last command must report `v22.23.3`.

Mount the PostgreSQL image, copy its PostgreSQL 16 directory, and detach it:

```sh
mkdir -p .build/postgres-image
hdiutil attach -readonly -nobrowse -mountpoint "$PWD/.build/postgres-image" \
  .build/downloads/postgres.dmg
ditto .build/postgres-image/Postgres.app/Contents/Versions/16 .build/bundle/postgres
hdiutil detach "$PWD/.build/postgres-image"
.build/bundle/postgres/bin/postgres --version
```

The last command must report PostgreSQL 16.15. Do not install or launch the Postgres.app GUI. The copy is packaged below to keep the tools, required libraries and database resources while omitting unused add-ons.

## Prepare the locked Python packages and database engines

Use the supplied `requirements.lock`; do not resolve a new dependency set during this reproduction. First obtain a download list and its size from public PyPI metadata:

```sh
.build/bundle/python/bin/python3.12 -I scripts/estimate-download.py
```

The next block downloads the LiteLLM wheel into the cache expected by the wheel downloader and checks it against the lock:

```sh
/usr/bin/python3 -I - <<'PY'
import hashlib, json, urllib.request
from pathlib import Path
items = json.loads(Path('.build/downloads/wheel-estimate.json').read_text())
item = next(value for value in items if value['name'] == 'litellm')
assert item['sha256'] in Path('requirements.lock').read_text()
with urllib.request.urlopen(item['url'], timeout=60) as response:
    data = response.read()
assert hashlib.sha256(data).hexdigest() == item['sha256']
Path('.build/downloads/litellm.whl').write_bytes(data)
PY
.build/bundle/python/bin/python3.12 -I scripts/download-wheels.py
```

Install the verified wheels into the staging bundle, still as your ordinary account:

```sh
.build/uv-aarch64-apple-darwin/uv pip install \
  --python .build/bundle/python/bin/python3.12 \
  --target .build/bundle/packages --require-hashes --no-index \
  --find-links .build/wheels --only-binary :all: -r requirements.lock
```

Prisma is the database client tooling LiteLLM uses. Prepare its pinned CLI and native engines now, so the installed service does not need to download executable code later:

```sh
mkdir -p .build/bundle/prisma
cp assets/prisma/package.json assets/prisma/package-lock.json .build/bundle/prisma/
PATH="$PWD/.build/bundle/node/bin:/usr/bin:/bin" \
  .build/bundle/node/bin/npm ci --prefix .build/bundle/prisma --cache .build/npm-cache
.build/bundle/python/bin/python3.12 scripts/build-prisma.py generate
```

Keep the supplied npm lock. The generation helper changes the upstream schema's engine targets to `native`, avoiding unused Linux engine downloads. Runtime settings select the bundled Node and native query/schema engines, with Prisma offline mode enabled.

Package and inspect the native runtime, then build the two fixed helpers:

```sh
.build/bundle/python/bin/python3.12 -I scripts/package-postgres.py
.build/bundle/python/bin/python3.12 -I scripts/relocate-runtime.py
.build/bundle/python/bin/python3.12 -I scripts/audit-runtime.py
clang -O2 libexec/control.c -o .build/control
clang -O2 libexec/gateway-launcher.c -o '.build/LiteLLM Gateway'
```

These helpers use fixed installation paths. Compile the launcher without `SUPERVISOR_TEST`; a fixture build is unsuitable for installation. The audit must succeed, and relocation errors must be resolved before continuing.

Generate the bundle manifest after all staging changes:

```sh
/usr/bin/python3 -I - <<'PY'
import hashlib, json
from pathlib import Path
root = Path('.build/bundle')
manifest = {
    path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(root.rglob('*')) if path.is_file()
}
Path('.build/bundle-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY
```

The installer compares the copied runtime with this manifest. The manifest detects changes after preparation; publisher checksums and package locks provide the upstream provenance checks.

## Install the protected service

This is the point where administrator rights are needed. The installer creates the locked `_litellm` account, protected installation, one LaunchDaemon and three client commands. It also adds a narrowly scoped sudoers rule granting your account only `start`, `stop`, `restart` and `status` through the fixed control helper. It grants no general passwordless shell, Python, database or service-management access.

The runtime, configuration, helpers, service plist and sudoers policy are owned by the administrator. Database files, logs and backups are private to `_litellm`; the bootstrap secrets file is administrator-owned and readable by that account. Provider keys will be entered later in the dashboard.

The parent directories must already be root-owned, without group/world write permission or unexpected ACLs. On a fresh Mac, `/usr/local/bin` or `/private/etc/sudoers.d` may be missing. Inspect them first:

```sh
ls -lde '/Library/Application Support' /Library/LaunchDaemons \
  /usr/local /usr/local/bin /private/etc/sudoers.d
```

If a directory is missing, create **only that missing directory** with the appropriate command below. Do not apply these commands to fix ownership of an existing shared directory.

```sh
sudo /usr/bin/install -d -o root -g wheel -m 755 /usr/local/bin
sudo /usr/bin/install -d -o root -g wheel -m 755 /private/etc/sudoers.d
```

Stop for review if existing parents fail the installer's ownership or ACL checks. Do not recursively change permissions on shared system or Homebrew directories.

Run the installer from your ordinary Terminal:

```sh
sudo /usr/bin/python3 -I scripts/install.py "$USER"
sudo -k
```

Enter your Mac administrator password in Terminal. Nothing appears while you type it. Run `sudo -k` after the installation attempt, including after a failure, to clear the cached sudo authorization before returning to agent work. The installer refuses an existing installation, account/group conflicts, conflicting helper files or launch jobs, and occupied ports 4000 or 55432. Do not delete or reuse whatever caused a conflict.

It initializes only its own cluster, generates fresh bootstrap credentials and a stable encryption salt, and starts the one service. Package installers never run as root. The application database role is neither a superuser nor allowed to create databases or roles; password authentication uses SCRAM.

The installation then runs local fixture checks for account separation, authentication, route/model limits, budget rejection, revocation, usage capture, snapshot restoration and service controls. These checks do not call paid models. They create the initial verified snapshot and may leave tiny synthetic entries in usage history. Finally, a one-time dashboard invitation opens in your browser.

If installation stops, retain the error and workspace for review. The installer is for a fresh installation and is not a general repair command; repeatedly rerunning it over a partial installation is unsafe.

## Set your dashboard password

In the invitation page, set a dashboard password. The login identifier is `admin@litellm.local`; it is local and no email is sent. Save the password in your own password manager.

If the page did not open, run this yourself:

```sh
llm-gateway-admin invite
```

It requests fresh Mac administrator authentication and opens a new invitation directly in your browser. The invitation is a credential: do not copy its URL into agent output. Master-key/environment browser login is disabled. Keep the logged-in dashboard outside agent browser control.

For normal visits, open `http://127.0.0.1:4000/ui` and log in with the password you set.

## Add a provider and model

1. Create a dedicated OpenRouter API key in OpenRouter. Give it a provider-side spending cap appropriate to your use; this is an additional limit independent of LiteLLM. OpenRouter supports per-key credit limits and reset periods. [OpenRouter limits](https://openrouter.ai/docs/api_reference/limits)
2. In the LiteLLM sidebar, open **Models** and its credential management view. Add a reusable credential, choose OpenRouter and enter the provider key yourself. Menu labels can differ across UI revisions.
3. In **Models**, choose **Add Model**. Select OpenRouter, select your saved credential, and enter the upstream model as `openrouter/` followed by the exact OpenRouter model ID. For example, an OpenRouter ID `vendor/model-id` becomes `openrouter/vendor/model-id`. [LiteLLM OpenRouter configuration](https://docs.litellm.ai/docs/providers/openrouter)
4. Set or retain the public model name shown to clients. Keeping the full name is fine; an alias is optional. Save it and record that exact public name for clients and virtual-key permissions. Model records are stored in the gateway database. [LiteLLM model management](https://docs.litellm.ai/docs/proxy/model_management)

The public name goes in client requests and the virtual key's model allowlist. The upstream provider ID goes in the model's provider configuration. Do not invent a shorter alias in clients if you kept the original name in the dashboard.

Provider credentials entered through the dashboard are encrypted in this dedicated database using the protected salt. Rotate a provider key by creating its replacement at the provider, updating the saved credential in the dashboard, and revoking the previous provider key once the replacement works. Preserve the salt; changing it casually can make existing encrypted records unreadable.

## Create a virtual key for an agent or tool

1. Open **Virtual Keys → Create New Key**.
2. Give it a descriptive name, such as `agent-work` or `promptfoo-work`.
3. Select **AI APIs** as its key type. Do not grant management access to an inference client.
4. In **Models**, select the exact public model names it may call.
5. Set a budget of **$5**, reset duration **1 day**, and **60 requests per minute**. The configured default concurrency is **4**. Adjust the budget deliberately if your workload needs something else.
6. Create the key, copy it once, and give it only to the intended client. The dashboard supports key management and model/budget controls. [LiteLLM virtual keys](https://docs.litellm.ai/docs/proxy/virtual_keys)

Leaving Models at `no-default-models` blocks inference; it does not mean all models. The GUI's **AI APIs** preset is important: in this pinned release, the `allowed_routes` entry in default key-generation settings is not itself applied by the generator. The preset restricts the GUI key to AI APIs, whereas the optional provisioning helper uses explicit chat/model-discovery routes.

The default workflow does **not** create client key files. Hand the limited virtual key to an agent explicitly when authorizing its work. A virtual key is still a usable credential; revocation, selected models and spending limits control its authority.

`llm-gateway-admin clients MODEL_NAME ...` exists as an optional convenience, but writes separate `agents.key` and `promptfoo.key` files beneath `~/.config/llm-gateway`. It is outside this default workflow; use it only if you deliberately choose persistent client credentials.

## Make an explicitly authorized model call

For SDKs, use `http://127.0.0.1:4000/v1`, the exact public model name, and the virtual key. No upstream provider key is needed.

For the supplied command, create a `request.json` in your client workspace:

```json
{
  "model": "REPLACE_WITH_EXACT_PUBLIC_MODEL_NAME",
  "messages": [{"role": "user", "content": "Reply with gateway-ok."}],
  "max_tokens": 16,
  "stream": false
}
```

After replacing the model name, use your default macOS zsh Terminal to enter the virtual key without putting its literal value in a command or shell history:

```sh
read -r -s 'LITELLM_API_KEY?Paste the virtual key and press Return: '
export LITELLM_API_KEY
llm-call < request.json
unset LITELLM_API_KEY
```

The call can spend money and sends the prompt to the configured remote provider. This example creates no credential file. The key is available to processes started from that Terminal while the environment variable is set. `llm-call` disables ambient HTTP proxies for the local request.

LiteLLM's pinned OpenRouter chat adapter consumes provider-reported `usage.cost` when present. OpenRouter documents that usage can include the request cost. Other models/endpoints can use different accounting paths, so verify cost reporting for each one before relying on a dollar budget. Retain the provider-side cap as a second control. [OpenRouter response usage](https://openrouter.ai/docs/api_reference/overview#responses)

For promptfoo, configure its LiteLLM provider with the exact public name, `apiBaseUrl: http://127.0.0.1:4000`, and a session-provided `LITELLM_API_KEY`. Its dedicated LiteLLM provider uses that variable as the bearer key. An evaluation can make many calls; choose the scope and spending limit before running it. [promptfoo LiteLLM provider](https://www.promptfoo.dev/docs/providers/litellm/)

## Start and stop the whole service

```sh
llm-gateway status
llm-gateway stop
llm-gateway start
llm-gateway restart
```

These four fixed operations need no Mac password after installation. `status` shows whether the startup job is loaded; it is not a full health check. Give a start/restart time to become ready, then open the dashboard.

`stop` stops LiteLLM, its database and housekeeping, and keeps the service disabled across reboot. `start` enables it again. The supervisor stops the gateway before asking PostgreSQL to shut down. If either component fails unexpectedly, it cleans up its partner and launchd restarts the service after a delay. Sleep suspends availability; closing the dashboard tab does not stop the service.

## Understand Login Items and administrator prompts

In **System Settings → General → Login Items & Extensions**, expect one background service named **LiteLLM Gateway**. It manages PostgreSQL as a child process, rather than registering a separate PostgreSQL job. The local launcher has no Apple Developer ID, so macOS may describe it as an unidentified developer.

PostgreSQL retains Postgres.app's original signature from Jakob Egger. That publisher attribution is normal for those database binaries; the Postgres.app GUI/updater is not installed. Old Python/PostgreSQL entries can remain briefly in macOS's background-item records after a previous arrangement is replaced. Refresh Settings and inspect the actual launch jobs before changing anything. Avoid resetting all background-item records to fix one cached label. Apple documents inspection with `sfltool dumpbtm`. [Apple background task management](https://support.apple.com/en-gb/guide/deployment/depdca572563/1/web/1.0)

This manual recipe uses Terminal's `sudo` for installation. An agent may instead use AppleScript with administrator privileges to run a reviewed installation command; then macOS names **osascript** in the authentication prompt. That is real administrator execution. Everyday provider/model/key changes use the dashboard; `llm-gateway-admin` actions request fresh authentication and invalidate their sudo ticket afterward.

## Housekeeping and the single manual backup

Diagnostic logs are checked at startup and hourly inside the gateway process. Each file rotates when it exceeds **5 MiB**, with **three older copies** retained. This is a periodic check, not a strict size cap; logs can grow between checks. There is no separate housekeeping startup item.

Detailed spend/request records have **30-day retention** with the built-in cleanup interval set to **1 hour**, making cleanup practical during laptop sessions. Full prompt/response storage in spend logs is disabled. Daily usage and gateway-request summaries remain. They grow slowly with active days and the keys/models used; a small laptop deployment keeps this history rather than adding custom deletion jobs. LiteLLM's retention documentation describes the distinction; newer settings on that page should not be assumed to exist in the pinned release. [LiteLLM spend retention](https://docs.litellm.ai/docs/proxy/spend_logs_deletion)

PostgreSQL manages its own transaction logs and autovacuum. Do not manually delete files from its data cluster. Build downloads and caches are separate: the service runs from the protected installation after setup and does not depend on the original workspace's `.build` folder.

To make a backup, keep the gateway running and run this yourself:

```sh
llm-gateway-admin backup
```

There is no scheduled backup. The command creates a private archive, restores its database dump into a disposable database in **this dedicated cluster**, checks it, then atomically replaces `/Library/Application Support/LiteLLM/backups/latest.tar.gz`. A failed attempt preserves the old completed snapshot.

The archive includes the database, gateway YAML, installation version record and bootstrap/encryption secrets. It is private to the service and administrators, and is not an encrypted archive by itself. Export it only deliberately and protect any exported copy. It does not include all runtime binaries and is not a complete automatic disaster-recovery system. The supplied helper verifies restoration into a disposable database; restoration over a live installation needs a separate reviewed recovery procedure.

## Future updates and final checks

Updates are manual. Review release notes and security advisories, prepare a pinned replacement runtime without administrator rights, take the single protected backup, and preserve the old runtime before replacement. Database migrations may make code-only rollback insufficient. Never use an unrestricted package upgrade in the live installation, and preserve the encryption salt.

After setup, check the dashboard login, exact allowed models, virtual-key scope, one small authorized model call and its cost in the dashboard. Check start/stop behavior and Login Items. A full reboot and each live endpoint's cost capture still need checking on the destination Mac; the reference setup was tested for service stop/restart and one live non-streaming chat call, but not for an actual machine reboot or every API endpoint.

Account separation protects against ordinary-user access to provider secrets and modification of the protected runtime. Host administrator access, dashboard administrator access or a service vulnerability can bypass that boundary. Giving an agent a limited key authorizes that key's permitted calls, not installation administration.
