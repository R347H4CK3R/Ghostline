# Native video coordinator acceptance gate

The production coordinator diagnostic now has independent audio and video matrix
jobs. The video fixture is an original 640×360 label movie at 12 fps, muxed with the
same installed macOS neutral speech used by the audio regression. Acquisition of
external URLs, character identification and likeness are not tested by this fixture.

The video job must pass the actual coordinator's cancellation/resume, source
retention, speaker analysis, F 5 preview, independent ASR, exact-byte embedding
comparison, transactional import, catalog reload and new-speech verification.
It additionally requires nonempty retained frame evidence, matching source hashes,
zero missing sampled frames, and OCR of the synthetic visible label. Optional visual
failure cannot silently satisfy this diagnostic. Existing audio coverage remains.
Both jobs are required by the reusable candidate workflow; their artifacts have
separate names to avoid replacement. Networking is denied during synthesis and
pipeline execution. The fixture generator retains its inputs and intermediate movie.

The preview passage now budgets 25 ordinary words instead of 8. The earlier actual
preview was 2.101 seconds, below the existing 3 second embedding lower bound. Word
count is not a duration guarantee: actual generated audio must still pass the 3–30
second bounds, word recognition and pairing/hash checks. There is no padding,
repetition or generic-voice substitution to make the diagnostic pass.

Local source regression tests do not establish native success. Only the exact-source
macOS CI result establishes this gate; physical iPhone installation, thermals,
memory and real-character likeness require separate evidence. This is not 1.0
completion or native RVC training.
