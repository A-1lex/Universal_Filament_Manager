# Розрахункове пакетне списання: реалізація та приймання

Дата: 2026-10-28. Стан: базове й пакетне приймання пройшли: 23 тести,
4 підперевірки, включно з process-crash/restart. Не вважати
всі E09/E10/E11 виконаними лише за наявністю цього коду.
Установлений EXE й робочі дані не змінювалися; live автоматизація не ввімкнена.

## Від перевіреного файла до пропозиції

`integrations/haspel_calculation.py` та `integrations/haspel_worker.mjs`
з’єднують VerifiedSliceFacts із bounded CalculationWorkerTransport і canonical
ProposalMessage. Source-tree Node entrypoint використовує pure HaspelSync
calculation exports; його runtime/engine ще не запаковані в дистрибутив.

Full policy `three-mf-full-mg-preview-v1` зберігає точні міліграми з metadata.
Partial policy `haspel-range-cent-preview-v1` рахує кожний logical material
окремо за його ranges, не об’єднує однакові profile/color, не вмикає неявний
global fallback. Усередині діапазону збережена legacy точність 0.01 г; після
останнього його шару повертається точна full-file маса, без втрати міліграмів.
Немає ranges — немає цього partial розрахунку. G-code extrusion ще не використано.

Preview має quantity=estimate, позначку «Розрахункова витрата», confidence=0
(оцінку довіри worker не призначає), needs_mapping та порожні allocations.
Він сам не проводить залишки. Реальні Node-тести: 4 passed / 6 subtests.
На першому запуску виявлено втрату 5 мг через JS legacy округлення на повному
покритті; виправлено явним поверненням точного metadata total для завершених ranges.

## Новий сервіс проведення

`application/calculated_finalization.py`: async CalculatedFinalizationCommands.
Залежності — application ports SliceCalculator/SliceFileReader та UnitOfWork.
DTO facts перенесені в application/dto/slice_facts.py; старі imports із
integrations/sliced_files.py збережені як явні compatibility reexports.

Перед прийняттям нової операції потрібні:

- явна EstimatedUsagePolicy.enabled; за замовчуванням False;
- окремі дозволи unknown purge, range partial, manual splits;
- persisted THREE_MF/ESTIMATE evidence для кожного закритого assigned сегмента;
- canonical job/file hash/plate, terminal receipt, alias occurrence, незмінний
  provenance з hash файла/metadata/G-code, parser/calculation policy, mg,
  logical totals, allocation та partial layer;
- для COMPLETED completed_at, для FAILED failed_at, для CANCELLED cancelled_at;
  рівно один terminal timestamp, повне покриття інтервалу кожного матеріалу;
- сума сегментів дорівнює перевіреній логічній витраті, без пропусків/дублів;
- для кількох сегментів одного material — явний manual-confirmed split,
  estimated_usage та immutable audit підтвердження; автоматичного rollover
  за часом/кольором тут не вигадується;
- відомий consistent stock, початковий запис до друку, відсутнє наступне
  зважування, достатній залишок після чужих резервів.

Файл і Node-розрахунок перевіряються поза writer-lock. Потім під BEGIN IMMEDIATE
повторно читаються всі факти та fingerprint. Один UoW записує finalization,
decision/evidence links, усі ledger/projections, settlement власних резервів,
job/receipt states, audit і low-stock alert. Окремий decision/ledger на кожний
ненульовий segment, sequential balances при повторному використанні котушки.
Нульовий segment не створює debit. Settlement виконується один раз на пару
material/spool; невикористаний власний резерв звільняється.

Replay перевіряє request та result hashes, усі decisions/links/ledger items/
settlements/audit і processed receipt. Після commit файл не потрібен для
повтору; пізніші коректні ручні операції не змінюють початковий результат.
Default PRINTER/ABSOLUTE FinalizationCommands не послаблений.

## Provenance та інтерфейс

ConsumptionEvidence.metadata_json, FilamentTransaction.metadata_json та
description відображають уже наявні v1 колонки: schema/migration не змінені.
Domain JSON validation bounded, відхиляє duplicate keys/NaN/Infinity literals.
Додані read-порти ledger by command/job, decision evidence links і settled
reservations для перевірки повного результату, а не тільки ledger item 0.

Ledger source=THREE_MF, description=«Розрахункова витрата», policy/version,
confidence та provenance зберігаються явно. Qt history позначає file/slicer/
progress sources українською або англійською; PRINTER не позначається як
розрахунковий. Qt-набір із новим сценарієм: 5 passed. Деталі job та settings
керованого автоматичного ввімкнення ще не підключені.

Policy confidence 8000 для full та 6000 для range partial — версійований
policy score, не статистична ймовірність і не фізичне вимірювання.
Unknown purge лишається None й потребує окремого дозволу. Manual split
підтверджує розподіл оцінки, а не фактичну зважену масу.

Пройшли success/replay після ручної витрати/видалення файла/вимкнення policy,
відмови зміни actor/key/evidence, immutable provenance, audit rollback,
real Node → verified file → ledger. Окремі 7 batch tests перевіряють повторну
котушку з послідовними балансами й одним settlement, дві котушки, повний
rollback за нестачі другої, відмову непідтвердженого split, FAILED partial,
нульовий CANCELLED без ledger debit та конкурентні async завершення.
Додатково пройшли два паралельні потоки, subprocess os._exit до/після commit,
відновлення й replay, два logical materials однакового кольору без об’єднання,
захист чужого резерву, пізнє зважування та відсутня частина evidence.
Повний набір: 402 тести / 366 підперевірок; Ruff та mypy 107 files успішні.

Наступне: ширші негативні scope сценарії та UI mapping. Durable receipt intake
вже реалізований окремо; потрібні lifecycle reducer, file artifacts,
owner/cutover та live UI/worker integration.
