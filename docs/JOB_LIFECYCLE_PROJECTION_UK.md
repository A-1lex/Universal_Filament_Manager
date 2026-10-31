# Стійкі спостереження про друк

2026-10-28. Application JobProjectionCommands та нова additive revision
0002_job_projection прийняті на тестових базах. Постійний MQTT worker і
встановлений EXE ще не підключені. Реальні бази не мігрувалися.

Оновлення 2026-10-29: strict `JobMessage` тепер може нести окремі optional
`exact_started_at` та terminal `exact_ended_at` разом із явним джерелом
`printer_reported`/`provider_reported`. Projection зберігає їх у вже наявні
`PrintJob.started_at` і відповідне terminal поле, а provenance лишається в
immutable receipt та `mapping_history()`. Нової DDL-міграції не потрібно.
Поточні Bambu LAN/HTTP adapters все ще лишають точні часи й provenance порожні;
live receipt consumer відсутній, списання не активоване.

## Ідентичність та відновлення

Job/alias визначається provider instance + printer + PRINTER source + epoch
+ occurrence. Filename/hash/sequence не є identity. Два запуски того самого
файла окремі; reconnect і replay того самого scope не створюють новий job.
Нова occurrence/epoch під час іншого активного run зберігається окремо,
а обидва runs потрапляють на звіряння. Старий підтверджений job/alias без
projection cursor не переписується автоматично.

job_projection_state зберігає latest observation, nullable completed-layer
COUNT і перший terminal receipt/state. job_receipt_application — окремий
immutable marker для кожного застосованого receipt. Все записується одним
BEGIN IMMEDIATE разом із job/alias/audit/reconciliation. Projection queue
вибирає ще не застосовані receipts через anti-join marker; terminal receipt
лишається accounting PENDING, доки відповідне ядро не проведе витрату.

observed_at — час спостереження, не підтверджений фізичний start/end.
Точний source start/end зберігається лише коли message явно передає його з
дозволеним provenance; adapters без такого джерела лишають значення NULL.
completed_layers не копіюється
у current_layer. Plate/tool/material/slot/segment/reservation/evidence не
вигадуються. Цей reducer не записує ledger і не є готовим автосписуванням.

На vendor-neutral provider DTO `PrintJobSnapshot.exact_started_at` тепер
приймається лише разом з `exact_started_at_source` (`printer_reported` або
`provider_reported`). Час спостереження адаптера не є дозволеним джерелом.
Поточні Bambu LAN та HTTP adapters обидва лишають точний start і provenance
порожніми; перевірено тестами. Ця межа DTO не змінює durable `JobMessage v1`,
міграцію 0002 чи облікове ядро; для збереження факту в lifecycle ще потрібен
окремий версійований контракт і міграція.

## Конфлікти та порядок

Перший terminal sticky; інший terminal завжди створює conflict. Пізня стара
running-подія не регресує стан; новіша чи неоднозначна running після terminal
вимагає звіряння. Зміна відомого file hash, зменшення count у новішій події,
повторний start чи неоднозначний порядок також не перезаписують факти.
sequence зберігається як delivery metadata, не замінює chronology.

Task job:{UUID}:lifecycle_conflict дедуплікується, блокує новий debit в actual
і calculated ядрах, навіть коли проблема прийшла з іншого receipt. Після
FINALIZED конфлікт не переписує ledger; перевірений replay доступний.
Deleted/future cursors відхиляються. SQL та repository захищають terminal
facts від зміни, marker від UPDATE/DELETE, receipt/job printer scope.

## Міграція й постачання

Frozen0001 та print_job не змінені. Перед upgrade validated0001 створюється
узгоджений verified snapshot під writer reservation, до DDL; невдалий backup
зупиняє upgrade. Default: поруч із базою backups/migrations/UUID. Latest
no-op не створює копій. Невідомі/unversioned schemas не оновлюються.
Старий EXE з v1 не слід підключати до upgraded v2; повернення — через
перевірену копію в новий файл, не SQL downgrade. Оновлення реальної програми
потребує окремої перевірки cutover та відновлення.

## Перевірки

- 15 independent lifecycle tests /5subtests; 3 crash/queue/terminal tests /5subtests.
- Migration21tests/27subtests: populated v1 backup/upgrade, exception/process
  rollback, constraints, immutable/scope/terminal guards, unknown/latest paths.
- Чотири нові financial guard/replay scenarios для конфлікту іншого receipt.
- Повний suite448tests/427subtests; Ruff clean, mypy113sourcefiles clean.
- Перебудований wheel поза checkout: 8module origins, v2 migration/no-op,
  resources, queue та Decimal smoke успішні; WORKER_WHEEL_ACCEPTANCE_UK.md.

Known next integration requirement: rejected unavailable/malformed/future
receipts можуть залишатися в projection pending. Drain worker повинен мати
skip/backoff/quarantine без голодування наступних подій. Receipt identity
conflicts уже пропускаються до явного resolution. Далі потрібні durable
parser artifacts, verified start/plate/material binding та accounting owner.
