# Companion automation validation — 2026-11-08

The source-inspection worker already canonicalizes its queue root before passing an inspection request to the path-protected reader. Direct inspection tests instead used the unresolved system temporary directory. On macOS this can include the /var system symlink, so five tests stopped at the path guard before exercising their intended behavior (run 42521922111).

Canonicalize the fixture root once, matching the real worker. Keep production rejection of linked request files and parents unchanged, including the existing real symlink/junction rejection test. Run the complete macOS source suite and native import checks automatically when tools or Python tests change, rather than discovering companion regressions only during an unrelated app change.

This is validation automation only. No app, model, private voice, source permission, review decision, installed laptop runtime or publication changes. Existing review requirements and pipelineConnected=false remain appropriate. Unfinished product automation includes reviewed revision activation, native feedback, completion ledger and speaker/visual-label proposals.

Validation: pending fresh macOS run; prior Windows/Linux source-inspection and listening-review evidence remains historical, not a result for this commit.
