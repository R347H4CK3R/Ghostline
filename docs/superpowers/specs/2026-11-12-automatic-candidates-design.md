# Automatic private voice candidates

## Intent
A request from the iPhone should actually start bounded laptop work instead of merely recording a URL. Preserve the working F5 collection and offer selective offline downloads. The user requested real RVC models too; those remain a separate honest compatibility/training milestone, never renamed reference files.

## Chosen approach and alternatives
The parent directed implementation of the compatible F5 path while assessing genuine RVC in parallel. Existing shared F5/OpenVoice engines can consume reference audio and transcripts today. A pure RVC replacement would require a new laptop training runtime and a native iOS inference port, and cannot be presented as the current implementation. A manual-only review queue leaves the reported request stall unresolved.

## Engineering decisions
- A new authenticated request records a source-use affirmation supplied by the user. Legacy queue-only submissions retain their current semantics. No default is treated as permission.
- Run bounded download, local speaker-candidate analysis, transcription and existing synthesis/audio/word checks. Speaker grouping is tentative, never character identification; unknown names stay anonymous. Similarity scores do not establish likeness.
- Publish new F5 reference candidates under source-specific IDs, with explicit unreviewed identity metadata. Preserve existing voices and keep listening review separate from technical success.
- Temporary downloaded movies are removed after processing, including errors and cancellation. Retained reference audio remains available for offline speech. No private source asset enters public source or release artifacts.
- Keep the loopback server and authenticated Tailscale HTTPS transport. Do not change account, firewall or Tailscale permissions.
- Refresh a metadata-only remote catalog. Download one selected voice when requested; existing local voices are retained. Offline means local audio plus the installed shared speech engine. iOS foreground refresh is not continuous background sync.

## Acceptance and limits
Use real source-bound artifacts, actual stage events and independent word checks. Tests must cover duplicate submissions, changed authorization, lost worker ownership, cancellation, malformed media, stale catalog downloads and preserved old voices. Native compile/UI checks and a real laptop request are required before release claims. Physical iPhone verification and perceptual likeness cannot be inferred from CI. RVC exports require actual trained checkpoints plus independent conversion verification and sufficient clean data.
