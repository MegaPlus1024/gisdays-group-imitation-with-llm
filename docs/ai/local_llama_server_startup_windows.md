# Local llama-server Startup on Windows

This project uses Python virtualenv for Python dependencies and `llama-server.exe` for local model serving. These are separate things:

- `.venv` provides Python packages for tests and project scripts.
- `.venv` does not add `llama-server.exe` to `PATH`.
- The startup wrapper now searches for `llama-server.exe` automatically.

## Default startup

From the project root:

```powershell
.\scripts\start_llama_server.ps1
```

The wrapper starts:

- host: `127.0.0.1`
- port: `8080`
- ctx-size: `4096`
- model: `models\gguf\first_model.gguf`

Before launching, it prints:

- project root
- model path
- server path
- host/port
- ctx-size

## Python venv

Activate the Python environment when running Python scripts or tests:

```powershell
.\.venv\Scripts\Activate.ps1
```

This is useful for commands such as:

```powershell
python scripts\run_llama_smoke.py --help
python scripts\run_runtime_baseline.py --help
```

It is not required for finding `llama-server.exe`; the PowerShell wrapper handles that separately.

## Model path

The default model path is:

```text
models\gguf\first_model.gguf
```

If the model is elsewhere, pass it explicitly:

```powershell
.\scripts\start_llama_server.ps1 -ModelPath "C:\path\to\model.gguf"
```

Do not commit GGUF model files to git.

## Server path override

The wrapper first tries:

1. `Get-Command llama-server`
2. `Get-Command llama-server.exe`
3. common Windows install/extract locations, including WinGet, scoop, project-relative folders, and user folders

If automatic search fails, pass the executable explicitly:

```powershell
.\scripts\start_llama_server.ps1 -ServerPath "C:\path\to\llama-server.exe"
```

Do not commit `llama-server.exe` to git.

## Parameter overrides

```powershell
.\scripts\start_llama_server.ps1 -Port 8081
.\scripts\start_llama_server.ps1 -Host 127.0.0.1
.\scripts\start_llama_server.ps1 -CtxSize 4096
.\scripts\start_llama_server.ps1 -ModelPath "C:\path\to\model.gguf"
.\scripts\start_llama_server.ps1 -ServerPath "C:\path\to\llama-server.exe"
```

Show usage without starting the server:

```powershell
.\scripts\start_llama_server.ps1 -Help
```

Verify path detection and command construction without starting the server:

```powershell
.\scripts\start_llama_server.ps1 -DryRun
```

## Confirmed runtime helper commands

These commands only show usage/help and do not start a model run:

```powershell
python scripts\run_llama_smoke.py --help
python scripts\run_runtime_baseline.py --help
```

Run smoke/baseline scripts without `--help` only after `llama-server` is running.

## Troubleshooting

### `llama-server.exe not found`

Use the explicit path override:

```powershell
.\scripts\start_llama_server.ps1 -ServerPath "C:\path\to\llama-server.exe"
```

Or add the directory containing `llama-server.exe` to User `PATH`.

### `model file not found`

Put the model here:

```text
models\gguf\first_model.gguf
```

Or pass a model path:

```powershell
.\scripts\start_llama_server.ps1 -ModelPath "C:\path\to\model.gguf"
```

### Port `8080` already in use

Use another port:

```powershell
.\scripts\start_llama_server.ps1 -Port 8081
```

Then use the matching base URL for Python smoke/runtime scripts:

```powershell
python scripts\run_llama_smoke.py --base-url http://127.0.0.1:8081/v1 --model-name first_model.gguf
```

### Server starts but runtime smoke cannot connect

Check:

- The server terminal is still open.
- The startup output says `Host/port: 127.0.0.1:8080`.
- Smoke script uses the same base URL, for example `http://127.0.0.1:8080/v1`.
- Firewall or local security tools are not blocking localhost connections.
- The model name passed to smoke scripts matches the served model alias/name expected by the local runtime.
