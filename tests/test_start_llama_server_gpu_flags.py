from __future__ import annotations

import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "start_llama_server.ps1"


def _run_dry_run(tmp_path: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    fake_model = tmp_path / "fake-model.gguf"
    fake_server = tmp_path / "llama-server.exe"
    fake_model.write_text("fake model placeholder", encoding="utf-8")
    fake_server.write_text("fake server placeholder", encoding="utf-8")
    return subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-ModelPath",
            str(fake_model),
            "-ServerPath",
            str(fake_server),
            "-Port",
            "8099",
            "-DryRun",
            *extra_args,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_default_dry_run_does_not_emit_gpu_flags(tmp_path: Path) -> None:
    completed = _run_dry_run(tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert "--ctx-size 4096" in completed.stdout
    assert "--n-gpu-layers" not in completed.stdout
    assert "--main-gpu" not in completed.stdout
    assert "--device none" not in completed.stdout
    assert "default llama-server behavior; no wrapper GPU flags" in completed.stdout


def test_gpu_dry_run_emits_supported_gpu_flags(tmp_path: Path) -> None:
    completed = _run_dry_run(
        tmp_path,
        "-GpuLayers",
        "999",
        "-MainGpu",
        "0",
        "-SplitMode",
        "none",
        "-TensorSplit",
        "1",
        "-BatchSize",
        "1024",
        "-UBatchSize",
        "256",
        "-Threads",
        "8",
        "-CtxSize",
        "2048",
        "-FlashAttention",
        "auto",
    )

    assert completed.returncode == 0, completed.stderr
    assert "--ctx-size 2048" in completed.stdout
    assert "--n-gpu-layers 999" in completed.stdout
    assert "--main-gpu 0" in completed.stdout
    assert "--split-mode none" in completed.stdout
    assert "--tensor-split 1" in completed.stdout
    assert "--batch-size 1024" in completed.stdout
    assert "--ubatch-size 256" in completed.stdout
    assert "--threads 8" in completed.stdout
    assert "--flash-attn auto" in completed.stdout


def test_empty_optional_gpu_values_are_not_emitted(tmp_path: Path) -> None:
    completed = _run_dry_run(tmp_path, "-TensorSplit", "")

    assert completed.returncode == 0, completed.stderr
    assert "--tensor-split" not in completed.stdout


def test_cpu_only_uses_device_none_and_rejects_gpu_placement(tmp_path: Path) -> None:
    cpu_only = _run_dry_run(tmp_path, "-CpuOnly")

    assert cpu_only.returncode == 0, cpu_only.stderr
    assert "--device none" in cpu_only.stdout

    rejected = _run_dry_run(tmp_path, "-CpuOnly", "-GpuLayers", "999")

    assert rejected.returncode != 0
    assert "-CpuOnly cannot be combined with GPU placement options" in (rejected.stderr + rejected.stdout)
