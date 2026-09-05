# Compatibility matrix

| Contract | Runtime contractVersion | Server | Agent | Updater | Package metadata | Public build state | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| contract-v2.1.0 | `2.0` | discriminated `/command` implementation required for rollback | discriminated durable command implementation required for rollback | existing `POST /rollback` wire behavior compatible; gitlink update required | `SlamCoreWeb/.slamcore-package.json` format 2 | none; startup is runtime-internal | Draft additive explicit-rollback orchestration release |
| contract-v2.0.1 | `2.0` | implemented; main pins `ae3f183…` | implemented; main pins `ae3f183…` | implemented; main pins `ae3f183…` | `SlamCoreWeb/.slamcore-package.json` format 2 | none; startup is runtime-internal | Deployed Contract 2.0 machine-conformance baseline; no Server-orchestrated explicit rollback |
| contract-v2.0.0 | `2.0` | TBD (coordinated upgrade required) | TBD (coordinated upgrade required) | TBD; currently pinned to `2d76fe8…` | `SlamCoreWeb/.slamcore-package.json` format 2 | none; startup is runtime-internal | Initial Draft Contract 2.0 baseline |
| contract-v1.1.0 | `1.1` | TBD | TBD | pinned legacy baseline | ZIP-root `.slamcore_release` KEY=VALUE plus required build manifest | `building` | Legacy; incompatible with 2.0 |
| contract-v1.0.0 | `1.0` | TBD | TBD | TBD | v1 package format | `building` | Legacy |

## Compatibility rules

- Contract 1.x and 2.0 cannot participate in the same in-flight job. Finish or terminate 1.x jobs before upgrading all API participants.
- `/api/v1` remains the HTTP endpoint generation; the header and DTO discriminator select runtime Contract `2.0`.
- A 2.0 Updater validates `.slamcore-package.json`, never a Build Manager manifest, and maintains workspace `.slamcore_release` solely as the active SemVer marker.
- Repository `2.1.0` retains runtime `2.0` because it adds a new endpoint and schema without changing existing endpoint or Updater payload semantics. Rollback commands are never delivered through the legacy update-only endpoint.
- Server and Agent must pin and implement `2.1.0` before rollback command creation is enabled. An upgraded Agent rejects missing or unknown `commandType` values on `/command`.
