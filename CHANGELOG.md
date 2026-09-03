# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and Semantic Versioning.

## [Unreleased]

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
