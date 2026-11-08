# Prepared Queue Processor

Goal: connect queue ownership to actual reference-pack preparation, local synthesis, independent WAV/word checks and native-format publication, with review retained.

Architecture: one serial worker uses existing pack/F5/publisher APIs; a second SQLite connection renews its lease. Explicit private specifications supply reviewed labels/references; no pretend automated acquisition or licensing. Resource paths are local and pinned.

- [x] Write missing-processor regression tests; observe failures.
- [x] Implement actual queue-to-pack-to-speech-to-wordcheck-to-folder flow.
- [x] Preserve missing inputs, failed attempts and terminal reasons; never mark previews completed or clear links.
- [x] Independent review found publication fencing and stranded pauses. Add failing regressions, then transactional owned publication and same-attempt pause/resume.
- [x] Add stop/pause checks between neural steps through F5 transformer hooks and terminate cancelled recognition child processes.
- [x] Full local source suite:95tests passed.
- [x] Execute one actual neutral CPU F5/whisper pipeline; first attempt failed at0.125WER, second passed0WER and published a real reference folder. This is not a character or device test.
- [x] Real Torch transformer-hook cancellation interrupted generation; work resumed attempt1 and passed on quality attempt2.
- [x] Broader hosted suite exposed a pre-existing Windows killpg failure; preserve its failing timeout regression and repair process-tree cleanup, with FFmpeg installed for media tests.
- [ ] Verify repaired hosted suite and integrate.

Review focus: stale workers mutating the master folder; pause consuming retry budget or losing work; stop during expensive stages; unsafe reference paths; recognition results bound to exact generated WAV; no false likeness/device/completion claims. Automatic source acquisition, metadata review, missing-spec requeue, completion ledger, network sync and UI feedback integration remain unfinished.
