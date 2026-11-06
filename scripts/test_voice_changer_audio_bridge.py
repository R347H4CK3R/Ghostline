#!/usr/bin/env python3
"""Source-contract checks for the private record-to-convert bridge."""
from pathlib import Path
native=Path("Ghostline/OfflineRVCWeb.swift").read_text()
changer=Path("Ghostline/VoiceChanger.swift").read_text()
builder=Path("scripts/build_offline_rvc_web.py").read_text()
for x in ("func allowSourceAudio(_ audio: URL)", "privateAudio = nil",
          "privateAudio = PrivateAudio", "private-source-",
          "fileSHA256(audio.file)", "size <= 80_000_000",
          "importedAudioPath = try server.allowSourceAudio(sourceAudio)",
          "window.__ghostlinePrivateAudioPath", "Cross-Origin-Resource-Policy: same-origin",
          "GhostlineRVCWebScreen"):
    assert x in native, x
assert native.count("privateAudio = nil") == 1
assert "GhostlineRVCWebScreen(importedPack: selected, sourceAudio: recordingURL)" in changer
assert "Save it to Files, then" not in changer
for x in ("__ghostlinePrivateAudioPath?: string", "sourceResponse = await fetch(",
          "if (!audio && window.__ghostlinePrivateAudioPath)",
          "if (!audio) throw new Error", "new File([contents]"):
    assert x in builder, x
assert "api.github.com" not in builder
print("Private native-to-WKWebView WAV/MP3 handoff contracts passed.")
