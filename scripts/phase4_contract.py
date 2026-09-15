"""Pure Phase 4 contract assertions; no network, persistence, or deployment engine.

Schema validation checks shape. These checks enforce cross-object relationships
against explicit authority, authenticated peer context, and durable transcripts.
"""
from __future__ import annotations
import copy
import hashlib
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CAPABILITY = 'hierarchical-relay-v1'
EVIDENCE_CAPABILITY = 'physical-operation-evidence-v1'


class Violation(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(condition, code):
    if not condition:
        raise Violation(code)


def canonical(value):
    """Sorted JSON, ASCII keys/strings, integers only; see normative algorithm."""
    def check(x):
        if isinstance(x, str):
            require(all(0x20 <= ord(c) <= 0x7e for c in x), 'CANONICAL_CHARACTER')
        elif x is None or isinstance(x, bool):
            return
        elif isinstance(x, int):
            require(abs(x) <= 2147483647, 'CANONICAL_INTEGER')
        elif isinstance(x, list):
            for child in x:
                check(child)
        elif isinstance(x, dict):
            for key, child in x.items():
                check(key)
                check(child)
        else:
            raise Violation('CANONICAL_TYPE')
    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def route_hash(route):
    return digest({k: v for k, v in route.items() if k != 'routeSnapshotHash'})


def command_fingerprint(command):
    return digest({k: v for k, v in command.items() if k != 'hopContext'})


def event_fingerprint(event):
    # Human messages can be Unicode. Hash its UTF-8 bytes as lowercase hex before
    # canonical JSON, a fixed transform that preserves every byte of the message.
    value = {k: v for k, v in event.items() if k != 'hopContext'}
    value['message'] = value['message'].encode('utf-8').hex()
    return digest(value)


def source_hash(record):
    value = copy.deepcopy(record)
    value['evidenceSource'].pop('recordSha256')
    return digest(value)


@lru_cache(maxsize=1)
def schema_registry():
    resources = []
    for path in (ROOT / 'schemas').rglob('*.json'):
        data = json.loads(path.read_text())
        resources.append((data['$id'], Resource.from_contents(data)))
        resources.append((path.as_uri(), Resource.from_contents(data)))
    return Registry().with_resources(resources)


def shape(name, value):
    path = ROOT / 'schemas/phase4' / (name + '.schema.json')
    validator = Draft202012Validator(json.loads(path.read_text()), registry=schema_registry(), format_checker=FormatChecker())
    require(not list(validator.iter_errors(value)), 'SCHEMA')


def topology(value):
    shape('topology', value)
    agents = [x['agentId'] for x in value['agents']]
    require(len(set(agents)) == len(agents), 'DUPLICATE_AGENT')
    parents = {}
    for link in value['parentLinks']:
        p, c = link['parentAgentId'], link['childAgentId']
        require(p in agents and c in agents, 'ORPHAN')
        require(c not in parents, 'MULTI_PARENT')
        parents[c] = p
    for agent in agents:
        seen = set()
        while agent in parents:
            require(agent not in seen, 'CYCLE')
            seen.add(agent)
            agent = parents[agent]
    devices, updaters = set(), set()
    for attachment in value['attachments']:
        require(attachment['agentId'] in agents, 'ORPHAN_ATTACHMENT')
        require(attachment['deviceId'] not in devices, 'DUPLICATE_ATTACHMENT')
        require(attachment['updaterId'] not in updaters, 'DUPLICATE_UPDATER')
        require(attachment['deviceId'] not in agents, 'IDENTITY_COLLISION')
        require(attachment['capability']['deviceId'] == attachment['deviceId'], 'DEVICE_CAPABILITY_IDENTITY')
        devices.add(attachment['deviceId']); updaters.add(attachment['updaterId'])
    registrations = [x['updaterId'] for x in value['updaters']]
    require(len(set(registrations)) == len(registrations) and set(registrations) == updaters, 'UPDATER_REGISTRATION')
    return parents


def observation(value, authenticated_agent, previous=None):
    shape('agent-observation', value)
    own = value['agent']['agentId']
    require(own == authenticated_agent, 'UNAUTHORIZED_PEER')
    require(own not in value['directChildAgentIds'] and own != value['observedParentAgentId'], 'CYCLE')
    require(all(x['agentId'] == own and x['deviceId'] != own for x in value['directDevices']), 'OBSERVATION_SCOPE')
    require(len({x['deviceId'] for x in value['directDevices']}) == len(value['directDevices']), 'DUPLICATE_ATTACHMENT')
    if previous and value['observationEventId'] == previous['observationEventId']:
        require(value == previous, 'IDEMPOTENCY_CONFLICT')


def route(value, authority):
    shape('route-snapshot', value)
    parents = topology(authority)
    require(value['routeSnapshotHash'] == route_hash(value), 'ROUTE_HASH')
    require(value['serverId'] == authority['serverId'], 'WRONG_SERVER')
    require(value['topologyVersion'] == authority['topologyVersion'], 'STALE_ROUTE')
    agents = value['orderedAgentIds']
    attachments = [x for x in authority['attachments'] if x['deviceId'] == value['targetDeviceId']]
    require(len(attachments) == 1, 'MISSING_TARGET')
    leaf = attachments[0]
    require(leaf['updaterId'] == value['targetUpdaterId'] and leaf['agentId'] == agents[-1], 'WRONG_LEAF')
    require(agents[0] in {a['agentId'] for a in authority['agents']} and agents[0] not in parents, 'WRONG_ROOT')
    require(all(parents.get(c) == p for p, c in zip(agents, agents[1:])), 'INVALID_ADJACENCY')
    caps = value['capabilitySnapshot']
    require(caps['device'] == leaf['capability'], 'DEVICE_CAPABILITY_IDENTITY')
    require([x['agentId'] for x in caps['agents']] == agents, 'CAPABILITY_ORDER')
    authoritative = {x['agentId']: x for x in authority['agents']}
    for entry in caps['agents']:
        require(entry == authoritative[entry['agentId']] and CAPABILITY in entry['capabilities'], 'CAPABILITY_MISMATCH')
    updater = next(x for x in authority['updaters'] if x['updaterId'] == leaf['updaterId'])
    require(caps['updater'] == updater and EVIDENCE_CAPABILITY in updater['capabilities'], 'CAPABILITY_MISMATCH')


def expected_hop(snapshot, job, direction, index):
    nodes = [('server', snapshot['serverId'])] + [('agent', a) for a in snapshot['orderedAgentIds']] + [('updater', snapshot['targetUpdaterId'])]
    require(0 <= index < len(nodes) - 1, 'HOP_OVERFLOW')
    # Index is a fixed root-to-leaf edge index in BOTH directions.
    sender, receiver = nodes[index:index + 2]
    if direction == 'upstream':
        sender, receiver = receiver, sender
    result = dict(hopIndex=index, direction=direction, senderKind=sender[0], senderId=sender[1], receiverKind=receiver[0], receiverId=receiver[1], routeSnapshotHash=snapshot['routeSnapshotHash'])
    result['hopId'] = digest(dict(serverCommandJobId=job, **result))
    return result


def hop(context, snapshot, job, authenticated_peer, local_peer, direction):
    require(context['direction'] == direction, 'HOP_DIRECTION')
    wanted = expected_hop(snapshot, job, direction, context['hopIndex'])
    require((context['senderKind'], context['senderId']) == tuple(authenticated_peer), 'UNAUTHORIZED_PEER')
    require((context['receiverKind'], context['receiverId']) == tuple(local_peer), 'WRONG_RECEIVER')
    require(context == wanted, 'INVALID_ADJACENCY')


def identity(value):
    j, u, original = value['serverCommandJobId'], value['updaterJobId'], value['originalUpdateJobId']
    require(j not in value['routeSnapshot']['orderedAgentIds'] and u not in value['routeSnapshot']['orderedAgentIds'] and value['targetDeviceId'] not in (j, u), 'IDENTITY_COLLISION')
    require(value['targetDeviceId'] == value['routeSnapshot']['targetDeviceId'], 'TARGET_MISMATCH')
    if value['commandType'] == 'update':
        require(j == u and original is None, 'UPDATE_IDENTITY')
    else:
        require(j != u and original == u, 'ROLLBACK_IDENTITY')


def command(value, authority, authenticated_peer, local_peer, original=None, previous=None):
    shape('routed-command', value)
    command_fingerprint(value)
    identity(value)
    reserved={a['agentId'] for a in authority['agents']} | {a['deviceId'] for a in authority['attachments']}
    require(value['serverCommandJobId'] not in reserved and value['updaterJobId'] not in reserved, 'IDENTITY_COLLISION')
    route(value['routeSnapshot'], authority)
    require(value['payload']['jobId'] == value['updaterJobId'], 'UPDATER_PROJECTION')
    require(value['createdAtUtc'] < value['expiresAtUtc'], 'EXPIRY_WINDOW')
    require(value['routeSnapshot']['createdAtUtc'] <= value['createdAtUtc'], 'ROUTE_TIME')
    hop(value['hopContext'], value['routeSnapshot'], value['serverCommandJobId'], authenticated_peer, local_peer, 'downstream')
    require(local_peer[0] == 'agent', 'ROUTED_UPDATER_INGRESS')
    if value['commandType'] == 'rollback':
        require(original is not None and original['commandType'] == 'update' and original['serverCommandJobId'] == value['originalUpdateJobId'], 'ORIGINAL_UPDATE')
        require(value['routeSnapshot'] == original['routeSnapshot'] and value['targetDeviceId'] == original['targetDeviceId'], 'ROLLBACK_ROUTE')
        require(value['operationCorrelationId'] != original['operationCorrelationId'], 'ROLLBACK_CORRELATION')
        require('explicit-rollback-v1' in value['routeSnapshot']['capabilitySnapshot']['device']['capabilities'], 'ROLLBACK_CAPABILITY')
    if previous:
        require(value['serverCommandJobId'] == previous['serverCommandJobId'] and command_fingerprint(value) == command_fingerprint(previous), 'IDEMPOTENCY_CONFLICT')


def dispatch_gate(value, current_authority):
    parents = topology(current_authority)
    r = value['routeSnapshot']; agents = r['orderedAgentIds']
    require(agents[0] not in parents and all(parents.get(c) == p for p,c in zip(agents,agents[1:])), 'STALE_ROUTE')
    attachment = next((a for a in current_authority['attachments'] if a['deviceId'] == r['targetDeviceId']), None)
    require(attachment is not None and attachment['agentId'] == agents[-1] and attachment['updaterId'] == r['targetUpdaterId'], 'STALE_ROUTE')
    registrations = {a['agentId']:a for a in current_authority['agents']}
    require(all(a in registrations and registrations[a]['contractVersion']=='2.0' and CAPABILITY in registrations[a]['capabilities'] for a in agents), 'CAPABILITY_MISMATCH')
    updater = next((u for u in current_authority['updaters'] if u['updaterId']==r['targetUpdaterId']),None)
    require(updater is not None and updater['contractVersion']=='2.0' and EVIDENCE_CAPABILITY in updater['capabilities'], 'CAPABILITY_MISMATCH')
    if value['commandType']=='rollback':
        require('explicit-rollback-v1' in attachment['capability']['capabilities'], 'ROLLBACK_CAPABILITY')


def status(value, obligation, authenticated_peer, local_peer, previous=None):
    shape('routed-status-event', value)
    event_fingerprint(value)
    identity(value)
    for key in ('contractVersion','commandType','serverCommandJobId','originalUpdateJobId','updaterJobId','operationCorrelationId','targetDeviceId','routeSnapshot'):
        require(value[key] == obligation[key], 'STATUS_IDENTITY')
    hop(value['hopContext'], value['routeSnapshot'], value['serverCommandJobId'], authenticated_peer, local_peer, 'upstream')
    require(authenticated_peer[0] == 'agent', 'RAW_UPDATER_STATUS')
    if value['versionEvidence']['availability'] == 'notObserved':
        require(value['failureEvidence']['agentId'] in obligation['routeSnapshot']['orderedAgentIds'], 'FAILURE_EVIDENCE_AUTHORITY')
        failure_receipt = value['failureEvidence']['originReceipt']
        require(digest(failure_receipt) == value['failureEvidence']['originReceiptHash'], 'FAILURE_PROOF_HASH')
        receipt(failure_receipt)
        source_index = obligation['routeSnapshot']['orderedAgentIds'].index(value['failureEvidence']['agentId'])
        require(source_index >= value['hopContext']['hopIndex'], 'FAILURE_EVIDENCE_AUTHORITY')
        require(failure_receipt['command']['hopContext'] == expected_hop(obligation['routeSnapshot'], obligation['serverCommandJobId'], 'downstream', source_index), 'FAILURE_EVIDENCE_AUTHORITY')
        require(failure_receipt['command']['hopContext']['receiverId']==value['failureEvidence']['agentId'], 'FAILURE_EVIDENCE_AUTHORITY')
        require(failure_receipt['receiptId']==value['failureEvidence']['obligationReceiptId'] and failure_receipt['serverCommandJobId']==obligation['serverCommandJobId'] and failure_receipt['semanticFingerprint']==command_fingerprint(obligation) and failure_receipt['downstreamEverSubmitted'] is False and failure_receipt['obligationState']=='terminal', 'FAILURE_AFTER_SUBMISSION')
    for item in value['physicalEvidence']:
        projected_evidence(item, obligation)
    known = value['physicalEvidence'] + (previous['physicalEvidence'] if previous else [])
    evidence_facts([item['source'] for item in known])
    if previous and value['statusEventId'] == previous['statusEventId']:
        require(event_fingerprint(value) == event_fingerprint(previous), 'STATUS_EVENT_CONFLICT')


def root_status(value, obligation, previous=None):
    """Validate a root envelope; previous means previous LOCAL allocation only."""
    shape('root-status', value)
    root = obligation['routeSnapshot']['orderedAgentIds'][0]
    require(value['rootAgentId'] == root and value['event']['hopContext']['hopIndex'] == 0, 'ROOT_SEQUENCE_OWNER')
    status(value['event'], obligation, ('agent', root), ('server', obligation['routeSnapshot']['serverId']))
    if previous:
        require(previous['event']['serverCommandJobId'] == value['event']['serverCommandJobId'], 'SEQUENCE_JOB_SCOPE')
        require(value['sequence'] >= previous['sequence'], 'STALE_SEQUENCE')
        if value['sequence'] == previous['sequence']:
            require(value == previous, 'SEQUENCE_CONFLICT')
        else:
            require(value['sequence'] == previous['sequence'] + 1, 'SEQUENCE_GAP')
            require(value['event']['statusEventId'] != previous['event']['statusEventId'], 'EVENT_SEQUENCE_REASSIGNMENT')
            require(previous['event']['state'] not in ('completed','failed','rolled_back'), 'TERMINAL_REGRESSION')
        evidence_facts([item['source'] for envelope in (previous, value)
                        for item in envelope['event']['physicalEvidence']])


def server_ingest(value, obligation, receipts, latest=None):
    """Receipt validation is independent of network arrival/allocation order."""
    root_status(value, obligation)
    key = (value['event']['serverCommandJobId'], value['sequence'])
    if key in receipts:
        require(receipts[key] == value, 'SEQUENCE_CONFLICT')
    for prior in receipts.values():
        if prior['event']['serverCommandJobId'] == value['event']['serverCommandJobId'] and prior['event']['statusEventId'] == value['event']['statusEventId']:
            require(prior == value, 'EVENT_SEQUENCE_REASSIGNMENT')
    candidate = latest
    if latest is None or value['sequence'] > latest['sequence']:
        if latest and latest['event']['state'] in ('completed','failed','rolled_back'):
            require(value['event']['state'] == latest['event']['state'], 'TERMINAL_REGRESSION')
        candidate = copy.deepcopy(value)
    # Validate partial known facts across durable receipts, including stale arrivals.
    # Missing phases may arrive later; contradictory known times cannot be committed.
    evidence_facts([item['source'] for envelope in [*receipts.values(), value]
                    for item in envelope['event']['physicalEvidence']])
    # Commit only after every rejection condition has been evaluated.
    receipts[key] = copy.deepcopy(value)
    return candidate


def raw_evidence(value):
    shape('raw-operation-evidence', value)
    require(value['evidenceSource']['recordSha256'] == source_hash(value), 'EVIDENCE_HASH')
    require(value['completedAtUtc'] is None or value['startedAtUtc'] <= value['completedAtUtc'], 'EVIDENCE_TIME')
    execution = value['executionEvidence']
    if execution['state'] == 'confirmed':
        require(execution['sourceRecordId'] is not None and execution['observedAtUtc'] is not None and execution['observedAtUtc'] >= value['startedAtUtc'], 'EXECUTION_PROVENANCE')
        require(value['completedAtUtc'] is None or execution['observedAtUtc'] <= value['completedAtUtc'], 'EXECUTION_TIME')
    else:
        require(execution['sourceRecordId'] is None and execution['observedAtUtc'] is None, 'EXECUTION_PROVENANCE')
    if value['operationPhase'] == 'invoked':
        require(execution['state'] == 'notStarted', 'EXECUTION_PHASE')
    if value['result'] == 'succeeded':
        require(execution['state'] == 'confirmed', 'EXECUTION_UNPROVEN')
    links = value['links']
    if value['result'] == 'succeeded':
        require(links['markerVersion'] is not None and links['markerVersion'] == links['runtimeVersion'] and links['symlinkTarget'] is not None and links['symlinkTarget'].rstrip('/').split('/')[-1] == links['runtimeVersion'] and links['runtimeArtifactSha256'] is not None, 'RUNTIME_PROVENANCE')


def projected_evidence(value, obligation):
    shape('projected-operation-evidence', value)
    raw_evidence(value['source'])
    for key in ('serverCommandJobId','originalUpdateJobId','updaterJobId','operationCorrelationId'):
        require(value[key] == obligation[key], 'EVIDENCE_IDENTITY')
    route = obligation['routeSnapshot']; raw = value['source']
    require(value['routeSnapshotHash'] == route['routeSnapshotHash'], 'EVIDENCE_ROUTE')
    require(value['authorizedLeafAgentId'] == raw['authorizedLeafAgentId'] == route['orderedAgentIds'][-1], 'EVIDENCE_LEAF')
    require(raw['updaterJobId'] == obligation['updaterJobId'] and raw['updaterId'] == route['targetUpdaterId'], 'EVIDENCE_SOURCE')
    require((raw['operationKind'] == 'explicitRollback') == (obligation['commandType'] == 'rollback'), 'EVIDENCE_KIND')


def evidence_facts(records):
    """Validate partial known facts without requiring missing phases or ordinals."""
    phases, journal, ordinals = {}, {}, defaultdict(set)
    physical_sources, confirmations = {}, {}
    for record in records:
        raw_evidence(record)
        r = record
        attempt = (r['updaterId'], r['updaterJobId'], r['operationKind'], r['operationAttemptOrdinal'])
        confirmation = r['executionEvidence']
        if confirmation['state'] == 'confirmed':
            source = (r['updaterId'], confirmation['sourceRecordId'])
            require(source not in physical_sources or physical_sources[source] == attempt, 'PHYSICAL_SOURCE_REUSED')
            require(attempt not in confirmations or confirmations[attempt] == confirmation, 'PHYSICAL_START_CONFLICT')
            physical_sources[source] = attempt
            confirmations[attempt] = confirmation
        key = attempt + (r['operationPhase'],)
        if key in phases:
            require(phases[key] == r, 'EVIDENCE_PHASE_CONFLICT')
        phases[key] = r
        sequence = (r['updaterId'], r['evidenceSource']['journalId'], r['journalSequence'])
        require(sequence not in journal or journal[sequence] == r, 'JOURNAL_SEQUENCE_CONFLICT')
        journal[sequence] = r
        ordinals[attempt[:-1]].add(attempt[-1])
    for attempt, confirmation in confirmations.items():
        complete = phases.get(attempt + ('completed',))
        if complete is not None:
            require(confirmation['observedAtUtc'] <= complete['completedAtUtc'], 'EXECUTION_TIME')
    return phases, ordinals


def evidence_counts(records):
    """Validate a complete source set before counting deduplicated actual phases."""
    phases, ordinals = evidence_facts(records)
    for scope, values in ordinals.items():
        require(values == set(range(1, max(values) + 1)), 'ORDINAL_GAP')
        for ordinal in values:
            attempt = scope + (ordinal,)
            invoked = phases.get(attempt + ('invoked',))
            active = phases.get(attempt + ('activationStarted',))
            complete = phases.get(attempt + ('completed',))
            require(invoked is not None, 'MISSING_INVOCATION')
            for later in (active, complete):
                if later:
                    require(later['authorizedLeafAgentId'] == invoked['authorizedLeafAgentId'], 'EVIDENCE_LEAF')
                    require(later['startedAtUtc'] == invoked['startedAtUtc'] and later['journalSequence'] > invoked['journalSequence'] and later['evidenceSource']['journalId'] == invoked['evidenceSource']['journalId'], 'PHASE_ORDER')
            if complete and active:
                require(complete['journalSequence'] > active['journalSequence'], 'PHASE_ORDER')
            if complete and complete['result'] == 'succeeded':
                require(active is not None, 'MISSING_ACTIVATION')
    counts = {kind: {phase: sum(k[2] == kind and k[4] == phase for k in phases) for phase in ('invoked','activationStarted','completed')} for kind in ('activation','automaticRecovery','explicitRollback')}
    for kind in counts:
        attempts = {k[:4] for k in phases if k[2] == kind}
        confirmed = {a for a in attempts if any(k[:4]==a and r['executionEvidence']['state']=='confirmed' for k,r in phases.items())}
        unresolved = {a for a in attempts if a+('activationStarted',) in phases and a not in confirmed}
        counts[kind]['confirmedPhysicalStarts'] = len(confirmed)
        counts[kind]['unresolvedPhysicalStarts'] = len(unresolved)
    return counts


def root_fingerprint(value):
    body = copy.deepcopy(value)
    body['event']['message'] = body['event']['message'].encode('utf-8').hex()
    return digest(body)


def transcript(value, commands):
    """Check durable command and real adjacent status traces; no consumer runtime."""
    durable, submitted, unknown, queried = {}, set(), set(), set()
    downstream_acceptances, physical = set(), []
    events, sources, forwarded_events, upstream_pending = {}, {}, {}, set()
    root_events, outbox, acknowledged = {}, {}, set()
    attempts, status_attempts, server_online = 0, 0, True
    rollback_by_u = {}
    submission_counts, terminal_verified = defaultdict(int), set()

    def root_commit(actor, job, event, sequence):
        c = commands[job]
        require(actor == c['routeSnapshot']['orderedAgentIds'][0], 'ROOT_SEQUENCE_OWNER')
        event_key = (actor, job, event['statusEventId'])
        require(event_key in events, 'OBSERVE_BEFORE_SEQUENCE')
        identity_key = (job, event['statusEventId'])
        if identity_key in root_events:
            require(root_events[identity_key] == sequence, 'EVENT_SEQUENCE_REASSIGNMENT')
        else:
            sequences = [s for (j, _), s in root_events.items() if j == job]
            require(sequence == (max(sequences) + 1 if sequences else 0), 'SEQUENCE_GAP')
            root_events[identity_key] = sequence
        projected = copy.deepcopy(event)
        projected['hopContext'] = expected_hop(c['routeSnapshot'], job, 'upstream', 0)
        body = dict(event=projected, sequence=sequence, rootAgentId=actor)
        root_status(body, c)
        key = (job, sequence)
        require(key not in outbox or outbox[key] == body, 'SEQUENCE_CONFLICT')
        outbox[key] = body

    for item in value['steps']:
        action = item['action']
        if action == 'physical':
            c = commands[item['job']]
            leaf = c['routeSnapshot']['orderedAgentIds'][-1]
            require(item['actor'] == leaf and (leaf, item['job']) in durable and (leaf, item['job']) in downstream_acceptances, 'PHYSICAL_WITHOUT_ACCEPTANCE')
            projected_evidence(item['projection'], c)
            require(item['projection']['source'] == item['record'], 'EVIDENCE_SOURCE')
            physical.append(item['record'])
            continue
        if action == 'topologyChanged':
            topology(item['topology'])
            continue
        if action in ('serverOutage', 'serverRestored'):
            server_online = action == 'serverRestored'
            continue
        if action == 'restart':
            actor = item['actor']
            unknown.update(key for key in submitted if key[0] == actor)
            require(item['retained'] == sorted(j for a, j in durable if a == actor), 'RESTART_DURABILITY')
            require(item.get('retainedEvents', []) == sorted([j, e] for a, j, e in events if a == actor), 'STATUS_RESTART_DURABILITY')
            require(item.get('retainedUpstreamOutbox', []) == sorted([j, e] for a, j, e in upstream_pending if a == actor), 'STATUS_OUTBOX_RESTART')
            require(item.get('retainedRootOutbox', []) == sorted([j, seq] for j, seq in outbox if commands[j]['routeSnapshot']['orderedAgentIds'][0] == actor and (j, seq) not in acknowledged), 'ROOT_OUTBOX_RESTART')
            continue
        actor, job = item['actor'], item['job']
        key = (actor, job)
        c = commands[job]
        route_agents = c['routeSnapshot']['orderedAgentIds']
        require(actor in route_agents, 'TRACE_ACTOR')
        if action == 'commit':
            require(item['fingerprint'] == command_fingerprint(c) and item['routeSnapshotHash'] == c['routeSnapshot']['routeSnapshotHash'], 'DURABLE_FINGERPRINT')
            require(key not in durable or durable[key] == item['fingerprint'], 'IDEMPOTENCY_CONFLICT')
            if c['commandType'] == 'rollback':
                u = c['originalUpdateJobId']
                require(u not in rollback_by_u or rollback_by_u[u] == job, 'SECOND_ROLLBACK')
                rollback_by_u[u] = job
            durable[key] = item['fingerprint']
        elif action in ('forward', 'ack'):
            require(key in durable, 'WRITE_BEFORE_FORWARD' if action == 'forward' else 'WRITE_BEFORE_ACK')
            if action == 'forward':
                require(item['fingerprint'] == durable[key], 'REPLAY_PAYLOAD')
                require(key not in unknown or key in queried, 'QUERY_BEFORE_REPLAY')
                require(key in submitted or item['atUtc'] < c['expiresAtUtc'], 'EXPIRED_FIRST_SUBMISSION')
                wanted = expected_hop(c['routeSnapshot'], job, 'downstream', route_agents.index(actor) + 1)
                require(item['hopContext'] == wanted, 'INVALID_ADJACENCY')
                require(item['payload'] == c['payload'], 'UPDATER_PROJECTION')
                expected_key = ('rollback:' + c['updaterJobId'] if c['commandType'] == 'rollback' else c['updaterJobId']) if wanted['receiverKind'] == 'updater' else 'command:' + job
                require(item['idempotencyKey'] == expected_key, 'COMMAND_KEY')
                submitted.add(key)
                queried.discard(key)
                attempts += 1
                submission_counts[key] += 1
        elif action == 'downstreamAccepted':
            require(key in submitted, 'ACCEPT_WITHOUT_SUBMISSION')
            require(item['fingerprint'] == durable[key], 'ACCEPTANCE_FINGERPRINT')
            downstream_acceptances.add(key)
        elif action == 'responseLost':
            require(key in submitted, 'LOSS_WITHOUT_SUBMISSION')
            unknown.add(key)
        elif action == 'query':
            require(key in unknown, 'QUERY_WITHOUT_UNCERTAINTY')
            queried.add(key)
            require(item['result'] in ('404', 'accepted', 'terminal', 'unavailable'), 'QUERY_RESULT')
            if item['result'] in ('accepted', 'terminal'):
                require(item['receiptFingerprint'] == durable[key], 'ACCEPTANCE_FINGERPRINT')
                downstream_acceptances.add(key)
                unknown.discard(key)
                if item['result'] == 'terminal':
                    terminal_verified.add(key)
        elif action == 'mutationRejected':
            require(key not in unknown, 'UNKNOWN_TERMINAL')
            require(submission_counts[key] == 1 and item['attemptOrdinal'] == 1 and key not in downstream_acceptances, 'REJECTION_NOT_FIRST_KNOWN_SUBMISSION')
            require(item['requestFingerprint'] == durable[key], 'REPLAY_PAYLOAD')
            shape('error-response', item['response'])
            require(item['response']['status'] in (400, 401, 403, 404, 409, 422) and item['response']['retryable'] is False, 'REJECTION_NOT_DEFINITIVE')
            terminal_verified.add(key)
        elif action == 'terminalize':
            require(key in durable, 'TERMINAL_WITHOUT_OBLIGATION')
            require(key not in unknown, 'UNKNOWN_TERMINAL')
            require(key not in submitted or key in terminal_verified, 'TERMINAL_OUTCOME_UNVERIFIED')
        elif action in ('observe', 'receiveEvent'):
            require(key in durable, 'OBSERVATION_WITHOUT_OBLIGATION')
            event = item['event']
            event_id = event['statusEventId']
            require(event['serverCommandJobId'] == job, 'STATUS_IDENTITY')
            event_key = (actor, job, event_id)
            source_key = (job, event_id)
            fp = event_fingerprint(event)
            if action == 'observe':
                origin = event.get('failureEvidence', {}).get('agentId', route_agents[-1])
                require(actor == origin, 'STATUS_ORIGIN')
                if 'failureEvidence' in event:
                    require(key not in submitted, 'FAILURE_AFTER_SUBMISSION')
                own_index = route_agents.index(actor)
                receiver = ('server', c['routeSnapshot']['serverId']) if own_index == 0 else ('agent', route_agents[own_index - 1])
                status(event, c, ('agent', actor), receiver)
                require(source_key not in sources or sources[source_key] == fp, 'STATUS_EVENT_CONFLICT')
                sources[source_key] = fp
            else:
                # Principal comes from the trace's observed transport context,
                # independently of the claimed event sender and receiver.
                principal = tuple(item['authenticatedPeer'])
                status(event, c, principal, ('agent', actor))
                require(source_key in sources and sources[source_key] == fp, 'STATUS_EVENT_CONFLICT')
                delivery = (principal[1], actor, job, event_id)
                require(delivery in forwarded_events and forwarded_events[delivery] == fp, 'STATUS_RECEIVE_WITHOUT_FORWARD')
                unknown.discard(key)
                if event['state'] in ('completed', 'rolled_back', 'failed'):
                    terminal_verified.add(key)
            require(event_key not in events or event_fingerprint(events[event_key]) == fp, 'STATUS_EVENT_CONFLICT')
            events[event_key] = copy.deepcopy(event)
            if actor == route_agents[0]:
                # Root event dedupe, sequence and exact outbox commit together.
                root_commit(actor, job, event, item['sequence'])
            else:
                upstream_pending.add(event_key)
        elif action == 'forwardEvent':
            event = item['event']
            event_key = (actor, job, event['statusEventId'])
            require(event_key in events, 'STATUS_WRITE_BEFORE_FORWARD')
            require(actor != route_agents[0], 'ROOT_SEQUENCE_OWNER')
            require(event_fingerprint(event) == event_fingerprint(events[event_key]) == sources[(job, event['statusEventId'])], 'STATUS_EVENT_CONFLICT')
            receiver = route_agents[route_agents.index(actor) - 1]
            status(event, c, ('agent', actor), ('agent', receiver))
            require(item['idempotencyKey'] == 'event:' + job + ':' + event['statusEventId'], 'STATUS_EVENT_KEY')
            forwarded_events[(actor, receiver, job, event['statusEventId'])] = event_fingerprint(event)
            status_attempts += 1
        elif action == 'ackEvent':
            event_id, child = item['eventId'], item['childAgentId']
            require((actor, job, event_id) in events, 'STATUS_WRITE_BEFORE_ACK')
            require((child, actor, job, event_id) in forwarded_events and route_agents.index(child) == route_agents.index(actor) + 1, 'INVALID_ADJACENCY')
            if actor == route_agents[0]:
                require((job, event_id) in root_events, 'ROOT_OUTBOX_BEFORE_ACK')
            upstream_pending.discard((child, job, event_id))
        elif action == 'allocate':
            require(actor == route_agents[0], 'ROOT_SEQUENCE_OWNER')
            event_key = (actor, job, item['eventId'])
            require(event_key in events, 'OBSERVE_BEFORE_SEQUENCE')
            root_commit(actor, job, events[event_key], item['sequence'])
        elif action == 'sendStatus':
            require(actor == route_agents[0], 'ROOT_SEQUENCE_OWNER')
            seq_key = (job, item['sequence'])
            require(seq_key in outbox and item['body'] == outbox[seq_key] and item['fingerprint'] == root_fingerprint(outbox[seq_key]), 'STATUS_WRITE_BEFORE_SEND')
            require(item['idempotencyKey'] == f'status:{job}:{item["sequence"]}', 'STATUS_KEY')
        elif action == 'ackStatus':
            require(server_online, 'ACK_DURING_OUTAGE')
            require(actor == route_agents[0], 'ROOT_SEQUENCE_OWNER')
            require((job, item['sequence']) in outbox, 'STATUS_ACK')
            acknowledged.add((job, item['sequence']))
        else:
            raise Violation('TRACE_ACTION')
    return dict(logicalJobs=len({j for a, j in durable}), durableObligations=len(durable), deliveryAttempts=attempts, statusRelayAttempts=status_attempts, physical=evidence_counts(physical), pendingStatus=len(set(outbox) - acknowledged), pendingRelayStatus=len(upstream_pending))


def evidence_pages(pages, authoritative_records, projected=False, requests=None):
    """Validate capture coverage against durable raw/projection source, not labels."""
    require(bool(pages), 'EVIDENCE_COVERAGE')
    require(requests is not None and len(requests) == len(pages), 'EVIDENCE_REQUEST_CONTEXT')
    first = pages[0]
    watermark = first['journalHighWatermark']
    raw = lambda r: r['source'] if projected else r
    expected = sorted((r for r in authoritative_records if raw(r)['updaterJobId'] == first['updaterJobId'] and raw(r)['evidenceSource']['journalId'] == first['journalId'] and raw(r)['journalSequence'] <= watermark and (not projected or r['serverCommandJobId'] == first['serverCommandJobId'])), key=lambda r: raw(r)['journalSequence'])
    flattened, cursor = [], 0
    for i, page in enumerate(pages):
        shape('evidence-page' if projected else 'raw-evidence-page',page)
        request = requests[i]
        query = request['query']
        require(set(query).issubset({'afterJournalSequence','limit','journalId','journalHighWatermark'}), 'EVIDENCE_REQUEST')
        require(query.get('afterJournalSequence',0) == page['afterJournalSequence'] and 1 <= query.get('limit',50) <= 100 and len(page['records']) <= query.get('limit',50), 'EVIDENCE_REQUEST')
        expected_kind = 'serverCommand' if projected else 'updaterJob'
        expected_id = page['serverCommandJobId'] if projected else page['updaterJobId']
        require(request['resourceKind'] == expected_kind and request['resourceId'] == expected_id, 'EVIDENCE_RESOURCE')
        bound = 'journalId' in query or 'journalHighWatermark' in query
        require(not bound or ('journalId' in query and 'journalHighWatermark' in query), 'EVIDENCE_SNAPSHOT_BINDING')
        require(i == 0 and page['afterJournalSequence'] == 0 or bound, 'EVIDENCE_SNAPSHOT_BINDING')
        if bound:
            require(query['journalId'] == page['journalId'] and query['journalHighWatermark'] == page['journalHighWatermark'], 'EVIDENCE_SNAPSHOT_MISMATCH')
        if projected:
            require(page['serverCommandJobId'] == first['serverCommandJobId'] and all(r['serverCommandJobId'] == page['serverCommandJobId'] for r in page['records']), 'EVIDENCE_RESOURCE')
        require(page['journalHighWatermark']==watermark and page['journalId']==first['journalId'] and page['updaterJobId']==first['updaterJobId'], 'EVIDENCE_WATERMARK')
        require(page['afterJournalSequence']==cursor, 'EVIDENCE_CURSOR')
        seqs=[raw(r)['journalSequence'] for r in page['records']]
        require(seqs==sorted(set(seqs)) and all(cursor<s<=watermark for s in seqs), 'EVIDENCE_PAGE_ORDER')
        for record in page['records']:
            raw_evidence(raw(record))
            require(raw(record)['updaterJobId']==first['updaterJobId'] and raw(record)['evidenceSource']['journalId']==first['journalId'], 'EVIDENCE_SOURCE')
        flattened.extend(page['records'])
        last=i==len(pages)-1
        if not last:
            require(bool(seqs) and not page['complete'] and page['nextAfterJournalSequence']==seqs[-1], 'EVIDENCE_CURSOR')
            cursor=seqs[-1]
        else:
            require(page['nextAfterJournalSequence'] is None, 'EVIDENCE_CURSOR')
            require(not page['complete'] or page['retentionComplete'], 'EVIDENCE_RETENTION')
    require(flattened == expected, 'EVIDENCE_COVERAGE')
    count_scope = dict(kind='journalSnapshot', updaterJobId=first['updaterJobId'], journalId=first['journalId'], throughJournalSequence=watermark)
    if projected:
        count_scope['serverCommandJobId'] = first['serverCommandJobId']
    result = dict(snapshotProven=False, operationLifetimeProven=False, countScope=count_scope, counts=None)
    if pages[-1]['complete'] and all(x['retentionComplete'] for x in pages):
        result['counts'] = evidence_counts([raw(r) for r in flattened])
        result['snapshotProven'] = bool(flattened) and not any(x['unresolvedPhysicalStarts'] for x in result['counts'].values())
    return result


def evidence_request(page, projected=False, initial=False, limit=100):
    """Fixture request builder; real consumers send the explicit snapshot pair."""
    query = dict(afterJournalSequence=page['afterJournalSequence'], limit=limit)
    if not initial:
        query.update(journalId=page['journalId'], journalHighWatermark=page['journalHighWatermark'])
    return dict(resourceKind='serverCommand' if projected else 'updaterJob', resourceId=page['serverCommandJobId'] if projected else page['updaterJobId'], query=query)


def legacy_migration(value):
    """Assert an evidence-backed one-hop projection preserves existing identities."""
    source=value['source']
    require(value['sourceRecordId'] and value['sourceSha256']==digest(source), 'MIGRATION_EVIDENCE')
    require(all(source.get(k) for k in ('agentId','deviceId','updaterId')), 'MIGRATION_AMBIGUOUS')
    r=value['routeSnapshot']
    require(r['orderedAgentIds']==[source['agentId']] and r['targetDeviceId']==source['deviceId'] and r['targetUpdaterId']==source['updaterId'], 'MIGRATION_ROUTE')
    require(value['projectedJobs']==source['jobs'], 'MIGRATION_IDENTITY')
    route(r,value['authority'])


def receipt(value):
    shape('command-receipt',value)
    c=value['command']
    require(value['serverCommandJobId']==c['serverCommandJobId'] and value['routeSnapshotHash']==c['routeSnapshot']['routeSnapshotHash'] and value['semanticFingerprint']==command_fingerprint(c), 'RECEIPT_IDENTITY')
    require(value['acceptedAtUtc']>=c['createdAtUtc'], 'RECEIPT_TIME')
    require(value['downstreamEverSubmitted'] or value['obligationState'] in ('pending','terminal'), 'RECEIPT_SUBMISSION')


def strict_json(text):
    def pairs(values):
        result={}
        for key,value in values:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key]=value
        return result
    return json.loads(text,object_pairs_hook=pairs)
