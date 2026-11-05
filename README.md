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
- No neural speech-to-speech, singer conversion, or offline neural inference.
- An external provider must offer the mapped, authorized model and support the endpoint contract.
- This repository has not yet established a successful iOS device build or verified Strata installation. Check Actions logs and artifacts.

## Build
Use Actions > **GHOSTLINE iOS IPA** > Run workflow, or push to main. When successful, download `GHOSTLINE-unsigned-IPA`, extract the artifact ZIP and import `GHOSTLINE-unsigned.ipa` in Strata if your version supports the app.
The unsigned IPA is not an App Store-installable signed app. Device compatibility and host entitlements must be tested separately.

## Neural voice setup
Choose an identity in the catalog. Enter your provider's HTTPS speech API endpoint, save an API key, and map an authorized model ID and voice ID. The app sends `POST` with JSON fields `model`, `voice`, `input`, `response_format: mp3`. Generated audio can be played and shared. If the provider rejects a mapping, the app reports the failure rather than pretending it generated that identity.

Use only voice models with appropriate permissions. Do not use voice cloning for impersonation, scams, or deceptive attribution.
