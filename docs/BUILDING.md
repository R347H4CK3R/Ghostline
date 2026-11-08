# Build preparation

Use an Apple ARM64 executor with the supported iOS SDK, XcodeGen and Python3.12or newer. Before generating the project, run:

```sh
python3 tools/check_conversion_inputs.py
python3 tools/create_diagnostic_collection.py
```

The second command deterministically creates the test-only native profile collection from pinned, independently word-checked synthetic fixtures. It is a required generated input for the diagnostic test targets. The character-test workflow prepares it before every XcodeGen invocation; the source-only compile workflow also performs this preparation.

Source-only compilation additionally creates empty resource directories for Phonon/OpenVoice/F5TTS. This verifies source compilation only and does not produce a functional audio package. A distributable character-test IPA must use the pinned shared-model preparation, dependency notices, complete native audio gates and strict inspection in `.github/workflows/character-test-ipa.yml`. Private character folders are imported separately and never included in that IPA.
