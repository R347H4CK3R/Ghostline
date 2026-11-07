# Expand the working offline voice library

1. Audit all named conditioning tensors from the same pinned Phonon publisher catalog; exclude default/duplicate profiles and preserve provenance and source locale.
2. Build a candidate-only IPA; synthesize every profile and a varied English sentence for each additional profile. Retain real WAVs and matching checksums. No candidate release is published automatically.
3. Run independent ASR and waveform checks on retained WAVs. Exclude failing new profiles from the available catalog. Treat these as automated checks, not listening/similarity/device verification.
4. Rebuild the approved catalog, inspect the downloaded unsigned IPA, publish the new experimental release and update both install feeds while preserving 0.2.1.

The existing shared model is unchanged. No renamed copies or DSP variants are counted. Candidate embeddings remain distinct only numerically until perceptual listening assessment.
