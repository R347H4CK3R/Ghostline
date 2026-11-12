import pathlib,shutil,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).parents[1]
class CandidateNativeTests(unittest.TestCase):
 @unittest.skipUnless(shutil.which('swiftc'),'Swift compiler required')
 def test_request_model_in_native_swift(self):
  with tempfile.TemporaryDirectory() as directory:
   binary=pathlib.Path(directory)/'checks'
   subprocess.run(['swiftc',str(ROOT/'VoiceMatrix/VideoWorkflow.swift'),str(ROOT/'VoiceMatrix/VideoCandidateRequest.swift'),str(ROOT/'tests/native/VideoCandidateRequestChecks.swift'),'-o',str(binary)],check=True)
   subprocess.run([str(binary)],check=True)
