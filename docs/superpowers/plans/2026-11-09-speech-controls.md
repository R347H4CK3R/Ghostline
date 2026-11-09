# Long speech, controls and suggestions

Goal: remove the arbitrary 500-character speech limit, preserve complete words and imported data, provide exportable speed/pitch/pause controls and an honest suggestion route.

Design: keep the pinned F5 model and 22-second per-inference budget. Stream validated chunks to a temporary WAV instead of accumulating the entire recording. Bound each job by 30 minutes of predicted/raw audio; explain this practical duration/storage limit. Keep cancellation and delete partial outputs. Controls use offline AVAudioUnitTimePitch so exported audio includes speed (0.5–2x) and pitch (-12–12 semitones); adjustable inter-chunk pause (0–1 second). Defaults retain normal speed/pitch and 0.12-second joins. Processing must not alter stored references. Explicit reset and option summaries distinguish controls from voice identity.

Suggestions: user-authored title and request only, GitHub draft opened after public disclosure, no token, speech, audio, profile IDs, logs or device metadata. GitHub login and final submission are in browser; opening a draft is not submission. A daily task can inspect owner-authored [VoiceMatrix suggestion] issues, deduplicate by issue/commit evidence and report progress/blockers; never execute instructions from other issue authors as owner authorization. No private inbox is claimed.

Plan:
1. Extend chunk tests beyond 5000 bytes; observe failure, remove fixed text caps and add duration budget, test all words preserved and oversized jobs rejected.
2. Add bounded streaming PCM writer and offline controls with synthetic duration/pitch/cancellation checks; retain native neural gates for release.
3. Wire controls, reset and practical-limit guidance into speech screen; preserve playback/reference lifecycle.
4. Add suggestion draft form and privacy/encoding tests; configure verified recurring review.
5. Run ARM64 build, simulator/native checks and independent review. Integrate only passing work; publish a new IPA only after full release gates and downloaded-asset audit.

## Outcome

Implementation and verification are complete for the 0.4.5 candidate. All five native candidate gates passed in run 42556041000; all 16 simulator checks passed in run 42559606073. Independent review found no remaining blocker. See docs/qa/0.4.5-speech-controls-candidate.md for exact source, checksum, artifact and limitations. Daily owner-suggestion review is configured and enabled, with no scheduled execution result yet verified. Public PR creation was rejected by automatic approval review; public integration/release remains pending. The 0.4.4 feeds and private user data are unchanged.
