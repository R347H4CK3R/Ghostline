# Reusable character voice workflow

The user-approved next milestone is hands-off video import, speaker separation, reviewed character labels, reference synthesis, categorized profiles, TTS per usable character, real RVC training/index creation, inference checks, and export/import. Source updates only at this stage.

Implemented first component: `tools/voice_pack.py` exports and validates version 1 `.vmpack` archives for F5TTS_v1_Base conditioning. Each includes a mono PCM16 24 kHz 0.5–15 second reference, transcript, provenance/permission description, overlapping categories, SHA-256 and size. Engine weights are shared separately. Packs preserve references intentionally for future synthesis; temporary acquisition files may be cleaned after an authorized export. Do not publicly bundle unlicensed character reference recordings.

This format is **not a trained RVC model**. Real `.pth` and `.index` exports still need training and independent inference validation. Native iOS F5 inference, automatic diarization, training companion and app UI integration remain pending. Reference provenance fields record the supplied declaration, not legal verification. Passing pack tests establishes format integrity, not speaker resemblance.

Validation: `python -m unittest discover -s tests -p test_voice_pack.py` covers roundtrip, missing provenance, corruption, unexpected paths and silence. Reader rejects duplicate entries and oversized payloads without extracting archives.
