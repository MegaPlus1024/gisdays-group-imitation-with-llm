# Publishing This Repository to GitHub

## 1. Pre-Publish Checklist

Before pushing:

- Run `git status`.
- Confirm `.gitignore` excludes `.venv/`, GGUF models, runtime binaries, logs and credentials.
- Confirm `models/gguf/*.gguf` is not staged.
- Confirm no tokens, credentials, `.env` files, private keys or local secrets are staged.
- Check large files before commit.
- Run tests.

## 2. Git Status Check

```powershell
git status
git branch --show-current
git log --oneline -5
```

The branch should normally be `main`.

## 3. Large File Check

```powershell
Get-ChildItem -Recurse -File |
  Where-Object { $_.FullName -notmatch '\\.git\\|\\.venv\\' } |
  Sort-Object Length -Descending |
  Select-Object -First 30 FullName,Length
```

Do not commit:

- `.venv/`;
- `models/gguf/*.gguf`;
- `*.gguf`;
- `*.bin`;
- `*.safetensors`;
- `llama-server.exe`;
- credentials or private tokens.

## 4. Local Commit

Recommended staging command for this project state:

```powershell
git add README.md .gitignore docs/github_publish_guide.md reports/experiments
git add src scripts tests configs docs/ai docs/*.md experiments
git status
```

If `git status` shows `.venv/`, GGUF files, credentials or huge binaries staged, unstage them before committing:

```powershell
git restore --staged <PATH>
```

Commit:

```powershell
git commit -m "Prepare local LLM agent research prototype for publication"
```

## 5. GitHub CLI Option

Private repository:

```powershell
gh auth login
gh repo create local-llm-agent-lab --private --source=. --remote=origin --push
```

Public repository:

```powershell
gh auth login
gh repo create local-llm-agent-lab --public --source=. --remote=origin --push
```

## 6. Browser + Git Remote Option

Create an empty repository in the GitHub web UI. Do not initialize it with README, `.gitignore` or license if the local repository already has those files.

HTTPS remote:

```powershell
git remote add origin https://github.com/<OWNER>/<REPO>.git
git branch -M main
git push -u origin main
```

SSH remote:

```powershell
git remote add origin git@github.com:<OWNER>/<REPO>.git
git branch -M main
git push -u origin main
```

If `origin` already exists:

```powershell
git remote -v
git remote set-url origin https://github.com/<OWNER>/<REPO>.git
git push -u origin main
```

## 7. Public vs Private

Use a private repository if there is any uncertainty about:

- ownership of generated reports/artifacts;
- local machine paths in artifacts;
- organization policy;
- whether experiment outputs should be public.

Use a public repository only after reviewing artifacts and documentation for sensitive paths or project-specific constraints.

## 8. Verify After Push

After pushing:

```powershell
git status
git remote -v
git log --oneline -3
```

On GitHub, verify:

- README renders correctly;
- reports are visible under `reports/experiments/`;
- `.venv/` is absent;
- GGUF files are absent;
- `models/gguf/README.md` or `MODELS.md` explains model placement;
- tests and source files are visible.

## 9. Common Errors

### Authentication failed

Run:

```powershell
gh auth login
```

Or use a valid HTTPS token/SSH key.

### Remote origin already exists

```powershell
git remote -v
git remote set-url origin https://github.com/<OWNER>/<REPO>.git
```

### Rejected push because remote has README

The remote was probably initialized with files. Either create a fresh empty repo or pull/rebase carefully:

```powershell
git pull --rebase origin main
```

Resolve conflicts before pushing.

### Large file rejected

Find the file:

```powershell
git status --short
```

Unstage it:

```powershell
git restore --staged <PATH>
```

If it was already committed, remove it from history before pushing.

### Accidentally tracked `.venv` or GGUF

```powershell
git restore --staged .venv
git restore --staged models/gguf/*.gguf
```

Then verify `.gitignore`.
