"""Publish only the inspected unfinished build10; never replace old releases."""
import base64,copy,datetime,hashlib,json,os,pathlib,subprocess,sys,zipfile
REPO='R347H4CK3R/Ghostline'
DEV='R347H4CK3R/VoiceMatrix-Development'
SOURCE='e7023843438a2ed82ef95a7ee96df12ea56d68e9'
RUN=43787632211
VERIFY_RUN=43791024872
FULL_UI_RUN=43787631926
FULL_UI_SOURCE='e7023843438a2ed82ef95a7ee96df12ea56d68e9'
RUNTIME_ARTIFACT=14191694319
RUNTIME_HASH='156311dbee231e428f9015c1bf89e445182ef4ec67abe308c81ea2936cb2e39b'
ARTIFACT=14191844704
ZIP_HASH='116751d7f3dcd56862f7a10d3a8c7b1fceb189043d7fa6060e88fe053a3fc820'
IPA_HASH='8adee1c45510ac22557b77ed0bbb7d32346cbc39a11efaf9bcea16f9e43622fd'
IPA_BYTES=1314595724
TAG='voicematrix-v0.4.9-build10'
IPA='VoiceMatrix-0.4.9-build10.ipa'
FEEDS=('strata-source.json','source.json','livecontainer-test.json')
REPAIR_SOURCE='12e6f3535640246056a865f62d23460ede76e06a'
REPAIR_RUNS={43807237189:'.github/workflows/native-character-folder.yml',43807237128:'.github/workflows/queue-processor.yml',43807238116:'.github/workflows/native-queue.yml'}
REPAIR_STATUSES={'.circleci/config.yml': 'modified', '.github/workflows/queue-processor.yml': 'modified', 'ci/circleci/native-ui.candidate.yml': 'modified', 'tests/platform-regression-coverage.json': 'added', 'tests/test_catalog_history_ui.py': 'modified', 'tests/test_character_workflow_budget.py': 'modified', 'tests/test_full_retained_speaker_route.py': 'modified', 'tests/test_native_acquisition.py': 'modified', 'tests/test_platform_regressions.py': 'added', 'tests/test_reference_boundary_selection.py': 'modified', 'tests/test_reference_case_punctuation.py': 'modified', 'tests/test_reference_padding_holdout.py': 'modified', 'tests/test_reference_padding_independent.py': 'modified', 'tests/test_reference_text_format.py': 'modified', 'tests/test_retained_speech_diagnostic.py': 'modified', 'tests/test_second_complete_speaker_route.py': 'modified', 'tests/test_selective_voice_wiring.py': 'modified', 'tests/test_test_shell.py': 'added', 'tests/test_workflow_runner_isolation.py': 'modified', 'tools/run_platform_regressions.py': 'added', 'tools/test_shell.py': 'added'}
REPAIR_FILES=set(REPAIR_STATUSES)
NATIVE_IDS=['test_diarizer_eof_patch.EOFDiagnosticTests.test_actual_app_boundary_guard_still_rejects_invalid_evidence', 'test_direct_voice_profile.DirectVoiceProfileTests.test_actual_library_import_preserves_prior_profiles', 'test_direct_voice_profile.DirectVoiceProfileTests.test_package_roundtrip_bounds_cancellation_and_preservation', 'test_reference_attempt.ReferenceAttemptTests.test_native_candidate_evidence_and_asset_binding', 'test_reference_candidate_pool.CandidatePoolTests.test_later_clean_turn_is_reachable_without_expanding_preview_budget', 'test_reference_candidate_pool.CandidatePoolTests.test_real_migration_validates_legacy_windows_before_expanding', 'test_rvc_controls.Controls.test_default_strength_is_unchanged', 'test_rvc_controls.Controls.test_invalid_controls_and_missing_required_index_fail', 'test_rvc_controls.Controls.test_no_retrieval_preserves_features_and_allows_missing_index', 'test_rvc_controls.Controls.test_selected_strength_and_shift_reach_synthesizer', 'test_rvc_disk_vectors.DiskVectorTests.test_snapshot_integrity_isolation_and_rejections', 'test_rvc_model_admission.CandidateAdmission.test_exact_model_identity_and_retrieval_pairing', 'test_rvc_native_features.RVCFeatureTests.test_cancellation_before_allocation', 'test_rvc_native_features.RVCFeatureTests.test_disabled_retrieval_needs_no_index_and_preserves_frames', 'test_rvc_native_features.RVCFeatureTests.test_equal_neighbor_weights_have_hand_calculated_result', 'test_rvc_native_features.RVCFeatureTests.test_feature_retrieval_upsampling_and_protection', 'test_rvc_native_features.RVCFeatureTests.test_invalid_shapes_bounds_and_degenerate_neighbors_fail', 'test_rvc_native_features.RVCFeatureTests.test_pitch_interpolation_shift_and_bins', 'test_rvc_native_synthesis.NativeSynthesisTests.test_tensor_bytes_and_reject_malformed_assets_before_inference', 'test_rvc_retrieval_memory.RetrievalMemoryTests.test_bounded_selection_and_exact_sparse_fallback', 'test_rvc_retrieval_pack.RetrievalPackAdmission.test_profile_manifest_cannot_override_file_identity', 'test_character_package.CharacterPackageTests.test_complete_no_stock_artifact_passes_with_explicit_unverified_device_status', 'test_character_package.CharacterPackageTests.test_explicit_build_identity_rejects_reused_package', 'test_character_package.CharacterPackageTests.test_missing_or_tampered_f5_asset_fails', 'test_character_package.CharacterPackageTests.test_self_signed_forged_proof_does_not_override_pinned_hash', 'test_character_package.CharacterPackageTests.test_stock_or_private_reference_payload_is_rejected', 'test_character_package.CharacterPackageTests.test_bundled_private_pairing_token_is_rejected', 'test_character_package.CharacterPackageTests.test_missing_or_modified_license_is_rejected', 'test_character_package.CharacterPackageTests.test_duplicate_and_traversal_archive_names_are_rejected', 'test_character_package.CharacterPackageTests.test_missing_dependency_notice_or_resolved_proof_fails', 'test_character_package.CharacterPackageTests.test_wrong_architecture_or_placeholder_fails', 'test_character_package.CharacterPackageTests.test_rewritten_baseline_manifest_cannot_hide_missing_engine', 'test_character_package.CharacterPackageTests.test_private_or_case_variant_resource_outside_f5_is_rejected', 'test_character_package.CharacterPackageTests.test_download_rejects_bad_hash_and_does_not_replace_existing_file', 'test_character_package.CharacterPackageTests.test_prepare_stages_exact_resources_and_refuses_existing_destination', 'test_character_package.CharacterPackageTests.test_conversion_only_staging_does_not_fetch_or_install_f5_weights', 'test_character_package.CharacterPackageTests.test_dependency_collection_records_actual_revision_and_nested_notices', 'test_character_package.CharacterPackageTests.test_rewritten_dependency_inventory_cannot_override_external_evidence', 'test_character_package.CharacterPackageTests.test_missing_external_dependency_evidence_is_not_accepted', 'test_character_package.CharacterPackageTests.test_symlink_and_case_collisions_fail', 'test_character_package.CharacterPackageTests.test_download_accepts_exact_bytes', 'test_character_package.CharacterPackageTests.test_missing_compiled_speech_shader_is_rejected', 'test_character_package.CharacterPackageTests.test_invalid_compiled_speech_shader_is_rejected', 'test_character_package.CharacterPackageTests.test_matching_external_inventory_cannot_override_vendored_license', 'test_character_package.CharacterPackageTests.test_matching_external_inventory_cannot_reintroduce_remote_fluid', 'test_vendored_fluid.VendoredFluidTests.test_all_third_party_licenses_captured', 'test_vendored_fluid.VendoredFluidTests.test_exact_inventory_and_upstream_tree']
QUEUE_RUN=43807237128
DESCRIPTION='Unfinished preview: locally word-checked catalog speech and retained speech history with explicit review, save/share and confirmed deletion. Controlled simulator and native pipeline checks passed. Physical-iPhone behavior and likeness unverified; overlapping-speaker extraction, music separation and full RVC training incomplete. Not finished 1.0.0.'
NOTES='''VoiceMatrix 0.4.9 build 10 — unfinished development preview

Unsigned ARM64 IPA for iOS 26+, requiring signing through your sideloading setup. Update without deleting app data. Build 9 and older releases remain available.

Compared with build 9: local word verification before replacing a prior good catalog-speech result; bounded checks and explicit unverified states for unsupported, rejected, interrupted or missing-recognizer results; persistent paginated speech history; separate playback/save/share and confirmed deletion of generated results without deleting voice references. Reference-audio presets are not labeled trained RVC models. No stock celebrity voices are bundled.

Exact package source: e7023843438a2ed82ef95a7ee96df12ea56d68e9. Packaging run 43787632211 and independent archive verification 43791024872 passed. The native pipeline in the packaging run passed eight EOF boundary tests and two separate complete licensed human recordings through the local coordinator with zero measured new-speech word errors, retained-source pause/resume and preserved prior profiles. Runtime and IPA source/vendor proof and frozen dependency graph match. These controlled macOS tests do not establish arbitrary-video reliability, character identity or physical-device performance.

Simulator run 43787631926 passed 56 unit tests and 13 UI tests, including import/relaunch and naming. Additional retained-speech quality/history tests cover good output, rejection, cancellation, missing recognition, restart, storage-cap recovery and distinct saved-output identity. The original broad source-regression jobs failed four stale contract assertions. Test/harness/generated-CI-only repair 12e6f3535640246056a865f62d23460ede76e06a preserves application bytes and safety limits; successful native-folder and queue regression runs 43807237189 and 43807237128, plus native queue run 43807238116, are mandatory publication gates, not waived failures. Windows checkout preserves LF bytes and uses Python UTF-8 and explicitly resolves absolute Git Bash rather than the WSL launcher; syntax checks pass UTF-8 bytes without Windows newline translation. The Windows worker suite explicitly delegates 47 POSIX-native Swift and executable-mode package/vendor tests to the full Linux lane, where every delegated test must pass without skipping; both lanes must succeed and their source-bound evidence is checked before publication. Existing platform-specific skips are reported. This is not a claim that the entire native suite runs on Windows.

Physical-iPhone installation, memory/performance, human listening, character identity and likeness remain unverified. Music separation, reliable overlapping-speaker extraction and full RVC training remain incomplete. A harder truncated-reference fixture previously failed new-speech verification; the two complete recordings do not establish that case is repaired. Experimental RVC requires compatible imported packs. Not completed 1.0.0.
'''
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

def validate_repair(comparison):
 assert comparison['status']=='ahead' and comparison['base_commit']['sha']==SOURCE
 assert comparison['merge_base_commit']['sha']==SOURCE
 assert comparison['commits'][-1]['sha']==REPAIR_SOURCE
 files=comparison['files']
 assert len(files)==len(REPAIR_FILES) and {f['filename'] for f in files}==REPAIR_FILES
 assert all(f['status']==REPAIR_STATUSES[f['filename']] and 'previous_filename' not in f for f in files)


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
 assert not any(v['version']=='0.4.9' and int(v.get('buildVersion','0'))>10 for v in old)
 baseline='9'
 assert name in FEEDS
 assert any(v['version']=='0.4.9' and str(v.get('buildVersion'))==baseline for v in old)
 same=[v for v in old if v['version']=='0.4.9' and str(v.get('buildVersion'))=='10']
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
 c=api(f'repos/{REPO}/git/commits','POST',dict(message='Stage verified unfinished VoiceMatrix build10 catalog entries',tree=t['sha'],parents=[head]))
 return dict(base=head,commit=c['sha'])

def sync_catalogs(entry):
 # CAS retries re-read all three feeds. Never force or replay a stale whole feed.
 catalog_commit=None
 for attempt in range(3):
  head,tree,feeds=get_feeds();updated={n:new_feed(f,entry,n) for n,f in feeds.items()}
  if updated==feeds:catalog_commit=head;break
  entries=[dict(path=n,mode='100644',type='blob',content=json.dumps(f,indent=2)+'\n') for n,f in updated.items()]
  t=api(f'repos/{REPO}/git/trees','POST',dict(base_tree=tree,tree=entries))
  c=api(f'repos/{REPO}/git/commits','POST',dict(message='Add inspected unfinished VoiceMatrix build10 preview to catalogs',tree=t['sha'],parents=[head]))
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
  gh('release','create',TAG,'--repo',REPO,'--target',publication,'--title','VoiceMatrix 0.4.9 build 10 — unfinished preview','--notes-file',str(root/'release-notes.md'),'--draft','--prerelease')
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

def main():
 assert os.environ['GITHUB_REPOSITORY']==REPO
 validate_run(api(f'repos/{DEV}/actions/runs/{RUN}'),SOURCE,'.github/workflows/iphone-build10.yml')
 validate_run(api(f'repos/{DEV}/actions/runs/{FULL_UI_RUN}'),FULL_UI_SOURCE,'.github/workflows/character-ui-smoke.yml')
 validate_run(api(f'repos/{DEV}/actions/runs/{VERIFY_RUN}'),'62b5b83d9a09773b9ea9eb3444da44f887a71732','.github/workflows/verify-build10-artifact.yml')
 for run,path in REPAIR_RUNS.items():validate_run(api(f'repos/{DEV}/actions/runs/{run}'),REPAIR_SOURCE,path)
 validate_repair(api(f'repos/{DEV}/compare/{SOURCE}...{REPAIR_SOURCE}'))
 art=api(f'repos/{DEV}/actions/artifacts/{ARTIFACT}')
 assert art['workflow_run']['id']==RUN and art['digest']=='sha256:'+ZIP_HASH and not art['expired']
 root=pathlib.Path('preview10-evidence').resolve();root.mkdir()
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
 inspection=inspect_ipa(root/IPA,dependency_proof=notices['proof'],expected_version='0.4.9',expected_build='10')
 assert inspection==json.loads((root/'character-inspection.json').read_text())
 proof=json.loads((root/'source-proof.json').read_text());assert proof['sourceCommit']==SOURCE
 with zipfile.ZipFile(root/IPA) as z:assert json.loads(z.read(PREFIX+'VoiceMatrix-Source-Proof.json'))==proof
 validate_runtime(root,candidate,proof)
 assert json.loads((root/'vendor-before.json').read_text())==json.loads((root/'vendor-after.json').read_text())==proof['vendoredDependencies']['FluidAudio']
 status=json.loads((root/'packaging-status.json').read_text())
 assert status['sourceCommit']==SOURCE and status['build']=='10' and status['version']=='0.4.9'
 assert status['physicalDeviceVerified'] is False and status['likenessVerified'] is False
 for tool in ('bundle_asr.py','bundle_diarization.py'):
  subprocess.run([sys.executable,str(candidate/'tools'/tool),'--inspect-ipa',str((root/IPA).resolve())],check=True,cwd=candidate)
 entry=dict(version='0.4.9',buildVersion='10',date=datetime.datetime.now(datetime.timezone.utc).date().isoformat(),downloadURL=f'https://github.com/{REPO}/releases/download/{TAG}/{IPA}',localizedDescription=DESCRIPTION,minOSVersion='26.0',size=IPA_BYTES,sha256=IPA_HASH)
 _,_,preflight=get_feeds()
 for n,f in preflight.items():new_feed(f,entry,n)
 publication=os.environ['GITHUB_SHA']
 metadata=dict(sourceCommit=SOURCE,version='0.4.9',buildVersion='10',size=IPA_BYTES,sha256=IPA_HASH,packagingRun=RUN,independentVerificationRun=VERIFY_RUN,runtimeArtifact=RUNTIME_ARTIFACT,runtimeArtifactSHA256=RUNTIME_HASH,fullUIRun=FULL_UI_RUN,fullUISource=FULL_UI_SOURCE,publicationSource=publication,regressionRepairSource=REPAIR_SOURCE,regressionRepairRuns=list(REPAIR_RUNS),platformRegressionEvidence=platform_proof,physicalDeviceVerified=False,likenessVerified=False,unfinishedPreview=True)
 (root/'release-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');(root/'release-notes.md').write_text(NOTES)
 assets=[IPA,'character-inspection.json','source-proof.json','packaging-status.json','release-metadata.json','dependency-notices.json','vendor-before.json','vendor-after.json']
 release=ensure_release(root,assets,publication)
 staged=stage_catalogs(entry)
 (root/'staged-catalog.json').write_text(json.dumps(staged,indent=2)+'\n')
 # Publish only verified uploaded bytes; no broken download is ever added to feeds.
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
