# VoiceMatrix interface refresh Implementation Plan

**Goal:** Make selecting a voice and producing audio straightforward while preserving working playback and private data.
**Architecture:** SwiftUI presentation changes consume existing CharacterLibrary, Recorder and AudioStore APIs. Storage and engines remain unchanged.
**Tech Stack:** SwiftUI, XCTest, GitHub Actions macOS.
**Spec:** ../specs/2026-11-08-voicematrix-interface-design.md

## Global Constraints
- Keep private storage, playback lifecycle, model pins and bundle identifier unchanged.
- Test fixture import is DEBUG-only and available only when an explicit launch argument and simulator-only bundled fixture are present.
- Do not publish an unverified candidate.

## Review Focus
- Empty library cannot create or review fake output.
- Picker selection must be one tap and survive dismissal.
- Long voice names and accessibility sizes must wrap.
- Imported references survive relaunch; no reset or migration.
- Cancellation and mode changes retain microphone ownership rules.

## Tasks
- [x] Restyle Home in App.swift with compact primary and secondary actions; preserve accessibility identifiers.
- [x] Extract selection into CharacterPickerView in CharacterLibraryView.swift; keep model class byte-identical.
- [x] Organize composer and reference controls, retain output identity checks and errors.
- [x] Update CharacterEmptyStateUITests and add synthetic import/selection/playback/relaunch workflow.
- [x] Run character-ui-smoke and native compile; inspect failures/screenshots.
- [x] Review final diff, integrate tested changes, then produce gated IPA with feeds held until verified.

## Verification outcome

Published 0.4.4 after [native release gates](https://github.com/R347H4CK3R/Ghostline/actions/runs/42520114505), [13 simulator checks](https://github.com/R347H4CK3R/Ghostline/actions/runs/42519869947), screenshot inspection and review. PR #42 is merged. All three feeds were re-audited in [run 42522371606](https://github.com/R347H4CK3R/Ghostline/actions/runs/42522371606). Device UI and updater handoff verification remain outstanding.
