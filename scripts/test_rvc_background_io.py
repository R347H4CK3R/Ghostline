#!/usr/bin/env python3
"""Static regression guards for RVC candidate imports on the SwiftUI MainActor.

This is NOT an iPhone runtime test or proof of audio inference.
The iOS Actions job compiles the actual Swift 6 app after this test.
"""
from pathlib import Path

source = Path("Ghostline/RVCPackLibrary.swift").read_text(encoding="utf-8")
faiss = Path("Ghostline/RVCIndexInspector.swift").read_text(encoding="utf-8")
def section(start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]

assert "@MainActor" in source
for function, end in [
    ("func importWeights(_ source: URL, name: String, category: String, rights: String) async", "// Never overwrite the existing retrieval index"),
    ("func attachIndex(_ source: URL, for packID: UUID) async", "// JSON contains metadata"),
    ("func audit(_ pack: RVCPackRecord) async", "private func saveIndex() throws")
]:
    body = section(function, end)
    assert "busy = true" in body and "defer { busy = false }" in body, function
    assert "try await Task.detached(priority: .userInitiated)" in body, function
    assert body.index("busy = true") < body.index("try await Task.detached"), function
    assert any(term in body for term in ("UNVERIFIED", "not been verified", "not establish usable", "Retrieval inference remains unavailable")), function

assert "nonisolated private static func digest(" in source
assert "nonisolated private static func copyFromPicker(" in source
assert "source.startAccessingSecurityScopedResource()" in source
assert "defer { if permitted { source.stopAccessingSecurityScopedResource() } }" in source
assert 'try Self.digest(target)' in source
assert 'Task { await library.importWeights(url, name: name, category: category, rights: rights) }' in source
assert 'Task { await library.attachIndex(url, for: pack) }' in source
assert 'Task { await library.audit(pack) }' in source
assert 'struct Header: Sendable' in faiss
assert "GhostlineRVCIndexInspector.inspect(target)" in source
assert "packs[idx] = previous" in source
assert '"index_retrieval_inference_supported": false' in source
assert '"model_inference_on_iphone_verified": false' in source
assert '"voice_identity_verified": false' in source
print("RVC async copy/SHA, FAISS inspection, rollback and unverified-evidence contracts passed")
