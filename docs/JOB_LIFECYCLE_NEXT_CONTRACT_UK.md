# Контракт наступного етапу lifecycle job

Початкова підготовка: 2026-10-27. Стан 2026-10-29: durable reducer E07.02
реалізовано; E07.03 має exact lifecycle timestamp fields із provenance у
JobMessage та запис у вже наявні PrintJob колонки. Runtime ingestion і Bambu
точні timestamps/run identity лишаються непід’єднаними. Поточні queue, alias
repository та accounting ядра зберігаються.

## Що вже доступно

- ReceiptIngestion зберігає strict JobMessage: occurrence_key, state,
  optional file_sha256/completed_layers/current_layer/progress_bp, observed_at,
  sequence та scope. Від 2026-10-29 він також приймає optional exact start/end
  timestamps лише з явним printer/provider provenance.
- JobRepository має add/save, by_alias/add_alias й читання матеріалів.
- Scoped alias identity: provider instance, printer, source_type, source_epoch,
  occurrence_key. Ім’я файла та сам hash не визначають окремий запуск.
- Receipt conflict task блокує нове проведення в обох accounting ядрах.

## Потрібні рішення перед написанням reducer

1. Розрізняти приймання lifecycle-події та проведення витрати. Terminal
   receipt не можна позначити PROCESSED як списаний до atomic finalization.
   Повтор reducer має відновити той самий job без нового debit. Для черги
   потрібний окремий durable projection cursor/receipt-job application marker;
   не перевантажувати фінальний processing_result чужим значенням.
2. Epoch та occurrence повинні переживати reconnect. Не генерувати нову
   identity за кожного TCP-сеансу; delivery sequence/request_id не є job ID.
   Receipt raw hash доводить незмінність доставки, не фізичний початок друку.
3. observed_at — час спостереження. Пропущений start не дозволяє вигадати
   started_at з часу завершення або імені файла. Зберігати неоднозначний run
   на звіряння, без створення підтвердженого облікового інтервалу.
4. Наявний JobMessage.completed_layers — кількість завершених шарів.
   PrintJob.current_layer має іншу семантику: calculated range fallback
   використовує max(-1,current_layer-2). Не копіювати count у це поле.
   Перед reducer зафіксувати окремий completed-layer cursor і версію contract/
   schema або явне перевірене перетворення. Особливо перевірити 0, перший,
   останній шар та current_layer<=total_layers. Не додавати +1 без перевірки
   граничного випадку останнього шару.
5. Plate та lifecycle start/end timestamp provenance частково передаються новим
   optional JobMessage fields; точні поля лишаються NULL, якщо джерело їх не
   підтвердило. Вони записуються у наявні PrintJob lifecycle columns без DDL.
   JobMessage усе ще не має plate identity чи material channels. Не заповнювати
   plate=1, tool=0 чи file identity за припущенням. Зв’язок із verified parser
   artifact/slot mapping має бути явним і стійким.

## Найменший приймальний пакет

Спочатку DTO/міграція для projection facts, versioned terminal policy та
іdempotent receipt→alias/job reducer в одному UoW. Жодних ledger writes у ньому.
Стійкий marker має дозволяти відновлення між projection і finalization.
Відкриті конфлікти, зміна hash у межах run, інший terminal state або reset
не перезаписують підтверджену історію; створюють deduplicated reconciliation.

Перевірки на реальній SQLite: два послідовні запуски одного файла; restart
після start; reconnect без другого job; out-of-order running після terminal;
cancel/failed pair; late complete; пропущений start; epoch/counter reset;
нуль/середина/останній completed layer; збій до/після commit і два writers.
Потім інтеграція з canonical 3MF facts/evidence та opt-in calculated kernel.
Установлений EXE підключати після цих перевірок, owner/cutover та bundle tests.
