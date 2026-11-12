# Conservative candidate screening and retained evidence

Source-only patch based on release82081bf. No deployed service, active queue, original specification, model, voice catalog or quality threshold is changed by this patch.

## What changes

Automatic preparation retains a bounded, allowlisted analysis projection in specification provenance. It contains the actual acquired source SHA256, video ID, independently measured decoded PCM duration, declared metadata duration, optional analyzer duration, representative intervals and alternate member intervals. Canonical JSON SHA256 binds this projection. No arbitrary analyzer properties, paths, tokens or raw omitted-record content are retained.

Limits remain32 tentative groups and512 alternate intervals. Groups must be unique in representatives. Every interval uses finite nonboolean timestamps, belongs to a known group, spans3–12.001seconds, stays within the independently measured decoded PCM bound and is not a duplicate. Cross-group overlap remains explicitly unassessed. Declared yt-dlp metadata duration is not a measured container duration and may be rounded to whole seconds. It is retained as declaredSourceDurationSeconds and permits up to1second difference from decoded PCM for coarse sanity checking. Decoded PCM is authoritative for interval endpoints (one microsecond tolerance for six-decimal analyzer timestamps); analyzer duration must agree with it within0.05seconds. Larger duration mismatches fail closed.

Existing annotations such as music-note symbols or bracketed music/singing/applause labels now flag a candidate as review-needed. This is a conservative transcript warning, not a music classifier. Missing annotations do not prove clean speech. The existing minimum3word/maximum3000character requirements remain, with word and character counts retained. Accepted candidates remain eligible-unreviewed, with cleanSpeechVerified=false and identityVerified=false. No acoustic thresholds or generated-word gates are weakened.

Every candidate group receives an outcome. Mixed specifications retain rejected outcomes, counts and all validated alternate intervals; a rejected group does not silently disappear from the private evidence. This patch does not add UI for these outcomes, so a caller must surface partial/review-needed coverage instead of reporting the requested voice collection complete.

## All-rejected boundary

When no candidate is eligible, preparation writes only a private review record at candidate-reviews/<videoID>/<revisionSHA256>.json. The filename hashes the canonical record bytes. The record is explicitly non-runnable and review-needed, binds the source and request IDs, and retains evidence/outcomes. It contains no full rejected transcript and is not an accepted video specification. Existing queue review behavior remains; no automatic retry or publication is added.

Review publication is cancellation-checked and routed through the caller's ownership-fenced commit operation. Atomic no-replace linking protects existing records, including competing writers; an existing identical record is idempotent, while conflicts and linked destinations are rejected. Accepted specification publication also uses atomic no-replace linking and rechecks cancellation at commit. Original voice data is untouched.

## Deliberate limits

Retained intervals are tentative alternatives only. This patch performs no alternate extraction, source separation, automatic label assignment or clean-speech certification. It does not determine whether a source contains the requested characters. A later reviewed recovery step can use the original source hash and intervals without guessing provenance.

Older analyzer responses without memberIntervals remain readable but evidence records alternateIntervalsAvailable=false. Older accepted specifications are not rewritten. No live migration occurs.
