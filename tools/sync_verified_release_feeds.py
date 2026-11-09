"""Keep all installation feeds on the newest proven public release; never publish releases."""
import argparse, base64, copy, hashlib, json, pathlib, re, subprocess, tempfile, zipfile
from tools.character_package import inspect_ipa, PREFIX
REPO = "R347H4CK3R/Ghostline"
FEEDS = ("livecontainer-test.json", "source.json", "strata-source.json")

def gh(*args):
    return subprocess.check_output(["gh", *args], text=True)

def api(path):
    return json.loads(gh("api", f"repos/{REPO}/{path}"))

def key(version, build="0"):
    assert re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,3}", version), "Invalid version"
    assert re.fullmatch(r"[0-9]+", str(build)), "Invalid build"
    parts = tuple(map(int, version.split(".")))
    return parts + (0,) * (4-len(parts)) + (int(build),)

def updated(feed, entry):
    result = copy.deepcopy(feed)
    apps = [a for a in result["apps"] if a["bundleIdentifier"] == "com.voicematrix.app"]
    assert len(apps) == 1
    app = apps[0]
    target = key(entry["version"], entry["buildVersion"])
    versions = app["versions"]
    if any(key(v["version"], v.get("buildVersion", "0")) > target for v in versions):
        return feed
    same = [v for v in versions if key(v["version"], v.get("buildVersion", "0")) == target]
    for v in same:
        assert all(v.get(k) == entry[k] for k in ("downloadURL", "size", "sha256")), "Conflicting release identity"
    if same and versions[0] == same[0]:
        return feed
    app["versions"] = [same[0] if same else entry] + [v for v in versions if v not in same]
    return result

def validate(report, release, run, jobs, asset, candidate=None):
    i = report["inspection"]
    assert not release["draft"] and not release["prerelease"]
    key(i["version"], i["build"])
    assert i["archive"] == "passed" and i["bundleIdentifier"] == "com.voicematrix.app"
    assert i["stockProfiles"] == 0 and report["bundledCharacterProfiles"] == 0
    assert all(report.get(k) is True for k in ("nativeDiagnosticSpeechPassed", "nativeSimulatorConversionPassed", "playbackAndUpdaterSimulatorTestsPassed"))
    assert run["status"] == "completed" and run["conclusion"] == "success"
    if "candidateRun" in report:
        assert run["head_sha"] == report["publicationSource"]
        assert {j["name"] for j in jobs if j["conclusion"] == "success"} >= {"publish"}
        assert candidate is not None, "Missing candidate run evidence"
        prior, prior_jobs = candidate
        assert prior["id"] == report["candidateRun"]
        assert prior["status"] == "completed" and prior["conclusion"] == "success"
        assert prior["head_sha"] == report["sourceCommit"]
        assert {j["name"] for j in prior_jobs if j["conclusion"] == "success"} >= {"resolve", "ipa", "speech", "conversion", "verify"}
    else:
        assert run["head_sha"] == report["sourceCommit"]
        assert {j["name"] for j in jobs if j["conclusion"] == "success"} >= {"resolve", "ipa", "speech", "conversion", "publish"}
    assert re.fullmatch(r"[a-f0-9]{64}", report["ipaSHA256"])
    assert asset["size"] == report["ipaBytes"] and 0 < asset["size"] < 2_000_000_000
    assert asset["digest"] == "sha256:" + report["ipaSHA256"]
    assert re.fullmatch(r"VoiceMatrix-[0-9.]+\.ipa", asset["name"])
    assert asset["browser_download_url"] == f'https://github.com/{REPO}/releases/download/{release["tag_name"]}/{asset["name"]}'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    candidates = []
    page = 1
    while True:
        releases = api(f"releases?per_page=100&page={page}")
        for release in releases:
            match = re.fullmatch(r"voicematrix-v([0-9]+(?:\.[0-9]+){1,3})", release["tag_name"])
            if match and not release["draft"] and not release["prerelease"] and any(a["name"] == "character-release-verification.json" for a in release["assets"]):
                candidates.append((key(match[1]), release))
        if len(releases) < 100:
            break
        page += 1
    assert candidates, "No verified release candidate; feeds preserved"
    release = max(candidates, key=lambda x: x[0])[1]
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        for pattern in ("character-release-verification.json", "dependency-notices.json", "*.ipa"):
            gh("release", "download", release["tag_name"], "--repo", REPO, "--pattern", pattern, "--dir", directory)
        report = json.loads((root/"character-release-verification.json").read_text())
        assets = [a for a in release["assets"] if a["name"].endswith(".ipa")]
        assert len(assets) == 1
        asset = assets[0]
        run = api(f'actions/runs/{int(report["workflowRun"])}')
        jobs = api(f'actions/runs/{int(report["workflowRun"])}/jobs?per_page=100')["jobs"]
        candidate = None
        if "candidateRun" in report:
            candidate_id = int(report["candidateRun"])
            candidate = (api(f"actions/runs/{candidate_id}"), api(f"actions/runs/{candidate_id}/jobs?per_page=100")["jobs"])
        validate(report, release, run, jobs, asset, candidate)
        assert api(f'commits/{release["tag_name"]}')["sha"] == report.get("publicationSource", report["sourceCommit"])
        ipa = root/asset["name"]
        with ipa.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == report["ipaSHA256"]
        notices = json.loads((root/"dependency-notices.json").read_text())
        inspection = inspect_ipa(ipa, dependency_proof=notices["proof"], expected_version=report["inspection"]["version"])
        assert inspection == report["inspection"]
        with zipfile.ZipFile(ipa) as archive:
            proof = json.loads(archive.read(PREFIX+"VoiceMatrix-Source-Proof.json"))
            assert proof["sourceCommit"] == report["sourceCommit"]
            assert proof["inferenceSourceFingerprint"] == report["inferenceSourceFingerprint"]
        entry = dict(version=inspection["version"], buildVersion=inspection["build"],
                     date=release["published_at"][:10], downloadURL=asset["browser_download_url"],
                     localizedDescription="Verified native release. Physical iPhone sound and character likeness require device testing.",
                     minOSVersion="26.0", size=asset["size"], sha256=report["ipaSHA256"])
        for name in FEEDS:
            current = api(f"contents/{name}?ref=main")
            feed = json.loads(base64.b64decode(current["content"]))
            result = updated(feed, entry)
            if result == feed:
                print(name + ": current or newer; preserved")
                continue
            if not args.write:
                print(name + ": verified update ready (read-only)")
                continue
            request = root/"request.json"
            request.write_text(json.dumps(dict(message=f'Sync verified VoiceMatrix {entry["version"]} feed', branch="main", sha=current["sha"],
                content=base64.b64encode((json.dumps(result, indent=2)+"\n").encode()).decode())))
            gh("api", "--method", "PUT", f"repos/{REPO}/contents/{name}", "--input", str(request))
            assert json.loads(base64.b64decode(api(f"contents/{name}?ref=main")["content"])) == result
            print(name + ": updated and read back")
        print("Verified published IPA SHA-256: " + report["ipaSHA256"])

if __name__ == "__main__":
    main()
