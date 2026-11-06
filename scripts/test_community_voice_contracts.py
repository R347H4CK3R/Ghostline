#!/usr/bin/env python3
"""Contract checks: no fake verified voices or private files in community workflow."""
from pathlib import Path
import re

root = Path("Ghostline")
app = (root / "App.swift").read_text()
community = (root / "CommunityVoices.swift").read_text()
downloader = (root / "CommunityRVCDownload.swift").read_text()
diagnostics = (root / "GitHubDiagnostics.swift").read_text()
changer = (root / "VoiceChanger.swift").read_text()

assert "GhostlineVoiceChangerView()" in app
assert "GhostlineCommunityVoicesView()" in app
assert "GhostlineDiagnosticsView()" in app
assert app.count(".tabItem") == 5, "Keep the approved five-tab navigation"
assert "CANDIDATE_UNVERIFIED" in community
assert "Voice Changer" in changer and "GhostlineRVCWebScreen(importedPack: selected)" in changer
assert "index retrieval is not yet implemented" in changer
assert "ShadowSH2306/shadowww-voices" in community
assert "CC BY-NC 4.0" in community
assert "https://huggingface.co/" in downloader
assert "Task.detached" in downloader
assert "model_checksum_failed" in downloader
assert "downloadProgress" not in downloader or "percent" in downloader
assert "SecItemAdd" in diagnostics and "kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly" in diagnostics
assert "GitHubDiagnostics.shared" not in community, "Do not confuse public GitHub reports with private diagnostics"
assert "GhostlineDiagnostics.shared.record" in community
assert "https://api.github.com/repos/R347H4CK3R/Ghostline/issues" in diagnostics
assert "enabled && hasToken" in diagnostics
for forbidden in ("input_text", "model_path", "raw_audio", "private_token"):
    assert f'\"{forbidden}\"' not in diagnostics
assert "fileImporter" in changer and "startRecording()" in changer
print("Community Voices, Voice Changer, private model import and opt-in diagnostic source contracts passed.")
