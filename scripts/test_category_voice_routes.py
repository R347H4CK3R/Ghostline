#!/usr/bin/env python3
"""Prevent empty categories, false identity verification and broken TTS wiring."""
from pathlib import Path
import json, re

source = Path("Ghostline/CategorizedVoiceLibrary.swift").read_text()
app = Path("Ghostline/App.swift").read_text()
manifest = json.loads(Path("Ghostline/Resources/approved-piper-bundle.json").read_text())
packs = {p["id"] for p in manifest["models"]}
expected = ["film", "television", "cartoons", "anime",
            "gaming", "singers", "celebrities", "original"]
for category in expected:
    pattern = r'\.init\(id: "' + re.escape(category) + r'", title:.*?modelIDs: \[(.*?)\]'
    found = re.search(pattern, source, re.S)
    assert found, category + " missing"
    ids = re.findall(r'"([^"]+)"', found.group(1))
    assert ids and all(i in packs for i in ids), (category, ids)
assert "NavigationStack { GhostlineUSVoiceLibrary() }" in app
assert "await studio.generate(words)" in source
assert "studio.replaySavedWAV()" in source
assert "GhostlineVoiceChangerView()" in source
assert "0 target-iPhone identity-verified voices" in source
assert "not authentic entertainment or performer replicas" in source
print("All 8 category routes backed by actual packaged Piper model IDs; no false verified claims.")
