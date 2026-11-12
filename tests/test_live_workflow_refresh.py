import pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class LiveWorkflowRefreshTests(unittest.TestCase):
 def test_native_view_uses_thirty_second_policy_and_preserves_last_snapshot(self):
  source=(ROOT/'VoiceMatrix/VideoWorkflowView.swift').read_text(encoding='utf-8')
  self.assertIn('VideoWorkflowFreshness.refreshNanoseconds',source)
  self.assertIn('VideoWorkflowFreshness.isStale',source)
  self.assertIn('Task.sleep(until: nextRefresh, clock: .continuous)',source)
  self.assertLess(source.index('let nextRefresh = ContinuousClock.now'),source.index('await refresh()',source.index('while !Task.isCancelled')))
  self.assertIn('Current reported stage',source)
  self.assertIn('WorkflowVoiceCatalogView',source)
  self.assertNotIn('snapshot = nil',source)
 def test_browser_uses_thirty_second_refresh_without_erasing_history_on_failure(self):
  source=(ROOT/'tools/workflow_log.html').read_text(encoding='utf-8')
  self.assertIn('setTimeout(refresh,Math.max(0,30000-(performance.now()-started)))',source)
  self.assertIn('Last recorded event',source)
  self.assertIn('catalog.events',source)
  self.assertIn('Long computation alone does not prove a stall',source)
