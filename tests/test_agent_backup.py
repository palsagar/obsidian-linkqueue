import subprocess

import pytest

from agent.backup import run_backup


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture()
def vault_repo(tmp_path):
    """A vault git repo with a bare 'origin' it can push to."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    vault = tmp_path / "vault"
    vault.mkdir()
    git(vault, "init", "-b", "main")
    git(vault, "config", "user.name", "test")
    git(vault, "config", "user.email", "test@example.com")
    git(vault, "remote", "add", "origin", str(origin))
    (vault / "note.md").write_text("hello")
    git(vault, "add", "-A")
    git(vault, "commit", "-m", "initial")
    git(vault, "push", "origin", "main")
    return vault


class TestRunBackup:
    def test_commits_and_pushes_changes(self, vault_repo):
        (vault_repo / "new-note.md").write_text("triaged tonight")
        (vault_repo / "note.md").write_text("edited")

        summary = run_backup(vault_repo)

        assert "2 files" in summary
        assert git(vault_repo, "status", "--porcelain") == ""  # clean tree
        # the backup commit reached origin
        assert git(vault_repo, "rev-parse", "HEAD") == git(
            vault_repo, "ls-remote", "origin", "main"
        ).split()[0]
        assert "vault backup" in git(vault_repo, "log", "-1", "--format=%s")

    def test_no_changes_is_a_noop(self, vault_repo):
        before = git(vault_repo, "rev-parse", "HEAD")
        summary = run_backup(vault_repo)
        assert "no changes" in summary
        assert git(vault_repo, "rev-parse", "HEAD") == before

    def test_never_pulls_remote_changes(self, vault_repo, tmp_path):
        # someone else pushes to origin; backup must not bring it into the vault
        other = tmp_path / "other"
        subprocess.run(
            ["git", "clone", git(vault_repo, "remote", "get-url", "origin"), str(other)],
            check=True, capture_output=True,
        )
        git(other, "config", "user.name", "other")
        git(other, "config", "user.email", "other@example.com")
        (other / "remote-only.md").write_text("x")
        git(other, "add", "-A")
        git(other, "commit", "-m", "remote change")
        git(other, "push", "origin", "main")

        (vault_repo / "local.md").write_text("y")
        with pytest.raises(subprocess.CalledProcessError):
            run_backup(vault_repo)  # push rejected (diverged) — never merges

        assert not (vault_repo / "remote-only.md").exists()
        assert "vault backup" in git(vault_repo, "log", "-1", "--format=%s")  # local commit kept

    def test_not_a_git_repo_raises(self, tmp_path):
        plain = tmp_path / "plain"
        plain.mkdir()
        with pytest.raises(ValueError, match="not a git repo"):
            run_backup(plain)
