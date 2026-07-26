# Итоговый сравнительный отчёт

## Behavioral Benchmark v2 для локальных LLM

* **Версия кода:** `5826c8c`
* **Дата проведения:** 26 июля 2026 года
* **Модели:** `fifth_model`, `third_model`, `fourth_model`
* **Объём испытаний:** 105 real-model trials
* **Итог:** 0 из 3 моделей прошли обязательный correctness gate

---

## 1. Резюме

В рамках Behavioral Benchmark v2 были протестированы три локальные языковые модели в одинаковых условиях. Каждая модель выполнила семь сценариев по пять независимых trials, то есть 35 trials на модель и 105 trials суммарно.

Все три модели показали одинаковый результат по базовой успешности:

* 30 успешных trials из 35;
* шесть сценариев пройдены с результатом `5/5`;
* сценарий `long_horizon_multi_fact_retention` завершён с результатом `0/5`;
* итоговый обязательный gate не пройден ни одной моделью.

Таким образом, среди протестированных моделей нет победителя, удовлетворяющего установленным требованиям корректности. Переход к ресурсному ранжированию как к способу выбора лучшей модели методологически некорректен: correctness имеет приоритет над скоростью и потреблением ресурсов.

---

## 2. Цель оценки

Цель benchmark — проверить способность модели работать как policy-компонент в детерминированной многоагентной среде:

1. принимать ровно одно допустимое действие за ход;
2. соблюдать границы ролей;
3. использовать только подтверждённые факты;
4. передавать данные между агентами без подмены значений;
5. корректно восстанавливаться после ожидаемых ошибок;
6. не повторять неизменённые неуспешные действия;
7. завершать работу только после выполнения обязательных требований;
8. сохранять несколько фактов и файлов на длинной траектории без регрессии состояния.

Runtime отвечал за детерминированную оркестрацию, round-robin scheduling, histories, tool allowlists, validation, guarded finish и сохранение общего состояния. Модель выбирала действия в пределах предоставленного контракта.

---

## 3. Проверенный baseline

Все итоговые cohort runs выполнялись на commit:

```text
5826c8c — Decouple trace counters from retention metrics
```

Перед запуском cohort была исправлена инструментальная ошибка: общие trace counters были отделены от retention-specific gate. После исправления:

* `recoverable_failed_tool_actions`;
* `exact_value_validations`;
* `conflict_resolution_steps`;
* `inter_role_handoffs`;
* `post_completion_drift_events`

стали рассчитываться независимо от наличия retention contract.

Регрессионная проверка baseline:

```text
2648 passed
20 skipped
Tracked working tree clean
```

Новая граница между generic trace metrics и retention gate была подтверждена отдельными тестами, включая V2-02, V2-05 и V2-07.

---

## 4. Методика

Для каждой модели использовалась одна и та же конфигурация:

```text
7 сценариев
5 trials на сценарий
35 trials на модель
105 trials суммарно
```

Модели запускались последовательно, по одной:

| Модель | Порт |
| --- | ---: |
| `fifth_model` | 8084 |
| `third_model` | 8082 |
| `fourth_model` | 8083 |

Общие параметры сервера:

```text
--ctx-size 12288
--n-gpu-layers 999
--parallel 1
```

Перед каждым cohort run выполнялись:

1. проверка commit и чистого tracked tree;
2. проверка отсутствия других model servers;
3. запуск одного `llama-server`;
4. readiness check;
5. проверка `/v1/models`;
6. direct protocol smoke;
7. полный cohort;
8. анализ experiment summary и trial summaries;
9. остановка сервера;
10. проверка отсутствия listener и ответа endpoint.

После завершения всех запусков:

```text
ActiveModelServers   : 0
TrackedTreeClean     : True
TotalBehavioralTrials: 105
```

---

## 5. Сценарии

Benchmark включал следующие сценарии:

| ID | Проверяемая способность |
| --- | --- |
| `article_file_handoff_v2` | Чтение источника, создание grounded-файла и точная передача результата |
| `office_shared_fact_recovery_v2` | Публикация shared facts, наблюдение ошибки файла и последующее recovery |
| `role_boundary_exact_handoff` | Соблюдение ролей и точная межролевая передача |
| `malformed_action_recovery` | Восстановление после некорректно сформированного действия |
| `conflicting_grounded_facts` | Выбор правильного authoritative source при конфликте |
| `dependency_progress_and_finish_guard` | Progress-aware ожидание зависимости и guarded finish |
| `long_horizon_multi_fact_retention` | Долгосрочное удержание нескольких фактов, файлов и выполненных требований |

---

## 6. Обязательный correctness gate

Для прохождения benchmark модель должна была одновременно выполнить все условия:

* не менее `32/35` успешных trials;
* не менее `4/5` в каждом сценарии;
* grounded fact success — `100%`;
* role violations — `0`;
* ungrounded publications — `0`;
* unchanged failed action retries — `0`;
* required recovery success rate — не менее `90%`;
* value mismatch attempts — `0`;
* wrong-authority selections — `0`;
* undeclared dependency waits — `0`;
* post-completion drift — `0`.

Невыполнение любого обязательного условия означает итоговый результат `Failed`.

---

## 7. Сводный результат

| Метрика | `fifth_model` | `third_model` | `fourth_model` |
| --- | ---: | ---: | ---: |
| Успешные trials | 30/35 | 30/35 | 30/35 |
| Пройденные сценарии | 6/7 | 6/7 | 6/7 |
| V2-07 | 0/5 | 0/5 | 0/5 |
| Grounded requirements | 108/120 | 102/120 | 90/120 |
| Grounded success | 90% | 85% | 75% |
| Required recoveries | 19/20 | 15/20 | 19/20 |
| Recovery success | 95% | 75% | 95% |
| Invalid actions | 0 | 15 | 2 |
| Unchanged failed retries | 21 | 11 | 15 |
| Aggregate role-violation rate | 0 | 0.020661 | 0.00335 |
| Exact-value validations | 30 | 42 | 27 |
| Recoverable failed tools | 19 | 25 | 14 |
| Conflict-resolution steps | 5 | 5 | 5 |
| Inter-role handoffs | 79 | 87 | 47 |
| Итоговый gate | **Failed** | **Failed** | **Failed** |

* Результаты `fifth_model` подтверждены experiment summary полного cohort.
* Результаты `third_model` подтверждены experiment summary полного cohort.
* Результаты `fourth_model` подтверждены experiment summary полного cohort.

---

## 8. Результаты по сценариям

Все три модели показали одинаковое распределение успешных trials:

| Сценарий | `fifth_model` | `third_model` | `fourth_model` |
| --- | ---: | ---: | ---: |
| `article_file_handoff_v2` | 5/5 | 5/5 | 5/5 |
| `office_shared_fact_recovery_v2` | 5/5 | 5/5 | 5/5 |
| `role_boundary_exact_handoff` | 5/5 | 5/5 | 5/5 |
| `malformed_action_recovery` | 5/5 | 5/5 | 5/5 |
| `conflicting_grounded_facts` | 5/5 | 5/5 | 5/5 |
| `dependency_progress_and_finish_guard` | 5/5 | 5/5 | 5/5 |
| `long_horizon_multi_fact_retention` | 0/5 | 0/5 | 0/5 |

Суммарно:

```text
90/105 trials succeeded
15/105 trials failed
```

Все 15 failures относятся к одному сценарию — V2-07.

---

## 9. Анализ `fifth_model`

### Сильные стороны

`fifth_model` — наиболее чистая из трёх моделей по формальному соблюдению action contract:

* `0` invalid actions;
* нулевая aggregate role-violation rate;
* `0` ungrounded publication attempts;
* `0` value mismatch attempts;
* `0` undeclared dependency waits;
* `0` post-completion drift;
* required recovery rate `95%`.

Модель прошла все шесть коротких и средних сценариев с результатом `5/5`.

### Причины failure

Основной блокирующий результат:

```text
long_horizon_multi_fact_retention: 0/5
```

Все пять V2-07 trials завершились по `max_turns_total`. Это привело к:

* общему результату `30/35`;
* grounded result `108/120`;
* пяти long-horizon failures;
* `21` unchanged failed action retries.

### Классификация

`fifth_model` лучше других моделей соблюдает локальный action protocol, но не умеет стабильно завершать длинную многошаговую retention-траекторию в рамках фиксированного лимита.

Итог:

```text
Behavioral v2: Failed
Основной failure mode: long-horizon policy non-convergence
```

---

## 10. Анализ `third_model`

### Сильные стороны

* все шесть non-retention сценариев пройдены `5/5`;
* наибольшее число exact-value validations — `42`;
* наибольшее число inter-role handoffs — `87`;
* `0` ungrounded publication attempts;
* `0` value mismatch attempts;
* `0` undeclared dependency waits;
* `0` post-completion drift.

### Причины failure

Помимо V2-07 `0/5`, модель нарушила несколько глобальных требований:

* grounded success — `85%`;
* recovery success — `75%`, ниже порога `90%`;
* aggregate role-violation rate — `0.020661`;
* invalid actions — `15`;
* unchanged failed retries — `11`;
* пять unresolved premature-finish agents.

Хотя модель совершала больше validations и handoffs, увеличение активности не привело к более высокой итоговой корректности.

### Классификация

`third_model` демонстрирует активное использование инструментов и межролевых операций, но хуже соблюдает формальные ограничения и recovery contract.

Итог:

```text
Behavioral v2: Failed
Основные failure modes:
- long-horizon policy non-convergence
- insufficient required recovery
- role/action contract violations
```

---

## 11. Анализ `fourth_model`

### Сильные стороны

* шесть non-retention сценариев пройдены `5/5`;
* required recovery rate — `95%`;
* только `2` invalid actions;
* `0` ungrounded publication attempts;
* `0` undeclared dependency waits;
* `0` post-completion drift;
* все пять conflict scenarios содержали успешный resolution step.

### Причины failure

* V2-07 — `0/5`;
* grounded success — `75%`, худший результат из трёх;
* aggregate role-violation rate — `0.00335`;
* unchanged failed retries — `15`;
* общий результат — `30/35`.

Число inter-role handoffs составило `47`, заметно меньше, чем у двух других моделей. Однако это не является самостоятельным критерием качества: важен не объём действий, а выполнение контрактов.

### Классификация

`fourth_model` успешно справляется с ограниченными сценариями и recovery rate, но показывает наиболее слабое суммарное выполнение grounded requirements.

Итог:

```text
Behavioral v2: Failed
Основные failure modes:
- long-horizon policy non-convergence
- insufficient grounded completion
- repeated failed actions
```

---

## 12. Сравнительная интерпретация

### 12.1. Общий успешный контур

Все три модели устойчиво справились с:

* чтением и использованием grounded source;
* точной публикацией shared facts;
* базовой межролевой передачей;
* восстановлением после malformed action;
* разрешением конфликтующих источников;
* dependency-aware progression;
* guarded finish в коротких и средних траекториях.

Результат `5/5` по шести сценариям для каждой модели показывает, что architecture и scenario contracts исполнимы реальными моделями.

### 12.2. Общий блокирующий контур

Ни одна модель не завершила ни одного V2-07 trial:

```text
0 successful trials из 15
```

Общий паттерн указывает на неспособность текущих моделей стабильно поддерживать длинную последовательность обязательств, включающую:

* несколько точных фактов;
* несколько файлов;
* межролевые handoffs;
* recovery;
* authority resolution;
* retention checkpoints;
* progress-aware dependency handling;
* guarded completion;
* отсутствие регрессии уже выполненных требований.

### 12.3. Почему 30/35 недостаточно

Формально каждая модель получила одинаковые `85.7%` успешных trials. Однако benchmark специально требует минимальной успешности в каждом сценарии.

Результат `0/5` в одном сценарии нельзя компенсировать идеальным выполнением остальных шести, поскольку V2-07 проверяет отдельную критическую способность — long-horizon retention.

### 12.4. Почему нельзя выбрать победителя по ресурсам

Correctness gate имеет лексикографический приоритет:

```text
сначала корректность
затем ресурсы
```

Поскольку все модели получили `Failed`, показатели latency, VRAM, throughput или energy use могут использоваться только для описательного сравнения. Они не могут превратить не прошедшую correctness модель в победителя benchmark.

---

## 13. Ранжирование без объявления победителя

Официального победителя нет. При этом можно дать ограниченную описательную характеристику.

### По соблюдению action contract

1. `fifth_model`
2. `fourth_model`
3. `third_model`

Основание: invalid actions и role violations.

### По grounded completion

1. `fifth_model` — 90%
2. `third_model` — 85%
3. `fourth_model` — 75%

### По required recovery

1. `fifth_model` — 95%
2. `fourth_model` — 95%
3. `third_model` — 75%

### По количеству unchanged failed retries

1. `third_model` — 11
2. `fourth_model` — 15
3. `fifth_model` — 21

Это не итоговое ранжирование качества. Метрики описывают различные стороны поведения и не заменяют обязательный gate.

---

## 14. Failure taxonomy

### Общий failure

```text
long_horizon_multi_fact_retention
15 failures из 15 trials
```

Классификация:

```text
model-policy failure
long-horizon non-convergence
failure to satisfy retention contract before terminal limit
```

### Дополнительные failures `fifth_model`

* unchanged failed retries;
* недовыполненные grounded requirements;
* max-turn exhaustion в V2-07.

### Дополнительные failures `third_model`

* required recovery ниже порога;
* role violations;
* invalid actions;
* premature finish;
* unchanged failed retries;
* недовыполненные grounded requirements.

### Дополнительные failures `fourth_model`

* role violations;
* invalid actions;
* unchanged failed retries;
* наиболее низкий grounded completion;
* long-horizon completion failure.

---

## 15. Что результаты не доказывают

Отчёт не доказывает, что:

* модели непригодны для всех агентных задач;
* увеличение turn limit обязательно исправит V2-07;
* более быстрая модель будет более корректной;
* большее число tool calls означает лучшее reasoning;
* один общий failure автоматически доказывает ошибку runtime.

На основании cohort не было получено нового свидетельства о generic runtime defect. До запуска cohort code path был покрыт deterministic regression tests, включая genuine retention success и failure cases.

---

## 16. Ограничения исследования

1. Использовалось три локальных model artifacts.
2. Каждый scenario/model pair проверялся пять раз.
3. Runtime использовал логическую round-robin concurrency, а не параллельный inference.
4. Browser, Playwright и внешняя сеть не использовались.
5. Resource measurement не входил в behavioral cohort.
6. Результаты относятся к конкретным GGUF, prompt contracts, server configuration и commit `5826c8c`.
7. Изменение sampling, context size, prompts или turn limits создаст другой benchmark condition и потребует отдельной серии испытаний.
8. Cohort нельзя автоматически повторять только для получения более благоприятного результата.

---

## 17. Итоговый вывод

Behavioral Benchmark v2 завершён полностью:

```text
3 модели
7 сценариев
5 trials на сценарий
105 real-model trials
90 successful trials
15 failed trials
0 моделей прошли gate
```

Главный вывод:

> Все три модели надёжно выполняют ограниченные многоагентные сценарии, но ни одна не демонстрирует достаточную устойчивость в длинной retention-траектории.

`fifth_model` показал лучшее соблюдение action и role contract, однако также не прошёл обязательный long-horizon сценарий. `third_model` чаще нарушал action/recovery contract. `fourth_model` показал наиболее низкий grounded completion.

Официальный результат:

```text
fifth_model  — Failed
third_model  — Failed
fourth_model — Failed

Behavioral Benchmark v2 winner: none
```

---

## 18. Рекомендуемые следующие действия

1. Заморозить все три cohort artifact directories как итоговые evidence.
2. Не повторять существующие trials без изменения заранее объявленного experimental condition.
3. Не повышать turn limits и не ослаблять V2-07 gate внутри текущей версии benchmark.
4. Использовать resource harness только для отдельного описательного профилирования.
5. Для следующего этапа исследовать новые модели или новый заранее объявленный экспериментальный профиль.
6. Сравнивать новый cohort с текущим baseline `5826c8c`, не изменяя постфактум критерии прохождения.

---

## 19. Artifact locations

```text
artifacts/canonical_multi_agent_experiments/
  behavioral_v2_fifth_model_5826c8c/
  behavioral_v2_third_model_5826c8c/
  behavioral_v2_fourth_model_5826c8c/
```

Каждый каталог содержит:

* `experiment_summary.json`;
* семь scenario directories;
* пять trial directories на сценарий;
* `trial_summary.json`;
* `group_trace.jsonl`;
* созданные scenario artifacts.

---

## 20. Финальный статус среды

```text
Commit                : 5826c8c
ActiveModelServers    : 0
TrackedTreeClean      : True
FifthModelTrials      : 35
ThirdModelTrials      : 35
FourthModelTrials     : 35
TotalBehavioralTrials : 105
ModelsPassingGate     : 0
```
