# Explicit rollback orchestration

## Decision

Contract repository release `2.1.0` adds a backward-compatible Server-to-Agent
command endpoint while keeping runtime `contractVersion` at `2.0`:

- `GET /devices/{deviceId}/update` remains the Contract 2.0 update-only endpoint.
  It never returns rollback commands.
- `GET /devices/{deviceId}/command` is the upgraded endpoint. Every `200`
  response has the required `commandType` discriminator `update` or `rollback`.
- A consumer must reject an absent or unknown discriminator on the upgraded
  endpoint. It must never infer the command type from versions or package fields.

The new endpoint avoids making a new field required on the existing endpoint.
Existing Agents can continue normal update processing while Server and Agent
roll out explicit rollback support together. Server must withhold rollback from
the legacy endpoint.

## Command model

### Update

An update command has `commandType: update`. Its Server-owned `jobId` is the
logical update identity `U` and is passed unchanged to Updater `POST /update`.
It requires `deviceId`, `targetVersion`, `packageUrl`, `packageSha256`,
`platform`, `createdAtUtc`, and `expiresAtUtc`. It must not contain
`originalUpdateJobId`.

### Rollback

An explicit rollback command has `commandType: rollback`. It has:

- `jobId`: the independent Server rollback-command identity `R`;
- `deviceId`: the device to which both `R` and the original update belong;
- `originalUpdateJobId`: the successful update identity `U` whose retained
  previous release is requested;
- `createdAtUtc` and `expiresAtUtc`: the rollback command delivery window.

Rollback does not carry `targetVersion`, `packageUrl`, `packageSha256`, or
`platform`. Empty strings are not substitutes. Updater is authoritative for the
rollback target: it resolves the durable `fromVersion` recorded for `U` and
verifies that the release is still retained.

Server must create at most one logical rollback command `R` for a given `U`.
Repeated management retries return the same `R`; they must not allocate a new
rollback command.

## Identity mapping

```text
Server
  commandType = rollback
  rollback command jobId = R
  originalUpdateJobId = U

        ↓

Agent
  durable command identity = R
  durable original update identity = U
  status/outbox scope = R

        ↓

Updater POST /rollback
  body.jobId = U
  Idempotency-Key = rollback:U
  accepted/status jobId = U
  GET /update/U
```

`R` is the central orchestration/audit identity. `U` is the existing Updater
journal identity. Agent validates an Updater acceptance response against `U`,
but reports rollback observations to Server under `R` using
`status:R:<sequence>`.

## Idempotency and recovery

Before the first Updater mutation, Agent atomically persists the complete
rollback command, including `R`, `U`, timestamps, and submission state. It then
sends the exact rollback request above.

`expiresAtUtc` gates only an operation that has never been submitted. Server
must not deliver a command at or after expiry. Agent independently checks the
deadline before its first `POST /rollback`; an already-expired command is not
sent to Updater and is reported as terminal `failed` with
`COMMAND_EXPIRED`. Once submission may have occurred, expiry does not cancel or
replace the operation: response-loss and restart recovery still query `U` and,
when required, replay the exact request. This prevents an accepted rollback from
being abandoned merely because its delivery window elapsed.

Server polling retries always return the same immutable `R` and `U`. Agent
restart, HTTP response loss, and Updater restart must not allocate either ID
again. Recovery follows this rule:

1. Load durable `R` and `U`; do not poll for or accept a second command.
2. Query `GET /update/U`.
3. If the current operation is visibly `rolling_back`, `rolled_back`, or a
   terminal rollback `failed`, resume tracking it.
4. If the response is still the original successful `completed` update, or the
   query returns `404`, replay the exact `POST /rollback` with
   `Idempotency-Key: rollback:U`.
5. A replay with the same body returns the same Updater operation. A different
   body under that key is `409 IDEMPOTENCY_CONFLICT`.

Status delivery to Server is separately idempotent and remains scoped to `R`.
The first distinct durable rollback observation uses sequence `0`; retries reuse
the exact body, sequence, and key.

## State and terminal mapping

No public state is added. Explicit rollback reuses the existing subset:

```text
queued → rolling_back → rolled_back
                     ↘ failed
```

Implementations may omit an instantaneous `queued` observation. `rolling_back`
is active. For command `R`, `rolled_back` is terminal success and maps to the
Server compatibility state `Completed`/successful. `failed` is terminal failure.

For an update command `U`, the existing meaning is unchanged: `completed` is
terminal success, while `rolled_back` means the update failed after activation
and automatic rollback restored the previous runtime. Server therefore maps
`rolled_back` according to the command type, not as one global compatibility
result.

The rollback status `fromVersion` is the release active before rollback
(normally the successful update target), and `targetVersion` is the retained
previous release selected by Updater. Server validates that relationship against
the immutable original update evidence.

## Failure semantics

| Condition | Contract result | Retryable | Terminal for R |
| --- | --- | --- | --- |
| `U` does not exist or belongs to another device | `404 RESOURCE_NOT_FOUND` | no | yes |
| `U` was not a successful update or no retained previous release exists | `404 RESOURCE_NOT_FOUND` | no | yes |
| The same `U` was already rolled back | idempotent replay of the same rollback result | no new operation | existing terminal result |
| The same `R` is delivered again | same immutable command | yes | unchanged |
| The same `rollback:U` key has a different body | `409 IDEMPOTENCY_CONFLICT` | no | yes |
| Another deployment mutation is active | `409 UPDATE_ALREADY_RUNNING` | no automatic retry | no operation started |
| `R` expires before its first Updater submission | terminal `failed` with `COMMAND_EXPIRED`; no Updater call | no | yes |
| Updater/transport is temporarily unavailable | `503 DEPENDENCY_UNAVAILABLE` or transport failure | yes | no |
| Rollback exceeds its health window | terminal `failed`, normally `OPERATION_TIMEOUT` | no automatic new operation | yes |
| Previous runtime remains unhealthy after rollback | terminal `failed` with an implementation error code | no automatic new operation | yes |
| Agent restarts during rollback | recover `R`/`U`, query `U`, then track or exact-replay | yes | unchanged |
| Server is temporarily unavailable | retain and replay the exact `status:R:<sequence>` outbox item | yes | unchanged locally |

Permanent pre-submission rejections are reported as terminal failure for `R`.
Terminal failure does not authorize a second rollback command for the same `U`:
`rollback:U` continues to identify the existing Updater result. An operator must
remediate the failed operation explicitly; transport retry logic never allocates
a new `R`.

## Compatibility and rollout

This is an additive Contract 2.0 extension, so repository SemVer advances from
`2.0.1` to `2.1.0` while wire `contractVersion` stays `2.0`. No existing field,
endpoint, update state, or Updater request changes meaning.

Rollout order:

1. Merge and tag this Contract repository release.
2. Upgrade Server and implement storage plus `/command`; keep `/update`
   update-only.
3. Upgrade Agent and switch its polling to `/command` only after it can validate
   both command variants and durably recover rollback.
4. Enable creation of rollback commands after compatible Server and Agent are
   deployed.

An old Agent cannot receive rollback from the legacy endpoint. If rollback JSON
is nevertheless delivered to an old update deserializer, its absent required
package fields must fail validation before persistence or Updater mutation.
Unknown `commandType` values always fail closed.

## Consumer impact

### SlamCore-Server

- Extend `UpdateJob` and its EF configuration/migration with `commandType` plus
  nullable `originalUpdateJobId`; enforce variant constraints and one `R` per
  `U`. Update `CreateUpdateJobRequest`/`UpdateJobResponse` and add an explicit
  rollback creation DTO/use case that validates original job success, same
  device, rollbackability, uniqueness, and active-command exclusion.
- Extend `DevicesController` with
  `GET /api/v1/devices/{deviceId}/command`; preserve its existing `/update`
  action as update-only. Extend `UpdateJobsController` only for the explicit
  rollback management operation.
- Serialize update and rollback variants exactly as the schema defines.
- Map `rolled_back` to success for `R`, but preserve its existing failed-update
  meaning for `U`.
- Extend `PendingCommandTests`, `Contract2CommandSnapshotTests`,
  `ExpiredUpdateJobLifecycleTests`, `StatusIngestTests`, and
  `ContractHistoryTests`; add rollback creation/idempotency/concurrency tests.

### SlamCore-Agent

- Replace `AvailableUpdate` and `IServerClient.GetAvailableUpdateAsync` with a
  discriminated command model/client call to `/command`.
- Migrate `SqliteAgentRepository`'s `UpdateJob` table and the core `UpdateJob`
  model to persist `commandType` plus `originalUpdateJobId`; package fields are
  nullable only for rollback rows and protected by variant constraints.
- Branch `UpdateCoordinator` dispatch explicitly: update calls
  `IJetsonClient.StartUpdateAsync` with `U`; rollback calls the already-present
  `IJetsonClient.RollbackAsync`/`JetsonClient.RollbackAsync` with `U` while
  retaining `R` locally.
- Validate Updater acceptance/status identity against `U`, while Server status
  `StatusOutbox` identity and sequence remain scoped to `R`.
- Extend `HttpClientTests`, `SqliteAgentRepositoryTests`,
  `UpdateCoordinatorTests`, and `StatusOutboxDispatcherTests` with restart,
  response-loss, exact replay, expiry, unknown discriminator, contradictory
  payload, terminal projection, and Server-outage cases.

### SlamCore-Updater

No product code change is required. Current Contract 2.0 behavior already uses
body `jobId=U`, `Idempotency-Key=rollback:U`, resolves the retained previous
release from `U`, exposes rollback state through `GET /update/U`, and replays the
same operation idempotently. Its Contract gitlink and conformance evidence still
need updating after this Contract change is reviewed.

### SlamCoreWeb

No change.
