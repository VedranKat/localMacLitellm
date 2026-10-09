# Local LiteLLM gateway on a Mac

A guide to recreating a local gateway so agents and evaluation tools can call OpenRouter or other providers using limited virtual keys. Provider credentials stay with a protected service account. The coding agent's own backend is unchanged.

## Start with the guides

1. [Quick human summary](docs/01-summary.md) — what the setup does and why.
2. [Manual Mac setup](docs/02-manual-mac-setup.md) — Terminal and dashboard steps for a human.
3. [Agent recreation instructions](docs/03-agent-mac-setup.md) — the required design, permission handoffs, known problems and verification steps.

## Reference files worth reusing

The [reference implementation](reference/) supplies the fresh-install code, configuration, dependency locks and client examples used by the guides. Reuse or review it before rebuilding the same pieces. It saves another agent from rediscovering the account permissions, native-library relocation, service supervision and database tooling.

| Files | Purpose |
| --- | --- |
| `reference/config/` | LiteLLM defaults, model-access restrictions and detailed request retention; no credentials |
| `reference/bin/` and `reference/libexec/` | One native service supervisor, fixed start/stop controls, isolated runtime, onboarding, housekeeping and manual backup |
| `reference/scripts/` | Fresh installer and preparation tools for the pinned runtime |
| `reference/requirements.in`, `reference/requirements.lock` and `reference/assets/prisma/` | Dependency versions, wheel hashes and the pinned database tooling |
| `reference/examples/` | Python and promptfoo clients using an explicitly supplied virtual key |

The repository contains no runtime downloads, generated credentials, database, backup or build artifacts. Earlier migration/debug scripts and a duplicate source ZIP are excluded. The guides define the desired result; the reference code is there to help someone reproduce it efficiently.

## The resulting service

LiteLLM and a dedicated PostgreSQL cluster run under a hidden, locked `_litellm` account. One **LiteLLM Gateway** startup job manages both. The API and dashboard listen on `127.0.0.1:4000`; the database uses its own loopback port, `55432`.

Normal-account commands control the service. The human manages provider credentials, models and virtual keys in the dashboard. Logs rotate inside the gateway, detailed request records have 30-day retention, small daily summaries remain, and backups are manual with one replaceable snapshot.

Read the manual before running commands. Preparation takes place without administrator rights; installation changes accounts, protected files, a startup job and a narrowly scoped sudoers policy. The reference reflects a working Apple Silicon installation; the complete fresh-install recipe still needs validation on a second Mac. Versions are a reproduction baseline, not an instruction to ignore security advisories.
