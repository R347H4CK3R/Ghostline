# Native offline conversion implementation plan

Goal: implement genuine short-clip speech-to-speech with the licensed OpenVoice V2 Core ML models, using the existing 37 original Phonon voices as targets.

Architecture: one Phonon TTS engine plus one optional converter, loaded sequentially. Target speaker profiles are precomputed from the QA reference clips. User source recordings stay private; source embeddings remain in memory. English words and timing are preserved by audio-to-audio processing, never transcription/TTS substitution.

1. Pin and validate the community Core ML artifacts and official MIT notices; compile packages during the macOS build. Record raw and compiled file checksums.
2. Implement independent native linear STFT (22,050 Hz mono, FFT1024/hop256, reflect384, periodic Hann, unnormalized complex FFT, sqrt(re²+im²+1e-6)). Verify DC, Nyquist, interior frequencies and padding against NumPy golden fixtures.
3. Implement Float16 Core ML tensor adapters, finite/shape validation, speaker extraction and true waveform conversion. Respect frame range10...1000; initially cap clips at10 seconds. Release encoder before loading converter.
4. Generate and attach target embeddings for all37 profiles. Test actual conversion between two distinct references; verify non-silence, decoded WAV, timing and speaker-embedding movement. Retain controlled QA clips for independent transcription checks.
5. Connect recording/import → choose target → convert → listen/save/share with cancellation and clear failures. Preserve the working TTS mode and previous release.
6. Publish only after source, numerical frontend, native audio and archive integrity gates pass. Report simulator checks separately from physical-device listening and near-indistinguishable quality.

No demo Swift source is copied: its code license is unclear. The model's MIT license and public tensor contract permit an independently written frontend/adapter.
