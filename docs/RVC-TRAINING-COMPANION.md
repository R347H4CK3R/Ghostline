# RVC training, conversion checks, and private export

The desktop commands operate on real upstream RVC model/index artifacts. They do
not turn short F5 references into trained models, identify characters, establish
likeness, or add an iPhone RVC runtime. Nothing here publishes to the live voice
collection or changes the installation feed.

## Isolated training

Use authorized, clean, single-speaker recordings. `audit-training` counts unique
non-silent PCM16 audio and rejects malformed/clipped recordings. It does not
separate overlapping voices or detect every duplicate passage. Sixty unique
active seconds is an engineering admission floor, not a quality guarantee.

```
python -m tools.voice_studio audit-training /path/to/recordings
python -m tools.voice_studio train-rvc --root /path/to/RVC --dataset /path/to/recordings --experiment original-voice --permission "Creator authorized training" --epochs 200 --python /path/to/rvc-env/python --stage-timeout 21600
```

The adapter requires clean tracked source at official
[RVC revision 81eed5e](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/tree/81eed5e8f68b6bed1789f682fe78cdd324495afc),
installed CLI dependencies, local 40 kHz pretrained generator/discriminator, and
local HuBERT weights, config, and preprocessor config. Missing assets are errors,
not download requests. Do not install these dependencies over the F5 environment.

Only the audited, unique WAV bytes are copied into a new experiment. The five
stages are preprocessing, PM pitch extraction, HuBERT features, training, and
retrieval-index construction. Logs and atomic progress metadata stay in that
experiment. Existing experiments, weights, and matching exported indices are
preserved, not resumed or overwritten. A successful command reports
`trained-needs-independent-conversion-check`, exact model/index hashes, and
`verified: false`. An exit code or an output filename alone is not model-quality
proof; an actual smoke run must additionally examine training steps and losses.

Each stage has a wall-time limit. A caller-supplied cancellation event terminates
its descendants. POSIX uses a process group; Windows gates launch until a Job
Object with kill-on-close contains the process tree. Native Windows tests cover
cancellation, an exited leader, and an abruptly killed runner owner. On failure,
partial logs/checkpoints remain for diagnosis. Restarting uses a new experiment.

Training is CPU-only but can still use substantial CPU/RAM. The upstream loader
starts additional workers, so `OMP_NUM_THREADS=2` is not a whole-machine CPU cap.
The CLI itself does not watch games or available memory. An unattended caller
must monitor gaming/pause/stop signals and memory/disk budgets and pass
cancellation. Do not train during play.

## Independent conversion and word checks

Use an original, held-out recording with an accurate transcript. It must not be
the training/reference excerpt. The checker snapshots the hashed model/index and
input, runs the pinned CPU HuBERT/RVC conversion with pitch extraction and
retrieval enabled, then independently transcribes the resulting WAV using the
existing pinned local Whisper recognizer.

```
python -m tools.voice_studio verify-rvc --root /path/to/RVC --training-report /path/to/RVC/logs/original-voice/voicematrix-training.json --input held-out.wav --output /path/to/new-conversion-check --text "The exact held-out words." --whisper-cli /path/to/whisper-cli --whisper-model /path/to/ggml-tiny.en.bin --python /path/to/rvc-env/python --timeout 600
```

The neural child is network-blocked and uses safe tensor-only checkpoint loading.
It validates v2/40 kHz architecture, finite tensors, the populated 768-dimensional
retrieval index, output duration, RMS, and zero full-scale samples. Upstream's
109-row speaker-embedding capacity is preserved; conversion selects trained label
0 rather than mistaking table capacity for the number of characters. Word error
rate must be at most 10%, bound to the exact output WAV hash. Silent, clipped,
mutated, mismatched, or failed-transcription output cannot pass. A passing status
is `conversion-checked-needs-review`, not identity or likeness verification.

## Separate per-voice export

Metadata JSON requires `id`, `name`, `categories`, `source`, and `permission`.
Use an honest anonymous or synthetic label unless the identity was reviewed.

```
python -m tools.voice_studio export-rvc --report /path/to/new-conversion-check/conversion.json --metadata original-voice.json --output /path/to/private-rvc-models
```

This creates a new `id` folder containing the exact checked `model.pth`,
`model.index`, and a hash/size/provenance manifest. Publication is atomic; existing
folders are never replaced. The destination must be separate from the F5
`collection.json` directory. Export does not include training recordings,
transcripts, conversion WAVs, or machine paths in the manifest.

The current iPhone engine cannot consume these RVC weights/index files. The
manifest explicitly reports `nativeIPhoneRuntimeVerified: false`,
`identityVerified: false`, and `likenessVerified: false`. Merely downloading a
folder is not offline voice inference.

## Verification scope

Source tests cover dataset snapshots, subprocess containment, collision
preservation, CLI argument routing, conversion/transcription evidence, and export
integrity. Fast orchestration tests replace the expensive neural boundary and use
opaque model fixtures; they are not evidence of trained neural audio.

On 2026-11-12 an isolated Windows Python 3.12 CPU environment passed pinned asset
hash checks, dependency checks, actual local HuBERT feature inference, and all 20
native safety tests. The final process-drain guard subsequently passed all 25
native safety tests twice. No live companion configuration or saved voices changed.

The [synthetic training smoke record](qa/rvc-synthetic-training-smoke.json) documents
a real one-epoch CPU run that admitted 83.08 active seconds of original synthetic
speech. A later accounting check found that a pinned-upstream preprocessing bug
silently dropped short slice tails: only 40.195 seconds actually reached training.
That is below the 60-second effective-data floor. The functional result remains
real, but this run is not eligible as an automatic-training admission proof.
A source-preserving tail correction and independent post-preprocessing gate are
being implemented before another neural run.
All five stages completed in about 130 seconds; 456 nonembedding tensors changed
versus a same-dtype pretrained baseline. The resulting 55.2 MB model and 6.3 MB
index passed real offline indexed conversion on a separate held-out clip and
independent Whisper transcription with zero word error. The exact checked pair
was exported to a new private synthetic-voice folder. This establishes desktop
functionality only, not character quality, production queue integration, or
iPhone inference. Minimum sampled free RAM was 2.48 GiB on the test laptop.

Still pending: production dataset preparation from speaker groups, source
separation/identity review, durable training-job integration, model catalog/sync,
resumable training, quality evaluation, and native iPhone RVC execution. The
existing short anonymous-candidate workflow remains F5 reference conditioning.


## Isolated queue integration (source candidate, not deployed)

The candidate `rvc_request`, `rvc_dataset_prepare`, `rvc_queue_processor`, and
`rvc_worker` modules form an opt-in private RVC path. It never promotes an F5
request into training permission. `create_server(..., rvc_root=...)` enables
paired `/rvc/capabilities`, `/rvc/status`, and `/rvc/requests` routes; without an
explicit separate root they do not create RVC jobs. Existing F5 routes and the
60 saved references are not migrated.

Dataset preparation retains original non-overlapping speaker-group segments,
reserves held-out excerpts, audits unique active speech, and records every
omission. Groups are anonymous: neither diarization nor this manifest proves a
character name, source separation, or likeness. The downloaded MP4 is temporary
and is removed by acquisition cleanup before dataset publication. An immutable
request snapshot, including insufficient-data results, prevents repeated downloads.

Training retains short slice tails that the pinned upstream preprocessor dropped.
A second gate counts only sampler-eligible audio after feature alignment and
subtracts overlaps. At least 60 effective active seconds must remain. The
single-CPU launcher calls the pinned training function directly without DDP's
random localhost port; a missing model halts before index generation. Hash-bound
training, conversion, independent transcription, and export proofs all carry the
effective-data gate. Models remain separate from the F5 catalog.

The optional worker requires explicit runtime paths, a 1–20 epoch diagnostic
budget, and once/poll mode. Windows gaming, pause/stop, available-memory (8 GiB),
and disk (20 GiB) guards fail closed. No automatic service is installed. See
`python -m tools.rvc_worker --help`. This source integration still needs a real
queued-video test and live deployment verification.

The `rvc_portable` candidate is only a fixed-shape one-second synthesizer ONNX
feasibility check. Its proof admission requires the corrected effective-data
gate. It is not an iPhone engine: HuBERT, pitch, retrieval, audio processing,
longer audio, native runtime integration and physical-device parity remain open.


## Corrected synthetic result, November 12, 2026

The [corrected smoke record](qa/rvc-corrected-synthetic-smoke.json) supersedes the
old run as an effective-data admission test. It retained 74.155 effective active
seconds, completed one real CPU epoch in 271.855 seconds, produced a populated
5,819-vector index, and passed a separate 7.22-second conversion with independent
Whisper transcription (zero word error). All 456 compared nonembedding tensors
changed beyond dtype rounding. The exact checked model/index pair was exported
privately; nothing was added to the live app catalog.

The same model also passed real ONNX Runtime CPU synthesizer parity for five
fixed-shape cases. Worst absolute error was 0.000048399 and RMS error 0.0000076582,
within the predeclared thresholds. The adapter matched the original PyTorch
function exactly for those cases. Generated Python caches were moved to a
separate backup before the strict source guard, not silently ignored or deleted.
This is a synthesizer portability milestone, not a complete offline iPhone engine.

The committed source run completed 486 tests: 481 passed and 5 platform checks
were skipped. Separate Windows safety/preparation tests passed 63/63. None of
these results establishes character likeness, physical-device performance, or a
finished end-to-end video request in production.
