#!/usr/bin/env python3
"""Static source/provenance check. NOT proof of device inference or listening."""
import json
import re
from pathlib import Path
catalog=json.loads(Path("Ghostline/Resources/approved-piper-bundle.json").read_text(encoding="utf-8"))
assert catalog["verified_identity_count"] == 0 == catalog["device_verified_audio_count"]
assert catalog["distribution_scope"].startswith("experimental unsigned IPA")
assert len(catalog["models"]) >= 7
assert len({p["id"] for p in catalog["models"]}) == len(catalog["models"])
assert sum(len(p["speaker_ids"]) for p in catalog["models"]) >= 9
rev=catalog["source_revision"]
for p in catalog["models"]:
    assert re.fullmatch(r"[a-z]{2}_[A-Z]{2}-[a-z0-9_]+-(?:x_low|low|medium|high)",p["id"])
    assert p["claimed_real_person_identity"] is None and p["device_status"]=="UNVERIFIED_CANDIDATE"
    assert p["dataset_license"] in ("public domain","CC0","CC0 1.0 Universal")
    assert p["speaker_ids"] == list(range(len(p["speaker_ids"]))) and p["speaker_ids"]
    assert p["model_card_url"].startswith("https://huggingface.co/rhasspy/piper-voices/blob/"+rev+"/")
    assert {f["name"] for f in p["files"]} == {"model.onnx","model.onnx.json","MODEL_CARD"}
    for f in p["files"]:
        assert f["size"]>0 and re.fullmatch(r"[0-9a-f]{64}",f["sha256"])
        assert f["upstream_path"] and ".." not in f["upstream_path"]
by_id={p["id"]:p for p in catalog["models"]}
assert by_id["nl_BE-rdh-medium"]["dataset_license"]=="CC0 1.0 Universal"
assert by_id["uk_UA-ukrainian_tts-medium"]["speaker_ids"]==[0,1,2]
# November 6 expansion: source-declared slots are candidate IDs, never target-device proof.
for key in ("no_NO-nvcc-medium", "nl_BE-nathalie-x_low", "sv_SE-nst-medium"):
    item=by_id[key]
    assert item["device_status"]=="UNVERIFIED_CANDIDATE"
    assert item["dataset_license"]=="CC0"
    assert item["dataset_source_url"].startswith("https://")
    assert "Trained from scratch" in item["training_lineage"]
    assert item["claimed_real_person_identity"] is None
assert by_id["no_NO-nvcc-medium"]["speaker_ids"]==list(range(10))
assert by_id["nl_BE-nathalie-x_low"]["speaker_ids"]==[0]
assert by_id["sv_SE-nst-medium"]["speaker_ids"]==[0]
# The original Swedish model card mislinks NST dictation sbr-17.
# KBLab's first-party model report instead references TTS corpus sbr-18.
sv = by_id["sv_SE-nst-medium"]
assert sv["dataset_source_url"] == "https://kb-labb.github.io/posts/2023-05-24-swedish-text-to-speech/"
assert sv["dataset_historical_catalogue_url"].endswith("/oai-nb-no-sbr-18/")
assert "sbr-17" in sv["dataset_provenance_note"] and "sbr-18" in sv["dataset_provenance_note"]
assert "source-reported" in sv["dataset_provenance_note"].lower()
source=Path("Ghostline/PiperIncludedVoiceStudio.swift").read_text()
assert "speakerId: Int32(selectedSpeakerID)" in source
assert '"speaker_id": selectedSpeakerID' in source
assert '"speaker_slot_unverified": true' in source
assert "func selectSpeaker(_ id: Int)" in source
reset=source.split("func selectSpeaker(_ id: Int)",1)[1].split("private func packDirectory",1)[0]
for marker in ("outputURL = nil","evidenceURL = nil","playbackCompleted = false","userAttestedListening = false"):
    assert marker in reset
assert "0 voice identities verified" in source
print(f"Provenance: {len(catalog['models'])} unverified model packs; {sum(len(p['speaker_ids']) for p in catalog['models'])} candidate speaker slots; 0 verified device voices.")
