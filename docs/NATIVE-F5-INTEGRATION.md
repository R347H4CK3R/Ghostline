# Native F5 character speech — source integration

The My Character Folder screen now routes selected imported references and newly entered text to the native F5 engine. It uses 32 flow steps and seed347, matching the CPU preview settings where supported. Native fp16 numerical behavior and perceptual quality still need evaluation. The standalone initial benchmark uses upstream defaults (16 steps); its latency is not a 32-step iPhone measurement.

The native app shares one audio-work lease between recording, speech, conversion and this character test route. Other voice models are unloaded before F5 runs; F5 unloads after each request to bound memory while other engines remain available. The selected reference is checksum-validated again. No stock speaker fallback occurs. The generated WAV can use the existing Listen, Save and Share actions. Cancellation takes effect around the current F5 sampling call; mid-step interruption is not implemented upstream.

The engine is loaded only from bundled F5TTS resources using fromBundle. The shared engine is separate from imported per-character folders. SHA-256 proofs and exact file names are checked before loading; the app never downloads missing engine files. Source-only compile builds contain a placeholder, so Create Test Speech is disabled there. Complete audio packaging must use the pinned bundle from aufklarer/F5TTS-v1-Base-MLX-fp16 revision685e88161a2841a5f102a6f8094613ba7131e350 and preserve its CC BY-NC4 model notice. No character reference assets or transcript bytes have been added to the public repository.

This source integration has not yet proven physical-iPhone synthesis, per-character intelligibility, likeness, or recording conversion. The folder importer and isolated ARM64 F5 API compile passed; source integration and the separate real Metal/network-denied audio benchmark must pass their own gates before packaging a new test kit. Existing released IPAs and feeds are unchanged.

## Real audio findings —2026-11-08

The complete app at bd320ebafd5f1f015074dac09be9b0b13190980b passed ARM64 compilation (Actions42442063240) and native import, ownership and listening-history tests (42442063329). This is compilation/storage evidence, not physical-device listening.

The initial hosted macOS Metal diagnostic, upstream16 steps/seed0, produced a decoded non-silent WAV whose independent tiny.en transcript matched the five requested words. The app's exact32-step/seed347 adapter then produced a WAV that failed independent word checks: tiny.en recognized different words (140% WER), and base.en also recognized different words. These settings must not be shipped as a verified character runtime. See docs/qa/native-f5-32-step-failed-wordcheck.json. Both runs denied network access during native generation; neither was an iPhone test.

A controlled4-configuration comparison (16/32 steps crossed with seeds0/347,3 neutral texts each) is running under Actions42442270742 on research/native-f5-calibration-20261108. It uses the exact app adapter, pinned weights and independent recognition with the unchanged10% WER/non-silence/no-clipping gate. No passing configuration or new IPA is claimed before its actual results. Parameter equivalence across PyTorch and MLX does not establish equivalent random state, numerical output or perceptual quality.

Listening feedback now persists independently of engine checks. Selecting or importing a different reference invalidates displayed acceptance; old generated output controls cannot be attributed to a different character. This records the listener's explicit decision, without inventing objective similarity scores or treating it as a controlled assessment.
