# Codex handoff

## Current baseline

- Repository version is `2.1.0`; runtime contract version remains `2.0`.
- Contract 2.0 is a breaking correction of the Updater/SlamCoreWeb ownership boundary.
- The package metadata is strict JSON at `SlamCoreWeb/.slamcore-package.json`; workspace `.slamcore_release` is only a one-line SemVer active marker.
- Explicit rollback orchestration uses the additive `/devices/{deviceId}/command` endpoint, mandatory `commandType`, independent Server/Agent rollback identity `R`, original Updater update identity `U`, and registration capability `explicit-rollback-v1`.
- Validate with `python -m pip install -r requirements-dev.txt` and `python scripts/validate-contracts.py`.

## Decided ownership

- Updater: download/integrity, package validation, staging, activation, active link/marker, managed runtime restart/health, rollback, durable crash recovery.
- SlamCoreWeb startup: ROS build detection and reconciliation.
- `.slamcore_build_manifest.json`: internal workspace state owned by SlamCoreWeb Build Manager. Its schema is deliberately absent from this repository. Updater may neither inspect nor alter it and must preserve unrelated workspace state.

## Consumer migration status

- SlamCore-Server, SlamCore-Agent, and SlamCore-Updater main all pin Contract commit `ae3f183aaf4e864fb02ac10c7f4cb8b723ebcd84` (`2.0.1`) and implement the runtime `2.0` update path.
- SlamCore-Updater already implements the authoritative rollback wire identity: request body `jobId=U`, key `rollback:U`, retained target derived from update journal `U`, and status at `GET /update/U`.
- SlamCore-Server has no discriminated command persistence or rollback creation path yet.
- SlamCore-Agent has an unused `RollbackAsync` HTTP client method, but its command model and coordinator remain update-only.
- No product repository is modified by this Contract branch.

## Required explicit rollback consumer work

1. Server persists the latest complete registration capability snapshot plus explicit command type and `originalUpdateJobId`, creates one rollback identity `R` per successful update `U` only when `explicit-rollback-v1` is present, and exposes the new `/command` endpoint while preserving `/update` as update-only.
2. Agent validates the discriminator, durably persists `R` and `U` before mutation, dispatches rollback using `U`, reports status to Server under `R`, and advertises `explicit-rollback-v1` only when the complete path is ready.
3. Server maps rollback `rolled_back` to successful completion for `R`; update `rolled_back` retains its existing automatic-rollback failure meaning for `U`.
4. Server and Agent add registration capability replacement/removal, capability-gated creation/delivery, idempotency, restart, response-loss, pre-submission expiry, post-submission expiry recovery, conflicting-payload, unknown-command, and terminal projection tests.
5. Updater requires no product logic change; update its Contract gitlink and rerun conformance after this Contract release is reviewed.

See [`explicit-rollback-orchestration.md`](explicit-rollback-orchestration.md) for the authoritative mapping and failure table.

## Deferred scope

Authentication, TLS, package signatures, rollout waves, pause/cancel, and messaging remain outside Contract 2.0.
