# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and Semantic Versioning.

## [Unreleased]

## [2.2.0] - 2026-09-15

### Added

- Define capability-gated ViaAgent tree/forest registration, immutable ordered route snapshots and cross-language SHA-256 vectors, authenticated adjacent hops, stable end-to-end correlation, routed U/R commands and durable replay/uncertainty rules.
- Add Agent command/status reconciliation, root-only status sequence, dedicated Server history with R→U and unavailable version evidence, and explicit never-forwarded U failure evidence without changing legacy status schemas.
- Add topology-agnostic raw Updater evidence reads and Leaf/Root projections with immutable ordinals/phases, journal/runtime provenance, pagination coverage and explicit unknown versus confirmed physical execution.
- Add single-hop, branching and N-hop fixtures, durable restart/response-loss/outage transcripts, exact-reason semantic negative cases, compatibility/migration/security guidance and consumer handoff to Server #8/#18, Agent #9 and Updater #55.

### Review corrections

- Align Phase 4 error correlation UUID acceptance with the existing attempt header: preserve valid lowercase, uppercase and mixed-case spelling exactly, retaining generated diagnostic UUIDs for missing/malformed headers. Enforce the same canonical 8-4-4-4-12 case-insensitive structure and 36-character bound in both header/error schemas even without format assertion. Keep operationCorrelationId canonical lowercase and legacy 2.0 surfaces unchanged; add examples and exact-echo/invalid-UUID regressions under the recorded Issue #5 architecture decision.

- Enforce the already-defined actual-start bound against a known completion across phase records, including failed/unknown completion and either arrival order; validate partial status evidence before atomic receipt commit while retaining complete-set counting requirements. Add five regression groups without changing the unpublished 2.2.0 wire surface or runtime 2.0.

- Validate Server status acceptance before mutating receipts; reject terminal regressions atomically.
- Bind physical-start source identity/time across phases and attempts; reject reused confirmation sources and starts after completion.
- Carry explicit journal/watermark request continuations and snapshot-only proof scope; retain uncertainty after a rejected retry.
- Carry complete immutable originating rejection receipts through every authenticated upstream Agent and validate real durable A3/A2/A1 status/restart/outbox traces.

### Compatibility decision

- Repository minor version advances to 2.2.0; runtime remains 2.0 under the existing additive-endpoint precedent. Existing registration, pending commands, Agent/Updater payloads, twelve states, U/R rollback, status sequence/expiry and legacy history schemas retain their behavior.
- Require exact Agent-scoped hierarchical-relay-v1 and Updater physical-operation-evidence-v1 for new routed dispatch; existing explicit-rollback-v1 remains device-scoped. Unknown/missing support fails closed.
- No consumer runtime, deployment, tag, release, merge or production/HIL qualification is included.

## [2.1.1] - 2026-09-06

### Fixed

- Define a strict `versionEvidence=unavailable` Agent-to-Server status variant so an explicit rollback `R` can terminally fail after a definitive permanent rejection when authoritative Updater `fromVersion`/`targetVersion` evidence is unavailable, without fabricating versions.
- Require `failed`, a non-null `errorCode`, and a paired null version relationship for that variant; reject success, active rollback, one-sided null, missing/unknown discriminator, and null-error cases.
- Require Server contextual validation that the referenced job is rollback `R`, preserve the device current-version projection and original update `U`, and retain exact-replay behavior whenever mutation acceptance is uncertain.
- Document the coordinated Server-before-Agent rollout for the additive accepted payload while keeping normal status payloads, Updater behavior, and runtime `contractVersion=2.0` unchanged.

## [2.1.0] - 2026-09-06

### Added

- Add the explicitly discriminated `GET /devices/{deviceId}/command` endpoint and machine-readable update/rollback command schema while preserving the existing update-only endpoint.
- Define independent Server/Agent rollback identity `R`, required `originalUpdateJobId=U`, and the authoritative mapping to Updater body `jobId=U` with `Idempotency-Key: rollback:U`.
- Add valid update/rollback command and Updater rollback request examples, invalid discriminator/identity/package cases, round-trip checks, and cross-repository implementation guidance.
- Add the optional registration capability snapshot and require exact `explicit-rollback-v1` advertisement before Server rollback creation or delivery.

### Changed

- Clarify that explicit rollback reuses existing `rolling_back`, `rolled_back`, and `failed` states; `rolled_back` is success for rollback command `R` but remains failed-update recovery for update `U`.
- Keep runtime `contractVersion` at `2.0` because the new endpoint is additive and existing Server/Agent update plus Updater request semantics remain unchanged.
- Align Server legacy-update and Updater mutation OpenAPI responses with existing validation and idempotent replay behavior.

## [2.0.1] - 2026-09-03

### Fixed

- Align Contract 2.0 machine definitions with the existing status sequence and JSON-request correlation requirements: device status now requires the Agent-owned per-job sequence, status idempotency keys use `status:<jobId>:<sequence>`, affected JSON requests require `X-Correlation-Id`, and examples/validation enforce those relationships.
- Keep the runtime Contract version at `2.0`, the `/api/v1` generation, Server-owned logical `jobId`, and all Server/Agent/Updater responsibility boundaries unchanged.

## [2.0.0] - 2026-08-28

### Added

- Add strict JSON release-package metadata at `SlamCoreWeb/.slamcore-package.json` with its schema and example.
- Define workspace `.slamcore_release` as an atomic, one-line SemVer active-release marker and add an example.
- Add crash recovery and acceptance requirements around active-link mutation, marker commit, runtime health convergence, and workspace-state preservation.

### Changed

- Make SlamCoreWeb runtime startup solely responsible for ROS build reconciliation and allow 60 minutes for combined managed-runtime startup and health convergence.
- Make Updater failures runtime-oriented: inability to reach health after activation triggers rollback without exposing colcon or ROS-specific causes.
- Bump repository SemVer to `2.0.0` and every runtime contract discriminator to `2.0`.

### Removed

- Remove the Updater-managed public `building` state, incremental build behavior, ROS package validation, Build Manager invocation, and 45-minute Build timeout.
- Remove `schemas/release/slamcore-build-manifest.schema.json`, `examples/slamcore-build-manifest.json`, and all contract validation/references for this SlamCoreWeb-internal state.
- Remove the Contract 1.x ZIP-root `.slamcore_release` KEY=VALUE package metadata schema/example; package metadata and workspace active marker now have distinct filenames, formats, and owners.

## [1.1.0] - Draft

### Added

- Add `idle` to the Updater public `State` enum as the canonical `/status` value when no job is active.

### Fixed

- Resolve Integration Spec and Updater OpenAPI state mismatch and fix CI dependency cache discovery.

## [1.0.0] - Draft

### Added

- Initial OTA integration specification, OpenAPI 3.1 definitions, Draft 2020-12 schemas, examples, validation tooling, and governance documentation.
