# Automatic private speaker candidates

This is an unreleased source integration, not a completed video-to-RVC system.
The existing published application, update feeds and saved voices are unchanged.

## Request and processing

The request form sends the YouTube URL and an explicit private-source-use
affirmation to the authenticated laptop endpoint. Adding a URL to the list alone
does not authorize automatic candidate processing. The receipt means the laptop
accepted the request, not that voices have been generated.

When the separate speaker runtime is configured, the worker acquires a bounded
temporary video, decodes its audio, groups tentative speakers, extracts selected
references, transcribes them, and runs the existing F5 preview and independent
word/audio checks. A reviewed recipe takes precedence over automatic analysis.
Anonymous groups use source-specific IDs and unreviewed names; they cannot
silently replace an existing named character.

The integrated `tools/speaker_candidates.py` backend uses hash-pinned local
ECAPA weights and a Silero ONNX voice-activity detector. It does not fetch or
evaluate model-provided Python/YAML. Inference requires a separately provisioned
CPU Python environment with PyTorch, matching torchaudio, SpeechBrain, Silero VAD,
ONNX Runtime, NumPy and scikit-learn, plus the exact model assets accepted by the
loader. The exact integrated module and local models passed an isolated laptop
test in an already provisioned speaker environment. This did not install or
deploy the runtime into the live companion.

Configure all three worker options together:

- `--candidate-python /path/to/speaker-runtime/python`
- `--speaker-checkpoint /path/to/embedding_model.ckpt`
- `--vad-checkpoint /path/to/silero_vad.onnx`

The worker otherwise remains awaiting preparation without downloading media or
allocating the synthesis model. Missing runtime configuration can resume after it
is supplied. When a completed automatic preparation finds no usable references,
that request waits persistently for reviewed speech segments rather than
re-downloading on every poll. A later reviewed recipe or prepared specification
can resume it. Transport retries with a new request ID do not silently discard
that review requirement or change the saved source-use scope.

## Limits and preservation

- At most 30 minutes of analysis, 512 examined windows and 32 tentative groups.
- Each selected reference is 3–12 seconds. This is F5 conditioning input, not a
  sufficient RVC training dataset or trained network.
- Speaker names, character identity and likeness remain unverified. Grouping may
  miss or merge speakers. Overlapping speech and music are not separated.
- The downloaded MP4 is removed on success, failure or cancellation. Validated
  conditioning WAVs are retained because offline speech needs them.
- Reference revisions are written in a staging directory and published by an
  atomic rename. Interrupted copying cannot expose a partial final revision.
  Existing conflicting revisions and prepared specifications remain preserved.
- Queue ownership fences preparation publication and persistent review waits.
  Cancellation and transient failures do not become permanent no-candidate waits.

The catalog/selective-download implementation is described in
[SELECTIVE-VOICE-DOWNLOADS.md](SELECTIVE-VOICE-DOWNLOADS.md). It refreshes metadata
on app/library opening and foreground return and downloads only a selected
reference pair. It does not promise always-on iOS background synchronization.

## Verification and remaining work

On this Linux integration, `python3 -m unittest discover -s tests -v` ran 310
tests: 307 passed and three native Apple/Swift checks were skipped. The run
includes actual FFmpeg extraction and temporary-media cleanup, real queue/HTTP
contracts, interruption regressions and the bundled backend CLI. Speaker tests
use deliberately fixed embeddings to test grouping logic; they do not establish
real neural accuracy. The backend test dependencies are installed in the private
video-workflow CI job, so those grouping tests do not silently skip there.
The local browser regression could not launch Chromium because this environment
denied its process socket, including on the approved escalation attempt; no
fresh browser or screenshot result is claimed.

The exact integrated module also passed real ECAPA/Silero inference on three
existing synthetic laptop fixtures with networking blocked and two CPU threads:
silence produced zero candidates, one synthetic voice produced one group, and
two alternating synthetic voices produced two groups. Model loading and the
three cases took 5.38 seconds in that isolated environment. Source/model/fixture
hashes and dependency versions are recorded in
[speaker-candidate-synthetic-checks.json](qa/speaker-candidate-synthetic-checks.json).
This small test does not establish accuracy on real characters, overlapping
dialogue, music, long videos or every individual speaker.

No live YouTube processing, new RVC training, physical-iPhone download, likeness
approval, or newly built IPA was verified in this integration. The live companion
remains unchanged. Apple build/UI/audio gates and deployment/integration checks
are still required before release. Actual trained RVC export and native RVC use
remain separate unfinished work; see
[RVC-TRAINING-COMPANION.md](RVC-TRAINING-COMPANION.md).
