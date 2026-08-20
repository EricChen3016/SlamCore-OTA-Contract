# Repository guidance

This repository is the single authoritative source for the SlamCore OTA contract shared by SlamCore Server, Agent, and Updater.

## Contract governance

- Change public APIs, DTOs, the update state machine, error codes, or release formats here before changing an implementation repository.
- Server, Agent, and Updater must not independently extend or reinterpret the contract.
- A breaking change includes removing or renaming a field or endpoint, making an optional field required, narrowing accepted values, changing a type or state meaning, or changing a required release-package file. Breaking changes require a new SemVer major version.
- Backward-compatible additions use a minor version; documentation or validation fixes that do not change runtime semantics use a patch version.
- Runtime `contractVersion` is `major.minor`; repository releases use full SemVer.
- Schema changes must update their examples, referenced OpenAPI definitions, and `CHANGELOG.md` in the same change.

## Codex scope

Codex may edit specifications, OpenAPI documents, JSON Schemas, examples, validation tooling, CI, and governance documentation in this repository. It must not add Server, Agent, or Updater runtime implementations, a database, a UI, authentication, or transport encryption. It must not modify any other repository.

Do not create or push tags from a feature branch. A human creates `contract-v*` tags only after review, validation, and merge.
