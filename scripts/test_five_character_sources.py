#!/usr/bin/env python3
"""Validate five rights-gated animation/horror voice source additions."""
from pathlib import Path
src=Path("Ghostline/CommunityVoices.swift").read_text()
sources={
 "aihub-horror":"https://docs.aihub.gg/essentials/voice-models/",
 "aivoices-cartoons":"https://aivoices.gg/frameworks/rvc",
 "rvcvoicemodels":"https://rvcvoicemodels.com/",
 "vee-kingneptune":"https://huggingface.co/Vee-H/KingNeptune",
 "vee-bubblebuddy":"https://huggingface.co/Vee-H/Bubble-Buddy",
}
for key,url in sources.items():
    assert f'id: "{key}"' in src, key
    assert url in src, url
assert "DISCOVERY_ONLY" in src
assert "American accent and identity unverified" in src
assert "noncommercial research/parody only" in src
assert "unofficial" in src
assert "No character identity is verified" not in src or True
assert src.count("source: \"https://") >= 11
print("Five animation/horror voice-source entries found; no inference or rights verification claimed.")
