# VoiceMatrix

Native ARM64 voice studio for iPhone 16 Plus, LiveContainer and Strata. **0.4.4 build 1 is published with a redesigned voice studio.** It is not the completed autonomous video-to-voice project.

[Download the inspected unsigned IPA](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.4.4/VoiceMatrix-0.4.4.ipa) · [LiveContainer source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/source.json) · [Strata source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/strata-source.json) · [Test source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/livecontainer-test.json)

The refresh adds a simpler Home screen, searchable one-tap voice selection, grouped speech/reference controls and collapsed collection management. Working audio engines and private storage are unchanged. Thirteen simulator checks passed, including imported-reference playback after relaunch with the original import folder removed.

## Install and import

1. Install **0.4.4 build 1** from the source above.
2. Connect Tailscale on the iPhone and laptop using the same owner account; keep the laptop companion available.
3. Open **Make speech** or **Voices**. The character library checks your private laptop collection automatically. **Sync voices from laptop** retries; **Stop sync** cancels. Wait for the saved-reference count before testing speech.
4. Choose a character, type new words and tap **Create speech**, or record/import up to 10 seconds and tap Convert. Listen, save or share the resulting WAV.
5. Compare the reference and generated audio using **Matches / Doesn't Match / Unsure**. Word recognition cannot decide character resemblance.

Manual import is also supported: extract the private collection ZIP in Files, then choose the **Voices** folder containing `collection.json`. Select the folder, not the JSON file.

The app includes the shared speech and conversion engines, with **zero bundled character or stock voice profiles**. Imported revisions are copied into private storage for offline use; an unavailable external folder does not remove those copies. The laptop queue uses same-account Tailscale and needs no pairing JSON. After synchronization or manual import, speech and conversion use cached private copies without the laptop. Existing references with changed audio or conditioning text are rejected pending reviewed replacement support. Physical-device checks still require the phone. [Private sync protocol and checks](docs/PRIVATE-VOICE-SYNC.md).

## Current voices and categories

The private development collection has **60 reusable F5 reference-conditioning candidates**, with distinct IDs and reference hashes. Categories overlap without duplicate counting: Animation & Cartoons and Rick and Morty. Reference recordings and transcripts are excluded from this public repository and IPA.

All 60 generated preview clips passed decoding, non-silence, clipping, SHA-256 and independent word checks. These are intelligibility checks, not 60 finished likeness-verified models. The two originally accepted Rick/Morty previews are preserved. Their reusable conditioning candidates are explicitly experimental second-generation references derived from those generated previews; the other 58 use their corresponding source references.

| Measure | Recorded count |
|---|---:|
| Separate conditioning candidates | 60 |
| Bundled character profiles | 0 |
| Physical-device-verified character profiles | 0 |
| Controlled likeness approvals | 0 |
| Authorized recognizable likenesses | 0 |
| Newly trained RVC models | 0 |

The older 537-profile speaker/style library belongs to the preserved 0.3.0 release. It is not included or relabeled as character replicas in this test. [Historical release evidence](docs/RELEASE-0.3.0-HISTORY.md).

## Offline runtime

One shared `F5TTS_v1_Base` engine generates new text using the selected imported reference. The speech runtime is pinned to SpeechSwift `a57702e6f523fa36ac5532d2bdc5f35f701a052c`; model revision `685e88161a2841a5f102a6f8094613ba7131e350`. Pinned OpenVoice CoreML encoder/converter models perform actual speech-to-speech conversion with the selected reference. This is not real-time microphone conversion.

The IPA includes weights, tokenizers, vocoder, Metal shaders and license notices. Inference uses local files without cloud calls, credentials or first-launch model downloads. F5 weights carry noncommercial terms. Reference permissions and recognizable-likeness authorization are separate from engine licenses. The private candidates are not authorized for public redistribution.

The current speech test UI limits text to 500 characters, splits complete-word chunks and validates tokenizer length. Conversion accepts recordings up to 10 seconds. Cancellation is cooperative between model calls. [Runtime and import details](docs/CHARACTER-TEST-KIT.md).

## Updates

In VoiceMatrix, open **Settings → Check for Updates** to check and download the latest published IPA or copy its link and open Strata. Exit VoiceMatrix before Strata replaces the existing app; keep its existing data container. Do not delete the app first. The iPhone handoff still needs device verification.

All three existing source URLs track verified public releases. Publication updates them after native gates and a downloaded-asset audit; the release feed workflow also checks on publication and hourly, preserving older versions and refusing incomplete evidence, conflicting assets or downgrades. An Actions test artifact is not a published update.

## Verification

[Native audio gates run 42520114505](https://github.com/R347H4CK3R/Ghostline/actions/runs/42520114505) passed all five jobs against packaged source `b0a39f7525ca23b96d4f4f303abb732916485d5b`:

- Simulator reference playback progress, stop/replay, stale callbacks, visible controls and updater validation passed [run 42519869947](https://github.com/R347H4CK3R/Ghostline/actions/runs/42519869947). The owner reported working audio in 0.4.3; the refreshed interface still needs physical iPhone verification.
- Frozen dependencies, unsigned ARM64 compilation, bundle/version/icon/license/model checks and compiled Metal shaders.
- Actual folder import and 13 native hosted-Mac Metal F5 diagnostic clips, including a forced two-chunk paragraph, under denied network access. Production-setting independent word/audio checks passed.
- Actual iOS-simulator folder import, selected-reference encoding, neural conversion and valid WAV export. Independent recognition passed with zero word errors.
- Matching source fingerprints, dependency identities and imported diagnostic profile/reference hashes across the IPA, speech and conversion evidence.

The published IPA was downloaded again and re-inspected: **731,078,368 bytes**, SHA-256 `274ca2b0f64d0a884358f04e624f30f454830be0d7921bd02eeaa2a9c2c64059`. All three installation feeds point to that exact asset and preserve older versions. [Release verification](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.4.4/character-release-verification.json) · [Speech evidence](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.4.4/speech-evidence.json) · [Conversion evidence](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.4.4/conversion-result.json).

These checks use one neutral diagnostic profile; they do not verify every private character. F5 was tested on hosted Mac Metal because MLX documents unsupported array evaluation in iOS Simulator. [Simulator limitation](docs/qa/MLX-SIMULATOR-LIMIT.md). Physical iPhone loading, memory, Airplane Mode, host-container microphone behavior, latency and character resemblance remain unverified. No near-indistinguishable or official-character claim is made.

## Remaining development

The laptop now has a bounded reviewed-recipe processor, verified with real neutral CPU speech, independent recognition and reusable-folder export; raw links still require reviewed segments. Fully automatic labeling, complete queue/retry/discovery integration, reviewed replacement activation and further beginner workflow refinement remain unfinished. The RVC training companion has real preparation/training/index commands, but no new training or validated RVC export has been executed. F5 conditioning cannot be renamed into RVC weights. Expansion toward 500 usable character profiles remains a separate quality-gated goal.

[Build instructions](docs/BUILDING.md) · [Current engineering state](docs/DEVELOPMENT-STATE.md) · [Release](https://github.com/R347H4CK3R/Ghostline/releases/tag/voicematrix-v0.4.4)
