#!/usr/bin/env python3
"""Prepare the pinned pre-merge Hermes connector and install this plugin.

The supported release remains plugin-only on stock Hermes.  This helper exists
only so contributors can evaluate the unmerged host contract in a dedicated
profile without hand-copying patches or modifying the default live profile.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, TextIO


CONNECTOR_REPOSITORY = "https://github.com/NousResearch/hermes-agent.git"
CONNECTOR_REF = "refs/pull/100004/head"
CONNECTOR_BASE = "21b2095d00a98b8ad7b5c60b10587619c852cdb8"
CONNECTOR_COMMIT = "bd853a945e46cf0cdf24db9530b8a6aa4cc514d2"
PLUGIN_IDENTIFIER = (
    "chriskimjj/agent-extensions/plugins/hermes/discord-related-threads"
)
PLUGIN_NAME = "discord-related-threads"
DEFAULT_PREVIEW_BRANCH = f"preview/{PLUGIN_NAME}-{CONNECTOR_COMMIT[:10]}"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class PreviewInstallError(RuntimeError):
    """A fail-closed preview precondition or operation failure."""


@dataclass(frozen=True)
class PreviewPlan:
    hermes_root: Path
    hermes_home: Path
    hermes_command: Path
    plugin_ref: str
    preview_branch: str


@dataclass(frozen=True)
class ConnectorResult:
    original_ref: str
    original_head: str
    active_branch: str
    applied: bool


def _run(
    command: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path | None = None,
    command_env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    rendered = [os.fspath(part) for part in command]
    try:
        result = subprocess.run(
            rendered,
            cwd=cwd,
            env=command_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise PreviewInstallError(
            f"Could not run command: {' '.join(rendered)} ({exc})"
        ) from exc
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if detail:
            detail = detail.splitlines()[0]
        else:
            detail = f"exit {result.returncode}"
        raise PreviewInstallError(f"Command failed: {' '.join(rendered)} ({detail})")
    return result


def _git(
    root: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return _run(("git", "-C", root, *arguments), check=check)


def _git_text(root: Path, *arguments: str) -> str:
    return _git(root, *arguments).stdout.strip()


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.fspath(left.resolve())) == os.path.normcase(
        os.fspath(right.resolve())
    )


def validate_hermes_root(path: Path) -> Path:
    root = path.expanduser().resolve()
    if not root.is_dir():
        raise PreviewInstallError(f"Hermes checkout does not exist: {root}")
    top_level = Path(_git_text(root, "rev-parse", "--show-toplevel")).resolve()
    if not _same_path(root, top_level):
        raise PreviewInstallError(
            f"--hermes-root must be the Git checkout root, not a subdirectory: {top_level}"
        )
    if _git(root, "diff", "--name-only", "--diff-filter=U").stdout.strip():
        raise PreviewInstallError("Hermes checkout has unresolved merge conflicts")
    for marker in ("CHERRY_PICK_HEAD", "MERGE_HEAD", "REBASE_HEAD"):
        marker_path = Path(_git_text(root, "rev-parse", "--git-path", marker))
        if not marker_path.is_absolute():
            marker_path = root / marker_path
        if marker_path.exists():
            raise PreviewInstallError(
                f"Hermes checkout already has an in-progress Git operation ({marker})"
            )
    return root


def validate_preview_home(path: Path, *, hermes_root: Path) -> Path:
    preview_home = path.expanduser().resolve()
    default_home = (Path.home() / ".hermes").resolve()
    if _same_path(preview_home, default_home):
        raise PreviewInstallError(
            "The pre-merge helper refuses the default live ~/.hermes profile; "
            "choose a dedicated preview HERMES_HOME"
        )
    if preview_home == hermes_root or preview_home.is_relative_to(hermes_root):
        raise PreviewInstallError("Preview HERMES_HOME must be outside the Hermes checkout")
    return preview_home


def resolve_hermes_command(root: Path, explicit: Path | None = None) -> Path:
    candidates = (
        [explicit.expanduser().resolve()]
        if explicit is not None
        else [
            root / ".venv" / "bin" / "hermes",
            root / "venv" / "bin" / "hermes",
            root / ".venv" / "Scripts" / "hermes.exe",
            root / "venv" / "Scripts" / "hermes.exe",
        ]
    )
    command = next((candidate for candidate in candidates if candidate.is_file()), None)
    if command is None:
        raise PreviewInstallError(
            "No Hermes executable found inside the checkout; pass --hermes-command"
        )

    version = _run((command, "--version")).stdout
    install_lines = [
        line.split(":", 1)[1].strip()
        for line in version.splitlines()
        if line.startswith("Install directory:")
    ]
    if not install_lines:
        raise PreviewInstallError(
            "Hermes --version did not report its install directory; cannot prove that "
            "the command belongs to --hermes-root"
        )
    if not _same_path(Path(install_lines[0]), root):
        raise PreviewInstallError(
            f"Hermes command belongs to {install_lines[0]}, not {root}"
        )
    return command


def resolve_plugin_ref(explicit: str | None = None) -> str:
    if explicit is not None:
        if not FULL_SHA.fullmatch(explicit):
            raise PreviewInstallError("--plugin-ref must be a full 40-character Git SHA")
        return explicit

    plugin_root = Path(__file__).resolve().parents[1]
    repository_root = Path(
        _git_text(plugin_root, "rev-parse", "--show-toplevel")
    ).resolve()
    relative_plugin = plugin_root.relative_to(repository_root)
    dirty = _git(
        repository_root,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        os.fspath(relative_plugin),
    ).stdout.strip()
    if dirty:
        raise PreviewInstallError(
            "The plugin directory has uncommitted files; commit them or pass an already "
            "published --plugin-ref"
        )
    return _git_text(repository_root, "rev-parse", "HEAD")


def validate_preview_branch(root: Path, branch: str) -> str:
    if not branch.startswith("preview/"):
        raise PreviewInstallError("Preview branch must stay under the preview/ namespace")
    if (
        _git(
            root,
            "check-ref-format",
            "--branch",
            branch,
            check=False,
        ).returncode
        != 0
    ):
        raise PreviewInstallError(f"Invalid preview branch name: {branch}")
    return branch


def build_plan(args: argparse.Namespace) -> PreviewPlan:
    hermes_root = validate_hermes_root(args.hermes_root)
    hermes_home = validate_preview_home(args.hermes_home, hermes_root=hermes_root)
    hermes_command = resolve_hermes_command(hermes_root, args.hermes_command)
    plugin_ref = resolve_plugin_ref(args.plugin_ref)
    preview_branch = validate_preview_branch(hermes_root, args.preview_branch)
    return PreviewPlan(
        hermes_root=hermes_root,
        hermes_home=hermes_home,
        hermes_command=hermes_command,
        plugin_ref=plugin_ref,
        preview_branch=preview_branch,
    )


def _branch_exists(root: Path, branch: str) -> bool:
    return (
        _git(
            root,
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
            check=False,
        ).returncode
        == 0
    )


def _current_ref(root: Path) -> str:
    result = _git(
        root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False
    )
    return result.stdout.strip() or "HEAD"


def _restore_after_failed_cherry_pick(
    root: Path,
    *,
    original_ref: str,
    original_head: str,
    preview_branch: str,
) -> None:
    _git(root, "cherry-pick", "--abort", check=False)
    if original_ref == "HEAD":
        _git(root, "switch", "--detach", original_head, check=False)
    else:
        _git(root, "switch", original_ref, check=False)

    branch_head = _git(
        root, "rev-parse", "--verify", preview_branch, check=False
    ).stdout.strip()
    if branch_head == original_head:
        _git(root, "branch", "-D", preview_branch, check=False)


def prepare_connector(
    root: Path,
    *,
    preview_branch: str,
    connector_repository: str = CONNECTOR_REPOSITORY,
    connector_ref: str = CONNECTOR_REF,
    connector_base: str = CONNECTOR_BASE,
    connector_commit: str = CONNECTOR_COMMIT,
) -> ConnectorResult:
    original_head = _git_text(root, "rev-parse", "HEAD")
    original_ref = _current_ref(root)

    _git(root, "fetch", "--no-tags", connector_repository, connector_ref)
    fetched_head = _git_text(root, "rev-parse", "FETCH_HEAD")
    if (
        _git(
            root,
            "merge-base",
            "--is-ancestor",
            connector_commit,
            fetched_head,
            check=False,
        ).returncode
        != 0
    ):
        raise PreviewInstallError(
            "The PR ref no longer contains the pinned connector commit; the preview "
            "instructions must be revalidated before use"
        )
    if (
        _git(
            root,
            "merge-base",
            "--is-ancestor",
            connector_base,
            "HEAD",
            check=False,
        ).returncode
        != 0
    ):
        raise PreviewInstallError(
            f"Hermes HEAD does not descend from the verified connector base {connector_base[:10]}"
        )

    changed_paths = [
        line
        for line in _git_text(
            root,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            f"{connector_commit}^",
            connector_commit,
        ).splitlines()
        if line
    ]
    target_status = _git(
        root,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        *changed_paths,
    ).stdout.strip()
    if target_status:
        raise PreviewInstallError(
            "Hermes has local changes in files touched by the connector; preserve or "
            "move those changes before preview installation"
        )
    all_status = _git(
        root, "status", "--porcelain", "--untracked-files=all"
    ).stdout.splitlines()
    if all_status:
        print(
            f"Warning: {len(all_status)} unrelated Hermes worktree change(s) remain "
            "uncommitted and will not be staged by the preview helper."
        )

    if (
        _git(
            root,
            "merge-base",
            "--is-ancestor",
            connector_commit,
            "HEAD",
            check=False,
        ).returncode
        == 0
    ):
        active_branch = _current_ref(root)
        return ConnectorResult(original_ref, original_head, active_branch, False)

    if _branch_exists(root, preview_branch):
        raise PreviewInstallError(
            f"Preview branch already exists: {preview_branch}; inspect it before retrying"
        )

    _git(root, "switch", "-c", preview_branch)
    try:
        _git(root, "cherry-pick", "-x", connector_commit)
    except PreviewInstallError as exc:
        conflicts = _git(
            root, "diff", "--name-only", "--diff-filter=U", check=False
        ).stdout.strip()
        _restore_after_failed_cherry_pick(
            root,
            original_ref=original_ref,
            original_head=original_head,
            preview_branch=preview_branch,
        )
        suffix = f" Conflicts: {conflicts}" if conflicts else ""
        raise PreviewInstallError(
            f"Connector did not apply cleanly; the original checkout was restored.{suffix}"
        ) from exc

    return ConnectorResult(original_ref, original_head, preview_branch, True)


def install_plugin(plan: PreviewPlan) -> None:
    command_env = os.environ.copy()
    command_env["HERMES_HOME"] = os.fspath(plan.hermes_home)
    _run(
        (
            plan.hermes_command,
            "plugins",
            "install",
            "--no-enable",
            "--ref",
            plan.plugin_ref,
            PLUGIN_IDENTIFIER,
        ),
        command_env=command_env,
    )
    _run(
        (
            plan.hermes_command,
            "plugins",
            "doctor",
            "--ci",
            PLUGIN_NAME,
        ),
        command_env=command_env,
    )


def _print_plan(plan: PreviewPlan) -> None:
    print("Pre-merge preview plan")
    print(f"  Hermes checkout: {plan.hermes_root}")
    print(f"  Dedicated profile: {plan.hermes_home}")
    print(f"  Preview branch: {plan.preview_branch}")
    print(f"  Connector: {CONNECTOR_COMMIT}")
    print(f"  Plugin: {PLUGIN_IDENTIFIER}@{plan.plugin_ref}")
    print("  Activation: disabled (the helper never starts a gateway or edits config)")


def _print_return_path(
    plan: PreviewPlan,
    connector: ConnectorResult,
    *,
    output: TextIO = sys.stdout,
) -> None:
    print(f"  Return checkout: {plan.hermes_root}", file=output)
    if connector.original_ref == "HEAD":
        print(
            f"  Return command: git switch --detach {connector.original_head}",
            file=output,
        )
    else:
        print(f"  Return command: git switch {connector.original_ref}", file=output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the pinned Hermes PR connector and install discord-related-threads "
            "into a dedicated, non-default preview profile."
        )
    )
    parser.add_argument(
        "--hermes-root",
        required=True,
        type=Path,
        help="root of a Git-installed Hermes checkout",
    )
    parser.add_argument(
        "--hermes-home",
        required=True,
        type=Path,
        help="dedicated preview HERMES_HOME; ~/.hermes is refused",
    )
    parser.add_argument(
        "--hermes-command",
        type=Path,
        help="Hermes executable belonging to --hermes-root",
    )
    parser.add_argument(
        "--plugin-ref",
        help="published 40-character agent-extensions commit; defaults to this checkout HEAD",
    )
    parser.add_argument(
        "--preview-branch",
        default=DEFAULT_PREVIEW_BRANCH,
        help=f"dedicated Hermes branch to create (default: {DEFAULT_PREVIEW_BRANCH})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the connector and plugin installation; omission is plan-only",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    plan: PreviewPlan | None = None
    connector: ConnectorResult | None = None
    try:
        parsed = build_parser().parse_args(argv)
        plan = build_plan(parsed)
        _print_plan(plan)
        if not parsed.apply:
            print("\nPlan only: no files were changed. Re-run with --apply to execute it.")
            return 0

        connector = prepare_connector(
            plan.hermes_root,
            preview_branch=plan.preview_branch,
        )
        install_plugin(plan)
        print("\nPreview installation passed Plugin Doctor.")
        if connector.applied:
            print(f"  Hermes is now on: {connector.active_branch}")
            _print_return_path(plan, connector)
        else:
            print("  The pinned connector was already present; no host commit was added.")
        print("  The plugin remains disabled and no Discord or gateway action was performed.")
        return 0
    except PreviewInstallError as exc:
        print(f"Preview installation stopped: {exc}", file=sys.stderr)
        if plan is not None and connector is not None and connector.applied:
            print(
                "The connector branch remains available for inspection.",
                file=sys.stderr,
            )
            _print_return_path(plan, connector, output=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
