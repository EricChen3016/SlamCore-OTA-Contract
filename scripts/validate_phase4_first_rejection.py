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
    checks = [propagate, durable_propagation, trace_negatives, immutable_proof_and_atomic_ingest, child_acceptance_contradiction, retained_progress_contradiction, stable_rejection_event, no_execution_integrity, retained_terminal_order]
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


def child_acceptance_contradiction():
    steps, command, _ = traced_rejection()
    child_commit = dict(action='commit', actor='A3', job='U3',
                        fingerprint=p.command_fingerprint(command),
                        routeSnapshotHash=command['routeSnapshot']['routeSnapshotHash'])
    # Child acceptance exists before parent transport, during that transport, or
    # appears after the purported pre-acceptance rejection. None fits this proof.
    for index in (4, 5, 6):
        changed = copy.deepcopy(steps)
        changed.insert(index, copy.deepcopy(child_commit))
        rejected('REJECTION_DOWNSTREAM_ACCEPTED', lambda:p.transcript(dict(steps=changed), {'U3':command}))
    # Normal idempotent dispatch to an existing child and response-loss recovery
    # remain legal. They cannot be reclassified as first pre-acceptance rejection.
    for use_query in (False, True):
        recovery = copy.deepcopy(steps[:4]) + [copy.deepcopy(child_commit),copy.deepcopy(steps[4])]
        if use_query:
            recovery += [dict(action='responseLost',actor='A2',job='U3'),
                         dict(action='query',actor='A2',job='U3',result='accepted',receiptFingerprint=p.command_fingerprint(command))]
        else:
            recovery.append(dict(action='downstreamAccepted',actor='A2',job='U3',fingerprint=p.command_fingerprint(command)))
        assert p.transcript(dict(steps=recovery), {'U3':command})['durableObligations'] == 3
    # Independently valid child status/physical facts contradict the parent proof.
    child_status = [copy.deepcopy(child_commit),dict(action='observe',actor='A3',job='U3',event=load('leaf-before-forward-failure.json'))]
    existing = load('durable-transcript.json')['steps']
    child_physical = [copy.deepcopy(child_commit),copy.deepcopy(existing[20]),
                      dict(action='downstreamAccepted',actor='A3',job='U3',fingerprint=p.command_fingerprint(command))]
    child_physical += [copy.deepcopy(x) for x in existing if x['action']=='physical' and x['job']=='U3']
    for source in (child_status, child_physical):
        prefix = copy.deepcopy(steps[:5]) + source
        p.transcript(dict(steps=prefix), {'U3':command})
        rejected('REJECTION_DOWNSTREAM_ACCEPTED',lambda:p.transcript(dict(steps=prefix+copy.deepcopy(steps[5:])), {'U3':command}))
    visible = copy.deepcopy(steps[:5]) + child_physical + [copy.deepcopy(existing[i]) for i in (31,33,34)]
    p.transcript(dict(steps=visible), {'U3':command})
    rejected('REJECTION_KNOWN_PROGRESS',lambda:p.transcript(dict(steps=visible+copy.deepcopy(steps[5:])), {'U3':command}))


def retained_progress_contradiction():
    command = load('n-hop-update.json')
    proof = load('first-submission-rejected-root-status.json')
    known = next(x['event'] for x in load('durable-transcript.json')['steps'] if x['action']=='observe' and x['job']=='U3')
    known['hopContext'] = p.expected_hop(command['routeSnapshot'],'U3','upstream',0)
    for state in ('installing','failed','completed'):
        for physical in (False, True):
            event = copy.deepcopy(known)
            event.update(state=state,errorCode='OPERATION_TIMEOUT' if state=='failed' else None)
            if not physical: event['physicalEvidence'] = []
            for first_is_proof in (False, True):
                for second_sequence in (0, 3, 7):
                    progress = dict(event=copy.deepcopy(event),sequence=3,rootAgentId='A1')
                    first, second = (copy.deepcopy(proof),progress) if first_is_proof else (progress,copy.deepcopy(proof))
                    first['sequence'] = 2
                    second['sequence'] = second_sequence
                    p.root_status(first,command);p.root_status(second,command)
                    receipts = {}
                    latest = p.server_ingest(first,command,receipts)
                    before = copy.deepcopy((receipts,latest))
                    rejected('REJECTION_KNOWN_PROGRESS',lambda:p.server_ingest(second,command,receipts,latest))
                    assert (receipts,latest) == before
                    # Even without a latest projection, durable older receipts rule.
                    rejected('REJECTION_KNOWN_PROGRESS',lambda:p.server_ingest(second,command,receipts))
                    assert (receipts,latest) == before
    # A downstream neverForwarded receipt still proves that child accepted U,
    # despite null versions and empty physical evidence. It contradicts this proof.
    child = load('leaf-before-forward-failure.json')
    child['hopContext'] = p.expected_hop(command['routeSnapshot'],'U3','upstream',0)
    child_body = dict(event=child,sequence=0,rootAgentId='A1')
    for first, second in ((child_body,proof),(proof,child_body)):
        first, second = copy.deepcopy(first), copy.deepcopy(second)
        second['sequence'] = 3
        receipts = {};latest = p.server_ingest(first,command,receipts)
        before = copy.deepcopy((receipts,latest))
        rejected('REJECTION_FAILURE_CONFLICT',lambda:p.server_ingest(second,command,receipts,latest))
        assert (receipts,latest) == before
    # The existing local-allocation and status validators also reject this pairing.
    progress = dict(event=known,sequence=0,rootAgentId='A1')
    next_proof = copy.deepcopy(proof);next_proof['sequence']=1
    rejected('REJECTION_KNOWN_PROGRESS',lambda:p.root_status(next_proof,command,progress))
    rejected('REJECTION_KNOWN_PROGRESS',lambda:p.status(next_proof['event'],command,('agent','A1'),('server','server-1'),known))


def stable_rejection_event():
    steps, command, original = traced_rejection()
    duplicate = copy.deepcopy(original)
    duplicate['event']['statusEventId'] = 'event-U3-A2-first-rejection-duplicate'
    for reverse in (False, True):
        for second_sequence in (0, 3, 7):
            first, second = (duplicate, original) if reverse else (original, duplicate)
            first, second = copy.deepcopy(first), copy.deepcopy(second)
            first['sequence'] = 2;second['sequence'] = second_sequence
            receipts = {};latest = p.server_ingest(first,command,receipts)
            before = copy.deepcopy((receipts,latest))
            rejected('REJECTION_EVENT_REASSIGNMENT',lambda:p.server_ingest(second,command,receipts,latest))
            rejected('REJECTION_EVENT_REASSIGNMENT',lambda:p.server_ingest(second,command,receipts))
            assert (receipts,latest) == before
            assert p.server_ingest(copy.deepcopy(first),command,receipts,latest) == latest
    duplicate['sequence'] = 1
    rejected('REJECTION_EVENT_REASSIGNMENT',lambda:p.root_status(duplicate,command,original))
    rejected('REJECTION_EVENT_REASSIGNMENT',lambda:p.status(duplicate['event'],command,('agent','A1'),('server','server-1'),original['event']))
    # Crash/restart cannot mint a new local event for the persisted terminal proof.
    changed = copy.deepcopy(steps)
    extra = copy.deepcopy(next(x for x in steps if x['action']=='observe'))
    extra['event']['statusEventId'] = duplicate['event']['statusEventId']
    changed.insert(next(i for i,x in enumerate(changed) if x['action']=='terminalize'),extra)
    rejected('REJECTION_EVENT_REASSIGNMENT',lambda:p.transcript(dict(steps=changed),{'U3':command}))
    for restart in (False, True):
        changed = copy.deepcopy(steps)
        if restart:
            retained = copy.deepcopy(next(x for x in steps if x['action']=='restart' and x['actor']=='A2'))
            retained['retainedEvents'] = [['U3',original['event']['statusEventId']]]
            changed.append(retained)
        changed.append(copy.deepcopy(extra))
        rejected('REJECTION_EVENT_REASSIGNMENT',lambda:p.transcript(dict(steps=changed),{'U3':command}))
    # Root must reuse the same allocated sequence for the original event ID.
    changed = copy.deepcopy(steps)
    changed.append(dict(action='allocate',actor='A1',job='U3',eventId=original['event']['statusEventId'],sequence=1))
    rejected('EVENT_SEQUENCE_REASSIGNMENT',lambda:p.transcript(dict(steps=changed),{'U3':command}))
    changed[-1]['sequence'] = 0
    p.transcript(dict(steps=changed),{'U3':command})
    p.root_status(copy.deepcopy(original),command,original)
    # Normal observations are still distinct: installing then completed gets two
    # event IDs and sequences, with normal late/exact replay behavior on Server.
    event = next(x['event'] for x in load('durable-transcript.json')['steps'] if x['action']=='observe' and x['job']=='U3')
    event['hopContext'] = p.expected_hop(command['routeSnapshot'],'U3','upstream',0)
    completed = dict(event=event,sequence=1,rootAgentId='A1')
    installing = copy.deepcopy(completed);installing['sequence']=0
    installing['event'].update(state='installing',statusEventId='event-U3-distinct-installing')
    installing['event']['physicalEvidence'] = installing['event']['physicalEvidence'][:2]
    p.root_status(completed,command,installing)
    for inputs in ((installing,completed),(completed,installing)):
        receipts = {};latest = None
        for body in inputs: latest = p.server_ingest(body,command,receipts,latest)
        assert latest == completed and len(receipts)==2
        assert p.server_ingest(copy.deepcopy(inputs[0]),command,receipts,latest)==completed


def no_execution_integrity():
    command = load('n-hop-update.json')
    first = load('first-submission-rejected-root-status.json')
    leaf = copy.deepcopy(load('never-forwarded-history.json')['items'][0])
    ancestor = copy.deepcopy(leaf)
    event = ancestor['event'];event['statusEventId']='event-U3-A1-never-forwarded'
    failure = event['failureEvidence'];failure['agentId']='A1'
    failure['obligationReceiptId'] = 'receipt-U3-A1-never-forwarded'
    receipt = failure['originReceipt'];receipt['receiptId']=failure['obligationReceiptId']
    receipt['command']['hopContext'] = p.expected_hop(command['routeSnapshot'],'U3','downstream',0)
    failure['originReceiptHash'] = p.digest(receipt)
    for left, right in ((first,ancestor),(leaf,ancestor)):
        for reverse in (False,True):
            a,b = (right,left) if reverse else (left,right)
            a,b = copy.deepcopy(a),copy.deepcopy(b);a['sequence']=0;b['sequence']=3
            p.root_status(a,command);p.root_status(b,command)
            receipts={};latest=p.server_ingest(a,command,receipts)
            before=copy.deepcopy((receipts,latest))
            rejected('REJECTION_FAILURE_CONFLICT',lambda:p.server_ingest(b,command,receipts,latest))
            rejected('REJECTION_FAILURE_CONFLICT',lambda:p.server_ingest(b,command,receipts))
            rejected('REJECTION_FAILURE_CONFLICT',lambda:p.status(b['event'],command,('agent','A1'),('server','server-1'),a['event']))
            assert before==(receipts,latest)
            b['sequence']=1
            rejected('REJECTION_FAILURE_CONFLICT',lambda:p.root_status(b,command,a))
    duplicate=copy.deepcopy(ancestor);duplicate['event']['statusEventId']+='-duplicate';duplicate['sequence']=1
    receipts={};latest=p.server_ingest(ancestor,command,receipts)
    before=copy.deepcopy((receipts,latest))
    rejected('REJECTION_EVENT_REASSIGNMENT',lambda:p.server_ingest(duplicate,command,receipts,latest))
    assert before==(receipts,latest)
    assert p.server_ingest(copy.deepcopy(ancestor),command,receipts,latest)==latest
    # No-execution proofs at two different route origins cannot coexist even in
    # a complete source trace before either proof reaches the other Agent.
    steps,_,_=traced_rejection()
    prefix=copy.deepcopy(steps[:9])
    prefix.insert(1,dict(action='observe',actor='A1',job='U3',event=ancestor['event'],sequence=0))
    rejected('REJECTION_FAILURE_CONFLICT',lambda:p.transcript(dict(steps=prefix),{'U3':command}))


def retained_terminal_order():
    command=load('n-hop-update.json')
    event=next(x['event'] for x in load('durable-transcript.json')['steps'] if x['action']=='observe' and x['job']=='U3')
    event['hopContext']=p.expected_hop(command['routeSnapshot'],'U3','upstream',0)
    for terminal_state in ('completed','failed'):
        terminal=dict(event=copy.deepcopy(event),sequence=0,rootAgentId='A1')
        terminal['event'].update(state=terminal_state,errorCode='OPERATION_TIMEOUT' if terminal_state=='failed' else None)
        for higher_state in ('installing','completed','failed'):
            higher=copy.deepcopy(terminal);higher['sequence']=4
            higher['event'].update(statusEventId='event-U3-impossible-later',state=higher_state,errorCode='OPERATION_TIMEOUT' if higher_state=='failed' else None)
            for a,b in ((terminal,higher),(higher,terminal)):
                p.root_status(a,command);p.root_status(b,command)
                receipts={};latest=p.server_ingest(a,command,receipts)
                before=copy.deepcopy((receipts,latest))
                rejected('TERMINAL_REGRESSION',lambda:p.server_ingest(b,command,receipts,latest))
                rejected('TERMINAL_REGRESSION',lambda:p.server_ingest(b,command,receipts))
                assert before==(receipts,latest)
    # A lower active observation may legitimately arrive after a terminal gap.
    active=copy.deepcopy(terminal);active['event'].update(state='installing',errorCode=None,statusEventId='event-U3-earlier-active')
    terminal['sequence']=4
    for a,b in ((active,terminal),(terminal,active)):
        receipts={};latest=p.server_ingest(a,command,receipts)
        latest=p.server_ingest(b,command,receipts,latest)
        assert latest==terminal and len(receipts)==2
        assert p.server_ingest(copy.deepcopy(a),command,receipts,latest)==terminal

    # Root's real allocation path also rejects a second terminal observation;
    # source and relay can deliver it, but cannot allocate past terminal sequence.
    trace = copy.deepcopy(load('durable-transcript.json'))
    next_event = copy.deepcopy(event)
    next_event.update(statusEventId='event-U3-after-terminal',state='failed',errorCode='OPERATION_TIMEOUT')
    next_event['hopContext']=p.expected_hop(command['routeSnapshot'],'U3','upstream',2)
    trace['steps'] += [dict(action='observe',actor='A3',job='U3',event=copy.deepcopy(next_event)),
                       dict(action='forwardEvent',actor='A3',job='U3',event=copy.deepcopy(next_event),idempotencyKey='event:U3:'+next_event['statusEventId']),
                       dict(action='receiveEvent',actor='A2',job='U3',event=copy.deepcopy(next_event),authenticatedPeer=['agent','A3'])]
    next_event['hopContext']=p.expected_hop(command['routeSnapshot'],'U3','upstream',1)
    trace['steps'] += [dict(action='forwardEvent',actor='A2',job='U3',event=copy.deepcopy(next_event),idempotencyKey='event:U3:'+next_event['statusEventId']),
                       dict(action='receiveEvent',actor='A1',job='U3',event=copy.deepcopy(next_event),authenticatedPeer=['agent','A2'],sequence=1)]
    rejected('TERMINAL_REGRESSION',lambda:p.transcript(trace,{'U3':command,'R3':load('n-hop-rollback.json')}))
