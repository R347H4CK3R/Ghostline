# Standalone local studio: implementation and verification boundary

This is a development candidate, not VoiceMatrix 1.0.0 acceptance.

## Implemented source path

An authorized local video or recording is copied into private app storage without sending it to a laptop or server. AVFoundation extracts bounded mono 24 kHz PCM windows. English speech recognition requires `supportsOnDeviceRecognition` and `requiresOnDeviceRecognition`; missing permission or local support stops explicitly. There is no server fallback.

The first usable transcribed reference drives the bundled F5 engine. Up to three generated previews may be attempted on different candidate windows. An independent on-device spoken-word check must have at most 10% word error before the reference is atomically imported into the existing private library. The name is explicitly unidentified. A reference preset is never marked as a trained RVC model. The user can listen to the reference/preview and use the saved reference for new speech.

This mode produces **one reference**, not a complete character cast. Audio energy and transcription confidence do not prove isolated speech, clean music separation, identity or likeness. A plausible transcript can still come from singing or overlapping speakers. Automatic diarization, visual attribution, separation, web-video acquisition and native RVC training remain outstanding.

## Retention and activity

The private job directory retains the copied source, reference WAVs, transcripts, completed previews, staged collection and a timestamped JSON stage log. It is separate from launch-cleaned temporary audio. Admission requires 800 MB available and refuses new jobs when measured retained data is already 2 GB; it never evicts existing files. A single admitted source can be up to 512 MiB, so this admission threshold is not an exact 2 GB global quota.

The screen refreshes its log view every second. It labels view refresh separately from the last actual processing update. After 30 seconds without a processing update it reports that the operation may still be busy, not that it has failed. Logs retain the latest 160 events for each job. The latest status is committed atomically.

Processing is foreground-first. Going into the background requests cancellation at a safe boundary, retains completed work and exposes Resume. Resume checks the source checksum and reruns selection/verification; this is stage retry, not an inference checkpoint. It does not promise unrestricted iOS background execution. The local studio opts into retaining incomplete F5 output files for diagnosis; other existing speech callers keep their previous temporary-output behavior. Incomplete files are not admitted as successful previews.

## Required verification

- Source contract tests check wiring and local-only safeguards, not native functionality.
- Native unit tests cover real synthetic AVFoundation extraction, source preservation, bounds, silence refusal and text/window policies.
- Native UI checks cover reopening without a laptop and disabled generation without selected media.
- The actual OS recognition permission/installed language assets, F5 inference, thermal/memory behavior, complete import and airplane-mode new-text synthesis must still be tested on iPhone.
- CI must compile the exact candidate. No native compile, phone test, character likeness or complete end-to-end success is claimed by this document.

The laptop option and previous voices remain intact. Public source contains no user media, models, transcripts, pairing data or credentials. Publish 1.0.0 only after the agreed complete acceptance scope is verified; do not overwrite the released 0.4.9 IPA with this development candidate.
