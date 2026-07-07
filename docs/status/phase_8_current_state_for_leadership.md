# Phase 8: текущий статус для руководства

## 1. Краткое резюме

Проект проверяет, может ли связка локальных LLM-агентов выполнять рабочие сценарии в контролируемой среде: один агент планирует, другой исполняет, а система валидирует действия, собирает артефакты и оценивает результат.

На текущем этапе подтвержден успешный контролируемый mini-matrix прогон для пары `second_model -> first_model` на офисном сценарии с реальными DOCX-артефактами. Детерминированная проверка исполнения прошла полностью: все три повтора успешны, все офисные действия выполнены, все созданные DOCX-файлы читаются.

Семантическая оценка LLM-as-a-judge подготовлена инфраструктурно, но не запускалась. API judge runner добавлен только в guarded-режиме и требует отдельного operator opt-in и ключа.

## 2. Что реализовано по спецификации

- Локальная orchestrator/executor пара `second_model -> first_model`.
- Основа virtual network и scenario policy для контролируемых сценариев.
- Browser/Playwright scaffold без автоматического запуска браузера.
- Office actions для DOCX/XLSX/PPTX-типов через валидируемый action registry.
- Реальный document-file office backend для controlled DOCX execution.
- Controlled single-trial runner для одного проверяемого прогона.
- Compact prompt budget для локальных trial runs.
- Action repair для безопасного восстановления model-produced office action paths.
- DOCX append precreate, когда append-цель отсутствует.
- Mini-matrix из 3 повторов для controlled single-trial workflow.
- Детерминированный сбор office artifacts.
- Детерминированный correctness scoring по execution/artifact criteria.
- Matrix adapter outputs: normality inputs и resource observations.
- Flagship judge prompt exchange как offline prompt pack.
- Guarded API judge runner, который не выполняется без явного разрешения и локальной конфигурации.

## 3. Подтвержденные результаты

По текущему `phase_8_26_mini_matrix_r3` aggregate summary:

- 3/3 mini-matrix repeats succeeded.
- 6/6 office actions executed successfully.
- 6/6 DOCX artifacts generated and readable.
- Deterministic execution correctness score count = 3.
- Mean deterministic execution correctness = 1.0.
- Normality input count = 3.
- Resource observation count = 3.
- Semantic LLM judge score = not run yet.

## 4. Что это означает

Проект перешел от плановых и stub-проверок к контролируемому выполнению office document workflow с реальными файловыми артефактами. Это сильный сигнал, что базовая цепочка "orchestrator plan -> executor actions -> validation -> real office artifact -> deterministic scoring" работает на коротком, ограниченном сценарии.

Результат пока не является production-grade доказательством. Он подтверждает feasibility для выбранной пары, выбранного сценария и малого N=3, а не универсальную надежность всех сценариев и моделей.

## 5. Ограничения

- Semantic LLM-as-a-judge score пока не получен.
- DeepSeek/openai-compatible judge provider не реализован в этой фазе.
- Live API judge не запускался из-за отсутствия готового operator key/config opt-in.
- Mini-matrix покрывает один controlled office scenario, а не полный набор рабочих процессов.
- Browser/Playwright и real browser/network actions остаются scaffold/guarded и не запускались.
- MS Office/LibreOffice не запускались автоматически; office backend работает через контролируемые file-level actions.
- GGUF/model files не входят в репозиторий.
- Нет production scheduler и production autonomous loop.

## 6. Текущая стадия

Последняя реализованная code stage перед этим статусом: `71f66dd Add guarded flagship API judge runner`.

Текущий репозиторный статус после этого документационного шага: Phase 8 controlled execution доказана детерминированно, semantic judge остается следующим отдельным этапом.

## 7. Рекомендуемые следующие шаги

1. Спланировать Phase 8.30: budget LLM-as-a-judge provider для openai-compatible/DeepSeek-style API без автозапуска.
2. Добавить dry-run first workflow для judge provider, чтобы проверять конфиг, schema и prompt pack без live API call.
3. После operator approval и ключа выполнить один guarded judge run на уже собранном prompt pack.
4. Расширить mini-matrix на дополнительные сценарии только после фиксации semantic judge path.
5. Сохранить правило: runtime artifacts и local judge configs не коммитятся.

## 8. Риски

- Semantic judge может изменить итоговую качественную оценку, даже если deterministic execution score равен 1.0.
- Короткий N=3 не заменяет долгий robustness/stress test.
- Office action repair/precreate полезны для controlled flow, но требуют дальнейших negative tests.
- Любой live API judge требует строгого контроля секретов, стоимости и provenance.
- Production claims преждевременны до расширения сценариев, моделей и длительности прогонов.

## 9. Попунктная сверка с ТЗ

Подробный отчёт в структуре исходного технического задания:
`docs/status/tz_point_by_point_completion_report.md`
