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

### Terminal failure without authoritative version evidence

Contract `2.1.0` required a permanent failure such as a missing original `U` or
missing retained release to terminalize `R`, while the Agent-to-Server status
schema required both version fields to be strings. When Updater has lost the
entire `U` journal, it cannot provide an authoritative version relationship.
Consequently, no Contract-valid terminal status existed without fabricating
versions. Fabrication is prohibited: Agent must not infer either version from a
package name, Server command target, `Device.currentReleaseVersion`, local
historical `U` row, or any other heuristic. Updater remains the rollback-target
authority.

Normal status payloads are unchanged: `fromVersion` and `targetVersion` are both
strings and `versionEvidence` is absent. The only missing-evidence representation
is this mutually exclusive variant:

```json
{
  "contractVersion": "2.0",
  "state": "failed",
  "progressPercent": 0,
  "message": "Original Updater journal is unavailable.",
  "errorCode": "RESOURCE_NOT_FOUND",
  "fromVersion": null,
  "targetVersion": null,
  "versionEvidence": "unavailable",
  "observedAtUtc": "2026-09-06T03:00:00Z",
  "sequence": 0
}
```

Both version fields remain required and must be null together. Null is legal
only when `state=failed`, `errorCode` is a non-null valid code, and
`versionEvidence=unavailable`. It is invalid for `completed`, `rolled_back`,
`rolling_back`, either one-sided-null form, or any update success/failure with
missing evidence.

JSON Schema cannot determine whether the status key references update `U` or
explicit rollback `R`. Server therefore MUST apply a contextual invariant: when
`versionEvidence=unavailable`, the job referenced by
`status:<jobId>:<sequence>` MUST be an explicit rollback `R` and the state MUST
be `failed`; otherwise Server returns `400 VALIDATION_FAILED`. This status and
its idempotency identity remain scoped to `R`; it MUST NOT terminalize or mutate
the original `U`. Any presentation or audit relationship to that successful
update MUST use the existing `R.originalUpdateJobId=U` association rather than
overwriting `U` or reusing its identity as the status scope.

`versionEvidence=unavailable` means only that rollback failed permanently and
the authoritative version pair cannot be reported. It does **not** mean rollback
succeeded. Server terminalizes `R` as failed and MUST preserve its existing
device current-version projection because there is no evidence that the runtime
switched versions. Specifically, Server MUST NOT update
`Device.currentReleaseVersion`; it MUST NOT assume that either the previous or
attempted version is active or that rollback succeeded.

## Failure semantics

| Condition | Contract result | Retryable | Terminal for R |
| --- | --- | --- | --- |
| `U` does not exist or belongs to another device | `404 RESOURCE_NOT_FOUND` | no | yes |
| `U` was not a successful update | `404 RESOURCE_NOT_FOUND` | no | yes |
| No retained previous release exists for `U` | `404 RESOURCE_NOT_FOUND` | no | yes |
| The same `U` was already rolled back | idempotent replay of the same rollback result | no new operation | existing terminal result |
| The same `R` is delivered again | same immutable command | yes | unchanged |
| Rollback for the same `U` is already active | recover and track the same `R`, `U`, and `rollback:U` | yes | unchanged |
| The same `rollback:U` key has a different body | `409 IDEMPOTENCY_CONFLICT` | no | yes |
| Another deployment mutation is active | `409 UPDATE_ALREADY_RUNNING` | no automatic retry | no operation started |
| Device lacks `explicit-rollback-v1` | reject creation, or withhold a previously pending `R` until capability returns or expiry | after capable registration | no operation started |
| `R` expires before its first Updater submission | terminal `failed` with `COMMAND_EXPIRED`; no Updater call | no | yes |
| Updater/transport is temporarily unavailable | `503 DEPENDENCY_UNAVAILABLE` or transport failure | yes | no |
| Rollback exceeds its health window | terminal `failed`, normally `OPERATION_TIMEOUT` | no automatic new operation | yes |
| Previous runtime remains unhealthy after rollback | terminal `failed` with an implementation error code | no automatic new operation | yes |
| Agent restarts during rollback | recover `R`/`U`, query `U`, then track or exact-replay | yes | unchanged |
| Server is temporarily unavailable | retain and replay the exact `status:R:<sequence>` outbox item | yes | unchanged locally |
| `commandType` is absent/unknown or variant fields contradict it | `400 VALIDATION_FAILED` or local Agent rejection before persistence/mutation | no | no operation started |

Permanent pre-submission rejections are reported as terminal failure for `R`.
Terminal failure does not authorize a second rollback command for the same `U`:
`rollback:U` continues to identify the existing Updater result. An operator must
remediate the failed operation explicitly; transport retry logic never allocates
a new `R`.

The unavailable-evidence variant is eligible only when Agent has a definitive
permanent outcome but no authoritative Updater version pair. Examples include:

- `GET /update/U` returns `404`, then an exact `POST /rollback` or replay returns
  permanent `404 RESOURCE_NOT_FOUND` because the original journal is absent;
- Updater permanently rejects rollback with `RESOURCE_NOT_FOUND` because the
  retained previous release is unavailable and no queryable journal supplies
  the version relationship; or
- another Contract-defined permanent rollback rejection is received while the
  authoritative journal relationship is unavailable.

A `404` query by itself is never sufficient to terminalize `R` after submission
may have occurred. Timeout, connection reset, lost response, `503`, and temporary
Updater unavailability leave mutation acceptance uncertain; `R` stays Unknown
and Agent must query or exact-replay the same `rollback:U` operation. If a
rollback acceptance response is lost, later `GET /update/U` observations of
`rolling_back` or `rolled_back` continue the existing recovery path. The new
variant does not change response-loss semantics.

For a never-submitted `R` that has expired, Agent performs no Updater mutation
and reports terminal `failed` with `COMMAND_EXPIRED`. It uses the normal string
pair if trustworthy evidence is already available; otherwise it may use
`versionEvidence=unavailable` with both version fields null. Server still
preserves the device version projection and original `U`.

## Compatibility and rollout

This is an additive Contract 2.0 extension, so repository SemVer advances from
`2.0.1` to `2.1.0` while wire `contractVersion` stays `2.0`. No existing field,
endpoint, update state, or Updater request changes meaning.

Repository `2.1.1` is a patch correction to the `2.1.0` explicit-rollback
feature: it adds the accepted missing-evidence failure variant without changing
normal status payloads or runtime `contractVersion=2.0`. Because an old Server
does not accept this variant, rollout is coordinated in this order:

1. Merge and review Contract `2.1.1`.
2. Upgrade Server to accept the structural variant, enforce the `R`-only
   contextual rule, and preserve the device version projection.
3. Only then upgrade/enable Agent emission of the variant.

Until Server is upgraded, Agent MUST NOT emit `versionEvidence=unavailable`.
Old Agents remain compatible because normal string-version status is unchanged.
Updater wire behavior and product code do not change.

### Capability gate

An Agent that has completed its discriminated-command and durable `R`/`U`
implementation advertises `explicit-rollback-v1` in the optional registration
`capabilities` array. The array is the Agent's complete current capability set,
not a patch: each successfully accepted registration replaces the capability
set stored for that device. An absent or empty array means no optional
capability. Unknown tokens never imply explicit rollback support.

Server must require the exact `explicit-rollback-v1` token in the device's most
recent successful registration both when creating `R` and when returning a
rollback from `/devices/{deviceId}/command`. `agentVersion`, runtime
`contractVersion: 2.0`, use of `/command`, and an operator feature flag are not
substitutes for this device-level capability. A feature flag may impose an
additional restriction.

If a newer registration removes the token while `R` is still pending, Server
withholds the command; it does not fall back to `/update`. The pending command
may be delivered after a capable registration returns, provided it has not
expired; otherwise normal expiry applies. An Agent advertises the token only
after its schema validation, durable storage migration, dispatch, and recovery
paths are ready.

Rollout order:

1. Merge and tag this Contract repository release.
2. Upgrade Server to persist registration capability snapshots and implement
   storage plus `/command`; keep `/update` update-only and rollback creation
   disabled without the capability.
3. Upgrade Agent and switch its polling to `/command` only after it can validate
   both command variants, durably recover rollback, and advertise
   `explicit-rollback-v1`.
4. Verify the device's most recent successful registration contains the token.
5. Enable rollback command creation, still enforcing the per-device capability
   check on creation and delivery.

An old Agent cannot receive rollback from the legacy endpoint. If rollback JSON
is nevertheless delivered to an old update deserializer, its absent required
package fields must fail validation before persistence or Updater mutation.
Unknown `commandType` values always fail closed.

## Consumer impact

For the `2.1.1` missing-evidence correction specifically:

- **SlamCore-Server:** update `ContractDeviceStatusRequest`, its JSON converter,
  schema/status validation, rollback-context validation, and device-version
  projection. Add tests proving `R failed + unavailable` is accepted and
  terminal while the device version and original `U` remain unchanged, and that
  the same payload for `U` is `400 VALIDATION_FAILED`. Update the Contract
  gitlink after review.
- **SlamCore-Agent:** allow nullable versions only in the special status model
  variant, serialize `versionEvidence=unavailable`, map definitive permanent
  rollback rejection—including the journal-missing case—and evidence-free
  `COMMAND_EXPIRED`, and add schema, persistence/outbox exact-replay, and mapping
  tests. Do not emit before Server is upgraded. Update the Contract gitlink
  after review.
- **SlamCore-Updater:** no product change and no wire-contract change.
- **SlamCoreWeb:** no change.

### SlamCore-Server

- Extend `ContractRegistrationRequest`, `DeviceRegistrationAttempt`, `Device`,
  registration receipt/storage, and EF persistence with the complete capability
  snapshot. Every successful registration replaces the previous set and feeds
  both rollback creation and delivery gates.
- Extend `UpdateJob` and its EF configuration/migration with `commandType` plus
  nullable `originalUpdateJobId`; enforce variant constraints and one `R` per
  `U`. Update `CreateUpdateJobRequest`/`UpdateJobResponse` and add an explicit
  rollback creation DTO/use case that validates original job success, same
  device, rollbackability, uniqueness, active-command exclusion, and the latest
  successful registration's `explicit-rollback-v1` capability.
- Extend `DevicesController` with
  `GET /api/v1/devices/{deviceId}/command`; preserve its existing `/update`
  action as update-only. Extend `UpdateJobsController` only for the explicit
  rollback management operation.
- Serialize update and rollback variants exactly as the schema defines.
- Map `rolled_back` to success for `R`, but preserve its existing failed-update
  meaning for `U`.
- Extend `PendingCommandTests`, `Contract2CommandSnapshotTests`,
  `ExpiredUpdateJobLifecycleTests`, `StatusIngestTests`, and
  `ContractHistoryTests`; add registration capability replacement,
  rollback creation/idempotency/concurrency, capability removal, and
  creation/delivery gate tests.

### SlamCore-Agent

- Extend `ServerRegistrationRequest` and its durable serialized payload and
  fingerprint with `capabilities`; advertise `explicit-rollback-v1` only after
  the whole rollback implementation is active.
- Replace `AvailableUpdate` and `IServerClient.GetAvailableUpdateAsync` with a
  discriminated command model/client call to `/command`.
- Retain the legacy `/update` client during coordinated migration if needed.
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
