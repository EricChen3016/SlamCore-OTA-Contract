"""Phase 4 positive fixtures, targeted mutation fixtures, and OpenAPI wiring."""
import copy
import hashlib
import json
from pathlib import Path
import yaml
from openapi_spec_validator import validate_spec
import phase4_contract as p

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'examples/phase4'


def load(name):
    return json.loads((FIXTURES / name).read_text())


def apply_changes(value, changes):
    for change in changes:
        parts = change['path'].strip('/').split('/')
        target = value
        for part in parts[:-1]:
            target = target[int(part)] if isinstance(target, list) else target[part]
        key = parts[-1]
        if isinstance(target, list):
            index = int(key)
            if index == len(target):
                target.append(change['value'])
            else:
                target[index] = change['value']
        else:
            target[key] = change['value']


def check_case(check, value, base):
    authority = load('topology.json')
    update, rollback = load('n-hop-update.json'), load('n-hop-rollback.json')
    if check == 'topology':
        p.topology(value)
    elif check == 'observation':
        p.observation(value, 'A4')
    elif check in ('command','replay'):
        p.command(value, authority, ('server','server-1'), ('agent','A1'), original=update, previous=base if check=='replay' else None)
    elif check in ('status','eventReplay'):
        p.status(value, rollback, ('agent','A3'), ('agent','A2'), base if check=='eventReplay' else None)
    elif check in ('root','rootReplay'):
        p.root_status(value, rollback, base if check=='rootReplay' else None)
    elif check == 'raw':
        p.raw_evidence(value)
    elif check == 'projection':
        p.projected_evidence(value, rollback)
    elif check == 'counts':
        p.evidence_counts(value)
    elif check == 'updateFailure':
        p.status(value, update, ('agent','A1'), ('server','server-1'))
    elif check == 'migration':
        p.legacy_migration(value)
    elif check == 'receipt':
        p.receipt(value)
    elif check == 'failureReceipt':
        event=load('update-before-forward-failure.json')
        event['failureEvidence']['originReceipt']=value
        event['failureEvidence']['originReceiptHash']=p.digest(value)
        p.status(event,update,('agent','A1'),('server','server-1'))
    elif check == 'page':
        p.evidence_pages([value],load('raw-evidence-page.json')['records'],requests=[p.evidence_request(value)])
    elif check == 'gate':
        p.dispatch_gate(load('n-hop-rollback.json'),value)
    elif check == 'trace':
        p.require(p.transcript(value, {'U3':update,'R3':rollback}) == value['expected'], 'TRACE_COUNT_MISMATCH')
    else:
        raise AssertionError('Unmapped check: ' + check)


def run(report_error):
    counts = dict(schema=0, semantic=0, negative=0, hashVectors=0, openapiOperations=0)
    def test(label, function):
        try:
            function()
        except Exception as exc:
            report_error(f'Phase 4 {label}: {exc}')

    mappings = {name+'.json': name for name in ['agent-observation','topology','route-snapshot','routed-status-event','root-status','history-page','pending-page','command-receipt','raw-operation-evidence','projected-operation-evidence','raw-evidence-page','evidence-page','event-page','error-response']}
    mappings.update({top+'-'+kind+'.json':'routed-command' for top in ['single-hop','branching','n-hop'] for kind in ['update','rollback']})
    mappings.update({'update-before-forward-failure.json':'routed-status-event','intent-only-evidence-page.json':'raw-evidence-page','never-forwarded-receipt.json':'command-receipt','leaf-before-forward-failure.json':'routed-status-event','never-forwarded-history.json':'history-page'})
    mappings.update({'error-correlation-'+case+'.json':'error-response' for case in ('lowercase','mixedcase','uppercase')})
    for name, schema in mappings.items():
        test(name, lambda n=name,s=schema: p.shape(s, load(n)))
        counts['schema'] += 1
    authority = load('topology.json')
    test('topology', lambda: p.topology(authority)); counts['semantic'] += 1
    test('pure relay registration', lambda: p.observation(load('agent-observation.json'), 'A4')); counts['semantic'] += 1
    for topology_name in ['single-hop','branching','n-hop']:
        original = load(topology_name+'-update.json')
        for kind in ['update','rollback']:
            c = load(topology_name+'-'+kind+'.json')
            for i, agent in enumerate(c['routeSnapshot']['orderedAgentIds']):
                peer = ('server','server-1') if i==0 else ('agent', c['routeSnapshot']['orderedAgentIds'][i-1])
                at_hop = copy.deepcopy(c)
                at_hop['hopContext'] = p.expected_hop(c['routeSnapshot'], c['serverCommandJobId'], 'downstream', i)
                test(topology_name+' '+kind+' '+agent, lambda c=at_hop,a=agent,peer=peer,o=original: p.command(c, authority, peer, ('agent',a),original=o))
                counts['semantic'] += 1
    for name, check in [('routed-status-event.json','status'),('root-status.json','root'),('raw-operation-evidence.json','raw'),('projected-operation-evidence.json','projection'),('physical-operations.json','counts'),('durable-transcript.json','trace'),('legacy-migration.json','migration'),('command-receipt.json','receipt')]:
        test(name+' semantic', lambda n=name,k=check: check_case(k,load(n),load(n))); counts['semantic'] += 1
    def history():
        for row in load('history-page.json')['items']:
            job = row['event']['serverCommandJobId']
            p.root_status(row, load('n-hop-'+('rollback' if job=='R3' else 'update')+'.json'))
    test('unavailable history union', history); counts['semantic'] += 1
    def count_trace():
        value = load('durable-transcript.json')
        result = p.transcript(value, {'U3':load('n-hop-update.json'),'R3':load('n-hop-rollback.json')})
        assert result == value['expected'], (result,value['expected'])
    test('logical/delivery/physical counts', count_trace); counts['semantic'] += 1
    def out_of_order():
        c=load('n-hop-rollback.json'); late=load('root-status.json'); high=copy.deepcopy(late)
        high['sequence']=2; high['event']['statusEventId']='new-terminal-event'
        receipts={}; latest=p.server_ingest(high,c,receipts)
        assert p.server_ingest(late,c,receipts,latest)==high
        assert p.server_ingest(high,c,receipts,latest)==high and len(receipts)==2
    test('out-of-order gap stale exact receipts',out_of_order); counts['semantic'] += 1
    def event_hops():
        c=load('n-hop-rollback.json'); old=load('routed-status-event.json')
        for i in [1,0]:
            new=copy.deepcopy(old);new['hopContext']=p.expected_hop(c['routeSnapshot'],'R3','upstream',i)
            h=new['hopContext'];p.status(new,c,(h['senderKind'],h['senderId']),(h['receiverKind'],h['receiverId']),old)
            assert p.event_fingerprint(new)==p.event_fingerprint(old)
    test('same event different hop envelope',event_hops); counts['semantic'] += 1
    def topology_change():
        c=load('n-hop-update.json');new=copy.deepcopy(authority);new['topologyVersion']=2;new['parentLinks'][1]['parentAgentId']='A1'
        p.topology(new)
        # Accepted jobs use retained authority revision; never re-hash to current.
        p.command(c,authority,('server','server-1'),('agent','A1'))
        try:
            p.command(c,new,('server','server-1'),('agent','A1'))
        except p.Violation as exc:
            assert exc.code=='STALE_ROUTE'
        else:
            raise AssertionError('new dispatch must not silently accept old authority')
    test('accepted snapshot versus changed topology',topology_change); counts['semantic'] += 1
    for vector in load('hash-vectors.json'):
        def vector_test(v=vector):
            unhashed={k:x for k,x in v['route'].items() if k!='routeSnapshotHash'}
            assert p.canonical(unhashed).decode()==v['canonicalUtf8']
            assert hashlib.sha256(v['canonicalUtf8'].encode()).hexdigest()==v['sha256']==p.route_hash(v['route'])
        test('hash '+vector['name'],vector_test); counts['hashVectors'] += 1
    for case in load('negative-cases.json'):
        def negative(c=case):
            baseline=load(c['base']); check_case(c['check'],baseline,baseline)
            value=copy.deepcopy(baseline);apply_changes(value,c['changes'])
            if c.get('rehash'):
                value['routeSnapshot']['routeSnapshotHash']=p.route_hash(value['routeSnapshot'])
                h=value['hopContext'];value['hopContext']=p.expected_hop(value['routeSnapshot'],value['serverCommandJobId'],h['direction'],h['hopIndex'])
            if c.get('rehashSource'):
                value['evidenceSource']['recordSha256']=p.source_hash(value)
            if c.get('rehashSources'):
                for r in value:r['evidenceSource']['recordSha256']=p.source_hash(r)
            try:
                check_case(c['check'],value,baseline)
            except p.Violation as exc:
                assert exc.code==c['expectedCode'], f"expected {c['expectedCode']}, got {exc.code}"
            else:
                raise AssertionError('negative fixture was accepted')
        test('negative '+case['name'],negative);counts['negative'] += 1
    # Independently assert that adding a duplicate raw record never raises counts.
    test('physical exact replay', lambda: p.require(p.evidence_counts(load('physical-operations.json')*2)==p.evidence_counts(load('physical-operations.json')), 'COUNT_REPLAY'))
    counts['semantic'] += 1
    def trust_and_canonical():
        c=load('n-hop-update.json')
        try:p.command(c,authority,('agent','A4'),('agent','A1'))
        except p.Violation as exc:assert exc.code=='UNAUTHORIZED_PEER'
        else:raise AssertionError('body claim substituted for transport identity')
        try:p.strict_json('{"routeId":"first","routeId":"second"}')
        except p.Violation as exc:assert exc.code=='DUPLICATE_JSON_KEY'
        else:raise AssertionError('duplicate JSON key accepted')
        row=dict(event=load('update-before-forward-failure.json'),sequence=0,rootAgentId='A1')
        p.root_status(row,c)
    test('independent peer duplicate keys and pre-forward root history',trust_and_canonical);counts['semantic']+=1
    def explicit_uncertainty():
        page=load('intent-only-evidence-page.json')
        result=p.evidence_pages([page],page['records'],requests=[p.evidence_request(page,initial=True)])
        assert result['snapshotProven'] is False
        assert result['counts']['activation']['activationStarted']==1
        assert result['counts']['activation']['confirmedPhysicalStarts']==0
        assert result['counts']['activation']['unresolvedPhysicalStarts']==1
        check_case('updateFailure',load('update-before-forward-failure.json'),None)
    test('intent-only crash unproven and U never-forwarded failure',explicit_uncertainty);counts['semantic']+=1
    def pagination():
        whole=load('raw-evidence-page.json')
        a=copy.deepcopy(whole);b=copy.deepcopy(whole)
        a['records']=whole['records'][:3];a['complete']=False;a['nextAfterJournalSequence']=3
        b['records']=whole['records'][3:];b['afterJournalSequence']=3
        result=p.evidence_pages([a,b],whole['records'],requests=[p.evidence_request(a,initial=True),p.evidence_request(b)])
        assert result['snapshotProven'] and result['counts']['activation']['activationStarted']==1
        partial=copy.deepcopy(whole);partial['retentionComplete']=False;partial['complete']=False
        assert not p.evidence_pages([partial],whole['records'],requests=[p.evidence_request(partial,initial=True)])['snapshotProven']
        projection=load('evidence-page.json')
        assert p.evidence_pages([projection],projection['records'],True,requests=[p.evidence_request(projection,True,True)])['counts']['explicitRollback']['invoked']==1
    test('raw and projected evidence pagination retention',pagination);counts['semantic']+=1
    def compatibility():
        for name in ['single-hop-update','single-hop-rollback','n-hop-update','n-hop-rollback']:
            p.dispatch_gate(load(name+'.json'),authority)
        changed=copy.deepcopy(authority);changed['topologyVersion']=2
        p.dispatch_gate(load('n-hop-rollback.json'),changed)
    test('exact current capability and unchanged retained route',compatibility);counts['semantic']+=1
    def rollback_uniqueness():
        c=load('n-hop-rollback.json');another=copy.deepcopy(c);another['serverCommandJobId']='R-second'
        steps=[]
        for command in [c,another]:
            steps.append(dict(action='commit',actor='A1',job=command['serverCommandJobId'],fingerprint=p.command_fingerprint(command),routeSnapshotHash=command['routeSnapshot']['routeSnapshotHash']))
        try:p.transcript({'steps':steps},{'R3':c,'R-second':another})
        except p.Violation as exc:assert exc.code=='SECOND_ROLLBACK'
        else:raise AssertionError('second R was accepted')
    test('one logical rollback per U',rollback_uniqueness);counts['semantic']+=1
    def openapi():
        source=ROOT/'openapi/slamcore-phase4-v1.yaml';doc=yaml.safe_load(source.read_text())
        from importlib.machinery import SourceFileLoader
        legacy=SourceFileLoader('legacy_contract_validation',str(ROOT/'scripts/validate-contracts.py')).load_module()
        resolved=copy.deepcopy(doc);legacy.absolute_refs(resolved,source)
        validate_spec(resolved,base_uri=source.as_uri())
        assert str(doc['info']['version'])==(ROOT/'VERSION').read_text().strip()
        # Check every actual operation, its example against the referenced schema,
        # the required headers, and error correlation contract.
        expected = {
            ('/agents/observations','post'):('Server','agent-observation',None),
            ('/topology','get'):('Server',None,'topology'),
            ('/agents/{agentId}/commands','get'):('Server',None,'pending-page'),
            ('/commands','post'):('Agent','routed-command','command-receipt'),
            ('/commands/{serverCommandJobId}','get'):('Agent',None,'command-receipt'),
            ('/commands/{serverCommandJobId}/events','post'):('Agent','routed-status-event',None),
            ('/commands/{serverCommandJobId}/events','get'):('Agent',None,'event-page'),
            ('/jobs/{serverCommandJobId}/status','post'):('Server','root-status',None),
            ('/devices/{targetDeviceId}/history','get'):('Server',None,'history-page'),
            ('/commands/{serverCommandJobId}/evidence','get'):('Agent',None,'evidence-page'),
            ('/jobs/{serverCommandJobId}/evidence','get'):('Server',None,'evidence-page'),
            ('/updates/{updaterJobId}/evidence','get'):('Updater',None,'raw-evidence-page')}
        actual={(path,method) for path,entry in doc['paths'].items() for method in entry if method in ('get','post')}
        assert actual==set(expected), 'Phase 4 endpoint set changed'
        for path,entry in doc['paths'].items():
            for method,operation in entry.items():
                if method not in ('get','post'):continue
                owner,request_schema,response_schema=expected[(path,method)]
                assert operation['x-owner']==owner
                def schema_ref(container):
                    return container['content']['application/json']['schema']['$ref']
                if request_schema:assert schema_ref(operation['requestBody'])=='../schemas/phase4/'+request_schema+'.schema.json'
                if response_schema:
                    code='200' if method=='get' else '202'
                    assert schema_ref(operation['responses'][code])=='../schemas/phase4/'+response_schema+'.schema.json'
                refs={x.get('$ref') for x in operation.get('parameters',[])}
                assert sum(x.get('$ref') == '#/components/parameters/CorrelationId' for x in operation.get('parameters', [])) == 1, (path, 'correlation')
                assert '#/components/parameters/ContractVersion' in refs
                assert '#/components/parameters/'+('EvidenceCapability' if owner=='Updater' else 'RelayCapability') in refs
                if path.endswith('/evidence'):
                    for name,query_name in [('EvidenceJournalId','journalId'),('EvidenceHighWatermark','journalHighWatermark')]:
                        assert '#/components/parameters/'+name in refs
                        parameter=doc['components']['parameters'][name]
                        assert parameter['name']==query_name and parameter['in']=='query'
                if method=='post':assert '#/components/parameters/IdempotencyKey' in refs,(path,'idempotency')
                for container in [operation.get('requestBody',{}),*operation['responses'].values()]:
                    for media in container.get('content',{}).values():
                        schema=media.get('schema',{}).get('$ref','')
                        assert schema.startswith('../schemas/phase4/'),(path,schema)
                        filename=schema.rsplit('/',1)[-1].replace('.schema.json','')
                        for ex in media.get('examples',{}).values():
                            sample=(source.parent/ex['externalValue']).resolve()
                            p.shape(filename,json.loads(sample.read_text()))
                assert {'400','401','403','404','409','422','503'}.issubset(operation['responses']),path
                for code in ['400','401','403','404','409','422','503']:
                    assert schema_ref(operation['responses'][code]) == '../schemas/phase4/error-response.schema.json', (path, code, 'error schema')
                    examples=operation['responses'][code]['content']['application/json']['examples']
                    for ex in examples.values():
                        payload=json.loads((source.parent/ex['externalValue']).read_text())
                        assert payload['status']==int(code) and payload['retryable']==(code=='503'),(path,code)
                assert operation['x-authenticated-peer-required'] is True
                counts['openapiOperations']+=1
        for name,header in [('CorrelationId','X-Correlation-Id'),('IdempotencyKey','Idempotency-Key')]:
            h=doc['components']['parameters'][name]
            assert h['name']==header and h['in']=='header' and h['required'] is True
        for name,value in [('ContractVersion','2.0'),('RelayCapability',p.CAPABILITY),('EvidenceCapability',p.EVIDENCE_CAPABILITY)]:
            parameter=doc['components']['parameters'][name]
            assert parameter['required'] is True and parameter['schema']['const']==value
    test('OpenAPI references headers examples',openapi)
    from validate_phase4_review import run as review_regressions
    counts['reviewRegressions'] = review_regressions(report_error)
    print('Phase 4 validation counts: '+json.dumps(counts,sort_keys=True))
    return counts
