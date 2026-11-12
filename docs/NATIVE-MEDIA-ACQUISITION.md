# Native media acquisition (candidate, not provider acceptance)

This path acquires authorized media directly on iPhone and feeds the existing LocalVideoStudio analysis/reference workflow. Internet is needed for acquisition, not a laptop or conversion service. Existing local import remains available. No private media or links are included in tests.

## Deliberate dependency decision

Inspected alexeichhorn/YouTubeKit at `7f75a2299dc329c0b7855afb25d47663a02855cb`. Its MIT Swift package declares no package dependencies and uses JavaScriptCore resources. It is **not included** here: explicit `.local` still reaches `bypassAgeGate`, verified-age watch parameters, alternate clients and shared sessions without app-controlled bounds/redirects. No upstream code/resources were copied or executed.

Instead the candidate fetches the ordinary canonical watch page, parses bounded `ytInitialPlayerResponse` JSON without executing JavaScript, requires public OK status, matching video ID, nonlive and bounded duration, rejects known non-family-safe responses, and selects only directly provided MP4 AVC/AAC URLs. Cipher-only formats, access/login/age challenges, DRM, HLS/DASH manifests and live video are not claimed supported. No remote service, OAuth, cookies or challenge bypass exists. Broad reliable YouTube compatibility remains an unresolved acceptance item; this limited resolver must not be marketed as general YouTube support.

Direct media hosts are intentionally limited to `upload.wikimedia.org`, `archive.org`, and the narrowly matched `ia[0-9]{6}.us.archive.org` storage-node form documented by Internet Archive itself (https://archive.org/developers/md-read.html). Archive redirects remain within that provider family; other CDN forms and cross-provider redirects fail closed. Native tests intercept a normal archive-to-storage-node redirect and reject a private-network redirect without network access. This does not claim live provider success. YouTube pages stay on exact approved YouTube hosts and their streams stay on googlevideo.com subdomains. HTTPS, normal certificate validation, no URL credentials, no arbitrary/IP/local hosts or ports, at most five redirects. This is trusted-host allowlisting, not a general-purpose URL fetcher or arbitrary-host DNS-rebinding defense.

## Retention and limits

Original submitted URL is private job metadata, normalized URL is the receipt identity, and provider stream URLs are private acquisition metadata. URLs/query tokens, provider response text, source paths and transcripts never enter the progress log. The retained ordinary watch HTML may contain provider metadata and is private, not a publication artifact.

Downloads stream to unique retained files with SHA256, expected-length checking, 512 MiB total source bound, 30-second request/900-second resource timeout, throttled actual received-byte progress and storage checks. Admission accounts for retained job data (2 GB cap) and an 800 MB free-space reserve, reserving room for a merged copy only while acquiring separate tracks. That reservation includes already completed tracks; direct/progressive downloads and the final merge do not reserve an extra second merged copy. Individual page bodies are bounded at4 MB or the smaller remaining storage budget. Unknown totals are stated, not invented percentages.

Each complete track is committed to an atomic private receipt. Resume verifies SHA256 before reusing it. Partial downloads are never appended without validation: retries create a new file while retaining prior partial evidence. Expired stream URLs produce a clear failure, not silent unsafe retries. Completed receipts are reused unchanged. Failed attempts can consume the cap; nothing is automatically deleted.

Separate AVC video/AAC audio are merged using AVFoundation passthrough with a five-minute bound. Both original tracks remain. Lengths must agree within250 ms; only their common range is merged. Successful merged output remains hash-bound. AVFoundation owns temporary export behavior on cancellation, so incomplete merged-file persistence is not guaranteed by this implementation; original downloaded tracks and receipts remain sufficient for retry.

The app pauses acquisition/processing when entering background (not transient inactive states such as permission dialogs) and exposes real stage/byte activity through its existing live/stale log. No background completion guarantee. Sources remain until user-directed removal; voices are never replaced.

## Verification gates

Python tests check wiring/security-source contracts only. Native XCTest covers normalization, host/credential rejection, restricted/cipher/live/mismatched-ID rejection, progressive/adaptive selection, synthetic intercepted transfer bytes, retained partials, mutation detection and cancellation. An additional native gate creates three-second synthetic black video/tone AAC tracks, runs the real AVFoundation merge, checks both output tracks/duration and verifies original bytes are unchanged. Network is intercepted by a test-only URLProtocol; the production downloader has no fixture bypass.

Pending: native compile and all native tests; real provider public-page success/failure; physical-iPhone download/memory/storage/interruption; AVFoundation separate-track merge gate and interrupted merge; broad provider coverage. No live source was fetched for an acquisition test, no external package was installed or executed, and no claim of full standalone1.0.0 acceptance is made.

Export uses Apple’s async `export(to:as:isolation:)`, whose initiating Task cancellation cancels the export: https://developer.apple.com/documentation/avfoundation/avassetexportsession/export(to:as:isolation:). Merge progress only updates when the exporter percentage changes, not on every polling heartbeat.
