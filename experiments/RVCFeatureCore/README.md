# Bounded native RVC feature preparation

This isolated C ABI performs real content feature nearest-neighbor interpolation
from 50 to 100 Hz, unvoiced protect blending of caller-supplied retrieved versus
original features, and 50–1100 Hz mel pitch quantization into RVC bins 1–255.
It uses original implementation of the RVC v2 frontend mathematical operations.
It does **not** estimate pitch, run HuBERT, search a retrieval index, train,
synthesize a voice, or identify a character. No models or private inputs included.

Caller passes contiguous valid-sized buffers as described in `features.h`.
Source frames are bounded at 500, doubled output frames at 1000, channels at 768.
Original features and retrieved features must have identical source shape. Padding
or alignment to other frame counts is deliberately unsupported until verified
against the real frontend. Silent pitch is zero. Protect applies below 1 Hz,
matching the upstream two-mask operation; protect >=0.5 disables this blending.
Pitch bins clamp to 1–255 with explicit nearest-even rounding.

All values, sizes, and output overlap are checked before commit. Intermediate
vectors are bounded, input/output aliasing is safe because inputs are consumed
before commit, and rejection preserves both output arrays. Arbitrary invalid
pointers cannot be made safe by a C API; the Swift caller must own the buffers.

Run `python experiments/RVCFeatureCore/test_features.py`. This compiles the actual
C++ implementation and invokes it through ctypes, checking numerical behavior and
transactional rejection. This component is not yet linked into the app. Native
Apple/iPhone compilation and trained-input parity are separate verification gates.

Numerical and invalid-input tests passed on Linux. The native harness also checks
in-place input/output and rejects overlapping outputs. Local ASan/UBSan passed
with leak detection disabled because this executor runs under ptrace; CI retains
default leak detection. These results do not establish trained-graph parity.
