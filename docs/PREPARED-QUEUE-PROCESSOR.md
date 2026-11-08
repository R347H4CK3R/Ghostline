# Prepared-reference queue processor

`python -m tools.queue_processor --help` exposes an actual serial worker that claims the existing SQLite queue, prepares validated reusable F5 packs, generates a new diagnostic sentence, independently recognizes its words, checks the real WAV, and publishes the profiles into the native-format master folder. Changed existing profiles remain quarantined by the publisher. The worker retains jobs as `needs-review`, not `completed`, because individual native/device checks and likeness review are separate. It never removes pending links or names.

This worker consumes prepared local references or a reviewed private video recipe. When a recipe exists, it now acquires and extracts the selected references automatically; see [Reviewed video preparation](VIDEO-PREPARATION.md). It does not identify all speakers, establish character identities or grant recording/likeness permission. This is not a claim that the installed laptop monitor creates voices from arbitrary links.

Put `<videoID>.json` inside the configured specifications folder. Its format is:

```json
{
  "schemaVersion": 1,
  "videoURL": "https://youtu.be/EAT0nWoEzJ8",
  "profiles": [{
    "referenceFile": "prepared/reference.wav",
    "referenceSHA256": "SHA-256 of the exact reference bytes",
    "metadata": {
      "id": "original-voice",
      "name": "Original Voice",
      "categories": ["Animation", "Fantasy"],
      "source": "Recording provenance",
      "permission": "Applicable recording and voice-use permission record",
      "referenceText": "Exact checked words spoken in the reference."
    }
  }]
}
```

Reference paths stay within that folder. The worker validates all source hashes and pack metadata before loading a shared model. There are at most 64 profiles per prepared job. Source recordings and transcripts stay private; the public repository contains only synthetic tests. Missing specifications/recipes remain awaiting-preparation and are checked again on subsequent polls without spending quality retries. Final generated audio still remains needs-review.

Required local resources are explicit arguments: `--checkpoint`, `--vocoder-directory`, `--vocab`, `--whisper-cli`, `--whisper-model`. The F5 loader pins its checkpoint and uses local files; the independent recognizer pins tiny.en. No API credentials, model downloads or default voice substitution are used. Reviewed source videos may be downloaded during companion preparation; this does not add an iPhone inference network requirement. The shared F5 model is reused between jobs in one worker process. Inference uses 32 steps with attempt seeds 347–350. Initial failure plus three retries is the limit; actual word error rates and every completed failed attempt are retained. Export format validation does not establish likeness or authorization.

The remaining arguments are `--database`, `--specifications`, `--work` and `--master`; use `--once` for one claim. Otherwise the loop polls every 30 seconds (configurable 5–3600). The work folder's `pause` and `stop` files prevent new work and are checked during synthesis/recognition. On Windows, the existing game detector is checked at most once per second. F5's transformer pre-forward hook interrupts between neural steps; a currently executing kernel must finish first. Recognition child processes are terminated on cancellation. Paused work releases ownership and resumes the same attempt when unpaused, preserving the quality retry budget. Heavy laptop deployment is not enabled by this source change.

An ownership transaction fences the entire final publisher operation; another queue connection cannot reclaim or revoke its token midway through publication. A process crash can still leave valid unindexed files or a published collection pending its review record; idempotent publication makes retry safe. There is no cross-filesystem/database atomicity or universal sudden-power-loss guarantee. No job-completion/ledger-cleanup API is provided yet.

Tests exercise real SQLite, packs, folders, subprocess cancellation and publication locks. Unit tests substitute only expensive synthesis/recognition dependencies. Separate real CPU F5 and pinned whisper checks use a neutral synthetic reference and are reported independently; they do not verify character likeness, iPhone execution or the full automatic video pipeline.

Model weights are released after a paused/empty poll and at shutdown; the process may retain runtime libraries, and physical Windows memory measurements are still required before unattended heavy deployment. Worker-loop failures are saved to private worker-state.json and retried on the next poll; one-shot worker failures exit nonzero. Independent Windows full-suite testing exposed and repaired an older Unix-only timeout cleanup in run_native_tests.py without skipping the stalled-process test. FFmpeg is explicitly installed for both hosted platforms so media checks are exercised.

