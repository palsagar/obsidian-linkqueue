from agent.cli import main

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
