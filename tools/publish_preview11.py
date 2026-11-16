"""Publish only the inspected unfinished build11; never replace old releases."""
import re,base64,copy,datetime,hashlib,json,os,pathlib,subprocess,sys,zipfile
REPO='R347H4CK3R/Ghostline'
DEV='R347H4CK3R/VoiceMatrix-Development'
SOURCE='3b976fe84b6f34b2fd7668baf45533e5b7a377a5'
RUN=43824886971
FULL_UI_RUN=43824887037
FULL_UI_SOURCE=SOURCE
RUNTIME_ARTIFACT=14207263769
RUNTIME_HASH='151b81691a48bb683651cf1052e15a29d7fecda712c952f1a37164c71561f723'
ARTIFACT=14208170051
ZIP_HASH='8381e006784c36d9b431d6f01be1f694f4932ea9513862e1703a2fc765aa9b0a'
IPA_HASH='e2d7d26ce2c7d8fa1ae92c389deead7cb0be83572bd64224b3b7a8fc91fe41d2'
IPA_BYTES=1314598007
TAG='voicematrix-v0.4.9-build11'
IPA='VoiceMatrix-0.4.9-build11.ipa'
FEEDS=('strata-source.json','source.json','livecontainer-test.json')
REPAIR_SOURCE=SOURCE
REQUIRED_RUNS={43824886947: '.github/workflows/reference-context-full-route.yml', 43824886982: '.github/workflows/reference-context-human-holdouts.yml', 43824886979: '.github/workflows/local-pipeline-diagnostic.yml', 43824887108: '.github/workflows/native-app.yml', 43824887028: '.github/workflows/native-character-folder.yml', 43824887037: '.github/workflows/character-ui-smoke.yml', 43824887128: '.github/workflows/bundled-asr-diagnostic.yml', 43824887036: '.github/workflows/queue-processor.yml', 43824887041: '.github/workflows/native-queue.yml', 43824887178: '.github/workflows/queue-recovery.yml'}
FULL_ROUTE_RUN=43824886947
HUMAN_RUN=43824886982
EVIDENCE_PINS={FULL_ROUTE_RUN: {'id':14206628677,'sha256':'4e1fe518fe85dd9bd77d9aa1d81332c0b8163d9f2440dd2bd7dd47b6718455e0'},HUMAN_RUN: {'id':14207090826,'sha256':'c1b367b4dfabe776b7cf00450294e5421105bae7c93fb05c5c2d9c16c320e80a'}}
NATIVE_IDS=['test_diarizer_eof_patch.EOFDiagnosticTests.test_actual_app_boundary_guard_still_rejects_invalid_evidence', 'test_direct_voice_profile.DirectVoiceProfileTests.test_actual_library_import_preserves_prior_profiles', 'test_direct_voice_profile.DirectVoiceProfileTests.test_package_roundtrip_bounds_cancellation_and_preservation', 'test_reference_attempt.ReferenceAttemptTests.test_native_candidate_evidence_and_asset_binding', 'test_reference_candidate_pool.CandidatePoolTests.test_later_clean_turn_is_reachable_without_expanding_preview_budget', 'test_reference_candidate_pool.CandidatePoolTests.test_real_migration_validates_legacy_windows_before_expanding', 'test_rvc_controls.Controls.test_default_strength_is_unchanged', 'test_rvc_controls.Controls.test_invalid_controls_and_missing_required_index_fail', 'test_rvc_controls.Controls.test_no_retrieval_preserves_features_and_allows_missing_index', 'test_rvc_controls.Controls.test_selected_strength_and_shift_reach_synthesizer', 'test_rvc_disk_vectors.DiskVectorTests.test_snapshot_integrity_isolation_and_rejections', 'test_rvc_model_admission.CandidateAdmission.test_exact_model_identity_and_retrieval_pairing', 'test_rvc_native_features.RVCFeatureTests.test_cancellation_before_allocation', 'test_rvc_native_features.RVCFeatureTests.test_disabled_retrieval_needs_no_index_and_preserves_frames', 'test_rvc_native_features.RVCFeatureTests.test_equal_neighbor_weights_have_hand_calculated_result', 'test_rvc_native_features.RVCFeatureTests.test_feature_retrieval_upsampling_and_protection', 'test_rvc_native_features.RVCFeatureTests.test_invalid_shapes_bounds_and_degenerate_neighbors_fail', 'test_rvc_native_features.RVCFeatureTests.test_pitch_interpolation_shift_and_bins', 'test_rvc_native_synthesis.NativeSynthesisTests.test_tensor_bytes_and_reject_malformed_assets_before_inference', 'test_rvc_retrieval_memory.RetrievalMemoryTests.test_bounded_selection_and_exact_sparse_fallback', 'test_rvc_retrieval_pack.RetrievalPackAdmission.test_profile_manifest_cannot_override_file_identity', 'test_character_package.CharacterPackageTests.test_complete_no_stock_artifact_passes_with_explicit_unverified_device_status', 'test_character_package.CharacterPackageTests.test_explicit_build_identity_rejects_reused_package', 'test_character_package.CharacterPackageTests.test_missing_or_tampered_f5_asset_fails', 'test_character_package.CharacterPackageTests.test_self_signed_forged_proof_does_not_override_pinned_hash', 'test_character_package.CharacterPackageTests.test_stock_or_private_reference_payload_is_rejected', 'test_character_package.CharacterPackageTests.test_bundled_private_pairing_token_is_rejected', 'test_character_package.CharacterPackageTests.test_missing_or_modified_license_is_rejected', 'test_character_package.CharacterPackageTests.test_duplicate_and_traversal_archive_names_are_rejected', 'test_character_package.CharacterPackageTests.test_missing_dependency_notice_or_resolved_proof_fails', 'test_character_package.CharacterPackageTests.test_wrong_architecture_or_placeholder_fails', 'test_character_package.CharacterPackageTests.test_rewritten_baseline_manifest_cannot_hide_missing_engine', 'test_character_package.CharacterPackageTests.test_private_or_case_variant_resource_outside_f5_is_rejected', 'test_character_package.CharacterPackageTests.test_download_rejects_bad_hash_and_does_not_replace_existing_file', 'test_character_package.CharacterPackageTests.test_prepare_stages_exact_resources_and_refuses_existing_destination', 'test_character_package.CharacterPackageTests.test_conversion_only_staging_does_not_fetch_or_install_f5_weights', 'test_character_package.CharacterPackageTests.test_dependency_collection_records_actual_revision_and_nested_notices', 'test_character_package.CharacterPackageTests.test_rewritten_dependency_inventory_cannot_override_external_evidence', 'test_character_package.CharacterPackageTests.test_missing_external_dependency_evidence_is_not_accepted', 'test_character_package.CharacterPackageTests.test_symlink_and_case_collisions_fail', 'test_character_package.CharacterPackageTests.test_download_accepts_exact_bytes', 'test_character_package.CharacterPackageTests.test_missing_compiled_speech_shader_is_rejected', 'test_character_package.CharacterPackageTests.test_invalid_compiled_speech_shader_is_rejected', 'test_character_package.CharacterPackageTests.test_matching_external_inventory_cannot_override_vendored_license', 'test_character_package.CharacterPackageTests.test_matching_external_inventory_cannot_reintroduce_remote_fluid', 'test_vendored_fluid.VendoredFluidTests.test_all_third_party_licenses_captured', 'test_vendored_fluid.VendoredFluidTests.test_exact_inventory_and_upstream_tree']
QUEUE_RUN=43824887036
DESCRIPTION='Unfinished preview: reference-only recognition context, original audio preserved, unchanged final-speech verification. Physical-iPhone behavior and likeness unverified; overlapping-speaker extraction, music separation and full RVC training incomplete. Not finished 1.0.0.'
NOTES='VoiceMatrix 0.4.9 build 11 — unfinished development preview\n\nUnsigned ARM64 IPA; requires signing. Update without deleting app data. Build 10 and older releases remain available.\n\nReference-only 250 ms silent recognition context preserves original reference bytes. Bounded complete PCM reads now accommodate positive short reads while rejecting early EOF, invalid counts and cancellation; source files remain unchanged. Seven focused native buffer tests and nine replay checks passed in a separate repair diagnostic; release still requires all current-candidate gates. Final-speech verification remains unpadded. Release gates require the actual two-reader route, original build10 recognizer verification of exact final WAVs, and four separate human holdouts with original/reference method results and context receipts. These controlled checks do not establish general transcription accuracy or voice likeness.\n\nWindows delegates 47 explicitly listed POSIX/native checks to successful Linux coverage. Physical-iPhone installation, device latency/thermals and likeness remain unverified. Overlap extraction, music separation and full RVC training remain incomplete. Not completed 1.0.0.\n'

def gh(*args):return subprocess.check_output(['gh',*args],text=True)
def api(path,method='GET',body=None):
 args=['api',path]
 if method!='GET':args+=['--method',method]
 if body is not None:
  return json.loads(subprocess.check_output(['gh',*args,'--input','-'],input=json.dumps(body),text=True))
 return json.loads(gh(*args))
def digest(p):
 with pathlib.Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def validate_run(r,sha,path):
 assert r['head_sha']==sha and r['path']==path
 assert r['status']=='completed' and r['conclusion']=='success'
 assert r['repository']['full_name']==DEV

def validate_platform_evidence(evidence,platform):
 assert platform in ('Linux','Windows')
 assert evidence['sourceCommit']==REPAIR_SOURCE and evidence['successful'] is True
 assert evidence['mode']==('full' if platform=='Linux' else 'windows-worker')
 passed=evidence['passed'];skipped=evidence['skipped'];delegated=evidence['delegatedToLinux']
 assert isinstance(passed,list) and all(isinstance(x,str) for x in passed) and len(passed)==len(set(passed))
 assert isinstance(skipped,list) and all(isinstance(x,dict) and isinstance(x.get('id'),str) and isinstance(x.get('reason'),str) for x in skipped)
 skipped_ids=[x['id'] for x in skipped]
 assert len(skipped_ids)==len(set(skipped_ids)) and not set(passed)&set(skipped_ids)
 assert type(evidence['testsRun']) is int and evidence['testsRun']>0
 assert len(passed)+len(skipped)==evidence['testsRun']
 if platform=='Linux':
  assert delegated==[] and evidence['allDelegatedExecutedSuccessfully'] is True
  assert set(NATIVE_IDS)<=set(passed) and not set(NATIVE_IDS)&set(skipped_ids)
 else:
  assert delegated==NATIVE_IDS and evidence['allDelegatedExecutedSuccessfully'] is None
  assert not set(NATIVE_IDS)&(set(passed)|set(skipped_ids))

def validate_platform_artifacts(root):
 artifacts=api(f'repos/{DEV}/actions/runs/{QUEUE_RUN}/artifacts?per_page=100')
 assert artifacts['total_count']<=100
 records={}
 for platform in ('Linux','Windows'):
  matching=[a for a in artifacts['artifacts'] if a['name']=='Platform-regression-'+platform]
  assert len(matching)==1
  artifact=matching[0];assert not artifact['expired']
  assert artifact['workflow_run']['id']==QUEUE_RUN and artifact['workflow_run']['head_sha']==REPAIR_SOURCE
  expected=artifact['digest'];assert isinstance(expected,str) and expected.startswith('sha256:') and len(expected)==71
  path=root/('platform-'+platform+'.zip')
  with path.open('wb') as f:subprocess.run(['gh','api',f'repos/{DEV}/actions/artifacts/{artifact["id"]}/zip'],stdout=f,check=True)
  assert 'sha256:'+digest(path)==expected
  with zipfile.ZipFile(path) as archive:
   assert archive.namelist()==['platform-regression-evidence.json'] and archive.testzip() is None
   info=archive.getinfo('platform-regression-evidence.json');assert info.file_size<5_000_000
   evidence=json.loads(archive.read(info))
  validate_platform_evidence(evidence,platform)
  (root/('platform-'+platform+'-evidence.json')).write_text(json.dumps(evidence,indent=2)+'\n')
  records[platform]=dict(artifactID=artifact['id'],artifactSHA256=expected[7:],sourceCommit=REPAIR_SOURCE,testsRun=evidence['testsRun'],skipped=len(evidence['skipped']))
 return records


def new_feed(feed,entry,name):
 result=copy.deepcopy(feed)
 apps=[a for a in result['apps'] if a.get('bundleIdentifier')=='com.voicematrix.app'];assert len(apps)==1
 a=apps[0];old=a['versions'];assert old
 # Fail closed on any later/conflicting publication; never downgrade or overwrite.
 assert all(tuple(map(int,v['version'].split('.'))) <= (0,4,9) for v in old)
 assert not any(v['version']=='0.4.9' and int(v.get('buildVersion','0'))>11 for v in old)
 baseline='10'
 assert name in FEEDS
 assert any(v['version']=='0.4.9' and str(v.get('buildVersion'))==baseline for v in old)
 same=[v for v in old if v['version']=='0.4.9' and str(v.get('buildVersion'))=='11']
 if same:
  assert len(same)==1 and old[0]==same[0]
  assert all(same[0].get(k)==entry[k] for k in ('downloadURL','size','sha256'))
  return result # Already published: preserve exact prior date/description and older entries.
 a['versions']=[copy.deepcopy(entry)]+old
 assert a['versions'][1:]==next(x for x in feed['apps'] if x.get('bundleIdentifier')=='com.voicematrix.app')['versions']
 return result

def validate_asset(asset,draft=False):
 assert asset['name']==IPA and asset['state']=='uploaded'
 assert asset['size']==IPA_BYTES and asset['digest']=='sha256:'+IPA_HASH
 if not draft:assert asset['browser_download_url']==f'https://github.com/{REPO}/releases/download/{TAG}/{IPA}'

def optional_api(path):
 r=subprocess.run(['gh','api',path],capture_output=True,text=True)
 if r.returncode==0:return json.loads(r.stdout)
 if '(HTTP 404)' in r.stderr:return None
 raise RuntimeError('GitHub lookup failed, not confirmed absence: '+r.stderr)

def find_release():
 # The releases list includes accessible drafts; /releases/tags only finds published tags.
 found=[]
 for page in range(1,21):
  rows=api(f'repos/{REPO}/releases?per_page=100&page={page}')
  found.extend(r for r in rows if r['tag_name']==TAG)
  assert len(found)<=1,'Ambiguous release identity'
  if len(rows)<100:return found[0] if found else None
 raise RuntimeError('Release listing exceeded bounded lookup; no publication')


def validate_release_identity(release,tag,publication):
 assert tag is not None and tag['object']['type']=='commit' and tag['object']['sha']==publication
 assert release['tag_name']==TAG and release['target_commitish']==publication and release['prerelease'] is True
 assert release['body']==NOTES and type(release['draft']) is bool

def missing_assets(existing,wanted):
 names=[a['name'] for a in existing];assert len(names)==len(set(names))
 for a in existing:
  assert a['name'] in wanted and a['state']=='uploaded'
  assert all(a[k]==wanted[a['name']][k] for k in ('size','digest'))
 return [name for name in wanted if name not in names]

def get_feeds():
 head=api(f'repos/{REPO}/git/ref/heads/main')['object']['sha']
 tree=api(f'repos/{REPO}/git/commits/{head}')['tree']['sha'];feeds={}
 for name in FEEDS:
  x=api(f'repos/{REPO}/contents/{name}?ref={head}')
  assert x['encoding']=='base64'
  feeds[name]=json.loads(base64.b64decode(x['content']))
 return head,tree,feeds

def stage_catalogs(entry):
 head,tree,feeds=get_feeds();updated={n:new_feed(f,entry,n) for n,f in feeds.items()}
 entries=[dict(path=n,mode='100644',type='blob',content=json.dumps(f,indent=2)+'\n') for n,f in updated.items()]
 t=api(f'repos/{REPO}/git/trees','POST',dict(base_tree=tree,tree=entries))
 c=api(f'repos/{REPO}/git/commits','POST',dict(message='Stage verified unfinished VoiceMatrix build11 catalog entries',tree=t['sha'],parents=[head]))
 return dict(base=head,commit=c['sha'])

def sync_catalogs(entry):
 # CAS retries re-read all three feeds. Never force or replay a stale whole feed.
 catalog_commit=None
 for attempt in range(3):
  head,tree,feeds=get_feeds();updated={n:new_feed(f,entry,n) for n,f in feeds.items()}
  if updated==feeds:catalog_commit=head;break
  entries=[dict(path=n,mode='100644',type='blob',content=json.dumps(f,indent=2)+'\n') for n,f in updated.items()]
  t=api(f'repos/{REPO}/git/trees','POST',dict(base_tree=tree,tree=entries))
  c=api(f'repos/{REPO}/git/commits','POST',dict(message='Add inspected unfinished VoiceMatrix build11 preview to catalogs',tree=t['sha'],parents=[head]))
  if api(f'repos/{REPO}/git/ref/heads/main')['object']['sha']!=head:continue
  try:api(f'repos/{REPO}/git/refs/heads/main','PATCH',dict(sha=c['sha'],force=False))
  except subprocess.CalledProcessError:
   current=api(f'repos/{REPO}/git/ref/heads/main')['object']['sha']
   if current==head:raise
   # Includes uncertain successful update. Fresh read next iteration verifies all feeds.
   continue
  catalog_commit=c['sha'];break
 assert catalog_commit is not None,'Catalog raced repeatedly; exact release preserved; rerun to resume'
 _,_,actual=get_feeds()
 assert all(new_feed(f,entry,n)==f for n,f in actual.items()),'Catalog verification failed; rerun exact workflow to resume'
 return catalog_commit

def ensure_release(root,assets,publication):
 release=find_release()
 tag=optional_api(f'repos/{REPO}/git/ref/tags/{TAG}')
 if tag is not None:assert tag['object']['type']=='commit' and tag['object']['sha']==publication
 if release is not None:
  assert release['tag_name']==TAG and release['target_commitish']==publication and release['prerelease'] is True
 if tag is None:
  api(f'repos/{REPO}/git/refs','POST',dict(ref='refs/tags/'+TAG,sha=publication))
  tag=api(f'repos/{REPO}/git/ref/tags/{TAG}')
 assert tag['object']['type']=='commit' and tag['object']['sha']==publication
 wanted={name:dict(size=(root/name).stat().st_size,digest='sha256:'+digest(root/name)) for name in assets}
 if release is None:
  gh('release','create',TAG,'--repo',REPO,'--target',publication,'--title','VoiceMatrix 0.4.9 build 11 — unfinished preview','--notes-file',str(root/'release-notes.md'),'--draft','--prerelease')
  release=find_release();assert release is not None
  tag=api(f'repos/{REPO}/git/ref/tags/{TAG}')
 validate_release_identity(release,tag,publication)
 missing=missing_assets(release['assets'],wanted)
 assert release['draft'] or not missing, 'Published release has missing assets; stop instead of modifying it'
 for name in missing:gh('release','upload',TAG,str(root/name),'--repo',REPO)
 release=find_release();assert release is not None
 assert not missing_assets(release['assets'],wanted)
 matched=[a for a in release['assets'] if a['name']==IPA];assert len(matched)==1;validate_asset(matched[0],draft=release['draft'])
 return release

def validate_runtime(root,candidate,proof):
 a=api(f'repos/{DEV}/actions/artifacts/{RUNTIME_ARTIFACT}')
 assert a['workflow_run']['id']==RUN and a['workflow_run']['head_sha']==SOURCE
 assert a['digest']=='sha256:'+RUNTIME_HASH and not a['expired']
 path=root/'runtime.zip'
 with path.open('wb') as f:subprocess.run(['gh','api',f'repos/{DEV}/actions/artifacts/{RUNTIME_ARTIFACT}/zip'],stdout=f,check=True)
 assert digest(path)==RUNTIME_HASH
 with zipfile.ZipFile(path) as z:
  assert len(z.namelist())==len(set(z.namelist())) and z.testzip() is None
  assert json.loads(z.read('source-proof.json'))==proof
  graph=z.read('Package.resolved');assert hashlib.sha256(graph).hexdigest()==proof['dependencyResolvedSHA256']
  assert all(json.loads(z.read(n))==proof['vendoredDependencies']['FluidAudio'] for n in ['vendor-before.json','vendor-after-tests.json','vendor-after-build.json'])
  for part in ('first','second'):
   e=json.loads(z.read(part+'/pipeline-evidence.json'))
   assert e['sourceCommit']==SOURCE and e['newSpeechWordErrorRate']==0 and len(e['importedIDs'])==1
   assert all(e[k] is True for k in ['resumeCompleted','cancellationRetainedSource','freshStoreReloadPreservedIDs','priorProfilePreserved'])
   assert hashlib.sha256(z.read(part+'/complete-source.wav')).hexdigest()==e['sourceRetainedSHA256']==e['fixtureSHA256']
   assert hashlib.sha256(z.read(part+'/work/new-speech.wav')).hexdigest()==e['newSpeechSHA256']==json.loads(z.read(part+'/work/new-speech-asr.json'))['inputSHA256']
   assert json.loads(z.read(part+'/source-transcript-check.json'))['wordErrorRate']==0
   (root/(part+'-pipeline-evidence.json')).write_text(json.dumps(e,indent=2)+'\n')
  (root/'Package.resolved').write_bytes(graph)
 from tools.character_evidence import source_proof
 old=pathlib.Path.cwd();oldsha=os.environ['GITHUB_SHA']
 try:
  os.chdir(candidate);os.environ['GITHUB_SHA']=SOURCE
  assert source_proof((root/'Package.resolved').resolve())==proof
 finally:os.chdir(old);os.environ['GITHUB_SHA']=oldsha

def require_pins():
 # Preparation is intentionally non-runnable until reviewed immutable artifact pins exist.
 for value in (ARTIFACT,RUNTIME_ARTIFACT,IPA_BYTES):assert type(value) is int and value>0,'Missing reviewed artifact identity'
 for value in (ZIP_HASH,IPA_HASH,RUNTIME_HASH):assert isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value),'Missing reviewed digest'
 assert set(EVIDENCE_PINS)=={FULL_ROUTE_RUN,HUMAN_RUN}
 for pin in EVIDENCE_PINS.values():
  assert isinstance(pin,dict) and type(pin.get('id')) is int and pin['id']>0
  assert isinstance(pin.get('sha256'),str) and re.fullmatch('[a-f0-9]{64}',pin['sha256'])

def validate_human_results(manifest,results):
 cases=manifest['cases'];assert len(cases)==len(results)==8
 assert all(a['prepared'] is True and 'error' not in a for a in manifest['preparationAttempts']) and len(manifest['preparationAttempts'])==4
 assert len(manifest['sources'])==4 and len({s['speaker_id'] for s in manifest['sources']})==4
 expected={c['id']:c for c in cases};assert len(expected)==8 and {r['id'] for r in results}==set(expected)
 groups={}
 for r in results:
  c=expected[r['id']];groups.setdefault(c['file'],[]).append(c)
  assert r['accepted'] is True and r.get('error') is None and r['wordErrorRate']==0
  assert re.findall('[a-z0-9]+',r['recognized'].lower())==re.findall('[a-z0-9]+',c['expected'].lower())
  assert r['mode']==c['mode'] and r['file']==c['file'] and r['expected']==c['expected']
  assert r['inputSHA256']==c['sha256']==r['sourceSHA256']
  e=r['evidence'];assert e['inputSHA256']==c['sha256']
  assert e['transcriptSHA256']==hashlib.sha256(r['recognized'].encode()).hexdigest()
  assert e.get('referenceLeadingSeconds')==(.25 if c['mode']=='reference' else None)
  assert c['mode'] in ('reference','baseline')
 assert len(groups)==4
 for pair in groups.values():
  assert len(pair)==2 and {c['mode'] for c in pair}=={'baseline','reference'} and len({c['sha256'] for c in pair})==1

def validate_unpadded_results(inputs,outcomes):
 assert len(inputs)==len(outcomes)==2 and len({x['voiceID'] for x in inputs})==2
 expected={x['voiceID']:x for x in inputs};assert {x['voiceID'] for x in outcomes}==set(expected)
 for r in outcomes:
  i=expected[r['voiceID']]
  assert r['accepted'] is True and r['wordErrorRate']==0 and r.get('error') is None
  assert re.findall('[a-z0-9]+',r['actual'].lower())==re.findall('[a-z0-9]+',i['expected'].lower())
  assert r['file']==i['file'] and r['inputSHA256']==i['sha256'] and r['expected']==i['expected']
  assert r['evidence']['inputSHA256']==i['sha256'] and r['evidence'].get('referenceLeadingSeconds') is None
  assert r['evidence']['transcriptSHA256']==hashlib.sha256(r['actual'].encode()).hexdigest()

def diagnostic_archive(root,run):
 pin=EVIDENCE_PINS[run];a=api(f'repos/{DEV}/actions/artifacts/{pin["id"]}')
 assert a['workflow_run']['id']==run and a['workflow_run']['head_sha']==SOURCE and not a['expired']
 assert a['digest']=='sha256:'+pin['sha256']
 path=root/f'gate-{run}.zip'
 with path.open('wb') as f:subprocess.run(['gh','api',f'repos/{DEV}/actions/artifacts/{pin["id"]}/zip'],stdout=f,check=True)
 assert digest(path)==pin['sha256']
 dest=root/f'gate-{run}';dest.mkdir()
 with zipfile.ZipFile(path) as z:
  names=z.namelist();assert len(names)==len(set(names)) and z.testzip() is None
  assert sum(i.file_size for i in z.infolist())<4_000_000_000
  for i in z.infolist():
   p=pathlib.PurePosixPath(i.filename)
   assert not p.is_absolute() and '..' not in p.parts and '\\' not in i.filename and ':' not in i.filename
   assert (i.external_attr>>16)&0o170000!=0o120000
  z.extractall(dest)
 return dest

def validate_context_artifacts(root,candidate,proof):
 full=diagnostic_archive(root,FULL_ROUTE_RUN);human=diagnostic_archive(root,HUMAN_RUN)
 assert json.loads((full/'source-proof.json').read_text())==proof
 # Rerun original strict route and additional reference-only receipt guards against immutable candidate.
 subprocess.run([sys.executable,str(candidate/'probes/reference-context-receipts.py'),str(full/'mixed')],check=True)
 mixed=full/'mixed';u=mixed/'unpadded-verification'
 inputs=json.loads((u/'inputs.json').read_text());outcomes=json.loads((u/'outcomes.json').read_text())
 validate_unpadded_results(inputs,outcomes)
 for row in inputs:assert digest(mixed/'work'/row['file'])==row['sha256']
 baseline=json.loads((u/'source-proof.json').read_text())['sourceHashes']
 for name,sha in baseline.items():
  p=candidate/'probes/leading-padding-unpadded-verifier/Baseline'/name if name in ('OnDeviceTranscription.swift','BundledASRPolicy.swift') else candidate/'VoiceMatrix'/name
  assert digest(p)==sha
 assert baseline['OnDeviceTranscription.swift']=='758ed706e92fc3da63cdfb6048fb65afcd13475ece8534381bbd2f0050e06ae6'
 assert baseline['BundledASRPolicy.swift']=='ce50e078dfae0285efc4c574f88faea115ef0e1fdef1e0de9d75b8cebbe19d70'
 hp=json.loads((human/'source-proof.json').read_text());assert hp['sourceCommit']==SOURCE
 for name,sha in hp['productionSources'].items():assert digest(candidate/'VoiceMatrix'/(name+'.swift'))==sha
 manifest=json.loads((human/'manifest.json').read_text());results=json.loads((human/'results.json').read_text())
 validate_human_results(manifest,results)
 assert manifest['sources']==json.loads((candidate/'probes/reference-context-human-holdouts/sources.json').read_text())
 for c in manifest['cases']:assert digest(human/c['file'])==c['sha256']
 for s in manifest['sources']:assert digest(human/(s['id']+'.flac'))==s['sourceSHA256']
 return dict(sourceCommit=SOURCE,fullRouteRun=FULL_ROUTE_RUN,humanRun=HUMAN_RUN,artifactPins=EVIDENCE_PINS,originalBaselineVerified=True,referenceReceiptsVerified=True,humanMethodChecks=8)

def require_current_head():
 assert api(f'repos/{DEV}/git/ref/heads/preview/voicematrix-build11')['object']['sha']==SOURCE,'Candidate superseded; refusing publication'

def main():
 require_pins()
 require_current_head()
 assert os.environ['GITHUB_REPOSITORY']==REPO
 validate_run(api(f'repos/{DEV}/actions/runs/{RUN}'),SOURCE,'.github/workflows/iphone-build11.yml')
 validate_run(api(f'repos/{DEV}/actions/runs/{FULL_UI_RUN}'),FULL_UI_SOURCE,'.github/workflows/character-ui-smoke.yml')
 for run,path in REQUIRED_RUNS.items():validate_run(api(f'repos/{DEV}/actions/runs/{run}'),SOURCE,path)
 art=api(f'repos/{DEV}/actions/artifacts/{ARTIFACT}')
 assert art['workflow_run']['id']==RUN and art['workflow_run']['head_sha']==SOURCE and art['digest']=='sha256:'+ZIP_HASH and not art['expired']
 root=pathlib.Path('preview11-evidence').resolve();root.mkdir()
 platform_proof=validate_platform_artifacts(root)
 with (root/'artifact.zip').open('wb') as f:subprocess.run(['gh','api',f'repos/{DEV}/actions/artifacts/{ARTIFACT}/zip'],stdout=f,check=True)
 assert digest(root/'artifact.zip')==ZIP_HASH
 with zipfile.ZipFile(root/'artifact.zip') as z:
  expected={IPA,'character-inspection.json','character-ipa.sha256','source-proof.json','dependency-notices.json','assets.json','packaging-status.json','vendor-before.json','vendor-after.json'}
  assert len(z.namelist())==len(expected) and set(z.namelist())==expected and z.testzip() is None
  z.extractall(root)
 assert digest(root/IPA)==IPA_HASH and (root/IPA).stat().st_size==IPA_BYTES
 assert (root/'character-ipa.sha256').read_text().split()==[IPA_HASH,IPA]
 # Independently rerun trusted artifact inspection from exact package source checkout.
 candidate=pathlib.Path('package-source').resolve();sys.path.insert(0,str(candidate))
 from tools.character_package import inspect_ipa,PREFIX
 notices=json.loads((root/'dependency-notices.json').read_text())
 inspection=inspect_ipa(root/IPA,dependency_proof=notices['proof'],expected_version='0.4.9',expected_build='11')
 assert inspection==json.loads((root/'character-inspection.json').read_text())
 proof=json.loads((root/'source-proof.json').read_text());assert proof['sourceCommit']==SOURCE
 with zipfile.ZipFile(root/IPA) as z:assert json.loads(z.read(PREFIX+'VoiceMatrix-Source-Proof.json'))==proof
 validate_runtime(root,candidate,proof)
 context_proof=validate_context_artifacts(root,candidate,proof)
 assert json.loads((root/'vendor-before.json').read_text())==json.loads((root/'vendor-after.json').read_text())==proof['vendoredDependencies']['FluidAudio']
 status=json.loads((root/'packaging-status.json').read_text())
 assert status['sourceCommit']==SOURCE and status['build']=='11' and status['version']=='0.4.9'
 assert status['physicalDeviceVerified'] is False and status['likenessVerified'] is False
 for tool in ('bundle_asr.py','bundle_diarization.py'):
  subprocess.run([sys.executable,str(candidate/'tools'/tool),'--inspect-ipa',str((root/IPA).resolve())],check=True,cwd=candidate)
 entry=dict(version='0.4.9',buildVersion='11',date=datetime.datetime.now(datetime.timezone.utc).date().isoformat(),downloadURL=f'https://github.com/{REPO}/releases/download/{TAG}/{IPA}',localizedDescription=DESCRIPTION,minOSVersion='26.0',size=IPA_BYTES,sha256=IPA_HASH)
 _,_,preflight=get_feeds()
 for n,f in preflight.items():new_feed(f,entry,n)
 publication=os.environ['GITHUB_SHA']
 metadata=dict(sourceCommit=SOURCE,version='0.4.9',buildVersion='11',size=IPA_BYTES,sha256=IPA_HASH,packagingRun=RUN,independentVerification="Exact archive reinspected by publisher",runtimeArtifact=RUNTIME_ARTIFACT,runtimeArtifactSHA256=RUNTIME_HASH,fullUIRun=FULL_UI_RUN,fullUISource=FULL_UI_SOURCE,publicationSource=publication,requiredRuns=list(REQUIRED_RUNS),referenceContextEvidence=context_proof,platformRegressionEvidence=platform_proof,physicalDeviceVerified=False,likenessVerified=False,unfinishedPreview=True)
 (root/'release-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');(root/'release-notes.md').write_text(NOTES)
 assets=[IPA,'character-inspection.json','source-proof.json','packaging-status.json','release-metadata.json','dependency-notices.json','vendor-before.json','vendor-after.json']
 require_current_head()
 release=ensure_release(root,assets,publication)
 staged=stage_catalogs(entry)
 (root/'staged-catalog.json').write_text(json.dumps(staged,indent=2)+'\n')
 # Publish only verified uploaded bytes; no broken download is ever added to feeds.
 require_current_head()
 if release['draft']:api(f"repos/{REPO}/releases/{release['id']}",'PATCH',{'draft':False,'prerelease':True,'make_latest':'false'})
 release=api(f"repos/{REPO}/releases/{release['id']}");assert not release['draft'] and release['prerelease']
 validate_release_identity(release,api(f'repos/{REPO}/git/ref/tags/{TAG}'),publication)
 assert not missing_assets(release['assets'],{n:dict(size=(root/n).stat().st_size,digest='sha256:'+digest(root/n)) for n in assets})
 for a in release['assets']:assert a['browser_download_url']==f'https://github.com/{REPO}/releases/download/{TAG}/{a["name"]}'
 validate_asset(next(a for a in release['assets'] if a['name']==IPA))
 entry['date']=release['published_at'][:10]
 catalog_commit=sync_catalogs(entry)
 print(json.dumps(dict(releaseURL=release['html_url'],catalogCommit=catalog_commit,metadata=metadata),indent=2))
if __name__=='__main__':main()
