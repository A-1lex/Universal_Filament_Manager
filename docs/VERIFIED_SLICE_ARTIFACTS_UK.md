# Стійкий перевірений 3MF та прив’язка до job/plate

2026-10-28. Прийнятий source-level E08.06; FTPS, UI і live worker окремо.
Реальна база, installed EXE та власний HaspelSync не змінені.

## Сховище

SliceArtifactStore(root) зберігає immutable archive.3mf та canonical
manifest.json за root/SHA256/plate. Manifest містить version/parser,
file/metadata/G-code hashes, plate, logical material IDs/mg, quantity=estimate
та includes_purge=None; абсолютний source path не записується.

store_file/store_bytes/load завжди перевіряють identity та bounds і заново
розбирають архів trusted parser. Manifest порівнюється byte-exact; не можна
підмінити cached facts без відмови. Читання bounded: archive128MiB,
manifest128KiB. Невідомі parser version або змінені bytes не приймаються.

Staging з двома fsync файлами, OS advisory lock та atomic rename захищають
публікацію й два процеси. Наявний complete/corrupt/incomplete destination
не перезаписується. Після аварії незавершений staging не є артефактом;
retry не видаляє чужі дані. Cleanup дозволений лише для власного generated
staging і двох фіксованих файлів. Child links/junctions та вихід за root
відхиляються. Root — довірений локальний cache, не OS sandbox проти hostile
одночасної заміни filesystem paths. Повну power-loss durability Windows
не заявляємо: Python не надає directory fsync на цій платформі.

## Прив’язка

VerifiedSliceBindings отримує application port сховища; core не імпортує
integration implementation. bind_local вимагає expected SHA та явний plate.
Якщо job ще не має file identity/plate, потрібний manual_confirmation=True;
відомі mismatch не перезаписуються навіть цим прапорцем. Нову прив’язку
до IN_PROGRESS/FINALIZED або видаленого job створити не можна.

Розбір і cache write виконуються поза writer-lock. Далі повторно перевіряється
job fingerprint і одним UoW зберігаються його file/plate та immutable audit
job:{UUID}:slice_binding. Audit містить canonical parser/hash/request identity,
actor і явність ручного підтвердження. Ніяких physical timestamps, material
mapping, резервів чи ledger service не створює. Failed DB commit може лишити
неприв’язаний verified cache, але не часткову прив’язку або списання.

resolve і повтор bind читають сховище, а не втрачений source path. Зміна
actor/hash/plate/manual flag конфліктує; artifact/job/audit metadata повторно
перевіряються. Один файл може належати двом реальним jobs лише через дві
явні перевірені прив’язки, а не через пошук «найімовірнішої» назви файла.

## Перевірки

14storetests/14subtests: реальний Bambu fixture, restart, tamper, bounds,
ZIP traversal, incomplete destination, exception/process death prepublish,
два threads/processes, Windows junction, parser-version drift.
10bindingtests/6subtests: дві plate, confirmation, mismatches, durable audit,
source deletion/reopen, CAS race, rollback, cached-file tamper, no financial writes.
Один real Node integration test: bound source видалений, cache відновлений,
atomic calculated debit12345mg/replay без другого списання.
Повний suite473tests/447subtests; після нього додано strict request/metadata
parity та повторено binding11tests/6subtests успішно. Наступний full suite
включатиме bounded drain worker; старий wheel треба перебудувати.

## Runtime та backup wiring status — 2026-10-30

Повторний source search підтверджує, що `VerifiedSliceBindings` і
`SliceArtifactStore` реалізовані й покриті isolated integration tests, але
зараз не створюються з `StudioBackend`, `bootstrap` або `StudioWindow`.
Аналогічно, `ReceiptIngestion` і `ProjectionDrain` наявні як application
services, але runtime їх не викликає. Отже документований core binding — не
доступний користувачу production workflow і не створює справжню job identity.

`StudioBackend.backup()` викликає SQLite `create_snapshot(data/ufm.sqlite3,
data/backups/<id>)`; `sqlite_snapshot.py` зберігає лише
`database.sqlite3` та `manifest.json`. Зовнішній immutable 3MF cache у snapshot
не входить, тому повне відновлення binding ще не забезпечене. Наступна
інтеграція залежить від runtime receipt/job producer та явного data-dir/cache
layout і повинна включити перевірене пакування/відновлення зовнішніх артефактів.
До того часу не підключати ручний binding з preview UI до job/accounting і не
вважати E08.01 runtime завершеним. Installed EXE, реальні дані та HaspelSync
не змінювалися.
