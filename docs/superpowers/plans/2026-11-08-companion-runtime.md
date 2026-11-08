# Companion Runtime Implementation Plan

Goal: stage and verify the actual Windows companion without allowing duplicate model workers or unbounded Torch threads.
Architecture: preserve the existing endpoint and private master; stage a complete pinned source snapshot. Bind a process lifetime lock to the canonical database path, including aliases. Configure two CPU threads by default (allowed 1–4), one interop thread and lower scheduling priority before lazy model initialization.
Constraints: no automatic human approval, no character assets in source, no feed/IPA change, no model execution while gaming; retain current pause/ownership/audio checks.

- [x] Add failing real child-process tests for contention, canonical aliases, crash release and different databases; test thread limits and lazy Torch setup.
- [x] Implement companion runtime controls and wire them into the actual queue processor CLI. Run the full suite.
- [x] Stage pinned complete modules, verify Git blob hashes, run full Windows tests and live metadata-only acquisition probe; install isolated CPU dependencies, check imports without model inference.
- [x] Independent review, repair important findings, hosted platform checks, then fast-forward only after fresh main/feeds checks. Record actual deployment limits.

Review focus: locks must not be deleted while another worker can hold them; aliases must contend; failed initialization must release locks; thread controls must precede allocation; prepared input/word checks cannot become weaker.

Execution: original four tests RED→GREEN; real Windows priority startup failed with handle error6, then new native-priority regression RED→GREEN after pointer-sized WinAPI declarations. Full168tests passed locally, on the laptop and both hosted platforms (42481405058). Complete source/dependencies/assets were installed privately; real neutral synthesis/independent recognition/export passed, and the bounded reviewed-recipe worker was observed alive with its lock held. Automatic identity/review feedback/sync remain outside this completed runtime step.
