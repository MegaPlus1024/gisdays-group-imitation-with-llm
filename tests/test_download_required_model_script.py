from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "download_required_model.ps1"
POWERSHELL = shutil.which("powershell.exe")

FAKE_CURL_SOURCE = r"""
using System;
using System.IO;

public static class Program
{
    private static string FindArgument(string[] args, string name)
    {
        for (int index = 0; index + 1 < args.Length; index++)
        {
            if (args[index] == name)
            {
                return args[index + 1];
            }
        }
        return null;
    }

    public static int Main(string[] args)
    {
        string statePath = Environment.GetEnvironmentVariable("FAKE_CURL_STATE");
        string logPath = Environment.GetEnvironmentVariable("FAKE_CURL_LOG");
        string mode = Environment.GetEnvironmentVariable("FAKE_CURL_MODE") ?? "";
        string expectedToken =
            Environment.GetEnvironmentVariable("FAKE_EXPECT_TOKEN") ?? "";
        int callCount = 0;
        if (!String.IsNullOrEmpty(statePath) && File.Exists(statePath))
        {
            Int32.TryParse(File.ReadAllText(statePath).Trim(), out callCount);
        }
        callCount += 1;
        if (!String.IsNullOrEmpty(statePath))
        {
            File.WriteAllText(statePath, callCount.ToString());
        }

        string headerPath = FindArgument(args, "--dump-header");
        string outputPath = FindArgument(args, "--output");
        string configPath = FindArgument(args, "--config");
        bool tokenPresent = false;
        if (!String.IsNullOrEmpty(configPath) && File.Exists(configPath))
        {
            string config = File.ReadAllText(configPath);
            tokenPresent =
                !String.IsNullOrEmpty(expectedToken) &&
                config.Contains("Authorization: Bearer " + expectedToken);
        }
        if (!String.IsNullOrEmpty(logPath))
        {
            File.AppendAllText(
                logPath,
                "call=" + callCount + Environment.NewLine +
                "args=" + String.Join("|", args) + Environment.NewLine +
                "config=" + (configPath ?? "") + Environment.NewLine +
                "token_present=" + tokenPresent + Environment.NewLine
            );
        }

        if (mode == "rate-limit-then-error" && callCount == 1)
        {
            if (!String.IsNullOrEmpty(outputPath))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(outputPath));
                File.WriteAllText(outputPath, "partial-model-data");
            }
            File.WriteAllText(
                headerPath,
                "HTTP/1.1 429 Too Many Requests\r\n" +
                "RateLimit: \"resolvers\";r=0;t=1\r\n\r\n"
            );
            Console.Write("429");
            return 22;
        }

        File.WriteAllText(
            headerPath,
            "HTTP/1.1 500 Internal Server Error\r\n\r\n"
        );
        Console.Write("500");
        return 22;
    }
}
"""


def _ps_quote(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


@pytest.fixture(scope="module")
def fake_curl_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if POWERSHELL is None:
        pytest.skip("Windows PowerShell is required for downloader tests")

    directory = tmp_path_factory.mktemp("fake_curl")
    source_path = directory / "FakeCurl.cs"
    executable_path = directory / "curl.exe"
    source_path.write_text(FAKE_CURL_SOURCE, encoding="utf-8")
    command = (
        f"$source = Get-Content -LiteralPath {_ps_quote(source_path)} -Raw; "
        "Add-Type -TypeDefinition $source -Language CSharp "
        f"-OutputAssembly {_ps_quote(executable_path)} "
        "-OutputType ConsoleApplication"
    )
    completed = subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert executable_path.is_file()
    return directory


def _run_downloader(
    fake_curl_dir: Path,
    destination: Path,
    *,
    mode: str,
    state_path: Path,
    log_path: Path,
    extra_environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    environment = os.environ.copy()
    environment["PATH"] = str(fake_curl_dir) + os.pathsep + environment["PATH"]
    environment["FAKE_CURL_MODE"] = mode
    environment["FAKE_CURL_STATE"] = str(state_path)
    environment["FAKE_CURL_LOG"] = str(log_path)
    environment.pop("HF_TOKEN", None)
    if extra_environment:
        environment.update(extra_environment)
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT_PATH),
            "-Destination",
            str(destination),
            "-MaxRateLimitWaitSeconds",
            "1",
            "-DefaultRateLimitDelaySeconds",
            "5",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def test_downloader_retries_429_and_preserves_partial_file(
    fake_curl_dir: Path,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "model.gguf"
    state_path = tmp_path / "state.txt"
    log_path = tmp_path / "curl.log"

    started = time.monotonic()
    completed = _run_downloader(
        fake_curl_dir,
        destination,
        mode="rate-limit-then-error",
        state_path=state_path,
        log_path=log_path,
    )
    elapsed = time.monotonic() - started
    output = completed.stdout + completed.stderr

    assert completed.returncode != 0
    assert state_path.read_text(encoding="utf-8") == "2"
    assert destination.read_text(encoding="utf-8") == "partial-model-data"
    assert elapsed >= 0.8
    assert "HTTP 429 from Hugging Face" in output
    assert "Waiting 1 seconds before resuming" in output
    assert "HTTP 500" in output
    assert "partial file was preserved for resume" in output


def test_downloader_uses_hf_token_without_exposing_it(
    fake_curl_dir: Path,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "model.gguf"
    state_path = tmp_path / "state.txt"
    log_path = tmp_path / "curl.log"
    token = "placeholder-test-value"

    completed = _run_downloader(
        fake_curl_dir,
        destination,
        mode="generic-error",
        state_path=state_path,
        log_path=log_path,
        extra_environment={
            "HF_TOKEN": token,
            "FAKE_EXPECT_TOKEN": token,
        },
    )
    output = completed.stdout + completed.stderr
    log = log_path.read_text(encoding="utf-8")
    config_line = next(
        line for line in log.splitlines() if line.startswith("config=")
    )
    config_path = Path(config_line.split("=", 1)[1])

    assert completed.returncode != 0
    assert "Using HF_TOKEN from the environment." in output
    assert "token_present=True" in log
    assert token not in output
    assert token not in log
    assert not config_path.exists()


def test_downloader_keeps_integrity_checks_and_bounded_429_wait() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    for required in [
        "--continue-at",
        "$env:HF_TOKEN",
        "Retry-After",
        "RateLimit-Reset",
        "$MaxRateLimitWaitSeconds",
        "Start-Sleep -Seconds $WaitSeconds",
        "19509790944",
        "cfecab168156269f25d5ffe9e13cf2a401ca2f43a9693fa00bcd1625316ccbde",
        "Get-FileHash",
    ]:
        assert required in script
    assert "--retry 3" not in script
