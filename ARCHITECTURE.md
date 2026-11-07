# VoiceMatrix architecture and current limits

SwiftUI → SpeechStudio → NeuralSpeech actor → one pinned FluidAudio PocketTtsSmallManager (Phonon 31m) → streaming 24 kHz samples → PCM WAV → private AudioStore.

The model is loaded only from the bundled Phonon directory using `load(from:)`. The download-enabled FluidAudio initializer is never called. A profile switch releases the old manager to bound upstream's voice KV cache. This trades reload time for predictable profile memory; it needs iPhone measurements before final optimization.

A pinned build-only downloader checks 55 files (143,897,933 bytes), including 37 English voice payloads. The 37 profiles contain distinct numeric tensor payloads after metadata is excluded. This is asset validation, not a listening assessment. The IPA gate verifies model hashes, app identity/version, arm64 Mach-O and icon assets.

Speech is streamed into a WAV file rather than retained as an entire sample array. Empty, nonfinite, effectively silent and undecodable results are rejected. Cancellation cancels the upstream streaming session and removes partial output. Reports contain profile IDs, timing and numeric error codes; app text/audio is not exported in reports. FluidAudio text-bearing info logs are disabled.

Recording and importing preserve original audio; import normalizes to WAV for private saving. Conversion to a target neural voice remains unimplemented. No DSP preset is counted as a neural voice.

## Engine decision

Phonon is the first integration, not a benchmark winner. Its publisher catalog supplies compact English and original character profiles; FluidAudio supplies a native local-loader path. PocketTTS, Kokoro, OpenVoice V2 and OpenF5 are researched alternatives. A second engine is not bundled without measured gains. Core ML device performance, subjective quality, Airplane Mode, microphone permissions and LiveContainer/Strata operation are pending physical iPhone testing.

## Expansion research

- https://huggingface.co/gradium/phonon-voices — publisher catalog; currently 37 English profiles. Converted tensors are not interchangeable with arbitrary RVC checkpoints.
- https://github.com/FluidInference/FluidAudio — pinned native Core ML host. Local pack loading is used instead of network initialization.
- https://github.com/kyutai-labs/pocket-tts — short reference conditioning. Donation recordings need engine-specific conversion and compatibility validation.
- https://huggingface.co/kyutai/tts-voices — collections have separate provenance/licenses; do not treat every subfolder as CC0.
- https://huggingface.co/hexgrad/Kokoro-82M — alternative shared engine with published embeddings; requires separate frontend/runtime benchmarks.
- https://github.com/myshell-ai/OpenVoice — tone-color conversion candidate; no tested native iOS integration in this branch.
- https://huggingface.co/mrfakename/OpenF5-TTS-Base — conditioning TTS candidate; no verified iPhone memory/latency result here.

500+ voices and controlled likeness listening tests remain future milestones, not release claims. Recognizable likeness count is zero. No automatic model scraping or recording upload is performed.
