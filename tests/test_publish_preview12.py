import copy,importlib.util,pathlib,unittest
p=pathlib.Path(__file__).resolve().parents[1]/'tools/publish_preview12.py'
s=importlib.util.spec_from_file_location('preview12',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class PreviewPublicationTests(unittest.TestCase):
 def setUp(self):
  from unittest.mock import patch
  self.pins=patch.multiple(m,IPA_HASH='a'*64,IPA_BYTES=123)
  self.pins.start();self.addCleanup(self.pins.stop)

 def feed(self):return {'name':'Strata','apps':[{'bundleIdentifier':'other.app','versions':[{'version':'2.0'}]},{'bundleIdentifier':'com.voicematrix.app','versions':[{'version':'0.4.9','buildVersion':'11','sha256':'keep'},{'version':'0.4.9','buildVersion':'6'}]}]}
 def test_preserves_all_old_entries_and_other_apps(self):
  f=self.feed();old=copy.deepcopy(f);entry={'version':'0.4.9','buildVersion':'12'};r=m.new_feed(f,entry,"strata-source.json")
  self.assertEqual(f,old);self.assertEqual(r['apps'][0],f['apps'][0]);self.assertEqual(r['apps'][1]['versions'][1:],f['apps'][1]['versions']);self.assertEqual(r['apps'][1]['versions'][0],entry)
 def test_newer_or_conflicting_build_fails_without_mutation(self):
  for v in ({'version':'0.4.9','buildVersion':'12','sha256':'conflict'},{'version':'0.4.9','buildVersion':'13'},{'version':'1.0.0','buildVersion':'1'}):
   with self.subTest(v=v):
    f=self.feed();f['apps'][1]['versions'].insert(0,v);before=copy.deepcopy(f)
    with self.assertRaises(AssertionError):m.new_feed(f,dict(downloadURL="expected",size=m.IPA_BYTES,sha256=m.IPA_HASH),"strata-source.json")
    self.assertEqual(f,before)
 def test_missing_or_duplicate_voice_app_and_missing_build11_fail(self):
  for f in ({'apps':[]},{'apps':self.feed()['apps']*2},{'apps':[{'bundleIdentifier':'com.voicematrix.app','versions':[{'version':'0.4.9','buildVersion':'6'}]}]}):
   with self.assertRaises(AssertionError):m.new_feed(f,dict(downloadURL="expected",size=m.IPA_BYTES,sha256=m.IPA_HASH),"strata-source.json")
 def test_uploaded_asset_identity_fail_closed(self):
  a=dict(name=m.IPA,state='uploaded',size=m.IPA_BYTES,digest='sha256:'+m.IPA_HASH,browser_download_url=f'https://github.com/{m.REPO}/releases/download/{m.TAG}/{m.IPA}')
  m.validate_asset(a)
  for k,v in [('name','old.ipa'),('state','open'),('size',1),('digest','sha256:wrong'),('browser_download_url','https://example.com')]:
   with self.subTest(k=k),self.assertRaises(AssertionError):m.validate_asset({**a,k:v})
 def test_gate_rejects_other_source_run_repo_and_failure(self):
  a=dict(head_sha=m.SOURCE,path='.github/workflows/iphone-build12.yml',status='completed',conclusion='success',repository={'full_name':m.DEV})
  m.validate_run(a,m.SOURCE,a['path'])
  for k,v in [('head_sha','wrong'),('path','wrong'),('status','in_progress'),('conclusion','failure'),('repository',{'full_name':'other/repo'})]:
   with self.subTest(k=k),self.assertRaises(AssertionError):m.validate_run({**a,k:v},m.SOURCE,a['path'])
 def test_no_replace_flags_and_draft_before_catalog(self):
  t=p.read_text();self.assertNotIn('--clobber',t);self.assertIn("'--draft','--prerelease'",t);self.assertIn('force=False',t);self.assertLess(t.index("{'draft':False"),t.index("catalog_commit=sync_catalogs(entry)"))
  self.assertIn('Not completed 1.0.0',m.NOTES);self.assertIn('Physical-iPhone',m.NOTES)

 def test_representative_build11_feeds_and_idempotent_retry(self):
  base=p.parents[1]/'tests/fixtures/preview12'
  for name in m.FEEDS:
   path=base/name
   f=__import__('json').loads(path.read_text());before=copy.deepcopy(f)
   entry=dict(version='0.4.9',buildVersion='12',downloadURL='test',size=m.IPA_BYTES,sha256=m.IPA_HASH,date='2026-11-15')
   r=m.new_feed(f,entry,name)
   self.assertEqual(f,before)
   app=lambda x:next(a for a in x['apps'] if a['bundleIdentifier']=='com.voicematrix.app')
   self.assertEqual(app(r)['versions'][1:],app(f)['versions'])
   self.assertEqual(m.new_feed(r,{**entry,'date':'2026-11-16'},name),r)
 def test_resume_missing_assets_preserves_verified_existing_assets(self):
  wanted={'one.json':{'size':2,'digest':'sha256:abc'},m.IPA:{'size':m.IPA_BYTES,'digest':'sha256:'+m.IPA_HASH}}
  a={'name':'one.json','state':'uploaded',**wanted['one.json']}
  self.assertEqual(m.missing_assets([a],wanted),[m.IPA])
  with self.assertRaises(AssertionError):m.missing_assets([{**a,'digest':'sha256:wrong'}],wanted)
  with self.assertRaises(AssertionError):m.missing_assets([a,a],wanted)
  with self.assertRaises(AssertionError):m.missing_assets([{**a,'name':'unknown'}],wanted)
 def test_resume_release_must_match_publication_commit(self):
  r=dict(tag_name=m.TAG,target_commitish='abc',prerelease=True,draft=True,body=m.NOTES)
  m.validate_release_identity(r,{'object':{'type':'commit','sha':'abc'}},'abc')
  for bad in ({**r,'target_commitish':'wrong'},{**r,'prerelease':False},{**r,'tag_name':'wrong'}):
   with self.assertRaises(AssertionError):m.validate_release_identity(bad,{'object':{'type':'commit','sha':'abc'}},'abc')

 def test_catalog_cas_conflict_reloads_concurrent_changes_then_idempotent(self):
  from unittest.mock import patch
  import json
  entry=dict(version='0.4.9',buildVersion='12',downloadURL='test',size=m.IPA_BYTES,sha256=m.IPA_HASH)
  fixtures=p.parents[1]/'tests/fixtures/preview12'
  state={'head':'initial','feeds':{n:json.loads((fixtures/n).read_text()) for n in m.FEEDS},'trees':{},'commits':{},'attempts':0}
  def feeds():return state['head'],'base-tree',copy.deepcopy(state['feeds'])
  def api(path,method='GET',body=None):
   if path.endswith('/git/ref/heads/main'):return {'object':{'sha':state['head']}}
   if path.endswith('/git/trees'):
    key='tree'+str(len(state['trees']));state['trees'][key]={x['path']:json.loads(x['content']) for x in body['tree']};return {'sha':key}
   if path.endswith('/git/commits'):
    key='commit'+str(len(state['commits']));state['commits'][key]=body;return {'sha':key}
   if path.endswith('/git/refs/heads/main'):
    self.assertFalse(body['force']);state['attempts']+=1
    if state['attempts']==1:
     state['head']='concurrent';state['feeds']['strata-source.json']['unrelatedConcurrentField']='keep'
     raise m.subprocess.CalledProcessError(1,['gh'])
    commit=state['commits'][body['sha']];self.assertEqual(commit['parents'],[state['head']]);state['head']=body['sha'];state['feeds']=state['trees'][commit['tree']];return {'object':{'sha':state['head']}}
   self.fail(path)
  with patch.object(m,'get_feeds',feeds),patch.object(m,'api',api):
   result=m.sync_catalogs(entry);self.assertEqual(result,state['head']);self.assertEqual(state['attempts'],2)
   self.assertEqual(state['feeds']['strata-source.json']['unrelatedConcurrentField'],'keep')
   self.assertEqual(m.sync_catalogs(entry),result);self.assertEqual(state['attempts'],2)
 def test_draft_create_and_resume_uses_list_not_published_tag_endpoint(self):
  from unittest.mock import patch
  import tempfile,hashlib
  for scenario in ('new','partial','published'):
   with self.subTest(scenario=scenario),tempfile.TemporaryDirectory() as d:
    root=pathlib.Path(d);(root/'release-notes.md').write_text('notes')
    (root/m.IPA).write_bytes(b'ipa');(root/'proof.json').write_bytes(b'proof')
    assets=[m.IPA,'proof.json'];uploads=[];calls=[]
    def asset(name):
     return dict(name=name,state='uploaded',size=(root/name).stat().st_size,digest='sha256:'+hashlib.sha256((root/name).read_bytes()).hexdigest(),browser_download_url=(f'https://github.com/{m.REPO}/releases/download/{m.TAG}/{name}' if scenario=='published' else 'https://github.com/temporary-draft-url'))
    release=dict(id=1,tag_name=m.TAG,target_commitish='publication',body=m.NOTES,prerelease=True,draft=scenario!='published',assets=[asset(m.IPA)] if scenario=='partial' else [asset(n) for n in assets] if scenario=='published' else [])
    state={'tag':None,'release':None if scenario=='new' else release}
    def api(path,method='GET',body=None):
     calls.append((path,method))
     self.assertNotIn('/releases/tags/',path,'Drafts are not found by published tag endpoint')
     if '/releases?per_page=' in path:return [state['release']] if state['release'] else []
     if path.endswith('/git/refs'):
      self.assertIsNone(state['tag']);self.assertEqual(body,dict(ref='refs/tags/'+m.TAG,sha='publication'));state['tag']={'object':{'type':'commit','sha':'publication'}};return state['tag']
     if path.endswith('/git/ref/tags/'+m.TAG):return state['tag']
     self.fail(path)
    def gh(*args):
     if args[:2]==('release','create'):
      self.assertIsNotNone(state['tag']);self.assertIsNone(state['release']);state['release']=release
     elif args[:2]==('release','upload'):
      name=pathlib.Path(args[3]).name;self.assertNotIn(name,[a['name'] for a in state['release']['assets']]);uploads.append(name);state['release']['assets'].append(asset(name))
     else:self.fail(args)
    with patch.object(m,'api',api),patch.object(m,'optional_api',lambda _:state['tag']),patch.object(m,'gh',gh),patch.object(m,'IPA_BYTES',3),patch.object(m,'IPA_HASH',hashlib.sha256(b'ipa').hexdigest()):
     got=m.ensure_release(root,assets,'publication');self.assertEqual(got['id'],1)
     self.assertEqual(uploads,assets if scenario=='new' else ['proof.json'] if scenario=='partial' else [])
     # Same operation resumes idempotently, including a draft created without automatic tag creation.
     m.ensure_release(root,assets,'publication');self.assertEqual(len(uploads),2 if scenario=='new' else 1 if scenario=='partial' else 0)
 def test_draft_temporary_url_allowed_only_before_publication(self):
  a=dict(name=m.IPA,state='uploaded',size=m.IPA_BYTES,digest='sha256:'+m.IPA_HASH,browser_download_url='https://github.com/temporary-draft')
  m.validate_asset(a,draft=True)
  with self.assertRaises(AssertionError):m.validate_asset(a,draft=False)
  with self.assertRaises(AssertionError):m.validate_asset({**a,'digest':'wrong'},draft=True)
 def test_stage_catalog_creates_unreferenced_commit_without_public_urls(self):
  from unittest.mock import patch
  entry=dict(version='0.4.9',buildVersion='12',downloadURL='test',size=m.IPA_BYTES,sha256=m.IPA_HASH)
  feeds={n:self.feed() for n in m.FEEDS};calls=[]
  def api(path,method='GET',body=None):
   calls.append((path,method,body))
   if path.endswith('/git/trees'):return {'sha':'staged-tree'}
   if path.endswith('/git/commits'):
    self.assertEqual(body['parents'],['base']);return {'sha':'staged-commit'}
   self.fail('Unexpected ref/publication mutation: '+path)
  with patch.object(m,'get_feeds',lambda:('base','tree',feeds)),patch.object(m,'api',api):
   self.assertEqual(m.stage_catalogs(entry),dict(base='base',commit='staged-commit'))
  self.assertEqual(len(calls),2)
  text=p.read_text();self.assertLess(text.index('staged=stage_catalogs(entry)'),text.index("{'draft':False"))
 def test_release_notes_identity_mismatch_rejected(self):
  r=dict(tag_name=m.TAG,target_commitish='abc',prerelease=True,draft=True,body='wrong notes')
  with self.assertRaises(AssertionError):m.validate_release_identity(r,{'object':{'type':'commit','sha':'abc'}},'abc')

class PlatformEvidenceTests(unittest.TestCase):
 def sample(self,platform):
  native=platform=='Linux';passed=list(m.NATIVE_IDS) if native else ['worker.test']
  return dict(sourceCommit=m.REPAIR_SOURCE,successful=True,mode='full' if native else 'windows-worker',passed=passed,skipped=[],testsRun=len(passed),delegatedToLinux=[] if native else list(m.NATIVE_IDS),allDelegatedExecutedSuccessfully=True if native else None)
 def test_both_platform_reports_exact(self):
  for platform in ('Linux','Windows'):m.validate_platform_evidence(self.sample(platform),platform)
 def test_wrong_source_failed_run_or_invalid_counts_rejected(self):
  for platform in ('Linux','Windows'):
   for key,value in [('sourceCommit','wrong'),('successful',False),('mode','wrong'),('testsRun',0),('testsRun',True)]:
    with self.subTest(platform=platform,key=key),self.assertRaises(AssertionError):m.validate_platform_evidence({**self.sample(platform),key:value},platform)
 def test_linux_native_missing_skipped_or_duplicate_rejected(self):
  for kind in ('missing','skip','duplicate','not-confirmed'):
   e=self.sample('Linux')
   if kind=='missing':e['passed'].pop();e['testsRun']-=1
   elif kind=='skip':e['skipped']=[dict(id=e['passed'].pop(),reason='compiler missing')]
   elif kind=='duplicate':e['passed'].append(e['passed'][0]);e['testsRun']+=1
   else:e['allDelegatedExecutedSuccessfully']=False
   with self.assertRaises(AssertionError):m.validate_platform_evidence(e,'Linux')
 def test_windows_exact_delegation_and_no_native_claim(self):
  for kind in ('missing','extra','claim'):
   e=self.sample('Windows')
   if kind=='missing':e['delegatedToLinux'].pop()
   elif kind=='extra':e['delegatedToLinux'].append('unreviewed.test')
   else:e['passed'].append(m.NATIVE_IDS[0]);e['testsRun']+=1
   with self.assertRaises(AssertionError):m.validate_platform_evidence(e,'Windows')
 def test_platform_evidence_before_release(self):
  text=p.read_text();self.assertLess(text.index('platform_proof=validate_platform_artifacts(root)'),text.index('release=ensure_release('))

class CandidateGateTests(unittest.TestCase):
 def setUp(self):
  from unittest.mock import patch
  paths=list(m.REQUIRED_WORKFLOWS)
  runs={100+i:path for i,path in enumerate(paths)}
  bypath={path:run for run,path in runs.items()}
  pins={bypath['.github/workflows/reference-context-full-route.yml']:dict(id=200,sha256='b'*64),bypath['.github/workflows/reference-context-human-holdouts.yml']:dict(id=201,sha256='c'*64)}
  pins[bypath['.github/workflows/overlap-integration12.yml']]=dict(id=202,sha256='a'*64)
  self.patches=patch.multiple(m,OVERLAP_RUN=bypath['.github/workflows/overlap-integration12.yml'],OVERLAP_ARTIFACT=202,OVERLAP_HASH='a'*64,SOURCE='a'*40,REPAIR_SOURCE='a'*40,FULL_UI_SOURCE='a'*40,RUN=90,FULL_UI_RUN=bypath['.github/workflows/character-ui-smoke.yml'],QUEUE_RUN=bypath['.github/workflows/queue-processor.yml'],FULL_ROUTE_RUN=bypath['.github/workflows/reference-context-full-route.yml'],HUMAN_RUN=bypath['.github/workflows/reference-context-human-holdouts.yml'],REQUIRED_RUNS=runs,EVIDENCE_PINS=pins,ARTIFACT=10,RUNTIME_ARTIFACT=11,IPA_BYTES=123,ZIP_HASH='d'*64,IPA_HASH='e'*64,RUNTIME_HASH='f'*64)
  self.patches.start();self.addCleanup(self.patches.stop)

 def test_unreviewed_pins_fail_before_any_external_work(self):
  from unittest.mock import patch
  for name in ('SOURCE','RUN','FULL_UI_RUN','QUEUE_RUN','FULL_ROUTE_RUN','HUMAN_RUN','OVERLAP_RUN','OVERLAP_ARTIFACT','OVERLAP_HASH','ARTIFACT','RUNTIME_ARTIFACT','IPA_BYTES','ZIP_HASH','IPA_HASH','RUNTIME_HASH'):
   with self.subTest(pin=name),patch.object(m,name,None),self.assertRaises(AssertionError):m.require_pins()
  for run in (m.FULL_ROUTE_RUN,m.HUMAN_RUN,m.OVERLAP_RUN):
   pins=copy.deepcopy(m.EVIDENCE_PINS);pins[run]=None
   with self.subTest(evidence=run),patch.object(m,'EVIDENCE_PINS',pins),self.assertRaises(AssertionError):m.require_pins()
   for key in ('id','sha256'):
    pins=copy.deepcopy(m.EVIDENCE_PINS);pins[run][key]=None
    with self.subTest(evidence=run,key=key),patch.object(m,'EVIDENCE_PINS',pins),self.assertRaises(AssertionError):m.require_pins()
  text=p.read_text();self.assertLess(text.index(' require_pins()'),text.index(" validate_run(api(f'repos/{DEV}/actions/runs/{RUN}')"))
 def test_reviewed_pins_are_complete(self):
  m.require_pins()
 def test_missing_wrong_or_duplicate_required_gate_is_rejected(self):
  from unittest.mock import patch
  for mode in ('missing','wrong','duplicate','mismatched-ui'):
   runs=copy.deepcopy(m.REQUIRED_RUNS)
   if mode=='missing':runs.pop(next(iter(runs)))
   elif mode=='wrong':runs[next(iter(runs))]='.github/workflows/old.yml'
   elif mode=='duplicate':runs[next(iter(runs))]=runs[list(runs)[1]]
   else:runs[m.FULL_UI_RUN]='.github/workflows/raw-overlap-policy.yml'
   with self.subTest(mode=mode),patch.object(m,'REQUIRED_RUNS',runs),self.assertRaises(AssertionError):m.require_pins()
 def test_overlap_artifact_must_match_reviewed_evidence_pin(self):
  from unittest.mock import patch
  pins=copy.deepcopy(m.EVIDENCE_PINS);pins[m.OVERLAP_RUN]['id']+=1
  with patch.object(m,'EVIDENCE_PINS',pins),self.assertRaises(AssertionError):m.require_pins()
 def test_exact_same_candidate_gates_before_release(self):
  self.assertEqual(m.SOURCE,'a'*40);self.assertEqual(len(m.REQUIRED_RUNS),len(m.REQUIRED_WORKFLOWS))
  text=p.read_text();self.assertLess(text.index('for run,path in REQUIRED_RUNS.items()'),text.index('release=ensure_release('));self.assertLess(text.index('context_proof=validate_context_artifacts'),text.index('release=ensure_release('))
  self.assertEqual(m.REPAIR_SOURCE,m.SOURCE);self.assertEqual(len(m.NATIVE_IDS),50)
 def test_unpadded_checks_fail_on_any_error_identity_or_padding(self):
  import hashlib
  text='Please close the window and bring the notebook.';h=hashlib.sha256(text.encode()).hexdigest()
  inputs=[dict(voiceID=str(i),file=f'{i}.wav',sha256=str(i)*64,expected=text) for i in range(2)]
  outcomes=[dict(**x,inputSHA256=x['sha256'],actual=text,accepted=True,wordErrorRate=0,error=None,evidence=dict(inputSHA256=x['sha256'],transcriptSHA256=h)) for x in inputs]
  m.validate_unpadded_results(inputs,outcomes)
  for key,value in [('accepted',False),('wordErrorRate',.1),('error','noSpeech'),('file','wrong.wav'),('actual','Wrong')]:
   r=copy.deepcopy(outcomes);r[0][key]=value
   with self.assertRaises(AssertionError):m.validate_unpadded_results(inputs,r)
  r=copy.deepcopy(outcomes);r[0]['evidence']['referenceLeadingSeconds']=.25
  with self.assertRaises(AssertionError):m.validate_unpadded_results(inputs,r)
 def human(self):
  import hashlib
  cases=[];results=[]
  for i in range(4):
   for mode in ('baseline','reference'):
    sha=str(i)*64;text='Exact spoken words';c=dict(id=f'{i}-{mode}',file=f'{i}.wav',mode=mode,expected=text,sha256=sha)
    cases.append(c);results.append(dict(**{k:v for k,v in c.items() if k!='sha256'},accepted=True,error=None,wordErrorRate=0,inputSHA256=sha,sourceSHA256=sha,recognized=text,evidence=dict(inputSHA256=sha,transcriptSHA256=hashlib.sha256(text.encode()).hexdigest(),referenceLeadingSeconds=.25 if mode=='reference' else None)))
  return dict(cases=cases,sources=[dict(speaker_id=i) for i in range(4)],preparationAttempts=[dict(prepared=True) for _ in range(4)]),results
 def test_human_all8_same_original_and_context_receipts(self):
  manifest,results=self.human();m.validate_human_results(manifest,results)
  for mutate in [lambda r:r.pop(),lambda r:r[0].update(accepted=False),lambda r:r[0].update(wordErrorRate=.01),lambda r:r[1]['evidence'].update(referenceLeadingSeconds=None),lambda r:r[0].update(inputSHA256='f'*64)]:
   r=copy.deepcopy(results);mutate(r)
   with self.assertRaises(AssertionError):m.validate_human_results(manifest,r)
class CurrentHeadTests(unittest.TestCase):
 def test_current_head_guard_is_implemented(self):
  self.assertTrue(hasattr(m,'require_current_head'),'Missing candidate branch guard')
 def test_changed_head_rejected_with_reads_only(self):
  from unittest.mock import patch
  self.assertTrue(hasattr(m,'require_current_head'),'Missing candidate branch guard')
  for value in [m.SOURCE,'old-candidate']:
   calls=[]
   def read(path,method='GET',body=None):
    calls.append((path,method,body));self.assertEqual(method,'GET');self.assertIsNone(body)
    self.assertEqual(path,f'repos/{m.DEV}/git/ref/heads/preview/voicematrix-build12');return {'object':{'sha':value}}
   with patch.object(m,'api',read):
    if value==m.SOURCE:m.require_current_head()
    else:
     with self.assertRaises(AssertionError):m.require_current_head()
   self.assertEqual(len(calls),1)
 def test_checks_surround_release_mutations(self):
  text=p.read_text();main=text[text.index('def main():'):]
  self.assertIn(' require_pins()\n require_current_head()\n',main)
  self.assertIn(' require_current_head()\n release=ensure_release(',main)
  self.assertIn(" require_current_head()\n if release['draft']:",main)
class SwiftEncoderSchemaTests(unittest.TestCase):
 def fixtures(self,name):
  import json
  return json.loads((p.parents[1]/'tests/fixtures/preview12/schema'/f'{name}.json').read_text())
 def test_real_swift_human_optional_errors_absent(self):
  f=self.fixtures('human');self.assertTrue(all('error' not in r for r in f['results']))
  m.validate_human_results(f['manifest'],f['results'])
  for value in ['failure','',False,0,{}]:
   r=copy.deepcopy(f['results']);r[0]['error']=value
   with self.assertRaises(AssertionError):m.validate_human_results(f['manifest'],r)
 def test_real_swift_unpadded_optional_errors_absent(self):
  f=self.fixtures('unpadded');self.assertTrue(all('error' not in r for r in f['outcomes']))
  m.validate_unpadded_results(f['inputs'],f['outcomes'])
  for value in ['failure','',False,0,{}]:
   r=copy.deepcopy(f['outcomes']);r[0]['error']=value
   with self.assertRaises(AssertionError):m.validate_unpadded_results(f['inputs'],r)

class UnboundPreparationTests(unittest.TestCase):
 def test_unbound_preparation_fails_before_any_external_work(self):
  from unittest.mock import patch
  with patch.object(m,'SOURCE',None),patch.object(m,'api',side_effect=AssertionError('external work')) as api,patch.object(m,'gh',side_effect=AssertionError('external work')) as gh:
   with self.assertRaisesRegex(AssertionError,'Missing reviewed'):m.main()
   api.assert_not_called();gh.assert_not_called()
 def test_required_gate_paths_are_explicit(self):
  self.assertEqual(len(m.REQUIRED_WORKFLOWS),len(set(m.REQUIRED_WORKFLOWS)))
  self.assertIn('.github/workflows/raw-overlap-policy.yml',m.REQUIRED_WORKFLOWS)
  self.assertIn('.github/workflows/overlap-integration12.yml',m.REQUIRED_WORKFLOWS)

class OverlapReceiptTests(unittest.TestCase):
 def fixture(self):
  ids=('sequential','partial-2s','full-equal','full-quieter','single-A')
  manifest={'cases':[dict(id=x,file=x+'.wav',sha256='a'*64,frames=32000,sampleRate=16000) for x in ids]}
  execution=[dict(case=x,exitCode=0) for x in ids]
  analyses={x:dict(modelRevision='revision',seconds=2,selectionPolicyVersion=5,rawOverlap=dict(version=1,sourceSHA256='a'*64,modelRevision='revision',duration=2,frameDuration=1,speakerSlots=2,counts=[0,2] if x.startswith('full-') else [0,0]),speakerWindows=[dict(speaker='S1',windows=[] if x.startswith('full-') else [dict(start=0,end=1)])]) for x in ids}
  return manifest,execution,analyses
 def test_complete_bound_raw_evidence(self):
  m.validate_overlap_receipts(*self.fixture())
 def test_missing_duplicate_failed_source_or_coverage_rejected(self):
  for mutate in (lambda f:f[0]['cases'].pop(),lambda f:f[1].append(f[1][0]),lambda f:f[1][0].update(exitCode=1),lambda f:f[2]['single-A']['rawOverlap'].update(sourceSHA256='b'*64),lambda f:f[2]['single-A']['rawOverlap'].update(counts=[]),lambda f:f[2]['single-A'].update(selectionPolicyVersion=4),lambda f:f[2]['single-A']['rawOverlap'].update(counts=[-1,0]),lambda f:f[2]['full-equal']['speakerWindows'][0].update(windows=[dict(start=1,end=2)])):
   f=copy.deepcopy(self.fixture());mutate(f)
   with self.assertRaises(AssertionError):m.validate_overlap_receipts(*f)

class WorkflowTests(unittest.TestCase):
 def test_unbound_workflow_fails_before_candidate_checkout(self):
  import yaml
  import subprocess
  w=yaml.safe_load((p.parents[1]/'.github/workflows/publish-preview12.yml').read_text())
  self.assertEqual(w['on']['push']['branches'],['publish/voicematrix-build12-preview'])
  self.assertEqual(w['concurrency']['cancel-in-progress'],False)
  steps=w['jobs']['publish']['steps']
  for step in steps:
   if 'run' in step:subprocess.run(['bash','-n'],input=step['run'],text=True,check=True)
  guard=next(i for i,s in enumerate(steps) if s.get('name')=='Require reviewed immutable publication pins')
  checkout=next(i for i,s in enumerate(steps) if s.get('with',{}).get('repository')==m.DEV)
  self.assertLess(guard,checkout)
  self.assertEqual(w['jobs']['publish']['runs-on'],'ubuntu-latest')
