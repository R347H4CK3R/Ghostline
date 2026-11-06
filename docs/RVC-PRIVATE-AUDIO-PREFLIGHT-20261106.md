# Private recording import preflight — experimental v0.11.2

Scope: an additional storage/responsiveness safeguard for the Voice Changer in the experimental unsigned IPA. The existing offline RVC and Piper components are unchanged. This does **not** establish functioning iPhone/Strata synthesis, verified identity, or FAISS retrieval.

- The iOS Files importer now checks accepted extensions (WAV, MP3, M4A, CAF), regular-file status and byte length **before copying**. Empty or >128 MiB source audio is rejected without duplicating the large file.
- Security-scoped file access, copying into the application's temporary directory, and related disk I/O run in a detached user-initiated task, not SwiftUI's main actor. Recording and conversion navigation are disabled while import is active.
- The local RVC server independently rechecks temporary-root confinement, regular-file status, maximum length, and SHA-256 immediately before serving an unpredictable same-origin temporary route. Route is invalidated on converter teardown. Source audio does not reach GitHub diagnostics.
- Import errors use a sanitized diagnostic event without source path, recording bytes or filename. Conversion remains batch-only; not live microphone conversion.
- Limits are for private *source audio*, **not** limits on voice count. The 14 pinned Piper model candidates and 25 source-declared speaker slots remain **UNVERIFIED**. No private RVC weights or unapproved celebrity/character identities are bundled.
- Tests: `scripts/test_voice_changer_audio_preflight.py`, `scripts/test_voice_changer_direct_handoff.py`, existing rights, UI and voice evidence guards. These are source-level checks; physical iPhone/Strata synthesis and listening require device evidence.

## Source review notes

The pinned upstream Piper source-card scan identified potential CC BY LibriTTS-R (904 declared speaker slots) and Alba (CC BY 4.0), but both are derived from the U.S. English Lessac model. The Lessac card links to a separate Blizzard dataset license that has not been cleared for this bundle. They must **not** be added merely because their immediate training data is CC BY. The same concern covers CC0-marked Thorsten, Siwis, Sharvard, Kerstin and other models derived from Lessac/Ryan where the ancestor license may impose additional restrictions. Quarantine candidate labels are not distribution approval.

Existing release tags and LiveContainer source feeds are preserved. This branch is for private testing only.
