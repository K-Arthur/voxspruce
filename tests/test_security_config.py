import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GitHubWorkflowSecurityTests(unittest.TestCase):
    def test_ci_token_is_read_only_and_checkout_does_not_persist_credentials(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read\n", workflow)
        self.assertRegex(
            workflow,
            r"uses: actions/checkout@[0-9a-f]{40} # v[0-9.]+\n\s+with:\n\s+persist-credentials: false",
        )
        self.assertRegex(
            workflow,
            r"uses: actions/upload-artifact@[0-9a-f]{40} # v[0-9.]+",
        )

    def test_desktop_application_is_single_instance(self):
        app = (ROOT / "src/wayland_voice_control/app.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("ApplicationFlags.NON_UNIQUE", app)


if __name__ == "__main__":
    unittest.main()
