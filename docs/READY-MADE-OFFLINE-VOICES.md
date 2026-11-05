# Ready-made Voices — No Recordings Needed

This inventory is for **pretrained voices that GHOSTLINE can use without recording the user's voice**. Models and presets are distinct from the fictional-character/celebrity reference catalog. Availability means upstream publishes usable weights/audio; **functional in GHOSTLINE** requires successful runtime integration and a device WAV test.

## Highest priority: actual implemented engine adapters

1. **Kokoro-82M**, Apache-2.0, **54** preset voices, nine languages. iOS CoreML backend: `KokoroEngine` in `swift-tts`. Names and sample audio are documented at https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md. Names are stable voice identifiers `af_heart`, `am_adam`, `bf_alice`, etc. These are synthetic personas, not actor clones.
2. **Kyutai PocketTTS**, CC BY 4.0 weights, a documented selection of **18+** preset voices including Alba, Anna, Azelma, Bill Boerst, Caro Davy, Charles, Cosette, Eponine, Eve, Fantine, George, Jane, Jean, Giovanni, Lola, Jürgen, Rafael, Estelle. Upstream: https://kyutai-labs.github.io/pocket-tts/ and https://huggingface.co/kyutai/tts-voices. Some voice samples are CC BY-NC; users must respect each voice-specific licence. iOS CoreML adapter: `PocketEngine` in `swift-tts`.
3. **Additional Kyutai tts-voices**, https://huggingface.co/kyutai/tts-voices, reference recordings with per-folder rights (CC0, CC BY, CC BY-NC). PocketTTS can condition on pre-existing authorized samples instead of asking the app user to record anything, but **not yet automatically indexed, converted, or tested within GHOSTLINE**.

## Future expansion; NOT implemented as working voice engines yet

4. **Piper**, https://huggingface.co/rhasspy/piper-voices, large repository of offline ONNX models spanning many languages. Requires an iOS ONNX runtime, phonemizer and model/voice license checking; do not label Piper voices as installed or functioning before integration. Example speaker IDs include `en_US-lessac-medium`, `de_DE-thorsten-medium`, `fr_FR-siwis-medium`, `es_ES-sharvard-medium`, `ru_RU-denis-medium`. Specific Piper voice files may have different restrictions from the repo's MIT metadata. Download individual ONNX/config pairs only after checking MODEL_CARD.

## Acceptance criteria

- Generate an intelligible, playable WAV on a real iPhone in Strata using a pre-made neural voice.
- Confirm the second run works with airplane mode after the initial model installation.
- Keep each voice's legal attribution and any noncommercial restrictions visible.
- Model sizes, RAM use, iOS JIT rules and Strata file/cache access must be tested.
- Do not claim celebrity/character identity based on similarity or a matching file name.
