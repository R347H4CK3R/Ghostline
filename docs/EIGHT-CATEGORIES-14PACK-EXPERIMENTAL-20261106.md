# GHOSTLINE eight-category, 14-pack private test build — 2026-11-06

This experimental branch integrates two *distinct* validated source-level paths without merging them into the public release: the 14-model provenance-pinned Piper bundle from draft PR #29/#32, and the eight original synthetic demo categories from draft PR #31. The latter was separately compiled by GitHub Actions; this combined build needs its own Apple arm64 compilation and independent artifact audit.

Each of the eight categories (film, television, cartoons, anime, gaming, singers, celebrities, original voices) links to an actual bundled Piper model ID. These are **editorial demonstration styles only**, not voice replicas or authorized authentic screen/performer identities. There are no identity-verified celebrity, singer, actor, character or singer-model packs in this build. Piper speech is TTS, not singing synthesis.

The Library tab now navigates to individual categories, selectable model candidates, local offline Piper generate/replay/export, and optional test receipts. The separately licensed RVC Voice Changer offers batch conversion from an imported or recorded source, with the 128 MiB nonblocking import preflight and ephemeral SHA-256-checksummed localhost file route. RVC FAISS .index support remains import/inspection only; index retrieval inference is not implemented.

Source rights manifest: `Ghostline/Resources/approved-piper-bundle.json` contains model cards, dataset/source claims, revision pins, model/configuration/card SHA-256 and sizes for 14 model candidates and 25 declared speaker slots. `quarantined-piper-candidates.json` retains Swedish NST source conflict. Source-reported rights are not publicity/voice-cloning permission.

Verification: both eight-category route guard and private-audio preflight guard passed on Windows. These **do not** demonstrate physical iPhone/Strata synthesis or listening. **Verified target-iPhone offline voices: 0.** Existing public releases, main, private RVC weights and LiveContainer feed left untouched.

This is an experimental unsigned IPA test branch only. No arbitrary numerical voice-library cap has been added.
