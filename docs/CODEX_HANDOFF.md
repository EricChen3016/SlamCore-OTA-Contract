# Codex handoff

## Current Phase 4 baseline

- Repository 2.2.0, runtime 2.0, based on main `bdf02af7c4e746afecb7bed19a493645c8f412cc`.
- [Phase 4 normative contract](phase4-viaagent.md) freezes additive ViaAgent routing, Agent registration/capabilities, durable U/R relay, root status/history and raw/projected physical evidence.
- [Acceptance mapping](phase4-acceptance.md) and [compatibility matrix](compatibility-matrix.md#phase-4-supported-and-fail-closed-combinations) define consumer validation and rollout.
- Server #8, Agent #9 and Updater #55 implement consumer changes after reviewed Contract pinning. Server #18 owns fixed-artifact HIL/production qualification; prior evidence gaps remain unproven.
- No consumer repository is changed by this Contract delivery.

## Historical 2.1.1 baseline

- Repository version is `2.1.1`; runtime contract version remains `2.0`.
- Contract 2.0 is a breaking correction of the Updater/SlamCoreWeb ownership boundary.
- The package metadata is strict JSON at `SlamCoreWeb/.slamcore-package.json`; workspace `.slamcore_release` is only a one-line SemVer active marker.
- Explicit rollback orchestration uses the additive `/devices/{deviceId}/command` endpoint, mandatory `commandType`, independent Server/Agent rollback identity `R`, original Updater update identity `U`, and registration capability `explicit-rollback-v1`.
- An explicit rollback `R` that receives a definitive permanent rejection without authoritative Updater version evidence can report terminal `failed` with both versions null and `versionEvidence=unavailable`. Server accepts this only for `R` and preserves device current version plus original `U`.
- Validate with `python -m pip install -r requirements-dev.txt` and `python scripts/validate-contracts.py`.

## Decided ownership

- Updater: download/integrity, package validation, staging, activation, active link/marker, managed runtime restart/health, rollback, durable crash recovery.
- SlamCoreWeb startup: ROS build detection and reconciliation.
- `.slamcore_build_manifest.json`: internal workspace state owned by SlamCoreWeb Build Manager. Its schema is deliberately absent from this repository. Updater may neither inspect nor alter it and must preserve unrelated workspace state.

## Historical 2.1.1 consumer migration status

- Contract `2.1.0` is merged at `a19db3b25109d5b31019bf517f9cf0969746a41e`; the historical `2.1.1` branch started from that exact commit.
- SlamCore-Updater already implements the authoritative rollback wire identity: request body `jobId=U`, key `rollback:U`, retained target derived from update journal `U`, and status at `GET /update/U`.
- SlamCore-Server main `feed650ce0f1d5903ca6729b4ef0c98030f21c8b` implements explicit rollback orchestration but does not yet accept the `2.1.1` unavailable-evidence status variant.
- SlamCore-Agent feature `7006483eacdba9a274628a571f3705dc542ee5f4` implements durable explicit rollback and deliberately keeps `R` Unknown when authoritative versions are unavailable; it must not emit the new variant until Server is upgraded.
- No Server, Agent, Updater, or SlamCoreWeb product repository is modified by this Contract branch.

## Required `2.1.1` consumer work

1. Server updates `ContractDeviceStatusRequest`, its JSON converter, status/schema validation, rollback contextual validation, and device-version projection. `R failed + unavailable` is terminally accepted while device version and original `U` remain unchanged; the same variant for `U` is `400 VALIDATION_FAILED`.
2. Agent makes status versions nullable only for the special variant, serializes `versionEvidence=unavailable`, and maps definitive permanent rollback rejection—including the journal-missing case—plus evidence-free `COMMAND_EXPIRED`. Persistence/outbox exact replay and serialization tests must cover it.
3. Roll out Server acceptance before Agent emission. An Agent connected to an old Server must not emit the new variant; old normal status remains valid.
4. Updater and SlamCoreWeb require no product changes. Updater's wire identity, query, and exact-replay behavior remain unchanged.
5. Server and Agent update their Contract gitlinks only after this Contract change is reviewed.

See [`explicit-rollback-orchestration.md`](explicit-rollback-orchestration.md) for the authoritative mapping and failure table.

## Implementation scope boundary

Phase 4 requires authenticated adjacent peers and authorized Leaf access. Authentication/TLS/PKI runtime implementation, package signatures, rollout waves, pause/cancel and messaging implementation are outside this Contract change.
