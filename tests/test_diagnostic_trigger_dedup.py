"""Exercise the deliberately narrow branch/path filters without a YAML dependency.

This parser supports these workflows' literal positive path lists, not arbitrary
GitHub expressions. Reusable/manual events do not evaluate push filters.
"""
import pathlib,re,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
CANDIDATE='candidate/voicematrix-0.4.9'
FILES=['bundled-asr-diagnostic.yml','local-pipeline-diagnostic.yml']
def source(name):return (ROOT/'.github/workflows'/name).read_text()
def push_filter(text,key):
 match=re.search(r'^  push:\n(.*?)(?=^  [a-z_]+:|^[^ \n]|\Z)',text,re.M|re.S)
 if not match:raise AssertionError('Expected explicit push trigger')
 body=match.group(1)
 match=re.search(r'^    '+re.escape(key)+r':\n((?:(?:    |      )- [^\n]+\n)+)',body,re.M)
 if not match:return []
 return [line.split('- ',1)[1].strip().strip("'\"") for line in match.group(1).splitlines()]
def matches(pattern,path):
 # GitHub-style literal paths here use only *, ** and no negative/extglob rules.
 if pattern.startswith('!') or any(c in pattern for c in ['[',']','?']):raise AssertionError('Unsupported filter semantics require a test update')
 regex=re.escape(pattern).replace(r'\*\*','.*').replace(r'\*','[^/]*')
 return re.fullmatch(regex,path) is not None
def fires(text,event,branch,paths=()):
 if event in ['workflow_call','workflow_dispatch']:return ('  '+event+':') in text
 if event!='push':return False
 if any(matches(pattern,branch) for pattern in push_filter(text,'branches-ignore')):return False
 return any(matches(pattern,path) for pattern in push_filter(text,'paths') for path in paths)
class DiagnosticTriggerDedupTests(unittest.TestCase):
 def test_only_exact_candidate_direct_push_is_suppressed(self):
  for name in FILES:
   text=source(name)
   self.assertEqual(push_filter(text,'branches-ignore'),[CANDIDATE])
   for path in ['VoiceMatrix/OnDeviceTranscription.swift','project.yml']:
    self.assertFalse(fires(text,'push',CANDIDATE,[path]),name)
    for branch in ['main','work/standalone',CANDIDATE+'-fix','candidate/voicematrix-1.0.0']:
     self.assertTrue(fires(text,'push',branch,[path]),(name,branch,path))
   self.assertFalse(fires(text,'push','main',['README.md']),name)
   self.assertFalse(fires(text,'push','main',['VoiceMatrix/unrelated/OnDeviceTranscription.swift']),name)
 def test_manual_and_reusable_calls_remain_available_on_candidate(self):
  for name in FILES:
   for event in ['workflow_call','workflow_dispatch']:
    self.assertTrue(fires(source(name),event,CANDIDATE))
 def test_specific_non_candidate_paths_still_dispatch(self):
  self.assertTrue(fires(source(FILES[0]),'push','work/test',['probes/native-asr/Diagnostic.swift']))
  self.assertTrue(fires(source(FILES[1]),'push','work/test',['probes/native-local-studio/Diagnostic.swift']))
 def test_aggregate_still_requires_both_exact_source_diagnostics(self):
  main=source('voicematrix-049-candidate.yml')
  self.assertIn("branches: ['candidate/voicematrix-0.4.9']",main)
  self.assertIn('needs: [resolve, ipa, speech, conversion, bundled-asr, local-pipeline]',main)
  self.assertIn('  bundled-asr:\n    uses: ./.github/workflows/bundled-asr-diagnostic.yml',main)
  self.assertIn('  local-pipeline:\n    needs: resolve\n    uses: ./.github/workflows/local-pipeline-diagnostic.yml\n    with:\n      use-frozen: true',main)
  local=source(FILES[1])
  for phrase in ['use-frozen:', 'type: boolean', 'default: false', 'name: Character-frozen-dependencies', '-disableAutomaticPackageResolution', '-onlyUsePackageVersionsFromResolvedFile']:
   self.assertIn(phrase,local)
 def test_permissions_are_unchanged_read_only(self):
  for name in FILES+['voicematrix-049-candidate.yml']:
   text=source(name)
   self.assertEqual(len(re.findall(r'^\s*permissions:',text,re.M)),1,name)
   self.assertIn('permissions:\n  contents: read\n',text)
   self.assertNotRegex(text,r'permissions:\s*(?:write-all|read-all)')
