# VoiceMatrix

Native ARM64 voice studio for iPhone 16 Plus, LiveContainer and Strata. **0.4.5 build 1 adds long speech, saved/shared audio controls and public suggestion drafts.** It is not the completed autonomous video-to-voice project.

[Download the inspected unsigned IPA](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.4.5/VoiceMatrix-0.4.5.ipa) · [LiveContainer source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/source.json) · [Strata source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/strata-source.json) · [Test source](https://raw.githubusercontent.com/R347H4CK3R/Ghostline/main/livecontainer-test.json)

Speech has no fixed character cap: complete-word chunks stream to disk within a protective 30-minute raw-audio budget. Speed, pitch, volume and pause controls apply to saved/shared speech. Suggestions open an explicitly public GitHub draft for your review and submission. Imported voices, references and saved recordings remain in the existing private data container.

## Install and import

1. Install **0.4.5 build 1** from the source above.
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

The speech planner splits complete-word chunks and validates tokenizer length. Jobs exceeding approximately 30 minutes of predicted/raw audio fail clearly without silently dropping words. Keep the app open and allow storage for long outputs; the budget is not an endurance-test claim. Speed ranges from 0.5–2x, pitch from -12–12 semitones, volume from 25–100%, and inter-part pauses from 0–1 second. Conversion accepts recordings up to 10 seconds. Cancellation is cooperative between model calls. [Runtime and import details](docs/CHARACTER-TEST-KIT.md).

## Updates

In VoiceMatrix, open **Settings → Check for Updates** to check and download the latest published IPA or copy its link and open Strata. Exit VoiceMatrix before Strata replaces the existing app; keep its existing data container. Do not delete the app first. The iPhone handoff still needs device verification.

All three existing source URLs track verified public releases. Publication updates them after native gates and a downloaded-asset audit; the release feed workflow also checks on publication and hourly, preserving older versions and refusing incomplete evidence, conflicting assets or downgrades. An Actions test artifact is not a published update.

## Suggestions

Open **Settings → Suggestions** (also available from the voice studio). Drafts stay on the device until you open GitHub; opening sends the entered title/body in the browser URL. GitHub sign-in and a separate Submit action are required to publish. Submissions are public. The app attaches no voices, audio, speech history, logs or device identifiers automatically; do not enter private information.

Daily review is configured for owner-authored issues with the `[VoiceMatrix suggestion]` title prefix. An attempted run is recorded, but no execution result is available to verify. Requests are assessed against current work and tested before being described as fulfilled; fulfillment is not guaranteed.

## Verification

[Native audio gates run 42621717205](https://github.com/R347H4CK3R/Ghostline/actions/runs/42520114505) passed all five jobs against packaged source `4c42e6ad9780169e8a7afdf4a5ed8efe4c8d64b9`:

- All 16 simulator checks passed, including reference playback progress, stop/replay, stale callbacks, updater validation, actual audio effects, long-text entry, suggestion acknowledgement/draft retention and imported-reference playback after relaunch; see [run 42559606073](https://github.com/R347H4CK3R/Ghostline/actions/runs/42559606073). The owner reported working audio in 0.4.3; the refreshed interface still needs physical iPhone verification.
- Frozen dependencies, unsigned ARM64 compilation, bundle/version/icon/license/model checks and compiled Metal shaders.
- Actual folder import and 13 native hosted-Mac Metal F5 diagnostic clips, including a forced two-chunk paragraph, under denied network access. Production-setting independent word/audio checks passed.
- Actual iOS-simulator folder import, selected-reference encoding, neural conversion and valid WAV export. Independent recognition passed with zero word errors.
- Matching source fingerprints, dependency identities and imported diagnostic profile/reference hashes across the IPA, speech and conversion evidence.

The published IPA was downloaded again and re-inspected: **731,110,554 bytes**, SHA-256 `377d7b9d1c09dcbd023e5f2ea3199f2d2bc96a0684180c4a9a0a66b08e0ab7b0`. All three installation feeds point to that exact asset and preserve older versions. [Release verification](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.4.5/character-release-verification.json) · [Speech evidence](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.4.5/speech-evidence.json) · [Conversion evidence](https://github.com/R347H4CK3R/Ghostline/releases/download/voicematrix-v0.4.5/conversion-result.json).

These checks use one neutral diagnostic profile; they do not verify every private character. F5 was tested on hosted Mac Metal because MLX documents unsupported array evaluation in iOS Simulator. [Simulator limitation](docs/qa/MLX-SIMULATOR-LIMIT.md). Physical iPhone loading, memory, Airplane Mode, host-container microphone behavior, latency and character resemblance remain unverified. No near-indistinguishable or official-character claim is made.

## Remaining development

The laptop now has a bounded reviewed-recipe processor, verified with real neutral CPU speech, independent recognition and reusable-folder export; raw links still require reviewed segments. Fully automatic labeling, complete queue/retry/discovery integration, reviewed replacement activation and further beginner workflow refinement remain unfinished. The RVC training companion has real preparation/training/index commands, but no new training or validated RVC export has been executed. F5 conditioning cannot be renamed into RVC weights. Expansion toward 500 usable character profiles remains a separate quality-gated goal.

[Build instructions](docs/BUILDING.md) · [Current engineering state](docs/DEVELOPMENT-STATE.md) · [Release](https://github.com/R347H4CK3R/Ghostline/releases/tag/voicematrix-v0.4.5)
