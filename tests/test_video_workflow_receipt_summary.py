"""Source wiring plus real Swift behavior checks, never a substitute for iOS UI QA."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class VideoWorkflowReceiptSummaryTests(unittest.TestCase):
    def test_video_receipts_precede_the_voice_catalog(self):
        source = (ROOT / 'VoiceMatrix/VideoWorkflowView.swift').read_text(encoding='utf-8')
        catalog = source.index('if let catalog = snapshot.catalog')
        self.assertLess(source.index('Section("Laptop connection")'), source.index('if snapshot.videos.isEmpty'))
        self.assertLess(source.index('if snapshot.videos.isEmpty'), catalog)
        self.assertLess(source.index('VideoWorkflowSummary(video: video)'), catalog)
        self.assertLess(source.index('if snapshot.hasMore == true'), catalog)
        self.assertEqual(source.count('WorkflowVoiceCatalogView(catalog: catalog)'), 1)

    def test_receipt_and_next_action_are_visible_without_expanding_events(self):
        source = (ROOT / 'VoiceMatrix/VideoWorkflowView.swift').read_text(encoding='utf-8')
        self.assertIn('video.receiptEvent', source)
        self.assertIn('Received on laptop', source)
        self.assertIn('Laptop receipt not confirmed', source)
        self.assertIn('Video is on the laptop', source)
        self.assertIn('Receipt time unavailable', source)
        self.assertIn('Text(video.status.title)', source)
        model = (ROOT / 'VoiceMatrix/VideoWorkflow.swift').read_text(encoding='utf-8')
        self.assertIn('case .awaitingPreparation: return "Waiting for voice preparation"', model)
        self.assertNotIn('Waiting for reviewed speech segments', model)
        self.assertIn('case .awaitingPreparation: return "Waiting before voice preparation."', model)
        self.assertIn('video.processingSummary', source)
        self.assertIn('video.nextAction', source)
        self.assertNotIn('Processing is active in the queue.', source)

    def test_connection_host_and_failures_are_safe_and_separate_from_progress(self):
        source = (ROOT / 'VoiceMatrix/VideoWorkflowView.swift').read_text(encoding='utf-8')
        self.assertIn('VideoWorkflowConnectionDisplay.host', source)
        self.assertIn('UserDefaults.standard.string(forKey: "laptopURL") ?? LaptopConnection.bundledURL', source)
        self.assertIn('VideoWorkflowConnectionIssue(error: error)', source)
        self.assertIn('Connected · laptop snapshot received', source)
        self.assertNotIn('error.localizedDescription', source)

    def test_existing_poll_and_read_only_behavior_remain(self):
        source = (ROOT / 'VoiceMatrix/VideoWorkflowView.swift').read_text(encoding='utf-8')
        self.assertIn('VideoWorkflowFreshness.refreshNanoseconds', source)
        self.assertIn('requestGate.fetch', source)
        self.assertIn('visible && scenePhase == .active', source)
        self.assertNotIn('snapshot = nil', source)
        self.assertNotIn('LaptopConnection.send(', source)
        self.assertNotIn('LaptopConnection.requestCandidates(', source)

    def test_offline_ui_regression_uses_current_labels(self):
        source = (ROOT / 'VoiceMatrixUITests/CharacterEmptyStateUITests.swift').read_text(encoding='utf-8')
        self.assertIn('app.staticTexts["Could not reach laptop workflow"]', source)
        self.assertIn('app.staticTexts["Connected · laptop snapshot received"]', source)
        self.assertNotIn('app.staticTexts["Live workflow unavailable"]', source)

    def test_native_receipt_summary(self):
        compiler = shutil.which('swiftc')
        if not compiler:
            self.skipTest('Swift compiler unavailable; native receipt summary checks were NOT run')
        with tempfile.TemporaryDirectory() as directory:
            binary = pathlib.Path(directory) / 'receipt-checks'
            subprocess.run([compiler, '-parse-as-library',
                            str(ROOT / 'VoiceMatrix/VideoWorkflow.swift'),
                            str(ROOT / 'tests/native/VideoWorkflowReceiptSummaryChecks.swift'),
                            '-o', str(binary)], check=True, capture_output=True, text=True, timeout=120)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=30)
            self.assertIn('Receipt summary checks passed', result.stdout)
