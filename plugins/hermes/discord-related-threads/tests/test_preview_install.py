from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts import install_preview


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", root, *arguments),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", ".")
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD")


class PreviewInstallTest(unittest.TestCase):
    def test_default_live_profile_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            hermes_root = Path(temporary) / "hermes"
            hermes_root.mkdir()
            with self.assertRaisesRegex(
                install_preview.PreviewInstallError, "default live"
            ):
                install_preview.validate_preview_home(
                    Path.home() / ".hermes", hermes_root=hermes_root
                )

    def test_plugin_ref_requires_a_full_sha(self):
        with self.assertRaisesRegex(
            install_preview.PreviewInstallError, "40-character"
        ):
            install_preview.resolve_plugin_ref("abc123")

    def test_preview_branch_cannot_escape_its_namespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _git(root, "init", "-b", "main")
            with self.assertRaisesRegex(
                install_preview.PreviewInstallError, "preview/ namespace"
            ):
                install_preview.validate_preview_branch(root, "main")

    def test_prepare_connector_uses_a_dedicated_branch(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = Path(temporary)
            connector = fixture_root / "connector"
            target = fixture_root / "target"
            connector.mkdir()
            _git(connector, "init", "-b", "main")
            _git(connector, "config", "user.name", "Preview Test")
            _git(connector, "config", "user.email", "preview@example.invalid")

            (connector / "base.txt").write_text("base\n", encoding="utf-8")
            base = _commit(connector, "base")
            (connector / "gateway.py").write_text("connector = True\n", encoding="utf-8")
            connector_commit = _commit(connector, "connector")

            _git(fixture_root, "clone", connector.as_posix(), target.as_posix())
            _git(target, "config", "user.name", "Preview Test")
            _git(target, "config", "user.email", "preview@example.invalid")
            _git(target, "reset", "--hard", base)
            (target / "official.txt").write_text("later\n", encoding="utf-8")
            official_head = _commit(target, "later official change")

            result = install_preview.prepare_connector(
                target,
                preview_branch="preview/test",
                connector_repository=connector.as_posix(),
                connector_ref="refs/heads/main",
                connector_base=base,
                connector_commit=connector_commit,
            )

            self.assertTrue(result.applied)
            self.assertEqual(result.original_head, official_head)
            self.assertEqual(_git(target, "branch", "--show-current"), "preview/test")
            self.assertEqual(
                (target / "gateway.py").read_text(encoding="utf-8"),
                "connector = True\n",
            )
            self.assertTrue(
                _git(target, "merge-base", "--is-ancestor", official_head, "HEAD")
                == ""
            )

    def test_connector_conflict_restores_original_branch(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture_root = Path(temporary)
            connector = fixture_root / "connector"
            target = fixture_root / "target"
            connector.mkdir()
            _git(connector, "init", "-b", "main")
            _git(connector, "config", "user.name", "Preview Test")
            _git(connector, "config", "user.email", "preview@example.invalid")

            (connector / "gateway.py").write_text("value = 'base'\n", encoding="utf-8")
            base = _commit(connector, "base")
            (connector / "gateway.py").write_text(
                "value = 'connector'\n", encoding="utf-8"
            )
            connector_commit = _commit(connector, "connector")

            _git(fixture_root, "clone", connector.as_posix(), target.as_posix())
            _git(target, "config", "user.name", "Preview Test")
            _git(target, "config", "user.email", "preview@example.invalid")
            _git(target, "reset", "--hard", base)
            (target / "gateway.py").write_text("value = 'official'\n", encoding="utf-8")
            official_head = _commit(target, "conflicting official change")

            with self.assertRaisesRegex(
                install_preview.PreviewInstallError, "original checkout was restored"
            ):
                install_preview.prepare_connector(
                    target,
                    preview_branch="preview/conflict",
                    connector_repository=connector.as_posix(),
                    connector_ref="refs/heads/main",
                    connector_base=base,
                    connector_commit=connector_commit,
                )

            self.assertEqual(_git(target, "branch", "--show-current"), "main")
            self.assertEqual(_git(target, "rev-parse", "HEAD"), official_head)
            self.assertNotIn("preview/conflict", _git(target, "branch", "--list"))

    def test_plugin_install_is_pinned_disabled_and_profile_scoped(self):
        plan = install_preview.PreviewPlan(
            hermes_root=Path("/checkout"),
            hermes_home=Path("/preview-home"),
            hermes_command=Path("/checkout/venv/bin/hermes"),
            plugin_ref="a" * 40,
            preview_branch="preview/test",
        )
        with patch.object(install_preview, "_run") as run:
            install_preview.install_plugin(plan)

        install_call = run.call_args_list[0]
        self.assertIn("--no-enable", install_call.args[0])
        self.assertIn("--ref", install_call.args[0])
        self.assertIn("a" * 40, install_call.args[0])
        self.assertEqual(
            install_call.kwargs["command_env"]["HERMES_HOME"],
            os.fspath(plan.hermes_home),
        )
        self.assertEqual(
            run.call_args_list[1].args[0][-3:],
            ("doctor", "--ci", install_preview.PLUGIN_NAME),
        )

    def test_detached_checkout_return_uses_the_original_sha(self):
        output = StringIO()
        plan = install_preview.PreviewPlan(
            hermes_root=Path("/checkout"),
            hermes_home=Path("/preview-home"),
            hermes_command=Path("/checkout/venv/bin/hermes"),
            plugin_ref="a" * 40,
            preview_branch="preview/test",
        )
        connector = install_preview.ConnectorResult(
            original_ref="HEAD",
            original_head="b" * 40,
            active_branch="preview/test",
            applied=True,
        )
        install_preview._print_return_path(plan, connector, output=output)
        self.assertIn(f"git switch --detach {'b' * 40}", output.getvalue())

    def test_parser_keeps_apply_explicit(self):
        parser = install_preview.build_parser()
        parsed = parser.parse_args(
            [
                "--hermes-root",
                "/tmp/hermes",
                "--hermes-home",
                "/tmp/hermes-preview",
            ]
        )
        self.assertIsInstance(parsed, Namespace)
        self.assertFalse(parsed.apply)


if __name__ == "__main__":
    unittest.main()
