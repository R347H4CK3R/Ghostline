# GHOSTLINE iOS

Native SwiftUI voice-studio app for iPhone and compatible IPA importers such as Strata/LiveContainer.

## Implemented
- Searchable 235-name catalog: 81 characters, 62 actors, 72 singers, 20 original voice styles.
- Local iOS system speech for typed text (NOT a celebrity voice clone).
- Microphone recording, recording playback and file sharing.
- HTTPS provider integration for OpenAI-compatible neural text-to-speech with per-catalog-entry model+voice IDs.
- API tokens stored in the iOS Keychain; authorization required for named voice mappings.
- GitHub Actions macOS workflow generates an unsigned IPA artifact.

## Limitations
- Catalog names are references, not 235 working celebrity/character/singer voice clones.
- No celebrity or character model files or commercial voice licenses are included.
- No verified on-device celebrity identity conversion or singer synthesis; offline neural inference has an experimental implementation but is not yet validated on the target iPhone.
- An external provider must offer the mapped, authorized model and support the endpoint contract.
- The November 5, 2026 GitHub Actions iOS build succeeded, but iPhone launch, Strata installation and offline neural synthesis are not yet independently verified.

## Build
Use Actions > **GHOSTLINE iOS IPA** > Run workflow, or push to main. When successful, download `GHOSTLINE-unsigned-IPA`, extract the artifact ZIP and import `GHOSTLINE-unsigned.ipa` in Strata if your version supports the app.
The unsigned IPA is not an App Store-installable signed app. Device compatibility and host entitlements must be tested separately.

## Neural voice setup
Choose an identity in the catalog. Enter your provider's HTTPS speech API endpoint, save an API key, and map an authorized model ID and voice ID. The app sends `POST` with JSON fields `model`, `voice`, `input`, `response_format: mp3`. Generated audio can be played and shared. If the provider rejects a mapping, the app reports the failure rather than pretending it generated that identity.

Use only voice models with appropriate permissions. Do not use voice cloning for impersonation, scams, or deceptive attribution.

## Free offline mode (November 2026)

The iOS app now has an **Offline-only mode** (on by default) and a picker listing English speech voices installed on the device. In offline mode the app uses Apple's AVSpeechSynthesizer without making speech API requests; it requires no subscription, API token or usage billing. Voices not already installed may require installation through iOS settings beforehand. Local speech can be played, microphone recordings captured and shared. Neither the iOS speech voices nor the 235 catalog references are identity-accurate celebrity or singer clones.

A truly offline **neural** speech library requires redistributable model weights and a compatible on-device inference engine (e.g. sherpa-onnx with Piper/Kokoro). A Piper engine and model-download interface are **included experimentally** in the latest build. Piper weights are optional downloads, not inside the IPA. No generated Piper audio has yet been independently verified on the target iPhone. A successful compile is not evidence of functional offline voice synthesis or Strata compatibility.

## Native offline neural studio (experimental)

The app now builds with FluidAudio 0.15.2 and a patched Piper-ObjC dependency, exposing Kokoro, PocketTTS and a Piper LibriTTS-R speaker test studio. The iOS Piper model is approximately 81 MB and is downloaded on demand. Its catalog currently contains 543 unverified candidates across 178 Piper models; those are metadata entries, **not 543 working iPhone voices**. The featured LibriTTS-R medium model has **904 speakers in its pinned model configuration**; the upstream `voices.json` index incorrectly reports 2,306 and stale file checksums. The experimental branch now pins checked model assets and rejects mismatches. A declaration is not proof that 500 speakers sound distinct.

**Latest successful native build:** [GitHub Actions run 42124743868](https://github.com/R347H4CK3R/Ghostline/actions/runs/42124743868), November 5, 2026, commit `9843f7e`. The job compiled the app for arm64 iOS, assembled an unsigned IPA, and uploaded `GHOSTLINE-unsigned-IPA`. The artifact inspection confirmed that the IPA contains the speech-support resource bundle and candidate manifest. **Verified functional Piper speakers on the actual target iPhone: 0 evidence received.** Neither the build nor its 500-ID batch loop establishes offline functionality, perceptual distinctness, or a successful Strata launch.

The experimental verification screen generates locally using Piper, decodes WAV files, and tracks per-speaker checks. On the device-evidence development branch it also computes non-silent decoded PCM hashes and provides a shareable JSON evidence report. These hashes demonstrate audio differences, not different human-perceived voice identities. Full verification still requires a real iPhone running offline, sample playback and listening review. The existing preview releases are preserved until that happens.

No celebrities, actors, singers or fictional characters have authorized functioning replicas in this project. Their names in the original 235-entry reference catalog do not represent available models.
