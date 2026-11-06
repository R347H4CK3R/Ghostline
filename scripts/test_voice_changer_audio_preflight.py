#!/usr/bin/env python3
"""Source contracts for private RVC audio preflight; device inference not certified."""
from pathlib import Path

voice = Path("Ghostline/VoiceChanger.swift").read_text(encoding="utf-8")
server = Path("Ghostline/OfflineRVCWeb.swift").read_text(encoding="utf-8")
source = voice.split("private func importSourceAudio(_ source: URL) async {", 1)[1].split("private func startRecording()", 1)[0]
for required in (
    "Task.detached(priority: .userInitiated)",
    "source.startAccessingSecurityScopedResource()",
    "source.stopAccessingSecurityScopedResource()",
    '["wav", "mp3", "m4a", "caf"].contains(ext)',
    "(attributes[.type] as? FileAttributeType) == .typeRegular",
    "byteCount > 44, byteCount <= 128 * 1024 * 1024",
    "FileManager.default.copyItem(at: source, to: destination)",
    "return (destination, \"\")",
    'GhostlineDiagnostics.shared.record("app", "file_import_failed")',
    "defer { importingAudio = false }",
):
    assert required in source, required
assert source.index("byteCount > 44") < source.index("copyItem(at: source"), "Reject oversized source before copying"
assert voice.count(".disabled(recording || importingAudio)") == 2, "Do not record and convert while importing"
assert "Task { await importSourceAudio(source) }" in voice
for required in ("canonicalFile.path.hasPrefix(temporaryRoot", "size > 44, size <= 128 * 1024 * 1024",
                 "fileSHA256(canonicalFile)", "(try? self.fileSHA256(sourceAudio.file)) == sourceAudio.sha256",
                 "privateSourceAudio = nil", "Referrer-Policy: no-referrer", "Cache-Control: no-store"):
    assert required in server, required
assert "api.github.com" not in source
print("RVC private audio preflight, nonblocking copy and ephemeral hash-gated handoff source contracts passed; on-device inference remains UNVERIFIED.")
