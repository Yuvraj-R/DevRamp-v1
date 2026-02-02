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

# Directories to skip (dependencies, caches, builds, IDE)
SKIP_DIRS = {
    # Version control
    ".git",
    ".svn",
    ".hg",
    # Dependencies
    "node_modules",
    "bower_components",
    "jspm_packages",
    "vendor",
    "third_party",
    "third-party",
    "external",
    "externals",
    "deps",
    "dependencies",
    "packages",  # monorepo packages often have their own node_modules
    "lib",  # often contains compiled/vendored code
    "libs",
    # Python
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "site-packages",
    ".eggs",
    "*.egg-info",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    # JS/TS
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".cache",
    ".parcel-cache",
    ".turbo",
    ".vercel",
    ".netlify",
    # Build outputs
    "dist",
    "build",
    "out",
    "output",
    "target",
    "bin",
    "obj",
    "_build",
    "public/build",  # compiled assets
    "static/build",
    # Bundles and compiled assets
    "bundle",
    "bundles",
    ".bundle",
    "chunks",
    "assets",  # often contains compiled/static files
    "static",  # often contains compiled files
    # Coverage/test artifacts
    "coverage",
    "htmlcov",
    ".nyc_output",
    "__snapshots__",
    # IDE
    ".idea",
    ".vscode",
    ".vs",
    ".fleet",
    # Misc
    ".terraform",
    ".serverless",
    "cdk.out",
    ".aws-sam",
    ".gradle",
    ".maven",
}

# Files to skip (lock files, generated, minified)
SKIP_FILES = {
    # Lock files
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Gemfile.lock",
    "composer.lock",
    "go.sum",
    "Cargo.lock",
    "mix.lock",
    "pubspec.lock",
    "shrinkwrap.yaml",
    # Generated
    ".DS_Store",
    "Thumbs.db",
}

# File suffixes that indicate minified/bundled code (skip these)
SKIP_SUFFIXES = {
    ".min.js",
    ".min.css",
    ".bundle.js",
    ".bundle.css",
    ".chunk.js",
    ".chunk.css",
    ".packed.js",
    ".prod.js",
    ".production.js",
    "-min.js",
    "-bundle.js",
}

# Max file size to process (skip huge generated files)
MAX_FILE_SIZE = 100_000  # 100KB

# Max line length - files with lines longer than this are likely minified
MAX_LINE_LENGTH = 1000

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

        # Skip specific files
        if file_path.name in SKIP_FILES:
            continue

        # Skip minified/bundled files by suffix
        file_lower = file_path.name.lower()
        if any(file_lower.endswith(suffix) for suffix in SKIP_SUFFIXES):
            continue

        # Skip files that are too large (likely generated/minified)
        try:
            file_size = file_path.stat().st_size
            if file_size > MAX_FILE_SIZE:
                continue
        except OSError:
            continue

        # Skip files with very long lines (minified code)
        if _is_minified(file_path):
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


def _is_minified(file_path: Path) -> bool:
    """
    Check if a file appears to be minified based on line length.

    Minified files typically have very long lines (entire file on one line).
    """
    try:
        with open(file_path, 'r', errors='ignore') as f:
            # Just check first few lines - minified files are obvious
            for i, line in enumerate(f):
                if i >= 5:  # Only check first 5 lines
                    break
                if len(line) > MAX_LINE_LENGTH:
                    return True
        return False
    except Exception:
        return False  # If we can't read it, let other checks handle it
