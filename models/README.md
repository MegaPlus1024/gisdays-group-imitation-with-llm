# Локальные модели

Каталог `models/gguf/` предназначен для локальных GGUF-файлов. Сами модели
исключены из Git.

Основная модель итогового воспроизведения:

```text
models/gguf/sixth_model/Qwen3.6-27B-Q5_K_M.gguf
```

Загрузка и проверка:

```powershell
.\scripts\download_required_model.ps1
```

Полная инструкция находится в `docs/reproducibility.md`, а соответствие
технических идентификаторов моделям — в
`configs/model_display_names.json`.
