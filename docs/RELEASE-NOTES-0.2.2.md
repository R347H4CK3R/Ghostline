# VoiceMatrix 0.2.2 experimental — expanded English voices

101 included profiles: the previous 37 plus 64 distinct publisher-catalog profiles tested with English speech. The additional source recordings include German, Spanish, Mexican Spanish, French and Brazilian Portuguese. Their source locales are labeled; English inference still uses the same bundled shared Phonon engine.

All 102 candidates generated valid, non-silent WAV audio in five passing native simulator tests. Each of the 65 additions also generated a varied English sentence. Independent whisper.cpp tiny.en checks recovered the exact short test sentence for all 101 retained profiles; the additions passed a <=10% word-error threshold on each of two sentences and had no full-scale samples. One candidate, Rebeca, was excluded for failing the short-sentence threshold. This automated check is not human listening, naturalness, speaker-identity or perceptual-distinctness verification.

The unsigned ARM64 IPA is filtered from the tested candidate to exactly the approved 101-profile manifest without changing its executable. All model assets and retained native audio evidence are hash-checked; accented archive names are normalized to NFC for reliable inspection. The previous working 0.2.1 release is preserved.

Runtime and included profiles are bundled for offline speech, previews and WAV export. Voice conversion is not enabled in this release; its independent native probe passed separately and remains development work. Physical per-profile verification: 0 recorded. Human listening verification: 0 recorded. Authorized recognizable likeness claims: 0. Near-indistinguishable quality is not claimed. The 500-profile goal remains in progress.
