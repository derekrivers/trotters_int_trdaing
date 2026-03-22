from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
import json
import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
import uuid


class OpenClawSupervisorIntegrationTests(unittest.TestCase):
    def test_node_plugin_suite_passes(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        test_path = repo_root / "extensions" / "openclaw" / "trotters-runtime" / "index.test.js"
        node_command = self._node_command()
        if node_command is None:
            self.skipTest("Node plugin tests require node or nodejs")
        result = subprocess.run(
            [node_command, str(test_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            self.fail(f"Node plugin tests failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

    def test_bootstrap_script_replaces_existing_supervisor_cron_and_seeds_auth(self) -> None:
        if os.name != "posix":
            self.skipTest("Bootstrap smoke test requires a POSIX shell environment")
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("Bootstrap smoke test requires /bin/sh")

        repo_root = Path(__file__).resolve().parents[1]
        script_path = repo_root / "scripts" / "openclaw" / "start-openclaw.sh"
        real_node = self._node_command()
        if real_node is None:
            self.skipTest("Bootstrap smoke test requires node or nodejs")

        with tempfile.TemporaryDirectory(prefix="openclaw-bootstrap-") as temp_dir:
            root = Path(temp_dir)
            home = root / "home" / "node"
            state_root = home / ".openclaw"
            source_auth_file = state_root / "agents" / "dev" / "agent" / "auth-profiles.json"
            target_auth_file = state_root / "agents" / "runtime-supervisor" / "agent" / "auth-profiles.json"
            heartbeat_file = state_root / "workspaces" / "runtime-supervisor" / "HEARTBEAT.md"
            source_auth_file.parent.mkdir(parents=True, exist_ok=True)
            source_auth_file.write_text(json.dumps({"profiles": [{"provider": "openai"}]}), encoding="utf-8")

            config_dir = root / "fixtures" / "openclaw-config"
            extensions_dir = root / "fixtures" / "openclaw-extensions"
            bootstrap_dir = root / "fixtures" / "openclaw-bootstrap"
            config_dir.mkdir(parents=True, exist_ok=True)
            (extensions_dir / "trotters-runtime").mkdir(parents=True, exist_ok=True)
            bootstrap_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "openclaw.json").write_text('{"agents":[]}\n', encoding="utf-8")
            (bootstrap_dir / "runtime-supervisor-message.txt").write_text("first line\nsecond line\n", encoding="utf-8")

            jobs_path = root / "jobs.json"
            jobs_path.write_text(
                json.dumps(
                    [
                        {"id": "old-1", "name": "trotters-runtime-supervisor"},
                        {"id": "keep-1", "name": "another-job"},
                        {"id": "old-2", "name": "trotters-runtime-supervisor"},
                    ]
                ),
                encoding="utf-8",
            )
            log_path = root / "openclaw.log"
            bin_dir = root / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            self._write_executable(
                bin_dir / "openclaw",
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import os
                    import sys
                    from pathlib import Path

                    jobs_path = Path(os.environ["TEST_OPENCLAW_JOBS_FILE"])
                    log_path = Path(os.environ["TEST_OPENCLAW_LOG"])
                    args = sys.argv[1:]
                    with log_path.open("a", encoding="utf-8") as handle:
                        handle.write(" ".join(args) + "\\n")

                    if args[:2] == ["plugins", "install"]:
                        raise SystemExit(0)
                    if args[:3] == ["cron", "list", "--json"]:
                        sys.stdout.write(jobs_path.read_text(encoding="utf-8"))
                        raise SystemExit(0)
                    if args[:2] == ["cron", "remove"]:
                        job_id = args[2]
                        jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
                        jobs = [job for job in jobs if job.get("id") != job_id]
                        jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
                        raise SystemExit(0)
                    if args[:2] == ["cron", "add"]:
                        jobs = json.loads(jobs_path.read_text(encoding="utf-8"))

                        def value_after(flag: str) -> str | None:
                            try:
                                return args[args.index(flag) + 1]
                            except (ValueError, IndexError):
                                return None

                        jobs.append(
                            {
                                "id": "new-supervisor-job",
                                "name": value_after("--name"),
                                "agent": value_after("--agent"),
                                "message": value_after("--message"),
                            }
                        )
                        jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
                        raise SystemExit(0)

                    raise SystemExit(f"Unexpected openclaw invocation: {args}")
                    """
                ),
            )
            self._write_executable(
                bin_dir / "node",
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "$#" -ge 2 ] && [ "$1" = "dist/index.js" ] && [ "$2" = "gateway" ]; then
                      sleep 1
                      exit 0
                    fi
                    exec "$TEST_REAL_NODE" "$@"
                    """
                ),
            )

            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "PATH": f"{bin_dir}:{env['PATH']}",
                    "TEST_OPENCLAW_JOBS_FILE": str(jobs_path),
                    "TEST_OPENCLAW_LOG": str(log_path),
                    "TEST_REAL_NODE": real_node,
                    "OPENCLAW_GATEWAY_BIND": "0.0.0.0",
                    "OPENCLAW_GATEWAY_PORT": "18789",
                }
            )

            with ExitStack() as stack:
                stack.enter_context(self._replace_with_symlink(Path("/opt/openclaw-config"), config_dir))
                stack.enter_context(self._replace_with_symlink(Path("/opt/openclaw-extensions"), extensions_dir))
                stack.enter_context(self._replace_with_symlink(Path("/opt/openclaw-bootstrap"), bootstrap_dir))
                result = subprocess.run(
                    [shell, str(script_path)],
                    cwd=repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )

            if result.returncode != 0:
                self.fail(f"Bootstrap smoke test failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

            jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
            supervisor_jobs = [job for job in jobs if job.get("name") == "trotters-runtime-supervisor"]
            self.assertEqual(len(supervisor_jobs), 1)
            self.assertEqual(supervisor_jobs[0]["agent"], "runtime-supervisor")
            self.assertIn("first line second line", supervisor_jobs[0]["message"])
            self.assertEqual(
                target_auth_file.read_text(encoding="utf-8"),
                source_auth_file.read_text(encoding="utf-8"),
            )
            self.assertTrue((state_root / "openclaw.json").exists())
            self.assertIn("This workspace is active.", heartbeat_file.read_text(encoding="utf-8"))

            log_lines = log_path.read_text(encoding="utf-8").splitlines()
            self.assertTrue(any(line.startswith("cron remove old-1") for line in log_lines))
            self.assertTrue(any(line.startswith("cron remove old-2") for line in log_lines))
            self.assertEqual(sum(1 for line in log_lines if line.startswith("cron add")), 1)

    def _write_executable(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _node_command(self) -> str | None:
        return shutil.which("node") or shutil.which("nodejs")

    @contextmanager
    def _replace_with_symlink(self, target: Path, source: Path):
        backup = None
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            backup = target.parent / f"{target.name}.backup.{uuid.uuid4().hex}"
            target.replace(backup)
        target.symlink_to(source, target_is_directory=True)
        try:
            yield
        finally:
            if target.is_symlink():
                target.unlink()
            elif target.exists():
                shutil.rmtree(target)
            if backup is not None:
                backup.replace(target)


if __name__ == "__main__":
    unittest.main()
