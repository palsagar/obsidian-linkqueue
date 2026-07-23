import pytest

from agent.config import REQUIRED, Config, load_config

VALID = """\
# linkqueue agent config
OPENROUTER_API_KEY=sk-or-abc
QUEUE_URL=https://queue.example.dev
CF_ACCESS_CLIENT_ID=id.access
CF_ACCESS_CLIENT_SECRET="secret with quotes"
VAULT_PATH=~/Obsidian/vault
"""


class TestLoadConfig:
    def test_parses_required_keys_and_defaults(self, tmp_path):
        f = tmp_path / "agent.env"
        f.write_text(VALID)
        cfg = load_config(f)
        assert isinstance(cfg, Config)
        assert cfg.openrouter_api_key == "sk-or-abc"
        assert cfg.queue_url == "https://queue.example.dev"
        assert cfg.cf_access_client_id == "id.access"
        assert cfg.cf_access_client_secret == "secret with quotes"
        assert str(cfg.vault_path).endswith("/Obsidian/vault")  # ~ expanded
        assert cfg.model == "x-ai/grok-4.5"
        assert cfg.fallback_model == "deepseek/deepseek-v4-pro"
        assert cfg.limit == 20

    def test_expands_env_vars_in_vault_path(self, tmp_path):
        f = tmp_path / "agent.env"
        f.write_text(VALID.replace("VAULT_PATH=~/Obsidian/vault", "VAULT_PATH=$HOME/Obsidian/vault"))
        cfg = load_config(f)
        assert "$" not in str(cfg.vault_path)
        assert str(cfg.vault_path).endswith("/Obsidian/vault")

    def test_overrides_for_optional_keys(self, tmp_path):
        f = tmp_path / "agent.env"
        f.write_text(VALID + "TRIAGE_MODEL=foo/bar\nTRIAGE_LIMIT=5\n")
        cfg = load_config(f)
        assert cfg.model == "foo/bar"
        assert cfg.limit == 5

    def test_missing_required_key_raises_with_key_name(self, tmp_path):
        f = tmp_path / "agent.env"
        f.write_text("QUEUE_URL=https://q.example.dev\n")
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            load_config(f)

    def test_missing_file_falls_back_to_environment(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env")
        monkeypatch.setenv("QUEUE_URL", "https://queue.example.dev")
        monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
        monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "secret")
        monkeypatch.setenv("VAULT_PATH", str(tmp_path / "vault"))
        monkeypatch.setenv("TRIAGE_LIMIT", "7")
        cfg = load_config(tmp_path / "nope.env")
        assert cfg.openrouter_api_key == "sk-or-env"
        assert cfg.vault_path == tmp_path / "vault"
        assert cfg.limit == 7

    def test_missing_file_and_empty_environment_raises(self, tmp_path, monkeypatch):
        for key in REQUIRED:
            monkeypatch.delenv(key, raising=False)
        with pytest.raises(ValueError, match="nope.env"):
            load_config(tmp_path / "nope.env")
