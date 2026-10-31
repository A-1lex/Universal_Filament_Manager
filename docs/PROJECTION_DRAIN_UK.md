# Обмежена обробка черги спостережень

2026-10-28. ProjectionDrain.run_once(actor_device_id,limit=100,at) виконує
один bounded прохід, не створює scheduler, network worker або ledger writes.
Повертає DrainResult(applied,ignored,conflicts,quarantined).

Кожний receipt обробляється окремим UoW. Бізнес-відмова ProjectionRejected
зберігає deduplicated OPEN/ERROR task receipt:{UUID}:projection_rejected,
reason PROJECTION_OBSERVATION_REJECTED, static suggested action. Payload,
path, credentials або текст винятку в задачу не потрапляють. Receipt не
позначається PROCESSED. Черга пропускає відкриті quarantine/identity tasks
і disabled/deleted printers, тому відхилена подія не утримує першу сторінку.
Після явного resolution задача більше не виключає receipt з повторного проходу.

PersistenceError та неочікувані помилки не приховуються: прохід переривається,
раніше завершені UoW лишаються чинними, невдалий quarantine commit не
повідомляється як успіх. Обидва accounting ядра відхиляють нове списування
за власним quarantined terminal receipt; попередній immutable replay не змінює
залишку. Відкритий lifecycle blocker іншого receipt також перевіряється.

Якщо reducer відхиляє receipt, drain починає нову транзакцію `BEGIN IMMEDIATE`
і повторно читає receipt та projection marker. Уже застосований receipt,
видалений receipt або receipt з результатом `PROCESSED` не отримує хибний
quarantine. `PersistenceError` та неочікувані помилки як і раніше виходять
назовні.

Для коректного `JobMessage` drain додатково звіряє printer, source epoch та
event type зі сталим receipt. Run визначається тільки точним scope
provider/printer/`PRINTER`/epoch/occurrence. Утворюється окремий digest-key
`run:<sha256>:projection_rejected`, незалежний від job id, filename, file hash,
request id або sequence. Якщо alias ще немає, blocker усе одно зберігається;
майбутній alias утворить той самий key. Невалідний/невідомий payload отримує
лише receipt-level задачу, без вгадування запуску. Run-level задача має
необов’язковий `print_job_id`, якщо точний alias уже знайдений, та audit event
без сирого payload.

Actual і calculated finalization тепер шукають відкритий run blocker лише для
alias, який точно відповідає receipt та occurrence; інші provider/printer/epoch/
occurrence не перетинаються. Після `FINALIZED` попередній immutable replay
залишається безпечним і не змінює ledger. `ProjectionQuarantineResolution`
дозволяє оператору явно розв’язати одну receipt- або run-level задачу з
обов’язковими нотатками й audit event. Пов’язані задачі розв’язуються окремо;
звичайна наступна подія їх не закриває. Нативний екран ручного звіряння ще не
підключений.

Приймання цього source-level пакета:13 drain tests,4 actual/calculated
financial tests, включно з паралельним apply/quarantine interleaving,
PROCESSED-race, quarantine до першого alias, scope isolation, explicit
resolution/retry та replay після фіналізації. Повний suite494passed/452subtests,
Ruff clean, mypy117files clean. Acceptance
wheel132entries пройшов поза checkout; див. WORKER_WHEEL_ACCEPTANCE_UK.md.
Це не live MQTT/hardware acceptance і не встановлений native release.

E07.06 закритий для наявного durable source contract. E07.04/05 лишаються
частковими: live MQTT sequencing/reconnect та hardware/provider acceptance
потребують окремого кроку. Поточне writer policy лишається default-disabled.
