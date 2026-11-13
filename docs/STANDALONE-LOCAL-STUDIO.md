# Standalone local studio: implementation and verification boundary

This is a development candidate, not VoiceMatrix 1.0.0 acceptance.

## Implemented source path

An authorized local video or recording is copied into private app storage without sending it to a laptop or server. Bundled CoreML speaker analysis first groups local 16 kHz audio into tentative speakers, excludes model-detected overlap and retains its timing evidence. AVFoundation then extracts bounded mono 24 kHz PCM reference windows. Speech recognition uses pinned bundled Parakeet v3 CoreML assets, not OS speech permissions or installed language packs; missing or invalid bundled assets stop explicitly. Actual recognition on the new candidate remains a required native CI check. There is no server fallback.

Each tentative speaker group may supply up to three candidate windows, each confined to a contiguous speaker-only span. Alternate crops may overlap one another, but never cross intervals where different speakers were detected simultaneously. A usable transcribed reference drives the bundled F5 engine, with at most three preview attempts per group. An independent on-device spoken-word check must have at most 10% word error before the reference is atomically imported into the existing private library. The name is explicitly unidentified. A reference preset is never marked as a trained RVC model. The user can listen to the reference/preview and use the saved reference for new speech.

This mode attempts **one reference per tentative speaker group**, not a verified character cast. Audio energy and transcription confidence do not prove isolated speech, clean music separation, identity or likeness. A plausible transcript can still come from singing or overlapping speakers. Native diarization passed the bounded synthetic checks described below; real multi-speaker accuracy and physical-device behavior remain unverified. Visual attribution, separation, broad web-provider compatibility and native RVC training remain outstanding. See `NATIVE-SPEAKER-ANALYSIS.md` for provenance and limits.

The limited native URL path acquires authorized direct media from allowlisted hosts and some ordinary public YouTube responses without cipher/challenge bypass. Partial files and completed tracks are retained. Broad provider compatibility is not verified; see `NATIVE-MEDIA-ACQUISITION.md`.

## Retention and activity

The private job directory retains the copied source, reference WAVs, transcripts, completed previews, staged collection and a timestamped JSON stage log. It is separate from launch-cleaned temporary audio. Admission requires 800 MB available and refuses new jobs when measured retained data is already 2 GB; it never evicts existing files. A single admitted source can be up to 512 MiB, so this admission threshold is not an exact 2 GB global quota.

The screen refreshes its log view every second. It labels view refresh separately from the last actual processing update. After 30 seconds without a processing update it reports that the operation may still be busy, not that it has failed. The live snapshot retains the latest 160 selected events; the separate append-only journal retains every actual update within its explicit storage bound. The latest status is committed atomically.

Processing is foreground-first. Going into the background requests cancellation at a safe boundary, retains completed work and exposes Resume. Resume checks the source checksum and reruns selection/verification; this is stage retry, not an inference checkpoint. It does not promise unrestricted iOS background execution. The local studio opts into retaining incomplete F5 output files for diagnosis; other existing speech callers keep their previous temporary-output behavior. Incomplete files are not admitted as successful previews.

## Required verification

- Source contract tests check wiring and local-only safeguards, not native functionality.
- Native unit tests cover real synthetic AVFoundation extraction, source preservation, bounds, silence refusal and text/window policies.
- Native UI checks cover reopening without a laptop and disabled generation without selected media.
- Speaker-analysis assets are pinned and packaged without a runtime download. Candidate `be2890b` passed native synthetic speaker-positive/silence tests and native sound-screening speech/silence/tone tests. This does not prove multi-speaker accuracy, character identity or full pipeline success. Bundled ASR requires its actual native diagnostic; physical-iPhone thermal/memory behavior, complete import and airplane-mode new-text synthesis remain acceptance gates.
- CI must compile each exact new candidate. Earlier candidate compilation does not verify later source. The new macOS full-coordinator diagnostic uses installed synthetic speech, actual models and real atomic imports with networking denied; its presence is not a successful run. No phone test, character likeness or complete 1.0.0 acceptance is claimed by this document.

The laptop option and previous voices remain intact. Public source contains no user media, models, transcripts, pairing data or credentials. Publish 1.0.0 only after the agreed complete acceptance scope is verified; do not overwrite the released 0.4.9 IPA with this development candidate.

## Durable private event history

New jobs append each actual status/byte-count update to `events-v1.jsonl` in their private retained job directory, before updating the bounded 160-event live snapshot. The one-second UI refresh does not generate events or change the last-activity timestamp. Pause, resume and reopening the job append rather than replace history. There is no automatic journal or media deletion.

The “Complete retained event history” disclosure reads oldest-first pages of at most 100 entries. Refresh and next/previous controls read retained records; “Share this log page” explicitly exports only the displayed page through the system share sheet. It does not export source URLs, files, transcripts or model assets. Status text receives additional URL/path/credential-marker redaction. Older jobs retain compatibility: their existing snapshot is readable, and the first new append records that earlier events already truncated by older builds cannot be recovered.

The journal is limited to 16 MiB with at most 8 KiB per encoded event. Unsafe symlinks/hard links, oversized files and interrupted trailing records fail closed; the existing bytes remain untouched and processing reports a storage/history error rather than silently losing or rotating history. A partial record is retained for diagnosis, not automatically repaired. Files use private creation permissions and synchronized append. Actual Foundation behavior tests cover more than 160 events, pagination/reopen, redaction, legacy migration, linked/oversized files and torn-tail preservation. Swift-unavailable environments skip these tests explicitly; source-contract checks alone are not behavioral verification.

Journal descriptor opening is nonblocking before checking the file type, so a pre-existing FIFO cannot hang the main actor while waiting for a writer. The immediate parent directory is opened without following a final symlink; the job directory and fixed journal filename are then opened relative to retained directory descriptors with no-follow flags. This anchors journal operations even if those directory paths are subsequently swapped. Higher OS/app-container path ancestors remain trusted; this is not a general hostile-filesystem sandbox, and it deliberately does not reject legitimate system ancestors such as macOS `/var`. Native FIFO read/append rejection is exercised inside the Foundation test executable's 30-second subprocess deadline.
## Bounded alternate references

Selection keeps at most three candidates per speaker. Distinct clean contiguous turns are considered first (longest, then earliest); unused slots then consider four-second and three-second tail crops inside those same trimmed, overlap-excluded spans. Near-identical windows are deduplicated. No shorter-than-three-second reference is admitted, no different turns are concatenated, and classifier/word-error thresholds remain unchanged. Rejected attempts remain retained. This broadens bounded selection rather than certifying a clean voice or likeness.

Retained analyses without a selection-policy version (or version1) must exactly match the prior one-head-crop-per-turn policy before upgrade. Version2 must exactly match current selection. Unknown versions and arbitrary crop changes fail closed. A validated old analysis is upgraded into a new hashed file; its original file and source remain intact. Native synthetic tests must establish behavior on each candidate; alternative crops do not guarantee a job will succeed.

The bundled recognizer passed its network-denied Mac diagnostic at `055d53d8` on two pinned neutral fixtures with zero word error and cancellation/retry recovery. The full production coordinator compiled at `c8f1fa66`, retained its source and resumed cancellation, then correctly remained incomplete when its first reference failed conservative sound screening. Alternate-crop selection and full event history still require native verification on their final candidate. Neither result proves physical-iPhone behavior or character likeness.

## First complete production-coordinator regression

Candidate `d5afff603cfac7967fb80455bcaa0866b6120e95` passed diagnostic run `43307802622` on Apple Silicon with networking denied. The independently resolved diagnostic processed installed macOS synthetic neutral speech, imported one unidentified reference profile, preserved the previous profile, retained the original source with matching SHA-256, recovered cancellation/resume, reloaded the saved profile, and generated new text with zero measured word error. Evidence archive SHA-256: `b31b0242712fdff83536683f6625e1079dc7bca990f42094a5fbc6962f104263`.

This is an actual coordinator regression, not a simulation, but it is not physical-iPhone verification or proof of character identity/likeness. The diagnostic dependency graph was independently resolved (`d3788d2ebba47e0f6c6760ebbbb5c7c91736d8b48d9e81b14389c30487bd8fcb`); the same-source aggregate's shared frozen-graph gate and all release checks must also pass. The released 0.4.9 build remains unchanged.

The same-source aggregate run `43307802670` also passed the actual local-coordinator steps using its shared frozen dependency graph. Its downloaded evidence archive SHA-256 is `0ce384d15454c4e8cd9191e3dd25c7c877b73bd4e496b7941f4c7d3fe8cb29d3`; source retention, cancellation/resume, prior-profile preservation, fresh-store reload and zero word error on new speech were verified again. Other required release gates are evaluated separately.

The next development package uses version 0.4.9 build 2, distinct from released build 1. It is not 1.0.0 and does not claim complete character likeness, RVC training or physical-device acceptance. Any publication requires a fresh build and all exact-source gates; an old IPA must not be relabeled.

## Individual speaker audio receipts

New successful speaker imports and deduplicated-reference reuse retain an independent
receipt for that speaker's exact accepted reference and spoken-word-checked preview.
Each receipt binds both filenames, SHA-256 values and the imported voice ID. Selecting
another candidate never rewrites a previously saved speaker's pair. The result list now
exposes separate reference and preview playback controls per speaker, after processing
has stopped. These are preview-only references, not trained RVC models or identified
characters.

Playback requests validate both bounded regular files, reject symlinks, changed hashes,
unsafe paths and mismatched attempt names, and leave all files intact on failure. Checks
run on an explicit button action rather than each live-log refresh. This validates
private-container file snapshots, not a hostile-filesystem race-free sandbox. Existing
jobs without these optional receipts still load; no earlier file/voice is removed and no
unproven per-speaker pairing is retroactively invented.

Native unit coverage exercises two independent speaker pairs, reload, tampering and
cross-pair rejection. The actual audio/video production coordinator additionally reopens
the persisted job and requires each imported speaker's pair to validate and decode as
nonempty audio. These native checks require exact-source CI before claiming success;
Python wiring assertions alone do not establish playback on an iPhone.
