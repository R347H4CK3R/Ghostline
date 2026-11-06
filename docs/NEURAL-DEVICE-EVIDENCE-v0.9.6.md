# Neural audio evidence (experimental v0.9.6)

This branch adds a common physical-device evidence path to **PocketTTS** and **Kokoro**. The iPhone must actually synthesize a nonempty, structurally valid WAV. The shared native player must successfully finish before the user may attest that the entire recording was heard. Each export rechecks both the WAV-container and decoded-sample-payload SHA-256 digests; if the file changed, no report is produced.

The JSON includes engine, preset ID, sample rate, channels, WAV/PCM fingerprints, start timestamp, playback completion state and optional listening acknowledgement. It does **not** include synthesized text or private model files. Since runtime model hashes are not exposed by the current FluidAudio API, `model_weights_sha256` is `null`: do not infer model provenance or identity from the preset name alone.

Changing voices or starting a new generation clears earlier audio and listening evidence. The selected voice is captured before asynchronous synthesis and cannot be changed in the UI while synthesis is underway. Audio quality, device model compatibility and actual airplane-mode operation still require testing on the target iPhone/Strata installation.

**Not a verification claim:** Swift source guards and successful arm64 compilation do not prove that a voice generated audio on the physical iPhone. Neither local WAV structure nor a user's listening acknowledgment proves someone else's identity or grants rights. Evidence deliberately reports `airplane_mode_confirmed=false`, `voice_identity_verified=false`, `voice_rights_independently_verified=false`, and `perceptual_identity_review_confirmed=false`. These reports are private and may disclose preset IDs; do not publish without the user's consent. Do not treat 500 or 8,000 voice candidates as a cap or as verified identities.

## Target device check

After installing an experimental unsigned IPA through the user's approved private installation method, prepare the desired PocketTTS or Kokoro model while connected to the network. Once all necessary weights are cached, enable airplane mode, disable Wi-Fi, restart the app, select a preset and synthesize a short phrase. Confirm that the new WAV plays fully, acknowledge it in the app, and export the WAV and private JSON. The examiner must separately record whether the device was offline and identify the actual model files, voice provenance, usage rights and perceived identity if applicable. Do not label any candidate as verified without target-device evidence and the separate identity/rights review.

The same UI supports importing authorized private RVC `.pth/.index` candidates, but this change does not implement RVC index feature retrieval.
