# Compatibility matrix

| Contract | Runtime contractVersion | Server | Agent | Updater | Package metadata | Public build state | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| contract-v2.1.1 | `2.0` | accepts unavailable-evidence status only for terminal failed rollback `R`; preserves device version and original `U` | may emit unavailable-evidence status only after Server upgrade and only after definitive permanent failure | no product/wire change | `SlamCoreWeb/.slamcore-package.json` format 2 | none; startup is runtime-internal | Draft patch for explicit-rollback terminal failure without authoritative version evidence |
| contract-v2.1.0 | `2.0` | discriminated `/command` plus registration capability gate required for rollback | discriminated durable command plus `explicit-rollback-v1` advertisement required | existing `POST /rollback` wire behavior compatible; gitlink update required | `SlamCoreWeb/.slamcore-package.json` format 2 | none; startup is runtime-internal | Draft additive explicit-rollback orchestration release |
| contract-v2.0.1 | `2.0` | implemented; main pins `ae3f183…` | implemented; main pins `ae3f183…` | implemented; main pins `ae3f183…` | `SlamCoreWeb/.slamcore-package.json` format 2 | none; startup is runtime-internal | Deployed Contract 2.0 machine-conformance baseline; no Server-orchestrated explicit rollback |
| contract-v2.0.0 | `2.0` | TBD (coordinated upgrade required) | TBD (coordinated upgrade required) | TBD; currently pinned to `2d76fe8…` | `SlamCoreWeb/.slamcore-package.json` format 2 | none; startup is runtime-internal | Initial Draft Contract 2.0 baseline |
| contract-v1.1.0 | `1.1` | TBD | TBD | pinned legacy baseline | ZIP-root `.slamcore_release` KEY=VALUE plus required build manifest | `building` | Legacy; incompatible with 2.0 |
| contract-v1.0.0 | `1.0` | TBD | TBD | TBD | v1 package format | `building` | Legacy |

## Compatibility rules

- Contract 1.x and 2.0 cannot participate in the same in-flight job. Finish or terminate 1.x jobs before upgrading all API participants.
- `/api/v1` remains the HTTP endpoint generation; the header and DTO discriminator select runtime Contract `2.0`.
- A 2.0 Updater validates `.slamcore-package.json`, never a Build Manager manifest, and maintains workspace `.slamcore_release` solely as the active SemVer marker.
- Repository `2.1.0` retains runtime `2.0` because it adds a new endpoint and schema without changing existing endpoint or Updater payload semantics. Rollback commands are never delivered through the legacy update-only endpoint.
- Server and Agent must pin and implement `2.1.0` before rollback command creation is enabled. An upgraded Agent rejects missing or unknown `commandType` values on `/command` and advertises `explicit-rollback-v1` only when its durable rollback path is ready. Server requires that exact token in the device's latest successful registration for both creation and delivery; absent, empty, removed, or unknown capabilities fail closed.
- Repository `2.1.1` keeps normal status payloads and runtime `2.0` unchanged. `versionEvidence=unavailable` requires `failed`, non-null `errorCode`, and both versions null; Server additionally accepts it only for rollback `R`, terminalizes only `R`, and does not change the device version or original `U`.
- The `2.1.1` accepted-payload extension requires Contract → Server → Agent rollout. An Agent must not emit the unavailable-evidence variant to a `2.1.0` Server. Old Agents remain compatible, and Updater plus SlamCoreWeb require no changes.

## Phase 4 supported and fail-closed combinations

“Supported” below is a Contract conformance combination, not a claim that the
consumer implementation or production qualification has passed. Consumers must
pin repository **2.2.0's reviewed commit**; all wire DTOs remain **2.0**.

| Server | Every route Agent | Updater | Outcome |
| --- | --- | --- | --- |
| Legacy Contract 2.0/2.1.x | legacy single Agent | compatible 2.0 | Existing single-hop registration, update, lifecycle/status/history remain supported. Explicit rollback retains its device capability/2.1.1 emission gate. |
| New Server, routed dispatch disabled | legacy Agent | compatible 2.0 | Legacy endpoints remain supported; no routed envelope delivered. |
| New routed Server | all advertise exact Agent-scoped `hierarchical-relay-v1` | exact `physical-operation-evidence-v1`, runtime 2.0 | New routed single-hop, branching and N-hop update supported after complete migration/conformance. |
| New routed Server | same as above, device has latest `explicit-rollback-v1` | same as above | R→U supported; original successful U route retained, one R per U. |
| New routed Server | only `explicit-rollback-v1`, missing/removed/unknown hierarchy token | any | Fail closed for routed creation/delivery; no hierarchy inference or fallback. |
| New routed Server | fully capable hierarchy | missing evidence capability / unknown Updater wire version | Fail closed for new Phase 4 dispatch. Existing accepted 2.0 work keeps its recovery obligations. |
| Old Server | new Agents | any | Use legacy interface only where explicitly configured for existing single-hop deployment; do not send new DTOs to old Server or silently downgrade a multi-hop command. |
| Any | any Agent missing durable migration/authorization, ambiguous legacy attachment or unknown runtime version | any | Fail closed before new acceptance/forwarding. |
| New routed Server | current capability removal or route no longer authorized after acceptance | any | No reroute. Preserve original obligations/evidence; uncertainty must reconcile, not falsely terminalize. |

Upgrade order and explicit migration evidence are normative in
[Phase 4 sections 3, 6 and 9](phase4-viaagent.md). Pure relay Agents with no devices
register the same Agent-scoped capability; device registration never substitutes
for an Agent node. No DirectUpdater compatibility is supported.

### Consumer conformance handoff

| Owner | Required implementation evidence |
| --- | --- |
| [Server #8](https://github.com/EricChen3016/SlamCore-Server/issues/8) | Retained topology/route revisions and migration; exact-capability feed gating; U/R and per-device isolation; immutable receipts; stale/gap/late status; dedicated history and complete projected evidence reads. |
| [Agent #9](https://github.com/EricChen3016/SlamCore-Agent/issues/9) | Authenticated immediate-neighbor checks; write-before-ack/forward; exact U/R and fingerprint; root/relay/leaf restart; query-before-replay including 404; root-only sequence; original source evidence retention and projection. |
| [Updater #55](https://github.com/EricChen3016/SlamCore-Updater/issues/55) | Authorized Leaf only; unchanged U-only mutation engine; durable ordinal/phase and execution uncertainty; structured raw reads; source journal/marker/symlink/runtime linkage; no retries fabricating physical counts. |
| [Server #18](https://github.com/EricChen3016/SlamCore-Server/issues/18) | Fixed consumer/Contract/package SHAs/digests; real Windows/Jetson single-hop/branching/N-hop U/R, restart/outage/response loss; capture completeness and independently verified physical counts; security/runbook/go-no-go. |

Every consumer must run legacy 2.0 regressions plus the positive and exact-reason
negative fixtures and reproduce the three route hash vectors in its native
language. New-contract tests alone do not prove consumer persistence or HIL.
Historical TBD rows above document old release status only and are not unfinished
Phase 4 requirements.
