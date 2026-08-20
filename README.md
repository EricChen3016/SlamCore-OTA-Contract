# SlamCore OTA Contract

The authoritative, machine-verifiable cross-project contract for **SlamCore Server**, **SlamCore Agent**, and **SlamCore Updater**. Server schedules releases, Agent coordinates a device, and Updater validates and applies packages. This repository contains contracts only—no product runtime.

## Layout

- `docs/`: integration specification, governance, compatibility, and handoff notes.
- `openapi/`: OpenAPI 3.1 Server and Updater HTTP contracts.
- `schemas/`: JSON Schema Draft 2020-12 DTO and release models.
- `examples/`: non-sensitive valid payloads and release metadata.
- `scripts/validate-contracts.py`: local/CI contract validation.

## Versions and compatibility

Repository releases use SemVer (`1.0.0` in `VERSION`); runtime payloads and `X-SlamCore-Contract-Version` use major/minor (`1.0`). Compatible additions increment minor, fixes increment patch, and breaking API/DTO/state/release-format changes increment major. See the [governance ADR](docs/decisions/ADR-0001-contract-governance.md).

## Validate locally

```bash
python -m pip install -r requirements-dev.txt
python scripts/validate-contracts.py
```

The `.slamcore_release` artifact is UTF-8 `KEY=VALUE` text. `schemas/release/slamcore-release.schema.json` validates its **parsed data model**; the validator separately parses and validates the actual text example.

## Consume as a Git submodule

```bash
git submodule add -b contract-v1.0.0 <contract-repository-url> contracts/slamcore-ota
git submodule update --init --recursive
```

Pin the submodule to a reviewed commit/tag; never automatically track `main`. To upgrade:

```bash
git -C contracts/slamcore-ota fetch --tags
git -C contracts/slamcore-ota checkout contract-v1.0.0
git add contracts/slamcore-ota
git commit -m "chore: upgrade SlamCore OTA contract"
```

For a breaking change, first update this repository, increment the major version, update all artifacts and compatibility notes, obtain cross-project review, and then upgrade each consumer explicitly.

After the release change is merged and CI passes, a human may create a tag:

```bash
git tag -a contract-v1.0.0 -m "SlamCore OTA contract v1.0.0"
git push origin contract-v1.0.0
```

## FAQ

**May a consumer add a private state or DTO field?** No. Propose it here first.

**Does v1 require TLS or authentication?** No; deployments currently use trusted internal HTTP. Package SHA-256 verification remains mandatory.

**Why did a payload with an unknown field validate?** Runtime DTO schemas intentionally accept unknown fields for minor-version forward compatibility; release manifests remain strict.
