# Протокол внутрішнього calculation worker v1

E03.05, 2026-10-27. Реалізація моделей:
`src/ufm/application/dto/worker_protocol.py`. Код не підключений до live
worker/GUI і не дозволяє списування. ADR: [INTEGRATION_DECISION_UK.md](INTEGRATION_DECISION_UK.md).

JSON Schema 2020-12 згенеровані окремо за напрямами:
[worker → parent](WORKER_PROTOCOL_V1.schema.json) та
[parent acknowledgement → worker](WORKER_PARENT_OUTCOME_V1.schema.json).
Для вхідного worker stdout застосовується тільки перша схема; у ній немає
finalization_outcome. Runtime Pydantic guards залишаються авторитетними.

## Envelope і транспорт

Кожен message містить явні `v=1`, `kind`, `request_id`, `printer_id` UUID,
`source_epoch`, `sequence`, timezone-aware `observed_at`. Батьківський
процес додає власний received_at. Максимум 512 KiB на UTF-8 JSON frame;
обмежений reader має застосовувати межу ще до накопичення всього stdout.
Строкові ідентифікатори bounded, невідомі поля/версії/kinds відхиляються.
JSON duplicate keys, NaN/Infinity, bool-as-int, float-as-mg й numeric strings
не приймаються. Відмова назовні — лише `worker.frame_invalid`, без raw payload
або ValidationError, що містить input. Логи не повинні писати сирі facts.

Envelope не є автентифікацією. Parent зіставляє printer/epoch/request із
власним registry spawned process; чужий scope, запізнілий або конфліктний
response не має права перейти до проведення. Sequence допомагає порядку,
але не замінює стійку identity receipt та job occurrence.

## Напрями та payload

| kind | Напрям | Обов’язкові факти / значення |
|---|---|---|
| status | worker → parent | connected/offline/retrying/disabled, optional reason_code |
| job | worker → parent | occurrence_key, started/running/paused/completed/failed/cancelled, optional file_sha256, layer/progress та точні lifecycle timestamps із джерелом |
| slots | worker → parent | <=256 унікальних slot_key, optional logical_material та identifier; occurrence_key якщо відомий |
| evidence | worker → parent | occurrence_key, file hash, plate, source, estimate/measurement, confidence_bp, includes_purge nullable, interval start/end |
| proposal | worker → parent | occurrence_key, file hash, evidence_id, policy_version, estimate, точна позначка «Розрахункова витрата», confidence, partial, logical materials та spool allocations |
| error | worker → parent | bounded code, retryable; жодного довільного exception text |
| finalization_outcome | parent → worker | job_id, receipt_id, committed/already_committed/rejected, finalization_id або reason_code |

`decode_worker_message()` не включає finalization_outcome у допустиму union:
worker не може сам оголосити проведення прийнятим. Parent формує outcome
лише після commit або підтвердженого replay, а не за прапорцем у stdout.
Це acknowledgement; команди SQL, HTTP `/spool/use` чи ledger mutation у
протоколі відсутні. Експериментальний calculate.mjs має окремий спрощений
request/response для порівняння; його ще потрібно адаптувати до цих DTO.

У `JobMessage` необов’язкові `exact_started_at` та `exact_ended_at` приймаються
лише разом із `exact_started_at_source`/`exact_ended_at_source` (`printer_reported`
або `provider_reported`). Кінцевий час дозволений лише для terminal state; якщо
обидва моменти відомі, кінець не може передувати початку. `observed_at` не
підставляється замість жодного з них. Довірене projection ядро зберігає час у
вже наявні `print_job.started_at` та відповідне completed/failed/cancelled поле;
immutable receipt лишається носієм provenance. Відсутність точного джерельного
часу лишає значення NULL і не створює підтвердженого інтервалу. Ця опційна
добавка до ще не підключеного v1 DTO не змінює схему БД та не активує live
provider-ingestion.

## Evidence та розподіл

File evidence three_mf/gcode/slicer має quantity=estimate; заборонено
підмінювати його фізичним measurement. Printer measurement теж залишається
твердженням джерела, яке parent перевіряє за адаптером і policy. Interval
не може закінчуватися раніше початку, confidence — 0..10000 basis points.
Невідоме includes_purge не перетворюється на true.

Proposal містить 1..256 унікальних logical materials із невід’ємними цілими
mg. Не агрегувати їх лише за однаковими profile/color — два матеріали можуть
мати різні котушки. До 1024 allocations: унікальні allocation_id/segment_id,
logical material, spool_id, точна маса. Сума allocations за кожним logical
material не перевищує estimate. Ready вимагає повного точного покриття всіх
матеріалів; needs_mapping може мати неповне покриття й не фіналізується.
Одне logical material може розподілятися між кількома котушками через різні
segments. Остаточну масу, provenance, доступний запас та резерви перевіряє
UFM, а не worker. Нульова витрата не створює zero-debit ledger entry.

## Повтор, crash та власник проведення

Ці DTO не створюють durable receipts. Parent спочатку зберігає raw-event hash,
provider/epoch/occurrence identity; потім перевіряє файл, interval, mappings і
policy. Після цього application command у єдиному UoW проводить увесь batch
або відхиляє його без часткового списання. Request ID — correlation, а не
єдиний idempotency key. Перезапуск worker може повторити proposal; лише
стійкі job/evidence/finalization records визначають, чи був commit.

Для одного принтера має бути один активний accounting owner/epoch. До
вмикання нового writer старий HaspelSync `/spool/use` треба відключити або
перевести в shadow. Lock лише всередині одного Node/Python процесу недостатній.
Enforcement owner, durable intake та batch finalization ще не реалізовані
цим DTO-модулем; їхні кроки не закриваються через наявність schema.

## Приймальні перевірки

`tests/contract/test_worker_protocol.py` перевіряє partial multi-spool exact
mg, відсутній/неправильний version, coercion/extra fields, omission/overflow/
duplicates, needs_mapping, forged acknowledgement, file-vs-measurement,
interval, oversized frame, duplicate JSON keys/nonstandard numbers та
безпечний текст помилки. Повний runtime lifecycle, timeout reader, transport
correlation та реальна фіналізація залишаються окремими інтеграційними тестами.

## Реалізований процесний транспорт

`src/ufm/integrations/calculation_worker.py` додає one-shot async exchange
через trusted absolute executable/entrypoint і окремий workdir. Дочірній
процес отримує очищений env без provider credentials, приховане вікно Windows,
stdin request <=512 KiB, stdout <=512 KiB, stderr <=4096 bytes, timeout <=60 с.
Parent перевіряє printer/epoch/request correlation. Помилка, надмірний вивід,
таймаут і скасування завершують дочірній процес; raw stderr не повертається UI.
Це не OS sandbox; запускається лише перевірений bundled entrypoint.

`tests/integration/test_calculation_worker.py`: 8 тестів і 5 підперевірок
пройшли з реальними ізольованими subprocess. Усередині sandbox Windows тест
завис; поза sandbox весь набір пройшов, завислі test-only PID перевірено й
завершено. Запускати ці тести поза sandbox із потрібним системним схваленням.
Транспорт тепер під’єднаний до source-tree Node entrypoint haspel_worker.mjs
через HaspelCalculator. Він повертає canonical ProposalMessage; 4 tests /
6 subtests перевіряють full exact mg та per-material range partial. Live
provider boot і bundled Node runtime ще відсутні; E03.06 лишається partial.

Parent→worker CalculationRequest(kind=calculate) має окремий контракт
[CALCULATION_REQUEST_V1.schema.json](CALCULATION_REQUEST_V1.schema.json),
експортований з поточної Pydantic моделі. Він містить scope/version,
occurrence/evidence/file identity, full або range policy, completed_layer,
bounded metadata XML і logical material mg. Frame limit 512 KiB додатково
перевіряє транспорт у bytes; JSON Schema maxLength — це characters.
Schema не доводить походження XML, відповідність hash або наявність фізичної
котушки: verified intake та parent policy виконують ці перевірки окремо.

Durable receipt intake і calculated batch реалізовані окремими сервісами:
[приймання подій](DURABLE_RECEIPT_INTAKE_UK.md),
[розрахункове ядро](CALCULATED_BATCH_KERNEL_UK.md).
Це не постійний job lifecycle worker і не ввімкнення автосписування в EXE.
