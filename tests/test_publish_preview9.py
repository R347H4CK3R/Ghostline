import copy,importlib.util,pathlib,unittest
p=pathlib.Path(__file__).resolve().parents[1]/'tools/publish_preview9.py'
s=importlib.util.spec_from_file_location('preview9',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class PreviewPublicationTests(unittest.TestCase):
 def feed(self):return {'name':'Strata','apps':[{'bundleIdentifier':'other.app','versions':[{'version':'2.0'}]},{'bundleIdentifier':'com.voicematrix.app','versions':[{'version':'0.4.9','buildVersion':'8','sha256':'keep'},{'version':'0.4.9','buildVersion':'6'}]}]}
 def test_preserves_all_old_entries_and_other_apps(self):
  f=self.feed();old=copy.deepcopy(f);entry={'version':'0.4.9','buildVersion':'9'};r=m.new_feed(f,entry,"strata-source.json")
  self.assertEqual(f,old);self.assertEqual(r['apps'][0],f['apps'][0]);self.assertEqual(r['apps'][1]['versions'][1:],f['apps'][1]['versions']);self.assertEqual(r['apps'][1]['versions'][0],entry)
 def test_newer_or_conflicting_build_fails_without_mutation(self):
  for v in ({'version':'0.4.9','buildVersion':'9','sha256':'conflict'},{'version':'0.4.9','buildVersion':'10'},{'version':'1.0.0','buildVersion':'1'}):
   with self.subTest(v=v):
    f=self.feed();f['apps'][1]['versions'].insert(0,v);before=copy.deepcopy(f)
    with self.assertRaises(AssertionError):m.new_feed(f,dict(downloadURL="expected",size=m.IPA_BYTES,sha256=m.IPA_HASH),"strata-source.json")
    self.assertEqual(f,before)
 def test_missing_or_duplicate_voice_app_and_missing_build8_fail(self):
  for f in ({'apps':[]},{'apps':self.feed()['apps']*2},{'apps':[{'bundleIdentifier':'com.voicematrix.app','versions':[{'version':'0.4.9','buildVersion':'6'}]}]}):
   with self.assertRaises(AssertionError):m.new_feed(f,dict(downloadURL="expected",size=m.IPA_BYTES,sha256=m.IPA_HASH),"strata-source.json")
 def test_uploaded_asset_identity_fail_closed(self):
  a=dict(name=m.IPA,state='uploaded',size=m.IPA_BYTES,digest='sha256:'+m.IPA_HASH,browser_download_url=f'https://github.com/{m.REPO}/releases/download/{m.TAG}/{m.IPA}')
  m.validate_asset(a)
  for k,v in [('name','old.ipa'),('state','open'),('size',1),('digest','sha256:wrong'),('browser_download_url','https://example.com')]:
   with self.subTest(k=k),self.assertRaises(AssertionError):m.validate_asset({**a,k:v})
 def test_gate_rejects_other_source_run_repo_and_failure(self):
  a=dict(head_sha=m.SOURCE,path='.github/workflows/iphone-build9.yml',status='completed',conclusion='success',repository={'full_name':m.DEV})
  m.validate_run(a,m.SOURCE,a['path'])
  for k,v in [('head_sha','wrong'),('path','wrong'),('status','in_progress'),('conclusion','failure'),('repository',{'full_name':'other/repo'})]:
   with self.subTest(k=k),self.assertRaises(AssertionError):m.validate_run({**a,k:v},m.SOURCE,a['path'])
 def test_no_replace_flags_and_draft_before_catalog(self):
  t=p.read_text();self.assertNotIn('--clobber',t);self.assertIn("'--draft','--prerelease'",t);self.assertIn('force=False',t);self.assertLess(t.index("{'draft':False"),t.index("catalog_commit=sync_catalogs(entry)"))
  self.assertIn('Not completed 1.0.0',m.NOTES);self.assertIn('Physical-iPhone',m.NOTES)

 def test_actual_saved_feed_baselines_and_idempotent_retry(self):
  base=p.parents[1]/'tests/fixtures/preview9'
  for name in m.FEEDS:
   path=base/name
   f=__import__('json').loads(path.read_text());before=copy.deepcopy(f)
   entry=dict(version='0.4.9',buildVersion='9',downloadURL='test',size=m.IPA_BYTES,sha256=m.IPA_HASH,date='2026-11-15')
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
  entry=dict(version='0.4.9',buildVersion='9',downloadURL='test',size=m.IPA_BYTES,sha256=m.IPA_HASH)
  fixtures=p.parents[1]/'tests/fixtures/preview9'
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
  entry=dict(version='0.4.9',buildVersion='9',downloadURL='test',size=m.IPA_BYTES,sha256=m.IPA_HASH)
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
