# Browse online, keep selected voices offline

The phone now refreshes a metadata catalog rather than copying the entire laptop collection. Opening the app/library, returning to the foreground, or tapping **Refresh laptop catalog** checks the authenticated `/voices` endpoint. Automatic attempts are throttled to once per minute; there is no timer or promise of always-on iOS background synchronization.

In **Choose a voice**, names and categories from the laptop appear alongside existing imported voices. **Download for offline** requires a working Tailscale/laptop connection and fetches only the selected voice's manifest and WAV. The button displays their combined bytes. A fresh metadata response is required first so stale cached names cannot silently download changed content. The downloaded pair must pass SHA-256, length, manifest identity, audio-format and existing private-import checks before becoming selectable. Keep the app open while downloading; Stop, backgrounding or a connection failure retains existing saved voices.

The catalog is saved privately for offline browsing with a last-connected timestamp. Cached availability is not proof that the laptop is reachable now. **Downloaded · ready offline** means the voice is in the existing private imported library. A laptop removal does not delete that saved copy, and changed audio/transcripts still require reviewed replacement support. No automatic eviction or removal control is added. **Saved voice files** counts retained files in the character-reference store, including older immutable revisions, excluding the shared engine and saved recordings.

Manual folder import remains an explicit whole-folder operation. Old imports, index format, revision directories and bookmarks are preserved. Automatic refresh no longer reimports an old bookmarked folder. Shared F5/OpenVoice engine weights remain on the phone; these selected downloads are F5 conditioning references, not trained RVC weights.

## Wire compatibility and limits

`GET /voices` remains schema version 1, with the existing `revision` and hash/size-bound `files` list. An added `voices` array contains the exact validated manifest objects for browsing. Older clients can ignore the new field and continue using the existing endpoint. A newer phone with an older companion fails clearly without falling back to bulk audio downloads.

File URLs are unchanged: `/voices/{revision}/{id}/manifest.json` and `/voices/{revision}/{id}/reference.wav`. The phone constructs a single-entry `collection.json` locally only after both files validate. It never downloads the all-voice collection for an individual voice.

The catalog response is capped at 1 MiB, references at 848,000 bytes each, manifests at 65,536 bytes, and the source snapshot at 64 MiB/1,000 voices. Catalog requests have a 30-second overall deadline, downloads 120 seconds, request inactivity 15 seconds. HTTP redirects are rejected, response URLs must match, caching is disabled, streaming bodies are bounded, and cancellation invalidates the session. All endpoints retain bearer/same-account Tailscale authentication.

## Checks

`python3 -m unittest discover -s tests -v` includes real Python catalog and HTTP transfer regressions. On an Apple host it also compiles and executes `tests/native/SelectiveVoiceDownloadChecks.swift`, exercising selected-file requests, one-voice import, existing-voice preservation, corruption/cancellation, invalid catalogs and persistent metadata cache. The existing native-character-folder workflow watches the new sources. An Apple SDK build and simulator/physical-phone interaction remain required before releasing an IPA; Linux source tests do not prove native UI or Tailscale behavior.
