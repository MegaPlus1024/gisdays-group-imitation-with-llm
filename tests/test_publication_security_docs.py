from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_publication_security_doc_exists_and_readme_links_it() -> None:
    assert (PROJECT_ROOT / "docs/security/publication_security_check.md").exists()

    readme = _read("README.md")
    assert "docs/security/publication_security_check.md" in readme


def test_gitignore_excludes_common_secret_files() -> None:
    text = _read(".gitignore")

    for required in [
        ".env",
        ".env.*",
        "*.key",
        "*.pem",
        "token*",
        "secrets*",
        "credentials*",
    ]:
        assert required in text


def test_tracked_files_do_not_use_obvious_secret_file_names() -> None:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    tracked = [line.strip().lower().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]
    forbidden_suffixes = (
        "/.env",
        "/credentials.json",
        "/token.json",
        "/id_rsa",
        "/id_ed25519",
        ".pem",
        ".key",
        "/auth.json",
    )
    forbidden_names = {".env", "credentials.json", "token.json", "id_rsa", "id_ed25519", "auth.json"}

    offenders = [
        path
        for path in tracked
        if path in forbidden_names
        or path.endswith(forbidden_suffixes)
        or Path(path).name.startswith("secrets.")
    ]

    assert offenders == []
