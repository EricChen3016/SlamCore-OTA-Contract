# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and Semantic Versioning.

## [Unreleased]

### Added

- Add `idle` to the Updater public `State` enum as the canonical `/status` value
  when the service is available with no active job; `activeJobId` is null in this
  state.

### Changed

- Bump the repository contract to `1.1.0` and the runtime contract version to
  `1.1` for the backward-compatible public enum addition.

### Fixed

- Resolve the Integration Spec and machine-verifiable Updater OpenAPI mismatch
  while preserving `queued` as an accepted-but-not-started job state.
- Point the GitHub Actions pip cache at `requirements-dev.txt` so dependency cache discovery does not fail before contract validation runs.

## [1.0.0] - Draft

### Added

- Initial OTA integration specification, OpenAPI 3.1 definitions, Draft 2020-12 schemas, examples, validation tooling, and governance documentation.
