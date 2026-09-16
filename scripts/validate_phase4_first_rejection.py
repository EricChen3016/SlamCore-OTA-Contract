"""First known-unaccepted Agent rejection: wire proof and full durable propagation."""
import copy
import json
from pathlib import Path
import phase4_contract as p

FIXTURES = Path(__file__).resolve().parents[1] / 'examples/phase4'


def load(name):
    return json.loads((FIXTURES / name).read_text())


def rejected(code, call):
    try:
        call()
    except p.Violation as exc:
        assert exc.code == code, (code, exc.code)
    else:
        raise AssertionError('Expected rejection: ' + code)


def propagate():
    event = load('first-submission-rejected-event.json')
    command = load('n-hop-update.json')
    p.status(event, command, ('agent', 'A2'), ('agent', 'A1'))
    history = load('first-submission-rejected-history.json')
    p.shape('history-page', history)
    body = history['items'][0]
    assert body['event']['failureEvidence'] == event['failureEvidence']
    receipts = {}
    latest = p.server_ingest(body, command, receipts)
    assert p.server_ingest(copy.deepcopy(body), command, receipts, latest) == latest
    assert len(receipts) == 1 and latest['event']['state'] == 'failed'
    assert latest['event']['versionEvidence'] == dict(availability='notObserved', fromVersion=None, targetVersion=None)
    assert latest['event']['physicalEvidence'] == []
    original = load('first-submission-original-acceptance.json')
    p.receipt(original)
    assert original['receiptId'] == event['failureEvidence']['originReceipt']['receiptId']
    assert original['obligationState'] == 'pending' and original['downstreamEverSubmitted'] is False
    assert event['failureEvidence']['originReceipt']['obligationState'] == 'terminal'
    assert event['failureEvidence']['originReceipt']['downstreamEverSubmitted'] is True


def run(report_error):
    checks = [propagate, durable_propagation, trace_negatives, immutable_proof_and_atomic_ingest]
    for check in checks:
        try:
            check()
        except Exception as exc:
            report_error('Phase 4 first-rejection ' + check.__name__ + ': ' + str(exc))
    return len(checks)


def traced_rejection(event=None):
    event = copy.deepcopy(event or load('first-submission-rejected-event.json'))
    command = load('n-hop-update.json')
    original = load('first-submission-original-acceptance.json')
    proof = event['failureEvidence']['rejectionProof']
    submission, response_record = proof['records']
    fp = p.command_fingerprint(command)
    def step(action, actor, **values):
        return dict(action=action, actor=actor, job='U3', **copy.deepcopy(values))
    steps = [step('commit', 'A1', fingerprint=fp, routeSnapshotHash=command['routeSnapshot']['routeSnapshotHash']),
             step('forward', 'A1', fingerprint=fp, payload=command['payload'], hopContext=p.expected_hop(command['routeSnapshot'],'U3','downstream',1), idempotencyKey='command:U3', atUtc='2026-09-15T00:00:03Z'),
             step('commit', 'A2', fingerprint=fp, routeSnapshotHash=command['routeSnapshot']['routeSnapshotHash'], acceptanceReceipt=original),
             step('journalSubmission', 'A2', journalId=proof['journalId'], record=submission),
             step('forward', 'A2', fingerprint=fp, payload=command['payload'], hopContext=submission['request']['hopContext'], idempotencyKey='command:U3', atUtc=submission['recordedAtUtc'], correlationId=submission['correlationId']),
             step('mutationRejected', 'A2', attemptOrdinal=1, requestFingerprint=fp, response=response_record['response'], authenticatedPeer=['agent','A3'], httpStatus=response_record['httpStatus'], atUtc=response_record['recordedAtUtc'], record=response_record),
             dict(action='restart',actor='A2',retained=['U3'],retainedEvents=[],retainedUpstreamOutbox=[],retainedRootOutbox=[],retainedAcceptances=[original],retainedAttemptJournals=[dict(job='U3',journalId=proof['journalId'],records=proof['records'])]),
             step('replayAcceptance', 'A2', receipt=original),
             step('observe', 'A2', event=event),
             step('terminalize', 'A2')]
    for _ in range(2):
        steps += [step('forwardEvent','A2',event=event,idempotencyKey='event:U3:'+event['statusEventId']),step('receiveEvent','A1',event=event,authenticatedPeer=['agent','A2'],sequence=0)]
    root_event = copy.deepcopy(event)
    root_event['hopContext'] = p.expected_hop(command['routeSnapshot'],'U3','upstream',0)
    body = dict(event=root_event,sequence=0,rootAgentId='A1')
    steps += [step('ackEvent','A1',eventId=event['statusEventId'],childAgentId='A2'),dict(action='serverOutage'),
              step('sendStatus','A1',body=body,sequence=0,fingerprint=p.root_fingerprint(body),idempotencyKey='status:U3:0'),
              dict(action='restart',actor='A1',retained=['U3'],retainedEvents=[['U3',event['statusEventId']]],retainedUpstreamOutbox=[],retainedRootOutbox=[['U3',0]]),dict(action='serverRestored'),
              step('sendStatus','A1',body=body,sequence=0,fingerprint=p.root_fingerprint(body),idempotencyKey='status:U3:0'),step('ackStatus','A1',sequence=0)]
    return steps, command, body


def durable_propagation():
    for rejection in load('first-submission-rejection-cases.json'):
        event = load('first-submission-rejected-event.json')
        failure = event['failureEvidence']
        failure['rejectionProof']['records'][1]['response'].update(rejection)
        failure['rejectionProof']['records'][1]['response'].update(type='urn:slamcore:error:' + rejection['code'].lower(), title=rejection['code'])
        failure['rejectionProof']['records'][1]['httpStatus'] = rejection['status']
        event['errorCode'] = rejection['code']
        failure['rejectionProofHash'] = p.rejection_proof_hash(failure['rejectionProof'])
        steps, command, body = traced_rejection(event)
        original_steps = copy.deepcopy(steps)
        result = p.transcript(dict(steps=steps), {'U3':command})
        assert steps == original_steps
        assert result['logicalJobs'] == 1 and result['durableObligations'] == 2
        assert result['deliveryAttempts'] == 2 and result['statusRelayAttempts'] == 2
        assert result['pendingStatus'] == result['pendingRelayStatus'] == 0
        assert all(all(count == 0 for count in counts.values()) for counts in result['physical'].values())
        receipts = {}
        latest = p.server_ingest(body, command, receipts)
        assert p.server_ingest(copy.deepcopy(body), command, receipts, latest) == latest
        assert latest['event']['failureEvidence'] == event['failureEvidence']
        p.shape('history-page', dict(items=list(receipts.values()), nextCursor=None))
        # Every eligible code still rejects prior unknown or accepted work.
        for action, expected in [('responseLost','UNKNOWN_TERMINAL'),('downstreamAccepted','REJECTION_NOT_FIRST_KNOWN_SUBMISSION')]:
            invalid = copy.deepcopy(steps)
            invalid.insert(5,dict(action=action,actor='A2',job='U3',fingerprint=p.command_fingerprint(command)))
            rejected(expected, lambda:p.transcript(dict(steps=invalid),{'U3':command}))


def trace_negatives():
    steps, command, body = traced_rejection()
    def run_bad(expected, mutate):
        changed = copy.deepcopy(steps)
        mutate(changed)
        rejected(expected, lambda: p.transcript(dict(steps=changed), {'U3':command}))
    def at(items, action, actor='A2'):
        return next(item for item in items if item['action'] == action and item.get('actor') == actor)
    def before_response(items, extra):
        index = next(i for i,s in enumerate(items) if s['action'] == 'mutationRejected')
        items[index:index] = extra
    lost = dict(action='responseLost',actor='A2',job='U3')
    query = dict(action='query',actor='A2',job='U3',result='404')
    run_bad('UNKNOWN_TERMINAL', lambda s: before_response(s,[lost]))
    run_bad('UNKNOWN_TERMINAL', lambda s: before_response(s,[lost,query]))
    accepted = dict(action='downstreamAccepted',actor='A2',job='U3',fingerprint=p.command_fingerprint(command))
    run_bad('REJECTION_NOT_FIRST_KNOWN_SUBMISSION', lambda s: before_response(s,[accepted]))
    run_bad('REJECTION_CHILD', lambda s: at(s,'mutationRejected').update(authenticatedPeer=['agent','A1']))
    run_bad('REJECTION_RESPONSE', lambda s: at(s,'mutationRejected').update(httpStatus=503))
    run_bad('REJECTION_REQUEST', lambda s: at(s,'forward').update(correlationId='00000000-0000-4000-8000-000000000001'))
    run_bad('REJECTION_JOURNAL_RESTART', lambda s: at(s,'restart').update(retainedAttemptJournals=[]))
    run_bad('ACCEPTANCE_RESTART', lambda s: at(s,'restart').update(retainedAcceptances=[]))
    run_bad('ACCEPTANCE_REPLAY', lambda s: at(s,'replayAcceptance').update(receipt=body['event']['failureEvidence']['originReceipt']))
    def missing_outcome(items):
        items[:] = [s for s in items if not (s['action'] in ('mutationRejected','restart') and s.get('actor') == 'A2')]
    run_bad('REJECTION_OUTCOME_UNVERIFIED', missing_outcome)
    def missing_journal(items):
        items[:] = [s for s in items if not (s['action'] in ('journalSubmission','restart') and s.get('actor') == 'A2')]
    run_bad('REJECTION_JOURNAL', missing_journal)
    def no_event(items):
        items[:] = [s for s in items if s['action'] != 'observe']
    run_bad('REJECTION_EVENT_MISSING', no_event)
    def foreign_proof(items):
        failure = at(items,'observe')['event']['failureEvidence']
        failure['rejectionProof']['records'][1]['response']['detail'] = 'Invented different response.'
        failure['rejectionProofHash'] = p.rejection_proof_hash(failure['rejectionProof'])
    run_bad('REJECTION_JOURNAL', foreign_proof)
    def wrong_response(items, status=None, correlation=None):
        step = at(items,'mutationRejected')
        response = copy.deepcopy(step['response'])
        if status is not None: response['status'] = status
        if correlation is not None: response['correlationId'] = correlation
        step['response'] = response
        step['record']['response'] = copy.deepcopy(response)
    run_bad('REJECTION_NOT_DEFINITIVE', lambda s: wrong_response(s,status=503))
    run_bad('REJECTION_RESPONSE', lambda s: wrong_response(s,status=422))
    run_bad('ERROR_CORRELATION_ECHO', lambda s: wrong_response(s,correlation='123e4567-e89b-42d3-a456-426614174000'))
    def second_attempt(items):
        entry = copy.deepcopy(at(items,'journalSubmission'))
        entry['record'].update(journalSequence=2,attemptOrdinal=2)
        before_response(items,[entry,copy.deepcopy(at(items,'forward'))])
    run_bad('REJECTION_NOT_FIRST_KNOWN_SUBMISSION', second_attempt)
    # Other request rejections cannot stand in for a pre-acceptance U outcome.
    for status_code, code in [(400,'VALIDATION_FAILED'),(401,'UNAUTHORIZED_PEER'),(403,'UNAUTHORIZED_PEER'),(404,'RESOURCE_NOT_FOUND'),(409,'IDEMPOTENCY_CONFLICT'),(409,'INVALID_TOPOLOGY'),(409,'UPDATE_ALREADY_RUNNING'),(422,'INCOMPATIBLE_RELEASE')]:
        def unsupported(items):
            response = at(items,'mutationRejected')
            response['response'].update(status=status_code,code=code)
            response['httpStatus'] = status_code
            response['record']['httpStatus'] = status_code
            response['record']['response'] = copy.deepcopy(response['response'])
        run_bad('REJECTION_RESPONSE', unsupported)
    # A write-ahead submission reservation already makes neverForwarded false,
    # even when the observed trace crashes before its transport call.
    reservation = copy.deepcopy(steps[:4])
    never = load('first-submission-rejected-event.json')
    failure = never['failureEvidence']
    failure['stage'] = 'neverForwarded'
    failure.pop('rejectionProof'); failure.pop('rejectionProofHash')
    failure['originReceipt']['downstreamEverSubmitted'] = False
    failure['originReceiptHash'] = p.digest(failure['originReceipt'])
    reservation.append(dict(action='observe',actor='A2',job='U3',event=never))
    rejected('FAILURE_AFTER_SUBMISSION',lambda:p.transcript(dict(steps=reservation),{'U3':command}))
    # Journal tracking must still permit normal uncertainty query/replay; it can
    # never turn the resulting retry rejection into a first known-unaccepted proof.
    recovery = copy.deepcopy(steps[:5]) + [lost,query]
    retry = copy.deepcopy(steps[3]);retry['record'].update(journalSequence=4,attemptOrdinal=2)
    recovery += [retry,copy.deepcopy(steps[4]),accepted]
    result = p.transcript(dict(steps=recovery), {'U3':command})
    assert result['deliveryAttempts'] == 3
    # A later authoritative child terminal event remains a valid recovery outcome.
    # The parent's true submission state does not invalidate the child's distinct
    # neverForwarded proof when the child accepted but never sent to Updater.
    child_event = load('leaf-before-forward-failure.json')
    recovery += [dict(action='commit',actor='A3',job='U3',fingerprint=p.command_fingerprint(command),routeSnapshotHash=command['routeSnapshot']['routeSnapshotHash']),
                 dict(action='observe',actor='A3',job='U3',event=child_event),
                 dict(action='forwardEvent',actor='A3',job='U3',event=child_event,idempotencyKey='event:U3:'+child_event['statusEventId']),
                 dict(action='receiveEvent',actor='A2',job='U3',event=child_event,authenticatedPeer=['agent','A3']),
                 dict(action='terminalize',actor='A2',job='U3')]
    assert p.transcript(dict(steps=recovery), {'U3':command})['deliveryAttempts'] == 3


def immutable_proof_and_atomic_ingest():
    steps, command, body = traced_rejection()
    receipts = {}
    latest = p.server_ingest(body,command,receipts)
    before = copy.deepcopy((receipts,latest))
    bad = copy.deepcopy(body)
    bad['event']['failureEvidence']['rejectionProof']['records'][1]['response']['detail'] = 'Altered proof.'
    rejected('REJECTION_PROOF_HASH',lambda:p.server_ingest(bad,command,receipts,latest))
    assert (receipts,latest) == before
    failure = bad['event']['failureEvidence']
    failure['rejectionProofHash'] = p.rejection_proof_hash(failure['rejectionProof'])
    rejected('SEQUENCE_CONFLICT',lambda:p.server_ingest(bad,command,receipts,latest))
    assert (receipts,latest) == before
    p.status(body['event'],command,('agent','A1'),('server','server-1'))
    rejected('STATUS_EVENT_CONFLICT',lambda:p.status(bad['event'],command,('agent','A1'),('server','server-1'),body['event']))
    # Unicode response text is preserved in proof/event/root hashes, never trimmed.
    event = load('first-submission-rejected-event.json')
    failure = event['failureEvidence']
    failure['rejectionProof']['records'][1]['response']['detail'] = '路由已變更。\n原樣保留 '
    failure['rejectionProofHash'] = p.rejection_proof_hash(failure['rejectionProof'])
    unicode_steps, _, unicode_body = traced_rejection(event)
    p.transcript(dict(steps=unicode_steps),{'U3':command})
    assert unicode_body['event']['failureEvidence'] == failure
