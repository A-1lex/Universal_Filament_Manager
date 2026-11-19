## 2026-11-17 — E04.07 target collision preview завершено (статус Виконано)

Відновлено ізольоване середовище `.venv312` (Python 3.12.15, locked deps + dev/desktop) і перевірено baseline: 683 passed / 491 subtests, exit 0. Staging git: 2 коміти (`da73871` initial import, `97ae03a` docs), коміти не створювалися.

**Виконано:**
- `src/ufm/integrations/spoolman/importer.py`: новий read-only `preview_spoolman_target_state()` + DTO `SpoolmanTargetPreview`/`SpoolmanTargetRowState`. Для кожного рядка Spoolman-знімка повертає стан `new`/`consistent`/`preserved`/`conflict`, імена конфліктних полів (`catalog_profile`, `catalog_brand`, `opening_stock`, `archived_opening`) і збережених полів UFM (`display_name`, `lot_number`, `color_hex`, `storage_location`, `purchase_price`/`currency`/`basis`, `nominal_filament`, `empty_spool`, `remaining`, `lifecycle`) та `target_remaining_mg`. Порівняння йде з тими самими детермінованими EntityId і `_milligrams` half-up округленням, що й імпортер; функція нічого не пише.
- `src/ufm/ui/studio_window.py`: діалог імпорту після вибору джерела виконує target preview у worker і додає в таблицю 3 колонки (стан у UFM, конфлікти, збережені поля) + локалізоване зведення лічильників; 22 нові рядки в `studio_strings.json` (uk/en).
- `src/ufm/ui/desktop.py`: підтвердження імпорту додатково показує підсумок target-станів; новий ключ `desktop.import_target_summary` в uk-UA/en-US.
- Виправлено наявний крах обох UI при повторному імпорті: `recovery_label`-шаблон передавався через `text()`/`_text()` вже відформатованим → `KeyError`/`TranslationError`. Тепер raw template: `Translator.template()` (новий метод у `src/ufm/ui/i18n/__init__.py`) і прямий доступ до `studio_strings.json`.

**Перевірки:** `test_target_state_preview_reports_collisions_and_preserved_fields` (імпортер) і `test_studio_import_preview_shows_target_collisions` (Studio UI, вкл. відхилення діалогу без імпорту) — passed; `test_spoolman_importer.py` + `test_foundation.py` — 34 passed/20 subtests; `test_studio_window.py` — 80 passed; повний suite — **685 passed / 491 subtests, exit 0** (94,33 с); Ruff clean; mypy clean для 4 змінених source-файлів.

**CSV:** E04.07 → `Виконано` (критерій кроку — preview із конфліктами/пропусками/невідомими величинами/правилами mg — виконано й перевірено тестами; приймання на реальній базі лишається в E04.08/частині 04). E01.01 — додано доказ staging git provenance, статус `Частково виконовано` без змін (живі версії legacy не підтверджено). Підрахунок CSV: 118 ID — 30 Виконано / 70 Частково / 17 Заплановано / 1 У роботі; UTF-8 BOM збережено.

**Обмеження:** усе на синтетичних fixture/тимчасових SQLite; реальна база Spoolman, live legacy runtime, власник і фізичні принтери не задіяні; комітів немає.

**Наступна дія:** продовжити офлайн-аудит E01–E06 (E04.08 recovery/cutover parity, E05.x Qt-перенесення, E06.x observer) і тримати відкритими кроки, що потребують live-приймання.

## 2026-11-17 — Запит на дороблення частин 01–06

Отримано актуальніший за робочу копію upstream-архів `Universal_Filament_Manager-main.zip` у `D:/UFM/гітхаб`. Архів розгорнуто в окремий staging checkout `D:/UFM/_UFM_GitHubStage`; він був чистий на початок цієї сесії (`main...origin/main`). Оригінальний ZIP і `D:/UFM/Universal_Filament_Manager` не змінювалися. Робоча папка `D:/UFM/гітхаб` доступна лише для читання.

Звірка кроків 01–06: 47 підкроків, 21 `Виконано`, 23 `Частково виконано`, 1 `У роботі`, 2 `Заплановано`. Код та наявні докази в архіві вже покривають більшість базових сценаріїв; не змінювати статус на `Виконано` лише на підставі старого тексту handoff. Залишаються перевірки власником і на фізичних принтерах, живому legacy runtime, semantic/runtime parity та кілька незавершених workflow.

Ця сесія не запускала тестів, БД, GUI, мережу чи апаратні сценарії. Змінено тільки цей checkpoint для фіксації джерела та меж поточної роботи. Наступна дія: відновити дозволений Python 3.12 dev environment для staging і виконати вузькі регресії після вибору конкретного офлайн-підкроку; окремо спланувати живе приймання E01/E02/E03/E04/E05/E06, яке потребує реальних джерел, власника або принтера. Жоден крок не закривається цією приміткою.

# Поточна контрольна точка — Candidate16 (внутрішня portable-збірка) — 2026-10-30

## 2026-10-31 — деталізований preview імпорту Spoolman

Для E04.07 додано per-spool DTO у `src/ufm/integrations/spoolman/importer.py` та таблицю попереднього перегляду у Studio перед окремим підтвердженням імпорту. У таблиці видно назву/матеріал/виробника, номінал, тару, залишок, ціну з базою і валютою, стан, переносимі lot/color/location та поля, які не переносяться. Відсутній залишок відображається як невідомий. Усі маси переведено тим самим `_mass()` half-up до mg, що використовує імпортер. Цільова перевірка: `tests/integration/test_spoolman_importer.py` + вибірка Studio — 10 passed; Ruff clean; mypy для importer/Studio clean. Дані Spoolman і робоча UFM БД не відкривалися/не змінювалися.

E04.07 лишається **Частково виконано**: немає построкового зіставлення з уже наявними target-полями та конфлікт-резолюції, немає remote API import і owner/live acceptance. Checklist: 118 унікальних ID, 29 Виконано / 68 Частково виконано / 20 Заплановано / 1 У роботі; UTF-8 BOM збережено. Graphify map для змін Spoolman-preview синхронізовано окремою контрольної точкою 2026-10-31; поточний AMS-крок додає JSON-ресурс локалізації в відстежуваний source-manifest під час наступного refresh. Тестового друку, мережевого підключення до принтера або UI запуску Candidate16 не було.

Наступна конкретна дія: перевірити, чи можна безпечно додати target-field collision preview, використовуючи тільки ізольовану fixture БД; окремо дослідити read-only AMS snapshot coverage. Залишаються глобальні блокери списання: невизначений run identity, cross-process single-writer fence, Qt native process exit, release/legal gates. Не вважати продукт готовим до релізу.

Після завершення цього етапу Graphify синхронізовано: кореневий code graph оновлено командою `graphify update D:\Bot\Universal_Filament_Manager --no-cluster` без LLM, потім кластер/HTML/звіт — `cluster-only --no-label`. Root graph — 6151 nodes / 17924 raw edges; 525 направлених/540 неорієнтованих parallel endpoint edges залишаються в JSON і агрегуються лише для простого cluster graph. Combined Bambu/Spoolman/UFM/Haspel map побудовано з новим snapshot: 28960 nodes / 85560 edges; traceability 738 files / 13063 nodes / 45074 edges. Summary/межі оновлено у `D:/graphify-out/bambu-ufm/PROJECT_MAPS_UK.md`, `ENRICHMENT_UK.md`, `HANDOFF_UK.md`; карти залишаються засобом навігації, не runtime-доказом.

## Candidate16 — найновіша внутрішня portable-збірка — 2026-10-30

Зібрано окремо зі зміненого source: `D:\UFM_TestCandidate16\UFM Studio`. Незалежний manifest verify: 378 bundle files; 180 source inputs; source tree SHA-256 `8e1acd1710f4c96a53e82604e0e1409754c1137592026cc76ff3523a8c3fe57d`; Git revision та clean-state недоступні через відсутність root `.git`. EXE SHA-256 `3917132867052376851e9edc4e9fe9aaf91d39022b4ceb9c6a134a6730d612b0`, версія `0.1.0.dev0`, Authenticode `NotSigned`. Sidecar має 401 компонент і `composition=incomplete`; SHA-256 sidecar `8ed25b5cc37e53486f0e2ea1e196d389689a427b3b190e25c9f3032ab0ad0494`. Внутрішні SHA-256 зв’язки sidecar з `build-manifest.json` (`59077c0feaece2863d75ae879566eca80fe1c633d140ba86d594c24d42a0a5ef`) та runtime inventory незалежно перевірено; це не повний SBOM і не legal approval. Збірка включає діагностичний allowlist, але Candidate16 ще не запускався й не оглядався; Candidate15 — останній UI-reviewed build. Збірка не змінювала бази чи ярлики й не є інсталятором/релізом. Для ручного перегляду executable: `D:\UFM_TestCandidate16\UFM Studio\UFM Studio.exe`; для окремих даних слід передати новий `--data-dir D:\UFM_TestCandidate16\Data`, не використовувати встановлену UFM базу.


## Candidate15 — попередня тестова збірка, останній UI smoke — 2026-10-30

Після UI-підказки матеріалів зібрано окрему папку `D:\UFM_TestCandidate15\UFM Studio`; manifest independently verifies 374 files; EXE SHA-256 `3D7B92A2117FEDCDBC3EAA23D69BDFC16B6B77FE686E76CA353FB83A4BC9E71B`, version 0.1.0.dev0, Authenticode NotSigned, no complete SBOM. Ярлик `C:\Users\-PC-\Desktop\UFM Studio — ТЕСТ Candidate15.lnk` перевірено COM read-back: він передає лише `D:\UFM_TestCandidate15\Data` і `uk-UA`. Candidate15 відкрито; System page підтверджує власний DataDir, а Material page — нову порожню підказку. Скріншот: `D:\UFM_TestCandidate15\Review\materials-empty-candidate15-20261030.jpg`. Кандидат лишається внутрішнім тестовим, не релізом.


## Діагностика Candidate15 та E08 run identity — 2026-10-30

Через Computer Use відкрито саме `D:\UFM_TestCandidate15\UFM Studio\UFM Studio.exe` і без запису даних оглянуто всі вкладки у вікні 1360×860. «Філамент» має зрозумілі підсумки, фільтри та вимкнені дії без вибраної котушки; «Матеріали» показує перший крок для порожнього каталогу; «Пристрої» пояснює межі пошуку/читання й потребу явного підтвердження; «Система» прямо позначає тестову збірку, відсутні release gates і шлях ізольованої бази. UI в цілому читабельний у цьому розмірі, але ручне приймання власником, реальні Windows DPI, доступність і діалоги лишаються неперевіреними. Candidate15 залишено відкритим на вкладці «Філамент»; Candidate13 не змінювався.

E08 source audit підтверджено тестами: Bambu `task_id/subtask_id/job_id` є лише metadata (`provider_run_key` не задано), а epoch UUID та event sequence локальні для екземпляра провайдера. Точну ідентичність одного run через reconnect/reprint не доведено, отже receipt→job→slice binding і автоматичне списання лишаються закритими fail-closed. Вибір debugger (`cdb`, `windbg`, `WinDbgX`) у доступному PATH не знайдено; Qt combined-process exit 1 із AV досі без root cause. Точкові перевірки `test_reported_ids_are_preserved_as_metadata_not_run_identity` та `test_two_configured_printers_keep_credentials_events_and_slots_isolated`: 2 passed, 26 deselected. Код не змінювався.

Настанову `STUDIO_USER_GUIDE_UK.md` виправлено з Candidate14 на поточний Candidate15 і уточнено перелік попередніх ярликів. CSV збережено UTF-8 BOM; статуси не підвищено. Публічний реліз залишається **НЕ ГОТОВИМ**.

## E08.07 — актуалізована матриця підтримуваних форматів — 2026-10-30

`docs/VERIFIED_SLICE_INTAKE_UK.md` тепер відділяє sliced-3MF intake від G-code preflight і artifact store: підтримувана bounded підмножина 3MF має 11 HaspelSync XML fixtures та один реальний two-colour 3MF fixture; standalone text G-code приймається лише як explicit `marlin-linear-v1` read-only estimate у mm; невідомі/vendor dialect не вгадуються, `.bgcode` і FTPS retrieval не підтримуються. Грами/ledger, purge coverage, сумісність різних firmware і фізичне споживання не заявляються. Звірені `test_sliced_files.py` + `test_gcode_extrusion.py`: 21 passed / 90 subtests, exit 0; Ruff для обох модулів/тестів — clean. E08.07/E08.04 лишаються Partial: один реальний 3MF fixture і contract tests не дають широкої matrix або hardware acceptance.

Налаштування актуального тестового ярлика в user guide виправлене на Candidate15; Candidate15 лишається відкритим на Filament і з ізольованими даними. Checklist UTF-8 BOM, 118 унікальних ID, статуси 29/68/20/1; жоден пункт не підвищений до Done.

## E08 backup-root wiring audit — 2026-10-30

Graphify navigation plus source/test review confirms `AppPaths.resolve(data_dir)` defines `data/config/logs/cache`; runtime never creates `SliceArtifactStore`. `StudioBackend.backup()` snapshots only `data/ufm.sqlite3`, and `sqlite_snapshot.py` verifies/restores only `database.sqlite3` plus manifest. Isolated existing backup test: 1 passed, 4 deselected. Since the external slice store is not populated by runtime, changing archive format or inventing another root now would create unused/unverified behavior; choose one canonical store root and extend backup/restore atomically when a durable run/job producer is ready. No user data was touched.

Candidate15's light and dark Filament screens were also inspected live at 1360×860; both remain legible, and light mode was restored. This adds no physical DPI/accessibility/owner acceptance.

## E16.08 — повторна перевірка повного тестового процесу — 2026-10-30

Останні повні запуски: `.venv312\Scripts\python.exe -m pytest -q tests/integration/test_studio_window.py tests` — 654 passed / 489 subtests, exit 0 за 81,39 с; звичайний `.venv312\Scripts\python.exe -m pytest -q` — той самий зелений підсумок, але exit `-1073741819` (`0xc0000005`); ще один звичайний запуск із `PYTHONFAULTHANDLER=1` — 654/489, exit 0. Windows Application Error 1000 вказав Python 3.12.14 і `Qt6Widgets.dll` 6.12.0.0; раніший запис указував Qt6Core.dll. Це intermittent native teardown/process-exit дефект; спостереження не встановлюють причину, і faulthandler pass не доводить виправлення. Debugger відсутній у PATH/стандартних місцях; dump не відкривався. E16.08 лишається Partial; public release NOT READY.

## Виправлення mypy в Haspel authority client — 2026-10-30

У `authority_client.py` винесено валідацію booking grams у helper з точним `type is int/float` narrowing, збережено відхилення bool/NaN/out-of-range; після попередньої перевірки запис більше явно звужує поля до `str`, без надлишкових cast. Повний `mypy src`: Success для 138 файлів; повний `ruff check src tests`: clean; `tests/unit/test_haspel_authority_client.py`: 10 passed / 4 subtests. Протокол і accepted JSON дані не змінювалися.

Тестова матриця після змін: повний набір з явним запуском Studio-модуля першим — 654 passed/489 subtests, exit 0; звичайний `pytest -q` — той самий зелений summary, але exit `-1073741819`, Windows Event 1000 указує Python 3.12.14 → Qt6Widgets 6.12.0 (`0xc0000005`). Root cause не знайдено; без debugger/dump analysis виправлення не припускаю. E16.08 лишається Partial і публічний реліз не прийнято.

**Наступна дія:** не міняти pytest order як обхід; отримати debugger/символи або окремо довести детерміновану teardown-фіксацію. Паралельно продовжувати безпечні незалежні audit tasks і зберігати accounting fail-closed.


## Змістовний етап: перевірка контрасту прапорців матеріалу

У `src/ufm/ui/studio_window.py` додано явні стилі індикаторів QCheckBox для світлої й темної тем: рамку, поверхню, hover, checked і disabled стани. Додано ресурс `src/ufm/ui/assets/checkbox-checked.png` і регресійну перевірку обох тем. Візуальна перевірка Candidate14 на цьому ПК підтвердила читабельні контури в темній темі та виразний зелений/білий checked стан у світлій. Незбережену форму скасовано; матеріальний профіль не створено.

Перевірки: `tests/integration/test_studio_window.py` — 73 passed, exit 0; `ruff check src/ufm/ui/studio_window.py tests/integration/test_studio_window.py` — clean. Повний набір `.venv312\Scripts\python.exe -m pytest -q` — 654 passed, 489 subtests passed, exit 0 (81,52 с); це не знімає попередні докази intermittent Qt teardown AV. Candidate14: `D:\UFM_TestCandidate14\UFM Studio`, окрема data-папка `D:\UFM_TestCandidate14\Data`; незалежна перевірка manifest — 374 файли; EXE SHA-256 `A167E3EEC91C65002294F9A874C963E62BB835B0DD8BB2737C7CCA2F233921FD`. Це внутрішня непідписана збірка версії 0.1.0.dev0, без повного SBOM; не публічний реліз. Додатково зроблено Qt scale-factor/offscreen captures вкладки «Філамент» при 100/125/150/200% у `D:\UFM_TestCandidate14\Review\source-studio-{100,125,150,200}-review-20261030.png`; у цих знімках горизонтального обрізання немає, панель деталей вертикально прокручується. Це обмежена симуляція Qt, не повний тест реального Windows DPI/моніторів або діалогів. Клавіатурна навігація та власницьке приймання лишаються відкритими.

Створено ярлик `C:\Users\-PC-\Desktop\UFM Studio — ТЕСТ Candidate14.lnk`; COM read-back підтвердив Candidate14 EXE, окрему `D:\UFM_TestCandidate14\Data` і `uk-UA`. Настанову `docs/STUDIO_USER_GUIDE_UK.md` оновлено на актуальний кандидат. Чекліст збережено з UTF-8 BOM, 118 рядками та 5 колонками; статуси 29/68/20/1 без змін. E14.03, E16.05 і E16.08 отримали лише нові докази; жоден статус не підвищено. Публічний реліз залишається **НЕ ГОТОВИМ**.

**Наступна дія:** зберегти перевірений Candidate14 для ручного огляду. Продовжити найвищий залежнісний блок: точна printer run identity → receipt/job → slice binding та узгоджене backup/restore зовнішніх 3MF артефактів. Не вмикати списання без доведеного провенансу й глобального writer fencing.

---

# Поточна контрольна точка — фактичний статус готовності до релізу — 2026-10-30

## Пакет 1 — baseline, source provenance та межі очищення — 2026-10-30

## E16.08 — combined pytest process reproduces QtCore access violation — 2026-10-30

After the empty-materials change, the full suite printed 654 passed and 489 subtests but exited 1 (81.42 s). Windows Application Error 1000 at 23:03:50 +02 records Python 3.12.14 faulting in `PySide6\Qt6Core.dll`, exception `0xc0000005`. Split runs passed: Studio UI 73/exit 0 (11.03 s); remainder 581 passed + 489 subtests/exit 0 (71.60 s). This supports a combined-process/native Qt teardown failure, but does not identify the root cause. No dump contents were read. E16.08 remains Partial and release is NOT READY.

## E14.03 follow-up — empty Materials guidance — 2026-10-30

Live Candidate14 review found that an empty Materials page showed two blank tables without explaining the first step. Source now displays a localized reuse of the existing `no_profiles` guidance while there are no profiles; it hides after a profile is added and is suppressed on database error. The isolated transition regression plus checkbox-theme regression passed: 2 passed, 71 deselected; Ruff clean. This source change is not yet in Candidate14; the next test build must include it. Checklist BOM/118×5/status counts 29/68/20/1 remain unchanged; E14.03 remains Partial.

Qt simulated screenshot sweep for the empty Filament page at 100/125/150/200% is recorded under `D:\UFM_TestCandidate14\Review`; controls scale proportionally and the detail pane scrolls vertically. This is not physical Windows DPI/multi-monitor or dialog/keyboard acceptance.


План реалізації підтверджено власником. Read-only звірка: у корені UFM немає `.git`; `linked-stack/haspelsync` має окремі Git-метадані. Root revision не вигадується, репозиторій не ініціалізовано, commit не зроблено. Чекліст перевірений: UTF-8 BOM, 118 рядків, 5 колонок, статуси 29/68/20/1. `CLEANUP_REPORT-20261030T150320454Z.json` — лише dry-run (`Applied=false`); старі `.runtime` build-каталоги з `BUILD_ARTIFACT_CLEANUP.json` ще не пройшли перевірку manifest/reproducibility. Жодних файлів, збірок, баз, резервних копій або ярликів не видалено. Наступне: зафіксувати контрольну точку джерел і вирішити безпечний спосіб root Git provenance; продовжити інвентаризацію старих артефактів лише за allowlist.


Історичний checkpoint Candidate13 — на той момент остання внутрішня portable-збірка для ручного огляду, не реліз: `D:\UFM_TestCandidate13\UFM Studio`; незалежний повторний manifest-перерахунок підтвердив 377 файлів (378 файлів у каталозі разом із самим manifest). EXE SHA-256 `6053106251974122F63CF06781E94805A84BD2093A14E7D7C5A90AF36372E664`, версія `0.1.0.dev0`, Authenticode `NotSigned`; CycloneDX 1.7 sidecar SHA-256 `46DCE4D2B7B72D2A542DC62805714AEF45B5D946D0B86B98E17CC929F2AD351C`, 400 компонентів, `composition=incomplete`. Зібрано на Python 3.12.15 із `.venv-release`; 21 runtime distribution збігався з `uv.lock`. Ярлик `C:\Users\-PC-\Desktop\UFM Studio — ТЕСТ Candidate13.lnk` звірено: він запускав цей EXE з `--data-dir "D:\UFM_TestCandidate13\Data" --locale uk-UA`. На вкладці «Пристрої» візуально підтверджено кнопку «Перевірити локальний 3MF/G-code». Це підтверджувало лише наявність UI дії на Candidate13, а не повне приймання. Актуальний внутрішній кандидат — Candidate15; його характеристики й обмежене візуальне приймання наведені на початку цього файла.

У вихідному коді додано read-only інструмент «Перевірити локальний 3MF/G-code»: 3MF проходить наявний обмежений парсер з асинхронним списком валідованих sliced plate indexes і точним SHA-256; standalone `.gcode` проходить суворий `marlin-linear-v1` парсер з 64 MiB cap. UI показує оцінку по логічних каналах або інструменту/шару через фоновий worker. Файли не зберігаються, не прив’язуються до print job, не виконуються й не змінюють залишок; маса з G-code не виводиться. Candidate13 зібраний після цих змін; збірка не додає облікового списання.

Три останні повні запуски на Python 3.12.14 кожен дали 635 passed: два завершилися exit 0 (80.73 s, 79.55 s), третій — exit 1 після summary (79.20 s). Ще один повний запуск із -X faulthandler завершився -1073741819 після summary без Python frame. Studio UI окремо: 62 passed/exit 0 на offscreen, але повтор із QT_QPA_PLATFORM=minimal теж дав native exit -1073741819; решта suite: 573 passed/exit 0. Windows Application Error зафіксував три python.exe access violations (Qt6Core.dll двічі, Qt6Widgets.dll один раз; c0000005). Нестабільність native Qt teardown підтверджена, але її точна першопричина не встановлена. Принтер, Haspel, мережевий облік і production-БД не використовувалися.

**Публічний реліз НЕ ГОТОВИЙ.** Чекліст: 118 записів, 5 колонок, UTF-8 BOM; 29 виконано / 68 частково виконано / 20 заплановано / 1 у роботі. Ключові блокери: відсутній root Git provenance для UFM; невибрана UFM ліцензія та неповні/непогоджені SBOM і юридичний review; актуальний Candidate15 не підписано, повного SBOM немає, installer, clean-Windows, оновлення/rollback і збереження даних не прийняті; автоматичне списання лишається вимкненим через відсутність підключеного producer з надійною print-run identity, physical-spool/AMS event provenance та глобальним fencing проти паралельного Haspel writer; немає printer/hardware і повного owner UI/DPI/accessibility acceptance. Відсутні фізичні керування принтером не слід показувати як реалізовану функцію.

**Останній кодовий checkpoint:** E08.01/E08.02/E08.04 мають асинхронний локальний read-only UI preview; пізніший Candidate15 оглянуто на всіх чотирьох вкладках. Core `VerifiedSliceBindings` і `SliceArtifactStore` для immutable archive та audited job/hash/plate binding уже існують і мають isolated integration coverage, але `rg` не знаходить їх runtime wiring у Studio/backend/bootstrap. Поточний `StudioBackend.backup()` передає лише `ufm.sqlite3` у `create_snapshot`, а snapshot включає лише `database.sqlite3` і `manifest.json`, тож він не пакує зовнішній 3MF artifact store. Залишаються producer/job identity і підключення binding до UI, backup/restore артефактів, verified FTPS, purge coverage, vendor G-code dialects, матеріальне/AMS зіставлення та будь-яке облікове списання. Автоматична політика лишається вимкненою без перевіреної ідентичності запуску, reviewed mapping та глобального writer fencing.

**Наступна технічна точка цього історичного checkpoint:** перевірити й узгодити runtime path `printer observation → durable receipt → managed print job → verified slice binding`, зокрема точний provider/run identity; окремо вирішити включення зовнішніх immutable 3MF artifacts у backup/restore. Пізніший аудит підтвердив, що Bambu run identity досі не доведена, а Candidate15 залишається внутрішнім тестом. Не вмикати accounting authority на підставі лише локального файла. E08.01/.02/.04 лишаються Partial; релізні gates не закриті.

## E02.03 / E02.06 checkpoint — contract and feature-reference integrity — 2026-10-30

Статично звірено два action-contract каталоги: Spoolman має 318 унікальних SA001–SA318, HaspelSync — 211 унікальних HA001–HA211; усі 10 колонок у кожному записі заповнені. Feature map має 124 унікальні F IDs, у кожному рядку заповнено evidence/actions/Qt-location, а всі знайдені SA/HA-посилання відповідають наявним 529 ID (0 dangling). Це доводить структурну цілісність каталогів, а не їхню повну семантичну чи runtime-повноту; E02.03 і E02.06 лишаються Partial. Чекліст: 118 рядків, BOM, статуси 29/43/45/1 без змін.

Наступний безпечний крок — продовжити source-based перевірку релізного provenance/ліцензійної інвентаризації E03.08 і зафіксувати конкретні невирішені юридичні/комплектні питання. Не переводити UI відсутніх або неперевірених поведінок у Done на основі лише структурної перевірки CSV.

## Candidate10 SBOM / E03.08 checkpoint — static license metadata limits — 2026-10-30

Переглянуто згенерований для Candidate10 CycloneDX: 399 компонентів (`376 file`, `21 library`, `2 framework`), `composition=incomplete`. У 21 Python library є observed-license metadata; два пакети (`jaraco.classes`, `segno`) позначені `not specified`. PySide6_Essentials і shiboken6 показують альтернативи LGPL/GPL, а зібраний PyPI notice має `LicenseRef-Qt-Commercial`; придатність конкретних умов і source-offer obligations не визначені. SBOM показує Node.js license-path і Haspel subset license/provenance paths, але це не повне SPDX/CycloneDX license conclusion. Кореневого UFM `LICENSE` немає; `pyproject.toml` не задає `project.license`. Статус E03.08 лишається Partial, без власного вибору ліцензії чи юридичного висновку.

Чекліст повторно валідовано: BOM, 118 рядків/5 колонок, статуси 29/43/45/1. Залишаються зовнішні рішення: власник має визначити ліцензію UFM та отримати юридичну оцінку Qt/PyInstaller/Node/інших notices перед публічним розповсюдженням. Далі можна закрити лише перевірні технічні поля provenance; не позначати E03.08 Done до цих рішень і повного release SBOM.

## E03.07 checkpoint — focused cutover/client contract tests — 2026-10-30

Додано два ізольовані набори перевірок для нового облікового перехідного механізму. `tests/integration/test_accounting_authority.py`: 5 passed — точний replay, конфлікт повторно використаного ключа зі зміненим payload, stale revision без audit write, обов’язкові snapshot/attestations і точний збіг evidence для UFM_ACTIVE. `tests/unit/test_haspel_authority_client.py`: 5 passed — path encoding і scope, revision CAS, відхилення чужого printer/boolean revision, HTTP 409 та cleartext лише loopback. Тестовий клієнт використовує mock і не звертається до мережі; integration tests — тимчасова SQLite та isolated migrations, без production data/printer. Ruff для нових файлів clean.

E03.07 лишається Partial: це підтверджує тільки локальний UFM transition та API-client contract. Haspel authority endpoint у наявній реалізації не є глобальною блокіровкою між процесами/DataDir; віддалений запис вимикається лише явним операторським переходом, cutover/rollback ще не перевіряв власник, finalizer не пройшов live network sequence і автоматичне списання лишається fail-closed/off. Чекліст 118 рядків, BOM, статуси 29/43/45/1.

Наступна безпечна дія: розглянути стабільний fencing як окрему архітектурну межу й перевірити наявний endpoint/legacy writer статично. Не вмикати UFM_ACTIVE та не обліковувати принтерні витрати без спільної серверної блокіровки та реальних redacted traces.

## Candidate10 — запуск і візуальний огляд на цьому ПК — 2026-10-30

Тестовий ярлик `UFM Studio — ТЕСТ Candidate10` на тому історичному етапі відкрив тодішню portable-збірку. Переглянуто чотири основні сторінки: Філамент, Пристрої, Матеріали, Система. Ізольований порожній інвентар показав 0 котушок і 0 принтерів; вкладки, таблиці, панелі дій та системний статус завантажилися. Цей запуск створив тестову локальну БД `D:\UFM_TestCandidate10\Data\data\ufm.sqlite3`; її перевірено read-only: `PRAGMA integrity_check` = `ok`, `foreign_key_check` = 0, 39 таблиць, міграція `0007_haspel_authority_connection`. Candidate10 не отримував мережевий пошук/підключення до принтера, Haspel API, обліковий режим чи stock actions. Це не owner, clean-Windows чи DPI matrix acceptance; актуальний кандидат — Candidate15, описаний на початку документа.

Візуальна оцінка: інтерфейс розкладає навігацію, фільтри, кнопки й таблиці без явного обрізання на поточній роздільності; сторінки Матеріали/Система мають багато вільного місця, бо набір даних порожній. Пристрої чесно показують, що керувальні команди ще не реалізовані/перевірені. Автосписування прямо позначене як у розробці. Це внутрішня тестова збірка, не завершена програма.

Checklist: 118 рядків, BOM, статуси 29/43/45/1 без підняття статусів; E14.03/E16.04/E16.08 отримали лише scoped evidence. Наступна дія для власника на той час — перевірити Candidate10 shortcut і пройти keyboard/DPI acceptance, а до будь-якого live Haspel або printer flow залишатися read-only. Пізніше власник переглянув Candidate15 візуально на чотирьох вкладках на цьому ПК; інші acceptance gates лишились відкритими. Public release залишається NOT READY через ліцензійні/SBOM/signing/clean-Windows gates, distributed accounting fence/run identity, hardware, повний-suite flake та відсутні owner acceptances.

# Поточна контрольна точка — Candidate9, історія витрат і UI focus — 2026-10-30

Candidate9 зібрано в окрему portable-папку з джерелом, що додає до історії розрахункової витрати наявний ID завдання/квитанції та обмежену перевірену 3MF-походження (короткий SHA-256 і пластина). Неперевірені metadata й шляхи не показуються. Пакет: `D:\UFM_TestCandidate9\UFM Studio`; manifest перевірено — 376 файлів; EXE SHA-256 `99AF566B4E6CD3E38347437555C7ACCC7DB85C871585D31FE3CCE260B091AEE0`; PE version `0.1.0.dev0`; Authenticode `NotSigned`. CycloneDX 1.7 sidecar має 399 компонентів та `composition=incomplete`, SHA-256 `148438580A356B393A4563C580E62056BF8A127A9FCFF93E1DA26BD2CE3E42A8`. Тестовий ярлик `UFM Studio — ТЕСТ Candidate9.lnk` передає `--data-dir "D:\UFM_TestCandidate9\Data" --locale uk-UA`; data-папки ще немає, Candidate9 не запускався. Старі збірки, ярлики та production data не змінювалися.

Перевірки джерела/пакета: наявний `tests/integration/test_studio_window.py` — 62 passed/exit 0 після відповідних змін; Ruff clean; locale JSON valid; manifest verification — 376 файлів; SBOM generator — 399 компонентів, явно incomplete; docs audit: 86 локальних Markdown-посилань перевірено, битих немає, CSV 118/124 рядки й BOM валідні. Повний suite у locked Python 3.12.15: 625 passed/485 subtests; 3/4 запусків exit 0, один exit 1 після успішного pytest summary, -X faulthandler не виявив Python traceback; stability gate лишається відкритим. E09.03 лишається частково виконаним: label і безпечне provenance summary є, але повний job details view та end-to-end receipt/job→spool зв’язок не прийняті. E14.03 лишається частковим: потрібна ручна перевірка Tab/focus і DPI 100/125/150/200. Checklist: 118 рядків; Виконано: 29 / Частково виконано: 43 / Заплановано: 45 / У роботі: 1 / Заблоковано: 0 / Відкладено: 0; UTF-8 BOM збережено.

Реліз **НЕ ГОТОВИЙ**: Candidate9 внутрішній і непідписаний; SBOM неповний; відкриті юридичні/ліцензійні та installer gates, нестабільний повний-suite process exit (3/4 поточних запусків exit 0, 1 exit 1 після 625 passed; причина не встановлена), автоматичне списання і стабільна job-to-spool identity, hardware E05.04, clean-Windows E16.04 та owner UI acceptance. Candidate9 не запускався агентом. Локальну БД, printer, account і stock debit не змінювали.

Перевірка E07.04 встановила межу безпечного продовження: Bambu adapter створює випадковий source_epoch та event_key-лічильник з нуля для кожного provider instance; monitor створює новий instance при reconnect; 256-event FIFO має явний overflow, але нинішній UI drains до останньої події, а durable `take_pending_events` не має consumer. `ReceiptIngestion`/`ProjectionDrain` не викликаються з production `src`. До інтеграції потрібні підтверджені MQTT traces/fixture run IDs і поведінка повторного старту/reprint; до цього не можна прив’язувати дебет або показувати вигаданий job history. E09.04 fail-closed mapping і mounted RFID guards пройшли 63 passed/38 subtests, але operator mapping/reconciliation UI та live acceptance залишаються відкритими. Candidate9 можна оглянути окремо; E05.04 hardware, live provider E07 та clean-Windows E16.04 — зовнішні gates.

---

# Архівна контрольна точка — Candidate8, UI focus — 2026-10-30

Candidate8 зібрано після додавання помітного клавіатурного фокусу в кнопках, текстових полях, combo boxes, навігації й таблицях. Ізольований portable пакет: `D:\UFM_TestCandidate8\UFM Studio`, manifest — 376 файлів; EXE SHA-256 `0DF64CCB71ACACB1B88A9669837F5FE72D42D6A265708017385AB0BCEC7598D3`; версія `0.1.0.dev0`; Authenticode `NotSigned`. CycloneDX 1.7 sidecar: 399 компонентів, `incomplete`, SHA-256 `6AA4F3C1BDC4C3A904777012F412A2F849BAF85376C9CF1AADB1DFF4FBC567B0`. Ярлик `UFM Studio — ТЕСТ Candidate8.lnk` веде на цю збірку з окремим шляхом `D:\UFM_TestCandidate8\Data`; Candidate8 поки не запускався. Candidate5/7 та встановлена/dev-версії лишені без змін.

Перевірки: наявний `tests/integration/test_studio_window.py` — 62 passed/exit 0; Ruff clean; locale JSON valid; manifest повторно verified — 376 files. Це build/source evidence, не owner runtime acceptance. Чекліст: 118 рядків — 29 виконано / 43 частково виконано / 45 заплановано / 1 у роботі; BOM збережено. E14.03 переведено в «Частково виконано» через focus-style реалізацію; keyboard traversal, реальний focus appearance та DPI 100/125/150/200 ще не прийняті. Наступна технічна дія: звірити E09.03 — чи відображається «Розрахункова витрата» у всіх доступних деталях історії без підміни виміряних даних; owner review Candidate8 (Tab/focus) і DPI acceptance лишаються паралельними зовнішніми пунктами. E16.04 — окреме clean-Windows приймання.

Реліз досі **НЕ ГОТОВИЙ**: unsigned/incomplete SBOM, відкриті ліцензійні та installer gates, Qt/native teardown, автоматичне списання/job-to-spool identity, апаратне E05.04 і clean-Windows приймання. Локальну БД, printer, account та stock debit не змінювали.

## Source check E08.04: Marlin extrusion modes — 2026-10-30

Перевірено наявний subset parser `src/ufm/integrations/gcode_extrusion.py` проти офіційних описів Marlin M82/M83: M82/M83 задають effective E mode незалежно, а наступні G90/G91 очищають цю override. Парсер перемикає цей стан у відповідних командах і не приймає невідомі dialect/firmware extensions; supported dialect лишається тільки `marlin-linear-v1`. Наявний `tests/integration/test_gcode_extrusion.py`: 7 passed / 24 subtests / exit 0. Це узгодженість підмножини коду, не доказ сумісності іншого firmware і не hardware acceptance. Джерела: https://marlinfw.org/docs/gcode/M082.html та https://marlinfw.org/docs/gcode/M083.html. E08.04 лишається частковим.

---

# Архівна контрольна точка — Candidate7 / E16 — 2026-10-30

## Візуальний перегляд вікон Candidate5 — 2026-10-30

Переглянуто вкладки «Філамент», «Пристрої», «Матеріали», «Система» та діалог
додавання котушки у відкритому Candidate5. Знайдено обрізання підписів у
переповнених однорядкових панелях дій, надто яскраве виділення вибраного рядка
таблиці та застарілий текст Системи, що називав автономну збірку майбутньою.
У джерелі панелі фільтрів/дій переведено на сітки з кількома рядками, явно
задано контраст вибраного рядка, а текст Системи тепер відрізняє внутрішню
тестову збірку від неприйнятого публічного релізу. Діалог котушки лишився
довгим прокручуваним формуляром; його не скорочували, щоб не приховати поля.

Candidate5 уже запущений у цьому сеансі лише для візуального перегляду; даних
не зберігали, принтерних команд та списання не виконували. Оновлену верстку
перевірено в Candidate7; це не приймання власником, не апаратна перевірка й не
дозвіл на публічний реліз. Контрольний список лишає 118 кроків і
попередні статуси; E16.08 отримує доказ візуального огляду без підвищення статусу.

Наступна дія: отримати власницький візуальний/клавіатурний огляд Candidate8 для E14.03; DPI 100/125/150/200 і clean-Windows E16.04 залишаються окремими неперевіреними приймальними кроками. E05.04 чекає реального ScaleProvider та апаратного приймання; E07.03–.05 чекають підтверджених provider run identity/event traces. Release gate лишається NOT READY.

Candidate7 зібрано окремо за шляхом `D:\UFM_TestCandidate7\UFM Studio` із
locked Python 3.12.15. Manifest verification: 376 файлів;
PE version `0.1.0.dev0`; EXE SHA-256 `cdb0d8dae0f2738ee6dd0824e64750c44238ef5983a09b7434cce27ad0402498`;
CycloneDX sidecar — 399 components/incomplete, SHA-256
`e64a507b67361e92b295f0005631219429021088f3411b8261721a4d10fc0872`. Тестовий ярлик на Desktop:
`UFM Studio — ТЕСТ Candidate7.lnk`, передає `--data-dir
D:\UFM_TestCandidate7\Data --locale uk-UA`; Candidate5 і дві старі
робочі кнопки запуску не змінені. Candidate7 реально запущено для візуального
огляду: вкладки Пристрої, Матеріали, Система, темна/світла тема; жодного
принтерного підключення, облікового запису чи списання не запускали.
Панелі кнопок і фільтрів більше не обрізаються, права панель котушки стала
прокручуваною, selected row має явний контраст, а UI чесно позначає test build.
Candidate7 відкрито окремо з `D:\UFM_TestCandidate7\Data`; на фактичному
вікні панелі «Філамент»/«Пристрої» показують повні підписи, довгі дії котушки
доступні вертикальною прокруткою; переглянуто також «Матеріали», «Система» та
світлу/темну теми. Dialog котушки не зберігав даних. Ізольований
`tests/integration/test_studio_window.py`: 62 passed, exit 0; Ruff і JSON valid.
Поточне вікно лишено на вкладці Філамент із порожньою ізольованою тестовою БД.

Блокери релізу (списання/job-binding, SBOM, підпис, ліцензії, Qt/native
teardown та clean-Windows/hardware acceptance) залишаються.

## Portable Candidate5 для ручної перевірки — 2026-10-30

На запит власника зібрано окремий portable Candidate5 з актуального source у `D:\UFM_TestCandidate5\UFM Studio` через locked Python 3.12.15/build extra в новому scratch `.runtime\ufm-test-candidate-py312`. `.venv312`, `.venv-release`, інстальований `D:\UFM Studio`, наявні ярлики й робоча база не перезаписані. Build-manifest перевірив SHA-256 усіх 376 файлів; PE FileVersion/ProductVersion — `0.1.0.dev0`; EXE SHA-256 `4b7903fc2be099eec1b0f62db9137741fe17ad4eb10fe17d7162c2cd9b57ef35`. Створено sidecar CycloneDX 1.7, 399 components, але він попередній/incomplete; SHA-256 `4227dac3dce6fe15b3d401405b38eb97970ffe31eb087b0446ce3d12d954d113`. EXE має Authenticode `NotSigned`, отже Candidate5 лише для внутрішньої ручної перевірки.

На Desktop додано ярлик `UFM Studio — ТЕСТ Candidate5.lnk`, який запускає Candidate5 українською з окремою тестовою БД `D:\UFM_TestCandidate5\Data`. Candidate5 оглянуто від імені агента лише візуально; діалог котушки було відкрито й скасовано без збереження, принтерні та облікові дії не запускали. Власницьке UI acceptance і перевірки ручних потоків залишаються потрібними. Старий ярлик `UFM Studio.lnk` веде на встановлену збірку `D:\UFM Studio\UFM Studio.exe` та дані `D:\UFM Studio Data`; `Universal Filament Manager.lnk` веде на dev-версію через `.venv312` та `.runtime\desktop-test`. Ці ярлики лишені без змін. Інтерфейс Candidate5 — поточна реалізація source; повний UX-перегляд/приймання та видалення всіх непотрібних файлів ще не підтверджені.

Перевірка цього етапу: locked build exit 0; manifest `Verified 376 bundle files`; EXE/SBOM hash зафіксовані; вузли Qt — 26 DLL, усі версії `6.12.0`; Node `24.22.1`. Це не означає підписаний чи публічний реліз. Основні ліміти на етапі: 62% primary /35% weekly залишку.


## Додаткова Qt/native діагностика — 2026-10-30

У locked Python 3.12.15 середовищі повторно підтверджено нестабільне завершення Studio-набору: 62/62 перевірки пройшли, але процес після summary повернув Windows access violation `0xC0000005` (`faulthandler`: native frame відсутній). Обидві половини модуля окремо завершилися 31/31 з кодом 0; окремі групи 10/10 також проходили, хоча один повтор групи 31–40 завершився тією ж native аварією, а наступні повтори підгруп і повтори цього діапазону завершились з кодом 0. Отже, це flaky Qt/native teardown, а не встановлений регрес конкретного тесту; набір не має стабільного process-exit доказу і блокер не знятий. Цільовий тест моніторингу повторів пройшов 5 незалежних запусків; non-UI набір раніше пройшов 563/563 з 485 subtests і кодом 0.

Після виправлень типів `mypy src` проходить для 137 файлів, `ruff check src scripts tests` чистий. Жодної зміни production-коду чи запуску програми/інсталятора/принтера/production-бази в цьому етапі не було. Розслідування запусків обмежено ізольованими тестовими БД і Qt offscreen; підтвердити clean Windows install, hardware, ліцензії та SBOM повноту без власницьких рішень/обладнання неможливо. Checklist залишається 118 рядків: 29 виконано /42 частково /46 заплановано /1 у роботі; E05.04 активний. Наступна дія: знайти відтворювану причину native teardown або задокументувати мінімальне підтримуване розділення suite з повним coverage та exit 0, не приховуючи access violation. Ліміти на checkpoint: 62% primary /35% weekly залишку.


## Повторний аудит та перевірка наявних сценаріїв — 2026-10-30

Перечитано правила `AGENTS.md`, поточні план/чекліст/handoff, README та
релізний протокол; Graphify використано як карту навігації з перевіркою
висновків у коді й fixtures. Аудит охопив production source, scripts, тести,
кореневу та `docs/` документацію, конфігурації й поточні Candidate4 метадані.
Не розкривались і не змінювались бази, secrets, резервні копії, бінарні файли,
віртуальні середовища користувача чи vendored/cache дерево цілком. У корені та
`docs/` перевірено 56 Markdown-файлів і 115 локальних посилань: відсутніх немає.
Статичний синтаксичний обхід: 223 Python-файли, 11 JSON-ресурсів, `pyproject.toml`
і 9 PowerShell-скриптів без помилок; `ruff check src scripts tests` чистий.

Перевірка показала застарілі test helpers після зміни схеми/облікових правил:
додано лише вимогу реального cutover fixture через `PrinterAccountingAuthorityCommands`,
сортування повних DB snapshots за фактичним primary key, актуальні 39 таблиць
і 22 рядки реєстру Studio. Захист `UFM_ACTIVE` не послаблювався; production
source не змінено. У документації виправлено приклади installer/SBOM із Candidate3
на поточний Candidate4.

Перевірки у окремому locked Python 3.12.15 env з `uv.lock`: усі non-UI
перевірки — 563 passed / 485 subtests, exit 0; модуль Studio — 62 passed, exit 0.
У спільному процесі всі 625 tests і 485 subtests проходять, але після summary
Windows завершує pytest з `0xC0000005` (access violation). Спершу один запуск із
Studio як першим аргументом завершився з exit 0, але повтор із тим самим
порядком модулів через collection hook знову впав; hook вилучено як ненадійний.
Стабільний доказ наразі — тільки два окремі процеси; монолітний запуск має
відкриту нестабільність Qt/native teardown. Програма, installer, принтер і
production база не запускалися.

Чекліст: 118 кроків — 29 виконано / 42 частково / 46 заплановано / 1 у роботі;
активний крок E05.04 (апаратний ScaleProvider/калібрування/приймання). Реліз
**не готовий**: автоматичне списання та job→spool mapping лишаються P0; потрібні
стабільна ідентичність друку та безперервна доставка подій, UFM/Qt/Microsoft
ліцензійне рішення, повна SBOM-атрибуція, сертифікат підпису і clean-Windows
install/upgrade/rollback/data-retention acceptance. Автоматизація `ufm`
оновлена й ACTIVE з інтервалом 15 хвилин; вона має поновлювати цю роботу після
порогового відновлення лімітів.

## Аудит готовності до релізу — 2026-10-30

Після перевірки зібрано Candidate4 та інсталятор-кандидат окремо від
встановленої програми. Виправлено PE version resource; обидва PE version strings
відповідають `pyproject.toml`. У build scripts додано необов’язкове підписання
через сертифікат зі сховища Windows і обов’язкову RFC3161 timestamp адресу;
без обох явних параметрів build лишається unsigned. Код підписання пройшов лише
статичні перевірки; сертифікат не вибирався, файл не підписувався.
У локальних `CurrentUser\\My`/`LocalMachine\\My` немає придатного code-signing
сертифіката; Windows SDK містить `signtool.exe`, тож для підпису потрібен
затверджений сертифікат/приватний ключ і timestamp endpoint від власника релізу.

Рішення: Candidate4 **не готовий до публічного релізу**. Candidate3 збережений,
але більше не є поточним артефактом. Перевірені 118 кроків
інтеграції: 29 виконано, 42 частково, 46 заплановано, 1 у роботі; feature
matrix має 124 записи (28 наявних, 30 часткових, 46 на додавання, 20 бажаних).
Активний крок за checklist — E05.04: підключити ScaleProvider із перевіркою
калібрування та пройти hardware acceptance. Для P0 автоматичного обліку наступний
gate — E07.03/E07.04/E07.05: визначити stable provider-run identity та monotonic
event delivery через reconnect/restart до підключення
`ReceiptIngestion`/`ProjectionDrain`. Для цього потрібні підтверджені локальні
MQTT спостереження; не виводити ключ запуску з `task_id` чи filename.
Автоматичне списання — F053 Partial/P0; auto-binding job→котушка — F050 Add/P0.
У коді `EstimatedUsagePolicy.enabled=False` за замовчуванням; production-виклику
`ReceiptIngestion.ingest` не знайдено, а UI-принтерний handler бере лише останню
подію для візуального показу.

Позитивні статичні докази: Candidate4 manifest перевірив 370 файлів; runtime
inventory містить 21 пакет без version drift від `uv.lock`; не знайдено DB,
SQLite sidecar, log, `.env` або private-key файлів. BOM (393 components, hash
`1b4cfd283df2e843f581f54ba71808b1c362e7cb47b39302605841c50a18a481`) пройшов
CycloneDX 1.7 schema та дорівнює sidecar; composition навмисно `incomplete`.
`ruff check src scripts`, AST Python/8 PowerShell scripts і перевірка 100
локальних markdown-посилань у 48 файлах пройшли. `ruff check .` окремо має 23
знахідки у `.runtime` scratch/старих bundled stubs; release source scope чистий.

Candidate4 EXE має SHA-256
`1ead5dfbf6ab414aa9dfe990b7ae75ae235dd7a59b7d2b0d22f63b38578289a9`; PE
`FileVersion` і `ProductVersion` тепер обидва `0.1.0.dev0` з єдиного джерела
`pyproject.toml`. Інсталятор зібраний поточним SBOM-binding preflight:
`D:\UFM_InstallerCandidate4\UFM-Studio-Setup-0.1.0.dev0.exe`, SHA-256
`3673df1d876e4444a4f9f829072489aec7d96f07271c00d0182e5e8568a2c53e`,
`NotSigned`. Релізні блокери залишаються: немає UFM license, погодження
Qt/PySide та Microsoft runtime, повної SBOM, підпису, чистого Windows
acceptance та перевіреної процедури install/upgrade/rollback/data retention.
Installer не запускали, встановлення не перевіряли. Тести та product runtime
у цьому етапі не запускались.
Контрольні рядки E03.06/E16.* лишаються незавершеними; статуси не підвищувались.

## E16.05 — окремі компоненти Node.js та HaspelSync subset у SBOM — 2026-10-30

`scripts/write_release_sbom.py` тепер додає Node.js як окремий framework-компонент
із версією з PE `ProductVersion`, SHA-256 bundled `node.exe` і зв’язком з Node
LICENSE. Також додається окремий компонент лише для vendored HaspelSync
розрахункової підмножини; його версія й provenance читаються з bundled
`PROVENANCE.md`, а залежності ведуть на manifest-хешовані calculation/shared/
LICENSE/provenance файли. `build_release_candidate.ps1` передає PE-версію
генератору без запуску Node. Candidate3 SBOM перегенеровано поза bundle:
393 компоненти: додано Qt 6.12.0 як окремий framework із 26 file edges до
manifest-хешованих Qt core/plugin DLL. Версія підтверджена однаковим PE
`ProductVersion` цих файлів; `build_release_candidate.ps1` відхиляє відсутні,
змішані або некоректні версії. SHA-256 обох ідентичних BOM:
`aa6c45b526271e5e74d1c58a0d8183c1705fee5b93cf7c1a72dff82ceed8b199`.
CycloneDX 1.7 schema та статична перевірка унікальності/цілісності посилань
пройшли; composition лишається `incomplete`, інші native компоненти та правова
оцінка не охоплені. Ruff, Python AST і PowerShell AST перевірки пройшли. Bundle,
installed app, installer, бази, secrets і принтер не змінювались; тести/runtime
не запускались.

## E16.02/E16.08 — зв’язування installer із конкретним SBOM — 2026-10-30

`scripts/build_installer.ps1` тепер до створення output/компіляції вимагає
`UFM Studio.cdx.json` поряд із bundle і звіряє CycloneDX 1.7, версію продукту,
точні SHA-256 `build-manifest.json` та `third-party/runtime-dependencies.json`,
а також єдиний явний `incomplete` composition. Це не дає зібрати installer із
застарілим або відсутнім BOM і водночас не трактує неповний inventory як повний.
PowerShell AST перевірено; read-only звірка Candidate3 підтвердила версію
`0.1.0.dev0`, manifest SHA-256 `27890b4053c5d41524ec9b3040ef762d78ce1a40c111d6ce7e4a82214601a8b4`
і `incomplete`. Сам installer повторно не компілювався та не запускався.
Гайд і release acceptance protocol описують нову передумову. E16.02/E16.08
залишаються частковими до повторного складання, підпису й окремого чистого
Windows приймання; тести, app/runtime, БД та принтер не запускалися.

## E16.05 — задокументовано межі політики оновлень — 2026-10-30

У user guide та `docs/RELEASE_ACCEPTANCE_UK.md` зафіксовано фактичний стан:
автооновлення немає, unsigned candidate не слід накладати на робочу збірку,
майбутній затверджений реліз має перевіряти підпис, версію, manifest і SBOM,
створювати backup перед міграцією та зберігати user data. Downgrade через
звичайний setup не підтримується; потрібен окремо прийнятий restore/migration.
Це тільки політика документації, не реалізована чи перевірена процедура;
E16.05 лишається Partial. Чисте Windows-приймання, сертифікат підпису, license
review, backup/restore й міграційний acceptance ще потребують окремих
артефактів/середовища.

## E16.05 — попередня CycloneDX-інвентаризація — 2026-10-30

Додано `scripts/write_release_sbom.py` і створено `docs/RELEASE_CANDIDATE3.cdx.json`
на основі перевіреного manifest Candidate3 та переліку Python-пакетів у збірці.
CycloneDX 1.7 містить 370 файлів із SHA-256 та 20 бібліотек Python (плюс
кореневий компонент UFM) і ребра Python-залежностей із `uv.lock`; повнота
прямо позначена `incomplete`. Повний граф native-компонентів, застосовні
ліцензійні умови та дозвіл на поширення ще не підтверджені. Candidate bundle
не змінювався. `build_release_candidate.ps1` тепер складає SBOM поруч із новою
папкою candidate без перезапису наявних результатів. Sidecar Candidate3:
`D:\UFM_ReleaseCandidate3\UFM Studio.cdx.json`, 195,522 bytes, SHA-256
`54e36c4059e4cf9458641ccb5691ba844e5a31c96eac1dea0363de61a6392c1e`.
Ruff пройшов; генератор повторно перевірив 370 файлів manifest. JSON пройшов
офіційну CycloneDX 1.7 JSON Schema через PowerShell `Test-Json`, а структурна
перевірка підтвердила унікальні посилання компонентів і SHA-256. Тести й
програму не запускали. Протокол `docs/RELEASE_ACCEPTANCE_UK.md` тепер
ідентифікує SBOM sidecar за шляхом і SHA-256 та вимагає звірити його з
bundle/version; явне `incomplete` забороняє вважати його повним ліцензійним
чи component inventory.


Окремий portable candidate `D:\UFM_ReleaseCandidate3\UFM Studio` побудовано
через нову `.venv-release`: CPython 3.12.15 та desktop/build extras із
`uv.lock`. Існуючу `.venv312` не синхронізував. У `pyproject.toml` додано
PyInstaller build extra, lockfile містить його та транзитивний toolchain;
`scripts/build_release_candidate.ps1` автоматизує відтворюване середовище й
folder build. Статичне порівняння candidate показало 21 runtime distribution,
усі версії збігаються з `uv.lock`; `build-manifest.json --verify` звірив 370
файлів без розбіжностей. Архів EXE містить явні `win32ctypes` wrappers та
конкретні ctypes modules. Статичний список не має DB/SQLite/WAL/SHM, журналів,
`.env`, приватних ключів або особистих баз. Candidate має 214,834,774 bytes.

Попередній `D:\UFM_ReleaseCandidate2\UFM Studio` не відтворюється з поточного
lockfile: 8 пакетів мали інші версії, `greenlet` не було в lock. Його не
перебудовував і не використовую для наступних релізних кроків. Старий
`D:\UFM_ReleaseCandidate\UFM Studio` теж не використовувати — у ньому немає
`win32ctypes`. Встановлену `D:\UFM Studio`, desktop shortcut, бази й секрети
не змінював.

Для E16.02 додано чернетку per-user Inno Setup: шлях за замовчуванням у
`%LOCALAPPDATA%\Programs\UFM Studio`, вибір каталогу, меню Пуск, необов’язковий
ярлик на робочому столі та видалення без `[UninstallDelete]` особистих даних.
`scripts/build_installer.ps1` перед компіляцією перевіряє candidate manifest.
PowerShell AST parsing та Ruff пройшли. Inno Setup 6.7.3 встановлений у user
scope і успішно скомпілював installer candidate
`D:\UFM_InstallerCandidate3\UFM-Studio-Setup-0.1.0.dev0.exe` (61,474,770 bytes,
SHA-256 `deb550f43139c33f6d2a5516579bbfd86e868c50eace5e6f7c65f7fb876c86b7`).
Installer не підписаний; його не запускали, install/update/uninstall не
перевіряли. Є окремий протокол `docs/RELEASE_ACCEPTANCE_UK.md`.
Захисна перевірка `scripts/build_installer.ps1` також відхиляє output всередині candidate bundle та проходить усі наявні компоненти шляху, відмовляючи для symlink/junction до створення каталогу. Це статична перевірка безпеки побудови; інсталятор і далі не встановлювався.
`AppPaths.resolve(None)` зберігає базу, конфігурацію, журнали й кеш у
користувацьких каталогах `platformdirs`, окремо від програми.

E16.07: cleanup має явний `-Apply`, allowlist трьох кешів, path/project/reparse
checks і dry-run; створений `docs/CLEANUP_REPORT-20261030T150320454Z.json`
зафіксував 5/3/10 файлів у трьох кешах, `Applied=false`. Попередній
`CLEANUP_REPORT.json` збережено; жоден кеш не видалено. CSV: 118 рядків;
29 Виконано / 42 Частково виконано / 46 Заплановано / 1 У роботі; UTF-8 BOM
збережено. E16.01/E16.02/E16.03/E16.05/E16.07/E16.08 — Частково виконано.
Відкриті: installer install/upgrade/uninstall, чиста Windows,
runtime acceptance, Qt/MSVC та UFM license review, повна native-атрибуція SBOM, підпис і release
approval. Не змінював `D:\UFM Studio`, ярлик, реальні бази чи секрети. Не запускав
EXE, installer, продуктову БД, тести, принтер або мережеву інтеграцію;
auto-debit вимкнено.

Наступна конкретна дія: пройти ліцензійний review, потім виконати
`docs/RELEASE_ACCEPTANCE_UK.md` у чистому контрольному середовищі з тестовою
базою та credentials. Не переадресовувати чинний ярлик і не встановлювати
поверх робочої папки без окремого приймання.

---

# Попередня точка продовження — E03.08 release-notice collector — 2026-10-30

Колектор релізних notices тепер бере прямі runtime залежності та desktop
extra з source `pyproject.toml`, а не покладається на застарілі встановлені
метадані самого UFM; транзитивні залежності збираються через встановлені
`Requires-Dist`. Статичний збір у тимчасову директорію знайшов 22 пакети й 22
license files; Ruff пройшов. Локальні LICENSE файли `jaraco.classes 3.4.0`
(MIT) та `segno 1.6.6` (три умови BSD-style) звірено з PyPI та upstream.
Колектор додатково записує точні імена цих files у JSON manifest поруч із
кількістю. `uv.lock` фіксує PySide6 Essentials/shiboken6 Windows wheels із
PyPI-hosted URLs і SHA-256; Qt документація розрізняє LGPLv3/GPLv3 Community
та Commercial distributions. Файл `LicenseRef-Qt-Commercial` у package
notices сам не визначає ліцензію чи виконання вимог release. Треба зіставити
реально включені Qt binaries/modules з applicable terms/notices. UFM license не
вибрана; Qt/source offer, Microsoft runtime та публічний реліз не погоджені.
E03.08 Partial, висновку про правову сумісність не зроблено. Без
тестів/runtime/UI/network/DB/printer.

Наступний крок у E03.08: під час офіційного folder build зберегти статичний
manifest конкретних Qt DLL/modules і Microsoft runtime files та звірити їхні
notices/source-offer. `scripts/ufm_studio.spec` делегує Qt dependency
collection PyInstaller hooks, тому source/spec огляд не визначає точний вміст
артефакту. Не називати gate виконаним без manifest і review. Далі повернутися до ізольованого
typed event/receipt контракту E03.07 тільки в межах, де не потрібні заборонені
цього heartbeat поведінкові перевірки.

---

# Попередня точка продовження — E03.07 implementation dependency map — 2026-10-30

# Точка продовження — E03.07 implementation dependency map — 2026-10-30

На основі попередніх source audits складено конкретний implementation slice у `docs/INTEGRATION_DECISION_UK.md`: (1) versioned Bambu event adapter з payload provenance та однозначною occurrence identity; (2) process/local-per-printer ownership і окремий shared Haspel fence; (3) durable receipt commit до UI coalescing; (4) роздільна маршрутизація job/status/feed-slot; (5) startup replay, bounded consumer, backpressure і shutdown до SQLite dispose; (6) source-gap reconciliation; (7) перевірка owner fence на кожному legacy writer; (8) лише після цього ручна verified-file finalization. Для кожного кроку є існуючий кодовий орієнтир і критерій переходу. Це план приймання, не зміна статусу/готовності.

Оновлено E03.07 evidence у CSV, який лишився 118 рядків із 29 Виконано / 36 Частково / 52 Заплановано / 1 У роботі та UTF-8 BOM. Ліміти до цього підетапу: 86% п’ятигодинного / 39% тижневого. Жодного коду, тестів, runtime, UI, мережі, БД чи hardware не змінював/не запускав; automatic debit лишається вимкненим.

Наступна дія: перейти до першої реалізаційної залежності лише в безпечному ізольованому шарі — описати або додати pure typed conversion contract із fail-closed identity, не підключаючи production consumer і не вмикаючи accounting. Перевірки behavior лишаються обов’язковими перед просуванням статусу; heartbeat забороняє додавання/запуск тестів, отже consumer не можна оголошувати готовим зараз.

---

# Точка продовження — E03.07 process/printer ownership fence audit — 2026-10-30

Graphify навів на PrinterMonitorTask і printer accounting authority; вихідний код перевірено. В одному `StudioWindow` є лише один `_monitor_task`. Пошук у `src/ufm` не знайшов Windows named mutex, QLockFile, single-instance server або per-printer process lease. `AppPaths.resolve(root)` дозволяє альтернативний data root; printer accounting authority з revision та finalization guard читаються в конкретній SQLite DB. Це захищає лише цю базу, не інший файл/процес/ПК. У Haspel теж лишається per-process/Data_DIR boundary та старий MQTT writer.

У `docs/INTEGRATION_DECISION_UK.md` визначено шари захисту: локальний Windows mutex на принтер може закрити конкуренцію UFM процесів на одному ПК, але не має сили над Haspel чи іншими комп’ютерами; cross-product cutover потребує shared owner/fencing epoch, перевіреного кожним consumption writer навколо `/use`/PATCH. Без спільної координації дозволений лише явний ручний cutover, auto-debit лишається вимкненим. Checklist E03.07 evidence оновлено, статус Partial.

CSV: 118 рядків, 29 Виконано / 36 Частково / 52 Заплановано / 1 У роботі; BOM збережено. Ліміти перед аудитом: 86% п’ятигодинного / 39% тижневого залишку. Код не змінювався; тести, runtime, UI, мережа, DB і принтер не запускались.

Наступне: сформувати залежний implementation slice, не починаючи автоматичне списання: (1) schema-valid provider-event adapter з occurrence/event identity та payload provenance; (2) per-printer lifecycle/lease; (3) durable receipt sink before UI; (4) типізовані job/status/slot handlers і restart drain; (5) source-gap reconciliation; (6) глобальний legacy writer fence/cutover; (7) окрема ручна finalization за перевіреним 3MF/G-code. Кожну частину прив’язати до конкретних існуючих класів/модулів і критеріїв приймання; до доступу до перевірок кодовий consumer не вважати завершеним.

---

# Точка продовження — E03.07 provider reconnect, source gaps і shutdown — 2026-10-30

Звірив граф і код Bambu/Studio. Bambu MQTT підписаний із QoS 0; при з’єднанні provider надсилає `pushall` поточного стану, історичного event replay немає. Retry створює новий provider та `source_epoch` і очищує локальний report; це відновлює поточне спостереження, але не пропущені переходи. Тому пізній `IDLE` не доводить `COMPLETED`, нова epoch або невідома occurrence identity мають відкрити source-gap reconciliation та блокувати estimated finalization. Переповнення in-memory buffer є non-retryable.

Normal shutdown Studio має послідовність stop → cancel async monitor → close stream/disconnect provider → finished → close window → dispose SQLite engine/container. Новий consumer повинен зберегти цей порядок і не підтверджувати прийом при помилці DB/overflow. Висновки додано до `docs/INTEGRATION_DECISION_UK.md` та E03.07 checklist evidence.

CSV: 118 рядків, статуси незмінні (29/36/52/1), UTF-8 BOM. Ліміти на останній перевірці перед етапом: 86% п’ятигодинного / 39% тижневого залишку. Тільки статичний source/docs review; без тестів, runtime, мережі, БД чи принтера; код не змінювався. Auto-debit вимкнено.

Наступне: зібрати окрему implementation contract для одного керованого consumer lifecycle: при старті drain persisted PRINT_* receipts, потім активувати provider; кожну подію верифікувати й записати до UI coalescing; route accepted job facts до `ProjectionDrain`; status/feed facts — до визначених snapshot handlers; невизначені identity/source gaps — reconciliation. Перевірити однопроцесний lock/printer ownership і явно заборонити паралельні монітори того самого принтера.

---

# Точка продовження — E03.07 Qt consumer lifecycle integration seam — 2026-10-30

Graphify допоміг знайти lifecycle вузли; шлях звірено у Studio. `Task(QThread)` — коротка команда, не постійний consumer; `PrinterMonitorTask` уже тримає довгий asyncio stream, але його вручну запускають для одного принтера, а callback коалесує до останньої UI-події. Durable sink відсутній; buffer обмежений 256 і overflow піднімає non-retryable RuntimeError. `AppContainer` та `StudioBackend` поки не володіють receipt/drain сервісами; shutdown window зупиняє monitor до dispose SQLite engine.

У `docs/INTEGRATION_DECISION_UK.md` зафіксовано мінімальну інтеграційну межу: контрольований lifecycle, adapter і receipt commit до UI coalescing; після commit — окремий projection drain; помилка DB зупиняє/показує стан, не ігнорує event; явний shutdown handshake перед dispose; недоступні poll events не реконструювати як terminal, а відправляти на reconciliation. Оновлено E03.07 checklist evidence без зміни статусу.

CSV: 118 рядків; 29 Виконано / 36 Частково / 52 Заплановано / 1 У роботі, BOM збережено. Ліміти на останньому замірі: 87% п’ятигодинного / 39% тижневого. Код не змінювався; без тестів, UI/runtime, мережі, БД чи принтера; auto-debit вимкнено.

Наступне: перевірити provider/event identity, reconnect gaps і точну семантику shutdown у source/fixtures; після цього описати єдиний implementation slice з керованим lifecycle, маршрутизацією receipt types і replay. Автоматичному background provider потрібні явні правила щодо вибору принтерів, доступності credentials та облікового owner; поточний user-started monitor залишається лише read-only preview.

---

# Точка продовження — E03.07 pending receipt production lifecycle audit — 2026-10-30

Graphify UFM підказав `ProjectionDrain`; перевірено код і production wiring пошуком. Уже реалізовані primitives: `ReceiptIngestion.pending()` вибирає bounded PENDING receipts; repository projection query бере тільки enabled-printer `PRINT_*` receipts, сортує за received_at/ID та відсікає застосовані/заблоковані; `ProjectionDrain.run_once()` за один обмежений прохід застосовує projection idempotently або відкриває reconciliation для відхилених job observations. Ці класи не мають production-конструктора/виклику в `src/ufm`, тож post-restart replay ніхто не запускає. Водночас generic ingestion дозволяє status/slots, які job projection drain не обробляє. Документував відмінність між primitives та робочим lifecycle, вимоги bounded backpressure, provider ownership, стартового replay і окремих handlers у `docs/INTEGRATION_DECISION_UK.md`.

Оновлено E03.07 checklist evidence; статуси без змін. CSV: 118 рядків, 29 Виконано / 36 Частково виконано / 52 Заплановано / 1 У роботі, UTF-8 BOM. Останні ліміти до цього підетапу: 87% п’ятигодинного та 39% тижневого залишку. Source/docs review only; існуючі тести не запускались; код, UI, runtime, мережа, DB і принтер не змінювались/не запускались. Auto-debit вимкнено.

Наступний крок: визначити consumer lifecycle/типову маршрутизацію receipts і transactional delivery contract, використовуючи наявні application/Qt worker abstractions; чітко зберегти «persist before presentation», retry з dedupe, operator reconciliation і відсутність автоматичного finalization. Якщо зміни коду вимагатимуть tests для доказу, не вважати функцію готовою без них.

---

# Точка продовження — E03.07 snapshot-completeness evidence review — 2026-10-30

Звірив існуючі Bambu/provider fixtures та Haspel report examples, нічого не запускаючи. `tests/integration/test_bambu_lan_provider.py` навмисно розділяє mapping поточного `print.mapping` від попередніх `ams_mapping*`; `tests/unit/test_job_material_mapping.py` вимагає UNKNOWN для неповного feed snapshot. Їх лише прочитано. Приклади linked Haspel містять AMS набори з 4 слотами, multi-system та 1-slot systems без явного completeness marker. Це не специфікація Bambu; рахувати 4 слоти як ознаку повного snapshot не можна.

Зафіксовано це в `docs/INTEGRATION_DECISION_UK.md`, checklist E03.07. Статуси: 118 рядків; 29 Виконано / 36 Частково виконано / 52 Заплановано / 1 У роботі; BOM збережено. Ліміти на останній перевірці до цього read-only підетапу: 87% п’ятигодинного / 39% тижневого. Обмеження: fixtures прочитано, але тести не запускали; без runtime, мережі, баз і принтера. E03.07 Partial, auto-debit вимкнено.

Наступне: перевірити в UFM, чи є вже production worker, що бере `ReceiptIngestion.pending()` і викликає projection/reconciliation; встановити порядок, повторну обробку та чи не має pending cursor переходів. Якщо такого caller немає, сформувати bounded consumer lifecycle та критерії backpressure/restart recovery, не змінюючи auto-debit чи непідтверджену повноту AMS.

---

# Точка продовження — E03.07 Bambu job/material identity crosswalk — 2026-10-30

Graphify Bambu/UFM карти використано для навігації; перевірено вихідний код обох проєктів. `BambuLanProvider.get_current_job()` передає task/subtask/job IDs і поточний `print.mapping`, але не run key, external job ID, project UUID, file hash або точний час початку. Декодер `print.mapping` перетворює індекс у logical-material index та AMS/external slot; `ams_mapping`/`ams_mapping2` не можна підмішувати, бо в коді зазначено, що вони можуть прийти раніше з `project_file`. Підмножина logical-material індексів збігається з `VerifiedSliceFacts`/Worker Protocol.

Матеріальне зіставлення все одно закрите fail-closed: `feed_systems_from_report()` задає `complete=False`, а `job_material_mapping` вимагає hash-ідентичність файлу, printer scope, snapshot ≤120 с, єдиний system/slot, complete=true та зайнятість. Отже, поточний Bambu provider не може повертати MATCHED spool resolution на цих snapshot. Не можна виводити повноту AMS з відсутніх слотів або вгадувати новий print occurrence з повторно використаних provider IDs. Деталі додано в `docs/INTEGRATION_DECISION_UK.md`, доказ E03.07 оновлено.

CSV: 118 рядків; статуси залишились 29 Виконано / 36 Частково виконано / 52 Заплановано / 1 У роботі; UTF-8 BOM. Ліміти на останньому замірі після попереднього етапу: 87% п’ятигодинного, 39% тижневого залишку. Обмеження: source/docs-only, без тестів, UI/runtime, мережі, баз чи принтера; код не змінювався; auto-debit вимкнено.

Наступне: перевірити локальні fixtures та профільні джерела Bambu щодо явної повноти AMS slot snapshot і стабільного lifecycle identity. Якщо доказу немає, зафіксувати невизначеність у feature matrix та залишити spool mapping для ручної перевірки; не послаблювати `complete=False`.

---

# Точка продовження — E03.07 provider event → durable receipt contract audit — 2026-10-30

Граф UFM використано для навігації, потім звірено живий код. Bambu `PrinterEvent` містить нормалізований snapshot і digest canonical JSON, але не байти report; `source_epoch` випадковий на екземпляр provider, `event_key` є лише лічильником у межах epoch. `ReceiptIngestion` натомість очікує raw bytes та Worker Protocol v1 `StatusMessage`/`JobMessage`/`SlotsMessage`; production caller відсутній. Отже, пряме передавання hash як raw payload некоректне, а ключ epoch/event не є глобальним print ID. Документовано потрібний versioned adapter, provenance/hash правила, stable occurrence identity або fail-closed reconciliation та ingestion до UI coalescing у `docs/INTEGRATION_DECISION_UK.md`.

Виконано: попередній audit перевірив втрату проміжних monitor events через `take_latest_event()`; тепер встановлено контрактні несумісності для безпечного durable consumer. Оновлено доказ E03.07 у checklist і handoff. CSV: 118 рядків, статуси без змін — 29 Виконано / 36 Частково виконано / 52 Заплановано / 1 У роботі; UTF-8 BOM збережено. Остання перевірка лімітів: 88% п’ятигодинного, 39% тижневого залишку.

Обмеження: лише статичний source/docs review, без тестів, запуску UI/runtime, мережі, баз чи принтера. Жоден production consumer/adapter не додано; automatic debit лишається вимкненим, E03.07 — частково виконано. Наступне: звірити job identity та mapped logical-material поля проти provider DTO і протоколу; лише після цього додавати окремий adapter/inbox consumer з bounded backpressure та restart recovery. До того ж потрібен глобальний/міжпроцесний fence для legacy AMS PATCH writer.

---

# Точка продовження — E03.07 аудит legacy writer HaspelSync — 2026-10-30

Перевірив HaspelSync шляхами з Graphify та звірив у вихідному коді. У `src/mqtt.js`, `processSlot()` у legacy-mode напряму викликає `patchSpoolWeight()` за відсотком AMS RFID. Цей запис не створює booking intent і не входить до `activeBookingIds`, якими `transferAccountingAuthority()` захищає передачу власника. Тому transfer може не побачити активний/незавершений legacy PATCH. `routes.js` відхиляє ручне зважування в legacy mode, але це не закриває MQTT шлях. Також ця схема не доводить відсутність іншого процесу, старої версії або іншого DATA_DIR.

Це статичний аудит, без тестів, runtime, HTTP, БД чи принтера. Поведінкові зміни в linked Haspel не внесені: для коректного закриття потрібен узгоджений writer gate, який охоплює початок і завершення legacy PATCH та transfer, recovery після зупинки/невизначеного запиту і перевірку всіх інших writers; локальна перевірка owner перед PATCH сама по собі не усуває race. E03.07 — частково виконано; auto-debit вимкнено. CSV лишається 118 кроків, 29 Виконано / 36 Частково / 52 Заплановано / 1 У роботі; UTF-8 BOM збережено. Поточна остання перевірка лімітів після parity аудиту: 88% п’ятигодинного та 39% тижневого залишку.

Статичний source-аудит уточнив parity `F048` і `F071`: `ReceiptIngestion` уже має durable scoped/idempotent запис, а `PrinterMonitorTask` має reconnect/backoff, health та sleep-resume detection; обидві функції раніше були помилково лише `Додати`. Monitor запускається користувачем, зупиняється зі Studio, UI відкидає проміжні події до останньої, а monitor не викликає `ReceiptIngestion`. Обидві функції позначено `Частково`; це не автоматичний облік. Feature matrix: 124 рядки, Є 28 / Частково 30 / Додати 46 / Бажано 20. Ціль no-Docker: native UFM providers/application із власним ledger; Haspel API лише migration/cutover, Node — calculation helper. Наступне: спроєктувати durable provider-to-inbox consumer; до його активації закрити legacy AMS in-flight writer fence. Auto-debit вимкнено.

---

# Поточна точка продовження — E03.07 Haspel→UFM owner transfer — 2026-10-30

Майстер облікового виконавця показує endpoint/printer ID, дає явно перевірити Haspel capability та бачити owner/revision/pending/uncertain/active. Для переходу `CUTOVER_READY → UFM_ACTIVE` тепер обов’язкова свіжа перевірка вибраної Haspel служби: owner має бути `LEGACY_ACTIVE`, усі три лічильники — 0. Після підтвердження backend повторно читає remote стан, звіряє revision, надсилає CAS transfer до `UFM_ACTIVE`, перевіряє відповідь, а потім фіксує локальний UFM authority. Якщо локальна активація не підтвердилась, перевіряє локальний стан і намагається перевести той самий remote revision у `REVIEW_ONLY`; помилки та невизначений результат показуються без endpoint/key/response деталей. Endpoint-конфігурація, OS credential та remote observation залишаються окремими від Bambu.

Обмеження: компенсація best-effort; remote процес може бути недоступний. Haspel owner працює лише в межах вибраної служби/process/DATA_DIR і не блокує інші старі/паралельні екземпляри чи іншу UFM-базу. Remote snapshot/cache не є глобальним lock. Режим `UFM_ACTIVE` не вмикає сам по собі `EstimatedUsagePolicy`; automatic estimated debit лишається вимкненим. E03.07 частково виконано.

Статична перевірка після змін: Ruff clean; mypy clean для п’яти змінених модулів; JSON локалізації читається. Тести, UI/runtime, мережеві виклики, DB migration, реальні бази та принтер не запускали.

CSV: 118 кроків; Виконано 29, Частково виконано 36, Заплановано 52, У роботі 1; UTF-8 BOM збережено. Ліміти на останній перевірці: 92% залишку п’ятигодинного, 40% тижневого.

Graphify оновлено після UI/backend змін: UFM 232 файли / 5891 вузол / 21790 ребер; Spoolman 298 / 4920 / 15554; UFM↔Spoolman 530 / 10763 / 37344; traceability 729 файлів / 12846 вузлів / 44396 ребер; enriched 28743 вузли / 84882 ребра. Граф — тільки навігація.

Наступна дія: спроєктувати cross-process single-writer fence, контроль паралельних Haspel/UFM екземплярів і live revalidation перед estimated finalization. До появи доказу глобального власника та recovery не вмикати automatic debit.

---

# Поточна точка продовження — E03.07 read-only Haspel status у Studio — 2026-10-30

У майстрі облікового виконавця додано поля для origin HaspelSync, його printer ID і нового API key, кнопку явної перевірки/читання стану та статус capability. Збережена конфігурація підставляє лише endpoint/printer ID; секрет не читається в поле. Введений ключ очищається відразу після натискання й передається тільки в операцію backend. Backend спершу читає remote capability; тільки при успіху зберігає ключ у SecretStore ОС та endpoint-конфігурацію. Ключ не зберігається в SQLite або Bambu profile. Успішна відповідь показує owner, remote revision, pending/uncertain/active. Цей UI-крок не виконує transfer і не активує списання.

Статична перевірка: Ruff clean; mypy clean для 5 змінених Python-модулів; `studio_strings.json` валідний JSON. Тести, UI/runtime, HTTP-запит, міграція БД, база та принтер не запускалися. E03.07 лишається частковим. Забезпечення єдиного writer між процесами/DATA_DIR, керований transfer перед UFM_ACTIVE, безпечний rollback та live revalidation finalizer ще не готові; auto-debit вимкнено.

CSV: 118 кроків; Виконано 29, Частково виконано 36, Заплановано 52, У роботі 1, Заблоковано 0, Відкладено 0; UTF-8 BOM збережено.

Наступне: перевірити Graphify карту після оновлення графа, далі спроєктувати атомарний порядок transfer Haspel→UFM із компенсацією/fail-closed; до доведення міжпроцесного single-writer fence не дозволяти автоматичне списання.

---

# Поточна точка продовження — E03.07 persisted Haspel connection — 2026-10-30

Додано вузький `HaspelAuthorityClient` для capability-v1 API та його експорт у пакеті: strict parser для owner/revision/pending/uncertain/active counts; bounded response; відключені proxy та redirects; percent-encoded printer id; API key лише як `SecretValue` в Authorization header. HTTPS із перевіркою стандартного TLS і private/local destination для віддаленого сервісу; HTTP дозволений лише для loopback.

Додано revision 0007 і таблицю `haspel_authority_connection` для окремих endpoint origin, Haspel printer id, OS credential reference та останнього remote observation. `StudioBackend` тепер може перевірити GET API перед записом конфігурації, покласти API key у переданий `SecretStore`, а не в SQLite; потім читати/передавати remote authority та оновлювати кешоване спостереження з optimistic local revision. Жодна БД не мігрувала, мережевий endpoint не викликався; ці шляхи ще не підключені до UI.

Кешований `observed_revision/owner` — лише минуле спостереження, не джерело дозволу. Клієнт і сховище поки не під’єднані до Studio wizard чи calculated finalizer і не закривають race/інший Haspel process або DATA_DIR. Haspel API key має повні права; не передавати його віддаленому серверу через HTTP. Ruff/mypy clean для зміненого backend/client/migration manager; перевірено JSON міграції статичним парсингом. Тести, runtime, мережа та міграція БД не запускались. E03.07 лишається частковим, автоматичне списання вимкнене. Наступне: під’єднати UI для налаштування endpoint/API key і читання capability; далі окремо інтегрувати remote transition з локальним authority wizard та визначити fail-closed revalidation перед кожним estimated finalization. Якщо доказ міжпроцесного single-writer fence відсутній, зберегти блокування debit.

E03.06: deterministic package-resource sync and official Node.js v24.22.1 archive/executable SHA-256 checks are wired into the standalone build. PyInstaller folder build succeeded in `%TEMP%`; static manifest confirms `_internal/runtime/node.exe`, its bundled LICENSE, Haspel worker, calculation/shared resources, Haspel LICENSE and provenance. Rechecked the four runtime/resource hashes; bundled Node `--check` passed for worker and calculation module; Ruff and PowerShell parser checks are clean. No DB/log/linked-stack payload found in the bundle. The Python wheel includes the worker/resource closure but intentionally omits Node. This is packaging evidence only: no EXE/GUI/worker launch or product tests in this stage.

E03.07: extended (without replacing) the user-owned linked HaspelSync working tree. Its booking journal now has an optional per-printer owner/revision map; legacy schema-v1 journals default to LEGACY_ACTIVE. New Haspel print bookings are denied unless the service owner is LEGACY_ACTIVE. Added authenticated-by-existing-API-middleware GET/POST `/api/print/{printerId}/accounting-authority`, revision checking, request-ID retry handling, active/pending/uncertain guards, and OpenAPI docs. Static Node syntax checks and diff check passed. This is per-service state only: no interprocess lock, no detection of older/other Haspel instances or other DATA_DIRs, and no UFM client/revision revalidation yet. Do not enable automatic debit.

Graphify traceability and derived maps refreshed after this Haspel authority change: 727 files / 12761 nodes / 44057 edges; enriched graph 28658 nodes / 84543 edges. Counts are navigation metadata, not runtime proof. CSV: 118 steps; Partial 36 / Done 29 / Planned 52 / In progress 1; UTF-8 BOM preserved. At this heartbeat, Codex usage is 99% five-hour remaining / 41% weekly remaining. Next: implement the UFM adapter to read/transfer ownership on the selected authenticated Haspel service, bind its exact revision to UFM activation/finalization, and fail closed on mismatch/unavailable/unknown capability. Then determine how to detect competing Haspel instances/DATA_DIRs. Keep auto-debit off until race, restart and recovery behavior are validated. Preserve all linked Haspel working changes.

---



# Поточна точка продовження — E03.07 Studio authority wizard — 2026-10-29

Під’єднано кнопку «Власник обліку філаменту» на сторінці принтерів до `PrinterAccountingAuthorityCommands`. Майстер читає поточний per-printer режим/ревізію та відображає збережені SHA-256 і UTC-часи, показує лише дозволені переходи та застосовує їх через audited revision-checked UoW. Для CUTOVER_READY вибираються `bookings.json` і `accounting.json` HaspelSync (до 16 MiB кожен) та SQLite snapshot Spoolman (до 64 MiB). Read-only parser перевіряє схеми/цілісність, блокує pending/uncertain bookings для серійного номера принтера та всі pending/uncertain weighings. Окрема перевірка Spoolman порівнює source fingerprint з останнім імпортом і кожну котушку в UFM за детермінованим ID, залишком та archived state; будь-які пропущені/розбіжні котушки блокують перехід. Також latest Haspel booking/weighing activity мусить бути не новішою за час останнього імпорту в UFM — stale snapshot не пройде навіть якщо його hash формально відповідає попередньому імпорту. Оператор явно підтверджує, що SQLite належить саме endpoint HaspelSync і що writer/autostart зупинено; evidence SHA-256 повторно обчислюється перед записом і мусить збігтися зі збереженим CUTOVER_READY перед UFM_ACTIVE. UFM_ACTIVE вимагає окремого підтвердження та використовує тільки збережені evidence зі стану CUTOVER_READY. Перехід не запускає HaspelSync, worker або списання. Відсутній authority row залишається REVIEW_ONLY; локальний прапорець не є distributed lock і не доводить стан віддаленої служби.

Перевірки: Ruff clean; mypy success для authority command, Haspel/Spoolman preflight, StudioBackend і StudioWindow; `compileall` цих модулів та JSON локалізації valid. `uv build --wheel` успішний; огляд 154-entry wheel підтвердив наявність parser, importer, StudioWindow і localization. Це не інсталятор і не runtime proof. Тести, UI/runtime, міграцію, реальні БД та hardware не запускали. CSV — 118 рядків; Частково 36 / Виконано 29 / Заплановано 52 / У роботі 1; UTF-8 BOM збережено.

Ще потрібно: операторська перевірка UI; автоматизований fence/health для віддаленого Haspel writer поки відсутній і може потребувати міжпроцесного coordinator/протоколу. Поки це не реалізовано, CUTOVER_READY не є доказом автоматичного вимкнення старого writer, а чекбокси лишаються operator attestations. Не вмикати auto-debit лише через локальний mode.

Наступна конкретна дія: перевірити HaspelSync API/супервізор на підтримку безпечного remote pause/health handshake. Якщо його немає, описати технічний blocker і зберегти ручний cutover як обов’язкову умову; не видавати local DB row за distributed lock. Паралельно перейти до E03.06 worker packaging gap (wheel не містить linked Haspel source/dependencies). Тести не запускати без окремого запиту.

---

# Поточна точка продовження — E03.07 audited authority transitions — 2026-10-29

Реалізовано `PrinterAccountingAuthorityCommands.transition()`: optimistic `expected_revision`, deterministic request hash, idempotent audit replay, explicit allowed transition graph та AuditEvent у тій самій UoW. Початковий запис може бути лише REVIEW_ONLY/LEGACY_ACTIVE; CUTOVER_READY потребує snapshot SHA-256, timestamp звіряння та timestamp операторської фіксації зупинки Haspel; UFM_ACTIVE дозволений тільки з CUTOVER_READY та тими самими evidence values. Перехід назад спершу проходить REVIEW_ONLY, після чого можна зафіксувати LEGACY_ACTIVE.

Статичні перевірки: Ruff clean; mypy success для command, finalizer, persistence/schema/migration modules. Міграцію не застосовували; тести, UI/runtime/hardware не запускалися, реальні БД не відкривали. CSV: 118 рядків; Частково 36 / Виконано 29 / Заплановано 52 / У роботі 1; BOM збережено.

E03.07 частковий: Studio wizard не підключений; немає механічного способу перевірити, що віддалений Haspel справді вимкнений, timestamp залишається операторською атестацією. Локальний owner state не є distributed lock. Auto-debit лишається disabled за замовчуванням.

Наступна дія: підключити окремий Studio wizard до command із preview checklist, snapshot file/hash, unresolved/uncertain booking checklist, explicit confirmation, mode/revision display та rollback через REVIEW_ONLY. Не вмикати Haspel writer із UFM і не запускати списання без завершеного cutover.

---

# Поточна точка продовження — E03.07 default-deny accounting gate — 2026-10-29

Додано `PrinterAccountingMode`, `PrinterAccountingAuthority`, таблицю `printer_accounting_authority`, migration `0006_printer_accounting_authority`, repository/UoW port і gate у `CalculatedFinalizationCommands`: відсутній рядок або mode не `UFM_ACTIVE` блокує estimated finalization до calculator і повторно всередині транзакції запису. `CUTOVER_READY`/`UFM_ACTIVE` вимагають SHA-256 snapshot та timestamp операторської фіксації зупинки legacy writer. Read-only preview та звичайне фактичне finalization не змінювались.

Перевірки: Ruff clean і mypy success для змінених Python modules; migration JSON статично читається. Тести не запускались; міграцію до БД не застосовували, runtime/UI/hardware не запускали. Реальні БД не відкривали. Чекліст: 118 рядків; Частково 36 / Виконано 29 / Заплановано 52 / У роботі 1; BOM збережено.

E03.07 лишається `Частково виконано`: перехідний command/UI відсутній, тож через Studio поки неможливо встановити `UFM_ACTIVE`; operator timestamp не доводить, що віддалений Haspel процес справді вимкнено. Локальний gate не є distributed lock. Автоматичне списання не вмикати до explicit transition workflow та перевіреного cutover.

Наступна дія: реалізувати application command для revision-checked, audited переходів, який за замовчуванням створює лише `REVIEW_ONLY`, а `UFM_ACTIVE` допускає тільки після cutover snapshot, вирішених невизначених booking-ів та явного операторського підтвердження. Потім під’єднати окрему Studio wizard із fail-closed transition preview/confirm; не стартувати Haspel writer з UFM.

---

# Поточна точка продовження — E03.07 UFM-side single-writer guard audit — 2026-10-29

Graphify-навігація вказала на `calculated_finalization.py`, receipt, ledger, job projection та Haspel `bookings.js`/`mqtt.js`; усі поведінкові висновки звірені у вихідному коді. UFM вже має локальний fail-closed guard: `EstimatedUsagePolicy.enabled=False` за замовчуванням, preview працює без запису, `finalize()` відхиляє disabled policy, а `_verify()` повторно перевіряє policy та scope перед зміною котушок, ledger, receipt і audit в одній UFM UoW. Це не є міжпроцесним lock/owner contract. Haspel лишається окремим writer-ом через Spoolman `/use` і PATCH `last_used`; його idempotency-журнал локальний і не координується з UFM.

E03.07 лишається `Частково виконано`: немає persisted per-printer owner/cutover proof або способу UFM перевірити, що legacy Haspel writer справді вимкнено. Не вмикати estimated debit тільки зміною policy flag; потрібен операторський cutover/rollback із перевіркою старого writer і атомарним ledger reconciliation. Статичний огляд; тести, runtime та hardware не запускалися.

Наступна дія: реалізувати durable per-printer authority schema/repository та fail-closed перевірку у calculated finalizer за цим контрактом; окремо додати revisioned transition command і operator UI після статичної перевірки міграції. Не запускати автоматичне списання до фактичного Haspel cutover.

---

# Історичний checkpoint — E03.06 Haspel worker packaging audit — 2026-10-29 (оновлено 2026-10-30)

Зіставлено наявні `src/ufm/integrations/haspel_calculation.py`, `src/ufm/integrations/haspel_worker.mjs` і `CalculationWorkerTransport`; worker повертає лише `ProposalMessage` зі статусом `needs_mapping`, без allocations і ledger/Spoolman-команди. Для partial викликає `calcPartialConsumption()` із linked Haspel `gcode.js`; позитивна витрата без layer ranges відхиляється. Для full маса береться з перевірених UFM facts.

Перевірена фактична wheel-збірка командою `uv build --wheel --out-dir <тимчасова папка>`: з 149 записів wheel містить `haspel_worker.mjs` і Python adapter, але не містить `linked-stack/haspelsync/src/gcode.js`. Отже наявний відносний імпорт у worker у wheel не має цілі; wheel також не постачає Node runtime чи npm dependencies. Це підтверджує, що кодова наявність worker не дорівнює готовності standalone distribution. Артефакт залишився в `%TEMP%`, репозиторій не отримав `dist/`.

Статичний import-closure обхід знайшов 8 локальних Haspel-файлів та зовнішні пакети `basic-ftp`, `adm-zip`, `dotenv`. `config.js` пропускає dotenv при `NODE_TEST_CONTEXT`, який transport встановлює; `settings.js` читає `settings.json` при імпорті, але її `loadSettings()` не записує файл. `logger.js` змінює `console.log/error`; його виклики можуть писати у `LOG_DIR`, який transport спрямовує до worker workdir. Ці модулі запускаються лише в дочірньому процесі, але їхню ізоляцію ще треба перевірити при production caller. Копіювати всю HaspelSync-службу або лише додати каталог до wheel небезпечно: це затягне зайві модулі, залежності й GPL-3.0-only notice obligations.

Статика: `node --check` canonical worker clean; попередні Ruff/mypy чисті. Тести, runtime, UI, реальні 3MF, DB і hardware не запускалися. E03.06 лишається `Частково виконано`: calculation-only resource closure та bundled Node для PyInstaller folder build вже мають статичний provenance/hash proof (див. handoff 2026-10-30); production caller/receipt bridge, runtime isolation acceptance та single-writer authority/cutover ще відсутні. Автоматичне списання UFM не вмикати. E04.04 лишається preview-only; Haspel fingerprint не порівнюється з UFM `FeedSlotSnapshot`.

Чекліст: 118 рядків; Частково 36 / Виконано 29 / Заплановано 52 / У роботі 1; UTF-8 BOM збережено.

Це знімок стану на 2026-10-29. Подальші дії про worker-resource sync, runtime bundling, provenance та статичну перевірку PyInstaller описані в handoff від 2026-10-30; ці пізніші докази замінюють тодішній план щодо resource closure. Production receipt/finalization bridge та single-writer authority все ще не завершені; не вмикати auto-debit.

---

# Поточна точка продовження — E04.04 desktop HaspelSync preview — 2026-10-29

Додано офлайн-парсер `src/ufm/integrations/haspelsync/config_import.py`, CLI `--haspelsync-preview PRINTERS_JSON MAPPINGS_JSON ID_MAP_JSON` та кнопку попереднього перегляду в Studio → «Система». Користувач вибирає `printers.json`, `mappings.json` і versioned Spoolman ID map UFM. Preview перевіряє ID map SHA-256, schema v0/v1 і crosswalk AMS/HT/external, показує totals та перші 100 слотів. Код доступу, IP і fingerprint values не виводяться; preview не створює мережевих з’єднань, не застосовує конфігурацію і не змінює ledger. Qt dialog примусово PlainText; нормалізовані дублікати serial у mappings відхиляються, IP helper повертає лише boolean. Haspel format звірено з `linked-stack/haspelsync/src/mappings.js` і `printers.js`.

Перевірки: Ruff clean для parser/CLI/Studio; mypy success у 4 файлах; studio strings та обидва locale JSON — valid. Тести, UI runtime, Haspel runtime files, реальні БД та принтер не використовувалися.

E04.04 лишається `Частково виконано`: код має лише preview, settings allowlist review завершено, а окреме явне застосування, policy для conflicts, live slot/fingerprint verification і acceptance ще відсутні. Статуси: 118 рядків; Частково 36 / Виконано 29 / Заплановано 52 / У роботі 1; BOM UTF-8 збережено.

Зіставлення налаштувань (`linked-stack/haspelsync/src/settings.js` ↔ `src/ufm/bootstrap/settings.py`) показало, що mode, legacy RFID accounting, auto-assign, endpoint, polling/retry та log semantics не мають безпечного one-to-one переносу. Haspel `settings.json` не вибирається і не читається. Printer serial/name — лише match/display hints; LAN address — лише discovery hint; code потрібно окремо ввести через Credential Locker. Рішення внесене в `docs/INTEGRATION_DECISION_UK.md`.

Уточнено блокер slot mapping: UFM `FeedSlotSnapshot` не містить Haspel `tray_info_idx`/`tray_type`/color fingerprint, лише slot key, occupancy, trusted `tray_uuid`/`tag_uid`, assigned spool і mass; порівняння fingerprint неможливе без розширення перевіреного provider contract. Наразі mapping із файла лишається підказкою, не mount.

Наступна дія: перевірити залежний E03.06 single-writer authority contract і те, як він має gate-ити будь-яке майбутнє застосування імпортованих mapping hints. Звірити proposal/staged-vs-active design з E03.07; не торкатися E04.05 історії, доки writer ownership не визначений.


## E03.06 dependency checkpoint: old writer remains independent — 2026-10-29

Read-only code review confirms `linked-stack/haspelsync/src/mqtt.js:bookConsumption()` calls `src/spoolman.js:useSpoolWeight()`, which commits directly to Spoolman `/api/v1/spool/{id}/use`, journals the attempt, and separately patches `last_used`. UFM `CalculationWorkerTransport` is bounded one-shot and strips provider credentials, but the bundled Node calculate entrypoint, live receipt/proposal bridge, and shared authority endpoint/store/lock are absent. Thus E03.06 and E03.07 remain Partial; do not enable UFM auto-debit while an old writer may still run.

This also gates Haspel mapping application: the import preview remains read-only. E04.04 has no safe automatic mount path until writer ownership enforcement is implemented and accepted. No Haspel source/runtime data, tests, database, or hardware were changed.


---

# Поточна точка продовження — E04.04 безпечне зіставлення принтерів/слотів — 2026-10-29

## Останні завершені етапи

- E04.02: `spoolman_import_source`, migration 0005, legacy-token backfill і явний source selector у Studio/desktop/CLI. Legacy UUID формули збережені. Runtime acceptance на контрольній копії не проводилося.
- E04.03: імпорт повертає versioned JSON ID map vendor/filament/spool лише після успішного проходу записів. CLI/GUI показують шлях. Alias для зміни зовнішніх IDs і контрольна копія лишаються.
- E04.04: read-only аудовано HaspelSync printer/mapping formats і UFM printer/feed-slot schema. Сформовано crosswalk AMS та external slot keys; визначені межі секретів і обов’язкового live verification.

## Висновок E04.04 та безпечні межі

Haspel `printers.json` зберігає id/code/ip/name; `code` є LAN secret. У UFM відповідають display name, serial, model і connection profile host/port/TLS, а credential зберігається через ОС Credential Locker. Credentials/API keys/password hashes/TLS trust material не імпортувати: користувач повторно вводить код і UFM окремо перевіряє сертифікат. Haspel mapping — serial + label (`A1`, `HT-A`, external) → Spoolman integer spool ID, fingerprint і optional automatic origin. UFM потребує source map E04.03 та provider slot identities `ams:{unit}` / `{unit}:{slot}` або `external` / `external`; остаточне mount робити лише після свіжого відповідного слота. `printstate.json` — runtime recovery, не конфіг; його не можна перетворювати на поточний UFM job без exact run provenance. Haspel runtime files не відкривалися.

## Перевірки та наступні дії

E04.02/E04.03/E04.04 — `Частково виконано`. Не запускали тести, інтерфейси, міграцію користувацьких БД чи мережеве підключення. Наступне: спроєктувати явний Haspel export/import preview з allowlist полів, потрібними crosswalk confirmations, secrets-excluded summary, mapping/unknown/conflict totals і dry-run; потім імплементувати застосування тільки після окремої явної дії UI, без запуску імпортера під час відкриття файла. Тести не запускати без прямого прохання. CSV: 118; Частково виконано 36 / Виконано 29 / Заплановано 52 / У роботі 1; BOM UTF-8 збережено.

---

# Поточна точка продовження — E04.02 source identity — 2026-10-29

Граф UFM звірено з живим кодом: Spoolman importer окремий локальний контур. У поточному `_source_instance()` ID джерела = hash абсолютного шляху; переміщений файл отримує інший source ID. Перевірено стандартний реєстр налаштувань/моделі локального Spoolman: явного installation UUID серед перевірених полів немає. Не можна виводити ідентичність лише з числових spool/filament ID або mutable content, бо незалежні інстанси можуть мати ті самі ID/дані.

У `docs/INTEGRATION_DECISION_UK.md` зафіксовано напрям: UFM-owned immutable source instance ID + registry/alias; при неоднозначності користувач вибирає попереднє джерело або створює нове; конфлікт ключа з несумісними даними зупиняє імпорт. Старі path-hash ID треба зберегти явною alias-відповідністю. Код ще не змінений, тому E04.02 лише частково виконано.

CSV: 118 рядків, Частково виконано 34 / Виконано 29 / Заплановано 54 / У роботі 1; UTF-8 BOM збережено. Обидві локальні БД не відкривали й не змінювали. Наступна дія: спроєктувати registry migration/модель E04.02 та її replay/conflict semantics, а потім реалізувати source selector у preview/CLI/UI; не міняти існуючі UFM IDs автоматично.

---

# Поточна точка продовження — E04.01/E04.07 імпорт Spoolman — 2026-10-29

У `src/ufm/integrations/spoolman/importer.py` додано перенесення номера партії (`spool.lot_nr`) і валідного кольору (`filament.color_hex`) у порожні поля котушки. Текстова `spool.location` створює окрему локацію UFM типу `OTHER` і призначається котушці. Імпорт не перезаписує вже непорожні lot/color/location, а зміни метаданих виконуються через `InventoryCommands`/`StorageCommands`, окремо від початкового stock ledger.

Попередній перегляд тепер показує кількість кандидатів для партій/кольорів/локацій та кількість непідтримуваних метаданих у Studio, desktop UI і CLI. Непідтримані/надто довгі значення не переносяться і враховуються в лічильнику. Spoolman не дає підстав виводити дати купівлі/виробництва чи ієрархію з довільної локації; їх не синтезуємо. Ідентичність джерела ще заснована на шляху файла — переміщення та multi-source reconciliation лишаються E04.02/E04.03.

Перевірки: Ruff clean для importer, Studio, desktop і CLI; mypy clean для цих 4 Python-файлів; три JSON-файли локалізації валідні. Тести не запускалися й не змінювалися. Джерельну та цільову БД користувача не відкривали і не змінювали; код імпорту тепер реалізує ці додаткові поля при майбутньому явному запуску.

Чекліст: 118 рядків, Частково виконано 33 / Виконано 29 / Заплановано 55 / У роботі 1; UTF-8 BOM збережено. E04.01 і E04.07 тепер «Частково виконано», не «Виконано».

Наступна дія: E04.02 — прибрати залежність джерельної ідентичності від шляху файла, не зливати незалежні Spoolman інсталяції з однаковими числовими ID і зберегти повторюваність імпорту після переміщення копії. Спершу потрібен безпечний source-instance ключ/реєстр, потім перевірка E04.03 для збереження вже наявних UFM ID.

---

# Поточна точка продовження — E07.03 exact lifecycle timestamps — 2026-10-29

`JobMessage` доповнено optional `exact_started_at`/`exact_ended_at` з обов’язковим парним provenance `printer_reported` або `provider_reported`. Кінець дозволено лише для terminal state; неприпустиме джерело/неповна пара/кінець перед початком відхиляються. `JobProjectionCommands` зберігає точний start та completed/failed/cancelled time у вже наявні поля `PrintJob`; точний час не підміняється `observed_at`. Конфліктує зміна збереженого часу чи provenance, а майбутні timestamps не приймаються. Необроблена provenance залишається в immutable receipt і mapping history; schema БД не змінена. Оновлено worker JSON Schema, lifecycle/protocol docs та E07.03 checklist.

Перевірки: Ruff clean для двох змінених модулів; mypy success для `worker_protocol.py` і `job_projection.py`; `docs/WORKER_PROTOCOL_V1.schema.json` розбирається як JSON. Тести не запускалися й не додавалися. Live Bambu/HTTP адаптери досі не передають ці exact timestamps, consumer не під’єднаний, отже це лише durable contract/persistence, не автоматичний облік.

Статуси чекліста (118): Частково виконано 31, Виконано 29, Заплановано 57, У роботі 1.

Наступна дія: не брати час із `observed_at`; перевірити authoritative Bambu report field/time semantics або залишити поля NULL. Далі реалізувати bounded FIFO→durable consumer лише після точного occurrence/provenance контракту й єдиного writer authority.

---

# Поточна точка продовження — 2026-10-29

## E07.03/E07.04: джерельна ідентичність і межа durable ingestion

Підтверджено по коду: `PrinterMonitorTask` накопичує `PrinterEvent` у bounded FIFO, але `rg` не знаходить викликів `ReceiptIngestion` або `ProjectionDrain` у `src`. `PrinterEvent` не містить первинних payload bytes; Bambu LAN формує SHA-256 від вибраного canonical snapshot. `PrintJobSnapshot.provider_run_key` є необов’язковим і Bambu provider його не заповнює; наявні task/subtask/job IDs не можна вважати ключем конкретного фізичного запуску без задокументованої семантики. Локальні `event_key` є лічильниками в межах `source_epoch`, а epoch створюється на екземпляр підключення. `ReceiptIngestion` вимагає worker-protocol payload і саме рахує hash перед збереженням.

Рішення: автоматичне проєктування job/списання не під’єднувати, поки адаптер не надає перевірений стабільний run identity, provenance payload/hash і reconnect/order contract. Не виводити ідентичність із назви файла або самостійно згенерованого occurrence key. Після цього можна реалізувати окремий batch consumer із fail-closed quarantine та backpressure, а потім перевірити порядок/replay/reconnect.

Чекліст: 118 пунктів; Частково виконано 31, Виконано 29, Заплановано 57, У роботі 1. BOM CSV збережено. Перевірка цього етапу — читання коду та пошук викликів; UI/тести/MQTT/принтер не запускалися.

Звірено локальні джерела Bambu Studio та власний HaspelSync (див. docs/CONSUMPTION_COMPARISON_UK.md): BBLSubTask task_id названий plate ID; HaspelSync відновлює startedAt за printer+jobName і дедуплікує запис за printer+startedAt+itemKey із pending/uncertain журналом. Це корисний recovery-pattern, але не доводить exact LAN run ID. Наступне: знайти/зафіксувати MQTT-приклади локального старту, повторного того самого файла й reconnect та звірити поля; до цього live accounting вимкнений.

Перевірка E07.05 без запуску тестів: у `test_job_projection.py` уже є синтетичні випадки `same_file_two_sequential_occurrences_remain_distinct`, `missing_start_is_durable_ambiguity_without_invented_interval`, `layer_reset_and_hash_change_are_conflicts_without_rewriting_facts` та `concurrent_occurrence_or_epoch_reconciles_both_runs_without_merging`. Вони перевіряють application contract, але не live MQTT. `linked-stack/haspelsync/test/fixtures/reports` містить статичні `pushall` snapshots; на деяких моделях task/subtask/job ID відсутній/нульовий. Потрібні часові траси для старту, двох послідовних запусків і reconnect.

---

## E05.07 checkpoint: налаштування мови в UI — 2026-10-29

Сторінка «Система» має перемикач Українська/Англійська й кнопку збереження. Вибір проходить allowlist `uk-UA`/`en-US`, записується атомарно через `save_settings()` у config/settings.json, при помилці БД налаштувань не зачіпається; після зміни показується повідомлення про перезапуск для застосування на всіх екранах. Додано вибір рівня DEBUG/INFO/WARNING/ERROR/CRITICAL: allowlist, атомарне збереження й негайне оновлення рівня `container.logger`; журнал не виводиться в UI. Перевірки: Ruff clean для `studio_window.py`, strings JSON валідний; mypy для двох змінених модулів завершився Success: no issues found in 2 source files після виправлення всіх 12 діагностик. UI-тести не запускалися.

E05.07 лишається «Частково виконано»: новий language/log-level/log-view/inventory-export UI потребує acceptance; мова застосовується після restart, решта системних дій ще відкриті. CSV: 118 рядків; Частково 31, Виконано 29, Заплановано 57, У роботі 1. Наступна дія: додати контрольований вибір рівня журналювання з валідацією та застосуванням до наступного запуску; не відкривати журнали з секретами у UI.

## E05.08 checkpoint: validation форм профілю матеріалу й виробника — 2026-10-29

`StudioWindow.form()` перед прийняттям діалогу перевіряє поля, позначені обов’язковими, і значення QValidator; помилка показується в діалозі, користувач може виправити значення без повторного відкриття форми. У `material_fields()` задані межі diameter/density/температур/швидкості/часу сушіння та довжина текстових полів; десяткові поля використовують C locale, сумісну з `Decimal` persistence. Форми створення/редагування виробника мають обов’язкову назву. Зміна не торкається репозиторію напряму: submit і надалі викликає `StudioBackend`/`CatalogCommands`. Статичні перевірки: Ruff clean для Studio і QR helper; `studio_strings.json` — валідний JSON. Mypy для `studio_window.py` і QR helper спочатку виявив 12 старих typing diagnostics; виправлено всі (QDate conversion, Qt model cast, optional measurement net, callback types). Тепер mypy завершився Success: no issues found in 2 source files. UI-тести не запускалися.

E05.08 лишається «Частково виконано»: inventory action registry розширено з 18 до 22 дій, зокрема зафіксовано QR export/print cancel/error та partial-job межі. Для чотирьох нових QR дій та inline validation потрібен UI acceptance запуск; інші catalog/location/report/import/backup negative states лишаються предметом подальшого review. E05.04 залишається «У роботі»: окремого реального ScaleProvider/UI підключення до обладнання немає. CSV: 118 рядків; Частково 31, Виконано 29, Заплановано 57, У роботі 1. Наступна дія: після UI-перевірки продовжити помилкові/недоступні стани інших E05.08 дій; не заявляти hardware SCALE без конкретного протоколу/пристрою.

## E05.05 checkpoint: QR-етикетки, експорт і batch-друк — 2026-10-29

Є експорт SVG і системний друк однієї вибраної котушки; batch selector має спільний вибір кількох котушок для batch print або SVG export. Batch export створює окрему папку з випадковим суфіксом у вибраній користувачем директорії, тому не перезаписує попередній експорт. Batch print відкриває системний `QPrintDialog` і друкує одну сторінку на котушку. Перед друком задаються ширина/висота 20–300 мм (default 80×45); зменшення до доступної області не змінює пропорції. Self-contained SVG має назву, профіль/матеріал, колір, поточний залишок і QR канонічного UFM UUID. QR — лише ID, не mount/debit. Перевірки: `uv run ruff check src/ufm/integrations/qr/__init__.py src/ufm/ui/studio_window.py` — clean; `uv run python -m json.tool src/ufm/ui/studio_strings.json` — JSON valid. Тести і фізичний друк не запускалися.

E05.05 лишається «Частково виконано»: налаштування позиції/полів, реальне приймання принтером етикеток і решта parity E02 не завершені. CSV: 118 рядків; Частково 31, Виконано 29, Заплановано 57, У роботі 1. Дані котушок, принтери, БД, секрети, EXE та HaspelSync не змінювалися. Наступне: доповнити локалізований макет/параметри позиції та пройти UI/фізичне приймання без автоматичного обліку з QR.

## E03.07 checkpoint: правила єдиного writer і cutover — 2026-10-29

В ADR-001 додані чотири per-printer режими `LEGACY_ACTIVE`, `CUTOVER_READY`, `UFM_ACTIVE`, `REVIEW_ONLY`, порядок cutover та rollback. Старий HaspelSync/Spoolman writer вимикається до активації UFM; за невідомого власника обидва автоматичні шляхи мають бути вимкнені. Checklist E03.07 переведено в «Частково виконано»: policy визначена, але shared authority endpoint/міжпроцесного lock немає, E03.06 не завершений, отже runtime-гарантії від паралельного списання ще немає. Статуси CSV: 118 rows; Partial 29 / Done 30 / Planned 58 / In Progress 1. Код не змінювався; ніякі writer-и не вмикалися. Наступний залежний крок: довести E03.06 — межу HaspelSync writer → UFM і її блокування за відсутності активного UFM authority; не вважати документацію enforcement-ом.

## E07.03 checkpoint: окремі прогрес і шари у durable projection — 2026-10-29

`JobMessage` тепер має окремі необов’язкові `current_layer` і `progress_bp`; наявний `completed_layers` залишається незалежним. `JobProjectionCommands` записує перевірені значення у відповідні поля `PrintJob`, а `mapping_history()` відновлює усі три значення з immutable receipt. Додана монотонна перевірка current layer/progress для того самого occurrence та regression tests: рестартне відновлення SQLite і конфлікти при регресії шару/прогресу. Міграції не потрібні: поля `current_layer` та `progress_bp` уже присутні в схемі `print_job`.

Ruff для п’яти змінених Python-файлів: clean. Тести не запускалися. CSV E07.03 лишається «Частково виконано»: runtime receipt/projector bridge не заведений, спостереження без точного provenance для start/end/plate/material channels не трактуються як факти. E07.04 лишається частковим: додано bounded FIFO/overflow, але UI досі використовує display-only latest API, durable consumer і живі reconnect/order приймальні перевірки відсутні. Ніяке списання не активовано. CSV: 118 рядків; Partial 28 / Done 30 / Planned 59 / In Progress 1. Наступна дія: окремий runtime consumer для FIFO batch з DTO normalization, strict exact-run-identity gate і durable receipt ingestion; перевірити всі джерельні ID semantics перед адаптацією.

## E07.04 checkpoint: FIFO для подій монітора — 2026-10-29

Замість одного latest-value слота `PrinterMonitorTask` тепер тримає bounded FIFO до 256 `PrinterEvent` у порядку отримання. Додано `take_pending_events()` для пакетного читання; UI-сумісний `take_latest_event()` лишається лише для відображення snapshot і спорожнює пакет свідомо. `_publish()` сигналізує переповнення через `PrinterEventBufferOverflow`, не витісняючи найстарішу подію. Додано два regression tests: порядок пакета та збереження старої події при overflow.

Ruff для змінених Python-файлів: clean. Тести не запускалися в цьому етапі. Це не під’єднує події до ReceiptIngestion: runtime persistence відсутня; UI досі бере лише останній snapshot, тож ніякого автоматичного списання не активовано. E07.04 лишається частковим до окремого durable consumer, live ordering/reconnect та фізичної acceptance. E07.03 без змін: receipt→projection wiring і provenance plate/time/material facts не доведені. CSV: 118 рядків; Partial 28 / Done 30 / Planned 59 / In Progress 1. Наступне: створити тестований окремий consumer, який приймає весь FIFO batch, записує normalized events у durable receipt queue з exact scope/run identity й не проєктує неоднозначні запуски.

## E07.03/E07.04 checkpoint: live event-ingestion boundary — 2026-10-29

Граф-first аудит зведеної карти підтверджено вихідним кодом: `ReceiptIngestion` і `ProjectionDrain` мають надійне окреме ядро, але пошук викликів під `src` не виявив runtime wiring із `PrinterMonitorTask`. `PrinterMonitorTask.take_latest_event()` навмисно тримає лише останнє повідомлення; під’єднання його як durable ingress непомітно втрачало б проміжні lifecycle/mapping observations. Тому автоматичну проєкцію/списання з цього сигналу не вмикав.

CSV E07.03/E07.04 уточнено: E07.03 зберігає частковий статус, оскільки receipt→projection не під’єднано в runtime та не всі plate/source timestamps/material channel facts доступні з перевіреним provenance. E07.04 зберігає частковий статус через відсутність live ordering/reconnect acceptance і coalescing монітора. Наступна конкретна дія: спроєктувати та покрити тестами окрему bounded FIFO для всіх подій із явним overflow/backpressure, потім адаптер DTO→receipt із точним run identity; невизначену ідентичність залишати на review. Це спостереження не є приймальним тестом фізичного принтера. Код не змінювався, реальні принтери/БД/секрети не торкався.

## E06.05 checkpoint: live AMS slot and sensor details — 2026-10-29

У live-панелі Studio додано окремий список кожного повідомленого feed slot. Для кожного показуються тип feed system, slot key, occupancy (заповнений/порожній/точний стан невідомий) і `remaining_mass`, якщо адаптер передав вимір. `UNKNOWN`, `UNAVAILABLE` та `UNSUPPORTED` відображаються окремо; відсутня маса не стає нулем. Сирі tray UUID, tag UID і secret/ID-коди у цей монітор не виводяться. Температури, progress і layer користуються тим самим Availability mapping; capability panel E06.06 уже окрема.

Доказ: `show_monitored_status`, `monitor_slot_details` та тест `test_studio_monitor_details_render_confirmed_printer_snapshot`. Ordered Python 3.12 suite — **622 passed /485 subtests, exit 0** (повторний прогін після intermittent post-summary Windows Qt access violation); Ruff clean; JSON strings valid. Дані лише тестові.

E06.05 лишається частковим: провайдерський нормалізований live printer-error payload/датчики камери чи інших сенсорів не існують у DTO адаптерів, physical acceptance також не проводилося. Не створював вигадані повідомлення помилок. CSV 118: Частково виконано 28, Виконано 30, Заплановано 59, У роботі 1. Ліміти після повного прогону: залишок 64% primary /46% weekly. Наступне: перевірити E07.03/E07.04 на наявному ingestion pipeline та вибрати недоведений, програмно доступний шматок; не підміняти фізичний acceptance тестовим.

## E06.02 checkpoint: Studio connection edit workflow — 2026-10-29

Додано кнопку редагування LAN-підключення для вибраного Bambu. Вона не активна для Moonraker/OctoPrint, без вибраного рядка або під час поточного monitor/worker. Форма попередньо заповнює адресу й серійний номер, маскує LAN-код та вимагає явного натискання «Перевірити та зберегти». У підказці вказано, що чинний TLS CA/fingerprint зберігається. Далі UI викликає `update_bambu_printer_connection` у фоновому Task; код доступу не виводиться в повідомлення. Backend `StudioPrinter` тепер містить serial для заповнення форми.

Сервіс перед заміною перевіряє candidate connection і статус; при network failure не змінює старі поля/secret, при DB rollback повертає старий секрет під новим ref. Тести трьох шляхів: успішна зміна + failed connection preservation, DB rollback recovery, UI selection/provider gate та password masking. Повний ordered Python 3.12 suite: **622 passed /485 subtests, exit 0**; Ruff clean; `configuration.py` focused mypy clean; JSON strings valid. Обмеження: фізичний Bambu/TLS acceptance не проводився; UI зберігає діючий сертифікат/відбиток, але не має форми для їх заміни. E06.02 лишається частковим до фізичного acceptance та редагування TLS trust policy. У комбінованому focused mypy для `configuration.py` + `studio_backend.py` виявлено один не пов’язаний із цією зміною старий `Missing return statement` у `StudioBackend.create_storage_location` (рядок 522); цільовий `configuration.py` чистий.

Чекліст (118): Частково виконано 28, Виконано 30, Заплановано 59, У роботі 1. Ліміти після етапу: залишок 65% primary /46% weekly. Наступне: переглянути найближчі незавершені checklist залежності; hardware-gated рядки лишити частковими та обрати доступний software крок.

## E06.02 checkpoint: safe Bambu LAN connection replacement service — 2026-10-29

Реалізовано `update_bambu_printer_connection`: до будь-якої зміни збережених даних він створює нового Bambu LAN provider із введеними host/serial/access code, виконує connect і читає статус, використовуючи наявні TLS CA/pin. Тільки після успішної перевірки замінює credential reference та host/serial у транзакції з revision checks. Під час ротації прибирається старий секрет; якщо БД не приймає зміну, старий секрет повертається у SecretStore під новим reference і профіль лишається робочим. Невдала мережна перевірка не торкається старого профілю. Profile ID, сертифікат і його pin зберігаються.

Докази: `src/ufm/integrations/printers/configuration.py`; `test_bambu_connection_edit_tests_before_switch_and_keeps_old_profile_on_failure`; `test_bambu_connection_edit_restores_working_secret_after_database_rollback`. Ordered повний suite Python 3.12: **621 passed /485 subtests, exit 0**; Ruff clean. Тільки тимчасова SQLite БД і тестовий SecretStore.

E06.02 залишається частковим: UI-діалог Studio ще не під’єднано, а фізичне TLS/принтер приймання не проводилося. Статуси чекліста (118): Частково виконано 28, Виконано 30, Заплановано 59, У роботі 1. Ліміти після етапу: залишок 65% primary /46% weekly. Наступна дія: показати кнопку «Змінити підключення» для вибраного Bambu-принтера, з явним підтвердженням і маскованим LAN-кодом; не дозволяти змінювати інший provider через цей шлях.

## E06.07 checkpoint: two-printer identity isolation — 2026-10-29

Додано integration test із двома окремо збереженими Bambu LAN профілями у тимчасовій SQLite базі. Через справжній `configured_printer_provider` для кожного ID отримуються свої host, serial, secret і provider instance ID. На двох provider об’єктах із фікстурами перевірено різні `source_epoch`, ключі AMS систем і UUID котушок; перша подія кожного потоку має відповідний `printer_id`, `provider_instance_id`, epoch і власний progress. Це покриває ізоляцію на рівні профілю/адаптера без мережевого принтера. Studio вже показує багато сконфігурованих рядків і бере ID вибраного рядка у probe; саму таблицю не переписував.

Доказ: `tests/integration/test_bambu_lan_provider.py::test_two_configured_printers_keep_credentials_events_and_slots_isolated`, живий код `configuration.py`, `bambu_lan.py`, Studio UI; ordered повний Python 3.12 suite **619 passed /485 subtests, exit 0**; Ruff та compileall clean. Дані/секрети лише тимчасові тестові, фізичні принтери не підключали.

E06.07 лишається частковим до приймання на кількох реальних пристроях. E06.06 теж лишається частковим до перевірки capability-істинності на реальних моделях. Чекліст: 118 пунктів; Частково виконано 28, Виконано 30, Заплановано 59, У роботі 1. Наступне — пройти таблицю незавершених пунктів за ID та залежностями й продовжити найближчий без апаратної залежності. Ліміти після прогону: залишок 66% primary /46% weekly.

## E06.06 checkpoint: adapter capabilities in Studio — 2026-10-29

У Studio додано панель capability-матриці, яку монітор читає з `PrinterCapabilities` після підключення. Вона показує 15 полів, конкретний тип адаптера (`BAMBU_LAN`, `MOONRAKER`, `OCTOPRINT`) і час останнього спостереження. Значення `KNOWN true/false`, `UNKNOWN`, `UNAVAILABLE` і `UNSUPPORTED` мають окремі локалізовані позначки; з назви моделі можливості не виводяться. Невідомі значення тестуються як unknown, а не перетворюються на «ні».

Перевірки: `test_studio_monitor_capabilities_render_observed_availability` і підтвердження деталей стану — 2 passed; ordered повний suite Python 3.12 — **618 passed /485 subtests, exit 0**; Ruff — clean; `studio_strings.json` валідний JSON. Актуальні графи використані для навігації: `D:/graphify-out/bambu-ufm/PROJECT_MAPS_UK.md`, зведений enriched `graph.json`; графовий BFS вказав на DTO, monitor і Studio, фактичну поведінку підтверджено live-кодом і тестами. Перевірено ліміти після етапу: залишок 67% primary /46% weekly.

E06.06 лишається частковим до звірки статичних capability-відповідей із реальною поведінкою різних моделей принтерів. Жоден фізичний принтер не підключався. E06.05 лишається частковим через нормалізовані повідомлення помилок/датчики та physical acceptance. Чекліст 118 пунктів: Частково виконано 27, Виконано 30, Заплановано 60, У роботі 1, Заблоковано 0, Відкладено 0; UTF-8 BOM збережено. Наступне: E06.07 — перевірити, чи ізольовані події, слоти й облікові дані між кількома налаштованими принтерами, почавши з наявних тестів і композиції провайдерів.

## E06.05 checkpoint: live printer detail panel — 2026-10-29

Постійний монітор тепер бере `PrinterStatusSnapshot` одразу після підключення та після кожної успішної health-перевірки; status handoff має власний latest-value слот із максимум одним непідтвердженим Qt-сигналом. Studio показує підтверджені температури сопла/стола, progress, поточний шар, типи feed system і кількість слотів AMS/зовнішніх систем. Job-події показують локалізований стан, progress і шар. Поля без значення показуються як unknown; невідомі залишки не інтерпретуються як нуль. Помилку можна показати лише за станом FAILED/provider failure: адаптери поки не надають нормалізованого тексту printer error, а capability/sensor matrix належить E06.06.

Перевірки: тест confirmed snapshot UI, monitor subset 8 passed; ordered full Python 3.12 suite **617 passed /485 subtests, exit 0**; Ruff clean. Focused mypy для `printer_monitor.py`, `bambu_lan.py`, `windows_power.py` чистий; у `studio_window.py` лишилися 10 відомих попередніх типових діагностик в інших місцях, як і до цього UI-етапу. E06.05 частково: потрібні normalized live error records та відображення доступних sensors/capabilities з E06.06; фізичний acceptance також відкритий.

CSV: 118 вимог; Частково виконано: 26 / Виконано: 30 / Заплановано: 61 / У роботі: 1. Ліміти після suite: 69% primary /47% weekly. Наступне: E06.06 — перевірити capabilities та UNKNOWN/UNSUPPORTED у кожного адаптера, в UI показувати підтримку функції з джерелом/часом спостереження, а не виводити її з назви моделі.

## E06.04 checkpoint: bounded reconnect and event handoff — 2026-10-29

У `PrinterMonitorTask` додано повторне створення провайдера після retryable `ProviderError` з capped exponential backoff 1–30 с; провайдер від’єднується до паузи. Authentication/TLS та інші non-retryable помилки зупиняють цикл без повторів. Stop скасовує backoff. UFM Studio показує стани connecting/online/offline/retrying. Події з worker coalesce у спільному thread-safe слоті latest-event — Qt отримує максимум одне непідтверджене сповіщення, без накопичення черги.

Перевірки на Python 3.12: Bambu health надсилає get_version/pushall і визнає дані свіжими лише після нового валідного print-report; HTTP health викликає реальний endpoint провайдера. Монітор перевіряє health раз на 15 с, показує stale на деградації й запускає контрольований reconnect. Додано Windows `WindowsResumeDetector`: порівнює GetTickCount64 (включає сон) з QueryUnbiasedInterruptTime (лише awake time); після виявленого sleep gap монітор від’єднується й перепідключається. Тест Studio явно перевіряє, що нове вікно не відновлює доступ до принтера без дозволу; старт після рестарту лишається opt-in. Повний ordered suite: **616 passed /485 subtests, exit 0**; після додавання startup assertion 3 цільові тести passed, Ruff і focused mypy чисті. Докази Windows clock API: Microsoft Learn — GetTickCount64 враховує сон; QueryUnbiasedInterruptTime його виключає. E06.04 лишається частковим до реального Windows sleep/resume і Bambu printer acceptance.

CSV: 118 вимог; Частково виконано: 25 / Виконано: 30 / Заплановано: 62 / У роботі: 1. Ліміти після suite: 71% primary /47% weekly. Наступне: acceptance на реальному Windows sleep/resume та Bambu LAN; вирішити безпечно, чи потрібне відновлення після рестарту, не вмикаючи непідтверджену автопідписку. Жодного реального принтера не підключали.

## E06.02 checkpoint: Studio profile display details can be edited — 2026-10-29

Added a selected-printer edit action for display name/model. `update_printer_details` validates values, requires an enabled printer with a connection profile, and uses an immediate transaction with revision checking; endpoint, serial, certificate pin, secret reference, print identity and history remain untouched. Together with the earlier confirmed remove action, Studio can now edit the display details and remove a configured connection.

Checks: UI test `test_studio_edit_printer_details_preserves_connection_profile`; service test `test_editing_display_details_preserves_host_secret_and_history_identity`; removal UI/service tests. Focused set: 4 passed; full suite remains **604 passed /485 subtests, exit 0**; Ruff clean; three changed integration/UI modules pass focused mypy. E06.02 remains partial: change endpoint/LAN code with a verified reconnect and rollback is not implemented, and physical printer acceptance remains open.

CSV: 118 requirements; Частково виконано: 24 / Виконано: 30 / Заплановано: 63 / У роботі: 1. E06.03 is done. Next: reconnect/backoff and truthful offline/stale state in E06.04; keep live event persistence under E07.

## E06.03 виконано: постійний монітор принтера з керованим закриттям — 2026-10-29

У UFM Studio додано явний Start/Stop для вибраного підключення; при запуску показується попередження про тривале локальне з’єднання та можливу конкуренцію Bambu LAN із Bambu Studio. `PrinterMonitorTask` утримує async MQTT/HTTP stream у власному QThread/event loop. Зупинка скасовує async generator, викликає provider.disconnect і дожидається звільнення executor; закриття головного вікна відкладається до завершення worker. Bambu `disconnect()` будить заблоковане читання звіту, щоб завершення не чекало повний timeout. Події показуються у UI без витоку секретів; live receipt/job persistence не заявляється.

Перевірки на Python 3.12: ordered full suite **604 passed /485 subtests, exit 0**; Ruff clean; mypy для `printer_monitor.py`, `configuration.py`, `bambu_lan.py` з `--follow-imports=silent` — без помилок. Повний mypy команди проєкту окремо показав 24 діагностики в costing/inventory, migration/unit-of-work, studio_backend і старих ділянках Studio; це не помилки в трьох цільових файлах. Перший прогін suite пройшов assertions, але впав на Windows Qt teardown; після явного `deleteLater` монітора повторний ordered suite завершився clean exit 0.

CSV: 118 вимог; Частково виконано: 24 / Виконано: 30 / Заплановано: 63 / У роботі: 1. E06.02 залишається частковим через редагування профілю та acceptance. Наступне: безпечне редагування підключення із перевіркою нового endpoint/секрету перед заміною старої конфігурації; після нього продовжити E06.04 reconnect/stale/sleep-resume.


## E06.02 checkpoint: видалення підключення з UFM Studio — 2026-10-29

Додано кнопку «Видалити підключення» для вибраного принтера. Без вибраного рядка дія недоступна; перед видаленням потрібне явне підтвердження. UI викликає `remove_configured_printer`, який прибирає connection і секрет із системного сховища, вимикає запис принтера та зберігає історичні посилання. Нові рядки повідомлень додані українською й англійською.

Перевірки: `test_studio_remove_printer_requires_selection_and_confirmation` та `test_removing_printer_deletes_connection_and_secret_but_preserves_record` — 2 passed; Ruff clean. E06.02 залишається частковим: редагування існуючого профілю/секрету у Studio та фізична acceptance перевірка ще не виконані.

CSV: 118 вимог; Частково виконано: 24 / Виконано: 29 / Заплановано: 64 / У роботі: 1. Наступна дія в тому самому кроці — визначити і реалізувати безпечний потік редагування з повторною перевіркою підключення й атомарним оновленням секрету; фізичну перевірку не вважати виконаною тестовими фікстурами.

## E06.01 виконано: мережеве автозаповнення й локальний профіль — 2026-10-29

Перевірені ручне введення Bambu IP, мережеве визначення ідентичності, імпорт профілю Bambu Studio, явна довіра до сертифіката, відсутність запису коду до підтвердження/успішного підключення та вибір налаштованого принтера у списку перед читанням стану. Знайдено кілька налаштованих принтерів підтримується таблицею Studio; конкретна ціль probe береться з активного рядка. Для кількох автоматично знайдених Bambu адрес користувач вводить IP у формі; неоднозначний пошук без IP відхиляється без випадкового вибору. Незалежність обліку/слотів кількох принтерів лишається окремим критерієм E06.07.

Докази: `src/ufm/ui/studio_window.py` (`enroll_bambu`, `enroll_bambu_network`, `probe`, `refresh`), `src/ufm/infrastructure/studio_backend.py` (`printers`), `src/ufm/integrations/printers/bambu_studio.py` (`import_bambu_studio_profile`); тести `test_bambu_network_autofill.py`, `test_bambu_studio_import.py`, `test_printer_discovery.py` і три відповідні Studio UI тести. Перевірки: 25 passed + 9 subtests; Ruff clean. Повної збірки або підключення нового принтера не виконувалося.

CSV: 118 вимог; Частково виконано: 24 / Виконано: 29 / Заплановано: 64 / У роботі: 1. Наступний крок за планом — E06.02: пройти майстер підключення від моделі/serial і LAN-коду до довіри TLS, перевірки, сховища секретів та редагування/видалення профілю.

## E05.08 виконано: матриця станів Studio inventory — 2026-10-29

Перевірено всі 18 дій з `docs/UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv`: normal, empty/no-selection, error та unavailable там, де ці стани застосовні. Додано negative UI coverage для створення/редагування матеріалів і брендів, архівації бренду та котушки; empty catalog add-spool показує підказку без запису; assignment location OSError не змінює котушку/ledger; column settings OSError не змінює вигляд; history read failures чистять застарілий текст і показують лише тип помилки. Action registry statuses точно розрізняють `Перевірено` та `Частково виконано`; усі 18 тепер Перевірено. Legacy web UI для цих inventory actions не потрібен.

Перевірки: focused catalog states 11 passed, focused add-spool state passed, registry contract passed; `uv run ruff check src tests` clean; останній ordered full suite (Studio module first, далі інші test files без повторного збору) — **600 passed /485 subtests, exit 0**. Попередні повтори іноді проходили всі assertions, але мали intermittent Windows Qt teardown access violation після summary; останній повний прогін завершився чисто.

CSV: 118 вимог + header; Виконано 28 / Частково 24 / У роботі 1 / Заплановано 65. Ліміти на початку етапу: 81% primary /48% weekly. Наступний залежний крок — продовжити E05 решту пов’язаних UI та інтеграційних вимог за checklist; перед роботою повторно перевірити ліміти.

## E05.04 checkpoint: повний suite із чистим Qt teardown — 2026-10-29

В `qt_application` fixture додано явне закриття вікон, обробку відкладеного видалення Qt-об’єктів і вивільнення QApplication після тестів. Це прибрало повторюваний Windows access violation після summary: повний `uv run python -X faulthandler -m pytest -q` завершив **565 passed /477 subtests, exit 0**; `uv run ruff check src tests` — чисто. Попередні повні прогони перед зміною цього fixture друкували ті самі passed counts, але падали під час teardown.

E05.04 лишається «У роботі»: ручний gross/tare/net capture, explicit Yes/No reconciliation, evidence history, source/time/cutoff, reservations/revision/idempotency уже є; SCALE command поки перевіряє лише наявність sensor/calibration FK, але не enabled sensor, matching calibration version і expiry. Ліміти після етапу: 71% primary /52% weekly. CSV 118 рядків/BOM: 26 виконано /25 частково /1 у роботі /66 заплановано.

Наступна дія: додати read-only calibration/sensor repository ports і перевірений запис `WeightReading`, який відхиляє unstable/unknown reading, вимкнений/чужий sensor, відсутню/непоточну/прострочену calibration до створення SCALE evidence. Hardware serial adapter не вигадувати без протоколу конкретної ваги.

## Checkpoint: порядок тестів не усуває Qt teardown crash — 2026-10-29

Явний запуск Studio module першим, потім решти файлів у тому самому pytest процесі, знову завершив **565 passed /477 subtests**, після чого відтворив access violation без Python frame. Перевірено також окремо: 24 Studio tests exit 0; інші 541 tests exit 0. Наступна вузька діагностика — явно завершувати QApplication в session fixture після закриття всіх вікон і прокачування DeferredDelete, без змін runtime продукту. Ліміти: 71% primary /52% weekly.

## Checkpoint: звужено Qt shutdown access violation — 2026-10-29

Повтор повного набору двічі дав **565 passed /477 subtests**, а потім Windows access violation без Python frame. Для локалізації: Studio-модуль окремо — **24 passed, exit 0**; весь набір без `tests/integration/test_studio_window.py` — **541 passed /477 subtests, exit 0**; Ruff clean. Це вказує на interaction/порядок teardown лише при спільному запуску Qt UI тестів із рештою suite, а не на assertion failure. Точний тригер не встановлено; E05.04 не позначаю завершеним до повторної перевірки інтеграції UI/test runner.

Ліміти: 71% primary /52% weekly. Наступний діагностичний крок — один повний запуск із явним порядком: спершу Studio module, потім усі інші тести без повторного збору цього модуля; за успіху вказати порядок у команді повного тестування, не змінюючи runtime продукту.

## E05.04 checkpoint: read-only history та повний suite — 2026-10-29

Studio тепер читає до 100 останніх measurement evidence для вибраної котушки й показує source, captured time, gross/tare/net, ledger cutoff і прийнято/не прийнято. Перевірено manual Yes/No. Перевірки: focused inventory+Studio **65 passed /31 subtests**, Studio module **24 passed, exit 0**, Ruff clean. Повний набір показав **565 passed /477 subtests**, але Windows-процес у цьому запуску впав з Qt access violation після pytest summary (`faulthandler`: no Python frame); потрібен повтор для визначення відтворюваності.

Ліміти перед повторним повним запуском: 72% primary /52% weekly. E05.04 «У роботі»: ручний зважувальний і підтверджувальний шлях є; реальний ScaleProvider/перевірка калібрування і hardware acceptance залишаються. CSV 118 рядків/BOM: 26 виконано /25 частково /1 у роботі /66 заплановано. Наступне: повторити suite з faulthandler; якщо Qt exit crash повториться, ізолювати тестовий модуль.

## E05.04 checkpoint: історія вимірювань у картці котушки — 2026-10-29

Додано `EvidenceRepository.inventory_for_spool` із обмеженням 100 останніх вимірів та `InventoryCommands.measurement_history`, що повертає evidence разом зі станом прийняття звіряння. Studio показує захоплений час, джерело MANUAL/SCALE, gross/tare/net, ledger cutoff та «лише доказ» або прийнятий залишок. У параметризованому UI-тесті No лишає залишок без змін, Yes коригує ledger, а обидва стани видно в історії.

Цільові command/UI перевірки: **65 passed /31 subtests**; Ruff clean. E05.04 залишається «У роботі»: ручний end-to-end шлях готовий, ScaleProvider не під’єднаний; необхідна перевірка calibration/sensor version і придатності/expiry перед прийняттям SCALE evidence, плюс hardware acceptance. CSV 118 рядків/BOM: 26 виконано /25 частково /1 у роботі /66 заплановано. Ліміти до повного прогону: 72% primary /52% weekly.

Наступна дія: повний pytest + Ruff. Після цього — аудит відповідності одиниць/калібрування інтерфейсу ScaleProvider і визначення безпечного тестового адаптера; не приймати raw scale evidence без валідації calibration record.

## E05.04 checkpoint: reservation guards і виміри без ledger delta — 2026-10-29

Додано інтеграційні сценарії: вимір 700 мг не приймається, якщо активний резерв становить 800 мг (залишок і ledger незмінні); точна нульова дельта оновлює measured evidence/reconciliation без zero ledger event; виміряна порожня котушка приймається як початковий баланс 0 мг через INITIAL_STOCK. Цільові тести InventoryCommands + Studio: **65 passed /31 subtests**, Ruff clean.

E05.04 лишається «У роботі»: потрібні перелік/перегляд evidence у Studio та інтеграція реального ScaleProvider із перевіркою калібрування. Ліміти після етапу: 73% primary /52% weekly. CSV 118 рядків/BOM: 26 виконано /25 частково /1 у роботі /66 заплановано. Наступна дія — read-only історія вимірів, щоб користувач міг побачити збережені й прийняті свідчення після закриття діалогу.

## E05.04 checkpoint: зважування зі явним підтвердженням звіряння — 2026-10-29

Після immutable measurement capture додано `accept_inventory_measurement`: у транзакції перевіряє source MANUAL/SCALE, revision, evidence scope, точний `ledger_cutoff`, цілісність projection/history та активні reservations; додає `InventoryReconciliation`, за ненульової дельти — linked ledger entry, і оновлює `measured_remaining`, effective/estimated projection. Невідома котушка може бути встановлена як opening stock через accepted measurement; для відомої нульова дельта не породжує заборонену zero ledger entry. Дублікат того самого evidence відхиляється, replay тієї самої команди ідемпотентний.

Studio дозволяє ввести gross і масу порожньої котушки; net рахується точно. Перед застосуванням показує поточний запас і delta. No є default: evidence зберігається, залишок незмінний. Лише явне Yes запускає acceptance. Інтерфейс працює через application commands/backend; direct SQL для зміни обліку немає. Реалізовано валідацію calibration IDs для SCALE та їхніх FK, але реальний scale provider, перевірка строку calibration і перелік попередніх вимірів залишаються.

Цільові докази: InventoryCommands + Studio: **63 passed /31 subtests**; Ruff clean. CSV 118 рядків/BOM: 26 виконано /25 частково /1 у роботі /66 заплановано. Ліміти перед повним прогоном: 73% primary /52% weekly.

Наступні дії в E05.04: тест на measured remainder нижче активного reservation; тест reconciliation zero-delta та виміряного opening; read model/історія measurement evidence; інтеграція ScaleProvider з доступною перевіркою calibration status/expiry. Повний набір тестів ще має бути запущений після цих змін.

## E05.04 checkpoint: запис immutable evidence виміру — 2026-10-29

Додано `InventoryCommands.record_inventory_measurement` і `EvidenceRepository.get_inventory`. Команда приймає net та optional gross/tare, джерело, час виміру/отримання, sensor/calibration, stability, stable duration; в межах одного UoW зберігає immutable `InventoryEvidence` з `ledger_cutoff` та audit request fingerprint. Повтор із тим самим ключем і payload повертає ту саму evidence; інший payload — `IdempotencyConflict`; capture timestamp після отримання відхиляється. Evidence capture навмисно не змінює `Spool.measured_remaining`, effective/estimated stock або ledger.

Докази: `test_record_inventory_measurement_is_immutable_idempotent_and_stock_neutral`; `test_record_inventory_measurement_rejects_future_capture_time`; 37 inventory command tests +31 subtests; Ruff clean. CSV 118 рядків/BOM: 26 виконано /25 частково /1 у роботі /66 заплановано. Ліміти: 75% primary /53% weekly.

E05.04 лишається «У роботі»: треба під’єднати capture до локального backend/UI, показувати provenance, відокремити явне підтвердження відхилення/прийняття виміру та реалізувати ledger-linked reconciliation з revision, ledger cutoff і reservation guard. Наступна дія — додати read model і UI capture/review; не записувати stock до явного підтвердження.

## E05.04 у роботі: аудит зважування та звіряння — 2026-10-29

Перевірено карту UFM та live source. Уже наявні `InventoryEvidence` і `InventoryReconciliation`, доменний контроль `gross - tare = net`, `Spool.measured_remaining`, immutable SQLite-таблиці/репозиторії та `ScaleProvider.read/tare`. Їхні поточні перевірки здебільшого доменні/схемні. У `InventoryCommands` поки немає end-to-end use case, що зберігає фізичний вимір із provenance, а UI не має окремого потоку «виміряти → переглянути дельту → явно підтвердити звіряння». Тому наявність таблиць не є завершенням E05.04.

Зафіксовано в CSV як «У роботі». Наступна конкретна дія: розробити транзакційний application command для запису evidence і окремого явного прийняття звіряння з revision/idempotency; перевірити reserved stock, ledger cutoff, нульову дельту та повторний запит. Потім додати Studio UI/тести, що не допускають зміни залишку до підтвердження. Аудитний етап не змінював код обліку. Ліміти після етапу: 76% primary /53% weekly.

## E05.08 checkpoint: помилковий і недоступний стани інвентарю — 2026-10-29

`StudioWindow.refresh()` тепер обробляє недоступність локальних джерел без аварійного завершення: очищує застарілі таблиці/картки й історію, показує локалізовану підказку без тексту винятку та вимикає операції інвентарю до успішного повторного читання. Після відновлення доступу таблиця і дії повертаються. Додано перевірку відмови та успіху для початкового залишку: неправильна маса не змінює облік, правильні 125 г створюють початкову історичну операцію. Реєстр має 17 дій; `opening` і `refresh` тепер позначені перевіреними.

Докази: `test_inventory_empty_normal_unavailable_and_error_states`; повний набір **557 passed / 477 subtests in 75.14s**; `uv run ruff check src tests` — чисто. Основні ліміти перед наступним етапом: 76% primary / 53% weekly. CSV 118 рядків/BOM: 26 виконано / 25 частково / 67 заплановано. Жодні реальні бази, HaspelSync чи встановлена збірка не змінювалися.

E05.08 лишається частковим: потрібна пер-action перевірка error/unavailable станів для решти зареєстрованих дій. Наступна дія — звірити решту дій реєстру з контрактами/guards і додавати сценарії відмов та недоступності залежно від доступних контрольованих fixtures; не позначати весь крок завершеним лише за наявності загального error dialog.

## E05.02 завершено: форми виробника, профілю та котушки — 2026-10-29

Закрито всі підтверджені schema-backed поля створення/редагування Brand, FilamentProfile і Spool. Brand підтримує create/rename/soft archive зі збереженням історичних FK. FilamentProfile має матеріал, бренд, product line, діаметр/щільність, прапорці, subtype, температурні діапазони, max volumetric speed, drying temp/duration, default color і notes. Spool має бренд, партію/лот, кольори/HEX, image URI/notes, номінальну й порожню масу, дати відкриття/виробництва/придатності. Команди з revision/audit/idempotency та доменною валідацією; зміни метаданих не змінюють ефективний залишок або журнал.

Не включали поля власних наступних етапів: виміряне зважування/звірка — E05.04, purchase price/currency/історія вартості — E05.06, ledger balance — лише InventoryCommands. Дати last-used трактуються як подія/історія, а не довільне редаговане поле.

Докази: profile/brand/spool create/edit/soft-archive/date tests; full suite **556 passed/477 subtests in 74.69s**; Ruff clean. CSV 118 рядків/BOM; 26 виконано /25 частково /67 заплановано. Ліміти 77% primary /53% weekly.

Наступна дія: E05.08 — доповнити матрицю normal/empty/error/unavailable станів за 17 зареєстрованими Studio діями і коректно позначити залишкові прогалини.

## Checkpoint: створення котушки з метаданими — 2026-10-29

E05.02 продовжено: форма нової котушки приймає Brand, product line, batch/lot, nominal filament та empty spool mass, колір/HEX, image URI і notes. Для профілю задаються початкові значення brand/product line/default color. Поля збережені через `InventoryCommands.create_spool`, перевіряються доменом; effective stock лишається невідомим, ledger не створюється без окремої операції початкового залишку.

Доказ: `test_studio_creates_spool_with_metadata_without_opening_stock`; full suite **555 passed/477 subtests in 75.31s**; Ruff clean. CSV 118 рядків/BOM; 26 виконано /25 частково /67 заплановано. Ліміти 78% primary /53% weekly.

E05.02 лишається частковим до джерельної звірки дат/усіх підтверджених полів spool create/edit. Ціни/закупівлі — E05.06, measurement/calibration — E05.04. E05.08 лишається частковим до повного error/unavailable coverage для кожної зареєстрованої дії. Наступна дія: зіставити поля першоджерела з E05.02/E05.04/E05.06 контрактами і вносити лише підтверджені поля без дублювання ledger.

## Checkpoint: повні поля профілю та збереження архівних зв’язків — 2026-10-29

У E05.02 додано schema-backed FilamentProfile поля: subtype; nozzle/bed/chamber min/max; max volumetric speed; drying temp/duration; default color та notes. `ExactDecimal` і домен перевіряють невід’ємні температури, послідовність діапазону, додатну швидкість і невід’ємну тривалість. Studio показує їх у прокручуваній формі; create/edit ідуть через CatalogCommands/revision/audit.

Brand rename/soft archive перевірені. Зв’язки профілю/котушки не видаляються; форма зберігає disabled archived-brand selection, а команди дозволяють лишити той самий архівний FK, не призначаючи його новим сутностям. Котушка редагує свій виробник, номінальну/порожню масу та descriptive metadata через InventoryCommands; ефективний залишок і журнал незмінні.

Перевірки: focused 6 passed; full suite **554 passed/477 subtests in 74.22s**; Ruff clean. CSV 118 рядків/BOM; 26 виконано /25 частково /67 заплановано. Ліміти 79% primary /53% weekly.

E05.02 лишається частковим до перенесення metadata у створення нової котушки. Вартість/валюта/закупівля належать E05.06, зважування — E05.04. E05.08 лишається частковим до розподіленого state/error coverage. Наступна дія: додати до створення котушки Brand, nominal/empty mass і базові descriptive поля з профілю як початкові значення, без ledger stock write.

## Checkpoint: керування виробниками у Studio — 2026-10-29

E05.02: додано редагування назви Brand та підтверджене м’яке архівування через `CatalogCommands`; фізичне видалення не виконується. Archived brand більше не пропонується для нових зв’язків, але назва й FK-зв’язки профілю/котушки збережені. Revision, audit і command replay guards застосовуються в application layer. E05.08 action registry розширено до 17 дій, включно з потоками матеріалу/виробника.

Доказ: `test_studio_can_rename_and_archive_brand_without_losing_profile_links`; повний suite **554 passed/477 subtests in 75.29s**; Ruff чистий. CSV 118 рядків/BOM; 26 виконано /25 частково /67 заплановано. Ліміти після тестів 81% primary /54% weekly.

Ще E05.02: profile nozzle/bed/chamber ranges, max volumetric speed, drying temperature/duration, subtype/default color/notes — перевірено, що схема має поля, але треба додати доменну валідацію та керований UI. E05.08 лишається частковим: error/unavailable evidence потрібне для кожного перенесеного workflow. Наступна дія — розширити domain/profile command із точними ExactDecimal правилами, потім форму без прямого SQL.

## Checkpoint: метадані виробника та маси пакування котушки — 2026-10-29

Продовжив E05.02. Редагування котушки у Studio тепер включає окремий Brand, номінальну масу філаменту та масу порожньої котушки разом із раніше доданими product line, batch/lot, кольорами, URI зображення й notes. Brand перевіряється в тій самій UoW; маси парсяться через `Mass.from_grams`; всі зміни проходять `InventoryCommands.edit_spool` з очікуваною revision, audit та idempotency fingerprint. Залишок і журнал залишаються незмінними.

Перевірки: цільові Studio/backend 5 passed; повний suite **553 passed/477 subtests in 73.85s**; Ruff чистий. CSV 118 рядків/BOM; 26 виконано /25 частково /67 заплановано. Ліміти після suite: 82% primary /54% weekly.

Ще E05.02: звірити підтримку температур/сушіння/volumetric speed/notes профілю та редагування/архівацію Brand. E05.08 має реєстр 12 дій і базове покриття чотирьох UI-станів, але потрібне покриття відмов/недоступності для решти workflows. Наступна дія: звірити профільні поля з графом, схемою й classic UI; не додавати поля без джерельного контракту.

## Checkpoint: реєстр дій інвентарю та UI-стани — 2026-10-29

E05.08 частково виконано: створений `docs/UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv` із 12 діями/контролами, handler-ами, normal/empty/unavailable/error guard-ами й посиланнями на докази. Новий інтеграційний тест перевіряє порожній інвентар, звичайно вибрану котушку, блокування списання при невідомому залишку й безпечний діалог помилки. Повний suite **553 passed/477 subtests in 73.87s**; Ruff чистий. CSV: 118 рядків/BOM; статуси переобчислені автоматично. Ліміти після suite: 82% primary /54% weekly.

E05.02 лишився частковим: ще треба підтверджено підтримані brand/purchase та profile thermal/drying/speed полями; не редагувати залишок напряму. E05.08 ще не закритий: розширити state coverage на решту зареєстрованих workflows і звірити кожну дію з контрактом. Наступна дія: перевірити поля виробника/котушки у domain, classic UI та action contracts перед наступним малим блоком змін.

## Checkpoint: descriptive spool metadata edit — 2026-10-29

E05.02 remains partial. Studio spool editing now includes product line, batch/lot numbers, color name and validated HEX values, image URI, and notes. Writes flow through revision-checked `InventoryCommands.edit_spool`, fingerprint/idempotency, audit, and domain validation. The workflow intentionally excludes effective/estimated/measured stock, ledger sequence, nominal/empty mass, and purchase accounting fields; current edits leave stock and transaction history unchanged.

Evidence: `test_studio_edits_and_archives_spool_through_application_commands`; focused Studio/backend 5 passed; full suite **552 passed/477 subtests in 74.36s**; Ruff clean. CSV 118 rows/BOM, 25 complete/25 partial/68 planned. Limits after suite: 83% primary /54% weekly. No live database, HaspelSync, or installed build changed.

Remaining E05.02: spool brand and purchase metadata; profile thermal/drying/speed/notes; Brand edit/archive; verify which are supported by domain/schema and add through commands. Next E05.08: button registry and normal/empty/error/unavailable state coverage.

## Checkpoint: форми виробника й розширеного профілю матеріалу — 2026-10-29

Продовжив E05.02. Додав у Studio створення виробника (Brand) і створення/редагування матеріального профілю з підтриманими доменом атрибутами: назва, виробник, product line, тип/назва custom-матеріалу, діаметр, density та прапорці abrasive/flexible/hygroscopic/soluble/filled. Таблиця показує бренд, діаметр і density. Редагування попереджає про вплив профілю на всі пов’язані котушки.

Архітектура: додані `BrandRepository`/`FilamentProfileRepository` у порти та SQLite UoW; profile loader нормалізує null legacy-boolean до false. `CatalogCommands` створює бренд, створює/редагує профіль із idempotency hash, audit і revision guard; profile brand перевіряється через UoW. StudioBackend тепер проходить ці application commands, не створює профіль прямим SQL. UI зміна метаданих не змінює ledger чи залишок.

Перевірки: Studio/backend 22 passed; повний suite **552 passed/477 subtests in 73.11s**; Ruff clean. Mypy 4 існуючі діагностики в SQLite migration/UoW (`migrate.py`, `unit_of_work.py`); новий catalog/storage/UI/backend код без помилок. CSV: 118 рядків/BOM, 25 виконано /25 частково /68 заплановано. Ліміти після suite 83% 5h /54% week. Не змінені реальна база, HaspelSync чи встановлена збірка.

Ще E05.02: edit/archive виробника, профільні температури/сушіння/volumetric speed/notes, метадані котушки (brand/product/batch/color/nominal/empty/purchase), а також їхні guard-и/перевірки. Наступна дія — додати доступні підтверджені metadata котушки з явним поділом на ledger-запаси й описові поля; не редагувати залишок поза InventoryCommands.
## Checkpoint: inventory command workflows та редагування котушки — 2026-10-29

У Studio доповнив редагування котушки формою назви й порога малого залишку. Порожній поріг знімає правило сповіщення; число проходить через `Mass.from_grams`, а застосування — через `InventoryCommands.edit_spool` із revision/audit. Перевірка підтверджує, що зміна метаданих не додає ledger запис і не змінює залишок. Разом із попередніми перейменуванням/архівацією/rebuild/compensation E05.03 тепер закрито: усі чотири класи workflow є у Studio, небезпечні дії мають окреме підтвердження й викликають application commands.

E05.02 переведено у часткове виконання: є створення матеріалу/котушки і редагування назви/порога котушки, але ще не перенесено редагування виробника, повний набір полів профілю та інші spool metadata.

Перевірки: Qt/settings/location: 56 passed/35 subtests; повний suite **551 passed/477 subtests in 74.77s**; Ruff clean. Mypy: 4 diagnostics у незмінених `sqlite/migrate.py` та `sqlite/unit_of_work.py`; 123 модулі перевірено, новий application/storage, backend і Studio файли без помилок. CSV: 118 рядків/BOM, 25 виконано /25 частково /68 заплановано. Ліміти до checkpoint 85% 5h /54% week. Реальні бази, HaspelSync, EXE не змінювалися.

Наступна дія за залежностями: E05.02 — порівняти створення/редагування в `Brand`, `FilamentProfile`, `Spool` із наявними application commands та UI у класичній оболонці; додавати лише підтверджені поля з domain validation, revision і audit. Потім добрати E05.08 normal/empty/error/unavailable-state coverage та перевірку button registry.
## Checkpoint: локації котушок і завершення E05.01 — 2026-10-29

Завершив критерії E05.01: Studio має синхронні таблицю/картки, пошук, сортування, комбіновані фільтри, постійний вибір колонок, безпечні swatches, колір/локацію та архівований стан. Додано top-level storage location workflow: створення місця і призначення/зняття місця з активної котушки. Для цього додано `StorageLocationRepository` у application port/SQLite UoW і `StorageCommands`; зміна location використовує revision/audit та не змінює stock/ledger. Для однакових назв у списку показується короткий ID, щоб вибір був однозначним. E05.01 позначено виконаним.

E05.03 має rename/archive/rebuild/compensation UI, але лишається частковим: форма редагування котушки наразі змінює лише назву й зберігає попередній поріг; розширене редагування інших підтверджених полів потрібно завершити у E05.02/E05.03.

Перевірки: Studio/settings/location focused tests 37 passed/20 subtests, Ruff clean; повний suite **551 passed/477 subtests in 74.37s** до останньої зміни відображення короткого ID, після неї focused suite знову пройшов (37/20) і Ruff clean. Mypy: 4 діагностики тільки у SQLite `migrate.py`/`unit_of_work.py`; нові `storage.py`, UI і backend без помилок. CSV: 118 IDs, BOM, статуси 24 виконано /25 частково /69 заплановано. Ліміти після full suite: 86% 5h /54% week. Не змінювалися робочі бази, HaspelSync, інсталяція або EXE.

Наступна дія: перевірити E05.02 — розширені форми редагування профілю/котушки й інші вже підтримані поля; перед UI зміною дослідити `FilamentProfile`/`Spool` use cases та вирішити, які додаткові application commands потрібні для повноцінного редагування. Storage tree parent/edit workflow залишається окремим розширенням.
## Checkpoint: перебудова projection зі Studio — 2026-10-29

У E05.03 додано дію «Перебудувати облік». Після явного підтвердження Studio викликає `InventoryCommands.rebuild_projection` із показаною revision. Application command перевіряє актуальність revision, забороняє архівні котушки, валідовує історію і в транзакції синхронізує тільки projection та audit. Ledger-транзакції не редагуються. Кнопки редагування/архіву/перебудови read-only для архіву; компенсація лишається окремим явним шляхом.

Перевірки: Qt/settings 36 passed/20 subtests; повний suite **550 passed/477 subtests in 74.54s**; Ruff clean. Mypy повідомляє чотири помилки тільки в незмінених SQLite `migrate.py`/`unit_of_work.py`. CSV 118 рядків з BOM, E05.03 частковий; рахунок 23/26/69. Ліміти після набору 87% 5h /55% week. HaspelSync, production SQLite та встановлену збірку не змінювали.

Наступна дія: перевірити створення/редагування storage location. Граф і live source показують `StorageLocation`, але в `application/ports/persistence.py` немає репозиторію locations, у UnitOfWork — відповідного порту, і в Application не виявлено location commands. Тому UI для присвоєння/переміщення котушок поки не можна робити напряму через SQL; наступний крок — спроєктувати повний use case/domain поля та тестові інваріанти або перейти до іншого наявного завершуваного пункту.
## Checkpoint: компенсація руху філаменту зі Studio — 2026-10-29

Продовжив E05.03. У Studio додано дію компенсації: користувач обирає некомпенсовану ненульову операцію з історії та явно підтверджує дію. Викликається наявний `InventoryCommands.compensate`, який додає протилежний ledger entry з reference до первинної транзакції та audit; історію не видаляє. Уже компенсовані операції відфільтровано. Архівовані котушки залишаються без цієї дії. Додатково E05.03 уже містить перейменування та архівацію через application commands. Потрібні ще UI для rebuild projection та точне визначення інших compensation flows.

Перевірки: Qt/settings 35 passed/20 subtests; повний набір **549 passed/477 subtests in 73.19s**; Ruff clean. Mypy має 4 діагностики у незмінених SQLite migrate/UoW файлах, нові UI/backend файли чисті. CSV: 118 рядків BOM; 23 виконано /26 частково /69 заплановано. Ліміти до checkpoint: 88% 5h /55% week. Живі бази, HaspelSync та EXE не змінювалися.

Наступна конкретна дія: оцінити rebuild projection як окрему явно підтверджувану адміністративну дію; перед реалізацією звірити обмеження `rebuild_projection` й доступність першопричин у UI. Потім перевірити storage-location модель: зараз `StorageLocation` є, але без application repository/commands керування ним з UI неможливе без окремої розробки контрольованого use case.
## Checkpoint: редагування та архівація котушок у Studio — 2026-10-29

Продовжив E05.03, спершу використав Graphify карту `ufm-map` (вузли `InventoryCommands.edit_spool`, `InventoryCommands.archive_spool`, `StorageLocation`) і підтвердив точні сигнатури/запобіжники у вихідному коді. Studio отримала «Змінити назву котушки» і «Архівувати котушку». Backend передає поточну revision у наявні application commands; вони ведуть audit/idempotency і відхиляють архівацію з активним mount, reservation чи unresolved usage. Архівація вимагає явного підтвердження, не редагує ledger/залишок; далі картка залишається видимою, але дії вимкнені. E05.03 тепер частково виконано; rebuild/compensation і решта flows лишаються.

Перевірки: Studio/settings 34 passed/20 subtests; повний suite **548 passed/477 subtests in 73.06s**; Ruff clean. Mypy 4 попередні помилки в SQLite `migrate.py`/`unit_of_work.py`, змінені UI/backend файли без діагностик. Ліміти після suite: 88% 5h /55% week. CSV: 118 кроків, BOM; статуси 23 виконано /26 частково /69 заплановано. Реальні бази, HaspelSync та встановлений EXE не змінювалися.

Наступна дія: дослідити Application/API workflow storage location і точний scope rebuild/compensation; додавати форми лише коли UI передає revision, має явне підтвердження де потрібне та поважає блокування архіву/резервів.
## Checkpoint: постійний вибір колонок інвентарю — 2026-10-29

Продовжив E05.01. Видимі колонки тепер зберігаються в `config/settings.json` атомарно разом з іншими налаштуваннями. Додано закритий `Literal`-перелік допустимих колонок; невідомі поля у конфігурації відхиляються. Назва котушки обов’язкова, ідентичність залишається видимою; картковий режим не залежить від таблиці. Налаштування відновлюється після повторного створення вікна Studio.

Перевірки: Qt/settings 33 passed/20 subtests; повний набір **547 passed/477 subtests in 72.46s**; Ruff clean. Mypy: 4 помилки у незмінених `infrastructure/persistence/sqlite/migrate.py` та `unit_of_work.py`; змінені файли Settings/Studio UI чисті. Ліміти після перевірки: 89% за 5 годин /55% за тиждень. CSV: 118 кроків, BOM збережено, E05.01 лишається частковим. Робочі бази, HaspelSync та EXE не змінювалися.

Наступний крок: перейти до E05.02/E05.03 і зіставити наявні команди редагування котушки/архівації зі шляхом у Studio; додавати форму лише для команд, що підтримують повну перевірку та audit, без прямого SQL-запису залишків.
## Checkpoint: вибір колонок інвентарю — 2026-10-29

За планом E05.01 додано кнопку «Колонки…» та двомовний модальний діалог. Користувач може приховувати/показувати решту полів таблиці; стовпець назви котушки обов’язковий і не вимикається, щоб ідентичність для вибору та облікових дій залишалася очевидною. Налаштування діє тільки на таблицю, не змінює картки, а перемикання подань не скидає приховані колонки. Перевага поки живе протягом сесії, не зберігається після перезапуску.

Перевірено: новий інтеграційний сценарій вибору колонок, обов’язкової назви та table→cards→table; Qt/settings 33 passed/19 subtests; повний suite **547 passed/476 subtests in 73.31s**; Ruff clean. Mypy запущено з desktop extras: 4 помилки у незмінених `sqlite/migrate.py` та `sqlite/unit_of_work.py`, жодної у зміненому `studio_window.py`. Під час першого запуску середовище не мало PySide6; наступні команди виконані з `--extra desktop --extra dev`. Ліміти до/після етапу: 90% первинний /55% тижневий. CSV: 118 рядків, BOM збережено; E05.01 лишився частковим. Дані користувача, HaspelSync та встановлену збірку не змінювали.

Наступна конкретна дія: продовжити наступний доступний пункт залежностей E05 — workflow керування місцем/архівацією через application commands або найближчий крок, який не дублює вже реалізоване. Окремо вирішити атомарне збереження вибраних колонок у validated settings до позначення цієї вимоги завершеною.
## Checkpoint: перемикання таблиця/картки котушок — 2026-10-29

У Studio додано карткове подання котушок і перемикач виду. Обидва представлення містять ту саму identity та filter metadata; зміна виду переносить поточний spool ID, деталі/історію залишаються прив’язаними до нього. Пошук і фільтри синхронно приховують записи в обох view; кольоровий swatch і короткі дані доступні на картках. Цей етап лише читає дані, жодних stock/ledger змін.

Verification: тест перемикання table→cards→table із вибраною котушкою; Qt/settings suite 32 passed/19 subtests; full suite **546 passed/476 subtests in 66.87s**, Ruff clean, mypy 122 файли clean. CSV BOM збережено, 118 IDs; 23 complete/25 partial/70 planned. E05.01 і E05.07 залишаються partial. Ліміти після suite: 90% 5h/55% week. Живі БД, HaspelSync, встановлений EXE не чіпали.

Наступне: E05.01 — додати діалог вибору видимих колонок таблиці, не впливаючи на картковий режим; перевірити повторне відкриття/перемикання, ширину вікна та персистентність налаштування тільки якщо воно атомарно зберігається.


## Checkpoint: колірні swatches і стани порожнього інвентарю — 2026-10-29

У продовження E05.01 додано swatch тільки для суворо перевіреного `#RRGGBB`; foreground обирається за яскравістю, довільний текст/invalid HEX не стає стилем. Додано помітні повідомлення для порожнього інвентарю та для фільтра без збігів. Комбіновані матеріал/залишок/стан/місце фільтри, сортування й пошук залишаються зв’язані з ідентичністю рядка. Архівовані котушки не можна вибрати після фільтра й списати через приховану дію.

Перевірки: `tests/integration/test_studio_window.py` та settings tests: 32 passed/19 subtests; Ruff clean; mypy 122 файли clean; full suite **546 passed /476 subtests in 67.69s**. CSV — 118 рядків із BOM, 23 виконано/25 частково/70 заплановано. E05.01 ще частковий: потрібні картки/вибір колонок/керування місцем та інші workflows. Ліміти: 91% 5h/55% week. Дані користувача та HaspelSync не змінені; EXE не перебудовувався.

Наступна дія: картковий режим котушок, зберігаючи той самий selected spool ID та фільтри між таблицею/картками; потім тест перемикання виду під час активного вибору.


## Checkpoint: розширений перелік котушок у Studio — 2026-10-29

Продовжив E05.01. Graphify навігація вказала на `spool`/`storage_location`; джерельна перевірка схеми підтвердила `color_name`, `color_hex`, `storage_location_id`, `lifecycle`. `StudioBackend.spools()` тепер читає ці поля, місце підтягує необов’язковим LEFT JOIN. У Qt таблиці видно колір і місце; пошук охоплює їх. Додані фільтри за життєвим станом NEW/OPEN/ARCHIVED та місцем поверх попередніх фільтрів матеріалу/залишку. Архів лишається видимим, але відомі inventory actions лишаються вимкненими; жодного списання/редагування у цьому етапі не додано. Рядкова identity лишається пов’язаною з item data після сортування, а фільтр знімає вибір, якщо рядок приховано.

Докази: Qt/settings tests 32 passed/19 subtests; повний suite **546 passed /476 subtests in 68.16s**; Ruff clean; mypy `src/ufm`: 122 файли clean. CSV: 118 IDs; 23 повністю виконано /25 частково /70 заплановано. E05.01/E05.07 partial. Ліміти після повного тестування: 92% 5h /55% week. Не редагувалися реальні дані та HaspelSync; EXE не збирали.

Наступне: E05.01 — картковий/табличний перемикач або вибір колонок, кольоровий swatch з перевіреним hex і контрольованою палітрою, порожні/архівні стани. Потім окремо UI workflows для редагування/локацій за наявними application commands; не писати напряму у stock/ledger.


## Checkpoint: фільтри та безпечний вибір котушок у Studio — 2026-10-29

Продовжив E05.01 після використання Graphify UFM карти й перевірки живої таблиці. Додав матеріальний фільтр і фільтр відомого/невідомого залишку. Разом із пошуком за назвою/профілем/матеріалом і сортуванням діє єдиний view state. Ідентичність запису збережена у Qt UserRole; при приховуванні вибраного рядка вибір скидається та ручні кнопки вимикаються, тож операція не може непомітно перейти на іншу котушку. Логіка не змінює інвентар або ledger.

Verification: Qt/settings tests 30 passed/19 subtests; Ruff clean; mypy `src/ufm`: 122 files clean; повний suite **544 passed /476 subtests in 68.17s**. CSV зберігає BOM і 118 рядків; статуси: 23 виконано /25 частково /70 заплановано. E05.01, E05.07 залишаються частковими. Ліміти після suite: 93% п’ятигодинного /56% тижневого залишку. Ніякі real-data БД, HaspelSync або installed EXE не змінювалися.

Наступне продовження: E05.01 — розширити інвентарний огляд (колір/місце/картки/архів) після перевірки фактичних DTO й entity джерел, або вибрати найближчий залежний пункт плану; не позначати крок виконаним, доки всі перелічені вимоги й стани не перевірені.


## Checkpoint: Studio settings persistence і безпечне сортування котушок — 2026-10-29

За Graphify UFM картою простежено `AppSettings`/Studio UI та inventory table → selection; live source перевірено перед редагуванням. Studio тепер читає `config/settings.json`; явний `--locale` має пріоритет. Перемикач light/dark зберігає тему атомарно через тимчасовий файл і `os.replace`; помилка збереження не змінює тему активного вікна. Для котушок увімкнено сортування; маса сортується як ціле число mg, ID та текст пошуку (назва/профіль/матеріал) прив’язані до рядка, тому selection/history/actions не плутають котушки після сортування.

Докази: unit + Qt integration: 29 passed /19 subtests; Ruff clean; mypy `src/ufm`: 122 files clean; повний suite **543 passed /476 subtests in 64.67s**; ізольований offscreen запуск Studio exit 0, saved `en-US` застосовано та зроблено screenshot у тимчасовому каталозі. CSV: 118 ID; статуси 23 виконано / 25 частково / 70 заплановано. E05.01 та E05.07 — частково; для E05.01 бракує карток, кольорів/локацій/архіву, фільтрів і вибору колонок; E05.07 ще потребує native locale/log settings UI.

Ліміти після повного набору: 94% п’ятигодинного /56% тижневого залишку; додаткові кредити не використовувалися. Користувацькі дані й HaspelSync не зачеплені; EXE не перебудовувався.

Наступна дія за планом: продовжити E05.01 — додати фільтр за матеріалом і наявністю залишку на базі view state, не змінюючи облікових даних; залишити архівовані/невідомі стани видимими, якщо їх не фільтрує користувач.


## Checkpoint: UFM Studio завантажує локальні налаштування — 2026-10-29

Graphify UFM карту використано для простеження `AppSettings` → CLI → `StudioWindow`; live-код підтвердив, що `ufm-studio` завжди передавав `uk-UA` за замовчуванням і `run()` формував новий `AppSettings` замість читання user config. Виправлено: `--locale` тепер необов’язковий override; Studio читає `config/settings.json`, а явний параметр командного рядка має пріоритет. Пошкоджений/невідомий config завершує старт без мовчазного скидання налаштувань. E05.07 позначено частково: нативного UI редагування мови/теми й журналів ще немає.

Перевірки: `tests/unit/test_foundation.py` + `tests/integration/test_studio_window.py`: 26 passed /19 subtests; Ruff `src tests` clean; mypy `src/ufm`: 122 файли clean; ізольований `ufm-studio --capture`: exit 0, зчитано saved English locale, створено тестову SQLite та screenshot у тимчасовому каталозі. Перевірка лімітів: 95% п’ятигодинного /56% тижневого доступно; запас кредитів не використовувався. Дані користувача не зачіпалися.

Наступний доступний крок: повернутись до E09.07 — native review UI для вже реалізованого no-write estimate. Перед UI інтеграцією визначити/зібрати відсутній runtime composition для Haspel worker у standalone EXE; не показувати фальшиву дію, не фіналізувати без явного підтвердження та залишити списання за Bambu вимкненим до усунення E11 evidence gates.


## Checkpoint: read-only estimated-usage review — 2026-10-29

The user was right that a hardware evidence blocker for Bambu accounting should not have stopped unrelated planned work. Continued with the accessible E09.07 review step. Graphify UFM map located `CalculatedFinalizationCommands`, and live source/test review confirmed `finalize()` is an opt-in writer while the desktop currently has no calculated-usage review UI.

Added `CalculatedFinalizationCommands.preview()`: it binds a no-write calculation to a terminal job, pending terminal receipt, occurrence key, plate and verified 3MF SHA-256; it returns an explicit “Розрахункова витрата” label, per-logical-material milligrams, partial/range information and whether automatic policy is enabled. It works with automatic estimated usage disabled. It validates the worker proposal before returning and does not create finalization, audit, evidence, ledger, reservation or stock records. SQLite snapshot equality is asserted in the new test.

Checks: calculated-finalization suite 7 passed /2 subtests; Bambu provider suite 21 passed /15 subtests; Ruff `src tests` clean; mypy `src/ufm` clean (122 files); full suite **539 passed /476 subtests in 65.65s**. Latest limits: 96% primary /56% weekly remaining. CSV: 118 IDs, 23 complete /23 partial /72 planned. E09.07 is partial: the Qt review/confirmation UI and persisted, user-controlled automatic-policy setting are still absent. No installed EXE rebuild or live accounting change.

Next: add a native review surface and safe persisted policy controls around this no-write preview, retaining explicit confirmation before any estimate is finalized. Continue E10 partial-print/accounting work only where its source evidence and invariants permit; Bambu auto-segmentation/debit remains gated on cross-epoch identity and physical slot/mount/RFID evidence.

---

## Checkpoint: keep Studio send mapping separate from active-job mapping — 2026-10-29

Graphify enriched map navigated to HaspelSync `notePrintCommand()`, `decodeStudioMapping()` and their tests; source review confirms `ams_mapping`/`ams_mapping2` are read from the echoed Studio `project_file` command, held as a pending mapping and associated with a later job by its name. HaspelSync also prefers a current `print.mapping` report. Therefore the raw fields observed in UFM’s merged LAN report are not enough by themselves to establish that their mapping belongs to the active print occurrence. Their encoding semantics in HaspelSync are not proof of UFM-side job association.

Kept `ams_mapping` and `ams_mapping2` as separate validated metadata in `PrintJobSnapshot` and in the `PrinterEvent` digest; they do not populate logical material→slot mappings. Fixed `material_slot_mappings_from_report()` to accept both the full `{print: ...}` envelope and the flattened print object actually passed by `_print_report()`. It decodes only explicit current `print.mapping`; send-time AMS echo remains raw until UFM can correlate the command safely with the active job.

Checks: Bambu provider tests 21 passed /15 subtests; Ruff `src tests` clean; mypy `src/ufm` clean (122 files); full `.venv312` suite **538 passed /476 subtests in 66.68s**. Latest limits: 97% primary /56% weekly remaining. CSV: 118 IDs, 23 complete /22 partial /73 planned. E11.03 remains partial. No receipt, material usage segment, refill, stock/ledger action, HaspelSync edit, live printer operation, package rebuild, or EXE update.

Next: correlate `project_file` send echoes with a verified current job identity (including reconnect/restart and same-file reprint); then verify physical refill boundary and exact slot→active mount→RFID join. Until then leave AMS echo metadata unjoined and automatic accounting disabled.

---

## Latest checkpoint - preserve Bambu AMS mapping reports - 2026-10-29

Fixed the saved mypy issue in the Bambu raw mapping parser by casting AMS and
slot values after strict runtime validation. The provider keeps ams_mapping and
ams_mapping2 as distinct optional report tuples and hashes changes into
PrinterEvent. These vendor reports remain evidence only; they are not converted
into logical-material slot mappings, spool assignments, refill events, or
accounting.

Verification: Bambu provider tests 19 passed /15 subtests; Ruff src/tests
clean; mypy 122 source files clean; full suite 536 passed /476 subtests in
64.23s. Latest limit snapshot after full suite: 99% primary /57% weekly. E11.03
remains partial. Next examine HaspelSync/Bambu source contracts for the two raw
AMS fields; without a validated conversion contract, preserve them separately.
The physical trace still lacks reconnect/restart and same-file reprint evidence,
so occurrence-to-receipt projection and debit remain disabled.

---

## Checkpoint - preserve observed AMS report variants - 2026-10-29

Used the enriched Graphify map to locate material_slot_mappings_from_report;
source review confirms only print.mapping is currently decoded into
material_slot_mappings. The completed physical test instead observed
ams_mapping=[0,-1,-1,3] and ams_mapping2 entries, once before printing.
Implemented separate optional provider_ams_mapping and provider_ams_mapping2
fields in PrintJobSnapshot; Bambu adapter validates and preserves these reports
and includes changes in the PrinterEvent digest. It deliberately does not infer
logical-material-to-slot joins from them or treat them as refill events.

Targeted Bambu provider suite: 19 passed /15 subtests. Ruff src/tests clean.
Mypy currently reports one error at bambu_lan.py:141: int(ams_id)/int(slot_id)
arguments are Any|None despite preceding runtime checks. The code fix is small,
but the primary limit reached the 15% stop threshold, so no more source work
was started. Exact resume: import cast from typing, append
(cast(int, ams_id), cast(int, slot_id)), rerun Ruff/mypy and targeted provider
tests; run full suite only when limits allow. Latest limits: 15% primary /57%
weekly remaining. E11.03 stays partial; no receipt, inventory, or ledger write.

---

## Latest physical evidence checkpoint - 2026-10-29

Read-only review of D:/3D_Druk/UFM_Print_Test/captures/20261029T024215Z/:
the correlation report records 561 verified encrypted/raw-chain packets,
QoS 0 throughout, no payload parse errors, and state transitions IDLE ->
PREPARE -> RUNNING -> FINISH. End state: 100%, 50/50 layers, print_error=0;
max and last observed layer are 50. In the sanitized events, HMAC aliases for
task_id and subtask_id are present and unchanged from PREPARE through RUNNING
and FINISH in this one print. Raw IDs remain unrecorded. This establishes
single-run continuity only; the trace does not contain a reconnect, process
restart, or same-file reprint.

Before printing, one report observed print.ams_mapping=[0,-1,-1,3] and
print.ams_mapping2=[slot 0, slot 3 with unused 255 entries]; these fields were
observed once and cannot be equated with print.mapping or interpreted as refill.
The captured sliced file UFM_CUBE_10mm_PREPARED.gcode.3mf (SHA-256
67f155d7eadf80212602e5191f1b979efec8ada9e319d0ea24b396b39e127a61) reports
slicer estimates 1.37 g (filament id 1) + 0.51 g (id 4) = 1.88 g, not measured
consumption. No ledger/stock operation was performed. QoS 0 and the recorder
limitations mean this is only the received LAN packet sequence, not proof that
all internal printer events were delivered.

The enriched graph was queried first; it surfaced the receipt epoch-scope test
and PrinterEvent/JobMessage nodes. Direct source/test review confirms receipt
deduplication uses provider+printer+source_epoch+event_key and adapter epochs
are regenerated with uuid4() on construction. Therefore a single successful
print does not yet prove restart/reprint correlation. E11.03 remains partial.

Next: obtain/verify a second same-file print and a process restart/reconnect
trace, compare only salted task/subtask aliases and epoch semantics. Keep IDs
as metadata; no event-to-receipt converter or debit until idempotent occurrence
identity survives those boundaries. Latest limit check at this checkpoint: 16% primary /57% weekly remaining. Full suite remains 534 passed /472 subtests;
Ruff and mypy (122 files) clean.

---

## Latest implementation checkpoint: preserve Bambu report IDs — 2026-10-29

Added optional provider_task_id, provider_subtask_id and provider_job_id fields
to PrintJobSnapshot. The Bambu LAN adapter preserves these report values after
strict validation and includes changes in PrinterEvent payload digest. They
remain raw metadata only: not provider_run_key, not occurrence_key, and not a
receipt/debit trigger. This records what the printer reports without guessing
run identity. Tests cover valid values, blanks, zero, invalid shapes, and
event digest changes. Full suite: 534 passed /472 subtests; Ruff clean; mypy
122 source files clean. No installed EXE rebuild. E11.03 remains partial.

Latest limit snapshot after the full suite: 70% primary /65% weekly remaining.
Additional source review: BambuLanAdapter creates source_epoch from uuid4()
at bambu_lan.py:332; ReceiptIngestion scopes idempotency by provider, printer,
source_epoch and event_key. An app restart therefore creates a new receipt
scope even if the same print is still running. No consecutive LAN traces exist
in checked-in fixtures to prove identity across that boundary. This blocks a
safe event-to-receipt bridge. Required evidence: raw start, reconnect/restart,
and same-file reprint reports from a local printer, with task/job IDs preserved
and timestamps; otherwise keep provider ID fields as metadata only.

Next: acquire that trace evidence, then decide fail-closed correlation rules.
Do not create receipts for jobs without a verified occurrence contract.

---

## Latest checkpoint: Bambu LAN task identity investigation — 2026-10-29

Limits before this documentation update: 76% primary / 66% weekly remaining.
Evidence reviewed read-only: Bambu Studio local callback uses
MachineObject::parse_json("lan", msg) at
D:/GIT/BambuStudio/src/slic3r/GUI/GUI_App.cpp:2345; DeviceManager.cpp reads
task_id at line 3219 and subtask_id at 3243. HaspelSync fixtures show active
local P2S (task_id=6456, subtask_id empty, job_id=0), active local H2D
(task_id=9012, subtask_id empty, job_id=0), and idle P1S (both IDs empty).
Thus task_id is an optional candidate, not a verified occurrence key:
uniqueness across reprints, process restart, and reconnect remains unknown.
The event-to-receipt bridge is still absent. No source code or HaspelSync files
were changed. E11.03 remains partial; prior full suite 532 passed/468
subtests, Ruff clean, mypy 122 source files clean.

Next action: obtain consecutive raw LAN reports over start, reconnect, and
same-file reprint; verify identifier stability and source_epoch behavior,
including printers with empty IDs. Then build a fail-closed event-to-receipt
converter only for a proven identity contract. Do not debit inventory or
update the installed EXE before that.

---

# Поточний прогрес UFM Studio

## Найновіший етап: Bambu layer contract і межа інтеграції — 2026-10-29

Для спільної навігації використовувати доповнену карту
`D:/graphify-out/bambu-ufm/enriched/graphify-out/graph.json`;
покриття/обмеження — `D:/graphify-out/bambu-ufm/ENRICHMENT_UK.md`. Ребра карти
є статичними доказами зв’язків, а не runtime-перевіркою.

Bambu `PrintJobSnapshot` тепер має окремі `current_layer` та `completed_layers`.
Adapter зберігає `layer_num` як current layer і рахує завершену кількість як
`max(0, floor(layer_num) - 1)`, відповідно до
`D:/Filament_Manager/localization/haspelsync/src/gcode.js`:
`completedLayerIndex()` визначає, що на шарі N завершено N−1 шарів; для 0/1
не завершено жодного. Обидва поля включені в digest `PrinterEvent`, тож їхня
зміна створює нове спостереження. HaspelSync читався без змін.

Межа: у коді поки не знайдено мосту `PrinterEvent` → `JobMessage` → durable
receipt. Нові layer-поля поки не входять у `mapping_history()`; для безпечного
з’єднання потрібен перевірений provider run/occurrence ID. Не виводити його з
назви файлу чи завдання.

Перевірки: `.venv312` повний набір — 532 passed /468 subtests; Ruff src/tests
чистий; mypy 122 source files clean. Ліміти на checkpoint: 77% п’ятигодинного
і 66% тижневого залишку. E11.03 лишається частковим.

Наступний крок: збагаченою картою та першоджерелами перевірити, який Bambu
LAN/MQTT task/subtask identifier доступний локально під час друку, і чи може
`PrinterEvent` безпечно створити `JobMessage`; потім додати converter/receipt
bridge із fail-closed правилами для відсутнього/зміненого occurrence key. До
цього не створювати debit, не припускати фізичний момент refill за poll time
і не оновлювати installed EXE.

## Продовження після побудови графів Bambu — 2026-10-29

Карти доступні в `D:/graphify-out/bambu-ufm/`: локальні профілі, сфокусований
репозиторій Bambu Studio та об’єднаний граф. Точне покриття, джерела й
застереження — у [handoff карт](D:/graphify-out/bambu-ufm/HANDOFF_UK.md),
також закріпленому в `AGENTS.md`. Граф використовувався для навігації; UFM
адаптер і першоджерела перевірені окремо.

`JobProjectionCommands.mapping_history()` тепер реконструює кожне прийняте
спостереження з незмінного receipt та його незмінного application marker:
logical-material→provider-slot mapping, receipt/job scope і request hash,
sequence, observed/received time, стан друку та completed layer. Історія
відсортована за source sequence, не дублює receipt-payload і не робить
матеріальних чи облікових записів. Нова подія з регресією sequence або
суперечністю її часу, повтор sequence зі зміненими фактами, регресія шару й
mapping-зміна після terminal переводять подію в конфлікт; застаріле
старше спостереження не стає новою точкою історії.

Перевірки: `.venv312` повний набір — 530 passed / 464 subtests; Ruff src/tests
чистий; mypy — 122 source files без помилок. CSV: 118 IDs/BOM,
23 виконано /22 частково /73 заплановано; E11.03 лишається частковим.
Остання перевірка перед зупинкою: залишок п’ятигодинного/тижневого ліміту
13% / 68%; етап закрито й подальшу розробку зупинено до відновлення порога.

Наступний крок: за цією історією визначати тільки доказані межі provider
mapping change, з’єднати кожну сторону межі з точним збереженим FeedSlot,
active mount і підтвердженою RFID котушкою, а потім проєктувати окрему
ідемпотентну генерацію usage-сегментів. Потрібні фізичні/HaspelSync fixtures
для часу refill і визначення, чи completed layer точно локалізує межу. До
цього не створювати automatic debit, live writer або нову версію installed EXE.

Оновлено: 2026-10-29.

Автоматичне продовження: автоматизацію `ufm` активовано й налаштовано на
перевірку щогодини в цій задачі. Працювати, коли обидва основні ліміти
перевищують 15%; при 15% або менше зберегти точку й завершити запуск.
Останній знімок лімітів: залишок 77% / 66% (перевірено 2026-10-29);
після відновлення лімітів продовжено наступний доступний крок.
Додаткові платні кредити — 0. Перед наступним етапом потрібна свіжа перевірка.
Купівлю кредитів або використання скидань не налаштовано.
Після кожного етапу перевіряти ліміти та продовжувати в цьому самому запуску,
якщо обидва залишки понад 15%; не завершувати лише через готовність одного етапу.

## Джерела стану

- Повний план: [17 частин, 118 кроків](INTEGRATION_STEP_BY_STEP_UK.md).
- Статуси та докази кожного кроку: [CSV-чекліст](INTEGRATION_CHECKLIST_UK.csv).
- Технічні точки продовження: [журнал](DEVELOPMENT_HANDOFF.md).
- Постійне правило оновлення: [AGENTS.md](../AGENTS.md).
- Карти джерел Bambu Studio та межі їхньої достовірності:
  `D:/graphify-out/bambu-ufm/HANDOFF_UK.md`.

## Уже реалізовано за попередніми контрольними точками

- Нативний Qt-інтерфейс, автономний EXE, піктограма та ярлик Windows.
- Котушки й профілі, ручний облік, історія, резервна копія та імпорт Spoolman.
- Адаптери читання стану принтерів, мережеве автозаповнення Bambu.
- Однокотушкове атомарне ядро фіналізації з перевірками та захистом від повторів.
- Збережено детальний план інтеграції та чекліст; установлено постійне
  правило відмічати виконане, незавершене й точку продовження кожної сесії.

Ці можливості не закривають автоматично всі вимоги відповідних етапів.

## Облік нового плану

118 кроків: `Заплановано` — 73; `У роботі` — 0;
`Частково виконано` — 22; `Виконано` — 23; `Заблоковано` — 0; `Відкладено` — 0.

Прийняті E01.02–E01.06: узгоджені копії двох баз, копія встановленої
програми, маніфест і перевірка відновлення, захищений backup runtime HaspelSync.
E01.01 частковий.
Докази й обмеження: [INTEGRATION_BASELINE_UK.md](INTEGRATION_BASELINE_UK.md).
Закрито 22/118 кроків (18,6% пунктів); це не відсоток готовності програми.
Захищений знімок 9 приватних файлів відновлений і перевірений у пам’яті,
зіпсований DPAPI-файл відхилений. Копія прив’язана до профілю Windows;
переносний парольний експорт ще не реалізований.
Докази: [PRIVATE_HASPELSYNC_BACKUP_UK.md](PRIVATE_HASPELSYNC_BACKUP_UK.md).

E02.01/02 прийняті як статичні каталоги; E02.04 — B01–B24 фонових сценаріїв;
E02.08 — опис 25 еталонних сценаріїв і D1–D6, не їх виконання.
E02.03/05/06 часткові. [Каталог інтерфейсів](LEGACY_UI_CATALOG_UK.md):
28 груп Spoolman, 21 HaspelSync, 9 автоматичних сценаріїв; цільові місця Qt.
Відтворюваний лексичний реєстр: 95 файлів, 777 кандидатів controls/clicks,
усі потребують semantic review; вони не є 777 готовими функціями.
Підтверджений local-only accounting, 27 ключів settings. Стандартні Refine
кнопки перевірені на exact package 6.0.3 із SHA512 за lockfile.
58 Spoolman registrations і 54 HaspelSync endpoints перелічені в
BACKGROUND_AND_API_INVENTORY_UK.md; installed consumers ще не підтверджені.
SPOOLMAN_ACTION_CONTRACTS_UK.csv доповнений до 318 рядків SA001–SA318;
HASPELSYNC_ACTION_CONTRACTS_UK.csv має 211 рядків; AC-H01–05 виправлені
у 23 рядках, root виправив SA098/119. E02.03 лишається частковим до
повного candidate disposition/semantic coverage, не через вже виправлені findings.
FEATURE_PARITY_MAPPING_UK.csv зіставляє всі 124 F-вимоги з доказами/діями/Qt:
46 зберегти, 45 покращити, 33 нові; E02.07 прийнятий.

E03.01–E03.05 прийняті як архітектура, spike й контракт. ADR-001 обирає
Python orchestration + bundled вузький Node calculation worker; джерело
обліку — тільки UFM ledger. На 11 XML fixtures — 51 перевірка spike успішна.
Worker protocol v1 реалізований і тестований; він ще не підключений до live
transport, parser intake, receipt worker або автоматичного списування.

Доданий bounded one-shot CalculationWorkerTransport: scope correlation,
санітизований env, межі stdio, timeout/kill/cancellation; 8 tests/5 subtests.
Canonical source-tree Node entrypoint і Python adapter тепер з’єднані:
4 tests / 6 subtests, exact full mg та per-material range partial без
неявного global fallback. Live receipts/EXE ще не підключені, E03.06 частковий.
Verified sliced-3MF intake: E08.03 done, E08.01/02/05/06/07 partial;
докази [VERIFIED_SLICE_INTAKE_UK.md](VERIFIED_SLICE_INTAKE_UK.md).

## Ще не завершено

- Повний підтверджений паритет Spoolman, HaspelSync і власних доповнень.
- Постійний worker приймання подій і відновлення після перезапуску.
- Перевірений парсер 3MF/G-code та автосписування з позначкою
  «Розрахункова витрата».
- Часткові друки, атомарний розподіл між котушками й AMS.
- Повне керування принтером та перевірка розповсюдження на чистій Windows.

## Перевірки й установлені артефакти

Остання повна перевірка коду: 484 тести і 452 підперевірки, exit 0.
Ruff src/tests і mypy усіх 117 source files успішні.
Targeted: protocol 11/20, transport 8/5, 3MF intake 14/66; новий canonical
adapter 4/6, Qt history 5 tests. Після нових domain provenance/read ports
регресії старого ядра й контрактів: 43 tests / 112 subtests; mypy 106 files.
Calculated batch ядро пройшло 24 tests / 4 subtests: full/partial/zero,
дві котушки, repeated spool, reservations, replay, audit rollback та async race.
E09.02/05/06 прийняті; subprocess crash до/після commit, два потоки,
кілька logical materials, чужий резерв і пізнє зважування перевірені.
E07.01 прийнятий: durable ReceiptIngestion, 9 tests / 15 subtests; E07.04
частковий: persistent conflict routing готовий, lifecycle reducer ще потрібний.
Відкритий receipt conflict блокує новий debit в actual і calculated ядрах.
E08.04 частковий: strict offline Marlin-linear G-code preflight, 7 tests /
24 subtests, незалежний review. Поки лише Decimal mm за tool/layer,
без маси/evidence/live accounting. Усі 3 реальні Bambu fixtures відхилені
через gcode.command_unsupported після підтримки bounded metadata comments;
.runtime/gcode-compatibility-20261027.json. E03.08 частковий: THIRD_PARTY_NOTICES
тепер фіксує executable GPL engine reuse і дві MIT dependency metadata;
власна ліцензія, повний transitive inventory та release review ще потрібні.
Раніше новий скрипт
резервування пройшов Ruff, фактичний знімок/відновлення успішні,
9 тестів міграцій та backup пройшли поза пісочницею на етапі резервування.
Установлена програма — попередня збірка з мережевим автозаповненням:
`D:/UFM Studio/UFM Studio.exe`. Автоматичне списування в ній не готове.

## Найближча дія

Оновлено 2026-10-28: після durable provider-slot snapshot projection повний
suite — 508 тестів і 458 підперевірок; Ruff `src tests scripts` і mypy119
source files успішні. Wheel acceptance SHA256
`717be383a08770d51af5a17d1c5d5fbebc5208f941666b2c2f83160795cccfc6`; деталі в
WORKER_WHEEL_ACCEPTANCE_UK.md. Cross-receipt run quarantine E07.06 прийнятий;
Job projection/revision0002 та E08.06 прийняті;
див. JOB_LIFECYCLE_PROJECTION_UK.md і VERIFIED_SLICE_ARTIFACTS_UK.md.
Run blocker до створення alias, повторна перевірка стану receipt під writer
lock, справжнє паралельне apply/quarantine interleaving, ручне resolution з
audit, обидва financial kernels і replay після FINALIZED перевірені. Докази:
13 drain tests та PROJECTION_DRAIN_UK.md і
QUARANTINE_SCOPE_NEXT_UK.md. Реальні бази й installed EXE не змінювалися.

На межі `PrintJobSnapshot` exact start вимагає явного provenance
`printer_reported`/`provider_reported`; Bambu LAN та HTTP адаптери лишають його
NULL. Поточний lifecycle v1 часу start/end не зберігає.

Це DTO safety boundary; durable `JobMessage v1` та міграція не змінені, час
досі не записується як фізичний start. Додано read-only UoW port для точного
пошуку spool identifier за namespace/kind/value з обов’язковими
verified/current/not-deleted фільтрами та `resolve_feed_slot_spool`: точні
`tray_uuid`/`tag_uid` ідентифікатори дають MATCHED лише коли ведуть до однієї
котушки, інакше UNKNOWN/CONFLICT. Resolver не створює mount, reservation,
evidence чи ledger entry; колір/тип не використовуються для висновку.
SQLite acceptance:35 tests/31 subtests; resolver:4 tests; повний suite
508/458, Ruff clean, mypy119 clean. Offline wheel smoke:134 entries/14 module
origins, revision0002, queue/parser artifacts/Decimal успішні; SHA256
`717be383a08770d51af5a17d1c5d5fbebc5208f941666b2c2f83160795cccfc6`, report
`.runtime/wheel-acceptance-20261028-slot-snapshot-projection/report.json`. Node
runtime не bundled. `SpoolIdentifierCommands.verify` вимагає явне підтвердження,
не пише raw identifier у відкритий audit payload, блокує перепризначення та
підтримує ідемпотентний повтор. Кнопка читання стану показує
MATCHED/UNKNOWN/CONFLICT для точних Bambu tray/tag IDs і назву лише підтвердженої
котушки без UUID у UI та змін ledger. UI enrollment дозволяє вибрати прочитаний
slot/tag і котушку, показує ID у фінальному confirm dialog, після схвалення
викликає audited command. Окрема дія монтує лише точний MATCHED slot/spool після
другого підтвердження; FeedSystem/FeedSlot IDs стабільні, system kind/key
зберігаються, tool index не виводиться з фізичного номера AMS. Snapshot старше
120 секунд блокує enrollment і mount. Топологія та audit змінюються, stock і
ledger — ні. Для вже відомого provider slot durable projection зберігає лише
observed/received time та source epoch/sequence. Повтор є duplicate, змінений
payload під тим самим ключем — conflict, стара sequence/timestamp — stale;
новий epoch приймається лише з новішим received time. Audit має hash snapshot,
а не сирі ID чи значення. Невідомі slots автоматично не створюються.
E11.02 частковий: фізичне RFID acceptance та logical material/tool
binding ще не підключені. E11.03 частковий: часові
`MaterialUsageSegment` уже є, але provider/layer/AMS rollover acceptance
відсутні. Наступна дія — перевірити logical material/tool→slot mapping на
multi-material fixtures; mapping має бути explicit/verified і не виводитися з
порядку AMS або кольору.
Для live MQTT/reconnect і hardware acceptance E07.04/05 лишаються частковими.
JobMessage v1 має лише observation time:
physical start/end лишаються NULL. Не вмикати live списування до контракту,
provider acceptance й окремої release перевірки.
JobMessage v1 має лише час спостереження: physical start/end лишаються NULL,
тому live завершення ще не може саме провести витрату. Розширення контракту
має явно зберігати provenance, completed-layer COUNT та версію без припущень.
Початкові рішення: JOB_LIFECYCLE_NEXT_CONTRACT_UK.md; прийнята реалізація:
JOB_LIFECYCLE_PROJECTION_UK.md. Terminal projection не позначає receipt списаним.
Для E08.04 додати dialect-specific compatibility на 3 Bambu fixtures,
зберігаючи межі складності та відмову невідомих команд; без прямого mm→debit.
Поточне ядро default-disabled, live UI/worker його не викликають.
Докази: CALCULATED_BATCH_KERNEL_UK.md і VERIFIED_SLICE_ARTIFACTS_UK.md.
Перед оновленням installed EXE потрібні owner/cutover, bundled Node/engine,
pre-migration backup/restore та clean-Windows acceptance. Не змінювати
реальну базу старого EXE під час source tests.
Прототип experiments/calculate.mjs не плутати з canonical source entrypoint.
E02.03/06 потребують повного coverage ledger, E02.05 installed consumers
ще не підтверджені. Не повторювати вже завершений source audit.
Не вмикати live списування до цих перевірок; EXE лишається preview.
Читати LEGACY_UI_CATALOG_UK.md та source manifest, не повторювати весь аудит.
E01.01 потребує підтвердження фактичного legacy runtime; Docker engine
наразі недоступний. Не запускати його лише заради аудиту.
Далі вести роботи за залежностями плану. Source-level однокотушкове списування
за перевіреним cached файлом уже перевірене; наступна межа — його надійний
live lifecycle та кероване ввімкнення в нативному UI.

Не повторювати виконані роботи без потреби; не вважати попередні успіхи
доказом перевірки нових змін. Зберігати реальні дані й власний HaspelSync.

## Поточна точка продовження — 2026-10-28

Після durable provider-slot observation projection повний suite — 508 тестів і
458 підперевірок; Ruff `src tests scripts` clean, mypy119 clean. Offline wheel
smoke:134 entries/14 module imports; SHA256
`717be383a08770d51af5a17d1c5d5fbebc5208f941666b2c2f83160795cccfc6`.
E06.02 частковий: add/probe/remove + TLS and secret reference verified; in-place
profile edit і hardware acceptance лишились. Read-only identity resolver для
підтверджених tray/tag IDs є; E11.02 partial. `PrintJobMaterial` плюс
`MaterialUsageSegment` уже задають логічний канал→tool→slot→mount→spool з
часовими межами, які перевіряє finalization; нового сегментного ядра не
додавати. CSV:23 done/21 partial/74 planned/0 in progress,118 unique IDs/BOM.
Залишок Codex на останній перевірці:29%/73%.

Наступна конкретна дія: durable job-level збереження та звірка explicit
printer mapping з файлами 3MF і persisted FeedSlot; залишити logical material,
tool/extruder, physical slot і spool окремими поняттями. Не виводити мапу з
кольору/позиції, не вмикати automatic assignment/debit; installed EXE не
змінювати.

## Пряме зіставлення матеріалу Bambu з provider slot — 2026-10-28

Додано окремий `ProviderMaterialSlotMapping` у read-only `PrintJobSnapshot`.
Лише `print.mapping`, явно отриманий від принтера, створює mapping: зберігається
logical filament index окремо від майбутніх tool/extruder індексів і точний
provider system/slot key. Маркер `0xFFFF` позначає невикористаний матеріал;
невідомі, некоректні або непідтримані коди отримують `unsupported`, а відсутній
масив не генерує припущень. Тут ще немає персистенції, зіставлення зі snapshot
наявних слотів чи 3MF-файлом, `MaterialUsageSegment`, mount або списання.

Докази: `tests/integration/test_bambu_lan_provider.py` — 13 tests/3 subtests;
повний suite 510/461; Ruff clean; mypy119 clean. Wheel acceptance у
`.runtime/wheel-acceptance-20261028-printer-logical-slot`:134 entries,16
імпортованих модулів, printer mapping decoder smoke успішний; SHA256
`40a358c035fba822f8e3c32384d83f015bb94cee6aa1d4795625720732fd1436`. Node engine
не bundled. E11.01 тепер частково виконаний: source/provider mapping
відокремлено, але `PrintJobMaterial` і durable lifecycle ще не зберігають
логічний індекс незалежно від tool index.

## Окремий durable logical filament index — 2026-10-28

`PrintJobMaterial.logical_material_index` відокремлений від `tool_index` і
`extruder_index`; SQLite schema `0003_logical_material_index` додає nullable
індекс 0–255 із DB check constraint, щоб старі записи лишалися читабельними.
Domain перевіряє діапазон. Міграція зі схеми 0002 спершу створює перевірену
SQLite backup-копію, потім додає поле; тести доводять збереження старого запису
та версію backup. Repository acceptance зберігає logical index 5 окремо від
tool 0. Finalization поки не споживає це поле, тож live accounting не змінився,
а E11.01 залишається частковим.

Full suite:513 passed/461 subtests; Ruff clean; mypy120 clean. Wheel acceptance
`.runtime/wheel-acceptance-20261028-logical-material-index`:136 entries,
16 imports, migration `0003_logical_material_index`, Bambu mapping smoke
успішний; SHA256
`317194e73321d1beb33282f6abb7e9d3153499832537e97f3b2873c973c452fb`.
Наступна дія виконана нижче: fail-closed same-job receipt/3MF/provider-slot
resolver; persisted FeedSlot/mount join та material-row/segment projection
залишаються наступними. Не вмикати live writer чи списання та не оновлювати
installed EXE.

## Суворе зіставлення job receipt ↔ verified 3MF ↔ provider slot — 2026-10-29

Додано read-only `resolve_job_material_slots()`. Для зіставлення вимагає
однаковий SHA-256 файла в receipt і verified slice, той самий printer UUID,
свіжий (до 120 секунд) provider status і окремий повний AMS/feed-system
snapshot. Матеріали адресуються тільки через logical filament index із 3MF та
explicit mapping у receipt; точні system/slot keys мають знайти рівно один
зайнятий provider slot. Відсутній mapping, неповний/застарілий snapshot,
невідомий slot і unsupported залишаються UNKNOWN/UNSUPPORTED. `unused`, що
суперечить масі або шару 3MF, стає CONFLICT. Додаткові mapping IDs, яких немає
у вибраній plate, відхиляють зіставлення fail-closed.

Результат не шукає котушку, не створює/не змінює mount, `PrintJobMaterial`,
`MaterialUsageSegment`, reservation чи ledger. E11.01/E11.02 залишаються
частковими до join зі стійким FeedSlot/SpoolMount та приймання RFID; E11.03 —
до provider/layer rollover segments. Штатна `.venv312`: 521 passed,
464 subtests; Ruff clean; mypy121 clean. Wheel acceptance:
`.runtime/wheel-acceptance-20261029-job-slot-reconciliation/report.json`,
137 members, SHA-256 `51392013ad591bbf54dfc9b12c1b6324d43478cd1f2df1134e984d9ca8aa399b`.
Окремий `uv run` без Qt пропустив 6 UI tests; канонічна `.venv312` перевірка
повна. Наступна дія — перевірити, як перетворити MATCHED exact provider key на
рівно один durable FeedSlot/active mount і чи можна безпечно створити material
rows без облікової дії. Живе списання й встановлений EXE не чіпати.

## Exact durable FeedSlot ↔ mount ↔ RFID spool join — 2026-10-29

Додано точний printer-scoped `FeedSlotRepository.by_provider_key()` і
read-only `resolve_mounted_material()`. Resolver приймає лише MATCHED результат
попереднього same-job mapping; вимагає повний/свіжий AMS snapshot, точну
відповідність provider keys та durable observation timestamps/epoch/sequence.
Потім перевіряє opaque audit fingerprint payload (включно з hash tray/tag IDs),
наявність активного mount, assignment state та exact verified RFID identity,
яка мусить вести до тієї самої змонтованої котушки. Незбережений snapshot,
підроблений payload, відсутній mount, невідомий/конфліктний ID або різна котушка
не повертають spool id. Секретні/raw RFID values не записуються новим кодом.

Це ще не створює `PrintJobMaterial`, `MaterialUsageSegment`, reservation чи
ledger entry; E11.01/E11.02 лишаються частковими. Перевірено у `.venv312`:
524 passed, 464 subtests; Ruff clean; mypy122 clean. Wheel smoke:
`.runtime/wheel-acceptance-20261029-mounted-material-resolver/report.json`,
138 members; SHA-256
`5cfdfb1cbb9660b8a2061d50759246ff587d4c8469cc9d928fe6083794a4b3ca`.
Наступна дія — спроєктувати durable material-row projection із logical index
та tool/extruder окремо; спершу перевірити унікальний idempotency/conflict
contract, не підключаючи списання.

## Розділення logical material від tool у calculated finalization — 2026-10-29

Calculated finalization більше не зіставляє суми 3MF із `tool_index`.
Очікувані суми, provenance й підсумок матеріалу індексуються через окремий
`logical_material_index`; `tool_index` лишається перевіркою physical usage
segment. Кілька логічних матеріалів можуть належати тому самому tool, що є
необхідним для AMS із одним екструдером і кількома котушками. Для multi-material
job усі логічні індекси мають бути задані явно, повними й унікальними; старий
fallback дозволено лише коли є рівно один PrintJobMaterial і один факт 3MF.
Нульові/відсутні/дубльовані/часткові індекси не створюють припущень.

Acceptance: 527 passed, 464 subtests; Ruff clean; mypy122 clean. Offline wheel
`.runtime/wheel-acceptance-20261029-logical-material-finalization/report.json`,
138 members, SHA-256
`9b48398bb158aed822f9ca56d02f1756d501cc675de5b6b636c98c1e160fb160`.
Пов’язування receipt mapping із durable material rows і сегментами ще не
реалізоване; E11.01/E11.02/E11.03 залишаються частковими, автоматичний debit
та installed EXE не змінені. Наступна дія — спроєктувати ідентифікований
idempotency contract для проєкції materials і довести, звідки без припущень
отримується tool/extruder mapping; неоднозначні джерела залишати UNKNOWN.

## Checkpoint перед пороговою паузою — 2026-10-29

Повторно перевірені локальні HaspelSync джерела
`D:/Filament_Manager/localization/haspelsync/src/AGENTS.md` і `OPEN.md`. Вони
підтверджують, що `print.mapping` містить один target на logical filament
проєкту (unit у high byte, slot у low byte), `0xFFFF` — unused; mapping
активного job зберігається та перечитується, бо після реального remap AMS
принтер змінює його. Зміна після першого шару означає refill; старий slot/spool
потрібний для відрізка до зміни, новий — після неї. `tray_info_idx` — preset/
profile reference і не є spool ID. Це зафіксоване джерельне рішення, не кодова
зміна; HaspelSync не змінено.

На останньому ліміті п’ятигодинний залишок досяг рівно 15%, тому розробка
поставлена на паузу до наступного планового запуску. Тижневий залишок 71%.
Стан реалізації: 527 passed/464 subtests, Ruff чистий, mypy122 чистий; wheel
`.runtime/wheel-acceptance-20261029-logical-material-finalization/report.json`
SHA-256 `9b48398bb158aed822f9ca56d02f1756d501cc675de5b6b636c98c1e160fb160`.
CSV 118 IDs/BOM: 23 done, 22 partial, 73 planned.

Наступна дія після відновлення ліміту: розробити durable per-job mapping
observation history, щоб зберігати кожне `print.mapping` update разом із
sequence/observed time та completed layer; розрізняти початковий mapping до
першого шару від AMS refill після початку. Потім закривати/відкривати
`MaterialUsageSegment` лише за authoritative mapping change та підтвердженими
slot→mount→RFID joins. До цього не створювати debit; `tray_info_idx` не
використовувати як spool identity. Installed EXE не змінювати.











## E05.04 checkpoint: SCALE evidence gated by sensor and calibration — 2026-10-29

Added read-only SensorRepository and CalibrationRepository access inside the same SQLite UnitOfWork as evidence writes. `InventoryCommands.record_scale_reading(WeightReading, ...)` now requires an associated active spool, known gross/tare/net observations, a stable reading, valid interval/observation/receipt chronology, and an enabled SCALE sensor with that sensor's latest matching `scale` calibration version. Capture and explicit acceptance both reject expired calibration; acceptance rechecks sensor enablement and that calibration remains current. SCALE evidence is immutable, audit-fingerprinted/idempotent, captures the ledger cutoff, and does not change stock. The generic/manual capture command rejects SCALE source so callers cannot bypass validation. No hardware driver or Studio scale UI is claimed because no concrete device protocol is defined.

Evidence: `tests/integration/test_inventory_commands.py` includes calibrated/idempotent/stock-neutral capture, unstable/unknown rejection, disabled sensor, superseded calibration, and expired-at-acceptance checks. Focused suite: **48 passed /31 subtests**. Full suite: **569 passed /477 subtests in 74.86s**; `uv run ruff check src tests` clean. `uv run mypy src` still reports 26 diagnostics in existing migration/UoW/Studio files; no diagnostics were reported in the changed application/repository files. `git diff --check` could not run because `D:/Bot/Universal_Filament_Manager` is not a Git working tree.

E05.04 remains `У роботі`: hardware ScaleProvider implementation, UI setup/read path, device acceptance and Studio-scale history remain. Quota after the stage: 70% primary /52% weekly. Checklist totals are recorded from the BOM CSV.


## E05.06 checkpoint: current purchase profile in Studio — 2026-10-29

Перенесено з наявної схеми поля ціни/валюти/дати в домен, InventoryCommands і форми створення/редагування котушки. Додано окрему базову масу ціни, щоб не припускати, що вона завжди дорівнює nominal mass. Для ціни потрібні повні price+basis+currency; ExactDecimal не проходить через float; basis має бути >0; currency — три uppercase ASCII літери; purchase_date перевіряється як календарна дата ISO. Окрема безпечна міграція `0004_purchase_basis` додає нову nullable колонку без backfill старих значень; міграційний шлях перевіряє backup/versioned-schema умови на тестових БД. Метадані ціни не створюють ledger-дебет і не змінюють залишок.

Перевірки: InventoryCommands + Studio + migration focused **71 passed/37 subtests**; migration suite **22 passed/27 subtests**; останній повний suite **570 passed/483 subtests, exit 0**, `uv run ruff check src tests` clean. Перевірка Qt teardown окремо: перший повтор повного набору відтворив native access violation після summary; Studio окремо 24/exit0, решта 546/483 subtests exit0. Fixture тепер очікує завершення worker QThread, обробляє queued/deferred Qt events до закриття вікна; після цього повторний повний suite завершився кодом 0.

Статус E05.06 — `У роботі`: ще потрібні незмінний знімок ціни/бази/валюти на момент підтвердженої витрати, cost aggregation/history та UI-звіти. E05.04 теж лишається `У роботі`: hardware scale adapter/UI не можна довести без конкретної моделі/протоколу ваг. Checklist 118/BOM: 26 виконано /25 частково /2 у роботі /65 заплановано. Ліміти після етапу: 98% primary /51% weekly.


## E05.06 checkpoint: booking-time cost snapshots — 2026-10-29

Для підтвердженого ledger-дебету PRINT_CONSUMPTION тепер зберігаються точна загальна собівартість події (`unit_cost`) і валюта. Додано `application/costing.py`: кількість мінорних одиниць обчислюється цілими числами з half-up округленням за purchase price та окремою basis mass; snapshot додається до наявного JSON provenance. Підтримано UAH/EUR/USD/PLN, інші валюти залишаються без оцінки до визначення їхньої minor-unit точності. Невідомий/неповний профіль не блокує списання. Snapshot формується для успішного printer finalization та завершеного перевіреного 3MF; FAILED_PRINT не отримує вартості.

Докази: `tests/integration/test_print_finalization.py` перевіряє гривневий snapshot та поведінку для непідтриманої валюти; `tests/integration/test_calculated_finalization.py` перевіряє snapshot оцінкового 3MF із збереженням provenance. Повний suite: **573 passed / 483 subtests, exit 0**; `uv run ruff check src tests` — clean.

E05.06 лишається `У роботі`: потрібні запити історії вартості/агрегації за валютою та користувацький звіт. Наступна дія — додати read-only ledger cost report без сумування різних валют і без включення FAILED_PRINT чи записів без вартості. Ліміти після перевірки: 98% primary /51% weekly.


## E05.06 checkpoint: історія й підсумок вартості котушки — 2026-10-29

До booking-time snapshot додано read-only `InventoryCommands.cost_summary` та Studio backend. Для однієї котушки зведення рахує кількість підтверджених друків, суми окремо по валютах і невідомо оцінену витрачену масу; воно читає лише ledger PRINT_CONSUMPTION, не додає manual use/корекції/FAILED_PRINT і не складає різні валюти. Історія кожного запису показує його збережений snapshot; поточна ціна котушки на старі записи не впливає. Панель Studio показує окремі валютні суми та unknown-cost count/mass українською й англійською.

Докази: цільові finalization + Studio tests **56 passed /22 subtests**; повний `uv run python -X faulthandler -m pytest -q`: **574 passed /483 subtests, exit 0**; `uv run ruff check src tests`: clean. Підрахунок CSV після оновлення: 118 кроків, 26 виконано /25 частково /2 у роботі /65 заплановано (файл має BOM).

E05.06 лишається `У роботі`: є знімки та підсумок по котушці, але не реалізовано загальний/періодний звіт витрат і всі classic UI cost reports. Наступна дія — визначити підтверджений контракт старих звітів; потім додати read-only агрегат по періоду з валютним розділенням, не впливаючи на stock ledger. Ліміти перед наступним кроком: 97% primary /51% weekly.


## E05.06 checkpoint: date/printer cost report and CSV — 2026-10-29

Звірено classic HaspelSync actions HA177–180 і HA190 та `consumptionReport`: whitelisted UAH/EUR/USD/PLN, explicit price basis, booked/confirmed cost only, фільтр за принтером/періодом, currency-separated totals, unknown cost, row export CSV з UTF-8 BOM/`;`/formula escaping. Реалізовано UFM `InventoryCommands.cost_report(started_at, until, printer_id)` з bounded 10,000-row report; період застосовується за print-job start, а ціна береться лише зі знімка у незмінному ledger. SQL read використовує один join до принтера, котушки й завдання. Studio додає вибір локальних дат (кінцева дата включна), принтера або всіх принтерів, попередній перегляд звіту і безпечний CSV export. Різні валюти ніколи не підсумовуються разом; записи без знімка показуються як невідомі.

Докази: `tests/integration/test_print_finalization.py` звіряє дату старту, фільтр принтера, виключення запису поза періодом, точність валюти й invalid range; `tests/integration/test_studio_window.py` відкриває діалог і перевіряє CSV formula escaping. Цільові suites **58 passed /22 subtests**; повний suite **576 passed /483 subtests, exit 0**; Ruff clean. CSV лишається 118 кроків (119 рядків разом із header, BOM): 26 виконано /25 частково /2 у роботі /65 заплановано.

E05.06 все ще `У роботі`: кошторисний snapshot, історія, звіт по котушці та періодний звіт додано; треба звірити деталі повного старого CSV/schema semantics та acceptance UI, після чого додати точні missing behavior tests і закрити тільки якщо всі контрактні дії покрито. Ліміти після етапу: 95% primary /51% weekly.


## E05.06 checkpoint: Spoolman purchase-price import preview — 2026-10-29

Закрито дефект попередньої правки імпортера (невизначена таблиця schema metadata) і додано контрольоване перенесення закупівельних даних із локальної Spoolman SQLite. Ціна конкретної котушки має пріоритет над ціною профілю; валюта береться з read-only `setting.currency`, базова маса — з фактичної маси котушки або відомої nominal-маси філаменту. Без однозначної валюти ціна залишається неперенесеною. Preview показує кількість перенесених і пропущених цін. Підтримано старі схеми без колонок цін; тестові й production-шляхи відкривають джерело read-only, оригінальну базу не змінено.

Перевірки: importer + Studio **33 passed**; повний `uv run python -X faulthandler -m pytest -q` — **578 passed /485 subtests, exit 0, 76.83s**; `uv run ruff check src tests` — clean. Чекліст: 118 кроків, Частково виконано: 25 / Виконано: 26 / Заплановано: 65 / У роботі: 2; UTF-8 BOM збережено. Ліміти на початку/після етапу: залишок 93% primary /50% weekly.

E05.06 залишається `У роботі`: закупівельні поля й report path реалізовані, але необхідна окрема звірка старих екранів/CSV semantics і acceptance повного звіту до закриття кроку. Наступна дія: зібрати classic HaspelSync report contract та fixtures, зіставити header/order/periods/dates/unknown costs із UFM CSV, за потреби доповнити coverage; не змінювати ledger stock і не записувати в Spoolman DB.


## E05.06 checkpoint: report contract parity and clean Qt exit — 2026-10-29

Зіставлено `consumptionReport`/`exportReport` HaspelSync з UFM date/printer report та CSV. Старий формат має 7 основних колонок date/job/spool/mass/cost/currency/status; export бере всі bookings з вибраного періоду, але агрегує тільки `booked`, показує окремий `reviewCount` для pending/uncertain і `unknownCostCount` для booked без ціни. UFM CSV розширює схему до 9 колонок, додаючи printer/source, і включає тільки підтверджені `PRINT_CONSUMPTION` ledger-події. Це зберігає бухгалтерську межу підтвердження; відсутній review-count/рядки у звіті треба зіставити з окремим E05.08 reconciliation, перш ніж вирішити, чи додавати їх до цього екрана.

CSV acceptance винесено у чисту функцію й перевірено: BOM, `;`, заголовки/порядок полів, formula escaping, збереження `;` у назві та порожні cost/currency для невідомої оцінки. Повторюваний Windows access violation після pytest summary усунуто в тестовому fixture: QApplication закриває всі вікна й обробляє DeferredDelete, але wrapper не завершується/не збирається вручну. Цільові: 8 passed; Studio module: 26 passed; suite без Studio: 552 passed/485 subtests; повний suite явним запуском Studio першою: 578 passed/485 subtests за 76.60s, `PYTEST_EXIT=0`; Ruff clean. CSV: 118 кроків, UTF-8 BOM; ліміти останньої перевірки: 91% primary /50% weekly.

E05.06 лишається `У роботі`. Наступна дія: простежити UFM external receipt/reconciliation states і перевірити, чи є придатний read model для reviewCount без приписування ledger-кредиту/дебету; потім розв’язати межу E05.06↔E05.08 і покрити її тестом. Не змінювати balance напряму й не вмикати у витратні підсумки pending/uncertain.


## E05.06 завершено: price import та звіт витрат — 2026-10-29

Крок E05.06 переведено у `Виконано`: інвентарні ціни/валюта/база закупівлі, read-only імпорт Spoolman, immutable cost snapshot, історія по котушці та обмежений звіт за періодом/принтером із CSV covered tests мають реалізацію й приймання. CSV-звіт зберігає seven-field Haspel-compatible core (date/job/spool/mass/cost/currency/status) і додає printer/source; confirmed unknown-cost лишається рядком із порожньою сумою. Review bookings не змішуються зі stock cost: Haspel pending/uncertain — зовнішній write review, тоді як UFM receipt `PENDING` — ingestion queue, а `OPEN/IN_REVIEW` reconciliation — свої доменні задачі. Окремий функціональний паритет pending/uncertain віднесено до E12.03 згідно з планом.

Докази: cost/report/import tests у `tests/integration/test_print_finalization.py`, `test_calculated_finalization.py`, `test_spoolman_importer.py`, `test_studio_window.py`; focused importer+Studio 33 passed; CSV contract 8 passed; повний suite після Qt teardown зміни **578 passed /485 subtests, PYTEST_EXIT=0**; `uv run ruff check src tests` clean. `docs/INTEGRATION_CHECKLIST_UK.csv`: 118 steps; Частково виконано: 25 / Виконано: 27 / Заплановано: 65 / У роботі: 1; BOM verified. Основні ліміти після етапу: залишок 90%/50%.

Наступний крок за планом: E05.08 — перевірити зареєстровані дії на normal/empty/error/unavailable states та додати конкретні UI acceptance докази для ще непокритих дій; зберігати E12.03 окремим майбутнім review workflow.


## E05.08 checkpoint: measurement action error states — 2026-10-29

Додано UI acceptance для діалогу ручного зважування: порожній inventory вимикає дію; некоректне gross<tare імітує доменну помилку; offline backend імітує недоступність. У двох помилкових випадках форма не переходить до питання прийняття, evidence не створюється, залишок та ledger залишаються незмінними, UI показує sanitized exception type. Нормальні Yes/No сценарії були наявні й лишилися окремо перевірені. На першому запуску тест помилково очікував відсутність selection після додавання spool, але refresh навмисно автоматично вибирає першу видиму котушку; тест виправлено на справді порожній каталог, runtime-код не змінювався.

Докази: `test_studio_manual_weighing_requires_explicit_reconciliation_confirmation` та `test_studio_manual_weighing_errors_preserve_stock_and_evidence`: **4 passed**; `uv run ruff check src tests`: clean. У `docs/UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv` record_measurement тепер `Перевірено` для ручного UI шляху; hardware SCALE UI не заявляється і лишається E05.04. E05.08 залишається `Частково виконано`: ще потрібні негативні стани для інших дій. Чекліст: 118 кроків, Частково виконано: 25 / Виконано: 27 / Заплановано: 65 / У роботі: 1; BOM збережено.


## E05.08 checkpoint: stock action failure and unavailable states — 2026-10-29

Для UI stock opening/deduct/add перевірено невалідну масу та unavailable backend через кожну кнопку. В усіх 6 сценаріях Studio показує лише тип помилки, баланс і історія лишаються без змін; opening тестується на котушці з невідомим запасом, add/deduct — на відомому. Доказ доданий у `docs/UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv` до трьох відповідних action rows.

Цільові тести: **6 passed**, `uv run ruff check src tests`: clean. E05.08 лишається `Частково виконано`: частина інших edit/archive/rebuild/compensation/measurement screen error states іще без прямого UI evidence. Чекліст 118 кроків: Частково виконано: 25 / Виконано: 27 / Заплановано: 65 / У роботі: 1; BOM збережено. Повний suite останнього завершеного запуску до цього тестового пакета: 580 passed/485 subtests exit 0.


## E05.08 checkpoint: edit/archive/rebuild/compensation unavailable paths — 2026-10-29

Через справжній Studio QThread перевірено OSError/unavailable backend для `edit_spool`, `archive_spool`, `rebuild_projection`, `compensate_transaction`. Після `task.wait`/Qt event processing кожна дія показує sanitized type `OSError`; початковий залишок, кожен ledger transaction і spool lifecycle не змінені. Тест parameterized на чотири handlers. Action registry має evidence для відповідних рядків.

Цільові: **4 passed**, `uv run ruff check src tests`: clean. E05.08 ще `Частково виконано`: registry actions для normal/empty/error/unavailable повністю не закрито, необхідні решта read/edit/dialog, cost-report і system actions. CSV: 118 кроків, Частково виконано: 25 / Виконано: 27 / Заплановано: 65 / У роботі: 1; BOM збережено.


## E05.08 checkpoint: negative UI states with clean full suite — 2026-10-29

Action registry тепер має UI error/unavailable evidence для manual measurement, stock opening/deduct/add, edit/archive spool, rebuild projection і compensation. Для stock-помилок 6 cases: invalid amount і simulated backend failure; для 4 інших handler-ів — unavailable path через контрольований executor; у всіх збережено stock/history. Measurement додатково має порожній catalog. Нормальні confirmation/No сценарії лишаються попередніми доказами.

Повний suite після нових тестів: **590 passed /485 subtests, 78.40s, PYTEST_EXIT=0**; Studio модуль **38 passed, exit 0**; `uv run ruff check src tests` clean. Повторні QThread у negative-parametrized тестах повертали native access violation у кінці процесу; їх замінено керованим synchronous executor у самих UI-handler tests, production Task/QThread не змінювався. Чекліст 118 кроків: Частково виконано: 25 / Виконано: 27 / Заплановано: 65 / У роботі: 1; UTF-8 BOM збережено. Ліміти останньої перевірки до повного прогону: 88% primary /50% weekly.

E05.08 лишається `Частково виконано`: ще покрити error/unavailable для решти catalog/location/report/import/backup/refresh/column chooser дій, а потім окремо перевірити empty/default acceptance й оновити registry для кожного handler. Наступна дія — почати з create/edit material та brand form validation/unavailable writes.


## Read-only перевірка активного UI — 2026-10-30

Повторно звірено запущені вікна через Computer Use: Candidate7 (`D:\UFM_TestCandidate7\UFM Studio`) та попередній Candidate5 відкриті одночасно. Accessibility snapshot Candidate7 підтвердив українську навігацію «Філамент / Пристрої / Матеріали / Система», локальну базу без браузера/Docker, порожній інвентар і test-build позначку. Це лише стан вікна й доступних control labels; нічого не натискали, дані не змінювали, принтер/облік не запускали. Попередній візуальний перегляд Candidate7 (розкладка, теми та прокрутка) лишається окремим свідченням; власницьке UX-приймання, keyboard/focus та різні DPI не підтверджені. E16.04 — окремий clean-Windows gate. Для E14.03 додано стилі помітного клавіатурного фокусу й зібрано Candidate8; runtime appearance focus state і DPI-матрицю ще не прийнято.


## Кандидат8: видимий клавіатурний фокус — 2026-10-30

Під час статичного огляду QSS для E14.03 не було явного виразного `:focus` оформлення для основних кнопок і полів. Додано зелений 2px контур для кнопок, текстових полів і combo boxes та білий пунктирний контур для фокусованих елементів навігації/таблиці. Ізольовані наявні перевірки: `tests/integration/test_studio_window.py` — 62 passed/exit 0; Ruff clean; JSON ресурс лишився валідний.

Побудовано окремий Candidate8 у `D:\UFM_TestCandidate8\UFM Studio`: manifest перевірений, 376 файлів; EXE SHA-256 `0DF64CCB71ACACB1B88A9669837F5FE72D42D6A265708017385AB0BCEC7598D3`; PE версія `0.1.0.dev0`; Authenticode `NotSigned`. SBOM sidecar CycloneDX 1.7 має 399 компонентів, `incomplete`, SHA-256 `6AA4F3C1BDC4C3A904777012F412A2F849BAF85376C9CF1AADB1DFF4FBC567B0`. Створено новий ярлик `UFM Studio — ТЕСТ Candidate8.lnk` з `--data-dir D:\UFM_TestCandidate8\Data --locale uk-UA`; шлях тестових даних ще не створено/не використовувався. Candidate8 не запускався. Ярлики й тестові дані Candidate5/7 не змінювалися.

Статус чекліста: 118 рядків — 29 виконано / 43 частково виконано / 45 заплановано / 1 у роботі; UTF-8 BOM збережено. E14.03 тепер «Частково виконано» лише за реалізацію стилю фокусу; ручна перевірка keyboard traversal, фокусу на екрані та DPI 100/125/150/200 ще потрібна. E16.04 означає окрему перевірку clean Windows і не вважається виконаним. Release залишається NOT READY.


## E03.08 — package provenance boundary review — 2026-10-30

Static review of `pyproject.toml`, `scripts/build_studio.ps1`, `scripts/collect_studio_notices.py`, the release installer path and root notice files confirms: the project has no selected `project.license` metadata or root UFM LICENSE; the portable build copies `THIRD_PARTY_NOTICES.md` and collects package notices, but that collector expressly does not claim a complete SBOM or legal approval; the installer refuses a missing/mismatched CycloneDX sidecar but still accepts `composition=incomplete`. Candidate10 therefore remains internal-only and E03.08 Partial. Required external decisions: choose UFM license, resolve Qt/Python package license metadata and notices, then produce/approve a complete BOM. No legal conclusion inferred from SPDX/package metadata.


## E03.07 — legacy Haspel writer-scope review — 2026-10-30

Source paths inspected read-only: `linked-stack/haspelsync/src/bookings.js`, `state.js`, `jsonfile.js`, `config.js`, `spoolman.js`, and the matching source rules. `transferAccountingAuthority()` explicitly describes synchronous same-process checking; active booking IDs are a process-local Set; the authority/booking journal is a JSON file below configured `DATA_DIR`; shared persistence writes a deterministic `<file>.tmp` and rename, with no inter-process lock/fence or compare-and-swap. Inference from these implementations: two HaspelSync processes pointed at the same DATA_DIR can race journal ownership/updates, and isolated per-instance directories also cannot coordinate legacy Spoolman writes. This confirms the existing E03.07 blocker; no code/data/config was changed, no printer/API was contacted. Automatic debit remains disabled.


## E07.03 — source identity and ingestion-boundary trace — 2026-10-30

Static source trace: `bambu_lan.py` assigns a fresh UUID source epoch in each provider instance and increments a local event counter when the serialized snapshot changes. The provider includes `task_id`, `subtask_id`, and `job_id` fields in its JSON snapshot, but field names alone do not prove these IDs are stable or unique across reconnect/restart/reprint. The emitted `PrinterEvent` is a normalized snapshot, not the original MQTT report bytes. `printer_monitor.py` has a bounded event buffer; the current Studio UI drains via `take_latest_event()`. A source search found no runtime caller of `ReceiptIngestion` or `ProjectionDrain`, so there is no durable Bambu-to-job projection path yet. Keep automatic debit disabled until a consumer with verified occurrence identity exists and redacted traces cover reconnect, restart, same-file reprint, partial/cancelled runs, and replay. This is static code evidence only; no network/device was contacted.


## E07.03 — fixture identity coverage — 2026-10-30

A read-only aggregate scan of the 13 checked-in HaspelSync report fixture files found 22 nested objects with at least one task/job identity field. `job_id` was absent in 12, zero/empty in 4, and nonzero/other in 6; `task_id` was zero/empty in 13 objects; `subtask_id` was absent in 9 and zero/empty in 6. Raw values were suppressed. These are static report snapshots, not event sequences, and cannot establish uniqueness across reconnect, process restart, same-file reprint, or replay. The existing request for redacted sequence traces remains necessary before an automatic debit identity can be approved.


## E10.01 — terminal print-state projection coverage — 2026-10-30

Checklist classification corrected to Partial after source/test review. The domain and receipt projection already model distinct completed/failed/cancelled states, source-provenanced exact terminal times, and first-terminal conflict guards (`src/ufm/domain/entities/printing.py`, `src/ufm/application/dto/worker_protocol.py`, `src/ufm/application/job_projection.py`). Existing isolated projection coverage includes cancelled duplicate retention and conflicting failed/completed terminals in `tests/integration/test_job_projection.py`. However, current Bambu LAN snapshots are not wired to `ReceiptIngestion`/`ProjectionDrain`, and validated source timestamp/identity delivery plus restart/reconnect acceptance are absent. No automatic accounting path was enabled.


## E10.01–E10.05 — reconcile planned accounting rows with implemented calculation kernel — 2026-10-30

Source/test review showed E10.01–E10.05 were still marked Planned despite existing domain and calculation-kernel support. Reclassified these rows as Partial, without claiming live Bambu runtime: terminal state projection stores separate completed/failed/cancelled timestamps; the verified-3MF kernel calculates separate per-logical-material full/partial estimates; partial use prefers trusted per-layer extrusion and otherwise uses an explicit active-layer-range estimate; the range policy is opt-in and auto-policy defaults disabled; failed/cancelled partial/zero settlement cases have existing isolated test coverage. The required live event-to-job producer, stable provider run identity, runtime mapping to a confirmed physical spool and acceptance across reconnect/reprint/replay remain absent. Status totals now 29 Done / 48 Partial / 40 Planned / 1 In Progress (118 rows, 5 columns, UTF-8 BOM). No source or database changed; no test rerun because this stage only reconciled the documented status with current source and existing test names/results.


## E10.06 — часткове покриття скасування/збою — 2026-10-30

Перевірено відповідні наявні сценарії: zero-cancel без ledger, failed partial settlement із міткою оцінки, duplicate/conflicting terminal, пізній running після terminal, регрес layer/hash та current-layer/progress. Цільовий ізольований запуск: 7 passed. Змінено лише статус/evidence E10.06 на Partial. Не покрито повністю події після заміни AMS/котушки, всі реальні порядки cancel/failed/completed і модельно-специфічний producer; Bambu/принтер не підключалися. Чекліст з BOM: 118 рядків, статуси 29/49/39/1.


## E11.04–E11.07 — межі багатокотушкового settlement — 2026-10-30

Graphify-навігацію перевірено безпосередньо за `calculated_finalization.py`, `costing.py` та fixtures. Код перевіряє contiguous material-use segments, точне 3MF-total/evidence співпадіння, spool/mount/slot/RFID scope; ручні splits потребують окремої audit-події. Детермінований local SQLite batch записує decisions, ledger, balances, reservations і job state; невдалий другий spool або audit rollback не залишає часткових записів. Цільові наявні перевірки: 5 passed. Змінено E11.04–E11.07 на Partial. Відкриті прогалини: реальне створення сегментів з AMS/rollover/physical switch events, автоматичне версійоване розподілення mg-округлення, глобальне Haspel/UFM writer fencing і live acceptance. Чекліст: 118 рядків, BOM, статуси 29/53/35/1.


## E11.08 — межі AMS/невідомого mapping — 2026-10-30

Перевірено графові напрямки за кодом і synthetic fixtures. Логічний індекс матеріалу зберігається окремо; підтверджений swap повертає/створює сегмент, зовнішній слот залишається printer-scoped, невідоме зіставлення зберігає unresolved usage та не закриває чужий сегмент. Наявні ізольовані тести: 7 passed. E11.08 переведено з Planned у Partial. Не перевірено повну матрицю multi-AMS/color на моделях, живе rollover/offline/re-handling і надходження реальних подій у сегменти. Чекліст: BOM, 118 рядків, 29/54/34/1.


## E12.01–E12.03 — UI історії та pending/uncertain — 2026-10-30

Статично звірено `StudioWindow.show_history`, backend history/cost/measurement queries і authority transfer guard; існуючі UI-тести для ledger history, estimated label, cost summary та компенсації: 4 passed. E12.01/.02 стали Partial: UI показує per-spool ledger, вимірювання, суму та обмежені estimate details, але не durable print-job/receipt history і не повний пояснювальний ланцюг для окремого рішення. E12.03 лишився Planned: Haspel pending/uncertain counts показуються і блокують UFM cutover, але окремого inspect/resolve/retry workflow немає. Чекліст з BOM: 118 рядків, 29/56/32/1.


## E12.04–E12.07 — компенсації, вимірювання, експорт та parity — 2026-10-30

Перевірено UI/backend/application source і запущено 10 відповідних ізольованих чинних тестів: 10 passed. E12.04–E12.06 стали Partial: компенсації є append-only reversal; inventory measurement reconciliation захищає ledger cutoff та пізній друк від подвійного списання; Qt має formula-safe CSV report/inventory export. Немає локального HTTP API і немає повного conflict/pending booking UI. E12.07 лишено Planned: наявність feature/action CSV сама по собі не доводить кнопку/дію й acceptance для кожного HaspelSync сценарію. Статуси: 118 рядків, BOM, 29/59/29/1.


## E12.07 — інвентаризація UI action parity — 2026-10-30

Перечитано action registries: inventory має 22 дії (18 verified, 4 QR export/print acceptance pending); system має 7 дій (2 попередньо accepted, 1 partial UI acceptance, 4 pending). У 211 HaspelSync contracts та 124 feature rows описані посилання/дії, але це не підтверджує повного Qt equivalence. E12.07 стало Partial; ще потрібні pending-control acceptance і повний mapping кожної legacy дії у implemented/deferred/absent із доказом, включно з hardware/owner gates. Чекліст: BOM, 118 рядків, 29/60/28/1.


## E13.01–E13.06 — source audit фізичного керування — 2026-10-30

Перевірено contracts і реальні printer adapters. `pause/resume/cancel` визначені лише в port; обидва провайдери оголошують їх false. Температура доступна тільки як спостереження; setter/fan/load/unload/motion/upload/start-print handlers не знайдено. Camera capability також false; stream/job queue відсутні. E13.01–E13.06 лишаються Заплановано з конкретними source limitations у CSV, а непідтримувані фізичні команди мають залишатися недоступними. Hardware acceptance зараз не підтверджено. Загальні статуси без змін: 118 рядків, BOM, 29/60/28/1.


## E14.01–E14.06 — поточний UI, localization та lifecycle evidence — 2026-10-30

Candidate10 вже оглянуто на одному ПК/масштабі: чотири робочі сторінки відображалися без очевидного обрізання, але це не DPI/keyboard/owner acceptance. Український і англійський UI-каталоги мають по 186 ключів, однакові множини й 0 порожніх рядків; 5 наявних locale/monitor-close тестів passed. CloseEvent чекає фонового worker/monitor перед закриттям. Наявні guide і bounded safe-log viewer показують лише allowlisted поля. E14.01–E14.06 тепер Partial через реальні частини плюс невиконані acceptance: translation review, DPI matrix, великі списки/in-flight dialogs, повний feature acceptance та діагностичний export. Чекліст: BOM, 118, 29/65/23/1.


## E15/E16 — cutover limits and Candidate10 release inventory — 2026-10-30

E15.04/.05 стали Partial за локальні SQLite crash/concurrency fixtures та verified snapshot/migration-backup implementation; три відповідні тести пройшли. Відсутні cross-process Haspel fencing, dual-run, реальні AMS/принтерні trace comparisons, lost-response acceptance і owner cutover/posting checks. E15.01–.03/.06/.07 залишені Planned. У release rows E16 актуалізовано stale Candidate9 на Candidate10: 376-file manifest, SHA-256 EXE `D398AA91...B0BF02`, Authenticode NotSigned, CycloneDX 399 components/incomplete; portable test shortcut окремий від user data. Інсталятор був лише попередній Candidate4; clean-Windows, install/upgrade/restore acceptance відсутні. UFM license, native SBOM/legal review, signing, unexplained intermittent full-suite exit та owner/hardware acceptance залишають release NOT READY. E16.07 лишено Planned, cleanup не робили. Checklist: BOM, 118 rows, 29/67/21/1.


## Release provenance note — workspace metadata — 2026-10-30

Read-only check: `D:/Bot/Universal_Filament_Manager` has no root `.git`; `linked-stack/haspelsync` has its own Git metadata. Therefore root source revision/diff provenance could not be inspected in this checkout. No repository was initialized and no commit made. Add/recover source revision provenance before public release; Candidate10 remains an internal test bundle. Checklist remains 118 rows, BOM, 29/67/21/1.


## Повний suite — повторна перевірка Candidate10 source — 2026-10-30

На locked Python 3.12.14 запущено наявний повний suite: `python -m pytest` — 635 passed, exit 0, 80.73 s. Жодних тестів не додавали; fixtures/temp SQLite, без принтерів і production DB. Цей запуск підтверджує успішний повний прохід поточного source, але попередній одиничний exit 1 після повного зеленого summary залишається unexplained, тому процесну детермінованість не підтверджено. Checklist statuses unchanged: 29/67/21/1. Release remains NOT READY for independent identity/fencing/legal/SBOM/signing/clean Windows/hardware/owner gates.

## E03.08/E16.02/E16.05 — installer release gate hardening — 2026-10-30

Source review found that scripts/build_installer.ps1 previously required a matching CycloneDX 1.7 sidecar but accepted its declared incomplete composition and allowed unsigned EXE/installer builds. The gate now refuses before Inno Setup unless a signing certificate and timestamp are supplied, the bundle EXE is already validly signed by that same thumbprint, the SBOM explicitly declares complete metadata and composition plus a declared project license and approved license review, and the final installer verifies under the same certificate. The current SBOM generator still deliberately emits incomplete/observed-only metadata; therefore this change blocks public installer generation rather than claiming those missing obligations are satisfied. The earlier Candidate4 installer and Candidate10 portable folder were not modified. PowerShell AST parsing passed; no installer was compiled, installed, or launched. E03.08/E16.02/E16.05 remain Partial. Checklist: UTF-8 BOM, 118 records, 5 columns, 29/67/21/1. Next: complete source provenance/SBOM and license decisions; obtain approved signing material before producing any public installer.

### E16.02 version gate follow-up — 2026-10-30

The public installer builder also rejects development/prerelease versions and accepts only stable X.Y.Z; Candidate10 has PE version 0.1.0.dev0, so it is expressly not eligible. Updated the user guide, release acceptance checklist, and E16.02/E16.05 evidence. No artifact or installed program changed.

## E16.05 — source-input provenance in new bundle manifests — 2026-10-30

The package manifest writer now records a deterministic ordered inventory (relative path, size, SHA-256) for UFM package files, packaging/build scripts, dependency lock/project metadata, notices and the three Haspel source files used by the resource sync. It hashes that inventory and, when the root is a Git checkout, records revision and clean/dirty status. Manifest verification recomputes the source snapshot and rejects drift. A safe temporary bundle was generated and verified; it recorded 177 source inputs and a 64-hex tree hash. The current root has no Git revision, so a future public installer remains blocked even though content hashes are recorded. Candidate10 is unchanged and predates this field. Ruff passed for the modified manifest script; checklist status unchanged at 29/67/21/1. No test suite, public build, database, printer or linked-stack file was changed.

## Release-doc chronology audit — 2026-10-30

Reconciled historical Candidate13/Candidate10 notes so they cannot be mistaken for the current build; Candidate15 remains the current internal manual-test candidate. E12.03 evidence now identifies Candidate11/12 as historical and makes clear that Candidate15 has not received live HaspelSync acceptance for booking review. Release status and checklist statuses are unchanged; no build or user data was modified.

E14.06 status note: Candidate11/12 build references in the checklist are now historical; Candidate15 does not have owner acceptance of diagnostics preview/save. Release gates remain open.

## E05.04 — bounded weighing verification — 2026-10-30

Targeted existing tests run separately passed: Studio manual-weighing UI 4 passed/69 deselected; inventory measurement commands 6 passed/40 deselected; both exit 0. Source inspection confirms `ScaleProvider` is only a protocol port; Studio has no concrete hardware adapter. Manual gross/tare/net evidence and explicit stock reconciliation exist, but physical scale selection, calibration workflow and hardware acceptance are still open. E05.04 remains In Progress; no status was promoted and no device or production inventory was touched.

## E16 checklist — current-candidate chronology alignment — 2026-10-30

Release checklist rows E16.01, E16.02 and E16.08 now explicitly supersede earlier Candidate10/11/12 build snapshots with Candidate15 as the current internal test bundle. Historical evidence remains intact. Candidate15 is unsigned development build, 374 manifest files, no complete SBOM/installer; all-tab visual review is one-PC only. Full-suite Qt native exit instability remains open. Checklist status values are unchanged.

E14.01 checklist now labels Candidate10's screen check as historical and carries forward only the bounded Candidate15 four-tab visual evidence; status remains Partial.

## E03.08 — observed license-classifier fallback — 2026-10-30

The locked release environment's `jaraco.classes` 3.4.0 and `segno` 1.6.6 METADATA contain OSI license classifiers and packaged LICENSE files, but omit License/License-Expression fields; the collector therefore wrote “not specified”. Updated `scripts/collect_studio_notices.py` to retain sorted, deduplicated classifier strings explicitly labeled “Classifier metadata only”. Four focused tests passed; Ruff and separate mypy checks for the collector/test passed. A temporary run of the locked release collector covered 21 distributions and emitted the verified jaraco.classes MIT and segno BSD license-classifier observations. This records upstream-declared metadata only; it does not determine applicable terms or legal compatibility. Candidate15 has no complete SBOM, no SBOM was regenerated, and E03.08 remains Partial. Checklist remains UTF-8 BOM/118 unique IDs with 29 Done / 68 Partial / 20 Planned / 1 In Progress. Next: carry this observation-only metadata into a newly generated inventory after an eligible candidate build, then resolve full native component scope and obtain the project license/legal review; do not claim legal approval.

## E14.06 — Candidate15 diagnostics-consent preview smoke — 2026-10-30

On the isolated Candidate15 data path, opened the diagnostics consent preview only. At 1360×892 the dialog was centered and readable; it enumerated excluded raw fields, printer/spool numbers, paths, addresses, settings, DB and secrets; showed 0 included/0 omitted rows and a SHA-256; and asked the operator to review event names/times. Chose No. No diagnostic file was saved/transmitted and no settings or data changed. This is agent UI smoke on an empty test log, not owner acceptance; E14.06 remains Partial. Checklist still has BOM/118 unique IDs, 29 Done /68 Partial /20 Planned /1 In Progress.


## E14.01/E14.06 — UI review and diagnostic privacy fix — 2026-10-30

Computer Use rechecked Candidate15 at 1362×892 on Filament, Materials, Devices and System. Visible labels, tables and action buttons fit; empty-state guidance is clear and spool-specific controls are disabled without a selection. The Devices page correctly describes network discovery as candidates and marks physical control as unavailable. This remains an empty-data, single-PC smoke only. The diagnostics consent preview was readable and the log viewer showed its explicit empty-log state.

A source probe reproduced a privacy defect: arbitrary syntactically valid event names such as `printer_serial_123456` were exported verbatim. Added `SAFE_LOG_EVENT_CODES` as a shared explicit allowlist used by structured logging and the diagnostic exporter. Unknown well-formed event codes are now replaced/omitted and counted. Targeted tests: diagnostics/logging/release metadata 13 passed; the Studio diagnostics-registry UI test 1 passed (72 deselected); Ruff clean; `mypy src` clean for 139 source files. The live candidate log was empty; non-empty export was verified with isolated unit fixtures.

Default full-suite run after the code change: 659 passed and 489 subtests passed in 81.56s, then Python emitted a Windows fatal access violation and exited 1 without a Python frame. This is the known intermittent Qt/native teardown problem, still unresolved. Checklist: UTF-8 BOM, 118 unique rows, statuses 29 Done / 68 Partial / 20 Planned / 1 In Progress; no completion status was promoted. Candidate15 does not include this source fix. Next: build a separate Candidate16 portable internal test bundle from current source, preserving Candidate15 and all user data; run only its safe-launch/manifest checks unless launch-time approval is provided. Public release remains NOT READY.

## 2026-10-30 — Candidate16 test instructions and SBOM chronology

Aligned the manual guide, release acceptance, feature-parity note and E03.08 evidence: Candidate16 is the newest internal bundle (378 manifest-verified files; 401-component CycloneDX marked incomplete), while Candidate15 is still the latest UI-reviewed application. The guide now gives Candidate16's exact executable and isolated `--data-dir` without creating another desktop shortcut. Candidate15's release-document subsection is labeled historical. The classifier-only MIT/BSD fields are explicitly observations, not legal determinations. No app was launched and no data/shortcut was changed during this documentation-only stage. Checklist remains 118 unique IDs with UTF-8 BOM and unchanged counts: 29 Done / 68 Partial / 20 Planned / 1 In Progress.

**Verification after documentation edits:** diagnostics/logging/release-metadata unit selection 13 passed; safe diagnostics Studio registry integration selection 1 passed/72 deselected; affected-file Ruff clean. These checks do not replace Candidate16 UI launch/owner acceptance.

**Next:** obtain action-time confirmation before launching the new Candidate16 through Windows UI; independently continue the source audit of print-run identity, Haspel writer fencing, and safe artifact backup boundaries. Do not enable stock accounting while these safety prerequisites remain unproven.

## E03.07 — regression coverage for Haspel local authority guard — 2026-10-30

Added two isolated tests to the preserved HaspelSync test suite. They prove the per-service journal rejects UFM activation while a booking is pending, rejects stale revisions and conflicting reuse of a request ID, and blocks the real booking handler before its non-idempotent Spoolman HTTP write after local ownership transfers to `UFM_ACTIVE`. `node --test test/bookings.test.js`: **16 passed**, exit 0; fixture/server data are temporary and localhost-only. Source and configuration of linked HaspelSync were not changed.

This still does **not** establish global writer fencing: Haspel OpenAPI/source explicitly says this per-service authority endpoint is not a global process lock. Other Haspel instances or direct Spoolman clients remain outside its ownership record. E03.07 remains Partial and estimated auto-debit stays fail-closed. Checklist: 118 unique rows, UTF-8 BOM; 29 Done / 68 Partial / 20 Planned / 1 In Progress.

**Next:** continue the independent source audit for any shared service/lease that could fence all stock writers; if none exists, keep that as an architecture/owner blocker rather than inventing a local lock that would overstate safety. Candidate16 UI launch still awaits the action-time confirmation requested for the new binary.

**Cross-side focused verification:** `node --test test/bookings.test.js test/accounting.test.js` — 30 passed, exit 0; UFM `tests/unit/test_haspel_authority_client.py` — 10 passed plus 4 subtests, exit 0. Both use isolated test data/endpoints; neither proves production deployment-wide writer ownership.

## Candidate15 — read-only System-page visual follow-up — 2026-10-30

Computer Use captured the already-open Candidate15 System page at 1362×892. Heading, public-release limitation notice, language and log-level controls, actions and isolated data path were visible/readable without clipping. The lower area is mostly blank because this settings page has few controls. No UI action or setting/data change was performed. This is one-PC Candidate15 evidence only; Candidate16 launch, owner review, physical DPI, keyboard/accessibility and broader dialogs remain open. E14.01 stays Partial. Checklist status totals unchanged.


## 2026-10-31 — Bambu AMS read-only remain observations

За Graphify-підказкою перевірено `bambu_lan.py → FeedSlotSnapshot → topology audit proof → Studio monitor`, а поля підтверджено у локальному Bambu Studio source: `DevFilaSystem.h:82-83` описує `remain` як 0..100 та `remain_g` як грами з `-1` sentinel; `DevFilaSystem.cpp:117-121` трактує нульову точну масу як відсутнє вагове значення. Реалізовано незалежний `remaining_percent`, читання тільки bounded integer `remain` і exact positive-integer `remain_g`; жодної оцінки маси з номіналу, assignment, обліку чи stock write немає. Devices monitor явно маркує обидва значення як повідомлені принтером. Змінений E11.08 evidence, статус лишився `Частково виконано`; CSV має UTF-8 BOM, 118 унікальних ID; підрахунок: 29 Виконано / 68 Частково виконано / 20 Заплановано / 1 У роботі.

Перевірки: Ruff clean; targeted mypy — 4 source files clean; feed snapshot/Bambu parser selection 6 passed, topology idempotency selection 1 passed, Studio read-only monitor 1 passed; locale JSON and bilingual placeholder names valid. Це локальні contract/UI fixture тести, не реальне підключення/AMS acceptance. Зміни не торкаються принтера, робочої БД, HaspelSync source або ярликів; test print не запускався.

Незавершене: live hardware/model acceptance, зовнішня котушка, RFID-to-spool identity, production event-to-segment wiring та multicolor/multi-AMS rollover. Глобальні release gates лишаються: durable print-run identity, cross-process single-writer fence, intermittent Qt native exit, SBOM/legal/signing/source provenance/installer/clean-Windows and owner acceptance. Public release remains NOT READY; auto-debit stays disabled.

Наступна дія: refresh root Graphify plus external traceability/project maps including the localization JSON resource, verify all changed source hashes, then take next unblocked E11 item without promoting statuses without full evidence.


## 2026-10-31 — Bambu LAN auth diagnosis and Candidate18

A user-requested live, read-only Bambu connection attempt used the locally matched Bambu Studio profile in an isolated UFM candidate. TLS identity/profile matching succeeded after explicit fingerprint trust, but MQTT CONNACK returned `Not authorized`; no printer status or AMS report was obtained, `configure_bambu_printer` did not persist a printer/credential because it saves only after successful read, and no stock/ledger mutation or print occurred. A controlled in-memory diagnostic recorded only the response class.

The first Candidate17 UI surfaced `ProviderUnavailable` because `_on_disconnect` replaced the earlier precise `AuthenticationFailed` raised by `_on_connect`. The callback now preserves an already-classified error, with a regression test. Relevant suite: 158 passed and 59 subtests passed; Ruff and targeted mypy clean. Candidate18 was built from this source and manifest-verified (378 files), EXE SHA-256 `FA305F5DA99BFC70244943D68F22931EBB526FD6EA18B310186DB67494BF4698`, dev version `0.1.0.dev0`, unsigned; CycloneDX sidecar remains incomplete (401 components). Candidate18 is open on the PC against isolated `D:/UFM_TestCandidate16/Data`, still showing zero saved printers and spools.

**Blocker / next step:** the printer rejected the Studio-sourced LAN credential. Owner must verify LAN mode is enabled and refresh/confirm the LAN access code in Bambu Studio/printer settings; do not share the code in chat. Only retry after that change. Do not run print/control commands or enable automatic accounting. This live attempt did not verify AMS or external spool data. Public release remains NOT READY.


Graphify refresh for this checkpoint (2026-10-31): the root code graph was incrementally updated with the saved Graphify Python 3.14 interpreter (`graph.json`: 6,162 nodes / 17,953 edges; 141 changed/uncached code files extracted; unsupported files and files without AST symbols remain reported in Graphify output). The external source/requirement maps were deterministically refreshed after updating the checklist and source: UFM map 242 files / 6,134 nodes / 22,527 edges; Spoolman 298 / 4,920 / 15,554; UFM↔Spoolman 540 / 11,005 / 38,081; enriched combined graph 28,974 nodes / 85,612 edges, with source-hash manifests and snapshots retained. This is navigation/traceability evidence only, not runtime proof. The docs excluded from the graph's semantic corpus (`PROJECT_PROGRESS_UK.md`, `DEVELOPMENT_HANDOFF.md`) now carry this map checkpoint.

Root Graphify artifact check 2026-10-31: parsed current `graphify-out/graph.json` as 6,162 nodes, 17,953 raw `links`, and 10 hyperedges; cluster-only reported 276 communities and 17,412 simple edges for clustering (parallel endpoint links are retained in raw JSON). Hash comparisons against the refreshed external `source-manifest.json` passed for `bambu_lan.py`, `test_bambu_lan_provider.py`, and `INTEGRATION_CHECKLIST_UK.csv`. CSV retains UTF-8 BOM, 118 unique IDs; statuses remain 29 Done / 68 Partial / 20 Planned / 1 In progress.


## 2026-10-31 — Candidate18 ізольований UI та локальний облік

На Candidate18 (`D:/UFM_TestCandidate18/UFM Studio/UFM Studio.exe`) у тестовій теці `D:/UFM_TestCandidate16/Data` вручну створено профіль `UFM_TEST_PLA`, котушку `UFM_TEST_PLA_GREEN`, початковий залишок 500.000 г та ручне списання 1.000 г. Екран показав 499.000 г; історія містить обидві операції (`Початковий залишок`, `Коригування залишку`). На 1362×892 форму профілю та котушки можна було заповнити, а деталі/історію вибраної котушки видно праворуч. Дані навмисно тестові та ізольовані; цей smoke не торкався виробничої бази, принтера, HaspelSync чи реальних залишків. Тестова база залишена для ручного огляду. E14.01 лишається `Частково виконано`: один ПК/масштаб не замінює власницького приймання, DPI/клавіатурної доступності та інших станів UI.

Наявний повний source suite у цьому запуску завершився успішно: `.\.venv312\Scripts\python.exe -m pytest -q` — 664 passed, 491 subtests passed, exit 0 (87.78 s). Це доказ fixture/unit/integration suite, не hardware acceptance. Живе Bambu read-only підключення раніше отримало MQTT `Not authorized`; AMS не прочитано. Наступний Bambu retry лише після того, як власник локально перевірить LAN mode та оновить LAN code. Жодного тестового друку не запускали.

Checklist: UTF-8 BOM, 118 унікальних ID; 29 `Виконано`, 68 `Частково виконано`, 20 `Заплановано`, 1 `У роботі`. Release — NOT READY; автоматичне списання лишається вимкненим/fail-closed. Найближчий безпечний технічний крок: перевірити persistence/receipt→projection/event bridge та залишити нерозв’язані джерела ідентичності/подій/глобального writer fence як блокери, а не створювати витрату з невизначених даних.


## 2026-10-31 — Integration test fixture portability and fresh Graphify maps

Source diff in the nested `linked-stack/haspelsync` was reviewed without changing its Git configuration. Existing HaspelSync edits remain intact; the only new change for this stage is in `test/gcode.studiomapping.test.js`: `freshPrinter()` now directs the test logger to the temporary `LOG_DIR` established by first-import `test/helpers/tempdata.js`, replacing POSIX-only `/dev/null`. This avoids Windows `ENOENT: D:\dev\null` noise without altering HaspelSync runtime code or test semantics.

Verification: `node --test test/gcode.studiomapping.test.js` using Node v24.22.1 — 12 passed, exit 0. Remaining error-level log lines are intentional negative-path fixtures (no slice input and loopback FTPS connection refused at `127.0.0.1:990`); they do not access an actual printer or outside network. Full UFM source suite earlier this run: 664 passed and 491 subtests, exit 0.

CSV was updated in E08.07 and E11.03 as evidence only; statuses were not promoted. CSV retains UTF-8 BOM, 118 unique IDs, counts 29 Done / 68 Partial / 20 Planned / 1 In progress.

External deterministic Graphify refresh completed after the CSV and linked test fixture edits: traceability 739 files / 13,077 nodes / 45,125 edges; UFM map 242 / 6,134 / 22,527; Spoolman 298 / 4,920 / 15,554; Spoolman↔UFM 540 / 11,005 / 38,081; enriched graph 28,974 / 85,612. All five graphs were parsed and checked for unique node IDs and valid edge endpoints. Manifest SHA-256 matched the current CSV, `bambu_lan.py`, and `test_bambu_lan_provider.py`. This is source-navigation/traceability only. Root code graph was not rebuilt because UFM source files did not change.

**Resume:** continue the nearest source-verifiable integration task, but keep E11.03 partial: HaspelSync’s echo fixture helps confirm only the bounded `ams_mapping*` transfer semantics; it is not a stable run identity nor a UFM receipt/event-to-segment path. A fresh provider epoch/event counter on reconnect and missing original payload remain blockers. Keep production stock/debit disabled pending exact occurrence provenance and global writer fencing. Public release remains NOT READY.


## 2026-10-31 — Import retry after interruption + Graphify index reconciliation

Added an isolated importer integration case that injects a failure on the second spool after the first spool has been created and its opening stock recorded, then retries the same stable source key after physically moving/renaming the source DB file. Retry completes all three fixture spools; ledger still contains exactly the two expected opening-stock rows (350,000 mg and 799,448 mg), with no duplicate spool or stock entries. `tests/integration/test_spoolman_importer.py`: 9 passed; affected Ruff and targeted mypy clean. This is synthetic temporary SQLite evidence, not full import reconciliation against a real/legacy database. E04.08 moved from Planned to Partial; no other status promotion.

Reconciled the external Graphify overview Markdown against parsed current graph JSON: traceability 741 files / 13,089 nodes / 45,207 edges; UFM 244 / 6,147 / 22,612; Spoolman 298 / 4,920 / 15,554; UFM↔Spoolman 542 / 11,018 / 38,166; enriched 28,986 / 85,694. All five graphs have unique node IDs and all edge endpoints resolve. Manifest SHA matches current checklist CSV and the linked Haspel test fixture. Graph is navigation evidence only. Checklist remains UTF-8 BOM, 118 unique IDs: 29 Done / 69 Partial / 19 Planned / 1 In Progress.

Next: continue E04.08 with isolated snapshot reconciliation/legacy fixtures; then proceed by dependencies. Preserve all live data and keep auto debit fail-closed. Public release remains NOT READY: durable printer run identity, global writer fence, clean Windows install/signing/provenance/legal/SBOM, owner and hardware acceptance remain open.


## 2026-10-31 — Final verification after importer retry assertions

The interruption/retry test now also checks that the actual source SQLite file can be moved/renamed between attempts using the same source-instance key, that the completed mapping report contains every fixture spool (3) and filament (2), and that its source fingerprint equals the resumed preview fingerprint. After the final assertion: importer integration module 9 passed; Ruff clean; targeted mypy clean. Full UFM suite on the preceding test revision passed 665 tests + 491 subtests in 89.09s; the final change after that full run was limited to additional assertions in this same importer test, which was rerun successfully.

Final Graphify refresh follows the CSV and test changes. Current counts: traceability 741 files / 13,089 nodes / 45,207 edges; UFM 244 / 6,147 / 22,612; Spoolman 298 / 4,920 / 15,554; UFM↔Spoolman 542 / 11,018 / 38,166; enriched 28,986 / 85,694. Root graph 6,184 nodes / 18,011 raw edges. All five graph JSONs have unique node IDs and valid edge endpoints; manifests match current CSV and importer test SHA-256. CSV remains 118 unique IDs, BOM; statuses 29 Done / 69 Partial / 19 Planned / 1 In Progress.

Next: E04.08 full source-vs-target reconciliation and explicit interrupted-import recovery visibility. The current test proves deterministic retry, not atomic all-or-none import; a failure can leave a partial but resumable target. This remains a release concern to resolve before claiming a clean recovery UX. Public release remains NOT READY.


## 2026-10-31 — Interrupted-import recovery cue in both UIs

Changed the shared Spoolman source label formatter and both native source choosers (Studio and desktop): registered sources with no verified `snapshot_sha256` now carry a localized “snapshot unverified — review/resume” marker; chooser prompts clarify that this state can describe a legacy or interrupted import and reselecting the same source preserves stable IDs. Verified snapshots remain unmarked. The import algorithm, opening stock, backups, and source DB are unchanged. Added a focused pure label test; importer module 10 passed, Studio translation-placeholder contract 1 passed (72 deselected), Ruff clean, targeted mypy clean across importer/Studio/desktop/test, all three localization JSON files parse. This is UX guidance only, not a guarantee that arbitrary partial imports can be repaired or made atomic. E04.08 remains Partial.

Checklist stays 118 unique IDs with UTF-8 BOM; status totals unchanged at 29 Done / 69 Partial / 19 Planned / 1 In Progress. Source revision after this note requires the planned root/external Graphify refresh; do that before treating map hashes as current.


## 2026-10-31 — Full-suite and final graph refresh after recovery cue

The complete UFM suite on the current UI/source-label change passed: `pytest -q` — 666 passed, 491 subtests, 87.47 s, exit 0. The focused importer module (including interruption/moved-source/mapping fingerprint and unverified-label cases) passed 10; translation contract 1 passed / 72 deselected; Ruff and targeted mypy clean. No live printer, Spoolman service, production database, or print was used.

Final current Graphify counts after all source/resource/CSV changes: traceability 739 files / 13,085 nodes / 45,173 edges; UFM 242 / 6,143 / 22,576; Spoolman 298 / 4,920 / 15,554; UFM↔Spoolman 540 / 11,014 / 38,130; enriched 28,982 / 85,660; root graph 6,177 / 17,988 raw edges. Manifests and endpoint checks still need their final post-build verification in this checkpoint. E04.02 and E04.08 remain Partial.


## 2026-10-31 — Localization coverage completed in Graphify snapshot

The final external map check found `src/ufm/ui/i18n/en-US.json` and `uk-UA.json` were not in the previous source selection even though they were edited for the recovery cue. Extended `D:/graphify-out/bambu-ufm/tools/enrich_graph.py` to include all UFM UI locale JSON alongside `studio_strings.json`, then rebuilt the external maps. Final totals: traceability 741 files/13087 nodes/45175 edges; UFM 244/6145/22580; Spoolman 298/4920/15554; link 542/11016/38134; enriched 28984/85662. Exact current manifest SHA checks for checklist, retry test, Studio string registry, en-US and uk-UA all pass; all graph IDs unique and edge endpoints valid. Root code graph remains 6177 nodes/17988 raw edges; diagnostic has 0 dangling endpoints. Root graph is code-only; external map now hash-binds both locale catalogs.

Full test suite passed 666 tests + 491 subtests before the map-only change; targeted importer+locale tests and type/lint checks passed after the last source edit. Status totals remain 29/69/19/1 (118). E04.02/E04.08 Partial; release NOT READY.


## 2026-10-31 — Spoolman cutover detects target-only imported spools

Source review found `preview_spoolman_cutover()` only counted source rows that match/mismatch/miss in UFM; extra active target spools owned by that source-import device were invisible, so preview could report ready with source and target sets differing. Added `unexpected_count` from the exact source device's non-deleted spools minus deterministic expected IDs; cutover `ready` now requires zero extras. Studio evidence SHA payload and bilingual preview list “extra in UFM”. Focused cutover/import/translation selection: 12 passed / 72 deselected; Ruff clean; targeted mypy clean. Synthetic temp SQLite proves equal 3-row state passes, changed source fingerprint/balance gives one mismatch, and one extra UFM target spool blocks readiness. This does not detect a spool assigned under a different actor/device or prove live data integrity. E04.08 stays Partial.

Checklist remains 118 IDs/BOM and unchanged counts 29/69/19/1. Next run the full source suite and refresh Graphify after importer/UI/strings/CSV edits. Then continue E04.08 recovery/legacy scope; release not ready.


## 2026-10-31 — Verified full suite and graph after target-extra reconciliation

Full UFM source suite on the cutover reconciliation change: 667 passed, 491 subtests passed, 88.27s, exit 0. Focused selection: 12 passed/72 deselected; Ruff and targeted mypy clean. Final maps after code/resource/CSV edits: traceability 741 files/13089 nodes/45207 edges; UFM 244/6147/22612; Spoolman 298/4920/15554; link 542/11018/38166; enriched 28986/85694; root graph 6184/18011. External map includes studio_strings.json and both locale catalogs. Next verify hashes/endpoints for all maps and run graph diagnose; checklist 118 IDs/BOM, counts 29/69/19/1. E04.02/E04.08 remain partial; no release claim.


## 2026-10-31 — Final Graphify integrity and manifest verification

After the latest rebuild, all external graph JSONs pass unique-node and endpoint checks: traceability 741/13089/45205, UFM 244/6147/22610, Spoolman 298/4920/15554, link 542/11018/38164, enriched 28986/85692 (files/nodes/edges). Source-manifest SHA matches current checklist CSV, importer, Studio window, test, Studio strings, and both en-US/uk-UA locale catalogs. Root Graphify diagnose: 6184 nodes/18011 raw edges, 0 missing/dangling endpoints; 526 directed and 541 undirected same-endpoint collapses for clustering only. Checklist remains BOM/118 unique IDs, statuses 29 Done / 69 Partial / 19 Planned / 1 In Progress.

Validation state: full UFM suite 667 + 491 subtests passed; targeted change selection 12 passed, Ruff/mypy clean. Cutover reconciliation catches source-side changed/missing/mismatched and same-device extra target spools; external actor/device extras, import partial-row isolation, hardware/live acceptance remain unverified. Public release remains NOT READY.


## 2026-10-31 — E04.06 current-balance checkpoint evidence

Reviewed the importer source and existing fixture: `_load_rows()` computes a single current remainder as source `initial_weight` (fallback to filament nominal weight) minus source `used_weight`, rejects negative results, and creates only that remaining amount as a stable-keyed idempotent opening-stock entry. The focused test passed (1); it checks 799448 mg and 350000 mg rather than source full nominal weights 1000000/750000 mg. The full current suite in the preceding stage passed 667 tests + 491 subtests. This proves local fixture arithmetic and repeat safety only; historical transactions are not imported and real/legacy DB acceptance is absent. E04.06 moves from Planned to Partial. Checklist: BOM, 118 IDs; 29 Done / 70 Partial / 18 Planned / 1 In Progress. Graph traceability must be refreshed after this CSV status/evidence update.

## 2026-10-31 — Read-only partial-import reconciliation

Added `preview_spoolman_import_recovery()` in `src/ufm/integrations/spoolman/importer.py`. It is restricted to a registered source whose final `snapshot_sha256` is still absent, produces a source-to-target spool count comparison, and always fails closed for cutover readiness. The interrupted-import fixture verifies 1 matched / 2 missing / 0 mismatch / 0 same-device extras, followed by retry after moving/renaming the source DB and confirms stable mappings plus two opening-stock ledger rows total. The completed-source guard is verified in the cutover fixture. Importer module: 11 passed; Ruff and targeted mypy clean.

E04.08 remains Partial: the diagnostic is not yet surfaced in Studio/desktop, source-side table/database integrity beyond existing loader checks and unrelated-owner target extras remain outside attribution, and no real/legacy dataset acceptance was performed. No user DB, live Spoolman, printer, production stock, or print touched. Release remains NOT READY. Checklist is BOM-preserved with 118 unique IDs; counts are recorded in this checkpoint by the current CSV audit.

Next: integrate the read-only recovery report into the source-selection/retry UX (keep the UI responsive and identical in Studio/desktop), add localized report strings and UI contract coverage, then run focused and full isolated tests and refresh both Graphify snapshots/manifests.

## 2026-10-31 — Recovery counts integrated into source selection

The import preview now computes read-only reconciliation counts for registered sources without a final snapshot SHA and both Studio/desktop source choosers display them in Ukrainian/English: matched/total, mismatch, missing, extra. The recovery API remains unavailable for completed snapshots and never returns `ready=True`; these counts guide the same-key retry only. Comparison uses one filtered target query to avoid N+1 reads. Targeted importer + Studio UI tests: 84 passed; full UFM suite: 667 passed and 491 subtests in 87.13s; Ruff and targeted mypy clean. Checklist integrity: 118 unique IDs; UTF-8 BOM retained; statuses: 29 Виконано / 70 Частково виконано / 18 Заплановано / 1 У роботі.

E04.08 remains Partial: no real/legacy database acceptance, same-import-device extras are attributable but records owned by another actor/device cannot be mapped to this import key, and UI was covered by integration tests rather than manual visual/runtime acceptance. No live Spoolman, UFM user DB, printer, hardware or print was accessed. Release remains NOT READY.

Next: rebuild root Graphify after importer/test/UI/locale changes and rebuild the external Bambu↔UFM traceability manifests so they bind current hashes; validate unique node IDs/endpoints, CSV BOM/counts and map summary. Then move to the next unfinished integration step under the recorded plan.

Graph refresh after these changes: root 6199 nodes / 18052 raw edges; traceability 741 files / 13096 nodes / 45253 edges; UFM map 244/6154/22658; Spoolman 298/4920/15554; link 542/11025/38212; enriched 28993/85740. All graph IDs unique and endpoints valid; manifest SHA matches checklist, importer, Studio, desktop, strings, locales and importer test.

## 2026-10-31 — Import confirmation snapshot guard

Both Studio and desktop now pass the source fingerprint rendered in the preview into the Spoolman importer. It re-reads and compares normalized imported fields before creating app paths, making backups, or writing inventory; a changed source rejects the stale confirmation. A temporary SQLite regression mutates used_weight after preview and verifies that no UFM data directory is created. Targeted importer + Studio tests: 85 passed; full suite: 668 passed + 491 subtests in 89.25s; Ruff and targeted mypy clean. No production database/service or hardware was used.

E04.08 remains Partial because the confirmation guard does not prove live/legacy acceptance, external-owner attribution, or full UI visual acceptance. Recovery counts can become stale after preview; the fingerprint guard prevents their stale associated confirmation from mutating data. Checklist: 118 unique IDs, UTF-8 BOM; 29 Done / 70 Partial / 18 Planned / 1 In Progress. Release remains NOT READY.

Next: refresh root and external Graphify maps after code, tests, UI/resources and checklist evidence; validate manifests/endpoints/counts; then continue the next unblocked plan item. Auto-debit disabled; no commit/push/deploy.

Final Graphify after stale-preview guard: root 6203 nodes / 18061 raw edges; traceability 741/13098/45265; UFM 244/6156/22670; Spoolman 298/4920/15554; link 542/11027/38224; enriched 28995/85752. All six maps validated for unique IDs and resolvable endpoints. Current source SHA checks include checklist, importer, Studio/desktop, string registry, both locale catalogs and importer tests.

## 2026-10-31 — Current-source UI screenshot review

Captured and inspected current-source Studio at 1360x856 with Qt offscreen using only the isolated synthetic incomplete-import fixture under the Windows temp directory. The Filament workspace, summary cards, filters/actions, table and detail inspector fit the captured viewport without clipping; one synthetic fixture spool appeared. No production data, printer, Bambu/Spoolman service, user shortcuts or real stock were touched. This does not verify the recovery chooser itself, physical DPI scaling, keyboard/focus, resizing, other tabs or owner acceptance. E14.03 stays Partial; its CSV evidence was updated.

## 2026-10-31 — Moved Spoolman file default selection guard

E04.02 source selection now uses one shared helper in Studio and desktop. A path-derived key match remains the default; when a moved file does not match by path and exactly one registered source exists, the chooser selects that stable source key. If multiple candidate sources exist, it does not guess and requires explicit user choice. Four cases are covered: exact match, sole moved source, ambiguous sources, empty source list. E04.02 remains Partial until controlled legacy move acceptance.

The expanded importer + Studio selection passed 86 tests; full UFM suite passed 669 tests plus 491 subtests in 83.35 seconds; Ruff and targeted mypy clean. No live Spoolman/production database, printer, network stock update, physical print or deploy. Checklist is BOM-preserved with 118 unique IDs; counts remain 29 Done / 70 Partial / 18 Planned / 1 In Progress. E04.08/E04.02 remain Partial; public release NOT READY.

Next: refresh root and external Graphify from these source/checklist changes, validate manifests and endpoints, then continue to another unmet dependency. Manual import-dialog visual acceptance is still open.

Final Graphify after moved-source selection: root 6211/18076 raw nodes/edges; traceability 741/13103/45291; UFM map 244/6161/22696; Spoolman 298/4920/15554; link 542/11032/38250; enriched 29000/85778. All maps pass unique-node/valid-endpoint checks; current manifest matches CSV, importer, both UIs, strings/locales and importer tests.

## 2026-10-31 — Import ID-map integrity proof

E04.03 fixture now independently recomputes mapping_sha256 from canonical sorted JSON, verifies an edited UFM ID breaks the digest, and confirms the mapping report contains no source database path. Combined with the interrupted/moved-source retry, it validates deterministic spool/filament mappings and resumability on synthetic SQLite. Full UFM suite: 669 passed / 491 subtests in 83.97s; targeted importer/Studio 86 passed; Ruff and targeted mypy clean. E04.03 remains Partial because renamed external IDs/aliases and real/legacy acceptance are absent. Checklist remains BOM / 118 unique IDs, statuses 29 Done / 70 Partial / 18 Planned / 1 In Progress.

Next: refresh Graphify for test/CSV changes; validate hashes/endpoints. Continue the next highest-priority unfinished import/integration requirement. Release NOT READY; no user data, live service, printer, hardware or deployment.


## 2026-10-31 — HaspelSync journal preview coverage

Added isolated unit coverage for the existing read-only HaspelSync cutover preview (`tests/unit/test_haspel_cutover_preview.py`). Five checks pass for printer-scoped booking states, global weighing states, readiness gating, malformed/inconsistent journal rejection, and digest sensitivity; Ruff passes. The test uses only temporary JSON files and does not read live journals or change stock. E04.05 is now Partial because the preview path is evidenced; historical ledger import is still unimplemented. It depends on stable spool-ID mapping, exact-once ledger semantics and E03.06/E03.07 single-writer ownership controls. Current test evidence does not establish full-suite status after this test-file addition.

Root and external Graphify maps were rebuilt; all map JSONs have unique node IDs and resolvable edge endpoints, and source-manifest SHA matches checklist, importer, both UI modules/locales, and both relevant importer/Haspel test files. Release remains NOT READY. Next: review E04.05's import transaction design alongside E03.06/E03.07 before adding any ledger writer; continue only with isolated fixtures until ownership and historical-baseline semantics are established. No production data, printer, print, deployment, commit or push touched.


Full-suite follow-up: after adding the HaspelSync journal preview tests, `.venv312/Scripts/python -m pytest -q` completed with **674 passed, 491 subtests passed, exit 0 (85.05s)**. The five new tests are included. No test targets real database files, live Spoolman, printer, physical print, or stock mutation. Checklist status totals remain 29 Done / 71 Partial / 17 Planned / 1 In Progress (118 unique IDs; UTF-8 BOM).


## 2026-10-31 — Local printer discovery console regression

During the explicitly requested local-PC smoke of the Devices view, bounded read-only private-LAN discovery rendered two unverified candidates (one possible Bambu and one OctoPrint). No authentication, printer state, AMS, printer command, stock mutation, or print was performed. The operation briefly showed a PowerShell console over UFM; `src/ufm/integrations/printers/discovery.py` now sets `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)` for the Windows route query. Regression coverage asserts the flag: `tests/integration/test_printer_discovery.py` — 9 passed; Ruff clean. E14.01 evidence updated but remains Partial; E14.03 remains Partial. This only verifies one Windows UI configuration and a bounded discovery operation, not authenticated connection, AMS or hardware command behavior. Release remains NOT READY.

Full-suite follow-up for this Windows discovery fix: `.venv312\Scripts\python.exe -m pytest -q` — 674 passed, 491 subtests passed, exit 0 (82.96s). Focused printer discovery module: 9 passed; Ruff clean. The change is limited to suppressing the PowerShell child console when the OS exposes `CREATE_NO_WINDOW`.

Graph refresh after source/test/checklist/doc edits: root Graphify 6,230 nodes / 18,129 links; external traceability 13,124/45,394; UFM 6,182/22,799; Spoolman 4,920/15,554; UFM↔Spoolman 11,053/38,353; enriched 29,021/85,880; combined 15,897/40,276. All seven graphs have unique node IDs and zero dangling links. Traceability SHA manifest has 742 entries and matches discovery source, printer-discovery test, and checklist. Checklist remains 118 unique IDs with BOM; status counts unchanged at 29 Done / 71 Partial / 17 Planned / 1 In Progress. Release remains NOT READY.

Map follow-up after recording final full-suite proof in the BOM checklist: regenerated source, standalone UFM/Spoolman/link and enriched maps. Final map integrity/hash audit: all 7 JSONs have unique IDs and 0 dangling links; manifest matches current checklist, changed discovery source and test. Final counts: root 6230/18129; traceability 13124/45394; UFM 6183/22800; Spoolman 4920/15554; link 11054/38354; enriched 29021/85880; combined 15897/40276.


## Windows Devices view: readable discovery results

Manual PC inspection surfaced raw Python tuple output after network search. Studio now renders a localized line per candidate (provider/host, port, identified vs unverified) and uses a localized safe error for an unexpected result shape. Regression checks cover identified and possible Bambu candidates; translation placeholder contract passes. Targeted UI/translation: 2 passed. Full suite initially showed 675/491 then exit 1 without a reported test failure; repeat with captured log: 675 passed, 491 subtests passed, exit 0 in 83.50s. Ruff and JSON parse clean. E14.01 remains Partial; no auth or device state verified.


Latest current-source Windows UI smoke: launched `.venv312` Studio with isolated data at `D:/UFM_TestDiscoveryReview`, Devices tab at 1360×892. The local search result now presents one OctoPrint candidate and one possible Bambu candidate as separate readable lines, including port and explicit unverified warning; no console covered the window. This remained unauthenticated candidate detection only; no printer connection/state/AMS, credential handling, saved profile, production stock or print. E14.01 evidence updated in CSV but stays Partial. The isolated source app is left open on the Devices tab for user inspection.


Final validation after the readable discovery UI patch: `.venv312\Scripts\python.exe -m pytest -q` — 675 passed, 491 subtests passed, exit 0 (83.50s); selected UI + translation contract 2 passed; printer discovery 9 passed; Ruff and JSON parse clean. Current source UI was launched on Windows in isolated `D:/UFM_TestDiscoveryReview`; at 1360×892 its Devices page displayed two candidate rows as readable localized lines with port and explicit unverified confidence, and no console overlay. No printer was authenticated or configured; no status/AMS query, write, print, or stock debit occurred.

Latest graph integrity and hashes: root 6,233 nodes / 18,135 links; traceability 742 source files, 13,126 nodes / 45,401 edges; UFM 245/6,185/22,807; Spoolman 298/4,920/15,554; link 543/11,056/38,361; enriched 29,021/85,880; combined 15,897/40,276. All seven maps have unique IDs and zero dangling links; manifest matches discovery/provider/UI/locales/tests and current BOM checklist. Checklist: 118 unique IDs, status counts unchanged 29 Done / 71 Partial / 17 Planned / 1 In Progress. E14.01 remains Partial; broader integration and hardware acceptance remain open; release NOT READY.


## Read-only Bambu LAN identity probe

The isolated current-PC test called `identify_bambu_printer()` against the already discovered local candidate. It successfully read the TLS certificate identity and classified the device as Bambu Lab P1S. Fingerprint and root chain remained in memory only; no full fingerprint or certificate was written. This is pre-auth identity discovery, not an authenticated printer connection. No access code, MQTT telemetry, AMS slots, profile persistence, command, print or inventory change. Checklist E06.02 remains Partial pending owner-controlled certificate trust and LAN-code entry, then a read-only authenticated state/AMS verification.


Graph refreshed after recording the pre-auth identity read in E06.02: root 6,233/18,135; traceability 13,126/45,401 (742 files); UFM 6,185/22,807; Spoolman 4,920/15,554; UFM↔Spoolman 11,056/38,361; enriched 29,021/85,880; combined 15,897/40,276. All 7 graph JSONs have unique IDs and zero dangling links; SHA manifest matches current CSV, UI/provider/locales and tests. No production or secret bytes were included.

## 2026-10-31 — Portable Candidate launch and four-tab smoke

Built internal portable package at `D:/UFM_TestBuild_20261031/UFM Studio`. Manifest verification passed for 374 bundle files; EXE SHA-256 `855FA23E6F49F69F9701E5CBD091A6B7584F9EB09CF0DBC906642B38E4C91881`. Launched the EXE with separate empty data directory `D:/UFM_TestBuild_20261031/Data`. UI automation confirmed the Filament, Materials, Devices and System pages. Empty Filament shows 0 spools, 0.000 g and 0 configured printers; Materials explains profile/import startup; Devices rendered two unverified candidates after bounded local discovery; System explicitly states this is an internal test build and release is not accepted pending full SBOM, signing and Windows/device acceptance. No credentials, authenticated printer state/AMS, commands, print, user DB or stock mutation.

This establishes package-startup and page-render smoke on this PC only. It does not establish real workflow completion, owner/DPI/accessibility acceptance, clean Windows, install/reinstall, signature or release readiness. Checklist stays 118 IDs: 29 Виконано / 71 Частково виконано / 17 Заплановано / 1 У роботі; E14.01 and E16.01 remain Partial. Next: resume isolated integration verification; authenticated Bambu read still needs operator certificate review and manual LAN-code entry. Keep release NOT READY and automatic estimated debit disabled.

## 2026-10-31 — Localized Bambu candidate naming

The portable build's live Devices search exposed the English suffix `(possible)` embedded in the Bambu provider name, duplicating the already localized confidence warning. `PrinterCandidate.name` now says `Bambu Lab`; confidence remains explicitly unverified in the UI. Regression check asserts the English suffix is absent. Targeted printer-discovery plus Studio display tests: 10 passed; Ruff clean; mypy clean for the two production modules. A broader exploratory mypy invocation including `tests/integration/test_studio_window.py` reports 211 diagnostics in that large test file (mostly missing annotations and Qt stub mismatches); it was not altered. E14.01/E14.02 remain Partial.


## 2026-10-31 — Qt UI teardown stability and localized portable candidate

Fixed a Qt test lifecycle leak in `tests/integration/test_studio_window.py`: the secondary `StudioWindow` used to verify persisted column settings is now closed, scheduled for C++ deletion, and its `DeferredDelete` event is drained before the temporary SQLite engine is disposed. Evidence: the specific regression scenario passed (1, exit 0); `tests/integration/test_studio_window.py` passed 74 tests (exit 0); the project-scoped full suite passed 675 tests + 491 subtests in 84.78s (exit 0). Ruff passed for `src tests`; mypy passed all 139 source files. A first full-pytest invocation accidentally used `D:\` as root and collected external Graphify/site-packages; it was stopped at collection with no project test assertions, and the valid rerun explicitly scoped pytest to this project.

The latest isolated portable candidate was rebuilt and launched with a separate test data path; its 374-file manifest verified, EXE SHA-256 `EA3414AF918CA194D8B8FF59ED291F3475219E80E235852E4E5728A962512877`. The Devices view displayed localized `Bambu Lab` and explicit unverified status. No credentials, authenticated state, AMS, control, print or inventory mutation.

CSV remains 118 unique IDs with BOM; all step statuses remain 29 Виконано / 71 Частково виконано / 17 Заплановано / 1 У роботі. E14.04 stays Partial because this resolves only the discovered teardown instability; long-operation performance/recovery and owner/hardware checks are open. E14.01/E16.01 remain Partial; the internal candidate is not a release installer. Release NOT READY.

Next: refresh and validate root + external Graphify after this test/CSV/doc update, then continue an isolated integration item. Authenticated Bambu MQTT/AMS read requires the owner to review certificate identity and manually enter the LAN code in UFM; do not automate credential collection. No production data, printer command, stock debit, commit, push or deployment.


## 2026-10-31 — Localized safe printer-monitor diagnostics

E06.05 code gap closed in part: `StudioWindow.printer_monitor_failed()` now maps the known monitor failures (authentication, TLS verification, unavailable provider, unsupported capability, invalid observation, bounded event-buffer overflow) to concise Ukrainian/English explanations. Unknown exception class names/details are suppressed to a generic localized explanation, so LAN codes, file paths or diagnostics are not echoed. Added `test_studio_monitor_failure_messages_are_localized_and_do_not_expose_raw_errors`, covering every mapped error plus a credential/path-like unknown sentinel in both languages. Targeted locale+UI checks: 2 passed; Ruff clean for changed source/test; mypy clean for `studio_window.py`; JSON valid (464 keys). Full project-scoped suite: 676 passed + 491 subtests, exit 0 (84.49s).

E06.05 remains Partial: actual Bambu status, AMS/external-holder readings and hardware acceptance still require operator-owned LAN-code/certificate step. No real printer connection, command, print, stock mutation or credentials were used in this change. E14.02/E14.04 remain Partial; complete locale and accessibility/owner acceptance still open. Checklist is BOM/118 unique IDs; statuses unchanged (29 Done / 71 Partial / 17 Planned / 1 In Progress).

Next: refresh the current root Graphify for source/test/locale changes and validate graph integrity; external Spoolman/Bambu maps stay navigation snapshots and do not prove runtime. Then continue the highest-priority safe integration gap; release remains NOT READY.

## 2026-10-31 — Стан пошуку LAN і очищення застарілих кандидатів

Під час пошуку кнопки вкладки «Пристрої» блокуються, але старі рядки кандидатів лишалися у полі до відповіді worker-а. Додано двомовний стан «Шукаю пристрої…», який встановлюється перед стартом задачі; після завершення поле замінюється актуальними кандидатами, empty-state або безпечним повідомленням помилки. Регресійний тест перевіряє, що worker бачить стан пошуку замість старого кандидата та що для порожнього результату показано коректний empty-state. Вибіркові UI discovery перевірки: 2 passed; Ruff чистий для двох змінених Python-файлів; `studio_strings.json` парситься.

На відкритій тестовій збірці локальний scan завершився й повернув інтерфейс у «Готово». Поле вже мало два непідтверджені результати до цього повторного натискання, тому саме цей повтор не рахується новим доказом виявлення пристроїв. Жодних LAN-кодів, автентифікованого стану/AMS, команд принтеру, друку або списання не виконано. CSV E14.01 лишається «Частково виконано»; повне мережеве/власницьке приймання й перевірка широких UI-сценаріїв залишаються відкритими. Release NOT READY.

Наступне: зібрати окремий portable internal candidate зі зміненими UI/тестом; звірити маніфест і відкрити на ПК для smoke-перевірки. Потім оновити root Graphify і traceability SHA після CSV та docs. Не перезаписувати раніше відкриті тестові збірки; не торкатися production DB.

Candidate launch result, 2026-10-31: built `D:/UFM_TestBuild_20261031_DiscoveryUX/UFM Studio`; 374-file manifest verified; EXE SHA-256 `1D2D7AE03450DA2D077A4484CF2545A6A19362653F7F1913AC823646B29CF1A4`. Launched on this PC with a new isolated data root and confirmed the resolved path in System. On Devices, immediate screenshot after search showed the new Ukrainian “Шукаю пристрої…” message while all controls were disabled; the scan subsequently returned to `Готово` and displayed two unverified candidates (Bambu and OctoPrint). No credentials or printer state/AMS were accessed; no command, print, production DB or stock change. Full suite 677 passed + 491 subtests, Ruff clean, mypy 139 source files clean. The candidate is left open on System for review. Release remains NOT READY.

## 2026-10-31 — Local cutover authority rechecked at commit

Added two isolated safeguards to the calculated-finalization integration suite: a REVIEW_ONLY printer authority rejects estimated usage with no writes; and switching from UFM_ACTIVE to REVIEW_ONLY while the calculation worker is running prevents the final transaction from changing the ledger, job or receipt. The authority tests passed (2/2). Full project-scoped suite: 679 passed + 491 subtests, exit 0 (83.88s); Ruff clean for the changed test module.

This confirms only UFM's local persisted authority check at the commit boundary. It does not fence a separate HaspelSync process: linked `mqtt.js:processSlot()` still directly PATCHes Spoolman remaining weight and does not register in the same durable in-flight gate. Shared writer arbitration, process/DATA_DIR exclusion and ambiguous remote write recovery remain E03.07 blockers; automatic debit stays disabled. CSV E03.07 remains Partial, BOM/118 unique IDs preserved.

Next: refresh current root Graphify and external source traceability after the test/checklist/docs change; validate every graph JSON's node IDs/endpoints and the 742-source snapshot hashes. Then continue the next unblocked integration item; do not treat local authority tests as printer/production acceptance.

## 2026-10-31 — Fail-closed writer authority regression and map integrity

Two isolated calculated-finalization tests now guard the local owner boundary: REVIEW_ONLY rejects an estimated debit without writes, and a transition from UFM_ACTIVE to REVIEW_ONLY during the async calculation prevents the later local commit. Both tests passed. Complete project-scoped pytest: 679 passed + 491 subtests, exit 0 in 83.88s; Ruff clean for the changed test. This does not prove a shared gate with other Haspel processes: linked `mqtt.js:processSlot()` still PATCHes Spoolman remaining weight outside UFM's local authority table, so remote writer fencing, duplicate process/DATA_DIR exclusion, lost-response recovery and reconciliation remain release blockers. Keep auto-debit disabled.

Root Graphify refreshed for the test change: 6274 nodes / 17383 links. External traceability/project maps were refreshed from the current selected source snapshot; all 9 JSON graphs have unique IDs and zero dangling endpoints; the 742-entry SHA manifest matches changed Studio source/strings, tests, BOM checklist and handoff (the separate project progress file is not included in that external manifest). Current exact graph counts and snapshot hashes: `D:/graphify-out/bambu-ufm/PROJECT_MAPS_UK.md` and `traceability/graphify-out/source-manifest.json`. Graphs remain navigation evidence, not runtime proof. CSV remains BOM/118 unique IDs, status counts unchanged: 29 Done / 71 Partial / 17 Planned / 1 In Progress. E03.07 remains Partial; release NOT READY.

Next safe work: inspect the next unblocked connector/test acceptance gap. Authenticated Bambu state/AMS still needs owner-reviewed TLS identity and manual LAN-code entry. Continue using the open isolated DiscoveryUX candidate for manual UI review; do not enter/collect secrets automatically. No production DB, print, printer control, inventory debit, commit, push or deployment.


## 2026-10-31 — Перевірка UFM↔HaspelSync authority/booking зв’язку

Перевірено обидва боки локального контракту на ізольованих тестових фікстурах: `.venv312/Scripts/python -m pytest -q tests/unit/test_haspel_authority_client.py tests/unit/test_haspel_cutover_preview.py` — 15 passed + 4 subtests; у `linked-stack/haspelsync` `node --test test/bookings.test.js` — 16 passed. Покриті читання/валідація authority snapshot та booking журналу, revisioned owner transfer, блокування Haspel списання до HTTP write після передачі власника, unresolved intents, повтор/невизначений HTTP результат. Live принтер, Spoolman production, користувацькі credentials та склад не зачіпались.

Межа доказу: це HaspelSync service-level gate, а не спільний міжпроцесний/між DATA_DIR distributed lock; інші процеси Haspel/Spoolman можуть бути поза ним. E03.07 залишається Частково виконано, UFM auto-debit вимкнено. Чекліст — 118 унікальних ID, BOM збережено; статуси без зміни: 29 Виконано / 71 Частково виконано / 17 Заплановано / 1 У роботі. Наступне: повний ізольований linked HaspelSync suite, потім повторно оцінити контрольовану інтеграційну межу; Graphify оновити після цього етапу. Release NOT READY.


## 2026-10-31 — HaspelSync stale authority cache guard

У `linked-stack/haspelsync/src/bookings.js` authority та booking тепер перечитуються з durable JSON перед перевіркою власника і початком списання. Регресія в `test/bookings.test.js` імітує довгоживучий процес зі старим `LEGACY_ACTIVE` після передачі власника іншим процесом; тест перевіряє відмову до HTTP-запиту. Фокусований набір: 17 passed. E03.07 частково виконано: це усуває послідовне stale-cache вікно для спільного `DATA_DIR`, але не вирішує одночасні паралельні записи, окремі `DATA_DIR` або сторонніх Spoolman writers. Наступне: повторити повний HaspelSync suite; потім перезібрати й перевірити графи/manifest. Auto-debit залишається вимкненим; production не зачіпався.


## 2026-10-31 — Повний HaspelSync suite після stale-cache guard

Повторний повний suite після зміни `linked-stack/haspelsync/src/bookings.js`: `node --test --test-reporter=tap test/*.test.js` — 794 tests, 791 pass, 0 fail, 1 skipped, 2 todo, exit 0 (22.34s). Два TODO — A2L fixture: чотири AMS08 слоти від unit 16 мають label `Z` (однакові), отже формат не підтриманий. Не додав mapping навмання: ці labels є стійкими ключами збережених призначень. Інтеграція authority показує fail-closed передачу у межах одного HaspelSync DATA_DIR і refresh проти послідовного stale process cache; атомарний multi-process writer lock усе ще не існує/не підтверджений. E03.07 і E06.06 лишаються Частково виконано. Чекліст BOM збережено, 118 унікальних ID: 29 Виконано / 71 Частково виконано / 17 Заплановано / 1 У роботі. Наступне: оновити root та external Graphify на поточних source/checklist hashes і перевірити endpoints; потім перейти до наступної доступної безпечної інтеграції. Release NOT READY; production/printer/credentials/stock не використовувалися.


## 2026-10-31 — Локальні тести конекторів Bambu/Spoolman

Синтетичні/ізольовані набори `test_bambu_network_autofill.py`, `test_bambu_studio_import.py`, `test_bambu_lan_provider.py`, `test_spoolman_importer.py`, `test_spoolman_preview.py`: 64 passed + 45 subtests, exit 0. Вони перевіряють розбір оголошень без access code, fail-closed конфігурацію та TLS/provider, AMS normalization, import ID-map/source selection і preview/Cutover на mock/temp fixtures. Живе мережеве автентифіковане читання принтера, production Spoolman, реальні профілі чи зміни складу не перевірялися. E04.01/E04.03/E06.02/E06.05 частково виконані; manual LAN-code/certificate acceptance залишається потрібним.


## 2026-10-31 — Shared DATA_DIR journal lock у HaspelSync

Посилено `linked-stack/haspelsync/src/bookings.js`: всі durable мутації журналу (booking begin/finish/resolve та authority transfer) виконуються під ексклюзивним суміжним lock-файлом, і fresh journal load відбувається всередині lock. Зайнятий lock відхиляє booking до HTTP списання і забороняє зміну owner. Crash залишає lock fail-closed; автоматичного stale-lock видалення немає. Перевірки: `node --test test/bookings.test.js` — 18 passed; повний `node --test --test-reporter=tap test/*.test.js` — 795 tests, 792 pass, 0 fail, 1 skipped, 2 TODO, exit 0 (22.30s).

Межі: lock працює тільки з однаковим точним DATA_DIR/bookingsPath і lock-aware версіями; старі binaries, інші DATA_DIR та інші Spoolman writers залишаються поза fence, а перехід UFM↔Haspel не є distributed transaction. E03.07 Partial; auto-debit вимкнено. Відомі два Haspel A2L TODO не змінено через відсутність підтвердженого, сумісного зі збереженими слот-ключами mapping. Чекліст BOM та 118 IDs збережені. Наступне: зовнішня/локальна точка відновлення для stranded lock і операторське підтвердження; після цього — final Graphify hash/endpoints refresh.


## 2026-10-31 — Graphify checkpoint після shared journal lock

Root UFM code-only Graphify перебудовано після HaspelSync lock/test: 6,275 вузлів / 17,389 зв’язків; 49 non-code items (46 docs/3 images) збережено без повторної semantic extraction. Зовнішні maps перебудовано: traceability 742/13,139/45,457; UFM 245/6,197/22,856; Spoolman 298/4,920/15,554; UFM↔Spoolman 543/11,068/38,410; enriched 29,036/85,944; Bambu source 12,955/32,565; profiles 2,942/7,711; combined 15,897/40,276. Integrity/hash check пройшов: 9 графів, 0 duplicate IDs, 0 dangling endpoints; current hashes збіглися для bookings source/test, authority client, CSV, ADR та handoff. Перевірка виявила, що traceability manifest не містить PROJECT_PROGRESS_UK.md — це обмеження зафіксовано в зовнішній карті.

Цей запис оновлює handoff, тому зовнішню traceability треба один раз повторно перебудувати й перевірити після цього запису. Далі: фінальний source hash/endpoints audit; потім наступна безпечна інтеграційна прогалина. Release NOT READY; auto-debit вимкнено.


## 2026-10-31 — Повний локальний набір і read-only discovery smoke

Повторний ізольований запуск `.venv312\Scripts\python.exe -m pytest -q tests` показав 679 passed і 491 subtests passed за 84,36 с. Обгортка запуску не зберегла окреме поле exit code; у видимому підсумку помилки/Qt crash не з’явилися, але це не стирає раніші зафіксовані Windows Qt teardown AV. На відкритій ізольованій збірці DiscoveryUX натиснуто лише «Знайти у локальній мережі»: UI показав два непідтверджені кандидати; автентифікації, читання AMS, збереження профілю принтера, моніторингу, команд керування, виробничої БД чи списання не було. Вкладки «Філамент», «Матеріали», «Пристрої» оглянуті при 1360×890; база котушок у цьому ізольованому Candidate порожня. Це внутрішній smoke, не власницьке/clean-Windows приймання.

E06.02 лишається Частково виконано: потрібно окремо завершити модель/serial/TLS і LAN-code credential flow та зафіксувати read-only state/AMS acceptance за дією оператора. E16.08 лишається Частково виконано через історичні Qt process-exit AV та відсутність public signing/SBOM/clean-install acceptance. Checklist: 118 унікальних ID, BOM збережено; статуси без зміни: 29 Виконано / 71 Частково виконано / 17 Заплановано / 1 У роботі. Наступне: перед persistent credential linking отримати action-time згоду, прив’язану до UFM test build та вибраного пристрою; після цього виконувати лише read-only verify. Auto-debit вимкнено.


## 2026-10-31 — Bambu autofill regression та Windows firewall checkpoint

Фокусований повторний набір `.venv312\Scripts\python.exe -m pytest -q tests/integration/test_bambu_network_autofill.py tests/integration/test_studio_window.py` завершився: **83 passed, 9 subtests, exit 0**. У відкритій ізольованій збірці мережеве автозаповнення викликало системний запит Windows Firewall, що пропонує доступ одночасно для приватних і публічних мереж. Дозвіл не надано; форма залишилася в стані очікування мережевої операції. Це не доводить дефект Bambu адаптера: live identity/TLS крок не завершився через невирішений системний дозвіл. Код LAN, постійні секрети, профіль, AMS, команди принтера, облік і production дані не торкалися. Продовження потребує рішення про доступ лише в приватній мережі або відмову; прийняття широкого public-network винятку не є необхідним. E06.02 та release gate лишаються частковими.

## 2026-10-31 — Checkpoint at weekly usage threshold

Focused Bambu autofill/UI regressions: `tests/integration/test_bambu_network_autofill.py` plus `tests/integration/test_studio_window.py` — 83 passed, 9 subtests, exit 0. Windows Firewall requested an app exception covering private and public networks; no grant or TLS trust was accepted, and the read-only identity dialog remains pending. No LAN code, stored credential, printer profile, authenticated state/AMS read, command, print, production DB, or stock/debit change.

After the documentation update, external Graphify `enrich_graph.py` completed with traceability 742 files / 13,139 nodes / 45,459 edges. Usage check after this stage: primary 36% remaining, weekly 15% remaining. Work is paused at the configured threshold. **Resume point:** after both usage windows exceed 15%, rerun the external map pipeline in order: `project_maps.py`, then `combine_enriched.py`; validate all graph node IDs/endpoints and latest docs/source hashes, then append map metrics and refresh the project checkpoint. Current release remains NOT READY; E06.02 Partial.


## 2026-10-31 — Candidate BambuFix1: TLS/autofill regression і локальний smoke

Виправлено класифікацію `FileNotFoundError` під час створення TLS-контексту в `bambu_studio.py` та завислий індикатор в async ідентифікації: тепер з’являється локалізована порада перевірити мережу або ввести адресу вручну. Цільові перевірки `test_bambu_network_autofill.py` + `test_studio_window.py`: 85 passed, 9 subtests, exit 0; Ruff clean; `studio_strings.json` валідний JSON (466 ключів).

Портативний внутрішній кандидат `D:\UFM_TestBuild_20261031_BambuFix1\UFM Studio`: `build-manifest.json` перевірив 374 файли; source provenance має 180 inputs і збігається з поточним source tree; EXE SHA-256 `FA91FEED3F0F5388A5369DC04AF19C7E831923131E097D42E5F959B904F05A17`. Повторний offscreen startup/capture завершився кодом 0 із окремим `D:\UFM_TestBuild_20261031_BambuFix1_Capture\Data`; знімок `Review/startup.png` показує порожню ізольовану базу й вимкнені дії без вибраної котушки. Це не live-printer acceptance.

Спроба створити для нового EXE точкове правило лише Private відхилена ОС з `Access denied`; правило не створено і Public не відкривався. Тому мережеву перевірку нового кандидата не повторював. Немає автентифікованого читання стану/AMS, LAN-коду чи постійних секретів, команди/друку або списання; production-дані не чіпалися. E06.02 лишається Partial.

Checklist: 118 унікальних ID, UTF-8 BOM збережено; Виконано 29, Частково виконано 71, Заплановано 17, У роботі 1. П’ятигодинний ліміт має 96% залишку на момент checkpoint; останньою прямою вказівкою користувач зняв weekly-ліміт як умову паузи для цього продовження.

Graphify: root source graph оновлено після змін коду (6,283 nodes / 18,224 links). Traceability та project/enriched maps перебудовано після чекліста: traceability 742 файли / 13,151 nodes / 45,483 links; UFM map 245 / 6,212 / 22,882; Spoolman map 298 / 4,920 / 15,554; UFM↔Spoolman 543 / 11,083 / 38,436; enriched 29,048 nodes / 85,970 links. Перевірено 10 graph.json: унікальні IDs і всі endpoints узгоджені; вибрані шість source/checklist hashes збігаються з live files. Карти лишаються навігаційними, не доказом runtime.

Наступне: отримати від власника/адміністратора локальне правило Private-only для конкретного Candidate EXE або працювати в уже дозволеній ізольованій збірці; після цього лише read-only identity/status/AMS. LAN-код не зчитувати/не зберігати без action-time підтвердження. Автосписання вимкнене; release NOT READY. Коренева тека все ще без `.git`; GitHub upload не виконаний, remote не визначено.


## 2026-10-31 — Автозаповнення Bambu Studio у майстрі мережевого підключення

У діалозі підключення Bambu додано другу дію «Автозаповнити з Bambu Studio». Вона повторно використовує наявний захищений імпортер: звіряє локальний IP, серійний номер із TLS-сертифіката та відповідний запис `BambuStudio.conf`; fingerprint показується для явного підтвердження перед заповненням. LAN-код лишається замаскованим у формі та не записується в системне сховище до успішного тесту підключення і явного натискання «Перевірити та зберегти». Зміна IP очищає старий серійний номер/код; невідповідність ідентичності зупиняє заповнення.

Перевірено: `test_bambu_network_autofill.py`, `test_bambu_studio_import.py`, `test_studio_window.py` — 93 passed + 9 subtests; Ruff clean; mypy для двох змінених source-файлів clean; localization placeholder/JSON checks пройшли. Candidate зібраний окремо: `D:\UFM_TestBuild_20261031_BambuStudioAutofill1\UFM Studio`; manifest підтверджує 374 файли/180 source inputs, EXE SHA-256 `0EE879AD2157A5199C67FD87AFA027D30809F42F7797980EB174AF044E26E4EA`. Offscreen startup/capture exit 0 з новим ізольованим Data; тестовий executable відкритий з окремою порожньою базою.

Реальну конфігурацію Bambu Studio та LAN-код під час цього етапу не читали; жодних мережевих запитів, стану/AMS, принтерних команд, друку чи списання не було. Для нового executable не налаштоване правило Private-only; попередня спроба створити його для іншої тестової збірки завершилася OS `Access denied`, Public-доступ не додавався. E06.02 залишається Частково виконано до живої перевірки та ручного приймання.

Checklist: 118 унікальних ID, UTF-8 BOM; Виконано 29, Частково виконано 71, Заплановано 17, У роботі 1. Root/external Graphify після цих source/test/checklist змін ще потребує контрольного refresh. П’ятигодинний ліміт має 95% залишку; weekly gate користувач скасував для цього продовження. Release NOT READY; auto-debit вимкнений.

## 2026-10-31 — Підготовка приватного GitHub-репозиторію

Підготовлено окрему staging-копію для перегляду/редагування коду: 578 файлів (~11.65 MB), окремий main branch; вкладений HaspelSync включено як звичайний vendored source snapshot, його власний `.git` не переноситься. Виключено віртуальні середовища, кеші, залежності, локальні бази/backup, логи, готові збірки, Graphify output, локальні налаштування/секрети та локальні дані HaspelSync. На час цього checkpoint коміт і віддалений репозиторій ще не створено; перед завантаженням виконується path/secret audit. Ціль — приватний репозиторій акаунта A-1lex, без push/deploy до UFM production.

GitHub staging audit: removed a generated linked-stack test transcript from the upload copy and redacted private LAN/IP and device serial literals from the documentation copy only; originals remain unchanged. The scanner's two key-shaped matches are a symbolic config mapping and an intentionally synthetic signed-URL anonymization test fixture, not stored user credentials. The stage remains private and has no tracked database, environment file, build output or dependency tree. This upload checkpoint does not change release readiness; runtime/printer gates remain pending.

## 2026-10-31 — Приватний GitHub upload виконано

Створено приватний репозиторій `https://github.com/A-1lex/Universal_Filament_Manager` і завантажено початкову гілку `main` (initial commit `da73871`, 577 tracked files). Вміст завантажено з окремої staging-копії: без локальних БД/резервів, збірок, середовищ, залежностей, Graphify кешів і локальних секретних налаштувань. Приватні IP/серійні ідентифікатори з документаційної історії заредаговано тільки у staging-копії; робочі файли залишено недоторканими. Автоматичне форматування не застосовувалось: `git diff --check` показав наявні в імпортованих файлах пробіли/кінцеві порожні рядки, які не змінювались масово. UFM як продукт не оголошується готовим до релізу; цей крок лише публікує приватну копію коду для перегляду й редагування.

### Додатковий вихідний файл після повної звірки робочого дерева

Після під’єднання локальної теки знайдено один раніше неіндексований, але актуальний HaspelSync тест `linked-stack/haspelsync/test/ams.env.test.js`. Він містить тільки узагальнені AMS fixtures без серійних номерів чи LAN-коду; включено окремим комітом, щоб репозиторій не пропускав наявне джерело/перевірку. Решта локальних відмінностей — це збережені нерозкриті деталі середовища в документації; вони залишаються незакоміченими в робочій теці.

## 2026-10-31 — GitHub Actions type-check failure diagnosis

GitHub Actions failed on all three pushes at the same `Type check` step; Ruff and dependency installation passed, while pytest/build/wheel steps were skipped. The logs show unresolved `PySide6.QtCore/QtGui/QtPrintSupport/QtSvg/QtWidgets` imports and cascading `Any` subclass/type errors. Root cause: `.github/workflows/ci.yml` installed `.[dev]`, but did not install the declared `desktop` extra (`PySide6-Essentials`). Updated install target to `.[dev,desktop]`.

Local verification with `.venv312`: Ruff passed; MyPy passed (139 files); full pytest passed (683 tests + 491 subtests in 87.93s). This verifies the source with PySide6 present, not the remote multi-OS/3.12–3.14 matrix. Next: push the workflow correction and confirm GitHub Actions finishes successfully on the new commit; if a platform-specific PySide wheel fails to install, adjust the matrix based on its log. No runtime printer, database, or production data was touched.

## 2026-10-31 — Повторний CI виявив Windows-only API у MyPy на Unix

Після додавання `.[dev,desktop]` усунено помилки відсутніх PySide6 imports, але CI Linux/macOS матриця під час MyPy виявила два платформні атрибути: `ctypes.WinDLL` і `subprocess.CREATE_NO_WINDOW`. Обидва валідні для Windows runtime, проте відсутні в non-Windows stubs. Використання замінено на guarded `getattr`: detector без `WinDLL` повертає `None`, а worker передає прапор створення вікна лише коли платформа його надає; Windows гілки зберігаються.

Перевірено локально: Ruff чистий; MyPy чистий (139 source files); `tests/unit/test_windows_power.py` + `tests/integration/test_calculation_worker.py` — 10 passed + 5 subtests. Повний suite без цих останніх двох змін: 683 passed + 491 subtests; remote CI включає повний suite після наступного push. Наступне: запустити новий GitHub Actions matrix і підтвердити Linux/macOS/Windows на Python 3.12–3.14. Попередній workflow run `41211558386` є неуспішним через саме ці старі повідомлення до останнього виправлення.

## 2026-10-31 — Виправлено CI path assertions на Windows

Матриця після PySide6/type portability фіксів виявила дві невірні рівності в `tests/unit/test_foundation.py` на Windows runners: `Path.resolve()` canonicalizes `runneradmin` до короткого шляху `RUNNER~1`, а тести порівнювали із початковим неконанонізованим `Path`. Застосунок створював очікувані resolved paths; змінив лише очікування тестів на `config.resolve()` та `root.resolve() / "data"`, зберігши перевірку відсутності побічних записів.

Локальна перевірка після правки: `test_foundation.py` — 20 passed + 20 subtests; Ruff для зміненого тесту чистий; MyPy clean у 139 файлах; фокусні Windows API тести — 10 passed + 5 subtests. Наступне: новий push-triggered CI має підтвердити всі 9 ОС/Python комбінацій, включно з wheel verification. Невдалі старі run-и — до цього виправлення.


## 2026-10-31 — Linux Qt runtime dependency in GitHub Actions

GitHub Actions run `41211711591` reached pytest on Ubuntu after Ruff/MyPy, with 606 passed, 1 failed, 1 skipped and 75 collection/runtime errors. The captured failures consistently report `ImportError: libEGL.so.1: cannot open shared object file` while importing PySide6 QtWidgets in `tests/integration/test_studio_window.py`; this is a missing runner OS library, not an assertion regression. Updated `.github/workflows/ci.yml` to install Ubuntu package `libegl1` before the project install, conditional on `runner.os == 'Linux'`. Windows/macOS jobs are unchanged. The later run for commit `a5f3860` was in progress at checkpoint, so full matrix acceptance is still pending; after this workflow change, inspect all nine OS/Python jobs, pytest, build and installed-wheel verification. The failing run predates the Windows path expectation fix and Linux EGL install. No printer, database or production data was accessed.


## 2026-10-31 — Cross-platform CI follow-up findings

Review of run `41211933317` (`a5f3860`) confirmed Ubuntu 3.12/3.13/3.14 and macOS 3.13 failed tests because their commit predates the new Linux `libegl1` dependency; macOS 3.12 had one distinct timing-sensitive monitor shutdown assertion (`disconnected.count(2) == 1` observed 0), while macOS 3.14 passed. Windows 3.13/3.14 reached installed-wheel CLI smoke but failed printing Ukrainian output: the script set `PYTHONUTF8=1` in env yet invoked child Python with `-I`, which ignores environment variables. Updated `scripts/check_wheel.py` to pass `-X utf8` explicitly before isolated mode for each child interpreter. The Linux-only EGL workflow change remains local. The single macOS monitor result has not been reproduced or attributed; do not weaken the assertion without evidence. Latest Windows 3.12 job was still in progress when reviewed. Next: run focused local static checks, commit only CI workflow, wheel smoke script, project progress and sanitized handoff/checklist evidence, then inspect fresh 9-job matrix. No printer/production resources involved.


## 2026-10-31 — CI Linux, wheel encoding, and monitor-test synchronization fixes

Applied three targeted CI fixes from runs `41211711591` and `41211933317`: Ubuntu installs `libegl1` for PySide6 Qt imports; isolated child Python processes in `scripts/check_wheel.py` receive `-X utf8` because `-I` ignores `PYTHONUTF8`; two reconnect/shutdown tests now wait for the second provider's event stream to start before stopping, removing a scheduler race without relaxing disconnect assertions. Verification on Windows Python 3.12: wheel built successfully; `scripts/check_wheel.py` passed both locale CLI smoke checks, migration/resource checks and import-origin guard (exit 0). Ruff clean for changed Python files; py_compile clean; `git diff --check` clean. The two focused monitor tests passed in four consecutive runs (8 assertions total across runs). These checks do not validate Ubuntu package installation or macOS runtime; require the new 9-way GitHub Actions matrix before treating CI as green. E16.08 remains Partial and release readiness remains NOT READY pending existing product gates. No printer/production data accessed.


## 2026-10-31 — Guarantee provider disconnect when stream cleanup fails

Fresh CI run `41212790030` verified the Ubuntu-only `libegl1` step: Ubuntu Python 3.12 and 3.13 jobs completed successfully; macOS 3.13 also passed. macOS 3.12 still failed the existing stale-provider reconnect test after the second event stream had started: `provider.disconnect()` was not observed for provider 2. Code review found the cleanup sequence awaited cancellation/gather and stream `aclose()` before disconnect in a single `finally`, so an exception from stream cleanup could skip releasing the provider. Nested the provider disconnect in an unconditional inner `finally`; cleanup errors still propagate, but socket/provider release is always attempted. All three existing stop/reconnect tests passed four consecutive local runs (3 passed per run); Ruff and mypy pass for modified modules. Windows wheel jobs and remaining matrix jobs were still running at this checkpoint. New run required after this source fix.


## 2026-10-31 — Cross-platform GitHub Actions matrix is green

GitHub Actions run `41213065696` on commit `afa1d232ec577db5cd00c5ffffe4e1b0e977f86e` completed with conclusion `success`: all 9 OS/Python jobs passed (Ubuntu, macOS, Windows × Python 3.12, 3.13, 3.14), including lint, mypy, full pytest, wheel/sdist build and isolated installed-wheel checks. This verifies the Linux `libegl1`, Windows UTF-8 wheel smoke and provider disconnect cleanup changes in the remote matrix. E16.08 remains Partial: CI green is not a public-release approval; unsigned development build, incomplete SBOM/licensing/signing, clean-install and owner acceptance plus other checklist gates remain open. Source changes are at commits `a5ff01e` and `afa1d23` on private `main`. No printer or production data was accessed.


## 2026-10-31 — Root and external Graphify refresh after CI fixes

Updated the existing root map with `graphify D:\Bot\Universal_Filament_Manager --update --code-only`, then `cluster-only`: 6,278 nodes / 17,643 edges; 11 code files re-extracted, 478 unchanged, 0 deleted, 2 excluded. Graphify skipped 49 non-code inputs (46 Markdown, 3 images) without semantic re-extraction. Rebuilt external traceability/UFM/Spoolman/link/enriched maps from their selected source snapshot: 743/13,168/45,531; 246/6,229/22,931; 298/4,920/15,554; 544/11,100/38,485; enriched 29,065/86,018; Bambu source 12,955/32,565; local profiles 2,942/7,711; combined 15,897/40,276. All nine graph JSONs have unique IDs and zero dangling endpoints; 743-entry source manifest has zero missing snapshot files and zero snapshot/live SHA mismatches. Updated `D:\graphify-out\bambu-ufm\PROJECT_MAPS_UK.md` and `HANDOFF_UK.md`. E02.06 stays Partial; maps aid navigation and do not prove runtime behavior. Checklist counters unchanged: 29 done / 71 partial / 17 planned / 1 in progress.

## 2026-11-17 — Уніфікація інтерфейсу: дебрендинг, спрощення кнопок, автопідключення принтерів

За запитом власника видимий інтерфейс UFM Studio уніфіковано як єдиний продукт: з UI/CLI прибрано назви Spoolman і HaspelSync. Внутрішні імена модулів, функцій, тестів і міграційне SQL-сховище display_name для вже імпортованих джерел не перейменовували — вони не user-visible або є історичними даними.

Зміни:
- src/ufm/ui/studio_strings.json: 42 ключі переписано нейтрально — «Імпорт бази даних котушок…», «Джерело імпорту», «попередня система обліку», «база котушок»; у uthority_cutover_preview placeholder перейменовано {haspel_ready}→{journal_ready} (оновлено call site). Додано ключ connect_candidate.
- src/ufm/ui/i18n/uk-UA.json + en-US.json: desktop.import*, select_spoolman, import_source_*, error.spoolman_import, cli.help — нейтральні формулювання; placeholder-parity збережено.
- src/ufm/bootstrap/cli.py: первинні нейтральні прапорці --spool-api-preview, --spool-db-preview, --spool-db-import, --spool-source-id, --slot-mapping-preview; старі --spoolman-*/--haspelsync-* лишаються робочими прихованими аліасами того самого argparse-аргументу.
- src/ufm/integrations/spoolman/importer.py: user-visible fallback display_name/device name → «Spool database import».
- src/ufm/ui/studio_window.py: сховано три niche-контроли — haspel_import_preview (Система), inspect_slice_file (Пристрої), atch_print_qr_labels (Філамент); методи й рядки збережено для можливого повернення. Додано автоскан: перехід на сторінку «Пристрої» запускає discover() (busy-гард запобігає повтору під час задачі; 
efresh() скан не дублює; повторне відкриття сторінки — новий скан). Знайдені кандидати показуються у candidate_list; кнопка «Підключити вибраний пристрій…» для BAMBU_LAN відкриває мережеве заповнення з готовим host + авто-ідентифікацією, для Moonraker/OctoPrint — локальну форму з endpoint/provider. Користувач лише вводить LAN-код і підтверджує TLS; збереження credentials лише після явного підтвердження.

Тести (+6): test_user_facing_strings_have_no_legacy_brand_names, test_niche_buttons_are_hidden_from_studio_pages, test_devices_page_auto_scan_runs_once_per_opening, test_connect_candidate_prefills_bambu_enrollment_without_saving (studio_window); test_help_uses_neutral_flag_names_without_legacy_brands (foundation); test_cli_neutral_and_legacy_spool_db_flags_are_equivalent (spoolman importer). Оновлено test_system_registry_documents_haspel_booking_review_safety під нейтральний текст (зміст застереження збережено).

Перевірки: повний suite **696 passed / 491 subtests, exit 0** (90,97 с); ruff check clean; mypy clean для змінених source-файлів. Тимчасові скрипти дебрендингу видалено.

CSV: статуси E01–E06 не змінювалися — ця робота не закриває жодного кроку приймання; відкриті пункти та live/owner/hardware-блокери лишаються як у попередньому checkpoint. Зміни закомічено та відправлено в приватний `origin/main` після rebase на віддалені CI-виправлення.

## 2026-11-18 — E12.06: read-only loopback API для локальних споживачів

Реалізовано перший компонент сумісного API: src/ufm/integrations/local_api.py — LocalApiServer на ThreadingHTTPServer (daemon thread, bind 127.0.0.1, типово порт 7912). GET-only підмножина Spoolman v1: /api/v1/health, /info, /spool, /spool/{id}, /spool/group, /filament, /filament/{id}, /material, /vendor, /vendor/{id}, /location. Не-GET повертає 405, невідомі шляхи 404, JSON без секретів; жодних записів в облік через цей інтерфейс. StudioSpool отримав profile_id для коректного зв'язку spool→filament.

Тести: tests/integration/test_local_api.py — 4 contract-тести через реальний HTTP на ephemeral-порті (health/info, порожній каталог, повний spool payload із filament/vendor/location, 405/404, idempotent start/stop). Повний suite: 700 passed / 491 subtests (100,20 с); ruff clean; mypy clean для local_api.py і studio_backend.py.

Залишок E12.06: write-сумісні endpoints, auth/origin policy, автозапуск endpoint самою програмою або UI-перемикач, contract fixtures проти реальних споживачів (slicer/Moonraker/OctoPrint/HA), live-перевірка. Статус лишається Частково виконано.

Додатково того ж дня: `ufm --serve [--api-port ПОРТ]` запускає той самий LocalApiServer поверх бази програми (migrate + StudioBackend), виводить JSON з фактичним портом і працює до Ctrl+C. Ручна перевірка на 127.0.0.1:17923: /api/v1/health → {"status":"ok"}, /api/v1/spool → []. cli.help оновлено в обох локалях. ruff/mypy clean; foundation+local_api 25 passed.

## 2026-11-18 — E12.02: поверхня деталей завдання друку в Studio

Додано read-model агрегацію та UI для пояснення рішень списання:
- src/ufm/infrastructure/studio_backend.py: StudioJobRow/StudioJobMaterialInfo/StudioJobSegmentInfo/StudioJobLedgerEntry/StudioJobDetail; recent_jobs(limit<=500) і job_detail(job_id) — print_job + materials_for_job + segments.for_job + ledger.for_job з resolved іменами котушок/профілів/принтера; NotFound → None.
- src/ufm/ui/studio_window.py: кнопка «Історія друку» на сторінці «Пристрої» → діалог із таблицею завдань і read-only деталями (файл/пластина/принтер/статус/фіналізація/прогрес/шари/часові мітки, матеріали з оцінкою маси, сегменти з assignment_state/source/confidence/spool, ledger-записи з типом/масою/source/confidence_bp/policy/description). 32 нові локалізовані ключі (job_* + enum-мітки статусів) у studio_strings.json.
- Тести: tests/integration/test_studio_job_detail.py (2 тести: порожній стан + агрегація полів через прямий insert printer/print_job), test_job_detail_text_explains_decision_fields, test_show_print_jobs_empty_state.

Перевірки: цільові тести passed; ruff clean; mypy clean (studio_window.py, studio_backend.py). Повний suite: 704 passed / 491 subtests (92,20 с), exit 0. CSV E12.02 → Частково виконано з новим доказом; live-приймання на реальних друках і UI-акцептанс лишаються.

## 2026-11-19 — E12.01: список невизначених подій звіряння в Studio

Продовження уніфікованої історії (E12.01):
- src/ufm/application/ports/persistence.py + src/ufm/infrastructure/persistence/repositories/entities.py: новий ReconciliationRepository.open_tasks() — усі задачі зі статусом OPEN/IN_REVIEW (не видалені), упорядковані за created_at.
- src/ufm/infrastructure/studio_backend.py: DTO StudioReconciliationTask + open_reconciliation_tasks() з resolved іменами котушки/завдання.
- src/ufm/ui/studio_window.py: кнопка «Невизначені події» на сторінці «Пристрої» → діалог-таблиця (причина/важливість/стан/котушка/завдання/рекомендована дія/дата); 17 нових ключів локалізації (recon_* + статуси/важливість).
- Тести: tests/integration/test_studio_job_detail.py (+2: порожній стан; OPEN задачі повертаються, RESOLVED — ні), test_show_reconciliation_tasks_empty_state.

Перевірки: цільові тести passed; ruff/mypy clean; повний suite 707 passed / 491 subtests (90,68 с). CSV E12.01 → Частково виконано з новим доказом; лишається повний lifecycle/receipt browser parity та live-приймання.

## 2026-11-19 — E12.04: ручне розв'язання невизначених подій у Studio

- src/ufm/infrastructure/studio_backend.py: resolve_reconciliation_task(task_id, outcome, notes) — outcome resolved/dismissed, нотатка 1–500 символів, OPEN/IN_REVIEW → RESOLVED/DISMISSED (OPEN→DISMISSED через проміжний IN_REVIEW згідно з політикою переходів), revision+1, audit event reconciliation.manual_resolution; первинна історія задачі зберігається.
- src/ufm/ui/studio_window.py: діалог «Невизначені події» отримав кнопки «Вирішити…»/«Відхилити…» з обов'язковою нотаткою (QInputDialog) і оновленням таблиці; 4 нові ключі локалізації.
- Тести: tests/integration/test_studio_job_detail.py (+3: resolved+audit, dismiss через IN_REVIEW, валідація вводу), наявний UI empty-state тест оновлено під нову структуру діалогу.

Перевірки: цільові тести passed; ruff/mypy clean; повний suite 710 passed / 491 subtests (115,67 с). CSV E12.04 → Частково виконано з новим доказом; лишається паритет інспекції job/provider конфліктів і live-приймання.

## 2026-11-19 — E12.06: локальний API керується зі Studio

- src/ufm/bootstrap/settings.py: AppSettings.local_api_enabled (default False) + local_api_port (default 7912, 1–65535); старі settings.json без полів отримують типові значення.
- src/ufm/ui/studio_window.py: на сторінці «Система» — порт + кнопка «Локальний API: увімкнено/вимкнено»; toggle стартує/зупиняє LocalApiServer на 127.0.0.1, зберігає вибір атомарно в settings.json, автозапуск при старті програми якщо enabled, зупинка в closeEvent (лише при реальному закритті, не при відкладеному). 5 нових ключів локалізації.
- tests/integration/test_studio_window.py::test_local_api_toggle_starts_and_stops_server — реальний loopback GET /api/v1/health через UI toggle, перевірка persist і stop.

Перевірки: цільові тести passed; ruff/mypy clean; повний suite 711 passed / 491 subtests (90,85 с). CSV E12.06 → Частково виконано з новим доказом; лишаються write-endpoints, auth/origin policy, contract fixtures і live-приймання.

## 2026-11-19 — Перше live-підключення принтера + виправлення конфлікту ідентифікаторів

Користувач отримав реальний probe: принтер ONLINE, сопло 255 °C, стіл 70 °C, але всі 5 слотів (ams:0·0:0–0:3, external) у стані CONFLICT — tray_uuid і tag_uid були довірено прив’язані до різних котушок UFM, а шляху переприв’язки не існувало.

- src/ufm/application/spool_identifiers.py: новий SpoolIdentifierCommands.rebind() — retired_at для старої прив’язки (без видалення), новий verified SpoolIdentifier для обраної котушки, окремий audit event spool.identifier_rebound, ідемпотентний replay за command_key.
- src/ufm/application/ports/persistence.py: SpoolIdentifierRepository.save().
- src/ufm/ui/studio_window.py: діалог «Перевірити ідентифікатор» показує поточну прив’язку кожного ідентифікатора (ім’я котушки або «не прив’язано»); якщо обрано іншу котушку — підтвердження переприв’язки і виклик rebind. 3 нові ключі локалізації.
- Тести: tests/integration/test_spool_identifier_commands.py (+2: rebind retire+verify+audit+replay; rebind_not_needed без конфлікту/для тієї ж котушки).

Перевірки: цільові тести passed; повний suite 713 passed / 491 subtests (93,19 с); ruff/mypy clean. CSV E12.04 → Частково виконано з live-доказом конфлікту та новим шляхом розв’язання. Наступна дія власника: повторно probe → verify identity для кожного слота → mount verified.
