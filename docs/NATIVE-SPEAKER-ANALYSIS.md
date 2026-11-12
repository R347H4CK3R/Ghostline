# Bundled native speaker analysis: development boundary

The local studio now calls FluidAudio's offline diarizer before choosing references. It decodes one local audio track to bounded 16 kHz mono floats, loads only verified bundled CoreML models, and keeps model progress distinct from the log view's refresh. This is wired to the existing job path, not a standalone demonstration.

The model revision is `FluidInference/speaker-diarization-coreml@df2625ac79a7ac6b65ad868fee6d80f320da4232`. The 26 pinned files total 21,639,362 bytes, including attribution, license, upstream README/citations and provenance. Only the supported Community-1-derived segmentation, FBank, embedding, PldaRho and PLDA parameters are included. The scoped license is CC-BY-4.0. The upstream provenance explicitly says historical segmentation/embedding conversion revisions were reconstructed, not attested; this project does not claim a reproduced model conversion.

`tools/bundle_diarization.py` downloads at build time, checks every expected size/hash and refuses to replace conflicting existing bytes. Runtime has no download or purge path. It validates a source-pinned manifest hash and each model file before manually constructing `OfflineDiarizerModels`. Missing models stop explicitly. The candidate IPA workflow stages these assets and checks packaged bytes; source-only UI builds intentionally do not contain models.

## Bounds and honest interpretation

- At most 512 MiB source, 30 minutes, 28.8 million decoded floats (115.2 MB for the sample array, plus models and inference allocations).
- Audio timestamp discontinuities or offsets beyond 50 ms fail closed rather than silently applying speaker windows to the wrong video timestamps.
- Segmentation and embedding batch sizes are 1. This bounds batching, not all process RSS. Physical iPhone memory, speed and thermal behavior still require measurement.
- At most 10,000 timing segments and 32 speaker groups. Exceeding limits stops explicitly rather than inventing/truncating a cast.
- The overlap sweep discards intervals where two distinct model speaker labels are active. It does not assign overlapping audio to the first speaker. Duplicate segments for the same label do not become false overlap.
- Each candidate is one contiguous non-overlapping turn with 150 ms boundary padding, at least three seconds and at most eight seconds. Up to three candidates per group are tried. Short-only groups remain visible as needing review.
- Speaker labels remain unidentified. Timing/embedding groups are not character names, voice separation, music removal, likeness verification or RVC training.
- Retained analysis is hash checked and its candidate windows recomputed on Resume, preserving speaker-label continuity. Accepted references are reused without replacement; missing/failed groups remain explicitly unresolved. All source and reference/preview attempts remain retained.

## Verification boundary

Python tests exercise real staging corruption, path/link refusal and no replacement. Swift unit/standalone tests exercise overlap and bounds policy. Native compile, actual model inference, synthetic multi-speaker speech validation and physical-iPhone end-to-end processing are separate gates; no source-contract test proves them. This is not VoiceMatrix 1.0.0 acceptance.

The simulator model tests require real bundled inference on silence and on six repetitions (about 15 seconds) of the existing hash-pinned neutral synthetic conversion fixture. The positive test requires model segments and speaker groups, exercising the non-empty embedding/clustering path. The fixture belongs only to the test bundle, not the shipping app. These tests are wired, not claimed passed until CI executes them; no two-speaker accuracy or likeness is asserted.
