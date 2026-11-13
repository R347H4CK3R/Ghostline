# Isolated RVC synthesizer-session experiment

This is NOT an offline RVC voice converter, nor app integration. It implements the
existing desktop export's 40kHz,768-dimensional synthesizer boundary
only. Caller supplies content features, pitch, retrieval result and explicit noise.
No content encoder, pitch extraction, retrieval, audio DSP, training or character
weights are included. Synthetic fixtures contain algebra, not a trained voice.

Design: C++17 core using actual ONNX Runtime C API1.24.2, exported C bridge for Swift.
CPU only, one run per session. Fixed tensor names/types/shapes validated both against
model metadata and caller tensors. Preallocated output. Model bytes bounded128MiB;
no filesystem/network methods. Caller must admit only trusted, hash-verified,
self-contained models. This is not a sandbox for arbitrary ONNX: model-size and I/O
bounds do NOT bound internal graph allocations. Thread count1, sequential execution,
no CPU arena or memory pattern. Cooperative cancellation/deadline, not hard realtime.

Plan: generate original tiny ONNX fixtures; write native failure tests; implement
session metadata/input/output checks and actual ORT Run; run Linux C++ harness against
official1.24.2 binary; add isolated Apple SPM configuration and executable native
smoke tests. Keep main project.yml and existing F5 runtime unchanged.

## Reproducible native check

`swift run RVCContractDiagnostic fixtures` runs the actual C++ boundary against
original algebra-only ONNX fixtures on macOS. The Swift package pins Microsoft's
1.24.2 Apple binary and SHA-256 from its official package. The CI workflow also
builds the library for the iPhone ARM64 SDK. These are **not** real RVC voice-model
or physical-iPhone inference tests. The app target is intentionally unchanged.

The official Linux1.24.2 runtime passed this contract locally on2026-11-13,
including invalid model/tensor rejection, one-shot cancellation and preserving
caller output when generated values are invalid. Apple compile/runtime results
must be read from the exact-source workflow rather than assumed from Linux.

The fixed-frame contract is a component boundary only. `rvc_synth_create` preserves
100-frame compatibility; `rvc_synth_create_for_frames` accepts an explicit 1..1000
frame contract and requires every model/input/output axis to match it. Symbolic
axes are still rejected. Output is exactly frames*400 samples; the limit bounds
I/O, not graph internals. A real one-second RVC conversion with reflected context
needs approximately298frames. A 300-frame algebra-only fixture now executes through
the real runtime, but no real trained300-frame graph or complete end-to-end path
has been verified. Existing100-frame graphs cannot be relabeled as300-frame models. Native HuBERT, pitch, retrieval,
DSP, trusted model admission, complete trained-graph parity and iPhone resource
validation remain absent. The pinned ORT Swift distribution excludes training
bindings; this package does not provide RVC training.
