# Local visual evidence, not automatic character identity

The local studio samples the midpoint of the first retained speaker-only reference window for up to twelve tentative speaker groups. AVFoundation decodes at most640-pixel frames and applies the video track transform. Vision performs English OCR locally without a network service, language correction or a character-name model. Each retained JPEG is at most250,000bytes, with at most eight160-character text observations. A timestamp mismatch over150ms is rejected rather than attributed to the requested turn.

Source-bound reports retain frame timestamps, hashes and OCR confidence. The job snapshot commits the report only after extraction finishes; cancellation leaves any already written frames and original source intact. Successful reports are validated/reused on resume. Audio-only sources skip visual work. Frames that cannot be decoded or stored are counted as unavailable, not invented. A separate optional visual-stage failure allows the audio/reference path to continue with explicit unidentified labels. No existing voice or original media is removed.

The Video Voice Studio disclosure displays the sampled frame and visible text. Hash-changed or missing frames are not shown. A visible face or subtitle is not proof of who is speaking. OCR confidence is confidence in recognized text, not identity, name, audio/visual association or likeness. No profile is renamed and no reference is promoted into an RVC model by this feature. Persistent names and reliable character attribution remain separate work.

## Verification

`probes/native-visual-evidence/Checks.swift` creates an original synthetic H.264 video with a text label, invokes the actual production frame/Vision scanner, checks recognized text, source preservation, timestamp alignment, JSON reload, wrong-source and changed-frame rejection, traversal rejection, audio-only behavior and cancellation. The dedicated Apple workflow runs it with networking denied. Presence of this probe is not a passing native test; CI must be checked for the exact commit. Linux tests inspect wiring only.

Resource limits reduce work but do not promise a hard deadline for a framework call. Cancellation is checked between frames and before/after OCR; AVFoundation generation is cancelled on task cancellation. Frames written before interruption remain retained for recovery/diagnosis. The app's existing foreground, memory-pressure and thermal safe-stop behavior remains active. No physical-iPhone performance or universal OCR accuracy is claimed.
