"""Repository discovery - find files, detect languages, identify entry points."""

from pathlib import Path
from dataclasses import dataclass, field


# File extensions to language mapping
LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
}

# Directories to skip
SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    "vendor",
    ".idea",
    ".vscode",
}

# Common entry point patterns
ENTRY_POINT_PATTERNS = {
    "python": ["main.py", "app.py", "__main__.py", "cli.py", "run.py"],
    "javascript": ["index.js", "main.js", "app.js", "server.js"],
    "typescript": ["index.ts", "main.ts", "app.ts", "server.ts"],
}


@dataclass
class RepoDiscovery:
    """Results of repository discovery."""
    root_path: Path
    files: list[Path] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)  # language -> file count
    entry_points: list[Path] = field(default_factory=list)
    modules: list[Path] = field(default_factory=list)  # top-level directories

    @property
    def primary_language(self) -> str | None:
        """The most common language in the repo."""
        if not self.languages:
            return None
        return max(self.languages, key=self.languages.get)


def discover_repo(repo_path: Path) -> RepoDiscovery:
    """
    Discover the structure of a repository.

    Args:
        repo_path: Path to the repository root

    Returns:
        RepoDiscovery with files, languages, entry points, and modules
    """
    discovery = RepoDiscovery(root_path=repo_path)

    # Find top-level directories (modules)
    for item in repo_path.iterdir():
        if item.is_dir() and item.name not in SKIP_DIRS and not item.name.startswith("."):
            discovery.modules.append(item)

    # Walk the repo and collect files
    for file_path in repo_path.rglob("*"):
        # Skip directories in SKIP_DIRS
        if any(skip_dir in file_path.parts for skip_dir in SKIP_DIRS):
            continue

        if not file_path.is_file():
            continue

        ext = file_path.suffix.lower()
        if ext in LANGUAGE_EXTENSIONS:
            discovery.files.append(file_path)
            lang = LANGUAGE_EXTENSIONS[ext]
            discovery.languages[lang] = discovery.languages.get(lang, 0) + 1

            # Check if it's an entry point
            if file_path.name in ENTRY_POINT_PATTERNS.get(lang, []):
                discovery.entry_points.append(file_path)

    return discovery
