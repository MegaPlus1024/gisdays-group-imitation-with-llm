import json
from pathlib import Path


def test_models_local_example_json_is_valid_and_contains_second_model() -> None:
    config_path = Path("configs/models.local.example.json")
    payload = json.loads(config_path.read_text(encoding="utf-8"))

    assert isinstance(payload, dict)
    models = payload.get("models")
    assert isinstance(models, list)

    registry_ids = {item.get("registry_id") for item in models if isinstance(item, dict)}
    assert "qwen2_5_3b_instruct_q4_k_m" in registry_ids
