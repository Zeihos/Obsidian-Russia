"""Repository guardrails: don't publish generated databases or runtime state."""
import subprocess
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryHygieneTest(unittest.TestCase):
    def test_no_generated_state_is_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        files = [x.decode("utf-8", "surrogateescape") for x in result.stdout.split(b"\x00") if x]
        offenders = []
        for name in files:
            norm = name.replace("\\", "/")
            parts = norm.split("/")
            base = parts[-1].lower()
            if (
                "__pycache__" in parts
                or ".runtime" in parts
                or "data" in parts
                or ("static" in parts and "uploads" in parts)
                or base.endswith((".pyc", ".pyo", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm", ".db"))
                or (base.startswith(".env") and base != ".env.example")
                or (len(parts) == 1 and base.endswith((".rar", ".zip", ".jpg", ".png")))
            ):
                offenders.append(name)
        self.assertEqual([], offenders, "Private or misplaced generated files committed to Git: " + ", ".join(offenders))

    def test_expected_project_layout(self):
        for path in [
            "Сайт/server.py",
            "Форум/app.py",
            "Вики/app.py",
            "dev.py",
            "game/README.md",
            "design/README.md",
            "docs/SSO.md",
            "docs/DEPLOYMENT.md",
        ]:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
