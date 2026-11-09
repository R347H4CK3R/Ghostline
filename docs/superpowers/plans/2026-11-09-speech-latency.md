# Speech latency implementation plan

Goal: Reduce measured text-to-speech latency without changing the 32-step/seed-0 synthesis settings, private storage or offline behavior.

1. Profile the production adapter on one Metal runner: compare three unload/reload requests with three matched reused-model requests, separating load and synthesis wall time. Use only the existing neutral synthetic reference; deny network during generation. Record PCM differences and peak RSS.
2. Select an optimization only from measured results. Prefer bounded reuse if it materially helps and preserves audio. Do not lower step counts or change models based on intelligibility-only evidence.
3. Add lifecycle regression tests before app changes: timeout, memory pressure/background, error/cancellation and conversion must release retained resources. Ensure an old release timer cannot unload a newer request.
4. Implement the smallest supported change; run focused native tests, ARM64 compilation and simulator workflows. Repeat the measured comparison and report exact limits; hosted Mac timings do not predict iPhone performance.
5. Review the final diff and record evidence. Keep the verified 0.4.5 public release until a successor passes its release gates.

Existing main: 58db584fa616cda3169217b0327f3314738afd70. No overlapping open VoiceMatrix performance PR found. Work is isolated in performance/voicematrix-speech-latency. User's standing instruction authorizes autonomous implementation; no new design confirmation is needed.
