# Реестр локальных моделей

## Назначение

Документ связывает технические идентификаторы экспериментов с полными
названиями и локальными GGUF-файлами. Основной машиночитаемый источник:
`configs/evaluation_models.json`.

GGUF-файлы не добавляются в Git. В репозитории сохраняются только метаданные,
пути и известные alias.

## Текущие записи

| Идентификатор | Полное название | Локальный путь | Endpoint |
| --- | --- | --- | --- |
| `first_model` | IBM Granite 3.3 8B Instruct Q4_K_M | `models/gguf/first_model.gguf` | `http://127.0.0.1:8081/v1` |
| `second_model` | Qwen2.5-3B-Instruct Q4_K_M | `models/gguf/second_model.gguf` | `http://127.0.0.1:8080/v1` |
| `third_model` | Qwen3-14B Q5_K_M | `models/gguf/third_model.gguf` | `http://127.0.0.1:8082/v1` |
| `fourth_model` | Mistral Small 3.2 24B Instruct Q4_K_M | `models/gguf/fourth_model.gguf` | `http://127.0.0.1:8083/v1` |
| `fifth_model` | Qwen3-30B-A3B-Instruct-2507 Q4_K_M | `models/gguf/fifth_model.gguf` | `http://127.0.0.1:8084/v1` |
| `sixth_model` | Qwen3.6-27B Q5_K_M | `models/gguf/sixth_model/Qwen3.6-27B-Q5_K_M.gguf` | `http://127.0.0.1:8085/v1` |

## Исторические alias

| Старый идентификатор | Текущий идентификатор |
| --- | --- |
| `qwen2_5_3b_instruct_q4_k_m` | `second_model` |
| `qwen3_6_27b_q5_k_m` | `sixth_model` |

Alias нужны для чтения старых результатов. Новые команды используют текущие
идентификаторы.

## Известное происхождение файлов

- Для Qwen2.5-1.5B и Qwen2.5-3B в ранних документах сохранены ссылки
  `https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF` и
  `https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF`.
- Для Qwen3.6-27B закреплённый источник, версия, размер и SHA-256 приведены в
  `docs/reproducibility.md`.
- Для остальных локальных GGUF точные публичные revision и SHA-256 не
  подтверждены. Документ их не выдумывает.

## Добавление модели

1. Добавить запись в `configs/evaluation_models.json`.
2. Указать относительный путь внутри `models/gguf/`.
3. Добавить отображаемое название в `configs/model_display_names.json`, если
   модель участвует в пользовательских таблицах.
4. Добавить alias только при наличии старых результатов с другим
   идентификатором.
5. Проверить запись командой `scripts/check_evaluation_model.py`.
