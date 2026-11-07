"""Validate that three-provider discovery metadata cannot be mistaken for voice assets."""
import json
from pathlib import Path

path = Path("Ghostline/Resources/three-source-catalog.json")
catalog = json.loads(path.read_text(encoding="utf-8"))
assert catalog["schema_version"] == 1
assert catalog["catalog_scope"] == "discovery_metadata_only"
items = catalog["entries"]
assert len(items) >= 100, "Discovery snapshot unexpectedly empty"
providers = {x["provider"] for x in items}
assert providers == {"aivoices","huggingface","openvoice"}, providers
assert len({x["url"] for x in items}) == len(items)
allowed = {"Music & Singers","Movies & Film","Animation & Cartoons","Anime",
           "Games","Celebrities & Actors","Original & Synthetic","Other / Unclassified"}
for x in items:
    assert x["category"] in allowed
    assert x["availability"] == "discovery_only_unverified"
    assert x["downloaded"] is False
    assert x["device_verified"] is False
    assert x["identity_verified"] is False
    assert x["redistribution_rights_verified"] is False
    assert x["url"].startswith("https://")
openvoice = [x for x in items if x["provider"]=="openvoice"]
assert len(openvoice)==1 and "engine" in openvoice[0]["name"].lower()
source=Path("Ghostline/ThreeSourceVoiceCatalog.swift").read_text(encoding="utf-8")
assert "GhostlineSourceSnapshot" in source
assert "discovery_only_unverified" in path.read_text(encoding="utf-8")
assert "0 newly iPhone-verified voices" in source
app=Path("Ghostline/App.swift").read_text()
assert "GhostlineThreeSourceCatalogView()" in app
print(f"Three-source offline catalog passed: {len(items)} unverified metadata entries")
