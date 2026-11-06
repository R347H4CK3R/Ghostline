# Ghostline Community Voice Changer — experimental architecture

## What is actually implemented
- One primary **Voice Changer** entry point from the approved five-tab UI: pick a private RVC candidate, record or import source audio, open the experimental local converter, and replay/export only if conversion produces a WAV.
- Community source discovery (Kokoro, Piper, PocketTTS, Kyutai, creator-distributed RVC) with model-card links and explicit licensing / permission status.
- A separate user-confirmed, checksum-pinned download of Phoenix's original RVC v2 test weights and matching retrieval index. Downloads show file bytes, percentage, average throughput and stage. These files are imported as **unverified** private candidates, never redistributed through Ghostline releases.
- Offline local storage, checksums and an opt-in sanitized error queue. GitHub Issue posting requires a fine-grained token scoped to the repository's **Issues: write** permission, stored only in the iPhone Keychain. No token is embedded in the IPA. Auto-reporting requires internet; reports are public if the GitHub repository is public.
- Voice changer is **batch** conversion, not realtime audio streaming. RVC .index header inspection and import do not establish feature retrieval/inference support.

## Ground truth and blockers
- No physical iPhone 16 Plus / Strata offline conversion or human listening verified as of this source update.
- No celebrity, character or singer model rights are assumed or claimed. Zero new identity-verified voices.
- Raw .pth runtime compatibility with the experimental WebAssembly converter still needs target-device testing; ContentVec/RMVPE and input WAV are separate model inputs.
- The current guided recorder exports the original WAV to Files. The user then selects it in the converter; there is not yet a native recorder-to-WebView file bridge.
- Generic community assets are staged for audit only, not silently installed in another inference engine.

## Why download-on-demand
Large voice checkpoint archives inflate the IPA, create licensing uncertainty and consume scarce iPhone storage. Keep baseline rights-cleared Piper voices available and fetch only selected authorized candidate packs. Each new catalog entry must name the original source and license, pin weights/checksums, and never be counted verified from CI alone.

## Device evidence acceptance
In airplane mode (Wi-Fi explicitly disabled), record a novel sentence, convert with an authorized installed model, validate a non-silent WAV, replay completely, record memory/thermal/device details and separate user listening testimony. Test model pairing, repeatability, correct timbre and valid use rights. Only then may a device voice be labeled verified. Neither successful GitHub Actions nor model hash matching is sufficient.
