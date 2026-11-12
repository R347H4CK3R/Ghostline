"""Fail-closed publication and fresh-version evidence for the workflow release."""
import copy
import importlib
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WorkflowReleaseTests(unittest.TestCase):
    def publisher(self):
        self.assertTrue((ROOT / 'tools/publish_voicematrix_048.py').is_file(),
                        'The new release must have its own fail-closed publisher')
        return importlib.import_module('tools.publish_voicematrix_048')

    def binding(self, publisher):
        return dict(candidate='a' * 40,
                    gates={name: i + 100 for i, name in enumerate(publisher.REQUIRED_GATES)},
                    ipa_sha256='b' * 64, ipa_bytes=123456)

    def test_unbound_publisher_stops_before_external_calls(self):
        p = self.publisher()
        with mock.patch.object(p, 'CANDIDATE', ''), mock.patch.object(p, 'api', side_effect=AssertionError('External call before binding')) as api:
            with self.assertRaisesRegex(AssertionError, 'Unbound'):
                p.wait_for_gates()
            api.assert_not_called()

    def test_binding_requires_every_fresh_gate_and_ipa_identity(self):
        p = self.publisher()
        good = self.binding(p)
        p.validate_binding(**good)
        for change in [dict(candidate=''), dict(candidate='0' * 40), dict(ipa_sha256=''),
                       dict(ipa_bytes=0), dict(gates={}),
                       dict(gates=dict.fromkeys(p.REQUIRED_GATES, 100))]:
            with self.subTest(change=change), self.assertRaises(AssertionError):
                p.validate_binding(**dict(good, **change))

    def test_gate_must_be_successful_exact_source_workflow_and_repository(self):
        p = self.publisher()
        workflow = p.REQUIRED_GATES[0]
        run = dict(head_sha='a' * 40, path=workflow, status='completed', conclusion='success',
                   repository={'full_name': p.REPO}, event='push')
        p.validate_gate(run, 'a' * 40, workflow)
        for change in [dict(head_sha='b' * 40), dict(path='.github/workflows/voicematrix-047-candidate.yml'),
                       dict(status='in_progress'), dict(conclusion='failure'),
                       dict(repository={'full_name': 'other/repository'}), dict(event='pull_request')]:
            with self.subTest(change=change), self.assertRaises(AssertionError):
                p.validate_gate(dict(run, **change), 'a' * 40, workflow)

    def test_existing_tag_and_public_assets_are_verified(self):
        p = self.publisher()
        source = 'a' * 40
        p.validate_tag_target(None, source)
        for target in [dict(type='commit', sha='b' * 40), dict(type='tag', sha=source)]:
            with self.assertRaises(AssertionError):
                p.validate_tag_target(target, source)
        names = [p.IPA, p.IPA + '.sha256', 'character-release-verification.json',
                 'dependency-notices.json', 'speech-evidence.json', 'conversion-result.json']
        release = dict(tag_name=p.TAG, draft=False, prerelease=False, published_at='2026-11-12T00:00:00Z',
                       assets=[dict(name=name, size=10, digest='sha256:' + 'b' * 64) for name in names])
        report = dict(ipaSHA256='b' * 64, ipaBytes=10)
        p.validate_published_release(release, dict(type='commit', sha=source), source, report)
        for change in [dict(draft=True), dict(prerelease=True), dict(published_at=None),
                       dict(assets=release['assets'][:-1]), dict(tag_name='voicematrix-v0.4.7')]:
            with self.subTest(change=change), self.assertRaises(AssertionError):
                p.validate_published_release(dict(release, **change), dict(type='commit', sha=source), source, report)
        changed = copy.deepcopy(release)
        changed['assets'][0]['digest'] = 'sha256:' + 'c' * 64
        with self.assertRaises(AssertionError):
            p.validate_published_release(changed, dict(type='commit', sha=source), source, report)

    def test_feed_conflicts_rejected_and_newer_release_preserved(self):
        p = self.publisher()
        entry = dict(version='0.4.8', buildVersion='1', downloadURL='https://example.test/app.ipa',
                     sha256='a' * 64, size=100)
        feed = dict(apps=[dict(bundleIdentifier='com.voicematrix.app',
                              versions=[dict(entry, sha256='b' * 64)])])
        with self.assertRaises(AssertionError):
            p.publication_feed(feed, entry, 'Live workflow')
        newer = dict(apps=[dict(bundleIdentifier='com.voicematrix.app',
                               versions=[dict(entry, version='0.4.9')])])
        self.assertEqual(p.publication_feed(newer, entry, 'Live workflow'), newer)

    def test_fresh_candidate_has_correct_version_without_old_evidence(self):
        path = ROOT / '.github/workflows/voicematrix-048-candidate.yml'
        self.assertTrue(path.is_file(), 'A fresh 0.4.8 candidate is required')
        text = path.read_text()
        self.assertIn('VoiceMatrix-0.4.8-character-test.ipa', text)
        self.assertIn("'0.4.8'", text)
        self.assertNotIn('0.4.7', text)
        # Historical 0.4.8 workflow stays version-bound; current app identity
        # is checked separately by test_verbose_log_candidate.


if __name__ == '__main__':
    unittest.main()
