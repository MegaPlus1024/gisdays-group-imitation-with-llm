from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_deterministic_gpu_resource_harness import (
    build_corpus,
    build_optional_replay_flags,
    build_server_command_payload,
    build_server_args,
    PhaseSampler,
    build_resource_summary,
    evaluate_gpu_offload_evidence,
    evaluate_idle_stability,
    flatten_sample,
    parse_startup_log_evidence,
    percentile,
    read_startup_log_evidence,
    request_record_summary,
    validate_model_file,
    validate_local_host,
    validate_startup_log_evidence,
    wait_for_health,
    write_json,
    output_file_hashes,
)


def test_build_corpus_is_deterministic_and_ordered() -> None:
    first = build_corpus()
    second = build_corpus()

    assert first == second
    assert [item["case_id"] for item in first] == [
        "short",
        "medium",
        "long",
    ]
    assert [item["payload_words"] for item in first] == [448, 1856, 7424]
    assert [item["max_tokens"] for item in first] == [64, 128, 128]
    assert len({item["messages_sha256"] for item in first}) == 3


def test_qwen_challenger_server_args_are_generic_and_lifecycle_owned() -> None:
    args = build_server_args(
        server_path=Path("llama-server.exe"),
        model_path=Path("models/gguf/qwen3_6_27b_q5_k_m/Qwen3.6-27B-Q5_K_M.gguf"),
        model_id="qwen3_6_27b_q5_k_m",
        host="127.0.0.1",
        port=8085,
        ctx_size=12288,
        gpu_layers="999",
        parallel=1,
        jinja=True,
        reasoning="off",
        server_log_verbosity=4,
    )

    assert args == [
        "llama-server.exe",
        "--model",
        "models\\gguf\\qwen3_6_27b_q5_k_m\\Qwen3.6-27B-Q5_K_M.gguf",
        "--alias",
        "qwen3_6_27b_q5_k_m",
        "--host",
        "127.0.0.1",
        "--port",
        "8085",
        "--ctx-size",
        "12288",
        "--n-gpu-layers",
        "999",
        "--parallel",
        "1",
        "--jinja",
        "--reasoning",
        "off",
        "-lv",
        "4",
    ]


def test_server_log_verbosity_is_optional_and_replayable(tmp_path: Path) -> None:
    default_args = build_server_args(
        server_path=Path("llama-server.exe"),
        model_path=Path("models/gguf/fourth_model.gguf"),
        model_id="fourth_model",
        host="127.0.0.1",
        port=8084,
        ctx_size=12288,
        gpu_layers="999",
        parallel=1,
    )
    verbose_args = build_server_args(
        server_path=Path("llama-server.exe"),
        model_path=Path("models/gguf/qwen3_6_27b_q5_k_m/Qwen3.6-27B-Q5_K_M.gguf"),
        model_id="qwen3_6_27b_q5_k_m",
        host="127.0.0.1",
        port=8085,
        ctx_size=12288,
        gpu_layers="999",
        parallel=1,
        server_log_verbosity=4,
    )

    assert "-lv" not in default_args
    assert "4" not in default_args
    assert verbose_args[-2:] == ["-lv", "4"]

    server_command = build_server_command_payload(verbose_args)
    assert server_command["argv"][-2:] == ["-lv", "4"]
    write_json(tmp_path / "server_command.json", server_command)
    saved = (tmp_path / "server_command.json").read_text(encoding="utf-8")
    assert '"-lv"' in saved
    assert '"4"' in saved

    replay_flags = build_optional_replay_flags(
        jinja=True,
        reasoning="off",
        server_log_verbosity=4,
        expected_model_bytes=19509790944,
        expected_model_sha256="c" * 64,
        expected_offloaded_layers="65/65",
        require_startup_alias=False,
    )
    assert "--server-log-verbosity 4" in replay_flags
    assert "--jinja" in replay_flags
    assert "--reasoning off" in replay_flags


def test_validate_local_host_rejects_non_local_hosts() -> None:
    assert validate_local_host("127.0.0.1") == "127.0.0.1"
    assert validate_local_host("LOCALHOST") == "localhost"

    try:
        validate_local_host("0.0.0.0")
    except ValueError as exc:
        assert "localhost/127.0.0.1" in str(exc)
    else:
        raise AssertionError("expected non-local host to be rejected")


def test_default_server_args_preserve_previous_profile_shape() -> None:
    args = build_server_args(
        server_path=Path("llama-server.exe"),
        model_path=Path("models/gguf/third_model.gguf"),
        model_id="third_model",
        host="127.0.0.1",
        port=8082,
        ctx_size=12288,
        gpu_layers="999",
        parallel=1,
    )

    assert "--jinja" not in args
    assert "--reasoning" not in args
    assert args == [
        "llama-server.exe",
        "--model",
        "models\\gguf\\third_model.gguf",
        "--alias",
        "third_model",
        "--host",
        "127.0.0.1",
        "--port",
        "8082",
        "--ctx-size",
        "12288",
        "--n-gpu-layers",
        "999",
        "--parallel",
        "1",
    ]


def test_model_file_validation_checks_size_and_hash(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"abc")

    validated = validate_model_file(
        model,
        expected_bytes=3,
        expected_sha256="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    )

    assert validated["bytes"] == 3
    assert (
        validated["sha256"]
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_model_file_validation_rejects_size_sha_and_malformed_sha(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"abc")

    try:
        validate_model_file(model, expected_bytes=4)
    except ValueError as exc:
        assert "byte size mismatch" in str(exc)
    else:
        raise AssertionError("expected byte mismatch to be rejected")

    try:
        validate_model_file(model, expected_sha256="not-a-sha")
    except ValueError as exc:
        assert "64 lowercase/uppercase hex" in str(exc)
    else:
        raise AssertionError("expected malformed SHA to be rejected")

    try:
        validate_model_file(
            model,
            expected_sha256="0" * 64,
        )
    except ValueError as exc:
        assert "SHA-256 mismatch" in str(exc)
    else:
        raise AssertionError("expected SHA mismatch to be rejected")


def test_startup_log_evidence_detects_qwen_gpu_offload_without_running_server() -> None:
    log = """
0 I   - Vulkan1 : NVIDIA RTX PRO 4000 Blackwell (28886 MiB, 28118 MiB free)
0 I load_tensors: offloaded 65/65 layers to GPU
0 I load_tensors:      Vulkan1 model buffer size = 17761.91 MiB
0 I llama_context: n_ctx         = 12288
0 I llama_kv_cache:    Vulkan1 KV buffer size =   768.00 MiB
0 I sched_reserve:    Vulkan1 compute buffer size =   649.02 MiB
0 I srv          init: init: chat template, thinking = 0
qwen3_6_27b_q5_k_m
"""

    evidence = parse_startup_log_evidence(
        log,
        expected_alias="qwen3_6_27b_q5_k_m",
    )
    failures = validate_startup_log_evidence(
        evidence,
        expected_offloaded_layers="65/65",
        require_alias=True,
        expected_context_size=12288,
        require_reasoning_off=True,
    )

    assert failures == []
    assert evidence["backend_vulkan1_present"] is True
    assert evidence["gpu_name"] == "NVIDIA RTX PRO 4000 Blackwell"
    assert evidence["offloaded_layers"] == "65/65"
    assert evidence["vulkan1_model_buffer_mib"] == 17761.91
    assert evidence["vulkan1_kv_buffer_mib"] == 768.0
    assert evidence["vulkan1_compute_buffer_mib"] == 649.02
    assert evidence["context_size"] == 12288
    assert evidence["reasoning_disabled"] is True


def test_verbose_vulkan_startup_fixture_extracts_offload_and_buffers() -> None:
    log = """
load_tensors: offloaded 65/65 layers to GPU
load_tensors: Vulkan1 model buffer size = 17761.91 MiB
llama_kv_cache: Vulkan1 KV buffer size = 768.00 MiB
sched_reserve: Vulkan1 compute buffer size = 649.02 MiB
Vulkan1 : NVIDIA RTX PRO 4000 Blackwell
"""

    evidence = parse_startup_log_evidence(
        log,
        expected_alias="qwen3_6_27b_q5_k_m",
    )

    assert evidence["offloaded_layers"] == "65/65"
    assert evidence["vulkan1_model_buffer_mib"] == 17761.91
    assert evidence["vulkan1_kv_buffer_mib"] == 768.0
    assert evidence["vulkan1_compute_buffer_mib"] == 649.02


def test_non_verbose_log_still_fails_required_offload() -> None:
    evidence = parse_startup_log_evidence(
        "Vulkan1 : NVIDIA RTX PRO 4000 Blackwell\n"
        "llama_context: n_ctx = 12288\n"
        "srv init: chat template, thinking = 0\n",
        expected_alias="qwen3_6_27b_q5_k_m",
    )

    failures = validate_startup_log_evidence(
        evidence,
        expected_offloaded_layers="65/65",
        expected_context_size=12288,
        require_reasoning_off=True,
    )

    assert evidence["offloaded_layers"] is None
    assert evidence["vulkan1_model_buffer_mib"] is None
    assert "startup_log_offloaded_layers_mismatch" in failures


def test_startup_log_parser_reads_final_appended_logfile(tmp_path: Path) -> None:
    stderr = tmp_path / "server_stderr.log"
    stderr.write_text(
        "Vulkan1 : NVIDIA RTX PRO 4000 Blackwell\n",
        encoding="utf-8",
    )
    early = read_startup_log_evidence(
        stderr,
        expected_alias="qwen3_6_27b_q5_k_m",
    )
    assert early["offloaded_layers"] is None

    with stderr.open("a", encoding="utf-8") as handle:
        handle.write("load_tensors: offloaded 65/65 layers to GPU\n")
        handle.write("load_tensors: Vulkan1 model buffer size = 17761.91 MiB\n")
        handle.write("llama_kv_cache: Vulkan1 KV buffer size = 768.00 MiB\n")
        handle.write("sched_reserve: Vulkan1 compute buffer size = 649.02 MiB\n")

    final = read_startup_log_evidence(
        stderr,
        expected_alias="qwen3_6_27b_q5_k_m",
    )

    assert final["offloaded_layers"] == "65/65"
    assert final["vulkan1_compute_buffer_mib"] == 649.02


def test_startup_log_evidence_rejects_oom_or_wrong_offload() -> None:
    evidence = parse_startup_log_evidence(
        "Vulkan1 : NVIDIA RTX PRO 4000 Blackwell\n"
        "offloaded 64/65 layers to GPU\n"
        "failed allocation",
        expected_alias="qwen3_6_27b_q5_k_m",
    )

    failures = validate_startup_log_evidence(
        evidence,
        expected_offloaded_layers="65/65",
    )

    assert "startup_log_offloaded_layers_mismatch" in failures
    assert "startup_log_contains_oom_or_failed_allocation" in failures


def test_startup_log_evidence_rejects_missing_offload_context_or_reasoning() -> None:
    evidence = parse_startup_log_evidence(
        "Vulkan1 : NVIDIA RTX PRO 4000 Blackwell\n"
        "n_ctx = 8192\n"
        "srv init: chat template, thinking = 1\n",
        expected_alias="qwen3_6_27b_q5_k_m",
    )

    failures = validate_startup_log_evidence(
        evidence,
        expected_offloaded_layers="65/65",
        expected_context_size=12288,
        require_reasoning_off=True,
    )

    assert "startup_log_offloaded_layers_mismatch" in failures
    assert "startup_log_context_size_mismatch" in failures
    assert "startup_log_reasoning_not_disabled" in failures


def test_output_file_hashes_excludes_manifest_itself(tmp_path: Path) -> None:
    write_json(tmp_path / "benchmark_summary.json", {"status": "succeeded"})
    write_json(tmp_path / "evidence_manifest.json", {"self": True})

    rows = output_file_hashes(tmp_path)

    assert [row["file"] for row in rows] == ["benchmark_summary.json"]
    assert rows[0]["bytes"] > 0
    assert len(rows[0]["sha256"]) == 64


def test_wait_for_health_requires_success_status() -> None:
    class FakeResponse:
        def __init__(self, status_code: int, text: str) -> None:
            self.status_code = status_code
            self.text = text

    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, _url: str) -> FakeResponse:
            self.calls += 1
            if self.calls == 1:
                return FakeResponse(404, "not ready")
            return FakeResponse(200, "ok")

    class FakeProcess:
        returncode = None

        def poll(self) -> None:
            return None

    result = wait_for_health(
        client=FakeClient(),
        health_url="http://127.0.0.1:8085/health",
        process=FakeProcess(),
        timeout_seconds=1.0,
    )

    assert result == {"status_code": 200, "body_preview": "ok"}


def test_percentile_interpolates() -> None:
    values = [1.0, 2.0, 3.0, 4.0]

    assert percentile(values, 0.0) == 1.0
    assert percentile(values, 0.5) == 2.5
    assert percentile(values, 0.95) == 3.85
    assert percentile(values, 1.0) == 4.0
    assert percentile([], 0.5) is None


def test_request_record_summary_groups_measured_cases() -> None:
    records = [
        {
            "request_kind": "warmup",
            "case_id": "short",
            "success": True,
            "wall_time_ms": 1.0,
            "token_budget_met": True,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "llama_timings": {},
        },
        {
            "request_kind": "measured",
            "case_id": "short",
            "success": True,
            "wall_time_ms": 100.0,
            "token_budget_met": True,
            "usage": {"prompt_tokens": 500, "completion_tokens": 64},
            "llama_timings": {
                "prompt_per_second": 1000.0,
                "predicted_per_second": 50.0,
            },
        },
        {
            "request_kind": "measured",
            "case_id": "short",
            "success": False,
            "wall_time_ms": 200.0,
            "token_budget_met": False,
            "usage": {},
            "llama_timings": {},
        },
    ]

    summary = request_record_summary(records)

    assert summary["measured_request_count"] == 2
    assert summary["successful_request_count"] == 1
    assert summary["failed_request_count"] == 1
    assert summary["token_budget_met_count"] == 1
    assert summary["per_case"]["short"]["wall_time_ms"]["p50"] == 100.0
    assert summary["per_case"]["short"]["prompt_tokens"]["mean"] == 500.0


def test_resource_summary_uses_pre_server_baseline() -> None:
    samples = [
        {
            "phase": "baseline_without_server",
            "psutil_available": True,
            "pair_rss_mb": 0.0,
            "pair_private_mb": 0.0,
            "pair_cpu_percent": 0.0,
            "pair_cpu_percent_normalized": 0.0,
            "system_cpu_percent": 2.0,
            "system_ram_used_mb": 1000.0,
            "system_ram_available_mb": 9000.0,
            "active_llama_server_processes": 0,
            "gpu": {
                "gpu_telemetry_available": True,
                "gpu_name": "GPU",
                "driver_version": "1",
                "total_vram_mb": 24000.0,
                "used_vram_mb": 1000.0,
                "gpu_utilization_percent": 0.0,
                "gpu_memory_utilization_percent": 4.0,
                "temperature_c": 35.0,
                "power_draw_w": 20.0,
            },
        },
        {
            "phase": "loaded_idle",
            "psutil_available": True,
            "pair_rss_mb": 8000.0,
            "pair_private_mb": 8200.0,
            "pair_cpu_percent": 5.0,
            "pair_cpu_percent_normalized": 0.2,
            "system_cpu_percent": 3.0,
            "system_ram_used_mb": 9000.0,
            "system_ram_available_mb": 1000.0,
            "active_llama_server_processes": 1,
            "gpu": {
                "gpu_telemetry_available": True,
                "gpu_name": "GPU",
                "driver_version": "1",
                "total_vram_mb": 24000.0,
                "used_vram_mb": 19000.0,
                "gpu_utilization_percent": 1.0,
                "gpu_memory_utilization_percent": 80.0,
                "temperature_c": 40.0,
                "power_draw_w": 30.0,
            },
        },
        {
            "phase": "workload_short",
            "psutil_available": True,
            "pair_rss_mb": 8100.0,
            "pair_private_mb": 8300.0,
            "pair_cpu_percent": 30.0,
            "pair_cpu_percent_normalized": 1.2,
            "system_cpu_percent": 10.0,
            "system_ram_used_mb": 9100.0,
            "system_ram_available_mb": 900.0,
            "active_llama_server_processes": 1,
            "gpu": {
                "gpu_telemetry_available": True,
                "gpu_name": "GPU",
                "driver_version": "1",
                "total_vram_mb": 24000.0,
                "used_vram_mb": 19500.0,
                "gpu_utilization_percent": 100.0,
                "gpu_memory_utilization_percent": 82.0,
                "temperature_c": 70.0,
                "power_draw_w": 150.0,
            },
        },
    ]

    summary = build_resource_summary(samples)

    assert summary["derived"]["loaded_idle_vram_delta_mb"] == 18000.0
    assert (
        summary["derived"]["workload_vram_growth_over_loaded_idle_mb"]
        == 500.0
    )
    assert summary["derived"]["peak_vram_headroom_mb"] == 4500.0
    assert (
        summary["phases"]["workload_short"][
            "peak_cpu_percent_normalized"
        ]
        == 1.2
    )


def test_flatten_sample_extracts_gpu_fields() -> None:
    row = flatten_sample(
        {
            "timestamp": "now",
            "phase": "loaded_idle",
            "pair_rss_mb": 1.0,
            "gpu": {
                "gpu_telemetry_available": True,
                "gpu_name": "GPU",
                "used_vram_mb": 2.0,
                "power_draw_w": 3.0,
            },
        }
    )

    assert row["phase"] == "loaded_idle"
    assert row["gpu_name"] == "GPU"
    assert row["gpu_used_vram_mb"] == 2.0
    assert row["gpu_power_draw_w"] == 3.0

def test_gpu_offload_evidence_requires_vram_delta_and_activity() -> None:
    resource_summary = {
        "derived": {"loaded_idle_vram_delta_mb": 18000.0},
        "workload_combined": {
            "gpu_telemetry_available": True,
            "gpu_peak_utilization_percent": 100.0,
        },
    }

    verified = evaluate_gpu_offload_evidence(resource_summary, "999")
    no_layers = evaluate_gpu_offload_evidence(resource_summary, "0")
    no_delta = evaluate_gpu_offload_evidence(
        {
            "derived": {"loaded_idle_vram_delta_mb": 128.0},
            "workload_combined": {
                "gpu_telemetry_available": True,
                "gpu_peak_utilization_percent": 100.0,
            },
        },
        "999",
    )
    no_activity = evaluate_gpu_offload_evidence(
        {
            "derived": {"loaded_idle_vram_delta_mb": 18000.0},
            "workload_combined": {
                "gpu_telemetry_available": True,
                "gpu_peak_utilization_percent": 0.0,
            },
        },
        "999",
    )

    assert verified["verified"] is True
    assert verified["reasons"] == []
    assert no_layers["verified"] is False
    assert "gpu_layers_not_requested" in no_layers["reasons"]
    assert no_delta["verified"] is False
    assert "loaded_vram_delta_below_threshold" in no_delta["reasons"]
    assert no_activity["verified"] is False
    assert (
        "no_positive_gpu_utilization_sample_during_workload"
        in no_activity["reasons"]
    )


def test_phase_sampler_starts_in_baseline_phase() -> None:
    sampler = PhaseSampler(interval_seconds=0.5)

    assert sampler._snapshot_state() == ("baseline_without_server", None)


def test_idle_stability_requires_quiet_gpu_and_stable_vram() -> None:
    stable_samples = [
        {
            "gpu_telemetry_available": True,
            "used_vram_mb": value,
            "gpu_utilization_percent": utilization,
        }
        for value, utilization in [
            (19103.0, 1.0),
            (19104.0, 0.0),
            (19103.0, 2.0),
            (19104.0, 0.0),
        ]
    ]
    busy_samples = stable_samples[:-1] + [
        {
            "gpu_telemetry_available": True,
            "used_vram_mb": 19104.0,
            "gpu_utilization_percent": 98.0,
        }
    ]
    moving_vram_samples = stable_samples[:-1] + [
        {
            "gpu_telemetry_available": True,
            "used_vram_mb": 19200.0,
            "gpu_utilization_percent": 0.0,
        }
    ]

    stable = evaluate_idle_stability(stable_samples)
    busy = evaluate_idle_stability(busy_samples)
    moving = evaluate_idle_stability(moving_vram_samples)

    assert stable["stable"] is True
    assert stable["reasons"] == []
    assert busy["stable"] is False
    assert "gpu_utilization_above_idle_threshold" in busy["reasons"]
    assert moving["stable"] is False
    assert "vram_not_stable" in moving["reasons"]
