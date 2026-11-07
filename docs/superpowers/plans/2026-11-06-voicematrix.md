# VoiceMatrix implementation plan

Goal: native, beginner-friendly offline English speech studio with a bundled shared Phonon engine and compact profiles.
Architecture: SwiftUI screens, one FluidAudio Core ML manager, local-only model loading, streaming PCM WAV output, private saved recordings. No system speech fallback. No voice-conversion claim until a separate engine passes audio tests.
Spec: user supplied VoiceMatrix mission, 2026-11-06.

## Tasks
- [ ] Asset integrity: test rejection of missing, changed, duplicate and unsafe-path assets; implement pinned development-time downloader and manifest validator.
- [ ] Native speech: local pack loading, profile selection, streamed WAV, cancellation, playback, favorites, search, previews, recent profiles, save/share/rename/delete.
- [ ] Recording: permission, record/import/play/save, accurate conversion-unavailable explanation.
- [ ] CI: macOS build, model/profile integrity, unsigned arm64 IPA inspection, experimental artifact only. Publish only after actual build/archive checks.
- [ ] Validate tests, inspect Swift and dependencies, build where Apple toolchain is accessible, report measured limits.

## Review focus
Missing bundled model must fail without network. Cancellation must remove partial WAV. Save must not duplicate files. Invalid imported audio must fail clearly. Candidate counts must not become device verification claims.

## Decisions
Use Phonon 31m as first integration because its native API accepts a local pack and published profiles. This is provisional until comparative device benchmarks. 37 English embeddings are candidates, not 500 verified voices. Keep old releases untouched. Current host is Linux; connected hardware is Windows, so Apple execution requires GitHub macOS.
