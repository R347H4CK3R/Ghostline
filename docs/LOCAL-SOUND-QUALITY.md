# Local candidate sound screening

This is a development admission signal, not source separation, perfect music detection, speaker identity, or VoiceMatrix 1.0.0 acceptance.

## API basis and identifiers

Apple documents `SNClassifySoundRequest(classifierIdentifier: .version1)` as the built-in OS classifier, `knownClassifications` as the authoritative supported-label list, and `SNAudioFileAnalyzer` asynchronous analysis/cancellation. The implementation uses those APIs, not a custom model or service. Apple's WWDC explanation states that inference runs on-device and that label confidences are independent; comparing or normalizing speech against music would be incorrect.

Primary references:
- https://developer.apple.com/documentation/soundanalysis/snclassifysoundrequest/init(classifieridentifier:)
- https://developer.apple.com/documentation/soundanalysis/snclassifysoundrequest/knownclassifications
- https://developer.apple.com/documentation/soundanalysis/snaudiofileanalyzer/analyze(completionhandler:)
- https://developer.apple.com/documentation/soundanalysis/snaudiofileanalyzer/cancelanalysis()
- https://developer.apple.com/videos/play/wwdc2021/10036/

The exact `speech`, `music`, and `singing` identifiers are checked against the runtime's label inventory before any candidate can pass. Native tests assert their presence. Their availability and actual scores have **not** been empirically verified on this Linux executor. If labels or scores are missing, screening fails closed with a clear error, not a fabricated zero score. No model assets or application network calls are introduced. Physical-phone airplane-mode behavior remains a required check.

## Admission policy version 1

Each retained mono WAV must be 1–15 seconds and at most 1.5 MB. Analysis uses one-second windows with 50% overlap and stores at most 128 result windows. A 30-second deadline cancels asynchronous analysis. Apple object initialization is synchronous and cannot be forcibly interrupted by this wrapper; cancellation takes effect at its next safe boundary. The app's live log still distinguishes last real activity from screen refresh.

A candidate is not admitted when any observed music or singing score is at least 0.2, when analyzed temporal coverage is below 80%, or when speech confidence of at least 0.5 covers less than 60% of its duration. Overlapping windows are unioned rather than double-counted. A strong speech score never cancels music/singing risk. Invalid, missing and non-finite evidence cannot pass.

These are deliberately conservative initial engineering thresholds, **not calibrated accuracy guarantees**. False positives and missed contamination remain possible. Passing means only that this screening policy did not find sufficient contrary evidence. The app still transcribes the reference and independently checks generated words; none of these checks verifies likeness.

## Real workflow and retention

The local studio writes its reference WAV, screens it, and retains a separate hash-bound quality JSON before transcription or F5 generation. Rejected references remain on disk with their reason and the next candidate is tried. Framework failures/cancellation retain a failure record and stop rather than bypassing screening. The log never includes the transcript or source path.

Resume can reuse an already admitted speaker only when the job records this screening-policy version. Older references are preserved, but their existence is not treated as evidence of passing new screening. After an awaited import, the log reads the actual saved profile name/ID and current voice count from the library. Reuse is labeled separately; existing voices are not removed.

## Verification gates

Native policy tests cover independent scores, temporal coverage, invalid evidence and uncertainty. Native classifier tests require real supported identifiers, admission of the existing hash-pinned neutral synthetic speech fixture, refusal of synthetic silence/tone, cancellation and remote-input refusal. Synthetic audio remains in the test bundle only. JSON classifier evidence is attached to the neutral-speech native test for review.

These native tests are wired to CI, not claimed run here. Neutral speech, silence and pure tones do **not** validate real music/singing rejection, mixed dialogue, or broad false-positive rates. Those require additional authorized listening/benchmark tests before any clean-speech or release-quality claim.
