import pytest

from agent.cli import main
from agent.sync import SyncError

CONFIG = """\
OPENROUTER_API_KEY=sk-or-abc
QUEUE_URL=http://127.0.0.1:1
CF_ACCESS_CLIENT_ID=id.access
CF_ACCESS_CLIENT_SECRET=secret
VAULT_PATH={vault}
"""


class TestCli:
    def test_offline_queue_skips_silently_with_exit_zero(self, tmp_path, capsys):
        cfg = tmp_path / "agent.env"
        cfg.write_text(CONFIG.format(vault=tmp_path))
        code = main(["run", "--config", str(cfg)])
        assert code == 0
        assert "skipping" in capsys.readouterr().out.lower()

    def test_missing_config_exits_nonzero(self, tmp_path, capsys):
        code = main(["run", "--config", str(tmp_path / "nope.env")])
        assert code == 1
        assert "nope.env" in capsys.readouterr().err

    def test_backup_on_non_repo_vault_exits_nonzero(self, tmp_path, capsys):
        cfg = tmp_path / "agent.env"
        cfg.write_text(CONFIG.format(vault=tmp_path))
        code = main(["backup", "--config", str(cfg)])
        assert code == 1
        assert "not a git repo" in capsys.readouterr().err


class TestSyncBracket:
    @pytest.fixture()
    def config_file(self, tmp_path):
        cfg = tmp_path / "agent.env"
        cfg.write_text(CONFIG.format(vault=tmp_path))
        return cfg

    def test_pre_sync_failure_aborts_before_triage(self, config_file, monkeypatch, capsys):
        def boom(vault_path):
            raise SyncError("no session")

        monkeypatch.setattr("agent.cli.ob_sync", boom)
        monkeypatch.setattr(
            "agent.cli.run_triage",
            lambda *a, **k: pytest.fail("triage must not run against an unsynced vault"),
        )
        code = main(["run", "--sync", "--config", str(config_file)])
        assert code == 1
        assert "aborting" in capsys.readouterr().err

    def test_syncs_before_and_after_triage(self, config_file, monkeypatch, capsys):
        calls = []
        monkeypatch.setattr("agent.cli.ob_sync", lambda vault_path: calls.append("sync"))
        monkeypatch.setattr(
            "agent.cli.run_triage",
            lambda *a, **k: calls.append("triage") or {"done": 1, "failed": 0},
        )
        monkeypatch.setattr(
            "agent.cli.triage_clippings", lambda *a, **k: {"done": 0, "failed": 0}
        )
        code = main(["run", "--sync", "--config", str(config_file)])
        assert code == 0
        assert calls == ["sync", "triage", "sync"]

    def test_post_sync_failure_exits_nonzero(self, config_file, monkeypatch, capsys):
        calls = []

        def sync(vault_path):
            calls.append("sync")
            if len(calls) > 1:  # pre-sync succeeds, push fails
                raise SyncError("push refused")

        monkeypatch.setattr("agent.cli.ob_sync", sync)
        monkeypatch.setattr("agent.cli.run_triage", lambda *a, **k: {"done": 0, "failed": 0})
        monkeypatch.setattr(
            "agent.cli.triage_clippings", lambda *a, **k: {"done": 0, "failed": 0}
        )
        code = main(["run", "--sync", "--config", str(config_file)])
        assert code == 1
        assert "post-run sync failed" in capsys.readouterr().err
