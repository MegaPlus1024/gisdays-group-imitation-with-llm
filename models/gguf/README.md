# GGUF-модели

Помещайте локальные GGUF-файлы в этот каталог. Они исключены из Git.

Для воспроизведения итогового результата нужен файл:

```text
models/gguf/sixth_model/Qwen3.6-27B-Q5_K_M.gguf
```

Скрипт `scripts/download_required_model.ps1` загружает закреплённую версию,
проверяет размер и SHA-256, а также переносит ранее проверенный файл со старого
пути без повторной загрузки.

Источники метаданных:

- `configs/evaluation_models.json`;
- `configs/model_display_names.json`;
- `docs/ai/model_registry.md`;
- `docs/ai/model_file_mapping.md`.
