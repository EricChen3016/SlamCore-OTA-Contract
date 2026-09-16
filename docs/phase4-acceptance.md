# Phase 4 Contract acceptance mapping

Authority: [Contract #5](https://github.com/EricChen3016/SlamCore-OTA-Contract/issues/5). Base main `bdf02af7c4e746afecb7bed19a493645c8f412cc`. New repository version 2.2.0, runtime 2.0.

## Acceptance criteria

All references below are within this repository. `phase4-viaagent` means the normative document; examples live in `examples/phase4`, schemas in `schemas/phase4`, and named checks in `scripts/phase4_contract.py` / `scripts/validate_phase4.py`. These are Contract conformance checks, not consumer/HIL execution.

| Issue criterion | Requirement | Contract implementation / evidence |
| --- | --- | --- |
| AC-01 | Contract 2.0 single-hop ViaAgent registration、pending command、Agent→Updater request／status、history與lifecycle semantics保持可用；不建立Server direct ingress compatibility。 | Legacy schemas unchanged; original validator regressions; both legacy OpenAPI documents change info.version only. |
| AC-02 | Legacy single-Agent Contract 2.0 deployment deterministic projection為single-hop route `[legacy AgentId]`。 | phase4-viaagent §9; legacy-migration.json / legacy_migration. |
| AC-03 | Legacy records若缺route，僅能依明確migration evidence補出，不得由online endpoint猜測。 | phase4-viaagent §9; migration missing-evidence, route-guess and identity negatives. |
| AC-04 | `explicit-rollback-v1`不代表hierarchical relay capability；Phase 4使用獨立exact capability snapshot。 | protocol agentCapability/deviceCapability; dispatch_gate; current capability-removal negatives. |
| AC-05 | Capability可Agent-scoped，因Relay Agent可能attach zero Devices。 | agent-observation.json (A4, zero devices); observation check. |
| AC-06 | Unknown version／capability fail closed；no silent downgrade／route-critical delivery。 | OpenAPI exact required version/capability headers; command/gate version/capability negatives. |
| AC-07 | Compatibility matrix列出supported與fail-closed Server／Agent／Updater組合。 | compatibility-matrix Phase 4 combinations. |
| AC-08 | Breaking field／endpoint／header／state／owner change依governance升級runtime major version。 | phase4-viaagent §1; ADR-0001 precedent; VERSION 2.2.0 / runtime 2.0. |
| AC-09 | Agent／Device identity與topology observation。 | agent-observation and topology schemas; topology/observation semantic checks. |
| AC-10 | Immutable ordered route snapshot與capability snapshot。 | route-snapshot schema; route checks; 3 exact canonical hash vectors. |
| AC-11 | Routed update／rollback command與hop context。 | routed-command schema; expected_hop / command checks at every Agent hop. |
| AC-12 | Stable operation correlation與attempt correlation。 | command/status operationCorrelationId and OpenAPI X-Correlation-Id; correlation conflict negatives. |
| AC-13 | Routed status、root sequence與Server history projection。 | routed-status-event/root-status/history-page; root_status local allocation and server_ingest out-of-order tests. |
| AC-14 | `{R,U}` rollback relationship與unavailable version evidence。 | n-hop-rollback and history-page; R/U identity, null union and rollback-state negatives. |
| AC-15 | Physical-operation evidence projection。 | raw/projected evidence and page schemas; projected_evidence/evidence_counts/evidence_pages. |
| AC-16 | Structured deterministic error／conflict responses。 | Phase 4 error schema; response-specific 400/401/403/404/409/422/503 examples and response checks. |
| AC-17 | Normative identity／authority／route／hop／status／rollback rules。 | phase4-viaagent §§1–7; full schema/semantic suite. |
| AC-18 | Security trust boundaries與secret handling。 | phase4-viaagent §§2/4/9; authenticated caller independent of claimed body check. |
| AC-19 | VERSION／CHANGELOG／compatibility matrix／migration guidance。 | VERSION, CHANGELOG, README, compatibility-matrix and migration example. |
| AC-20 | Breaking／non-breaking version rationale。 | phase4-viaagent §1 additive decision; old required behavior untouched. |
| AC-21 | Legacy single-hop update／rollback。 | Legacy update/rollback examples retained; new single-hop-update / single-hop-rollback. |
| AC-22 | Branching與N-hop update。 | branching-update / n-hop-update; authority A1 and A2 have both children and devices. |
| AC-23 | N-hop explicit rollback `{R,U}`。 | n-hop-rollback; all-hop U/R projection checks. |
| AC-24 | Replay／conflict／response-loss／restart examples。 | durable-transcript; exact replay/conflict/restart/query-before-replay tests. |
| AC-25 | Wrong sender／route／hop negative fixtures。 | negative-cases: wrong sender/receiver, non-neighbor, route hash/order, overflow. |
| AC-26 | History with `versionEvidence=unavailable`。 | history-page rollback unavailable row; schema/context checks. |
| AC-27 | Physical activation／rollback evidence fixture。 | physical-operations / projected-operation-evidence / intent-only-evidence-page. |
| AC-28 | Single-hop normal update／explicit rollback。 | single-hop U/R positive command checks and retained legacy regressions. |
| AC-29 | Branching tree，Agent同時管理Device與child Agent。 | topology.json A1→A2→A3 plus A4 root; D1 at A1 and D2 at A2; branching U/R. |
| AC-30 | N-hop update／rollback，identity與correlation不變。 | all-hop command checks; same semantic event through upstream hops. |
| AC-31 | Same-job replay與conflicting route／payload。 | same-job payload/correlation/expiry and route hash/order negatives; receipt fingerprint. |
| AC-32 | Response lost before／after downstream accept。 | durable-transcript each actor first loss→404, exact replay→lost acceptance→receipt reconciliation. |
| AC-33 | Root／Relay／Leaf restart與Server outage。 | durable-transcript A1/A2/A3 restart and Server outage; dropped receipt/ACK during outage negatives. |
| AC-34 | Topology change after job accept不改snapshot。 | accepted snapshot/current topology positive distinction and current-adjacency negative. |
| AC-35 | Loop、wrong sender、non-neighbor、hop overflow fail closed。 | cycle/duplicate/empty route/caller/neighbor/overflow negatives, before acceptance checks. |
| AC-36 | Logical／delivery／physical operation counts可直接區分。 | trace expected: 2 logical jobs, 6 obligations, 12 deliveries; separate phase/intents/confirmed/unresolved physical counts. |
| AC-37 | Phase 4 ViaAgent identity、route、hop、correlation、idempotency、status與rollback semantics frozen。 | phase4-viaagent normative freeze and schemas/phase4. |
| AC-38 | Schema／OpenAPI／examples／validator與normative docs一致。 | Single validate-contracts.py runs schema, exact-reason semantics and pinned OpenAPI operation/schema/header/example coverage. |
| AC-39 | `AgentId != DeviceId`與rooted hierarchical topology無歧義。 | identity/topology functions and collision/cycle/multi-parent/orphan negatives. |
| AC-40 | Normal update保留single U；explicit rollback保留`Server R → Updater U`。 | command identity rules, leaf payload U checks and at-most-one-R test. |
| AC-41 | Root-only Server sequence與relay status event identity無歧義。 | status/event/root schemas; root/relay negatives; local contiguous allocation separated from arrival order. |
| AC-42 | Physical-operation evidence projection可machine-validate。 | raw/leaf/root projection identity/provenance tests; intent-only crash remains unproven; page coverage/retention tests. |
| AC-43 | Contract 2.0 legacy path與version／capability migration策略完成。 | unchanged legacy schemas plus capability/legacy-migration tests and matrix. |
| AC-44 | Consumer conformance matrix與negative fixtures通過。 | compatibility-matrix consumer handoff plus complete exact-reason fixture table below; downstream implementation tests are consumer-owned. |
| AC-45 | VERSION／CHANGELOG與breaking decision完成。 | VERSION 2.2.0, CHANGELOG 2.2.0 and phase4-viaagent §1. |
| AC-46 | Required PR、CI、Independent Review無unresolved blocking／high finding。 | Delivery gate: Draft PR + real CI + independent Work review are recorded in the final GitHub checkpoint, not claimed by synthetic Contract fixtures. |
| AC-47 | Evidence回連Server #8與#18。 | Consumer handoff links to Server #8/#18 below; Work posts final reviewed evidence checkpoint after CI and independent review. |

## Validation evidence and limits

Run `python -m pip install -r requirements-dev.txt` then `python scripts/validate-contracts.py`. The suite reports exact counts dynamically. At delivery preparation: **32 positive schema mappings, 33 semantic checks, 130 targeted negative fixtures, 3 hash vectors, 12 OpenAPI operations, 17 independent-review regression groups and 6 first-rejection regression groups**, plus all existing legacy validation. JavaScript independently reproduced all three canonical route digests during implementation.

The positive N-hop transcript contains **2 logical commands (U3/R3), 6 Agent durable obligations, 12 downstream command delivery attempts, and 8 upstream status relay attempts**. For activation and explicitRollback separately: invoked=1, activationStarted intent=1, completed=1, confirmedPhysicalStarts=1, unresolvedPhysicalStarts=0. Automatic recovery is a separate raw fixture for failed U-recovery. An intent-only crash has confirmedPhysicalStarts=0, unresolvedPhysicalStarts=1 and snapshotProven=false / operationLifetimeProven=false even when its journal page is complete. These numbers describe the fixtures, not a device.

Local allocation tests require sequence 0,+1; separate ingest tests preserve receipts on stale/gap/out-of-order arrival. Same-event relay fingerprints exclude only the independently validated hop envelope. Page coverage tests compare exact authoritative source records; no response label or expected scenario outcome substitutes for an assertion.

Negative cases first validate the unmodified base, then apply their JSON-pointer changes and optional documented digest repair; only the exact listed diagnostic satisfies the test. Semantic negatives cannot pass from unrelated SCHEMA errors. Error code SCHEMA is used only for deliberately malformed unions, versions, missing/unknown exact discriminants, duplicate/empty or over-limit array shape. Digest repair recomputes a syntactically valid input so the intended contextual invariant is tested.

## Negative fixture map

| Fixture | Check | Positive base | Required rejection |
| --- | --- | --- |
| cycle | topology | topology.json | CYCLE |
| multi-parent | topology | topology.json | MULTI_PARENT |
| orphan | topology | topology.json | ORPHAN |
| duplicate-agent | topology | topology.json | DUPLICATE_AGENT |
| duplicate-attachment | topology | topology.json | DUPLICATE_ATTACHMENT |
| orphan-attachment | topology | topology.json | ORPHAN_ATTACHMENT |
| agent-device-identity | topology | topology.json | IDENTITY_COLLISION |
| shared-updater | topology | topology.json | DUPLICATE_UPDATER |
| observation-forged-self | observation | agent-observation.json | UNAUTHORIZED_PEER |
| observation-foreign-attachment | observation | agent-observation.json | OBSERVATION_SCOPE |
| route-hash | command | n-hop-update.json | ROUTE_HASH |
| route-order | command | n-hop-update.json | WRONG_LEAF |
| wrong-root | command | n-hop-update.json | WRONG_ROOT |
| wrong-leaf | command | n-hop-update.json | WRONG_LEAF |
| empty-route | command | n-hop-update.json | SCHEMA |
| duplicate-route | command | n-hop-update.json | SCHEMA |
| hop-overflow | command | n-hop-update.json | HOP_OVERFLOW |
| wrong-sender | command | n-hop-update.json | UNAUTHORIZED_PEER |
| wrong-receiver | command | n-hop-update.json | WRONG_RECEIVER |
| non-neighbor | command | n-hop-update.json | INVALID_ADJACENCY |
| stale-route | command | n-hop-update.json | STALE_ROUTE |
| missing-target | command | n-hop-update.json | MISSING_TARGET |
| unknown-runtime | command | n-hop-update.json | SCHEMA |
| wrong-capability | command | n-hop-update.json | SCHEMA |
| target-mismatch | command | n-hop-update.json | TARGET_MISMATCH |
| U-discontinuity | command | n-hop-update.json | UPDATE_IDENTITY |
| updater-wrong-U | command | n-hop-update.json | UPDATER_PROJECTION |
| capability-missing | command | n-hop-update.json | CAPABILITY_MISMATCH |
| updater-evidence-missing | command | n-hop-update.json | CAPABILITY_MISMATCH |
| expiry-window | command | n-hop-update.json | EXPIRY_WINDOW |
| same-job-payload | replay | n-hop-update.json | IDEMPOTENCY_CONFLICT |
| same-job-correlation | replay | n-hop-update.json | IDEMPOTENCY_CONFLICT |
| same-job-expiry | replay | n-hop-update.json | IDEMPOTENCY_CONFLICT |
| R-equals-U | command | n-hop-rollback.json | ROLLBACK_IDENTITY |
| R-projects-R | command | n-hop-rollback.json | UPDATER_PROJECTION |
| R-correlation-reuses-U | command | n-hop-rollback.json | ROLLBACK_CORRELATION |
| R-route-revision | command | n-hop-rollback.json | ROLLBACK_ROUTE |
| R-package-fields | command | n-hop-rollback.json | SCHEMA |
| relay-allocates-sequence | root | root-status.json | ROOT_SEQUENCE_OWNER |
| sequence-gap | rootReplay | root-status.json | SEQUENCE_GAP |
| sequence-conflict | rootReplay | root-status.json | SEQUENCE_CONFLICT |
| event-conflict | eventReplay | routed-status-event.json | STATUS_EVENT_CONFLICT |
| status-correlation | status | routed-status-event.json | STATUS_IDENTITY |
| status-target | status | routed-status-event.json | TARGET_MISMATCH |
| rollback-completed | status | routed-status-event.json | SCHEMA |
| null-version-pair | root | root-status.json | SCHEMA |
| unavailable-success | root | root-status.json | SCHEMA |
| evidence-forged-leaf | projection | projected-operation-evidence.json | EVIDENCE_LEAF |
| evidence-forged-R | projection | projected-operation-evidence.json | EVIDENCE_IDENTITY |
| evidence-forged-route | projection | projected-operation-evidence.json | EVIDENCE_ROUTE |
| raw-hash | raw | raw-operation-evidence.json | EVIDENCE_HASH |
| physical-runtime-provenance | raw | raw-operation-evidence.json | RUNTIME_PROVENANCE |
| physical-time | raw | raw-operation-evidence.json | EVIDENCE_TIME |
| ordinal-gap | counts | physical-operations.json | ORDINAL_GAP |
| phase-replay-conflict | counts | physical-operations.json | EVIDENCE_PHASE_CONFLICT |
| journal-sequence-reuse | counts | physical-operations.json | JOURNAL_SEQUENCE_CONFLICT |
| missing-activation | counts | physical-operations.json | MISSING_ACTIVATION |
| forward-before-durable | trace | durable-transcript.json | WRITE_BEFORE_FORWARD |
| ack-before-durable | trace | durable-transcript.json | WRITE_BEFORE_ACK |
| restart-drops-obligation | trace | durable-transcript.json | RESTART_DURABILITY |
| unknown-404-terminal | trace | durable-transcript.json | UNKNOWN_TERMINAL |
| replay-without-query | trace | durable-transcript.json | QUERY_BEFORE_REPLAY |
| expired-first-submit | trace | durable-transcript.json | EXPIRED_FIRST_SUBMISSION |
| replay-payload-change | trace | durable-transcript.json | REPLAY_PAYLOAD |
| trace-relay-sequence | trace | durable-transcript.json | ROOT_SEQUENCE_OWNER |
| status-key-retry-change | trace | durable-transcript.json | STATUS_KEY |
| status-payload-retry-change | trace | durable-transcript.json | STATUS_WRITE_BEFORE_SEND |
| route-over-limit | command | n-hop-update.json | SCHEMA |
| job-agent-global-collision | command | n-hop-update.json | IDENTITY_COLLISION |
| current-agent-capability-removed | gate | topology.json | CAPABILITY_MISMATCH |
| current-device-rollback-capability-removed | gate | topology.json | ROLLBACK_CAPABILITY |
| current-adjacency-changed | gate | topology.json | STALE_ROUTE |
| evidence-page-omission | page | raw-evidence-page.json | EVIDENCE_PAGE_ORDER |
| evidence-cursor-skips | page | raw-evidence-page.json | EVIDENCE_CURSOR |
| evidence-truncated-claim-complete | page | raw-evidence-page.json | EVIDENCE_RETENTION |
| evidence-watermark-excludes-record | page | raw-evidence-page.json | EVIDENCE_PAGE_ORDER |
| pre-forward-version-fabrication | updateFailure | update-before-forward-failure.json | SCHEMA |
| pre-forward-unavailable-not-legacy-R | updateFailure | update-before-forward-failure.json | SCHEMA |
| pre-forward-authority | updateFailure | update-before-forward-failure.json | FAILURE_EVIDENCE_AUTHORITY |
| pre-forward-stage-unknown | updateFailure | update-before-forward-failure.json | SCHEMA |
| physical-confirmed-without-source | raw | raw-operation-evidence.json | EXECUTION_PROVENANCE |
| physical-success-with-unknown-execution | raw | raw-operation-evidence.json | EXECUTION_UNPROVEN |
| physical-before-durable-acceptance | trace | durable-transcript.json | PHYSICAL_WITHOUT_ACCEPTANCE |
| trace-forward-wrong-neighbor | trace | durable-transcript.json | INVALID_ADJACENCY |
| trace-forward-key-change | trace | durable-transcript.json | COMMAND_KEY |
| trace-relay-sends-server-status | trace | durable-transcript.json | ROOT_SEQUENCE_OWNER |
| server-ack-while-outage | trace | durable-transcript.json | ACK_DURING_OUTAGE |
| evidence-valid-order-omission | page | raw-evidence-page.json | EVIDENCE_COVERAGE |
| migration-missing-agent | migration | legacy-migration.json | MIGRATION_EVIDENCE |
| migration-route-guess | migration | legacy-migration.json | MIGRATION_ROUTE |
| migration-job-rekey | migration | legacy-migration.json | MIGRATION_IDENTITY |
| pre-forward-after-submission | failureReceipt | never-forwarded-receipt.json | FAILURE_AFTER_SUBMISSION |
| receipt-fingerprint | receipt | command-receipt.json | RECEIPT_IDENTITY |
| same-job-valid-target-route-conflict | replay | n-hop-update.json | IDEMPOTENCY_CONFLICT |
| same-event-new-sequence | rootReplay | root-status.json | EVENT_SEQUENCE_REASSIGNMENT |
| retry-fabricates-physical-invocation | trace | durable-transcript.json | TRACE_COUNT_MISMATCH |

## Independent review correction evidence

The first reviewed head `98c205c` was rejected for F1–F6. These corrections preserve
repository 2.2.0/runtime 2.0 and the additive boundary. Tests first reproduced the
faults; the corrected source now passes the same independent F1/F2/F4 probes and
the following eight regression groups in `scripts/validate_phase4_review.py`.
The final corrected-head Independent Review remains a separate delivery gate.

| Finding | Concrete correction and regression evidence |
| --- | --- |
| F1 | `atomic_ingest`: rejection leaves receipts/latest unchanged; valid stale/gap/replay still works. All acceptance validation precedes receipt commit. |
| F2 | `physical_start_time`, `physical_source_reuse`, `physical_confirmation_conflict`: actual start cannot follow completion; one source cannot identify two attempts; every confirmed phase repeats one immutable source/time; unknown-to-confirmed resolution and exact replay stay valid. |
| F3 | `fixed_snapshot_reads`, `evidence-read-transcript.json`: actual query journalId/high-watermark binds concurrent reads at 9 and 12; partial/mismatched pair, resource mismatch and response drift reject. Older bounded snapshots expose countScope and never claim operationLifetimeProven. |
| F4 | `uncertain_rejection`: rejected retry cannot clear an earlier unknown acceptance; first known-unaccepted mutation rejection and later verified reconciliation remain representable. |
| F5 | `relayed_origin_proof`, `leaf-before-forward-failure.json`, `never-forwarded-transcript.json`, `never-forwarded-history.json`: original A3 receipt/hash is carried durably through A2/A1/Server. No unreachable out-of-band proof injection. Omission, mutation, foreign origin and downstream-submitted receipt reject; replay/history works using the wire input. |
| F6 | `adjacent_status_durability`: actual A3 source creation, independent peer identity on A2/A1 receipt, immutable source fingerprint, commit-before-ACK/forward, duplicate forwarding, retained source/relay/root outboxes across restart, and Root-only atomic sequence/outbox. Mutation, forged actual actor, premature ACK/forward and lost restart state reject. |

The normal U/R trace has zero pending relay/root status obligations after ACK;
the never-forwarded U trace has 3 durable Agent obligations, 2 command deliveries,
4 status relay attempts and zero physical operations. These remain synthetic
Contract conformance facts, not runtime/HIL evidence.

## Consumer handoff and final gate

- [Server #8](https://github.com/EricChen3016/SlamCore-Server/issues/8): topology/route persistence, dispatch, status/history/evidence reads and compatibility migration.
- [Agent #9](https://github.com/EricChen3016/SlamCore-Agent/issues/9): durable authenticated relay, root-only sequence, R/U projection and evidence retention.
- [Updater #55](https://github.com/EricChen3016/SlamCore-Updater/issues/55): authorized Leaf, unchanged U-only mutation API and durable raw physical/execution evidence.
- [Server #18](https://github.com/EricChen3016/SlamCore-Server/issues/18): fixed-artifact HIL/capture/security/runbook and production go/no-go. All carried Phase 3 unproven evidence remains unproven.

PR/CI/independent review outcomes belong to the delivery checkpoint on the actual reviewed head. No merge, tag, release, deployment, issue closure, consumer repository mutation or production PASS is authorized by this document.


## Known completion time regression

`cross-phase-time-status.json` is a deliberately invalid aggregate whose three raw
records each pass schema/hash/per-record checks: actual start 00:01:10 follows the
same attempt's failed/unknown completion at 00:01:05. It must be rejected with the
existing `EXECUTION_TIME` diagnostic. Five additional review regression groups cover:

- All six record permutations in complete counts; no input mutation on rejection.
- Single-batch Root/status validation and atomic Server receipt rejection.
- Start prefix followed by completion, both local Root allocation and Server ingest;
  the rejected Server event preserves receipts/latest and exact prefix replay.
- Completion-only received first, followed by a stale or higher-sequence start;
  partial completion is accepted, contradiction rejected atomically, exact replay retained.
- Valid actual start at invocation or exactly at completion, both delivery orders,
  confirmed source deduplication and unknown intent resolved by later confirmation.

These tests implement the existing §8 time rule. They add no wire fields, HTTP error
codes or capabilities and do not change UUID casing behavior. The later correlation correction is recorded below.


## Attempt UUID correlation regression

The [Issue #5 architecture decision](https://github.com/EricChen3016/SlamCore-OTA-Contract/issues/5#issuecomment-5696925708)
retains valid lowercase, mixed-case and uppercase attempt UUIDs and requires exact
error echo. `error-correlation-{lowercase,mixedcase,uppercase}.json` are valid error
examples, checked against the same UUID range as the OpenAPI header. Four additional
review groups check:

- Each valid spelling remains byte-for-byte equal to its triggering header; a
  schema-valid normalized spelling is rejected with `ERROR_CORRELATION_ECHO`.
- Missing/malformed headers use a valid diagnostic UUID; non-UUID, non-string,
  compact or whitespace-padded echoes fail schema validation.
- Header and full error-response schema reject non-UUID, extra/misplaced hyphens
  and trailing whitespace under both default Draft202012Validator (no format
  checker) and explicit UUID format checking. A maximum length of 36 also excludes
  a terminal newline that some regex `$` anchors otherwise allow.
- Command, event and physical projection operationCorrelationId still reject valid
  uppercase/mixed-case UUIDs and non-UUID values while accepting canonical lowercase.

The OpenAPI validator pins the one shared CorrelationId header reference on all 12
operations and the shared error-response schema for every declared error status.
The old `9df0464` schema rejected the uppercase echo solely because of its lowercase
pattern. Replacing it with the same case-insensitive canonical UUID structure used
by the attempt header corrects the contradiction without relying on optional format
assertion. The interim 038a302 format-only correction failed independent review
because annotation-only validators accepted arbitrary strings. The structural
regression prevents that gap while leaving legacy 2.0 schemas, operation identity,
hash vectors and idempotency rules unchanged.


## First known-unaccepted child rejection (F4 completion)

The original F4 trace could locally terminalize without a valid U event. The new
firstSubmissionRejected proof completes AC-13/14/15/16, AC-29/30/31/32 and AC-38/42/44:
parent A2 has an immutable original acceptance plus a true-submitted terminal snapshot,
first write-ahead request and independently authenticated A3 409/422 response; the
same failure event/proof passes A2→A1, Root sequence0, exact status replay and Server
history. The valid scenario has 1 logical U, 2 durable Agent obligations, 2 command
deliveries, 2 status relay attempts, no pending status after ACK, and no observed
physical phases. These are synthetic facts, not HIL/production evidence.

Six first-rejection groups cover wire/history and preserved acceptance snapshots;
all four allowed 409/422 responses through actual journal/relay/restart/outage traces;
source-trace rejection cases plus legal uncertain query/replay; and conflicting
proof/atomic Server rejection/Unicode evidence preservation. The final two groups
reject child acceptance before/during/after send, actual child physical/status facts
and parent-visible child completion, while retaining normal acceptance/query recovery;
and atomically reject first proof versus available/physical progress across every
retained receipt in either order, including stale/gap/late and no latest projection.
A source cannot certify
an unknown/retried/accepted send by merely supplying a complete=true proof. Server
validates projected bindings through trusted relays; it cannot read a remote journal.
The old neverForwarded and R-only unavailable tests remain. The F4 review regression
now calls full propagation, replacing its earlier delivery-count-only positive check.

Additional exact-reason wire negatives (rehashRejection recomputes both supplied
hashes for semantic cases; altered-proof-hash intentionally retains a wrong hash):

| Fixture | Check | Positive base | Required rejection |
| --- | --- | --- | --- |
| first-rejection-wrong-child | firstRejection | first-submission-rejected-event.json | REJECTION_CHILD |
| first-rejection-wrong-auth-child | firstRejection | first-submission-rejected-event.json | REJECTION_CHILD |
| first-rejection-wrong-parent | firstRejection | first-submission-rejected-event.json | REJECTION_CHILD |
| first-rejection-foreign-receipt | firstRejection | first-submission-rejected-event.json | REJECTION_OBLIGATION |
| first-rejection-foreign-job | firstRejection | first-submission-rejected-event.json | REJECTION_REQUEST |
| first-rejection-foreign-operation-correlation | firstRejection | first-submission-rejected-event.json | REJECTION_REQUEST |
| first-rejection-wrong-route | firstRejection | first-submission-rejected-event.json | REJECTION_REQUEST |
| first-rejection-altered-payload | firstRejection | first-submission-rejected-event.json | REJECTION_REQUEST |
| first-rejection-wrong-fingerprint | firstRejection | first-submission-rejected-event.json | REJECTION_REQUEST |
| first-rejection-wrong-hop | firstRejection | first-submission-rejected-event.json | REJECTION_HOP |
| first-rejection-wrong-key | firstRejection | first-submission-rejected-event.json | REJECTION_KEY |
| first-rejection-response-echo | firstRejection | first-submission-rejected-event.json | ERROR_CORRELATION_ECHO |
| first-rejection-non-409-422 | firstRejection | first-submission-rejected-event.json | REJECTION_RESPONSE |
| first-rejection-wrong-response-code | firstRejection | first-submission-rejected-event.json | REJECTION_RESPONSE |
| first-rejection-retryable-response | firstRejection | first-submission-rejected-event.json | REJECTION_RESPONSE |
| first-rejection-mismatched-status-code | firstRejection | first-submission-rejected-event.json | REJECTION_RESPONSE |
| first-rejection-mismatched-event-code | firstRejection | first-submission-rejected-event.json | REJECTION_RESPONSE |
| first-rejection-late-first-send | firstRejection | first-submission-rejected-event.json | REJECTION_TIME |
| first-rejection-response-before-submission | firstRejection | first-submission-rejected-event.json | REJECTION_TIME |
| first-rejection-observation-before-response | firstRejection | first-submission-rejected-event.json | REJECTION_TIME |
| first-rejection-false-submission | firstRejection | first-submission-rejected-event.json | REJECTION_SUBMISSION |
| first-rejection-nonterminal-receipt | firstRejection | first-submission-rejected-event.json | FAILURE_AFTER_SUBMISSION |
| first-rejection-partial-journal | firstRejection | first-submission-rejected-event.json | SCHEMA |
| first-rejection-later-attempt | firstRejection | first-submission-rejected-event.json | SCHEMA |
| first-rejection-noninitial-journal | firstRejection | first-submission-rejected-event.json | SCHEMA |
| first-rejection-earlier-unknown | firstRejection | first-submission-rejected-event.json | SCHEMA |
| first-rejection-unavailable-U | firstRejection | first-submission-rejected-event.json | SCHEMA |
| first-rejection-available-with-proof | firstRejection | first-submission-rejected-event.json | SCHEMA |
| first-rejection-rollback-with-proof | firstRejection | first-submission-rejected-event.json | SCHEMA |
| first-rejection-claimed-child-receipt | firstRejection | first-submission-rejected-event.json | FAILURE_EVIDENCE_AUTHORITY |
| first-rejection-altered-proof-hash | firstRejection | first-submission-rejected-event.json | REJECTION_PROOF_HASH |
| first-rejection-physical-claim | firstRejection | first-submission-rejected-event.json | SCHEMA |
| first-rejection-transport-status-mismatch | firstRejection | first-submission-rejected-event.json | REJECTION_RESPONSE |
| first-rejection-transport-not-409-422 | firstRejection | first-submission-rejected-event.json | SCHEMA |
