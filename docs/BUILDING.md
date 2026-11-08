# Build preparation

Use an Apple ARM64 executor with the supported iOS SDK, XcodeGen and Python3.12or newer. Before generating the project, run:

```sh
python3 tools/check_conversion_inputs.py
python3 tools/create_diagnostic_collection.py
```

The second command deterministically creates the test-only native profile collection from pinned, independently word-checked synthetic fixtures. It is a required generated input for the diagnostic test targets. The character-test workflow prepares it before every XcodeGen invocation; the source-only compile workflow also performs this preparation.

Source-only compilation additionally creates empty resource directories for Phonon/OpenVoice/F5TTS. This verifies source compilation only and does not produce a functional audio package. A distributable character-test IPA must use the pinned shared-model preparation, dependency notices, complete native audio gates and strict inspection in `.github/workflows/character-test-ipa.yml`. Private character folders are imported separately and never included in that IPA.

## Published updates

0.4.4 passed the complete [release gates](https://github.com/R347H4CK3R/Ghostline/actions/runs/42520114505). Keep the version in project.yml, packaging commands and release evidence consistent. Test artifacts are not installation-feed releases.

A public release must include its IPA, dependency-notices.json and character-release-verification.json with successful native speech/conversion and playback/updater evidence. The feed synchronizer checks the completed release pipeline, exact source, asset SHA-256, downloaded archive and zero-stock/private-profile audit before advancing all three existing sources. Publication performs immediate synchronization; release events and an hourly reconciliation provide repair. Run `python3 -m tools.sync_verified_release_feeds` for a read-only check; `--write` applies SHA-guarded updates. The maintenance workflow runs tests and a read-only audit before its write job. It never creates releases or advances to an Actions test artifact.
