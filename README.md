# VoiceMatrix

A **new** iPhone text-to-speech and voice-effects app in the preserved repository R347H4CK3R/Ghostline. The former Ghostline project was removed from the active main branch.

## Start here (no smartphone experience needed)

**Speak:** Open VoiceMatrix. Tap **Speak**. Choose one of the English voices installed on your iPhone, enter words and tap **SPEAK MY WORDS**. You can slow down or raise/lower its pitch. Speech uses Apple's offline speech synthesis. The available voices depend on which English voices iOS already has installed.

**Change:** Tap **Change**. Tap **RECORD MY VOICE**, say a short sentence, then tap **STOP RECORDING**. Select an original effect (Deep Monster, Tiny Cartoon, Spooky Ghost, etc.) and tap **LISTEN**. You can share the original recording. **Important:** The effect previews work, but export of the transformed audio is not implemented in the initial experiment.

**Voices:** Shows the actual English speech voices installed locally; creative categories are organizational only, not unauthorized copies of movie characters or celebrity recordings.

## Offline
This initial test uses Apple's built-in local voices and AVFoundation. **It does not download extra model files**, send audio to a server, or require an account. iOS may prompt to install additional system voices through Settings if none are already installed.

## Actual capabilities versus goals

| Feature | Status |
| --- | --- |
| Offline local English TTS via AVSpeechSynthesizer | Implemented in source; physical-device testing pending |
| Offline record and original effect previews | Implemented in source; physical-device testing pending |
| Export original recording | Implemented in source; physical-device testing pending |
| Export transformed recording | Not implemented |
| Full RVC/neural likeness voice changer | Not implemented |
| 500 recognizable actor/character/singer voice clones | Goal only; **0 included/verified** |
| iPhone IPA | GitHub Actions unsigned experimental build |
| Compatible LiveContainer source manifest | Updated only after release artifact verification |

The app **does not** claim to include 500 voices. Counting a voice requires a real embedded model or installed local voice and actual on-device test evidence. Do not confuse a category, name, slider setting or metadata listing with a voice clone.

## Permissive catalog research for future compatible, authorized models

- [Kokoro 82M](https://huggingface.co/hexgrad/Kokoro-82M): Apache-2.0 English and multilingual TTS, 54 voices across eight languages. No arbitrary real-person cloning from names.
- [Kyutai Pocket TTS](https://github.com/kyutai-labs/pocket-tts): efficient CPU TTS; deployment to native iOS needs additional engineering.
- [Kyutai voice donations](https://huggingface.co/kyutai/tts-voices): 228 consented CC0 reference recordings. **Not** 228 ready-to-play iOS model bundles. Other subsets have different licenses.
- [OpenVoice V2](https://github.com/myshell-ai/OpenVoice): MIT-licensed voice-cloning framework and weights, but voice-reference permission and iPhone native inference are separate problems.
- [OpenF5-TTS-Base](https://huggingface.co/mrfakename/OpenF5-TTS-Base): Apache-2.0 alpha weights trained on permissive datasets, not a complete character catalogue.
- [Piper Voices](https://huggingface.co/rhasspy/piper-voices): downloadable ONNX voice models, with **individual** model-card and source-dataset licenses.

These resources are research, **not bundled in v0.1.0**. Real person/performer likeness rights and character-related rights may still require authorization, even for free model weights. Do not import or distribute unauthorized recognizable likeness models. Any new offline model requires its own weights, attribution, reproducible license review, Apple-compatible runtime, and tests on target hardware.

## Development

GitHub Actions builds an unsigned `VoiceMatrix-unsigned.ipa` using XcodeGen. Sideloading requires an authorized user installer; the IPA is not signed by Apple.

## Source / release
The same GitHub repository is retained, with reset default branch `main`. Experimental downloads appear under GitHub Releases and `source.json` after verified packaging. Historical GitHub issue and pull-request records may persist as platform audit records.

## License
Application source: MIT. Model and OS-provided voices have their own usage terms. Generated audio never leaves the app except through explicit Share.
