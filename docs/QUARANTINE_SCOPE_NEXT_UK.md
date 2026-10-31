# Cross-receipt run quarantine: реалізація й acceptance

2026-10-28. Вихідний план вузького пакета збережений нижче як acceptance
критерії. Source-level реалізація та перевірки завершені; документ не означає
готовність live MQTT worker або ввімкнення облікового списання.

Поточні guards захищають terminal receipt, що сам потрапив у quarantine,
та job із lifecycle conflict. Quarantine іншої події run ще не створює
автоматично run-level blocker. Не вмикати live writer до цього приймання.

1. Після ProjectionRejected у новому BEGIN IMMEDIATE повторно прочитати
   receipt та projection application. Якщо інший worker уже застосував
   receipt або accounting уже позначив його PROCESSED, не створювати хибну
   quarantine. Persistence/commit errors далі не приховувати.
2. Для валідного JobMessage повторно перевірити printer/epoch/event scope
   проти незмінного receipt. Визначати run лише provider/printer/PRINTER/
   epoch/occurrence; не filename/hash/sequence і не «найімовірніший» job.
3. Для вже наявного alias можна підняти deduplicated job lifecycle blocker
   без переписування підтверджених facts. Для run без alias потрібний окремий
   scoped run blocker: digest canonical identity, без payload чи секретів.
   Він має зберігатися до майбутнього створення alias та перевірятися обома
   accounting ядрами. Простого пошуку поточного job недостатньо.
   Чистий application.job_conflicts.run_quarantine_key(alias) вже доданий:
   SHA256 JSON array[run-quarantine-v1,*alias.occurrence_scope] зі str values,
   separators(',',':'), стандартним ensure_ascii=True. Він не залежить від
   alias/job IDs, file hash чи delivery metadata; 2tests/5subtests успішні.
   Підключення цього ключа до quarantine/task та обох kernels ще НЕ виконане.
4. Визначити явне ручне resolution пов’язаних receipt/run задач. Не видаляти
   blocker автоматично через наступну нормальну подію; не вимагати merge
   aliases за часом або кольором. Невідомий/некоректний payload лишається
   receipt quarantine без вигаданої run identity.
5. Приймання: future terminal іншого receipt known run блокує обидва ядра;
   quarantine до першого start також блокує пізніший alias того самого run;
   інший printer/provider/epoch/occurrence не блокується; два workers між
   apply і quarantine не створюють false incident; після FINALIZED ledger
   не змінюється; manual resolution/retry явно перевірені.

## Прийнятий доказ

- `ProjectionDrain` повторно перевіряє marker та стан receipt у новому
  writer UoW; уже застосовані або оброблені receipts не отримують quarantine.
- Run blocker додається тільки після точного scope validation; blocker працює
  до створення alias і збігається з його майбутнім occurrence scope.
- Обидва фіналізатори перевіряють blocker саме для alias, що відповідає
  фінансовому receipt; blockers іншого run ізольовані.
- Ручне розв’язання кожної receipt/run задачі окреме, з нотатками та audit;
  звичайна подія не очищує incident автоматично.
- `tests/integration/test_projection_drain.py`,
  `tests/integration/test_print_finalization.py`,
  `tests/integration/test_calculated_batch_edges.py`:13 drain tests та4
  фінансові acceptance tests. Повний suite494passed/452subtests; Ruff і
  mypy clean. Wheel smoke SHA256
  `1f1175e2466855dd16c6f8f8b42b1fd4a01dc85c05879b3fea604a160e1c90b1`.

Не входять до цього приймання: live MQTT/hardware sequencing, нативний екран
ручного звіряння, provider boot і writer cutover. Installed EXE та реальні
бази не змінювалися.
