# Video-reference imitation workflow

This development workflow takes a public YouTube link, reviews on-screen character labels and the associated isolated dialogue, and makes explicitly labeled synthetic imitations. It does not identify real people biometrically.

1. Use the normal downloader on a computer where the public media is accessible. Do not bypass authentication, bot challenges or access controls.
2. Inspect video frames and associate character labels with isolated speech; do not infer identity from pitch alone. Background music, overlapping speech and very short clips reduce reference quality.
3. Select 0.5–15-second single-speaker segments. Transcribe and check their reference text before conditioning.
4. Call the shared F5-TTS v1 model with each reference and novel text. Preserve source metadata and checksums; normalize only to prevent clipping.
5. Independently transcribe generated audio, decode it, and check sample energy and full-scale samples. Human reference-based resemblance testing is separate.
6. Retain downloaded originals, extracted references and interrupted intermediates until authenticated destination storage is verified. No cleanup eligibility is implemented yet; see SOURCE-RETENTION.md.

`tools/video_reference.py` exposes `acquire(url, segments, retention_root=persistent_root)` as a context manager and `synthesize(references, texts, output_directory)`. The acquisition context preserves its downloaded video and slices on success, failure and cancellation. It validates IDs, hosts, segment ranges and actual audio/video decoding before admitting a source. Temporary files created internally by synthesis libraries require their own cleanup; do not assume the acquisition context owns them.

Dependencies: Python, FFmpeg (or imageio-ffmpeg), yt-dlp[default] with Node support, f5-tts, NumPy and SoundFile. For Linux CPU, install matching CPU Torch/TorchAudio and **CPU TorchCodec** from the official PyTorch index; the default TorchCodec package can request CUDA libraries even when synthesis uses CPU. Install httpx[socks] when the selected environment uses a SOCKS proxy. Do not disable proxy or TLS validation to work around missing dependencies.

Historical experiment under the superseded cleanup policy: video EAT0nWoEzJ8; opening video cards identify Rick followed by Morty. Reference windows were 6–16 and 22–32 seconds. The full video downloaded and decoded on the connected Windows laptop; only reference slices were transferred internally for development processing. The full laptop video and all local laptop extraction files were deleted. No reference recordings or pretrained character weights are committed to this repository.

This is **development CPU synthesis, not native iOS integration or RVC training**. An F5-TTS reference-conditioned sample or reference metadata file is not a .pth RVC model. Do not rename audio or JSON to .pth. F5-TTS code is MIT; the selected pretrained F5 model is CC BY-NC 4.0. A public video link does not establish recognizable-likeness or recording redistribution permission. No authorization, human similarity score, near-indistinguishable claim or app-library replica count is established by this experiment.
