# SlamCore OTA Contract

The authoritative, machine-verifiable cross-project contract for **SlamCore Server**, **SlamCore Agent**, and **SlamCore Updater**. Server schedules releases, Agent coordinates a device, Updater applies and recovers release activations, and SlamCoreWeb startup owns ROS build reconciliation. This repository contains contracts only—no product runtime.

## Contract 2.0 responsibility boundary

Updater owns artifact download and SHA-256 verification, strict package metadata validation, safe staging, active link/marker activation, managed runtime restart and health verification, rollback, and crash recovery. It does **not** own ROS builds.

`.slamcore_build_manifest.json` is workspace-level internal state owned exclusively by SlamCoreWeb Build Manager. OTA does not define its schema. Updater must never parse, validate, create, mutate, delete, migrate, checkpoint, or rollback it, and deployment must preserve unrelated workspace state.

A release archive uses `SlamCoreWeb/.slamcore-package.json` for strict package metadata. Workspace-root `.slamcore_release` is a different artifact: a one-line SemVer active-release marker written by Updater. It is not included in the ZIP and is never `KEY=VALUE` in Contract 2.0. See the [Integration Specification](docs/SlamCore-OTA-Integration-Spec.md).

## Layout

- `docs/`: integration specification, governance, compatibility, migration, and handoff notes.
- `openapi/`: OpenAPI 3.1 Server and Updater HTTP contracts (the `/api/v1` HTTP generation remains stable).
- `schemas/`: JSON Schema Draft 2020-12 DTO and release-package metadata models.
- `examples/`: non-sensitive valid payloads, package metadata, and the active marker.
- `scripts/validate-contracts.py`: local/CI validation, including cross-file Contract 2.0 invariants.

## Versions and compatibility

Repository releases use SemVer (`2.0.1` in `VERSION`); runtime payloads and `X-SlamCore-Contract-Version` use major/minor (`2.0`). Contract 2.0 is breaking: 1.x consumers cannot send `building`, parse the former KEY=VALUE `.slamcore_release`, or require the former build manifest. See the [migration section](docs/SlamCore-OTA-Integration-Spec.md#10-1x--20-migration) and [compatibility matrix](docs/compatibility-matrix.md).

## Validate locally

```bash
python -m pip install -r requirements-dev.txt
python scripts/validate-contracts.py
```

The validator checks every JSON document/schema, examples, OpenAPI references and structure, `VERSION`, the plain-text active marker, and semantic version/state/ownership invariants.

## Consume as a Git submodule

```bash
git submodule add <contract-repository-url> contracts/slamcore-ota
git -C contracts/slamcore-ota checkout contract-v2.0.1
git add contracts/slamcore-ota
git commit -m "chore: upgrade SlamCore OTA contract to 2.0"
```

Pin a reviewed commit/tag; never automatically track `main`. Complete 1.x jobs before coordinated migration of Updater, Agent, and Server. After merge and CI, a human—not a feature branch—may create `contract-v2.0.1`.

## FAQ

**May a consumer add a private state or DTO field?** No. Propose public behavior here first.

**Does v2 require TLS, authentication, or signatures?** No. Package SHA-256 verification remains mandatory.

**May Updater reject an unknown Build Manager manifest?** No. It must not inspect that internal file at all.

**Why can a DTO contain an unknown field?** Runtime DTO schemas allow unknown fields for minor-version forward compatibility; release-package metadata remains strict.
