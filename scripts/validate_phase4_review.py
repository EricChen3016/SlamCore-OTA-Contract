"""Regressions for independent review findings on Phase 4 contract assertions."""
import copy
import json
from itertools import permutations
from pathlib import Path
import phase4_contract as p
import yaml

FIXTURES = Path(__file__).resolve().parents[1] / 'examples/phase4'


def load(name):
    return json.loads((FIXTURES / name).read_text())


def rejected(code, function):
    try:
        function()
    except p.Violation as exc:
        assert exc.code == code, (code, exc.code)
    else:
        raise AssertionError('Expected rejection: ' + code)


def rehash(record):
    record['evidenceSource']['recordSha256'] = p.source_hash(record)
    return record


def atomic_ingest():
    obligation = load('n-hop-rollback.json')
    terminal = load('root-status.json')
    receipts = {}
    latest = p.server_ingest(terminal, obligation, receipts)
    before = copy.deepcopy((receipts, latest))
    invalid = copy.deepcopy(terminal)
    invalid['sequence'] = 1
    invalid['event'].update(statusEventId='event-R3-reopened', state='rolling_back')
    rejected('TERMINAL_REGRESSION', lambda: p.server_ingest(invalid, obligation, receipts, latest))
    assert (receipts, latest) == before, 'rejected ingest mutated caller state'
    conflict = copy.deepcopy(terminal)
    conflict['event']['message'] = 'different body'
    rejected('SEQUENCE_CONFLICT', lambda: p.server_ingest(conflict, obligation, receipts, latest))
    assert (receipts, latest) == before
    gap = copy.deepcopy(terminal)
    gap['sequence'] = 3
    gap['event']['statusEventId'] = 'event-R3-gap-terminal'
    active = copy.deepcopy(terminal)
    active['event'].update(state='rolling_back',errorCode=None,statusEventId='event-R3-earlier-active')
    active['event']['physicalEvidence'] = []
    receipts = {}
    latest = p.server_ingest(active, obligation, receipts)
    latest = p.server_ingest(gap, obligation, receipts, latest)
    assert p.server_ingest(active, obligation, receipts, latest) == latest
    assert p.server_ingest(gap, obligation, receipts, latest) == latest
    assert len(receipts) == 2


def physical_start_time():
    record = load('raw-evidence-page.json')['records'][2]
    record['executionEvidence']['observedAtUtc'] = '2026-09-15T00:03:00Z'
    rejected('EXECUTION_TIME', lambda: p.raw_evidence(rehash(record)))


def physical_source_reuse():
    records = load('raw-evidence-page.json')['records'][:3]
    second = copy.deepcopy(records)
    for record in second:
        record['operationAttemptOrdinal'] = 2
        record['journalSequence'] += 9
        record['links']['journalRecordId'] += '-second'
        rehash(record)
    rejected('PHYSICAL_SOURCE_REUSED', lambda: p.evidence_counts(records + second))


def physical_confirmation_conflict():
    records = load('raw-evidence-page.json')['records'][:3]
    records[1]['executionEvidence'] = copy.deepcopy(records[2]['executionEvidence'])
    rehash(records[1])
    assert p.evidence_counts(records * 2)['activation']['confirmedPhysicalStarts'] == 1
    bad = copy.deepcopy(records)
    bad[1]['executionEvidence']['sourceRecordId'] = 'contradictory-confirmation'
    rehash(bad[1])
    rejected('PHYSICAL_START_CONFLICT', lambda: p.evidence_counts(bad))
    bad = copy.deepcopy(records)
    bad[1]['executionEvidence']['observedAtUtc'] = '2026-09-15T00:01:30Z'
    rehash(bad[1])
    rejected('PHYSICAL_START_CONFLICT', lambda: p.evidence_counts(bad))
    # Delayed resolution in completion retains an immutable earlier physical start.
    records[1]['executionEvidence'] = dict(state='unknown', sourceRecordId=None, observedAtUtc=None)
    rehash(records[1])
    assert p.evidence_counts(records)['activation']['confirmedPhysicalStarts'] == 1
    assert p.evidence_counts(records[:2])['activation']['unresolvedPhysicalStarts'] == 1


def uncertain_rejection():
    steps = load('durable-transcript.json')['steps'][:4]
    steps.append(dict(action='terminalize', actor='A1', job='U3', definitiveMutationRejection=True))
    commands = {'U3': load('n-hop-update.json')}
    rejected('UNKNOWN_TERMINAL', lambda: p.transcript({'steps': steps}, commands))
    # Definitive pre-forward rejection is representable without any uncertain send.
    known = [steps[0], dict(action='terminalize', actor='A1', job='U3')]
    assert p.transcript({'steps': known}, commands)['deliveryAttempts'] == 0
    first_rejection = [steps[0], steps[1], steps[2], dict(action='mutationRejected',actor='A1',job='U3',attemptOrdinal=1,requestFingerprint=p.command_fingerprint(commands['U3']),response=load('error-400.json')), dict(action='terminalize',actor='A1',job='U3')]
    rejected('REJECTION_JOURNAL', lambda:p.transcript({'steps':first_rejection},commands))
    # A local terminalize is insufficient: validate the actual U status wire,
    # durable adjacent relay, Root receipt and Server history for the first rejection.
    from validate_phase4_first_rejection import durable_propagation
    durable_propagation()
    retry_rejection = steps[:-1] + [first_rejection[-2],first_rejection[-1]]
    rejected('UNKNOWN_TERMINAL',lambda:p.transcript({'steps':retry_rejection},commands))
    recovered = steps[:-1] + [dict(action='query',actor='A1',job='U3',result='accepted',receiptFingerprint=p.command_fingerprint(commands['U3']))]
    assert p.transcript({'steps': recovered}, commands)['durableObligations'] == 1


def run(report_error):
    checks = [atomic_ingest, physical_start_time, physical_source_reuse,
              physical_confirmation_conflict, uncertain_rejection, fixed_snapshot_reads,
              relayed_origin_proof, adjacent_status_durability,
              cross_phase_time_counts, cross_phase_time_batch, cross_phase_time_prefix,
              cross_phase_time_reverse, cross_phase_time_boundaries,
              attempt_correlation_echo, attempt_correlation_invalid, operation_correlation_lowercase,
              attempt_correlation_structural]
    for check in checks:
        try:
            check()
        except Exception as exc:
            report_error('Phase 4 review regression ' + check.__name__ + ': ' + str(exc))
    return len(checks)


def fixed_snapshot_reads():
    data = load('evidence-read-transcript.json')
    result = p.evidence_pages(data['pages'], data['authoritativeRecords'], requests=data['requests'])
    assert result['snapshotProven'] and result['operationLifetimeProven'] is False
    assert result['countScope']['throughJournalSequence'] == 9
    assert result['counts']['activation']['confirmedPhysicalStarts'] == 1
    requests = copy.deepcopy(data['requests'])
    requests[1]['query'].pop('journalHighWatermark')
    rejected('EVIDENCE_SNAPSHOT_BINDING', lambda: p.evidence_pages(data['pages'], data['authoritativeRecords'], requests=requests))
    requests = copy.deepcopy(data['requests'])
    requests[1]['query']['journalHighWatermark'] = 12
    rejected('EVIDENCE_SNAPSHOT_MISMATCH', lambda: p.evidence_pages(data['pages'], data['authoritativeRecords'], requests=requests))
    requests = copy.deepcopy(data['requests'])
    requests[1]['query']['journalId'] = 'foreign-journal'
    rejected('EVIDENCE_SNAPSHOT_MISMATCH', lambda: p.evidence_pages(data['pages'], data['authoritativeRecords'], requests=requests))
    requests = copy.deepcopy(data['requests'])
    requests[1]['resourceId'] = 'different-U'
    rejected('EVIDENCE_RESOURCE', lambda: p.evidence_pages(data['pages'], data['authoritativeRecords'], requests=requests))
    pages = copy.deepcopy(data['pages'])
    pages[1]['journalHighWatermark'] = 12
    rejected('EVIDENCE_SNAPSHOT_MISMATCH', lambda: p.evidence_pages(pages, data['authoritativeRecords'], requests=data['requests']))
    pages = copy.deepcopy(data['pages'])
    pages[0]['operationLifetimeProven'] = True
    rejected('SCHEMA',lambda:p.evidence_pages(pages,data['authoritativeRecords'],requests=data['requests']))
    # Same after=3 belongs to a separate concurrent snapshot at watermark 12.
    pages = copy.deepcopy(data['pages'])
    for page in pages:
        page['journalHighWatermark'] = 12
    pages[1]['records'] += data['authoritativeRecords'][-3:]
    requests = [p.evidence_request(pages[0],initial=True), p.evidence_request(pages[1])]
    newer = p.evidence_pages(pages,data['authoritativeRecords'],requests=requests)
    assert newer['snapshotProven'] and newer['counts']['activation']['confirmedPhysicalStarts'] == 2
    assert newer['operationLifetimeProven'] is False
    # A valid old snapshot is explicitly bounded; it cannot claim lifetime proof.
    lower = copy.deepcopy(data['pages'][0])
    lower.update(journalHighWatermark=3,complete=True,nextAfterJournalSequence=None)
    result = p.evidence_pages([lower],data['authoritativeRecords'],requests=[p.evidence_request(lower)])
    assert result['snapshotProven'] and result['countScope']['throughJournalSequence'] == 3
    assert result['operationLifetimeProven'] is False


def relayed_origin_proof():
    command = load('n-hop-update.json')
    leaf = load('leaf-before-forward-failure.json')
    p.status(leaf,command,('agent','A3'),('agent','A2'))
    relay = copy.deepcopy(leaf)
    relay['hopContext'] = p.expected_hop(command['routeSnapshot'],'U3','upstream',1)
    p.status(relay,command,('agent','A2'),('agent','A1'),leaf)
    root = load('never-forwarded-history.json')['items'][0]
    p.root_status(root,command)
    assert p.event_fingerprint(root['event']) == p.event_fingerprint(leaf)
    assert root['event']['failureEvidence'] == leaf['failureEvidence']
    receipts = {}
    assert p.server_ingest(root,command,receipts) == root
    assert p.server_ingest(root,command,receipts,root) == root and len(receipts)==1
    bad = copy.deepcopy(leaf)
    bad['failureEvidence'].pop('originReceipt')
    rejected('SCHEMA',lambda:p.status(bad,command,('agent','A3'),('agent','A2')))
    bad = copy.deepcopy(leaf)
    bad['failureEvidence']['originReceipt']['acceptedAtUtc'] = '2026-09-15T00:00:03Z'
    rejected('FAILURE_PROOF_HASH',lambda:p.status(bad,command,('agent','A3'),('agent','A2')))
    bad['failureEvidence']['originReceiptHash'] = p.digest(bad['failureEvidence']['originReceipt'])
    rejected('STATUS_EVENT_CONFLICT',lambda:p.status(bad,command,('agent','A3'),('agent','A2'),leaf))
    bad = copy.deepcopy(leaf)
    bad['failureEvidence']['agentId'] = 'A4'
    rejected('FAILURE_EVIDENCE_AUTHORITY',lambda:p.status(bad,command,('agent','A3'),('agent','A2')))
    bad = copy.deepcopy(leaf)
    bad['failureEvidence']['originReceipt']['downstreamEverSubmitted'] = True
    bad['failureEvidence']['originReceiptHash'] = p.digest(bad['failureEvidence']['originReceipt'])
    rejected('FAILURE_AFTER_SUBMISSION',lambda:p.status(bad,command,('agent','A3'),('agent','A2')))
    rejected('UNAUTHORIZED_PEER',lambda:p.status(leaf,command,('agent','A4'),('agent','A2')))
    data = load('never-forwarded-transcript.json')
    assert p.transcript(data,{'U3':command}) == data['expected']


def adjacent_status_durability():
    data = load('durable-transcript.json')
    commands = {'U3':load('n-hop-update.json'),'R3':load('n-hop-rollback.json')}
    assert p.transcript(data,commands) == data['expected']
    assert data['expected']['statusRelayAttempts'] == 8
    receive = next(i for i,s in enumerate(data['steps']) if s['action']=='receiveEvent')
    forward = next(i for i,s in enumerate(data['steps']) if s['action']=='forwardEvent')
    restart = next(i for i,s in enumerate(data['steps']) if s['action']=='restart' and s.get('retainedEvents'))
    def mutation(index, modify, code):
        bad = copy.deepcopy(data)
        modify(bad['steps'][index])
        rejected(code,lambda:p.transcript(bad,commands))
    mutation(receive,lambda s:s['event'].update(message='changed by middle Agent'),'STATUS_EVENT_CONFLICT')
    mutation(receive,lambda s:s.update(authenticatedPeer=['agent','A4']),'UNAUTHORIZED_PEER')
    mutation(receive,lambda s:s.update(actor='A1'),'WRONG_RECEIVER')
    mutation(forward,lambda s:s.update(actor='A2'),'STATUS_WRITE_BEFORE_FORWARD')
    mutation(restart,lambda s:s.update(retainedEvents=[]),'STATUS_RESTART_DURABILITY')
    mutation(restart,lambda s:s.update(retainedUpstreamOutbox=[]),'STATUS_OUTBOX_RESTART')
    # A receive cannot be replaced with an ACK before its local durable commit.
    bad=copy.deepcopy(data)
    original=bad['steps'][receive]
    bad['steps'][receive]=dict(action='ackEvent',actor='A2',job='U3',eventId=original['event']['statusEventId'],childAgentId='A3')
    rejected('STATUS_WRITE_BEFORE_ACK',lambda:p.transcript(bad,commands))
    # Root outbox is committed with receive; restart cannot erase its exact body.
    root_restart=next(i for i,s in enumerate(data['steps']) if s['action']=='restart' and s.get('retainedRootOutbox'))
    mutation(root_restart,lambda s:s.update(retainedRootOutbox=[]),'ROOT_OUTBOX_RESTART')
    allocate=next(i for i,s in enumerate(data['steps']) if s['action']=='allocate')
    mutation(allocate,lambda s:s.update(actor='A2'),'ROOT_SEQUENCE_OWNER')


def time_status(records=None, sequence=0):
    value = load('cross-phase-time-status.json')
    if records is not None:
        template = value['event']['physicalEvidence'][0]
        value['event']['physicalEvidence'] = [dict(copy.deepcopy(template), source=copy.deepcopy(r)) for r in records]
    value['sequence'] = sequence
    value['event']['statusEventId'] = 'known-time-' + str(sequence)
    return value


def time_records():
    return [item['source'] for item in time_status()['event']['physicalEvidence']]


def cross_phase_time_counts():
    records = time_records()
    # Each record is valid: the failed completion has no confirmed time of its own.
    for record in records:
        p.raw_evidence(record)
    for order in permutations(records):
        before = copy.deepcopy(order)
        rejected('EXECUTION_TIME', lambda: p.evidence_counts(order))
        assert order == before


def cross_phase_time_batch():
    value = time_status()
    obligation = load('n-hop-update.json')
    rejected('EXECUTION_TIME', lambda: p.root_status(value, obligation))
    receipts, latest = {}, None
    before = copy.deepcopy((receipts, latest, value))
    rejected('EXECUTION_TIME', lambda: p.server_ingest(value, obligation, receipts, latest))
    assert (receipts, latest, value) == before


def cross_phase_time_prefix():
    records = time_records()
    obligation = load('n-hop-update.json')
    prefix = time_status(records[:2], 0)
    completion = time_status(records[2:], 1)
    allocation_prefix = copy.deepcopy(prefix)
    allocation_prefix['event'].update(state='installing', progressPercent=50, errorCode=None)
    p.root_status(allocation_prefix, obligation)
    rejected('EXECUTION_TIME', lambda: p.root_status(completion, obligation, allocation_prefix))
    receipts = {}
    latest = p.server_ingest(prefix, obligation, receipts)
    before = copy.deepcopy((receipts, latest, completion))
    rejected('EXECUTION_TIME', lambda: p.server_ingest(completion, obligation, receipts, latest))
    assert (receipts, latest, completion) == before
    assert p.server_ingest(prefix, obligation, receipts, latest) == latest


def cross_phase_time_reverse():
    records = time_records()
    obligation = load('n-hop-update.json')
    # Completion-only is partial knowledge, not a missing-invocation error.
    # Cover both stale lower sequence and later higher sequence arrival.
    for completion_sequence, prefix_sequence in ((1, 0), (0, 1)):
        completion = time_status(records[2:], completion_sequence)
        prefix = time_status(records[:2], prefix_sequence)
        receipts = {}
        latest = p.server_ingest(completion, obligation, receipts)
        before = copy.deepcopy((receipts, latest, prefix))
        rejected('EXECUTION_TIME', lambda: p.server_ingest(prefix, obligation, receipts, latest))
        assert (receipts, latest, prefix) == before
        assert p.server_ingest(completion, obligation, receipts, latest) == latest


def cross_phase_time_boundaries():
    obligation = load('n-hop-update.json')
    for actual in ('2026-09-15T00:01:00Z', '2026-09-15T00:01:05Z'):
        records = time_records()
        records[1]['executionEvidence']['observedAtUtc'] = actual
        rehash(records[1])
        for order in permutations(records):
            counts = p.evidence_counts(order)['activation']
            assert counts == dict(invoked=1, activationStarted=1, completed=1,
                                 confirmedPhysicalStarts=1, unresolvedPhysicalStarts=0)
        for parts in ((records[:2], records[2:]), (records[2:], records[:2])):
            receipts, latest = {}, None
            for sequence, part in enumerate(parts):
                body = time_status(part, sequence)
                if sequence == 0:
                    body['event'].update(state='installing',errorCode=None)
                latest = p.server_ingest(body, obligation, receipts, latest)
            assert len(receipts) == 2 and latest['sequence'] == 1
    p.evidence_facts(records[2:])
    rejected('MISSING_INVOCATION', lambda: p.evidence_counts(records[2:]))
    # Consistent repeated confirmation and delayed unknown-intent resolution remain valid.
    records[2]['executionEvidence'] = copy.deepcopy(records[1]['executionEvidence'])
    rehash(records[2])
    assert p.evidence_counts(records * 2)['activation']['confirmedPhysicalStarts'] == 1
    records[1]['executionEvidence'] = dict(state='unknown', sourceRecordId=None, observedAtUtc=None)
    rehash(records[1])
    assert p.evidence_counts(records)['activation']['confirmedPhysicalStarts'] == 1
    assert p.evidence_counts(records[:2])['activation']['unresolvedPhysicalStarts'] == 1


def attempt_correlation_echo():
    document = yaml.safe_load((FIXTURES.parents[1] / 'openapi/slamcore-phase4-v1.yaml').read_text())
    header = document['components']['parameters']['CorrelationId']['schema']
    validator = p.Draft202012Validator(header, format_checker=p.FormatChecker())
    cases = [('lowercase', '123e4567-e89b-42d3-a456-426614174000'),
             ('mixedcase', '123E4567-e89B-42d3-A456-426614174000'),
             ('uppercase', '123E4567-E89B-42D3-A456-426614174000')]
    for label, value in cases:
        validator.validate(value)
        error = load('error-correlation-' + label + '.json')
        assert error['correlationId'] == value
        p.shape('error-response', error)
    for label, value in cases:
        error = load('error-correlation-' + label + '.json')
        before = copy.deepcopy(error)
        p.error_correlation(error, value)
        assert error == before and error['correlationId'] == value
        changed = copy.deepcopy(error)
        changed['correlationId'] = value.upper() if label == 'lowercase' else value.lower()
        p.shape('error-response', changed)  # Valid UUID, but not the triggering spelling.
        rejected('ERROR_CORRELATION_ECHO', lambda: p.error_correlation(changed, value))
        assert error == before


def attempt_correlation_invalid():
    document = yaml.safe_load((FIXTURES.parents[1] / 'openapi/slamcore-phase4-v1.yaml').read_text())
    validator = p.Draft202012Validator(document['components']['parameters']['CorrelationId']['schema'],
                                     format_checker=p.FormatChecker())
    for invalid in (None, '', 'not-a-uuid', '123e4567e89b42d3a456426614174000',
                    '123G4567-e89b-42d3-a456-426614174000',
                    ' 123e4567-e89b-42d3-a456-426614174000 ',
                    '123e4567-e89b-42d3-a456-426614174000-',
                    '123e4567-e89b-42d3-a456-4266-14174000',
                    '123e4567-e89b-42d3-a456-426614174000\n'):
        assert not validator.is_valid(invalid)
        diagnostic = load('error-400.json')
        p.error_correlation(diagnostic, invalid)
        assert diagnostic['correlationId'] == '30000000-0000-4000-8000-000000000003'
        echoed_invalid = copy.deepcopy(diagnostic)
        echoed_invalid['correlationId'] = invalid
        rejected('SCHEMA', lambda: p.error_correlation(echoed_invalid, invalid))


def operation_correlation_lowercase():
    for schema, filename in [('routed-command', 'n-hop-update.json'),
                             ('routed-status-event', 'routed-status-event.json'),
                             ('projected-operation-evidence', 'projected-operation-evidence.json')]:
        value = load(filename)
        value['operationCorrelationId'] = '123e4567-e89b-42d3-a456-426614174000'
        p.shape(schema, value)
        for invalid in ('123E4567-E89B-42D3-A456-426614174000',
                        '123E4567-e89B-42d3-A456-426614174000', 'not-a-uuid'):
            value['operationCorrelationId'] = invalid
            rejected('SCHEMA', lambda: p.shape(schema, value))


def attempt_correlation_structural():
    document = yaml.safe_load((FIXTURES.parents[1] / 'openapi/slamcore-phase4-v1.yaml').read_text())
    header = document['components']['parameters']['CorrelationId']['schema']
    wrapper = json.loads((FIXTURES.parents[1] / 'schemas/phase4/error-response.schema.json').read_text())
    invalid_values = [None, 42, '', 'not-a-uuid', '123e4567e89b42d3a456426614174000',
                      '123G4567-e89b-42d3-a456-426614174000',
                      '123e4567-e89b-42d3-a456-426614174000-',
                      '123e4567-e89b-42d3-a456-4266-14174000',
                      '123e4567--e89b-42d3-a456-426614174000',
                      '123e4567_e89b_42d3_a456_426614174000',
                      '123e4567-e89b-42d3-a456-426614174000\n',
                      ' 123e4567-e89b-42d3-a456-426614174000 ']
    for checker in (None, p.FormatChecker()):
        request_validator = p.Draft202012Validator(header, format_checker=checker)
        response_validator = p.Draft202012Validator(wrapper, registry=p.schema_registry(), format_checker=checker)
        for case in ('lowercase', 'mixedcase', 'uppercase'):
            error = load('error-correlation-' + case + '.json')
            assert request_validator.is_valid(error['correlationId'])
            assert response_validator.is_valid(error)
        for invalid in invalid_values:
            assert not request_validator.is_valid(invalid), ('header accepted', repr(invalid), checker)
            error = load('error-400.json')
            error['correlationId'] = invalid
            assert not response_validator.is_valid(error), ('error accepted', repr(invalid), checker)
