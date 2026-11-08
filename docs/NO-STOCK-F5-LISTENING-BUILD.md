# No-stock F5 listening candidate: local implementation

This separate, artifact-only build path uses current main's character comparison
screen and persistent Matches / Does Not Match / Unsure decisions. It does not
replace the existing stable release, no-stock build 9, installation feeds or user
recordings. The dedicated workflow runs manually or on its dedicated build/no-stock-f5-listening branch, has read-only repository
permissions, and contains no release, deployment or push action.

## What is packaged

- The exact released no-stock build-9 resource archive is verified by SHA-256 before
  extraction. Its manifest must contain zero stock profiles. Phonon/OpenVoice engine
  files and original notices remain, but profile payloads are rejected. All 41
  retained files also have independent repository pins checked in the final IPA.
- Seven F5 assets are pinned by revision, exact byte count and SHA-256, totaling
  702,250,584 bytes. The native runtime proof describes these exact files. The archive
  inspector compares to the repository's pins, not a self-authored archive manifest.
- F5 CC BY-NC 4.0 license, model attribution/card and speech-swift Apache 2.0 license
  accompany the bundle, plus upstream pypinyin/jieba/Vocos MIT notices. Before native
  compilation, dependency notices are collected from clean resolved Git checkouts,
  including nested tracked notices and Package.resolved. An external build inventory
  is required by final inspection; an archive cannot redefine that evidence.
  No character source or likeness permission is implied.
- Private character recordings/transcripts are not bundled. The user imports their
  existing collection on their phone. The shared engine loads from the bundle;
  missing or corrupted files fail rather than falling back to stock speech.

`tools/listening_package.py prepare --cache <cache> --resources <new-directory>`
prepares assets locally. It refuses an existing output directory. Caches are verified
before reuse, and a failed download cannot replace an existing asset. Do not place
private character references in a public workflow or artifact directory.

The workflow temporarily sets 0.3.2 build 10 in its checkout, compiles the current
ARM64 app, and runs `tools/listening_package.py inspect <candidate.ipa> --dependency-proof <build-notices.json>`. The gate
checks app identity, ARM64 header, icons, stock-free manifests, resource hashes,
complete F5 files, notices, duplicate paths, path traversal and unexpected F5 content.
It rejects the build-9 placeholder. Engine directories are replaced cleanly, rather
than overlaid. Recognized audio/collection filenames are forbidden elsewhere, but this
is not a general private-content scanner or a certification of all license obligations. A passing archive result explicitly says device
execution and character likeness are unverified.

## Evidence boundaries

Python 3.11+ is required; the workflow provisions Python 3.12.

Python unit tests use small synthetic model fixtures to exercise the packaging gate;
they do not execute a voice model or prove that an IPA launches. Native listening
history/audio-ownership checks and ARM64 compilation run only on the Apple executor.
The workflow does not claim new native speech quality from packaging alone. Earlier
12-clip neutral calibration passed ASR, but the prior same-settings failure is not
explained and actual character references were not tested by that calibration.

Before calling the result functional, run the candidate on the user's physical
phone: import the private collection, enable Airplane Mode, generate fresh text,
compare reference and generated speech, test decisions and changed selections,
save/replay output, and check cancellation, latency and memory. User listening
judgment is required for each character; zero ASR errors cannot establish resemblance.

## Current limits

Local implementation only. Actual local staging has verified all seven F5 assets and the 41 retained baseline
resource files. Native dependency-notice collection still requires real Apple
checkouts, and no new workflow run, native compile, IPA or release is
claimed until actual execution succeeds. This Linux workspace cannot compile the
iOS app. Existing publication restrictions still apply; this file is not approval
to publish or dispatch the workflow. Keep unrelated blocked benchmark publication
separate from this packaging change.

## No-stock source integration

The candidate accepts an intentionally empty stock catalog rather than reporting
corruption, routes the primary Home speech action to My Character Folder, and makes
voice-conversion limitations explicit. Current character review/store files remain
unchanged. Legacy stock inference XCTest cases now skip explicitly because there
are no stock profiles; that is not an F5 inference pass. Updated navigation tests
check the character-folder route without stock fallback. These XCTest/UI cases have
not run locally. The Mach-O inspection is an architecture/header smoke check, not
proof that an executable launches.
