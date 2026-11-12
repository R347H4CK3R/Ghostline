"""Run the real workflow model checks wherever a Swift compiler is available."""
import json
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class VideoWorkflowWiringTests(unittest.TestCase):
    def test_native_workflow_contract(self):
        sources = [ROOT / "VoiceMatrix/VideoWorkflow.swift",
                   ROOT / "tests/native/VideoWorkflowChecks.swift"]
        for path in sources:
            self.assertTrue(path.is_file(), f"Missing workflow implementation: {path.name}")
        compiler = shutil.which("swiftc")
        if not compiler:
            self.skipTest("Swift compiler unavailable; native workflow checks require Apple CI or Swift")
        with tempfile.TemporaryDirectory() as directory:
            binary = pathlib.Path(directory) / "workflow-checks"
            subprocess.run([compiler, "-parse-as-library", *map(str, sources), "-o", str(binary)],
                           check=True, capture_output=True, text=True, timeout=120)
            from tools.video_queue import VideoQueue
            from tools.workflow_activity import snapshot
            database = pathlib.Path(directory) / "queue.db"
            queue = VideoQueue(database)
            try:
                queue.add(["https://youtu.be/EAT0nWoEzJ8"])
            finally:
                queue.close()
            fixtures = []
            for name, selection in [("overview", None), ("selected", "EAT0nWoEzJ8")]:
                fixture = pathlib.Path(directory) / (name + ".json")
                fixture.write_text(json.dumps(snapshot(database, selection)))
                fixtures.append(str(fixture))
            result = subprocess.run([str(binary), *fixtures], check=True, capture_output=True, text=True, timeout=30)
            self.assertIn("Workflow checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
