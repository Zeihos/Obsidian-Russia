"""Regression checks for the repository entrypoints and documentation."""
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "Сайт/README.md",
    "Форум/README.md",
    "Вики/README.md",
    "design/README.md",
    "game/README.md",
    "docs/DEPLOYMENT.md",
    "docs/ROADMAP.md",
    "docs/SSO.md",
]
MARKDOWN_LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]+)\)")
HTML_LINK = re.compile(r"""(?:src|href)=["']([^"']+)["']""")


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class MaintenanceTest(unittest.TestCase):
    def test_internal_documentation_links(self):
        for rel in DOCS:
            document = ROOT / rel
            with self.subTest(doc=rel):
                self.assertTrue(document.is_file(), rel)
                text = document.read_text(encoding="utf-8")
                for raw in MARKDOWN_LINK.findall(text) + HTML_LINK.findall(text):
                    if raw.startswith(("#", "http:", "https:", "mailto:")):
                        continue
                    url = urlsplit(raw)
                    if url.scheme or url.netloc or not url.path:
                        continue
                    path = (document.parent / unquote(url.path)).resolve()
                    self.assertTrue(path.is_relative_to(ROOT.resolve()), f"{rel}: outside repository: {raw}")
                    self.assertTrue(path.exists(), f"{rel}: missing link: {raw}")

    def test_diagnostics_pass_with_unused_ports(self):
        ports = [free_port() for _ in range(3)]
        while len(set(ports)) != 3:
            ports = [free_port() for _ in range(3)]
        env = os.environ.copy()
        env.update({
            "OBSIDIAN_PORT": str(ports[0]),
            "OBFORUM_PORT": str(ports[1]),
            "OBWIKI_PORT": str(ports[2]),
        })
        result = subprocess.run(
            [sys.executable, "dev.py", "doctor"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[OK] site", result.stdout)
        self.assertIn("[OK] forum", result.stdout)
        self.assertIn("[OK] wiki", result.stdout)

    def test_diagnostics_catch_duplicate_port(self):
        env = os.environ.copy()
        selected = str(free_port())
        env.update({
            "OBSIDIAN_PORT": selected,
            "OBFORUM_PORT": selected,
            "OBWIKI_PORT": str(free_port()),
        })
        result = subprocess.run(
            [sys.executable, "dev.py", "doctor"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=20,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[ERROR] forum", result.stdout)


if __name__ == "__main__":
    unittest.main()
