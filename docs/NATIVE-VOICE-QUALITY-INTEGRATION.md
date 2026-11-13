# Standalone visual and speaker-quality development candidate

This is work toward 1.0, not acceptance or a new released IPA. It preserves build3,
existing reference profiles and retained media. No laptop or service is introduced.

The coordinator samples bounded source-hash-verified video frames and records
visible OCR text with OCR confidence. Audio-only input remains supported. A frame
near a speaker turn does not establish that the visible character spoke; captions,
name labels and faces do not silently rename a profile. Frames and failed attempts
remain in private job storage. The URL Paste button is an explicit system control,
not clipboard monitoring, and never starts acquisition on its own.

After a preview passes its independent word check, the coordinator snapshots and
rechecks its exact bytes against ASR evidence. It then compares the reference and
preview using existing pinned local 256D speaker embeddings. The finite normalized
cosine value and both audio hashes are retained in an attempt-specific report.
The current view displays a recorded metric only for the matching attempt; changing
the reference clears it. Reload/display rechecks the bounded retained WAV hashes; altered files hide the old score. This is not a likeness percentage, identity decision or
calibrated pass/fail gate. A bounded diagnostic failure does not discard otherwise
word-checked references; cancellation still pauses the whole job. Changed preview
bytes and source hash/read failures are fatal rather than treated as optional diagnostic failures.

Required verification: source tests and pure state tests, actual native Vision/frame
and embedding diagnostics, exact-source app compile/UI checks and the full production
coordinator with network denied. The latter must produce a matching diagnostic rather
than silently exercising only its optional failure branch. Physical-iPhone memory,
thermal, install and real-character likeness checks remain separate. Native RVC
training/inference and automatic reliable character identity are not implemented by
this change. Existing reference-conditioned presets remain accurately labeled.
