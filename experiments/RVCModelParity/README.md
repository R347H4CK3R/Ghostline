# Actual public model export and native parity gate

This isolated gate exports **real pretrained weights**, not toy algebra, then
executes the exact graphs on Linux and Apple Silicon through ONNX Runtime1.24.2.
It is not linked into VoiceMatrix and does not declare RVC conversion complete.

Sources:
- Official facebook/hubert-base-ls960 revision
  `dba3bb02fda4248b6e082697eee756de8fe8aa8a`, explicitly Apache-2.0 model card.
- torchcrepe0.0.24 pretrained tiny weights, SHA256 matching the MIT upstream
  `19e2ec3d494c0797a5ff2a11408ec5838fba6681` checked-in weights.

Input checkpoints and license texts are hash-pinned. Exports, original neutral
input tensors and Torch expected outputs are uploaded only as CI artifacts with
7-day retention. No weights are committed. Manifest source SHA and every artifact
hash are verified before native execution. No private speech or character models.

The exporter uses CPU Torch2.6, Transformers4.49, ONNX1.17 and ORT1.24.2. Inputs
are silence,220Hz sine and seeded noise. Fixed48k samples ->149×768 content; fixed
16×1024 pitch frames ->16×360 salience. Actual parity uses atol1e-4 + rtol1e-3.
Shape tracing warnings do not imply support for other sizes. No generic dynamic
shape support is advertised. Main RVC synthesis model's128MiB limit is unchanged.

This is only a diagnostic executable, not a production untrusted-model loader.
Artifacts are produced by this exact workflow from verified public sources.

## Limits before integration

- Official HuBERT weights/config/normalization may differ from previously used
  fp16/custom RVC wrapper. Trained RVC compatibility is explicitly **unverified**.
  Never substitute it into an existing trained model without intermediate parity.
- Pitch salience is not decoded pitch. Framing/normalization, decoder/unvoiced
  handling, retrieval, reflection/resampling/cropping and trained synth parity
  remain required.149content frames need298synth frames, not300.
- No actual iPhone run, latency/thermal/memory, native RVC training or likeness
  claims. Linux/Apple model execution is distinct from those acceptance gates.
- Existing lj1995 model bundle's root license contains research-only wording;
  its MIT model-card tag alone is not used to authorize redistribution here.

Local run: install the versions in the workflow, then
`python export_models.py <new-artifact-directory> <source-commit-sha>`.
Verify with `python artifacts.py <directory> <same-sha>` and run
`swift run RVCModelParity <directory>` on macOS.

## Native pitch candidate (not old PM frontend parity)

The native C ABI now frames mono16k audio into1024sample windows/160hop,
512zero-padding, mean removal and sample-standard-deviation normalization.
Count is bounded at48k samples and16frames per batch; all outputs are staged,
nonfinite/clipped input and overlapping outputs rejected. Mean-removed AC RMS
also rejects silence/DC rather than trusting pitch-model hallucinations.

A deterministic9-bin salience-weighted decoder implements explicit50–1100Hz,
confidence0.1/AC-RMS0.001 synthetic-control settings. These are engineering
settings, not verified human-voice accuracy thresholds. It does not implement
Torchcrepe's default Viterbi/dither or the old RVC PM extractor; do not describe it
as bit-exact replacement. Different tasks may require tuned thresholds.

The native actual-model diagnostic runs silence and110/220/440Hz controls through
native framing -> real CREPE ONNX -> native decoded pitch, requiring0 for silence
and all16estimates within3% for each tone. Synthetic tones establish a functioning
pitch path, not reliable pitch in real speech/music or character likeness. iPhone
ARM64 core compilation is separate from physical-device model execution.
