"""Git repository cloning utilities."""

from pathlib import Path
from git import Repo
from config import settings


def clone_repo(url: str, name: str | None = None) -> Path:
    """
    Clone a git repository to the repos directory.

    Args:
        url: Git URL (https or ssh)
        name: Optional name for the local directory. Defaults to repo name from URL.

    Returns:
        Path to the cloned repository
    """
    if name is None:
        # Extract repo name from URL
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]

    repo_path = settings.repos_dir / name

    if repo_path.exists():
        print(f"Repository already exists at {repo_path}, pulling latest...")
        repo = Repo(repo_path)
        repo.remotes.origin.pull()
    else:
        print(f"Cloning {url} to {repo_path}...")
        settings.repos_dir.mkdir(parents=True, exist_ok=True)
        Repo.clone_from(url, repo_path)

    return repo_path


def get_repo_path(name: str) -> Path | None:
    """Get the path to an already-cloned repository."""
    repo_path = settings.repos_dir / name
    if repo_path.exists():
        return repo_path
    return None
