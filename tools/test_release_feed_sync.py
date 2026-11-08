import copy, unittest
from tools.sync_verified_release_feeds import key, updated, validate, REPO

class FeedTests(unittest.TestCase):
    def setUp(self):
        self.entry = dict(version="0.4.3", buildVersion="1", downloadURL="https://example.invalid/app.ipa", size=12, sha256="a"*64)
        self.feed = {"apps":[{"bundleIdentifier":"com.voicematrix.app", "versions":[dict(self.entry, version="0.4.1")]}]}
    def test_numeric_versions_and_builds(self):
        self.assertGreater(key("0.10.0"), key("0.9.9"))
        self.assertGreater(key("0.4.3","2"), key("0.4.3","1"))
        for bad in ("v0.4.3", "0.4.beta", "1.2.3.4.5", "-1"):
            with self.assertRaises(AssertionError): key(bad)
    def test_preserves_history_and_input(self):
        original = copy.deepcopy(self.feed)
        result = updated(self.feed, self.entry)
        self.assertEqual(result["apps"][0]["versions"], [self.entry]+original["apps"][0]["versions"])
        self.assertEqual(self.feed, original)
    def test_no_downgrade(self):
        self.feed["apps"][0]["versions"][0]["version"] = "0.5.0"
        self.assertEqual(updated(self.feed, self.entry), self.feed)
    def test_noop_preserves_release_description(self):
        self.feed["apps"][0]["versions"] = [dict(self.entry, localizedDescription="Detailed release notes")]
        self.assertEqual(updated(self.feed, self.entry), self.feed)
    def test_conflicting_same_build_rejected(self):
        self.feed["apps"][0]["versions"] = [dict(self.entry, sha256="b"*64)]
        with self.assertRaises(AssertionError): updated(self.feed, self.entry)
    def test_incomplete_or_mismatched_evidence_rejected(self):
        report = dict(inspection=dict(version="0.4.3",build="1",archive="passed",bundleIdentifier="com.voicematrix.app",stockProfiles=0),
                      bundledCharacterProfiles=0, nativeDiagnosticSpeechPassed=True, nativeSimulatorConversionPassed=True,
                      playbackAndUpdaterSimulatorTestsPassed=True,sourceCommit="abc",ipaSHA256="a"*64,ipaBytes=12)
        release = dict(draft=False,prerelease=False,tag_name="voicematrix-v0.4.3")
        run = dict(status="completed",conclusion="success",head_sha="abc")
        jobs = [dict(name=n,conclusion="success") for n in ("resolve","ipa","speech","conversion","publish")]
        asset = dict(name="VoiceMatrix-0.4.3.ipa",size=12,digest="sha256:"+"a"*64,
                     browser_download_url=f"https://github.com/{REPO}/releases/download/voicematrix-v0.4.3/VoiceMatrix-0.4.3.ipa")
        validate(report,release,run,jobs,asset)
        for target, field, bad in ((report,"nativeDiagnosticSpeechPassed",False),(release,"draft",True),
                                    (run,"conclusion","failure"),(run,"head_sha","other"),(asset,"digest","sha256:bad")):
            old = target[field]; target[field] = bad
            with self.assertRaises(AssertionError): validate(report,release,run,jobs,asset)
            target[field] = old
        with self.assertRaises(AssertionError): validate(report,release,run,jobs[:-1],asset)

if __name__ == "__main__":
    unittest.main()
