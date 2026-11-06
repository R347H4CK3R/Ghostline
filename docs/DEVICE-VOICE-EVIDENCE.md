# Ghostline offline voice provenance and device-validation protocol

Updated: 2026-11-05. **This is not an identity voice certificate.**

## Voice software and data provenance

| Backend / pack | Provenance | Usage-rights checkpoint | Status |
| --- | --- | --- | --- |
| Piper `en_US-libritts_r-medium` | [Official Piper model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/libritts_r/medium/MODEL_CARD); 904 speakers according to the model card, 22,050 Hz, based on [OpenSLR 141](http://www.openslr.org/141/) | Dataset is CC BY 4.0; provide attribution, inspect the per-model card and applicable code/package licenses before sharing. This is **not** consent to describe a speaker as a particular celebrity. | Installed model must produce real decoded PCM on the target device before counting successful generation. |
| Kyutai PocketTTS | [Official project](https://github.com/kyutai-labs/pocket-tts); [Kyutai documentation](https://kyutai-labs.github.io/pocket-tts/) | Model weights and voice presets may have different licenses, including noncommercial presets. Respect per-voice rights and identify a preset by its official ID. | Engine connected in the app; no target-device listen test supplied. |
| Kokoro via FluidAudio | [FluidAudio](https://github.com/FluidInference/FluidAudio) | Review model/card and each voice pack license; a ready-made style cannot be labeled as an actor or character identity. | Core ML engine connected; no target-device listen test supplied. |
| Private RVC `.pth` / `.index` imports | Source and rights note entered by importing user; file SHA-256s recorded locally | **User-entered permission notes are not independently validated**. Keep weights private unless creator and performance rights are documented. | Import + hash integrity only. No converter, pitch extractor, content encoder, or RVC voice synthesis on iPhone yet. |
| Imported converted Core ML `.mlmodel` | User-selected model, local Core ML compile/load probe | A graph load is neither an authorized identity claim nor proof of audio synthesis. | Graph compile/load and input/output names only. |

## Provenance discrepancy

The catalog metadata derived from Piper's upstream index currently lists 2,306 `en_US-libritts_r-medium` speaker entries, while its official model card states **904**. Ghostline must derive playable ID bounds from the **installed model's `num_speakers`** and must never assume that 500, 904, or 2,306 represent verified unique human voices. The 500 and 8,000 goals are milestones, **not application limits**. Additional authorized voice packs and backends may increase the library independently of Piper's per-model speaker capacity.

## Device-side proof required

1. On the actual iPhone with the intended Strata/LiveContainer host, prepare the legitimate model and note its checksum, iOS version, and app build.
2. Disconnect network and enable airplane mode **after** the required first-time download. Confirm that voice synthesis does not require network or an external provider.
3. Generate the same controlled phrase for a test ID. Validate the WAV header and decode to non-silent PCM. Store the **decoded PCM SHA-256**, not the WAV container's hash.
4. Listen to each generated file, inspect human quality and audible differences, and verify the exact identity only by comparison with **authorized** reference audio.
5. Export the private evidence JSON and attach the corresponding WAV privately. The app's JSON intentionally reports airplane-mode, listening, and identity checks as false until independently attested.
6. Only then, and only if the specific voice identity and intended use are legally authorized, include the entry in the verified identity manifest. Keep unreleased models and recordings out of public workflow artifacts.

### Evidence tiers

- **Candidate**: model ID / catalog label / imported files exist.
- **Technical generation evidence**: actual iPhone non-silent decoded PCM, SHA-256, model checksum, host/runtime context.
- **Offline playback verified**: physical target iPhone generates and plays the recording while offline, recorded by an independent tester.
- **Authorized authentic identity verified**: attribution, written rights, direct listening / identity evidence and matching model/audio hashes all reviewed.

A GitHub Actions macOS build or an unsigned IPA **only** establishes that the app compiled and packaged. It does not advance a candidate into an audio-verified, offline-verified, or authentic-identity-verified entry.

## Experimental RVC native playback / human evidence (November 5, 2026)

- After a **structurally validated, non-silent** RVC WAV is saved, the experimental converter offers **Play saved WAV on iPhone** through `AVAudioPlayer`. Native playback start is logged separately from mere WAV output and separately from a person's listening.
- After playback starts, the user may explicitly acknowledge hearing **that particular WAV**. The app resets both flags when a different recording is imported from the web engine. Listening acknowledgement is a user assertion only, **not** perceptual identity validation, proof of an offline/airplane-mode environment, evidence of legal performance rights, or automatic promotion to a verified voice.
- Private RVC diagnostic JSON schema 2 records `device_audio_playback_started` and `user_attested_listening` and retains `voice_identity_verified: false`, `airplane_mode_confirmed: false`, `voice_rights_independently_verified: false`, and `rvc_index_retrieval_integrated: false`. Each new event invalidates previously generated JSON so exports reflect the most recent state. Do **not** publish these diagnostics without reviewing their contents.
- Code and CI source gates are preliminary, not physical iPhone/Strata proofs. A successful arm64 build alone cannot prove audio generation or that the user actually heard the WAV.
- Starting with experimental v0.9.2, accepted RVC output diagnostics carry both a WAV-container SHA-256 and a separate `pcm_audio_payload_sha256` over the WAV's uncompressed sample bytes. The latter stays stable when only RIFF metadata changes. NaN/infinite float samples and all-signed-zero float output are rejected. The PCM digest is **not** perceptual proof of intelligibility, identity, rights, or network isolation; it is only a reproducible audio-payload fingerprint.

## Privacy and safe updates

Do not commit private model weights, third-party reference audio, account tokens, device identifiers or user permission letters to the public repository. The private RVC audit export includes entered names and rights notes, so treat it as private information. Use draft experimental PRs and preserve existing download releases until target-device proof is available.

## Experimental Piper cache and evidence hardening (November 5, 2026)

- A downloaded Piper ONNX model and its JSON configuration now enter a private staging directory together. Each file is checked against the upstream registry MD5, the speaker count is validated, and both are SHA-256 fingerprinted **before** replacing the installed directory. A failed transfer should retain an existing intact pack; this rollback behavior still requires target-device testing.
- At launch, an installed model is **not considered ready** simply because files exist: both checksums and a positive configuration speaker count must validate.
- Device-test checkpoints are schema `piper.voice.lab.decodedPCM.v3`, bound to the exact ONNX and configuration SHA-256 pair. Pre-existing unbound v2 test counts are deliberately not migrated or considered evidence. Changing the model/config invalidates prior candidate test hashes.
- Evidence JSON schema version 2 includes `model_sha256` and `config_sha256` alongside decoded PCM hashes. An export is refused when either installed file no longer matches the tested model. Neither this code nor successful CI compilation establishes actual on-device playback, voice distinction, airplane mode, or identity authorization.
