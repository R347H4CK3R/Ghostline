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
- Experimental offline neural TTS (Kokoro, PocketTTS and Piper) and RVC conversion are integrated into separate screens, but **physical iPhone/Strata generation, audio playback, model compatibility, and device memory safety are not verified**. No identity-accurate singer conversion is certified.
- An external provider must offer the mapped, authorized model and support the endpoint contract.
- GitHub Actions has generated experimental unsigned iOS IPAs; that proves only CI compilation/packaging. No physical iPhone/Strata installation or offline voice generation has been independently verified. Keep previously working releases intact.

## Build
Use Actions > **GHOSTLINE iOS IPA** > Run workflow, or push to main. When successful, download `GHOSTLINE-unsigned-IPA`, extract the artifact ZIP and import `GHOSTLINE-unsigned.ipa` in Strata if your version supports the app.
The unsigned IPA is not an App Store-installable signed app. Device compatibility and host entitlements must be tested separately.

## Neural voice setup
Choose an identity in the catalog. Enter your provider's HTTPS speech API endpoint, save an API key, and map an authorized model ID and voice ID. The app sends `POST` with JSON fields `model`, `voice`, `input`, `response_format: mp3`. Generated audio can be played and shared. If the provider rejects a mapping, the app reports the failure rather than pretending it generated that identity.

Use only voice models with appropriate permissions. Do not use voice cloning for impersonation, scams, or deceptive attribution.

## Free offline mode (November 2026)

The iOS app now has an **Offline-only mode** (on by default) and a picker listing English speech voices installed on the device. In offline mode the app uses Apple's AVSpeechSynthesizer without making speech API requests; it requires no subscription, API token or usage billing. Voices not already installed may require installation through iOS settings beforehand. Local speech can be played, microphone recordings captured and shared. Neither the iOS speech voices nor the 235 catalog references are identity-accurate celebrity or singer clones.

A truly offline **neural** speech library requires redistributable model weights and a compatible on-device inference engine (e.g. sherpa-onnx with Piper/Kokoro). Those are **not bundled or operational** in this release. A successful compile only demonstrates source packaging, not that offline neural cloning is functional or that Strata can run it.

## Native offline neural studio (experimental)

The `Neural Studio` screen connects two real, free CoreML synthesis backends through [arraypress/swift-tts](https://github.com/arraypress/swift-tts) at version 3.2.1:
- **Kokoro-82M** (Apache-2.0) with its available built-in synthetic voice presets.
- **Kyutai PocketTTS** (model weights CC BY 4.0, some voice presets CC BY-NC) with its separate available synthetic voice presets.

Select a backend, tap **Prepare model** (one-time internet access to download model weights), then select a voice and **Generate and play offline WAV**. Model weights are cached for reuse, so after successful setup and cache verification, synthesis is fully local. The app uses no paid service or generated-audio upload for these engines. Neural audio is exported to WAV.

**Accuracy:** Neither engine comes with authentic named celebrity or character replicas. The reference catalog remains distinct from actual generated synthetic voices. PocketTTS supports reference-voice cloning through its engine API, but the user-facing model-cloning workflow is **not yet wired into Ghostline**. This must not be described as finished voice cloning.

**Build verification:** Xcode 26.3+ and Swift 6.2 required to resolve swift-tts 3.2.1 dependencies. Device-side synthesis and memory usage are not verified by an unsigned IPA build.
