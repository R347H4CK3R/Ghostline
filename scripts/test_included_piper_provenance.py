#!/usr/bin/env python3
"""Check American-English model source integrity and unverified voice status.

Static checks do NOT establish offline iPhone audio, perceptual accent, or identity.
"""
import json
import re
from pathlib import Path

catalog = json.loads(Path("Ghostline/Resources/approved-piper-bundle.json").read_text())
assert catalog["schema_version"] == 1
assert catalog["verified_identity_count"] == 0 == catalog["device_verified_audio_count"]
assert catalog["distribution_scope"] == "experimental unsigned IPA artifact only; not a public release"
by_id = {m["id"]: m for m in catalog["models"]}
expected = {"en_US-ljspeech-medium", "en_US-kristin-medium", "en_US-norman-medium", "en_US-john-medium"}
assert set(by_id) == expected, "Non-US model cannot enter American-only IPA"
revision = catalog["source_revision"]
assert re.fullmatch("[a-f0-9]{40}", revision)
for p in by_id.values():
    assert p["language"] == "en_US"
    assert p["device_status"] == "UNVERIFIED_CANDIDATE"
    assert p["claimed_real_person_identity"] is None
    assert p["dataset_license"] in {"public domain", "CC0", "CC0 1.0 Universal"}
    assert p["speaker_ids"] == list(range(len(p["speaker_ids"]))) and p["speaker_ids"]
    assert p["model_card_url"].startswith("https://huggingface.co/rhasspy/piper-voices/blob/" + revision + "/")
    review = p["rights_review"]
    assert review["decision"] == "SOURCE_DOCUMENTED_EXPERIMENTAL_ONLY"
    assert review["identity_permissions_independently_verified"] is False
    assert review["device_generation_verified"] is False
    assert {f["name"] for f in p["files"]} == {"model.onnx", "model.onnx.json", "MODEL_CARD"}
    for file in p["files"]:
        assert file["size"] > 0
        assert re.fullmatch("[a-f0-9]{64}", file["sha256"])
        assert ".." not in file["upstream_path"]
    if p["id"] == "en_US-john-medium":
        assert p["parent_model_id"] == "en_US-kristin-medium"
        assert "Finetuned from" in p["training_lineage"]
        assert p["rights_review"]["parent_model_source_url"] == by_id["en_US-kristin-medium"]["model_card_url"]
    else:
        assert p.get("parent_model_id") is None
        assert "Trained from scratch" in p["training_lineage"]
quarantine = json.loads(Path("Ghostline/Resources/quarantined-piper-candidates.json").read_text())
assert quarantine["schema_version"] == 1
assert quarantine["source_revision"] == revision
assert {p["id"] for p in quarantine["models"]}.isdisjoint(by_id)
assert any(p["id"] == "sv_SE-nst-medium" for p in quarantine["models"])

tts = Path("Ghostline/PiperIncludedVoiceStudio.swift").read_text()
assert "speakerId: Int32(selectedSpeakerID)" in tts
assert '"speaker_slot_unverified": true' in tts
assert "func selectSpeaker(_ id: Int)" in tts
assert "func replaySavedWAV()" in tts
assert "func exportEvidence()" in tts
assert '"airplane_mode_confirmed": false' in tts
print("American-English source audit: four model candidates, all pinned, no identity/device verification claims.")
