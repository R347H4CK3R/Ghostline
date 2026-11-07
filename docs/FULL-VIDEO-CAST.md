# Full supplied-video character pass

The entire 14:59 video EAT0nWoEzJ8 was visually surveyed in six contact sheets. Character-card classification then sampled every second, using the artwork half of the frame rather than actor portraits. Four missed brief cards were inspected individually: Pensylvester, Child Morty Jr., Beta VII and Pat Gueterman. The resulting map contains **60 named roles**. Rick and Morty already have user-accepted reference-conditioned previews; **58 other references are candidates**, not verified voices.

The public candidate map is models/research/full-video-cast.json. Original video/reference bytes are not committed. The downloaded MP4 decoded successfully on the connected laptop. Reference slices transferred with archive and per-file SHA-256 verification. The source video, contact sheets, source slices and transfer files were then deleted from that laptop (79 files, 67,597,684 bytes). Development processing is on the separate CPU workspace, not the gaming laptop.

The worker transcribes references, uses the same F5-TTS v1/32-step method as the accepted previews, synthesizes a neutral new sentence, checks finite/non-silent decoded WAVs and full-scale samples, and independently transcribes outputs. Failed word checks may retry one fixed alternative seed. It preserves failures and cannot replace a voice with a stock speaker. Very brief, nonverbal or mixed material may not support a usable result.

A live job is not a completed library. Perceptual resemblance, controlled listening, authorized recognizable likenesses, native iPhone inference, importable RVC models and app admission remain unverified/unimplemented for these candidates. Repeated seeds do not increase the voice count. No IPA build or feed update is part of this development pass.

## Resumable worker

Prepare a private job directory with references/manifest.json and the validated reference slices. Set VOICEMATRIX_CAST_JOB, VOICEMATRIX_WHISPER_CLI, VOICEMATRIX_WHISPER_MODEL and optionally VOICEMATRIX_F5_CACHE, then run tools/full_cast_video_worker.py using the isolated F5 environment. The model cache must be available locally for offline inference; missing development weights can download from the upstream model source. This is not an offline-ready iOS implementation.

job-state.json and results.json contain progress and measurements. The worker deletes each used reference and its synthesis-library cache copy. The final ZIP includes only generated WAV previews and the result report. Any private temporary recovery checkpoint containing reference material must also be removed after completion. Original source dialogue is not part of the public report. Requirements for this tested CPU setup: f5-tts1.1.22, Torch2.15.0+cpu, TorchAudio2.11.1+cpu, TorchCodec0.17.0+cpu, httpx[socks], NumPy, SoundFile, FFmpeg and independent whisper.cpp tiny.en. The F5 weights use CC BY-NC4.0 and do not establish rights to a character likeness or recording.
