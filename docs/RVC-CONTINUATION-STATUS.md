# RVC continuation: verification boundaries

The published 0.4.9 release remains unchanged. This isolated source candidate adds an opt-in laptop conversion service, an iPhone transport/session, and private intermediate-capture tooling. It does not establish a working end-to-end iPhone RVC product.

## What is separate

- Existing F5 reference voices and their offline engines are not RVC checkpoints.
- Laptop RVC conversion is speech-to-speech. It requires a running configured laptop and explicit audio submission; it is not offline or text-to-speech.
- The private RVC registry accepts separately exported, hash-bound models. It never migrates or replaces F5 voices.
- Source tests use explicit synthetic test doubles at the neural boundary. HTTP success in these tests proves protocol behavior, not generated speech or character likeness.

## Offline path

A new private capture tool records the exact intermediate tensors from the pinned desktop reference. A one-second clip includes two seconds of reflected context and approximately 298 synthesizer frames, producing approximately 39,200 samples after trimming. The earlier 100-frame ONNX synthesizer parity does not prove this complete path.

Neural capture, HuBERT export, pitch/retrieval/DSP parity, mobile memory/latency and physical iPhone execution remain required. New capture directories restrict POSIX permissions; Windows inherited ACLs must be checked before storing private capture data. Captures, request.json, paths, audio and logs are private and are not public release evidence.

## Release gates

Fresh full source tests, independent review, exact-source iOS compile/XCTest/UI checks, a real isolated laptop conversion and preservation checks precede any new release claim. A source-only pass or skipped compiler check does not satisfy these gates. Character identity/likeness needs separate listening review and is never inferred from word-error or tensor-parity scores.
