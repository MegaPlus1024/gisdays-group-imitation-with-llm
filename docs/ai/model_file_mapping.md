# Соответствие моделей и локальных файлов

Этот технический справочник показывает, какой GGUF-файл ожидается для каждого
идентификатора. Источник путей:
`configs/evaluation_models.json`.

| Идентификатор | Имя модели для `llama-server` | Локальный путь |
| --- | --- | --- |
| `first_model` | `first_model` | `models/gguf/first_model.gguf` |
| `second_model` | `second_model` | `models/gguf/second_model.gguf` |
| `third_model` | `third_model` | `models/gguf/third_model.gguf` |
| `fourth_model` | `fourth_model` | `models/gguf/fourth_model.gguf` |
| `fifth_model` | `fifth_model` | `models/gguf/fifth_model.gguf` |
| `sixth_model` | `sixth_model` | `models/gguf/sixth_model/Qwen3.6-27B-Q5_K_M.gguf` |

Старые результаты могут содержать `qwen2_5_3b_instruct_q4_k_m` и
`qwen3_6_27b_q5_k_m`. Реестр разрешает их соответственно в `second_model` и
`sixth_model`. Содержимое старых файлов не переписывается.

GGUF-файлы не добавляются в Git. Новый пользователь размещает их локально или
использует `scripts/download_required_model.ps1` для Qwen3.6-27B Q5_K_M.

Проверка записи:

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py `
  --models-config configs\evaluation_models.json `
  --model-id sixth_model `
  --json
```
