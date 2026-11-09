# Speech latency implementation plan and ledger

Goal: Reduce measured text-to-speech latency without changing the 32-step/seed-0 synthesis settings, private storage or offline behavior.

- [x] Profile the production adapter on a Metal runner. Compare matched reload/reuse requests, deny network and use only a neutral synthetic reference. See docs/qa/0.4.6-latency-measurements.json.
- [x] Implement measured bounded reuse with a 60-second idle timeout. Preserve cold-start model checks and per-request reference validation.
- [x] Observe RED for reuse against unload-every-request behavior, then GREEN for the actual adapter's lifecycle through a lightweight neural boundary: idle expiry, stale timers, pressure during suspended load/generation, background release, cancellation/error cleanup and corruption rejection.
- [x] Repeat real-model benchmarking with hard PCM equality and changed-text checks. Median repeat-pair saving: 1.69 seconds / 9.9% across six pairs; first-use pairs excluded, large hosted-runner outlier retained.
- [x] ARM64 compilation, 219 source regressions and all five native candidate gates passed. Candidate IPA 731114673 bytes, SHA-256 27cc1a45d92529bf1acd5f3c1383f8e278fb990cd6114baa3df3b1bef0c17aef.
- [ ] Finish corrected simulator run42642950816. Run42636544296 passed 15 checks including suggestions, then its replay tap hit a reference button partly behind the tab bar, confirmed in recording/hierarchy. Test now fully reveals controls and reserves status space; no product change.
- [x] Independent read-only review completed. Important validation findings addressed: enforce zero PCM difference and exercise suspended load/generation plus failure/cancellation. No confirmed production correctness blocker.
- [ ] Obtain successor integration/publication approval. Automatic approval review rejected the proposed public0.4.6 release/feed-writing workflow. It was not created or retried; only a read-only candidate build workflow was added. Public release/feeds remain0.4.5.

Ruling: Use a remote isolated branch and GitHub Actions because no local executor is available; no local or physical-device testing is claimed.
Ruling: Keep 32 steps/seed0 and the pinned model; no inference-quality tradeoff is introduced.
Ruling: Retain only successful no-effects requests. Effects/conversion release before their work, at the cost of losing this optimization for those requests.
Ruling: Treat the first benchmark pair per process as initialization-confounded and retain all other observations, including the large outlier; hosted Mac measurements do not predict phone performance.
Ruling: A requested20-ms harness sleep actually took82ms, crossing its80-ms expiry. Use condition-based waiting and a wider test deadline; production timer logic did not change.
Review caveat addressed in evidence: adapter load time excludes lazy neural weight setup performed inside generation. Total request time is the reported latency measure.
Remaining limits: physical iPhone latency, memory/thermal behavior, update handoff and character likeness. Effects/conversion call-site ordering was reviewed; the lightweight lifecycle harness does not measure actual neural memory reclamation.

Suggestions: existing daily monitor inspected, owner issue47 read and linked to PR48. No duplicate monitor, public issue comment or automatic submission. UI explains quiet review/build route; configured monitor's historical execution result remains unavailable.
