# Reviewed video preparation

The companion worker now discovers a private reviewed recipe when a queued video has no prepared specification. It acquires that video, checks that both audio and video decode, extracts bounded mono 24 kHz PCM16 references, optionally transcribes them locally, saves immutable reference revisions, and atomically publishes the specification consumed by the existing speech/profile processor.

This automates acquisition and segment preparation after reviewed labels, times and reference-use records exist. It does **not** automatically identify every character or establish recording/likeness permission. Uncertain labels and missing source-use reviews remain `awaiting-preparation`; no download or neural allocation occurs. The worker checks again on subsequent polls and resumes the same attempt when the missing recipe/specification arrives, preserving its quality retry budget. Final generated profiles remain `needs-review` for likeness/native/device checks, and links/names are not removed.

Use `--recipes /private/recipes`, or the default recipes folder beside specifications. A recipe is `<videoID>.json`:

```json
{
  "schemaVersion": 1,
  "videoURL": "https://youtu.be/EAT0nWoEzJ8",
  "referenceUseReview": {
    "decision": "approved-local-processing",
    "reviewer": "Reviewer identity",
    "record": "Source permission/provenance record"
  },
  "segments": [{
    "id": "original-speaker",
    "name": "Original Speaker",
    "start": 1.0,
    "end": 8.0,
    "labelStatus": "original-speaker-reviewed",
    "categories": ["Original", "Animation"],
    "source": "Recording provenance",
    "permission": "Reference recording and voice-use terms",
    "referenceText": "Optional checked reference words."
  }]
}
```

Label status may also be `on-screen-label-reviewed` or `speaker-label-reviewed`. A reviewed label is an assertion from the recipe's author, not biometric recognition or an official identity claim. A source-use record does not establish public redistribution or recognizable-likeness authorization. Those remain separate; the preparation report explicitly leaves likeness authorization and verification false.

If reference words are omitted, the worker's pinned local whisper recognizer transcribes the extracted audio. Such text is marked `automatic-needs-review` in the specification, reusable pack and processing report. Provided words are marked provided, without inventing a human-verification score. Reference transcripts and audio remain private.

Limits are 64 segments, each 0.5–15 seconds, 30 minutes per source by default (configurable up to 60), 256 MiB downloaded bytes by default (up to 1 GiB), and a 300-second overall download deadline (up to 900). Source format is bounded MP4 up to 480p. The real downloader runs in a separately bounded process; cancellation/timeout stops its process tree. FFmpeg extraction/decoding is also bounded and cancellable. Socket timeouts do not stand in for the overall deadline. The injectable in-process downloader factory exists only for tests.

Temporary source movies and extracted temporary clips are removed on success, error or cancellation. Validated conditioning references are retained because the reusable voice needs them. Existing prepared specifications remain intact when a replacement fails. Source-video, reference and recipe hashes are recorded. A changed recipe during acquisition prevents stale specification replacement.

Queue ownership loss propagates into download, extraction, transcription and synthesis cancellation. Specification-pointer publication is fenced by the current queue token. Transient preparation/publisher lock contention pauses and resumes without spending a quality retry; actual acquisition/generation failures use the initial attempt plus three retries and retain a reason. Preparation waiting and final likeness review are separate states.

Install the development-only downloader dependency with `python -m pip install -r tools/requirements-acquisition.txt`; FFmpeg and the explicit local F5/whisper resources are also required. The requirement pins [yt-dlp 2026.10.26](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.10.26). No cookies, authentication bypass, cloud speech API or first-launch iPhone download is introduced. This companion stage is not bundled in the IPA.

Tests use actual FFmpeg video/audio fixtures and the actual downloader child/control path, substituting external network acquisition. The queue-to-pack-to-native-folder tests additionally substitute expensive ASR/neural inference. This is not a new real-neural, live-YouTube, physical-iPhone or character-likeness result. The previously recorded real neutral F5/whisper diagnostic remains separately scoped. The original cloud model cache is no longer available in this environment; no old voice worker was restarted or character archive restored.

No laptop processor/runtime deployment, private 60-character folder modification or new IPA is performed by this source change. Automatic speaker/label proposal, review UI/feedback, completion ledger and private folder synchronization remain unfinished. Deploy all coupled modules together before using this extended worker; the installed laptop endpoint still has the older queue implementation.
