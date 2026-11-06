#!/usr/bin/env python3
"""Source-level regression for private recorder-to-WebKit RVC audio handoff.

This verifies wiring and rights/privacy invariants only, not device inference.
"""
from pathlib import Path

voice = Path("Ghostline/VoiceChanger.swift").read_text(encoding="utf-8")
native = Path("Ghostline/OfflineRVCWeb.swift").read_text(encoding="utf-8")
browser = Path("scripts/build_offline_rvc_web.py").read_text(encoding="utf-8")
assert "GhostlineRVCWebScreen(importedPack: selected, sourceAudioURL: recordingURL)" in voice
assert ".disabled(recording)" in voice
assert "No Files export/re-import required." in voice
assert "privateSourceAudio = nil // revoke source recording at converter teardown" in native
assert 'let route = "/private-source-" + UUID().uuidString + "." + ext' in native
assert '(try? self.fileSHA256(sourceAudio.file)) == sourceAudio.sha256' in native
assert "size > 44, size <= 128 * 1024 * 1024" in native
assert 'canonicalFile.path.hasPrefix(temporaryRoot + "/")' in native
assert "sourceAudioURL: URL? = nil" in native
assert "source: \"window.__ghostlineSourceAudioPath" in native
assert "Cache-Control: no-store" in native
assert "Cross-Origin-Resource-Policy: same-origin" in native
assert 'if let sourceAudio, path == sourceAudio.route {' in native
assert 'self.sendError(connection, code: 409, message: "Private Audio Integrity Failure")' in native
assert '__ghostlineSourceAudioPath?: string' in browser
assert 'if (!audio)' in browser
assert 'const response = await fetch(window.__ghostlineSourceAudioPath!' in browser
assert 'audio = new File([data], "private-recorded-source." + ext' in browser
assert '(!audio && !window.__ghostlineSourceAudioPath)' in browser
assert 'new File([data], "private-imported-candidate.pth"' in browser
assert '"rvc_index_retrieval_integrated": false' in native
assert '"voice_identity_verified": false' in native
assert '"airplane_mode_confirmed": false' in native
assert '"source_audio_sha256": NSNull()' in native
print("Private RVC audio handoff, no-upload routing and verification guards: PASS")
