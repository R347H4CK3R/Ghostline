"""Publish only the 0.4.8 IPA whose native gates and playback source have passed."""
import base64, datetime, hashlib, json, os, pathlib, re, shutil, subprocess, time
from tools.verify_character_kit import verify
from tools.character_package import inspect_ipa
from tools.character_evidence import digest
from tools.sync_verified_release_feeds import updated

REPO = "R347H4CK3R/Ghostline"
VERSION = "0.4.8"
TAG = "voicematrix-v0.4.8"
IPA = "VoiceMatrix-0.4.8.ipa"
# Bound to the fresh 0.4.8 candidate evidence. Every gate is rechecked before
# any publication; no previous release evidence can satisfy these bindings.
CANDIDATE = 'f8cb410be37e4747e180234a37a724c2801ec3ef'
EXPECTED_IPA_SHA256 = '21bd2d6e7ea4f2da1646e50c698f0b62ef3470dfca01670685da73831920b189'
EXPECTED_IPA_BYTES = 731244571
REQUIRED_GATES = (
    ".github/workflows/voicematrix-048-candidate.yml",
    ".github/workflows/character-ui-smoke.yml",
    ".github/workflows/native-app.yml",
    ".github/workflows/native-queue.yml",
    ".github/workflows/native-character-folder.yml",
    ".github/workflows/video-workflow.yml",
    ".github/workflows/queue-processor.yml",
    ".github/workflows/queue-recovery.yml",
)
GATES = {
    ".github/workflows/voicematrix-048-candidate.yml": 43133962680,
    ".github/workflows/character-ui-smoke.yml": 43133962600,
    ".github/workflows/native-app.yml": 43133962569,
    ".github/workflows/native-queue.yml": 43133962462,
    ".github/workflows/native-character-folder.yml": 43133962451,
    ".github/workflows/video-workflow.yml": 43133962551,
    ".github/workflows/queue-processor.yml": 43133962454,
    ".github/workflows/queue-recovery.yml": 43133962455
}
ROOT = pathlib.Path("release-evidence")
NOTES = """VoiceMatrix 0.4.8

Open Video List → Live video workflow to follow actual laptop receipt, waiting and review pauses, preparation, processing stages, checks and failures. The phone records local send attempts and validates laptop acceptance receipts. Views refresh while visible and label stale, unavailable or partial history explicitly.

The authenticated companion /workflow-log page shows the same bounded private timeline. Events record known operations, not raw worker output or invented progress. A successful technical run still requires review. Voice sync is separate: laptop file responses do not prove the phone has imported them, and no per-video-to-phone completion is claimed.

Private video timeline entries are retained in the local queue database with bounded history. No voice names, paths, recordings, transcripts or credentials are copied into these entries. Existing imported voices, queue links, reference safeguards, saved audio, shared models and synthesis settings are preserved. No private or stock profiles are bundled.

This release is published only after fresh same-source package, speech, conversion, native import, iPhone SDK, simulator UI and backend/browser gates pass. Physical iPhone synchronization and character likeness remain unverified.

Replace the existing VoiceMatrix app in Strata and keep its data container; do not delete it first.
"""


def validate_binding(candidate, gates, ipa_sha256, ipa_bytes):
    assert isinstance(candidate, str) and re.fullmatch(r"[0-9a-f]{40}", candidate) and candidate != "0" * 40, "Unbound candidate source; no publication performed"
    assert set(gates) == set(REQUIRED_GATES), "Unbound required gates; no publication performed"
    assert all(type(value) is int and value > 0 for value in gates.values()) and len(set(gates.values())) == len(REQUIRED_GATES), "Unbound or duplicate gate runs; no publication performed"
    assert isinstance(ipa_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", ipa_sha256) and ipa_sha256 != "0" * 64, "Unbound IPA hash; no publication performed"
    assert type(ipa_bytes) is int and ipa_bytes > 0, "Unbound IPA size; no publication performed"


def validate_gate(run, source, workflow):
    assert run["head_sha"] == source, "Required gate tested another source"
    assert run["path"] == workflow, "Required gate used another workflow"
    assert run["repository"]["full_name"] == REPO, "Required gate belongs to another repository"
    assert run["event"] in ("push", "workflow_dispatch"), "Required gate is not a direct source run"
    assert run["status"] == "completed" and run["conclusion"] == "success", "Required gate has not succeeded"


def gh(*args, check=True):
    return subprocess.run(["gh", *args], check=check, capture_output=True, text=True).stdout

def api(path):
    return json.loads(gh("api", path))

def version_key(entry):
    version = tuple(int(x) for x in entry["version"].split("."))
    return (version + (0,) * (4 - len(version)), int(entry.get("buildVersion", "0")))

def validate_tag_target(tagged_object, source):
    assert tagged_object is None or (tagged_object.get("type") == "commit" and tagged_object.get("sha") == source), "Existing release tag targets another source; no publication performed"

def preflight_release_tag(source):
    result = subprocess.run(["gh", "api", f"repos/{REPO}/git/ref/tags/{TAG}"], capture_output=True, text=True)
    if result.returncode:
        error = json.loads(result.stdout)
        assert str(error.get("status")) == "404" and error.get("message") == "Not Found", "Could not verify existing tag; no publication performed"
        validate_tag_target(None, source)
    else:
        validate_tag_target(json.loads(result.stdout)["object"], source)

def validate_published_release(release, tagged_object, source, report):
    assert release["tag_name"] == TAG and not release["draft"] and not release["prerelease"] and release.get("published_at"), "Release is not public and complete"
    assert tagged_object.get("type") == "commit" and tagged_object.get("sha") == source, "Release tag does not target this publication source"
    required = (IPA, IPA + ".sha256", "character-release-verification.json", "dependency-notices.json", "speech-evidence.json", "conversion-result.json")
    for name in required:
        matches = [asset for asset in release["assets"] if asset["name"] == name]
        assert len(matches) == 1 and matches[0]["size"] > 0, "Missing or conflicting published evidence: " + name
    asset = next(asset for asset in release["assets"] if asset["name"] == IPA)
    assert asset["size"] == report["ipaBytes"] and asset.get("digest") == "sha256:" + report["ipaSHA256"], "Published IPA identity differs"

def publication_feed(feed, entry, description):
    result = updated(feed, entry)
    if result != feed:
        app = next(a for a in result["apps"] if a["bundleIdentifier"] == "com.voicematrix.app")
        app["name"] = "VoiceMatrix"
        app["localizedDescription"] = description
    return result

def wait_for_gates():
    validate_binding(CANDIDATE, GATES, EXPECTED_IPA_SHA256, EXPECTED_IPA_BYTES)
    for workflow, run_id in GATES.items():
        deadline = time.monotonic() + 1200
        while True:
            run = api(f"repos/{REPO}/actions/runs/{run_id}")
            if run["status"] == "completed":
                validate_gate(run, CANDIDATE, workflow)
                break
            assert run["head_sha"] == CANDIDATE and run["path"] == workflow, "Pending gate identity differs"
            assert time.monotonic() < deadline, f"Required check still pending: {run_id}"
            time.sleep(20)


def main():
    source = os.environ["GITHUB_SHA"]
    assert os.environ["GITHUB_REPOSITORY"] == REPO
    wait_for_gates()
    subprocess.run(["git", "fetch", "--depth=1", "origin", CANDIDATE], check=True)
    report = verify(ROOT / "ipa", ROOT / "speech", ROOT / "conversion", CANDIDATE, VERSION)
    assert report["ipaSHA256"] == EXPECTED_IPA_SHA256
    assert report["ipaBytes"] == EXPECTED_IPA_BYTES
    candidate = json.loads((ROOT / "candidate/candidate-verification.json").read_text())
    assert candidate["status"] == "candidate-verified-not-published" and candidate["workflowRun"] == GATES[REQUIRED_GATES[0]]
    for key in ("sourceCommit", "inferenceSourceFingerprint", "ipaSHA256", "ipaBytes"):
        assert candidate[key] == report[key], "Candidate artifact verification differs: " + key
    proof = json.loads((ROOT / "ipa/source-proof.json").read_text())
    for path, expected in proof["files"].items():
        content = subprocess.check_output(["git", "show", f"{CANDIDATE}:{path}"])
        assert hashlib.sha256(content).hexdigest() == expected, f"Shipped app differs from tested source: {path}"
        assert hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() == expected, f"Merged app differs from candidate: {path}"
    report.update(publicationSource=source, candidateRun=GATES[REQUIRED_GATES[0]], workflowRun=int(os.environ["GITHUB_RUN_ID"]), playbackTestSource=CANDIDATE,
                  playbackAndUpdaterSimulatorTestsPassed=True, workflowNativeAndBrowserTestsPassed=True, requiredGateRuns=GATES)
    verification = ROOT / "character-release-verification.json"
    verification.write_text(json.dumps(report, indent=2) + "\n")
    public_ipa = ROOT / IPA
    shutil.copyfile(ROOT / f"ipa/VoiceMatrix-{VERSION}-character-test.ipa", public_ipa)
    notes = ROOT / "release-notes.txt"
    notes.write_text(NOTES)
    checksum = ROOT / (IPA + ".sha256")
    checksum.write_text(report["ipaSHA256"] + "  " + IPA + "\n")
    preflight_release_tag(source)
    existing = gh("release", "view", TAG, "--repo", REPO, "--json", "tagName", check=False)
    if not existing:
        gh("release", "create", TAG, str(public_ipa), str(checksum), str(verification),
           str(ROOT / "ipa/dependency-notices.json"),
           str(ROOT / "speech/speech-evidence.json"),
           str(ROOT / "conversion/conversion-evidence/conversion-result.json"),
           "--repo", REPO, "--target", source, "--title", "VoiceMatrix 0.4.8 — live video workflow",
           "--notes-file", str(notes))
    published = ROOT / "published"
    published.mkdir(exist_ok=True)
    release = api(f"repos/{REPO}/releases/tags/{TAG}")
    tagged = api(f"repos/{REPO}/git/ref/tags/{TAG}")["object"]
    validate_published_release(release, tagged, source, report)
    expected_assets = {
        IPA: public_ipa,
        IPA + ".sha256": checksum,
        "character-release-verification.json": verification,
        "dependency-notices.json": ROOT / "ipa/dependency-notices.json",
        "speech-evidence.json": ROOT / "speech/speech-evidence.json",
        "conversion-result.json": ROOT / "conversion/conversion-evidence/conversion-result.json",
    }
    for name, expected in expected_assets.items():
        gh("release", "download", TAG, "--repo", REPO, "-p", name, "-D", str(published), "--clobber")
        assert digest(published / name) == digest(expected), "Published evidence differs: " + name
    assert digest(published / IPA) == report["ipaSHA256"], "Published bytes differ from verified IPA"
    dependency = json.loads((ROOT / "ipa/dependency-notices.json").read_text())["proof"]
    inspect_ipa(published / IPA, dependency_proof=dependency, expected_version=VERSION)
    url = f"https://github.com/{REPO}/releases/download/{TAG}/{IPA}"
    description = "Live private video workflow: verified receipt, real worker stages, waiting/review and failure history. Separate voice sync evidence. Existing private voices/audio, queues and offline engines preserved; no stock voices. Physical iPhone sync remains unverified."
    entry = dict(version=VERSION, buildVersion="1", date=datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
                 downloadURL=url, localizedDescription=description, minOSVersion="26.0",
                 size=report["ipaBytes"], sha256=report["ipaSHA256"])
    feeds = {}
    for name in ("livecontainer-test.json", "source.json", "strata-source.json"):
        current = api(f"repos/{REPO}/contents/{name}?ref=main")
        feed = json.loads(base64.b64decode(current["content"]))
        next_feed = publication_feed(feed, entry, description)
        if next_feed == feed:
            feeds[name] = "already current or newer release preserved"
            continue
        feed = next_feed
        expected_versions = next(x for x in feed["apps"] if x["bundleIdentifier"] == "com.voicematrix.app")["versions"]
        payload = dict(message="Publish verified VoiceMatrix 0.4.8 update feed", branch="main", sha=current["sha"],
                       content=base64.b64encode((json.dumps(feed, indent=2) + "\n").encode()).decode())
        request = ROOT / ("feed-" + name)
        request.write_text(json.dumps(payload))
        gh("api", "--method", "PUT", f"repos/{REPO}/contents/{name}", "--input", str(request))
        fresh = api(f"repos/{REPO}/contents/{name}?ref=main")
        actual = next(x for x in json.loads(base64.b64decode(fresh["content"]))["apps"] if x["bundleIdentifier"] == "com.voicematrix.app")
        assert actual["versions"] == expected_versions
        feeds[name] = "published and read back"
    report.update(status="published-and-redownload-verified", url=url, tag=TAG, feeds=feeds)
    (ROOT / "publication-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
