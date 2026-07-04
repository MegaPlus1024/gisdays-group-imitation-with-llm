# Publication Security Check

Date: 2026-07-03

Scope: pre-push security/secrets audit for the repository at `<repo>`.

## 1. What Was Checked

- Current git state: `git status --short`.
- Recent history: `git log --oneline -n 10`.
- Remote configuration: `git remote -v`.
- Tracked file names from `git ls-files`.
- Current tracked file contents.
- Full working tree text files, excluding `.git`, `.venv`, Python caches, pytest caches, and local GGUF model files.
- Ignored text files that remain under the repository tree.
- Git history across all commits.

## 2. Patterns Searched

High-confidence secret patterns:

- JWT-like values beginning with `eyJ`
- OpenAI-style keys beginning with `sk-`
- GitHub tokens beginning with `ghp_` or `github_pat_`
- Hugging Face tokens beginning with `hf_`
- Slack tokens beginning with `xoxb-` / `xoxp-`
- refresh-token-like values beginning with `rt.`
- `Bearer` tokens
- private key blocks beginning with `-----BEGIN`

Marker patterns:

- `token`
- `secret`
- `credential` / `credentials`
- `api_key` / `apikey`
- `access_token`
- `refresh_token`
- `authorization`
- `password` / `passwd`
- `private_key`
- `OPENAI_API_KEY`
- `GITHUB_TOKEN`
- `HF_TOKEN`
- `.env`

## 3. Results Summary

| Area | Result | Findings |
|---|---|---:|
| tracked high-confidence secret values | passed | 0 |
| untracked high-confidence secret values | passed | 0 |
| ignored high-confidence secret values | passed | 0 |
| git history high-confidence secret values | passed | 0 |
| tracked obvious secret file names | passed | 0 |
| git history obvious secret file names | passed | 0 |

Marker-only findings were reviewed as documentation/placeholders or benign runtime text. Examples include `.gitignore` secret exclusions, publishing guidance that says not to commit credentials, and llama-server timing lines containing the word `tokens`. No marker-only finding contained a real secret value in the repository scan.

## 4. Current Tracked-File Status

No tracked repository file matched a high-confidence secret value pattern.

No tracked path matched obvious secret file names such as:

- `.env`
- `credentials.json`
- `token.json`
- `id_rsa`
- `id_ed25519`
- `*.pem`
- `*.key`
- `secrets.*`
- `auth.json`

The repository `.gitignore` excludes local secret and runtime files, including `.env`, `.env.*`, token files, secret files, credential files, private key files, logs, GGUF files, llama-server binaries, and editor state directories.

## 5. Working Tree Status

No high-confidence secret values were found in non-git working tree text files after excluding local binary/model/runtime directories.

Ignored text files under the repository produced marker-only hits in runtime logs where the word `tokens` refers to model token counts, not credentials.

## 6. Git History Status

Git history scan covered 14 commits. No high-confidence secret values or obvious secret file names were found in history.

No history rewrite is currently indicated by the repository scan.

## 7. IDE/Editor Exposure Outside Repository

The IDE/editor context showed ChatGPT/OpenAI authentication JSON outside the repository. Those values were not found in tracked files, generated artifacts, or git history by this audit.

Manual action is still required because any token visible in an editor, chat, terminal, screenshot, or clipboard should be treated as exposed.

Recommended manual action:

- Rotate/revoke the visible ChatGPT/OpenAI session tokens through the provider UI.
- Remove local copies that are not needed.
- Keep `auth.json` and any token-bearing files outside the repository and never stage them.

## 8. Publishing Guidance

Before every push:

1. Run `git status --short`.
2. Confirm no `.env`, token, credential, private key, GGUF, runtime binary, or secret-bearing log file is staged.
3. Run `.\.venv\Scripts\python.exe -m pytest tests\test_publication_consistency.py -q`.
4. Run `.\.venv\Scripts\python.exe -m pytest -q`.
5. Rotate/revoke any secret that was visible outside the repository before publication.

## 9. Verdict

Repository files and git history passed this redacted secrets audit.

It is safe to push only after the user rotates/revokes the ChatGPT/OpenAI tokens that were visible in the IDE/editor context outside the repository.
