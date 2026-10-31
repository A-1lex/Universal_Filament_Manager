# Стійке приймання подій принтера

2026-10-27. Реалізовано application/receipt_ingestion.py та SQLite read/write
ports. Це збереження нормалізованих спостережень; постійне MQTT-підключення
та створення/відновлення job projection ще не підключені.

ReceiptIngestion приймає тільки protocol v1 status/job/slots у межах 512 KiB.
Зберігає provider/printer/epoch/event identity, SHA-256 сирого повідомлення,
санітизований DTO до 64 KiB та PENDING state. Сире повідомлення й секрети
не записуються. Черга pending читається після перезапуску за received_at/id.
Приймання не змінює запасів, рішень чи ledger.

Однаковий scoped key і незмінні hash/type/semantic facts повертають перший
receipt, включно з уже обробленим. request_id, sequence, observed_at можуть
відрізнятися при повторній доставці. Зміна інших фактів або raw digest
викликає IdempotencyConflict, зберігаючи оригінал. Перед відмовою атомарно
зберігається OPEN/ERROR завдання RECEIPT_IDENTITY_PAYLOAD_CONFLICT із ключем
receipt:{UUID}:payload_conflict. Задача містить сталі action/reason keys,
без raw/normalized payload, event key чи секретів. Повторні й паралельні
конфлікти дають одну відкриту задачу; після її закриття новий конфлікт створює
нову. Reducer переставлених lifecycle-подій ще потрібний.

Обидва ядра фіналізації перевіряють відкритий receipt conflict і відмовляють
у новому debit. Безпечний replay вже проведеного результату лишається
доступним, не змінюючи залишку. Збій commit задачі не приховується як успіх.

Repository забороняє змінювати identity/hash/body/received_at receipt після
створення, дозволяючи коректний перехід стану обробки. Використана вже наявна
nullable колонка sanitized_metadata; міграція схеми не потрібна.

Перевірки: tests/integration/test_receipt_ingestion.py — 9 тестів,
15 підперевірок: повтор/перезапуск, секрети, конфлікт, scope, processed replay,
незмінність, обмеження та паралельні SQLite writers. Повний набір після
інтеграції — 407 тестів і 366 підперевірок, exit 0. Окремо перевірені
commit failure задачі, parallel conflicts/reopen і обидва debit guards.
