# Exact production local-pipeline diagnostic

This is a native macOS verification target, **not a claim that it has passed**, and not an iPhone installation or likeness test.

`LocalStudioDiagnostic` compiles the same `LocalVideoStudio`, speaker diarization, sound screening, bundled ASR, F5 engine, processing lease, `CharacterLibrary` and atomic folder store used by the app. Production defaults continue using the same iPhone storage and bundle locations. Explicit roots let the diagnostic use a fresh isolated directory; they do not replace processing implementations. The library model was separated from its SwiftUI view, and only AVAudioSession route/configuration code is iOS-specific. macOS is explicitly not counted as a physical iPhone in `DeviceVoiceChecks`.

CI generates neutral continuous English speech using an already installed macOS voice (`say`). It records the exact text, voice, OS version and resulting WAV hash. This is synthetic diagnostic material, not a character recording. It does not download voice assets or claim likeness. Its duration must be 8–60 seconds; the production speaker-span, screening and word-error thresholds remain unchanged. Different installed OS voices can produce different results, which must be reported rather than bypassed.

With networking denied, the executable:

1. Imports a pre-existing pinned neutral profile through the real atomic store.
2. Starts the actual coordinator and cancels after its source copy is committed.
3. Verifies the source is retained and the library/processing ownership is released.
4. Resumes the actual speaker, sound, ASR, F5 and generated-word verification pipeline.
5. Requires completed import, retained stage evidence and a decodable preview.
6. Creates a fresh library instance and checks imported IDs and the pre-existing profile survived.
7. Confirms Resume on a completed job does not create duplicate voices.
8. Selects an imported voice and uses the real catalog's `speak` method for new text.
9. Releases warm F5 through its real ownership fence, verifies new speech with bundled ASR at ≤10% word error, and retains its WAV and evidence.

The workflow always uploads the synthetic evidence directory. Failure retains the job/status and generated attempts; success emits `pipeline-evidence.json` bound to the source commit and input hashes. It does not prove general YouTube acquisition, music separation, character identification, RVC training, perceptual similarity, arbitrary content performance, physical iPhone memory/thermal behavior, external speakers, or final 1.0.0 acceptance.

Required before release: this native target actually passes on the exact candidate, the iPhone build and UI gates pass, and remaining product/device requirements are checked independently. Presence of the workflow, Linux source-contract tests, or a successful build is not an end-to-end success.
