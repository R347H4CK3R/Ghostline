# VoiceMatrix: shared-engine offline voice architecture

Research/design decision only. The current native app does not implement this neural inference architecture yet.

## Core
- Use FluidAudio PocketTTS CoreML Swift engine for both text-to-speech and conditioning from short, rights-cleared reference recordings. Bundle all necessary CoreML model assets at build time; default initializers can download assets and are not acceptable for a no-download installation.
- Voice library = validated small per-speaker conditioning profiles + one shared model. Store source URL, source license, voice-use consent, embedding SHA-256, language/accent, profile bytes, and device-audio verification receipt.
- Prefer a single English model, lazy-loaded profiles and cached sessions over 500 independent RVC/TTS checkpoints.
- Phonon 31m English is a possible alternative small engine. It provides 103 presets overall, but not all are American. Verify the full deployment size (codec/runtime and text weights), license, voice rights and native iOS performance.
- Kyutai voice-donations has 228 CC0 verified volunteer submissions; these are references, not 228 automatically playable models. Verify accent and preprocess authorized samples into conditioning profiles.
- Optional Kokoro can provide pronunciation control later, but is a separate heavy model and should not be part of the initial small IPA without measured benefit.

## User experience
Two primary beginner actions: (1) Type words -> Choose voice -> Hear -> Save; (2) Record -> Choose voice -> Transform -> Hear -> Save. Large buttons, plain language, guided first-run checks.
Recorded voice -> transcription -> TTS is an offline phase-one replacement, NOT true waveform-preserving or real-time voice conversion. A separate optimized conversion engine is required for those capabilities.

## Identity, counts and offline verification
- Never count search results, fan uploads, style presets or names as downloaded/verified voice models.
- Every included voice profile must be individually rights-reviewed, locally bundled, checked by SHA-256, and played successfully on a physical offline iPhone before being marked device-verified.
- Any claim that a profile replicates a specific singer, actor or fictional-character performance must have suitable model and likeness-use authorization and independent listening comparison.
- No auto-downloading at runtime. IPA must contain all engine assets and all included profiles. Local user recordings remain local.
- The project goal is 500 usable profiles, not 500 separate engines or 500 unverified identity claims.

## Reference documentation
https://github.com/FluidInference/FluidAudio/blob/main/Documentation/TTS/PocketTTS.md
https://huggingface.co/agentory/phonon-31m-en
https://huggingface.co/kyutai/tts-voices
https://huggingface.co/hexgrad/Kokoro-82M