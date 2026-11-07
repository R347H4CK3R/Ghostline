#!/usr/bin/env python3
"""Build a bounded, auditable, metadata-only snapshot from three public voice sources.
No third-party voice weights, speech clips or gated artifacts are downloaded.
Entries are DISCOVERY_ONLY until source rights and iPhone inference are verified.
"""
import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://aivoices.gg"
HF = "https://huggingface.co"
HEADERS = {"User-Agent": "GhostlineCatalogResearch/1.0 (metadata-only; contact via GitHub)"}
CATEGORIES = [
    ("Music & Singers", ("singer","music","rapper","song","vocal","eminem","celine","adele","rhymes","madonna","drake","beyonce","taylor","artist")),
    ("Movies & Film", ("film","movie","star wars","iron man","darth","joker","batman","marvel","dc comic","venom","godfather","terminator")),
    ("Animation & Cartoons", ("cartoon","spongebob","simpson","family guy","mickey","looney","pokemon","shrek","scooby")),
    ("Anime", ("anime","naruto","one piece","dragon ball","genshin","hatsune","jojo","azur lane","arknights")),
    ("Games", ("game","gaming","overwatch","mgs","halo","call of duty","fnaf","minecraft","mario","sonic","zelda","elden","mordekaiser","bloons")),
    ("Celebrities & Actors", ("actor","celebrity","comedian","host","president","narrator","freeman","rhames")),
    ("Original & Synthetic", ("original","synthetic","test voice","ljspeech","piper","kokoro")),
]

def classify(title, label=""):
    t = (title + " " + label).lower()
    for category, needles in CATEGORIES:
        if any(x in t for x in needles):
            return category
    return "Other / Unclassified"

def get(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=35) as response:
        return response.read()

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.current = None
        self.found = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith("/models/") and not href.startswith("/models/?"):
                self.current = [href, []]
    def handle_data(self, data):
        if self.current is not None:
            self.current[1].append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            href, words = self.current
            label = " ".join(" ".join(words).split())
            self.found.append((href, label))
            self.current = None

def source_item(provider, name, url, engine, category, license_name="unknown", description=""):
    return {
        "id": provider + ":" + hashlib_key(url),
        "provider": provider,
        "name": name[:160],
        "category": category,
        "engine": engine,
        "license": license_name,
        "url": url,
        "summary": description[:220],
        "availability": "discovery_only_unverified",
        "downloaded": False,
        "device_verified": False,
        "identity_verified": False,
        "redistribution_rights_verified": False
    }

def hashlib_key(text):
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:16]

def aivoices(pages):
    items = []
    for page in range(1, pages + 1):
        try:
            url = BASE + "/models" + (f"?page={page}" if page > 1 else "")
            parser = Links()
            parser.feed(get(url).decode("utf-8", errors="replace"))
            found = 0
            for href, text in parser.found:
                # The directory links to model details; they are not downloadable files.
                cleaned = re.split(r"\bView model\b|\bDownload and source details\b", text)[0]
                cleaned = html.unescape(cleaned).strip()
                cleaned = re.sub(r"\s+(RVC|GPT-SoVITS|so-vits-svc).*", "", cleaned, flags=re.I).strip() or cleaned
                if not cleaned: continue
                absolute = urllib.parse.urljoin(BASE, href)
                items.append(source_item("aivoices", cleaned, absolute, "RVC / community model",
                    classify(cleaned), "source review required", "External model directory; model rights and identity permission not established."))
                found += 1
            print("AIVoices page", page, "entries", found, flush=True)
            if found == 0: break
        except Exception as exc:
            print("AIVoices page error", page, str(exc)[:100], flush=True)
            if page == 1: raise
            break
    return items

def huggingface(limit):
    items = []
    for query in (
        {"pipeline_tag":"text-to-speech", "limit":str(limit), "sort":"downloads", "direction":"-1"},
        {"search":"rvc", "limit":str(limit), "sort":"downloads", "direction":"-1"},
    ):
        try:
            payload = json.loads(get(HF + "/api/models?" + urllib.parse.urlencode(query)))
            for item in payload:
                repo = item.get("id")
                if not repo or "/" not in repo: continue
                card = item.get("cardData") or {}
                license_name = card.get("license") or "not declared"
                if isinstance(license_name, list): license_name = ", ".join(map(str, license_name))
                tags = item.get("tags") or []
                if not isinstance(tags, list): tags = []
                engine = ("RVC" if "rvc" in (repo + " ".join(tags)).lower() else
                          "TTS / voice model")
                items.append(source_item("huggingface", repo, HF + "/" + repo, engine,
                    classify(repo, " ".join(map(str,tags))), str(license_name),
                    "Hub metadata only; license labels do not establish performer voice consent."))
            print("Hugging Face query", query, "entries", len(payload), flush=True)
        except Exception as exc:
            print("Hugging Face query error", str(exc)[:150], flush=True)
    return items

def build(pages, limit):
    discovered = aivoices(pages) + huggingface(limit)
    discovered.append(source_item("openvoice", "MyShell OpenVoice V2 (engine, not celebrity voice pack)",
        HF + "/myshell-ai/OpenVoiceV2", "OpenVoice V2 cloning engine", "Original & Synthetic",
        "MIT", "A voice-cloning engine; real speaker identities are not bundled or licensed by engine availability."))
    seen = set()
    distinct = []
    for record in discovered:
        if record["url"] in seen: continue
        seen.add(record["url"])
        distinct.append(record)
    return {"schema_version":1,"generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "catalog_scope":"discovery_metadata_only",
        "aivoices_reported_directory_size_at_review":25657,
        "warning":"Entries are not included voices, not downloadable rights grants, and not functional iPhone voice claims.",
        "providers":{"aivoices":"https://aivoices.gg/models",
                     "huggingface":"https://huggingface.co/models",
                     "openvoice":"https://huggingface.co/myshell-ai/OpenVoiceV2"},
        "entries":distinct}

if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--aivoices-pages", type=int, default=12)
    ap.add_argument("--hf-per-query", type=int, default=150)
    ap.add_argument("--output", default="Ghostline/Resources/three-source-catalog.json")
    args=ap.parse_args()
    result=build(args.aivoices_pages,args.hf_per_query)
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":")) + "\n")
    print("Metadata-only unique entries:",len(result["entries"]))
