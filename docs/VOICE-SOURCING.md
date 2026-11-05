# Voice sourcing and licensing plan

## Voice acquisition

The 235 catalog entries are references, **not** preinstalled or verified functional clones. Do not label an identity "Ready" until a compatible authorized model is mapped, test audio has been generated successfully, and its use within GHOSTLINE is permitted.

1. **ElevenLabs Voice Library**: https://elevenlabs.io/voice-library — browse real community-shared professional voice clones and select ones licensed for the intended usage. Availability via API can depend on account tier, voice notice periods and pricing. Use provider voice IDs, not voice names or guessed IDs.
2. **ElevenLabs Iconic Marketplace**: https://elevenlabs.io/iconic-marketplace — request specific well-known voices via a license agreement defining app distribution, permitted content, territories, duration, API access, and fees. Marketplace listings must not be treated as automatically available in a third-party app.
3. **Respeecher**: https://www.respeecher.com — consider custom voice licensing for rights-holder-approved iconic performances. Client onboarding and written voice-owner consent apply; do not assume public API availability.
4. **ElevenLabs Voice Design**: https://elevenlabs.io/docs/overview/capabilities/voices — create new synthetic original voices such as a masked horror caller, gothic narrator, robotic commander, and trailer announcer. These are distinct original voices, not celebrity clones.
5. **Voice owners and performers**: request written consent, including authorization to create a voice model, permitted synthesis and app redistribution, and revocation process. For ElevenLabs Professional Voice Clone, the owner must create and verify their own model before sharing it.

## Functionality requirements

- Integrate provider voice-ID search, voice preview, licensed status, and model mapping.
- Keep API tokens in Keychain, never in app bundle, source repository or logs.
- Render voice availability as `Unlicensed`, `Licensed/Configured`, `Provider-ready`, `Audio-verified`, with each state independently checked.
- Verify real generated audio, not just HTTP 200; use test script, duration/format decoding and perceptual review.
- Distinguish named voice owners, original AI-designed styles, and style-inspired presets; never advertise a generic voice as a celebrity clone.
- Support a local model only if its license permits redistribution and the iPhone memory/performance constraints are verified.
- Celebrity and singer performance rights may be separate from recorded audio rights; singing synthesis requires a suitable singing model, which the existing TTS app lacks.

## Provider documentation
- https://elevenlabs.io/docs/eleven-creative/voices/voice-library
- https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning
- https://elevenlabs.io/docs/overview/capabilities/voices
- https://www.respeecher.com/faq

## Current release
`v0.1.0-preview` is a compiled unsigned IPA preview. The named catalog entries do not yet have installed or API-accessible celebrity voice models.
