# Preserve imported conditioning

Existing character IDs must not silently switch conditioning during folder refresh. The importer now rejects a changed reference WAV checksum or transcript before committing the private index. Metadata-only updates and new IDs remain supported. This conservative interim guard rejects the entire collection refresh if any existing conditioning changes; earlier valid additions in that batch are not activated. It preserves the existing index format for prior app versions.

This is not candidate listening, approval or promotion. A changed sample remains in the external folder; the app needs a real staged comparison/engine-verification/promotion workflow before it can activate that replacement. No manifest-supplied approval bypass exists. Existing listening reviews cannot approve newly supplied conditioning merely because the ID is the same.

Regression: native production importer failed with 'Unreviewed conditioning replaced the active reference' before the guard. Checks cover changed transcript, valid changed WAV and cached bytes; a mixed batch checks that an earlier new ID does not leak into the active library after rejection. An independent focused review found no blocking guard issue and called out the whole-batch tradeoff.

The first macOS full suite exposed an unrelated incorrect priority-test assumption. The runner inherited nice=-10; adding10 correctly produced0. The assertion now requires an actual relative decrease in priority (capped at19), rather than an absolute nice>=10. Windows still checks the exact native BELOW_NORMAL class. No production scheduling code or audio/quality threshold was weakened.
