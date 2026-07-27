# Сведения о моделях

Документ отделяет короткие технические идентификаторы от полных названий,
которые используются в отчётах.

Источники:

- `configs/evaluation_models.json`;
- `configs/model_display_names.json`;
- `docs/ai/model_registry.md`;
- `docs/ai/model_file_mapping.md`;
- сохранённые отчёты об испытаниях.

## Таблица моделей

| Идентификатор проекта | Локальный GGUF | Полное название | Размер | Квантование | Назначение |
| --- | --- | --- | ---: | --- | --- |
| `first_model` | `models/gguf/first_model.gguf` | IBM Granite 3.3 8B Instruct Q4_K_M | 8B | Q4_K_M | малая или средняя база сравнения не из семейства Qwen |
| `second_model` | `models/gguf/second_model.gguf` | Qwen2.5-3B-Instruct Q4_K_M | 3B | Q4_K_M | малая база сравнения Qwen |
| `third_model` | `models/gguf/third_model.gguf` | Qwen3-14B Q5_K_M | 14B | Q5_K_M | историческая сильная модель планирования |
| `fourth_model` | `models/gguf/fourth_model.gguf` | Mistral Small 3.2 24B Instruct Q4_K_M | 24B | Q4_K_M | сильная модель сравнения не из семейства Qwen |
| `fifth_model` | `models/gguf/fifth_model.gguf` | Qwen3-30B-A3B-Instruct-2507 Q4_K_M | 30B-A3B | Q4_K_M | эффективная MoE-модель сравнения |
| `sixth_model` | `models/gguf/sixth_model/Qwen3.6-27B-Q5_K_M.gguf` | Qwen3.6-27B Q5_K_M | 27B | Q5_K_M | дополнительная модель, прошедшая полный набор испытаний |

## Правило отображения

- В командах и ключах JSON используются идентификаторы проекта.
- В пользовательских таблицах и выводах используются полные названия.
- Старая сводка может содержать исторический alias. Реестр преобразует его при
  чтении, но исходный файл не изменяется.

## Подтверждённые alias

| Историческое имя | Текущее имя |
| --- | --- |
| `qwen2_5_3b_instruct_q4_k_m` | `second_model` |
| `qwen3_6_27b_q5_k_m` | `sixth_model` |

Для Qwen3.6-27B Q5_K_M точные источник, версия, размер и SHA-256 указаны в
`docs/reproducibility.md`. Для остальных моделей документ не делает
неподтверждённых заявлений о поставщике GGUF или контрольной сумме.
