#!/usr/bin/env python3
"""Regression checks for reconstructed five-tab American-English UI.

This validates catalog wiring, not runtime audio or perceptual accent.
"""
import json
from pathlib import Path

app = Path("Ghostline/App.swift").read_text()
studio = Path("Ghostline/AmericanStudio.swift").read_text()
manifest = json.loads(Path("Ghostline/Resources/approved-piper-bundle.json").read_text())
us = [m for m in manifest["models"] if m["language"] == "en_US" and m["id"].startswith("en_US-")]
assert len(us) == 5
assert len({m["id"] for m in us}) == len(us)
assert all(m["device_status"] == "UNVERIFIED_CANDIDATE" for m in us)
assert all(m["claimed_real_person_identity"] is None for m in us)

tabs = ('Label("Studio",', 'Label("Voices",', 'Label("Changer",',
        'Label("Downloads",', 'Label("Settings",')
assert app.count(".tabItem") == 5
assert all(token in app for token in tabs)
assert "GhostlineAmericanDashboard()" in app
assert "GhostlineUSVoiceLibrary()" in app
assert "GhostlineAmericanDownloads()" in app
assert "GhostlineAmericanSettings()" in app
assert "GhostlineVoiceChangerView()" in app

assert '$0.language == "en_US"' in studio
assert '$0.id.hasPrefix("en_US-")' in studio
assert 'ForEach(GhostlineUSVoices.all)' in studio
assert 'await studio.generate(phrase)' in studio
assert "studio.replaySavedWAV()" in studio
assert "studio.attestListening()" in studio
assert "studio.exportEvidence()" in studio
assert "GhostlineCommunityVoicesView()" in studio
assert '0 iPhone audio-verified voices' in studio
assert "not a licensed film-character voice" in studio
assert "not a replica of a celebrity" in studio
assert "not supported by Piper" in studio
assert studio.count('.init(id: "') == 8

assert {m["id"] for m in us} == {"en_US-ljspeech-medium","en_US-ljspeech-high","en_US-kristin-medium","en_US-john-medium","en_US-norman-medium"}
print(f"PASS: American-only Studio, {len(us)} model variants, 4 speaker identities, 0 device-verified voices.")
