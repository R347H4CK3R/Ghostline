# Bundled ASR development candidate, not 1.0.0 acceptance

## Choice and scope

The standalone studio's OS Speech recognizer is replaced behind the existing `authorize()` / `transcribe(_:activity:)` interface. `authorize` checks the bundled manifest; it does not request Speech permission, fetch OS language assets or load weights. There is no OS/server fallback. Existing source copying, speaker grouping, SoundAnalysis screening, F5 generation, final word-error check, atomic import and retained data remain unchanged.

The chosen FluidAudio dependency remains `ee78635d23d52379117554ba72358b65a0612447`. Its **actual source**, not the older manual-loading example, supplies `AsrModels.loadLocal`, which does not resolve/download/purge. `load(from:)` is deliberately not used. Local loading can discover optional CTC files, so the app rejects unlisted bundle files before invoking it.

The selected model is `FluidInference/parakeet-tdt-0.6b-v3-coreml`, revision `7dd20fe6b1797d35f5e3307e8b1732d9a178edfe`, with **Encoder_v2 / `.int8V2`**, Preprocessor, Decoder, JointDecisionv3 and vocabulary: **20 files, 632,169,729 bytes**. The smaller original 483 MB set was considered and rejected: pinned SDK `ModelNames.swift` documents right-context token corruption in its original 6-bit encoder (issue #760), addressed by Encoder_v2. Redux is a separate model and is not used. This selection is not an accuracy or physical-device claim.

## Provenance and notices

`tools/asr-resource-lock.json` pins each SHA256/size. Large-object identities originate in the pinned Hugging Face Git LFS tree. Non-LFS text hashes were calculated from downloaded text after checking the pinned Git blob identity. Build staging verifies the actual bytes. The runtime pins the entire lock hash and streams every asset hash before loading. Model binaries are ignored, never committed or uploaded as source artifacts.

NVIDIA's [pinned model README](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3/blob/541d1f99c6b0c3cd0b11a95167540bb8edefd82b/README.md) explicitly says: “GOVERNING TERMS: Use of this model is governed by the CC-BY-4.0 license.” Its use-case restrictions likewise point to CC-BY-4.0. No separate restrictive license/terms file was found in the selected conversion repository tree. Its [pinned README](https://huggingface.co/FluidInference/parakeet-tdt-0.6b-v3-coreml/blob/7dd20fe6b1797d35f5e3307e8b1732d9a178edfe/README.md) has CC-BY metadata but ends: “Apache 2.0. See the FluidAudio repository for details and usage guidance.” That paragraph does not explicitly distinguish code from weights. Both notices are preserved, together with full CC-BY and the actual SDK Apache license, in the app's `ParakeetNotices` folder. The SDK license is not substituted for NVIDIA attribution. No certification of redistribution clearance is claimed.

[Published conversion scripts](https://github.com/FluidInference/mobius/tree/588b8e7077d454e9613bdb2672b89824c2f7095d/models/stt/parakeet-tdt-v3-0.6b/coreml) identify the NVIDIA model, but the downloaded artifact metadata does not bind its historical conversion to an exact original checkpoint or conversion commit. `historicalConversionVerified` remains false. This is a reproducibility limitation distinct from the permissive-license notices. CC-BY obligations include attribution, notices, identifying modifications, license access, and no additional restrictions on recipients' licensed rights; publication must preserve these. No trademark, privacy or publicity rights are granted.

## Evidence and resource boundaries

- Input is a local regular non-symlink mono WAV, 0.2–30 seconds, 16–48 kHz, at most 8 MiB. App reference extraction already supplies 24 kHz mono. The SDK performs its required 16 kHz ASR resampling; original retained files are not changed.
- Only one wrapper transcription is admitted at a time. The SDK chunk concurrency is explicitly one, CPU+ANE is requested and the preprocessor uses CPU as specified by `loadLocal`.
- Each invocation creates its own manager. Success, failure and cancellation await `cleanup()` before returning, then release the manager and all model references. F5 cannot start through the sequential caller until this returns. The SDK schedules small shared-array cache cleanup internally; there is no API to await that cache clear. CoreML/OS allocator caches and peak resident memory require measurement, not promises.
- A 45-second deadline requests cooperative cancellation. CoreML prediction/model load cannot be forcibly preempted. The wrapper waits for the safe boundary and cleanup, rather than returning early and overlapping a new model job. Cancellation from backgrounding retains existing source/output files via the unchanged caller.
- `AsrResult.confidence` is not used for admission: pinned SDK fabricates a fallback 0.5 if token scores are missing. Actual nonempty token-timing scores must be finite in [0,1], at most 4096, and their mean must be at least 0.35. This retains a numerical floor but is **not equivalent calibration** to Apple's former segment confidence. There is no constant replacement score or claim of transcript correctness probability.
- `lastEvidence` is returned only after a second bounded file hash/byte-count check rejects input changes while FluidAudio reopens the URL. It records actual token count/mean, model revision, input SHA256 and transcript SHA256. Missing evidence fails closed. The existing final expected-text WER must still be at most 0.1 and SoundAnalysis screening is not weakened. Integrators should save `lastEvidence` next to the retained reference/preview transcript; no worker edits to `LocalVideoStudio.swift` were made.
- The existing activity closure fires only once a genuine final transcript exists. Hashing/loading time is not fabricated inference progress.

## Build and actual recognition gate

```sh
python3 tools/bundle_asr.py
# Then build with project.yml; ParakeetASR and ParakeetNotices are folder resources.
python3 tools/bundle_asr.py --inspect-ipa path/to/VoiceMatrix.ipa
```

Staging uses 1 MiB chunks, exclusive atomic publication and rejects/preserves mismatched existing files. It does not run downloaded code, extract archives, delete existing caches or download user media. The full app packaging workflow must call this staging and IPA inspection in addition to its existing engines; a source-only `.gitkeep` folder is not an ASR-equipped IPA.

`.github/workflows/bundled-asr-diagnostic.yml` is a manual or source-path-triggered native gate and a required reusable job of the candidate aggregate. The aggregate cannot succeed if actual bundled recognition fails. It builds the exact production wrapper as `BundledASRDiagnostic` on Apple Silicon and executes with networking denied. Only the two already-pinned neutral synthetic fixtures are allowed, with embedded exact hashes and known expected words. It requires ≤0.1 WER for each, rejects a canceled request, then proves a subsequent actual recognition can finish. It emits source/model/input/token-evidence identities. It does **not** verify full local pipeline completion or physical-device behavior. Unit/native policy checks additionally cover missing assets, remote/oversized inputs and missing/nonfinite/low token evidence. A skipped test is not native success.

## Remaining acceptance gates

No native compilation or real ASR inference has run in the Linux worker. The available environment catalog contains no Apple executor. Run the diagnostic and app XCTest suite in native CI, then verify complete retained-source → speaker analysis → screening → ASR → F5 → ASR word check → atomic import, cancellation/retry/backgrounding, airplane-mode use, language/fixture generalization, iPhone memory/thermal performance and installation/upgrade without data loss. These gates and broader user acceptance are required before calling this 1.0.0. Do not infer a completed pipeline from source checks or two short fixture transcriptions.
