import pathlib, shutil, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class LocalJournalTests(unittest.TestCase):
 def test_real_foundation_journal(self):
  if not shutil.which('swiftc'): self.skipTest('Swift unavailable; Foundation journal behavior awaits native execution')
  with tempfile.TemporaryDirectory() as folder:
   binary=pathlib.Path(folder)/'journal-tests'
   subprocess.run(['swiftc',str(ROOT/'VoiceMatrix/LocalStudioJournal.swift'),str(ROOT/'tests/native/LocalStudioJournalChecks.swift'),'-o',str(binary)],check=True,timeout=60)
   subprocess.run([str(binary)],check=True,timeout=30)
 def test_journal_integration_and_native_target(self):
  studio=(ROOT/'VoiceMatrix/LocalVideoStudio.swift').read_text()
  self.assertIn('LocalStudioJournal.append',studio)
  self.assertIn('journalPage',studio)
  self.assertIn('LocalStudioJournal.swift',(ROOT/'project.yml').read_text())
  ui=(ROOT/'VoiceMatrix/LocalVideoStudioView.swift').read_text()
  self.assertIn('ShareLink',ui)
  self.assertIn('Last actual update:',ui)
 def test_nonblocking_anchored_journal_contract(self):
  source=(ROOT/'VoiceMatrix/LocalStudioJournal.swift').read_text()
  self.assertIn('O_NONBLOCK',source)
  self.assertIn('openat(parentFD',source)
  self.assertIn('openat(folderFD',source)
  self.assertIn('mkfifo',(ROOT/'tests/native/LocalStudioJournalChecks.swift').read_text())
