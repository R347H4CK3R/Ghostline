# Local companion runtime

The processor CLI takes `--threads 2` by default (range 1–4). It sets OpenMP/MKL/OpenBLAS limits before lazy Torch loading, applies the same intra-op limit and one inter-op thread, and lowers its scheduling priority. These limits reduce contention; they do not promise zero gaming impact. Existing game/stop/pause cancellation remains active. No model is allocated for missing prepared input.

A process-lifetime OS lock belongs to the canonical database pathname, so two CLI workers targeting that queue cannot both initialize a model. Relative/path aliases share ownership; process exit/crash releases the lock. The persistent lock file must not be deleted while workers may exist. Separate database paths intentionally allow separate workers; the installed companion must use one configured database. This does not limit unrelated programs or differently named hard links to one database.

For Windows, use an isolated Python environment rather than the system environment. The measured acquisition setup uses `yt-dlp==2026.10.26` and `imageio-ffmpeg==0.8.1`; the latter includes the local FFmpeg executable. The processor's recognizer invokes `ffmpeg` by name, so its launch environment must include the companion-only bin directory on PATH. No system-wide PATH change is required.

Install the CPU PyTorch packages from their official CPU index first:

```powershell
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0+cpu torchaudio==2.11.1+cpu
python -m pip install f5-tts==1.1.22 torchcodec==0.17.0 -r tools/requirements-acquisition.txt
```

An installation is not a successful import, model load, inference or working queue service. Keep model/checkpoint/vocoder/vocabulary and independent whisper paths explicit and local; retain checksum checks. No model downloads occur implicitly in the worker. Validate dependency imports and neutral audio before enabling persistent processing, then use the actual quality/review gates. The existing endpoint must receive the complete coupled queue source snapshot when the processor is connected; staging source alone must not be reported as an endpoint upgrade.

The existing app release and private character collection are unaffected by companion setup. Human likeness review and physical iPhone tests remain separate.
