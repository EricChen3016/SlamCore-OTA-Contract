# SlamCore OTA Contract

The authoritative, machine-verifiable cross-project contract for **SlamCore Server**, **SlamCore Agent**, and **SlamCore Updater**. Server schedules releases, Agent coordinates devices and relays to child Agents, Updater applies and recovers release activations, and SlamCoreWeb startup owns ROS build reconciliation. This repository contains contracts only—no product runtime.

## Contract 2.0 responsibility boundary

Updater owns artifact download and SHA-256 verification, strict package metadata validation, safe staging, active link/marker activation, managed runtime restart and health verification, rollback, and crash recovery. It does **not** own ROS builds.

Repository `2.1.0` adds explicit Server → Agent rollback orchestration without changing the runtime `2.0` Updater wire API. Repository `2.1.1` adds the strict `versionEvidence=unavailable` terminal-failure variant for an explicit rollback whose authoritative Updater version relationship is unavailable; it never permits version guessing or changes the device version projection. Upgraded Agents poll `GET /devices/{deviceId}/command`, require `commandType=update|rollback`, persist an independent rollback command identity, and map it to the original Updater update identity. They advertise `explicit-rollback-v1` during registration; Server gates both rollback creation and delivery on the device's latest successful capability snapshot. See [Explicit rollback orchestration](docs/explicit-rollback-orchestration.md).

`.slamcore_build_manifest.json` is workspace-level internal state owned exclusively by SlamCoreWeb Build Manager. OTA does not define its schema. Updater must never parse, validate, create, mutate, delete, migrate, checkpoint, or rollback it, and deployment must preserve unrelated workspace state.

A release archive uses `SlamCoreWeb/.slamcore-package.json` for strict package metadata. Workspace-root `.slamcore_release` is a different artifact: a one-line SemVer active-release marker written by Updater. It is not included in the ZIP and is never `KEY=VALUE` in Contract 2.0. See the [Integration Specification](docs/SlamCore-OTA-Integration-Spec.md).

## Phase 4 ViaAgent extension

Repository **2.2.0** adds capability-gated Agent topology, immutable single-hop /
branching / N-hop routes, durable routed U/R commands, root-only status sequence,
dedicated history, and structured physical-operation evidence. Runtime remains
**2.0**; all previous schemas and wire semantics are preserved. Every new path
uses Server → Agent(s) → Updater. See [normative contract](docs/phase4-viaagent.md),
[acceptance mapping](docs/phase4-acceptance.md), and
[Phase 4 OpenAPI](openapi/slamcore-phase4-v1.yaml).

## Layout

- `docs/`: integration specification, governance, compatibility, migration, and handoff notes.
- `openapi/`: OpenAPI 3.1 Server and Updater HTTP contracts (the `/api/v1` HTTP generation remains stable).
- `schemas/`: JSON Schema Draft 2020-12 DTO, discriminated device-command, Updater request, and release-package metadata models.
- `examples/`: non-sensitive valid payloads, package metadata, and the active marker.
- `scripts/validate-contracts.py`: local/CI validation, including cross-file Contract 2.0 invariants.

## Versions and compatibility

Repository releases use SemVer (`2.2.0` in `VERSION`); runtime payloads and `X-SlamCore-Contract-Version` remain `2.0`. The `2.1.0` command endpoint is additive, and `2.1.1` is its missing-version-evidence patch: the existing update-only endpoint and normal string-version status remain unchanged. Contract 2.0 itself is breaking from 1.x: 1.x consumers cannot send `building`, parse the former KEY=VALUE `.slamcore_release`, or require the former build manifest. See the [migration section](docs/SlamCore-OTA-Integration-Spec.md#10-1x--20-migration), [rollback rollout](docs/SlamCore-OTA-Integration-Spec.md#11-201--210-explicit-rollback-rollout), and [compatibility matrix](docs/compatibility-matrix.md).

## Validate locally

```bash
python -m pip install -r requirements-dev.txt
python scripts/validate-contracts.py
```

The validator checks every JSON document/schema, examples, OpenAPI references and structure, `VERSION`, the plain-text active marker, and semantic version/state/ownership invariants.

## Consume as a Git submodule

```bash
git submodule add <contract-repository-url> contracts/slamcore-ota
git -C contracts/slamcore-ota checkout <reviewed-contract-commit>
git add contracts/slamcore-ota
git commit -m "chore: 升級至已審查的 OTA Contract 版本"
```

Pin a reviewed commit/tag; never automatically track `main`. Complete 1.x jobs before coordinated migration of Updater, Agent, and Server. Enable rollback command creation only after the device's latest successful registration advertises `explicit-rollback-v1`. Upgrade Server to accept the `2.1.1` unavailable-evidence status before Agent emits it. After merge and CI, a human—not a feature branch—may create a release tag for the reviewed version.

## FAQ

**May a consumer add a private state or DTO field?** No. Propose public behavior here first.

**Does Phase 4 require authenticated peers?** Yes. New routed interfaces require independently authenticated adjacent peers and an authorized Leaf at Updater. This repository defines trust requirements, not authentication/PKI implementation. Package SHA-256 remains mandatory; legacy wire requirements are unchanged.

**May Updater reject an unknown Build Manager manifest?** No. It must not inspect that internal file at all.

**Why can a DTO contain an unknown field?** Legacy runtime DTO schemas allow unknown fields for minor-version forward compatibility. New capability-gated Phase 4 envelopes and release-package metadata are closed to prevent unsigned semantic ambiguity.

**Can an Agent infer rollback from a lower target version or missing package URL?** No. Only `commandType` selects update versus rollback on the upgraded command endpoint; absent or unknown values fail closed.
