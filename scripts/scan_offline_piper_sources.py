#!/usr/bin/env python3
"""Revision-pinned discovery of Piper source-card claims for human license review.

Metadata only. No weights downloaded, no automated authorization or device
verification. An upstream dataset-license claim is not voice-identity consent.
"""
import concurrent.futures
import json
import urllib.request
from urllib.parse import quote

REV = "c10ece1aade47bb51c153c893d14e5bf8e5b7117"
BASE = "https://huggingface.co"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Ghostline-source-review/1"})
    with urllib.request.urlopen(req, timeout=40) as response:
        return response.read()

def tree(path="", recursive=False):
    option="?recursive=true" if recursive else ""
    return json.loads(get(f"{BASE}/api/models/rhasspy/piper-voices/tree/{REV}/{path}{option}"))

def inspect(path):
    try:
        card = get(f"{BASE}/rhasspy/piper-voices/resolve/{REV}/{quote(path)}").decode("utf-8")
    except Exception as exc:
        return (path, "UNAVAILABLE", str(exc)[:60])
    rows = [r.strip() for r in card.splitlines()]
    licenses = [r.split(":",1)[1].strip() for r in rows if r.lower().startswith("* license:")]
    lineage = [r for r in rows if "trained from scratch" in r.lower() or "finetuned" in r.lower()]
    if not licenses:
        return None
    if not any("cc0" in v.lower() or "public domain" in v.lower() for v in licenses):
        return None
    return (path, " / ".join(licenses), " ".join(lineage)[:140])

def main():
    families = [x["path"] for x in tree() if x["type"] == "directory" and not x["path"].startswith("_")]
    all_cards = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(tree, family, True): family for family in families}
        for future in concurrent.futures.as_completed(futures):
            try: all_cards.extend(x["path"] for x in future.result() if x["path"].endswith("/MODEL_CARD"))
            except Exception as exc: print("FAMILY UNAVAILABLE", futures[future], str(exc)[:100])
    print(f"Inspected {len(families)} families; discovered {len(all_cards)} model cards at {REV}", flush=True)
    approved = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        for result in pool.map(inspect, sorted(set(all_cards))):
            if result:
                approved.append(result)
                if "Trained from scratch" in result[-1] or "trained from scratch" in result[-1]:
                    print("SCRATCH", *result, sep=" | ", flush=True)
    print("CLAIMED CC0/PUBLIC DOMAIN CARDS", len(approved), flush=True)
    for r in approved:
        if "Finetuned" in r[-1] or "finetuned" in r[-1]:
            print("DERIVATIVE_REVIEW_ONLY", *r, sep=" | ", flush=True)

if __name__ == "__main__":
    main()
