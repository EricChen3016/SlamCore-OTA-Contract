# Phase 4 ViaAgent contract — normative

Repository **2.2.0**, runtime **2.0**. The only command path is:

```text
Server → A1 → … → An → Updater       1 ≤ n ≤ 32
```

This document and `schemas/phase4/` freeze the additive protocol. The new
`openapi/slamcore-phase4-v1.yaml` describes host ownership for each operation.
MUST/MUST NOT are requirements. Existing Contract 2.0 APIs remain available,
with unchanged DTOs, required headers, states, lifecycle, ownership and replay
semantics. The new interfaces live at `/api/v1/phase4` on the owning host.
No `deploymentMode` field is introduced. DirectUpdater is unsupported; there
is no Server-to-Updater mutation, status ingress, adapter or fallback.

## 1. Authority, identity and version decision

Server owns inventory, accepted topology revisions, device attachments, route
snapshots, logical jobs and history. An Agent owns durable local relay
obligations; Updater owns device-local U, version evidence and physical journal.
`AgentId`, `DeviceId` and `JobId` are distinct identities; equal strings across
these three domains MUST be rejected. UpdaterId is a separate stable inventory
identity; it is not a URL, DeviceId, or a replacement for U. Server identity is
explicit in the snapshot, preventing an ambiguous first hop in a forest.

For update, `serverCommandJobId = updaterJobId = U` and
`originalUpdateJobId = null`. Every Agent and Updater retains U. For rollback,
`serverCommandJobId = R`, `originalUpdateJobId = updaterJobId = U`, and R differs
from U. At most one logical R exists per U, including permanently failed R.
Creation requires the original successful U on the same device and its retained
rollbackable release. Existing per-device active-job protection applies;
sharing an Agent does not introduce a global deployment lock.

A breaking change would require a new major version under ADR-0001. This is a
minor release because new DTOs/endpoints are capability-gated and **no existing
field meaning or responsibility changes**. Root sequence ownership applies to
new routed jobs only. The legacy single Agent remains its existing sequence
owner. The dedicated new history page fixes the R/U and unavailable-evidence
representation gap without extending the legacy `UpdateStatus[]` response.
The additive runtime-2.0 precedent is repository 2.1.0.


This Draft's firstSubmissionRejected correction adds an accepted status/proof branch
only to the unpublished Phase 4 endpoints. Under AGENTS.md, an accepted-value addition
is additive/minor, not a patch-only semantic rewrite. It is included in the existing
unreleased 2.2.0 minor delivery relative to released 2.1.1; it does not remove or narrow
any previously valid legacy DTO or change runtime 2.0. Intermediate Draft commit pins
are not automatically compatible: consumers must coordinate the reviewed SHA and
Server-before-Agent rollout in the compatibility matrix before emitting this branch.

## 2. Observation versus accepted topology

`agent-observation.schema.json` is Agent-scoped registration/heartbeat evidence:
stable `observationEventId`, the complete current Agent capability set, direct
parent observation, direct child IDs, direct device attachments and observation
time/revision. Zero children and zero devices are valid (example A4).
The authenticated origin must equal `agent.agentId`. An Agent may report only
its own immediate neighbors. Duplicate attachments or self-neighbor observations
are invalid. Endpoint existence, reachability, `agentVersion`, and an online
flag never establish attachment or capability.

An Agent may send its own authenticated observation to Server. If deployment
requires observation relay, each parent must durably retain the original
observation and authenticated originating identity, then use the same event key
when forwarding through the configured ancestry. Transport must preserve
verifiable original identity; a parent claiming a child identity in JSON is
insufficient. If end-to-end origin cannot be authenticated, forwarded observation
is rejected; use direct authenticated registration. This does not authorize a
command path that bypasses any Agent.

`topology.schema.json` is a Server-owned accepted revision. Parent links form a
rooted tree/forest: a child appears in at most one link, all endpoints exist,
no cycle, no orphan, unique Agent IDs. A device has exactly one attachment and
an Updater has one device attachment. An Agent may attach devices **and** have
children; “Leaf” is a role for a particular route, not a globally childless node.
Device registration capability evidence remains device-scoped; the exact
`explicit-rollback-v1` token retains its existing meaning.

Registration is observation, not configuration authority. Server must serialize
acceptance, validate authorization and revision, and durably retain receipt and
new accepted revision before ack. Same event/key + same original body returns
the receipt; altered body conflicts. Old observations may be retained as audit
facts but MUST NOT replace newer accepted authority. Only authorized control
plane changes parent/attachment authority. This Contract defines no public
unauthorized topology-write endpoint, database, discovery or PKI implementation.

## 3. Route snapshot and canonical SHA-256

`route-snapshot.schema.json` requires routeId, routeVersion, routeSnapshotHash,
topologyVersion, serverId, targetDeviceId, targetUpdaterId, orderedAgentIds,
capabilitySnapshot and createdAtUtc. Ordered IDs are Root → Leaf, 1..32 unique
entries. Root and Leaf are derived as the first and last IDs. Capability entries
are in the same order and contain exact Agent registration evidence; device and
Updater evidence are also captured. Device capability is distinct from Agent
hierarchical capability. No secrets, credentials, endpoint URLs, bearer tokens,
or signed download URLs are permitted in the snapshot.

Server resolves the unique chain from the accepted device attachment to a root,
validates capabilities, computes the hash, and durably commits it with the job
before dispatch. Agents may verify the hash, but MUST NOT replace, recompute into
an accepted identity, reorder, skip, append, reroute or select an alternate path.
R uses the **byte-equivalent semantic snapshot of original U**, including route
ID, timestamps, capability registration identities and hash; R does not create
a refreshed route. Retained authority revisions must remain queryable internally
for verification even after the current topology changes.

Canonical algorithm `route-json-ascii-sha256-v1`:

1. Validate the complete closed route schema; reject duplicate JSON object keys
   before parsing. Remove only top-level `routeSnapshotHash`.
2. All keys/string values in this object must be printable ASCII U+0020..U+007E.
   Integers are 1..2147483647 where required; floats/exponents are invalid.
   No Unicode normalization, platform locale or URL normalization occurs.
3. Recursively sort object keys by ascending ASCII code units. Preserve array
   order, including capabilities (producers sort capability tokens ascending
   before freezing a snapshot; consumers never sort received arrays).
4. Serialize compact JSON without whitespace or BOM: ASCII decimal integers,
   standard lowercase `true`/`false`/`null`, `\"` for quotation and `\\` for
   backslash; leave `/` and every other permitted ASCII character unescaped.
   Timestamp spelling is exactly `YYYY-MM-DDTHH:mm:ssZ` with no fractions.
5. SHA-256 over these ASCII/UTF-8 bytes, encoded as 64 lowercase hex digits.

`examples/phase4/hash-vectors.json` contains exact canonical strings and digests
for single-hop, branching and N-hop; consumers must reproduce these vectors in
their own language. `scripts/phase4_contract.py` is a pure conformance utility,
not a route planner or consumer implementation.

## 4. Correlation, hop indexing and authenticated adjacency

Server assigns a lowercase UUID `operationCorrelationId` independently for each
U and R. R's correlation differs from U; originalUpdateJobId links them. This
identity is immutable across retry, restart, command, status and history.
`X-Correlation-Id` remains a UUID for one HTTP hop/attempt. Attempts may choose a
new value. Valid UUID lowercase, uppercase and mixed-case spellings are accepted.
ErrorResponse.correlationId MUST echo the triggering valid header's exact string,
without lowercasing or any other normalization. Both header and error correlation
schemas require the same canonical 36-character hexadecimal 8-4-4-4-12 UUID structure,
in either letter case, as well as UUID format. The structural pattern and length
bound remain enforced when a JSON Schema validator treats format only as annotation;
extra/misplaced hyphens, trailing whitespace and arbitrary strings are invalid. If the header is absent
or malformed, the service generates a diagnostic UUID because no valid echo exists.
This attempt-header rule does not change canonical lowercase operationCorrelationId,
route/hop hashes or replay fingerprints. Correlation never substitutes for a job ID,
idempotency key or sequence. The [Issue #5 architecture decision](https://github.com/EricChen3016/SlamCore-OTA-Contract/issues/5#issuecomment-5696925708)
records this spelling/echo requirement.

For `[A1,A2,A3]`, the immutable edge indexes are:

| Index | Downstream | Upstream |
| --- | --- | --- |
| 0 | Server → A1 | A1 → Server |
| 1 | A1 → A2 | A2 → A1 |
| 2 | A2 → A3 | A3 → A2 |
| 3 | A3 → Updater | Updater → A3 (leaf-local evidence only) |

Index is always the Root-to-Leaf edge number, **not** the traversal counter.
Direction changes the endpoints; neither index nor route changes.
`hopId = SHA256(canonical({serverCommandJobId, hopIndex, direction, senderKind,
senderId, receiverKind, receiverId, routeSnapshotHash}))`, using section 3's
serialization. It is stable for that directional logical edge across retries.
Leaf-local Updater edge context is retained by Leaf; it is not injected into the
old Updater mutation body or raw status. Every routed status sender is an Agent.

Receiver independently authenticates the transport principal, verifies its own
identity, and compares both to the immediate snapshot neighbors and configured
local trust/attachment. A body claiming the correct peer is not authorization.
Reject wrong root, wrong leaf, wrong caller, wrong receiver, non-neighbor, loop,
duplicate ID, empty route and overflow before any durable acceptance or downstream
mutation. A diagnostic security audit record is not an acceptance receipt.

## 5. Commands, acquisition and leaf projection

Server's Agent-oriented feed returns only jobs whose first snapshot ID equals
the authenticated requesting Agent. GET does not allocate identity or acknowledge
acceptance. Repeat GET and restart retain the command exactly. Page cursors fix
a read watermark and stable keyset order; expired never-submitted commands are
not dispatched. A pure relay Root is valid. A feed can include independent jobs
for several devices; sibling outage does not corrupt their identities.

All Agents save the complete command, R/U mapping, command fingerprint, immutable
route, resolved immediate endpoint/peer evidence, stable logical hop, expiry,
submission uncertainty and downstream obligation atomically **before both ack and
forward**. Persist endpoint resolution outside public route snapshots; never
expose credentials. At the next Agent the payload and semantic fingerprint remain
the same; only the deterministic hopContext changes.

Only Leaf projects `command.payload` to the existing Updater API:

| Command | Updater request | Key | Query |
| --- | --- | --- | --- |
| U | existing UpdateRequest, jobId U, exact package metadata | persisted U key for new routed U | GET /api/v1/update/U |
| R | `{ "contractVersion": "2.0", "jobId": "U" }` | `rollback:U` | GET /api/v1/update/U |

The new routed envelope MUST NOT be sent to Updater. Updater never receives R as
operation identity or rebuilds R. Existing Updater semantic fingerprint, lifecycle,
package validation, ROS/workspace boundaries, activation/recovery and rollback
responsibilities are unchanged. Opaque metadata, if separately present, is not a
new Updater job or fingerprint component.

## 6. Replay fingerprints, durability and failure semantics

| Mutation boundary | Idempotency key / scope | Complete semantic fingerprint |
| --- | --- | --- |
| Observation / Server | `observation:<AgentId>:<observationEventId>` | complete original observation |
| Routed command / receiving Agent | `command:<serverCommandJobId>` | complete command except hopContext |
| Routed event / receiving Agent | `event:<serverCommandJobId>:<statusEventId>` | complete event except hopContext |
| Root status / Server | `status:<serverCommandJobId>:<sequence>` | complete root-status body |
| Leaf → Updater update | existing persisted update key, new routed jobs use U | unchanged existing UpdateRequest semantics |
| Leaf → Updater rollback | `rollback:U` | unchanged rollback body `{contractVersion,jobId:U}` |

Fingerprint excludes HTTP attempt headers, never target, route, package URL,
package digest, platform, creation/expiry, R/U or operation correlation. The
command/event hop envelope is independently validated and fixed for that boundary;
excluding it does not permit route mutation. Root-status fingerprints include its
fixed root hop. Fingerprints use canonical JSON from section 3; for a status event,
replace message with the lowercase hex encoding of its original UTF-8 bytes before
canonicalization so arbitrary human text is preserved exactly. For the new
firstSubmissionRejected variant, also replace the embedded rejection response
type/title/detail strings with their original UTF-8 lowercase hex before hashing
the event or root-status. The proof hash uses the same text encoding (section 7.1).
No text trimming or wire-payload rewriting.

Same key + fingerprint returns the durable original acceptance/receipt. Same job
with different target/route/payload/correlation/expiry is `409 IDEMPOTENCY_CONFLICT`
even if a sender presents a new key. Same key with altered hop context is rejected
by adjacency checks. No new U, R, operation correlation, logical hop, obligation,
sequence or physical ordinal is allocated for retry.

| Condition | Required behavior |
| --- | --- |
| Response lost before/after accept, timeout, reset, restart | load durable obligation, query same job at immediate downstream; reconcile then exact replay when needed |
| Query 404 while outcome unknown | retain unknown and query/exact replay; 404 alone never terminalizes |
| Query confirms acceptance/terminal | validate durable identity/fingerprint, retain/replay status obligation |
| First submission at/after expiry | no downstream mutation; terminal failed COMMAND_EXPIRED; R may use unavailable version evidence |
| Submission may already have occurred, expiry/late status | continue same query/replay; retain all receipts/evidence and accepted route |
| Server outage | downstream work/recovery continues; Root durable outbox retains terminal events and exact sequence/key |
| Root/Relay/Leaf restart | restore identities, receipts, source dedupe, sequence allocations and downstream obligations before new dispatch |
| Verified terminal outcome | owner persists a schema-supported terminal event and proof; HTTP request rejection alone does not establish logical terminal eligibility |
| Stale route, changed adjacency, route mismatch, incapable neighbor | fail closed, no substitute path or silent downgrade; report deterministic rejection |

A new dispatch checks current authenticated capabilities and local adjacency as
well as the retained snapshot. Unrelated topology revision changes never mutate an
accepted route. If a retained route is no longer authorized, do not send a new
mutation. A never-submitted operation can fail terminally with STALE_ROUTE,
ROUTE_MISMATCH, INVALID_ADJACENCY or CAPABILITY_MISMATCH. An operation with uncertain downstream
acceptance keeps its recovery/evidence obligation; a rejected retry is **not** proof
that the earlier operation never ran. It must reconcile through the original
permitted boundary or await explicit remediation. Expiry never deletes evidence.

New structured errors are defined only in the Phase 4 ErrorResponse schema.
400 VALIDATION_FAILED, 401/403 UNAUTHORIZED_PEER, 409 INVALID_TOPOLOGY/STALE_ROUTE/
ROUTE_MISMATCH/INVALID_ADJACENCY/IDEMPOTENCY_CONFLICT, 422 CAPABILITY_MISMATCH or
INCOMPATIBLE_RELEASE are nonretryable request rejections. 503 DEPENDENCY_UNAVAILABLE
and transport failure leave acceptance uncertain. In particular, a nonretryable
rejection to a retry does not resolve an earlier lost acceptance. Terminalization
requires a verified outcome; a shortcut flag claiming definitive rejection is
insufficient while the earlier send is unknown. A first, known-unaccepted mutation
can be rejected deterministically only when its original request/attempt is matched
and no earlier uncertain/accepted submission exists. Their receipt/outcome meaning
must not be inferred solely from retryable=false; pre-existing obligations remain.

For a submitted U without observed Updater versions, only the four authenticated
pre-acceptance route/capability errors in §7.1 establish this first-rejection terminal
path. ROUTE_MISMATCH can occur when the immutable request snapshot disagrees with the
child's currently authorized binding. All four require the child to have **no existing
obligation for this U**: a child with an existing matching obligation returns its
retained acceptance/outcome; a conflicting identity or payload returns the appropriate
conflict. It MUST NOT describe such existing work as a first pre-acceptance rejection,
even if its current route/capability checks would now fail. A rejection of this request
does not prove that this U has never executed.

Other nonretryable responses do not authorize `notObserved` projection: 409
IDEMPOTENCY_CONFLICT/UPDATE_ALREADY_RUNNING/INVALID_TOPOLOGY may describe existing work, conflicting or invalid context;
400 VALIDATION_FAILED, 401/403 UNAUTHORIZED_PEER, 404, and 422 INCOMPATIBLE_RELEASE do
not supply the §7.1 route/capability attestation. Preserve the obligation in a blocked,
unresolved state for verified reconciliation or explicit remediation; do not create
a failure event or invent versions merely to terminate it. Any earlier unknown or
accepted attempt likewise requires its actual outcome, regardless of the latest error
code. This does not retry a nonretryable malformed/unauthorized request blindly.
503 and transport failures retain uncertainty under the existing recovery rules.

## 7. Status, root sequence and dedicated history

Leaf commits the first semantic observation with `statusEventId` and timestamp;
all upstream relays retain that exact observation, including R/U, correlation,
route, versions and raw physical evidence. Changing only the directional hop
envelope does not create a new event. Same event ID with altered semantic payload
is a conflict. Relays never allocate Server sequence. Each new observation at Root
atomically stores event dedupe, next sequence and the exact outbox body. Sequence
starts at 0 per Server job, incrementing exactly 1 for each new local observation.
Retries and restart reuse that body, sequence and key. The durable transcript now
models source creation at A3, independent authenticated peer context at each receive,
A3/A2 commit-before-ACK/forward, retained per-Agent event/outbox state on restart,
unchanged semantic source fingerprint through A2/A1, and Root's atomic sequence/body
commit. It includes duplicate forwarding before ACK on both upstream relay edges.
Root-to-Server fingerprint covers the complete fixed root envelope, not only its
inner source observation. No relay may originate a replacement body for an existing
event or allocate a Server sequence.

Allocation order does not require HTTP arrival order. Server validates every acceptance condition, including terminal transitions, before
atomically storing a receipt or changing latest state. A rejected request leaves
receipt/latest state unchanged. It accepts exact replay and handles stale/gapped arrivals without rolling back
latest sequence, and preserves terminal obligations. A conflicting existing
sequence or reassigned event is rejected. Newer nonterminal observations cannot
reopen terminal jobs. The validator distinguishes local allocation assertions from
Server ingest tests. Expired internal scheduling state never appears on the wire;
late valid status is accepted and does not reclaim a released active device slot.

The routed status has all identity fields plus state/progress/message/error,
versionEvidence, observedAtUtc, hopContext and physicalEvidence. Existing twelve
public update states retain their meanings. Explicit rollback uses only queued,
rolling_back, rolled_back, failed. R rolled_back is success; U rolled_back is a
failed update with automatic recovery. U and R history rows remain separate.

New `versionEvidence` is an object with availability and required fromVersion/
targetVersion. Available uses two SemVer strings. Unavailable requires paired
nulls, **rollback + failed + non-null errorCode**. It is illegal for update U or
rollback success/active states. Do not fabricate versions from inventory, old U
rows, package names or the command. Missing evidence leaves device version and
original U unchanged. For the neverForwarded variant, a routed update U rejected before the rejecting Agent has ever forwarded
its obligation, the new DTO additionally permits availability `notObserved` with
paired null versions, failed state and a specific pre-forward rejection code.
Required failureEvidence names `stage=neverForwarded`, the rejecting snapshot
Agent and its durable obligationReceiptId. The receiver must validate this
against the authenticated Agent's retained never-forwarded record. Command receipts
include receiptId and monotonic downstreamEverSubmitted; the latter can never return
to false after forwarding. Receipt job/hash/fingerprint and rejecting Agent must all
match, and state must be terminal before this failure is projected.

The complete `originReceipt` and its `originReceiptHash` are embedded in
failureEvidence, not fetched by Server through an undeclared side channel. The hash
covers the entire original receipt using section 3 canonicalization. The origin
receipt's incoming command hop must name the rejecting snapshot Agent; its command
semantic fingerprint must equal the original obligation. Every forwarded copy keeps
that exact receipt, hash and event identity, including after restart and in history.

Provenance uses the established adjacent-peer trust boundary: the origin validates
its own durable never-forwarded fact; its immediate parent authenticates that origin
and commits the proof before ACK/forward. Each next parent authenticates its own
immediate child and relies on that authorized trusted relay's validation/retention
of the unchanged descendant proof. The claimed origin must be on the remaining
snapshot descendant chain. Server authenticates Root and validates the full projected
proof using its retained obligation. This is explicit transitive trust through the
configured Agents, not a claim that an unsigned hash independently authenticates a
remote source or withstands a compromised trusted relay. No direct source bypass,
body-claimed identity alone, new PKI mechanism or out-of-band receipt is permitted.
For neverForwarded, see `leaf-before-forward-failure.json`, `never-forwarded-transcript.json`, and
`never-forwarded-history.json` for A3→A2→A1→Server proof transport. It cannot be
used after submission might have occurred, for a physical operation, or for R.
This separately named variant is exclusive to new routed interfaces; it neither
relaxes the legacy unavailable R-only union nor guesses a device version. Device
version and original records remain unchanged. See
`update-before-forward-failure.json` and its negative fixtures.

The new history endpoint returns these full root envelopes;
the old history endpoint remains the old schema and meaning.

### 7.1 First submission rejected by the immediate child

`failureEvidence.stage=firstSubmissionRejected` is a distinct U-only variant for a
parent Agent's **first** routed mutation to its immediate child Agent, rejected
before child durable acceptance. It is not neverForwarded: the parent retains
`downstreamEverSubmitted=true`. Only these response pairs are valid:

| HTTP status | ErrorResponse.code = event.errorCode |
| --- | --- |
| 409 | STALE_ROUTE, ROUTE_MISMATCH or INVALID_ADJACENCY |
| 422 | CAPABILITY_MISMATCH |

The event is `update + failed`, availability `notObserved`, paired null versions,
and an empty physicalEvidence array. No inventory, command or previous-job version
may be substituted. Server terminalizes U and retains the full proof in its dedicated
history; it does not change device version or claim physical execution from this
failure. This case requires a child Agent on the original immutable route; it does
not apply to Leaf→Updater, R, a later attempt, an ambiguous response, or a retry
rejection after earlier unknown/accepted submission. Other error codes do not become
valid merely because retryable=false. Existing unavailable R and neverForwarded U
rules remain unchanged.

The origin is the submitting **parent**, identified by failureEvidence.agentId.
Its originReceipt is an immutable **terminal proof snapshot**, created and persisted
after the verified rejection with obligationState=terminal and everSubmitted=true.
It keeps the original command, acceptedAtUtc, receiptId and semantic fingerprint.
receiptId identifies the durable obligation, not a unique serialization of every
read snapshot. The original POST acceptance body is separately retained byte-for-byte
and exact POST replay still returns it; it is never rewritten into the terminal
proof. GET receipt may report the current obligation snapshot under the same ID.
The event freezes its terminal originReceipt bytes and originReceiptHash forever.
State advancement and everSubmitted becoming true create new snapshots, never change
an already emitted acceptance/proof, and never reset everSubmitted to false. Replaying
a historical acceptance with false must not overwrite current true submission state.
`first-submission-original-acceptance.json` and `first-submission-rejected-event.json`
demonstrate both immutable bodies for the same parent obligation. No child receipt
is fabricated or required.

`rejectionProof` binds parentAgentId, childAgentId, obligationReceiptId and journalId
to a complete, append-only parent-local journal for this one obligation's downstream
attempts, starting at sequence 1. `journalComplete=true` attests retained coverage
from its creation through the matching response. This variant has **exactly two**
records, in order, both attemptOrdinal=1:

1. `submission`, journalSequence=1: full immutable routed request with the actual
   child-directed hop, semantic requestFingerprint, `command:U` Idempotency-Key,
   exact request correlationId and recordedAtUtc. Commit this write-ahead record
   and everSubmitted=true before issuing the HTTP request. It must match the real
   forwarded request, not be constructed later from an error message.
2. `rejection`, journalSequence=2: independently authenticatedChildAgentId, actual transport
   httpStatus, complete original ErrorResponse and recordedAtUtc. Persist only after receiving and matching
   the authenticated response to that first request. Response correlationId must
   equal the request's exact spelling; actual HTTP status must equal ErrorResponse.status; status/code must match the table and
   retryable=false. The incoming acceptance precedes submission; first submission
   is before expiry; rejection is not before submission or after event observation.

Any earlier/later attempt, lost response, uncertainty, acceptance or query is a
journal fact that MUST be retained, never erased to manufacture this two-record
proof. Restart after an unresolved send retains uncertainty; a subsequent 4xx cannot
certify first-known rejection. Lost/uncertain work continues the existing query/exact
replay process. After persisting the matched response record, the parent atomically freezes its
terminal proof snapshot, stable failure event/outbox and terminal obligation before
upstream delivery or local terminal completion. A crash after the response record
but before this final transaction resumes proof/event creation from those retained
facts. After a verified response was durably retained, restart never dispatches a
second mutation; it completes or reuses the same terminal proof and stable event.
For one U, this terminal failure has exactly one statusEventId: reusing its proof,
receipt or rejection outcome under a new event ID is not a new observation. Source,
relay and Root must retain that binding; Root reuses its original body/sequence/key.
Server validates it against all retained receipts before committing, independent of
arrival order or latest projection. Normal distinct observations outside this terminal
failure variant retain their existing allocation and late/replay rules. Original
acceptance replay remains available throughout.

`rejectionProofHash` is SHA-256 of section 3 canonical JSON of the complete proof,
after encoding only records[1].response.type/title/detail as lowercase hex of their
exact UTF-8 bytes. This makes arbitrary response text verifiable without normalization.
The wire proof remains unchanged. originReceiptHash keeps its existing algorithm.
All route/U/operation correlation fields, hop, fingerprint, parent/child identities,
receipt binding, response echo, timestamps and hashes are checked on every projection.
Same event ID plus altered proof is a conflict. Relays preserve the full proof;
Root alone allocates sequence; Server atomically validates then stores full status
and history, retaining exact replay and rejecting conflicting sequence/event bodies.

A first-rejection proof is incompatible with already known child acceptance or U
progress. The complete source trace MUST reject a child (or downstream descendant)
U obligation before, during or after that claimed rejection, and the parent MUST
reject it if a child status has already arrived. Physical/status source actions
cannot erase a durable acceptance fact. Server checks **all retained receipts for
that U**, not only latest: available Updater versions, any physical evidence, or a
downstream-origin failure receipt proving child acceptance and
firstSubmissionRejected cannot coexist, regardless of stale/gap/late arrival order.
Validate this exclusion before receipt/latest mutation; rejecting the new input
preserves every retained receipt and the current projection. It also applies to
local status/Root allocation and relay observations. Exact replay remains valid.

A wire claim of journalComplete is **not** proof of local storage truth. The origin
must validate its actual write-ahead journal, transport-authenticated response and
unchanged original acceptance. The trace validator independently compares those
source actions and restart state against the projected proof; it rejects an invented
proof even when that proof alone is schema-valid. Upstream relays and Server validate
all visible bindings and retain the evidence under the established adjacent-peer
trust boundary. Server cannot independently read the parent's DB or authenticate
this history solely from its unsigned hash. A compromised trusted parent remains
outside that proof guarantee; no new PKI or direct Server→child side channel is added.

## 8. Durable physical-operation evidence

Updater exposes a new **read-only**, authorized-Leaf interface for raw U journal
records. It is topology-agnostic: raw records contain U, UpdaterId and authenticated
authorizedLeafAgentId, never Server R, route or operation correlation. Leaf joins
raw records to its durable command mapping, adds R/U, stable operation correlation
and routeSnapshotHash, then preserves the complete source object. Relays and Root
retain it unchanged. Root status and dedicated Server/Agent read interfaces expose
those projections; evidence is never available only in unstructured private logs.

Identity of a physical attempt is `(updaterId, updaterJobId U, operationKind,
operationAttemptOrdinal)`. Ordinal starts at 1 **separately for each U and kind**,
is contiguous for actual engine attempts, and survives process/journal restart.
Delivery retries allocate neither ordinal nor physical phase. Kind is activation,
automaticRecovery or explicitRollback. Automatic recovery still belongs to its
failed update U; it is never an explicit rollback R.

Each attempt has at most one immutable record for each phase:

- invoked: the canonical engine durably begins an actual logical execution
  attempt (duplicate request handling does not emit another invocation);
- activationStarted: durable entry/intent at the activation boundary, tied to
  journal/marker recovery; by itself this is not proof that a switch executed;
- completed: operation result and completion time, including failed invocation
  that never reached activation.

`startedAtUtc` is the fixed invocation start on all phases; completedAtUtc is null
until completed. Journal sequence increases within one stable Updater journal,
with one immutable record per `(updaterId,journalId,journalSequence)`. Journal IDs
cannot reset ordinal identity. Journal/record IDs must resolve to the source;
recordSha256 hashes the complete raw record excluding only evidenceSource's own
recordSha256 with section 3 canonicalization. Paths in evidence are sanitized
printable ASCII. No credentials or full secret-bearing environment strings.

Links expose durable journalRecordId plus marker version, symlink release target,
runtime version and artifact SHA-256. Unknown links are explicit nulls. A succeeded
completion requires these runtime links present and consistent: marker version
matches runtime version and symlink's last component; runtime artifact digest is
known. Consumers additionally verify these links against independently captured
journal/filesystem/runtime artifacts; a self-reported hash alone is not provenance
or proof that a physical switch happened. Failed records may retain unequal or
unknown links as failure evidence, never silently “repair” them in projection.

`executionEvidence` separates physical facts from journal intent. `notStarted`
with null observation is used at invocation. An activation-boundary intent with
no direct execution capture is `unknown`. `confirmed` requires a durable direct
sourceRecordId and observedAtUtc from actual engine execution observation, checked
against captured journal/runtime evidence. A succeeded completion requires confirmed
execution. `(updaterId, sourceRecordId)` is the immutable unique physical-start
identity across jobs, operation kinds, ordinals and journal rotations; it cannot be
reused to manufacture a second attempt. observedAtUtc is the actual start time in
that source observation, not the later time a relay receives or stores it. It must
be at/after invocation and at/before completedAtUtc when completion is known. Every
confirmed phase of the same attempt repeats the identical sourceRecordId and actual
start time. Contradictory source/time confirmations are conflicts, not deduped facts. An intent-only crash remains unknown; a later completed phase may resolve
it using direct source evidence without altering the earlier immutable phase record.
If execution cannot be established, retain unknown; never manufacture confirmation
from a final version or an ordinal. A failed invocation without activationStarted
has zero observed physical starts. A boundary intent without confirmation has an
unresolved count, not an exactly-once result.

Validation has three scopes. `raw_evidence` checks one record's shape, hash and
facts available in that record. `evidence_facts` checks all currently known phase
records together, without treating missing invocation, activation or earlier
ordinals as invalid partial delivery. A confirmed actual start must not exceed a
known completion for the same updater/U/kind/ordinal, even if the failed completion
itself has unknown execution evidence and null source/time. This check is independent
of arrival order. Status validation checks the event's known facts; local Root
allocation also checks the supplied previous event. Server ingest checks the union
of all retained receipt evidence and the incoming event before committing any
receipt or latest projection, including on stale arrivals. Callers accumulating
partial evidence must retain and validate that union; per-record validity is not
aggregate validity. `evidence_counts` additionally requires complete source-set
invocation/phase/ordinal coverage before asserting counts. None of these checks
turn partial delivery into proof of a complete operation lifetime.

Count **distinct phase identities**, after exact-replay dedupe. A rollback invoked
record counts invocation; activationStarted counts boundary intents. confirmedPhysicalStarts counts only
physical starts backed by executionEvidence; unresolvedPhysicalStarts counts intents
without that confirmation. Do not equate invocation, intent and confirmed execution. A failed invocation can have zero activations. Likewise,
count U confirmed physical starts independently from automaticRecovery confirmed
physical starts. `intent-only-evidence-page.json` returns snapshotProven=false even with a
complete retained journal: one intent, zero confirmed starts, one unresolved start.
`physical-operations.json` includes activation U3, recovery for separate failed
U-recovery, and explicit rollback R3→U3. `durable-transcript.json` contains two
logical commands, six Agent obligations, twelve deliveries, one update activation,
and one explicit-rollback invocation/activation. These are synthetic Contract
fixtures, **not** HIL evidence or a claim about deployed runtimes.

Each evidence page also names updaterJobId, stable journalId, the incoming
afterJournalSequence, and retentionComplete. The first cursor is 0; nonfinal
pages have complete=false and nextAfterJournalSequence equal to their last record.
The final page has a null next cursor. Complete=true requires retentionComplete=true;
retention loss remains explicitly partial. All pages retain one job/journal/watermark,
strict increasing unique sequence, and exact equality to matching authoritative
source records through that watermark. All three evidence GETs use an explicit
continuation binding: send both `journalId` and `journalHighWatermark` from page one
alongside afterJournalSequence on every continuation or exact snapshot replay. Both
may be absent only on a fresh page at afterJournalSequence=0. A partial pair is a
400 validation error; a mismatched/unavailable snapshot binding returns
409 EVIDENCE_SNAPSHOT_MISMATCH, never a silently refreshed live read. The binding is
resource-scoped: raw U versus projected Server U/R must match the endpoint and every
response. Two simultaneous reads may share afterJournalSequence but carry different
watermarks; restart/retry retains each binding. `evidence-read-transcript.json`
includes actual requests and two pages at watermark 9 while records 10–12 are added. A complete empty record set still proves no
physical operation; the evidence result is unproven. Responses explicitly expose
`proofScope=journalSnapshot` and `operationLifetimeProven=false`. The conformance
result is named snapshotProven and returns countScope with job/journal/watermark;
it never attests operation-lifetime exactly-once, even for a complete older snapshot.
A lowered watermark with omitted later activity remains bounded historical evidence.
HIL must independently establish complete operation-lifetime source coverage. An unknown execution prevents
a proven count even when pagination and retention are complete.

Evidence queries fix a journal high-watermark on the first page and return records
in increasing journalSequence; subsequent pages use afterJournalSequence plus the
explicit journalId/high-watermark pair. Retain
source journal IDs and evidence across retries/expiry. `complete=false` or missing
records/capture means unproven; final version or one completion row never proves
exactly once. To claim a count, HIL must establish complete durable source coverage
for the operation and compare raw source, Leaf projection and Root history, including
before/after crash capture. Read-interface pagination is validated against an
explicit authoritative source set in Contract tests; it cannot attest a real device.

## 9. Capability negotiation, migration and security

Every new operation requires `X-SlamCore-Contract-Version: 2.0` plus exact
`X-SlamCore-Capability: hierarchical-relay-v1`; the raw Updater evidence read uses
`physical-operation-evidence-v1` instead. Unknown/missing/mismatched negotiated
values fail closed (missing header 400, unsupported value 422). These headers
are assertions, not authority: current authenticated registration evidence and
local support must agree. The complete capability set replaces the previous set.
Unknown advertised tokens may be stored, but never imply a recognized capability.

All route Agents require exact Agent-scoped hierarchical-relay-v1; zero-device
Agents still register. Updater needs exact physical-operation-evidence-v1 before
new routed Phase 4 dispatch. Existing explicit-rollback-v1 stays device-scoped and
must be present at R creation and dispatch. It never implies hierarchical support.
Removal withholds new dispatch, without deleting accepted recovery obligations.
Rollout order: Contract review/pin → Server new storage/read/ingest with dispatch
disabled → Updater evidence capability → all Agents durable relay migrations and
capability registration → verify exact route capability evidence → enable creation.
Never send route-critical fields to an old deserializer or downgrade to legacy
single-hop because one relay is incapable.

Legacy `[legacy AgentId]` migration requires explicit durable evidence linking old
DeviceId, stable Agent identity, authorized attachment and Updater identity. Preserve
old U/R, registrations, receipts, sequence ownership and outbox. Missing/ambiguous
records remain unresolved and ineligible for new routed dispatch; endpoint URL,
online status or route length is never migration evidence. Existing accepted legacy
operations finish with their existing 2.0 semantics. The new endpoint does not force
route fields onto old records. See compatibility-matrix.md for consumer combinations.

Deployment supplies authenticated adjacent-peer identity and authorization per
Server/Agent/Updater trust boundary. Only the authorized Leaf may call Updater.
Unauthorized requests cause no accepted obligation or filesystem mutation. TLS,
credential rotation and PKI implementation are consumer/deployment responsibilities;
this change neither exposes new listen interfaces nor implements them. Secret-bearing
headers/tokens never enter route/history/logs. Package URLs must be public/sanitized
immutable addresses; fetch credentials stay out of semantic fingerprints and use
separately configured transport authentication.

## 10. Conformance and handoff

`python scripts/validate-contracts.py` runs unchanged legacy schema/OpenAPI/rollback
regressions plus every Phase 4 fixture and actual cross-field checks. Negative
fixtures use explicit JSON-pointer mutations of validated positive bases, and must
fail with the exact intended diagnostic, never an unrelated malformed prerequisite.
`docs/phase4-acceptance.md` maps issue requirements to implementation and evidence.

Consumer implementation remains owned by
[Server #8](https://github.com/EricChen3016/SlamCore-Server/issues/8),
[Agent #9](https://github.com/EricChen3016/SlamCore-Agent/issues/9), and
[Updater #55](https://github.com/EricChen3016/SlamCore-Updater/issues/55).
Each must pin the reviewed Contract commit and reproduce its schema/hash/negative
vectors plus real consumer persistence/restart tests. Production/HIL qualification
belongs solely to [Server #18](https://github.com/EricChen3016/SlamCore-Server/issues/18).
Phase 3 evidence gaps remain unproven; this Contract does not close them, implement
consumer runtimes, or approve deployment.
