# Точка продовження UFM Studio

## Пакет 1 — baseline, source provenance та межі очищення — 2026-10-30

Підтверджено початок покрокового плану. Встановлено, що корінь `D:/Bot/Universal_Filament_Manager` не є Git checkout, тоді як `linked-stack/haspelsync` має власні Git-метадані. Не ініціалізували репозиторій і не створювали commit; root revision не заявляється. Чекліст після зміни evidence повторно перевірено: UTF-8 BOM, 118 рядків, 5 колонок, статуси 29 виконано / 68 частково / 20 заплановано / 1 у роботі.

Cleanup: звіт `docs/CLEANUP_REPORT-20261030T150320454Z.json` має `Applied=false` і є тільки dry-run для `.pytest_cache`, `.mypy_cache`, `.ruff_cache`. `docs/BUILD_ARTIFACT_CLEANUP.json` містить п’ять старих `.runtime` build-каталогів, але лише їхні шляхи/розміри; маніфести та відтворюваність не перевірені. У цьому пакеті нічого не видаляли й не торкалися даних, кандидатів, backups, build outputs чи ярликів.

Наступна дія: встановити безпечне джерело root provenance без вигадування revision; окремо перевірити manifest та посилання кожного allowlisted build-каталогу. Відкриті рішення: чи відновити root Git-історію/remote, і які ізольовані build outputs залишити як актуальні.

---


**Актуальний короткий стан:** `docs/PROJECT_PROGRESS_UK.md`.
Перед продовженням читати його та CSV-чекліст. Нижче збережена історія:
ранні списки «наступних дій» можуть бути вже виконані пізнішими записами.
З 2026-10-26 правило постійного оновлення прогресу закріплене в `AGENTS.md`.

Мета: одна розширювана настільна програма для Windows без браузера й Docker,
керування філаментом і принтерами, захищений облік витрат, оформлення з робочими
просторами на зразок Bambu Studio, окрема папка на D: і ярлик на робочому столі.

## Збережений стан

- Основний код: `D:/Bot/Universal_Filament_Manager`. Не переносити середовища Python:
  вони містять абсолютні шляхи. Окрема папка запуску: `D:/UFM Studio`.
- Активний Python: `.venv312/Scripts/python.exe`, Python 3.12;
  установлено PySide6-Essentials 6.12.0. Qt WebEngine не потрібний.
- Наявне ядро: SQLite, міграції, журнал у міліграмах, ручні команди запасів,
  імпорт Spoolman з резервними копіями, локальні адаптери принтерів лише для читання.
- Автоматичне списування ще не завершене; не позначати його готовим лише через
  наявність таблиць finalization або отримання MQTT-повідомлень.
- Зберегти `.runtime`, `backups`, `linked-stack`, обидва venv, конфігурації та
  історичні дані. Очищати лише перевірені відтворювані кеші.
- Існують графи в `graphify-out`; повна повторна побудова не потрібна.

## Поточні паралельні завдання

1. product_plan: повний план та CSV-матриця функцій у docs.
2. accounting_audit: аудит і алгоритм автоматичного списування у docs.
3. packaging: запуск, скрипт ярлика, безпечне очищення кешів.
4. Основний агент: Qt Studio, перевірка, окрема папка, піктограма, інтеграція.

## Наступні дії

- Реалізувати Qt інтерфейс поверх чинних команд, без прямих SQL-змін маси.
- Перевірити імпорт, ручне списування, історію та резервну копію на тестовій БД.
- Зробити знімок інтерфейсу через offscreen Qt і візуально перевірити.
- Оновити цей файл фактичними результатами тестів і шляхами артефактів.
- Не обіцяти готовність до розповсюдження без автономної збірки та перевірки
  на чистій Windows. Ярлик із Python-середовищем є локальним запуском.

Точки збереження робити після етапів. Точний поріг залишку контексту 15%
не доступний агенту; файл дозволяє відновитися після переривання.

## Контрольна точка: нативна збірка працює

- Додано `src/ufm/ui/studio.py`, `studio_window.py`, `studio_strings.json`,
  `src/ufm/infrastructure/studio_backend.py`, оригінальну піктограму assets/ufm.ico.
- Функції: профілі, котушки, початковий залишок, ручні операції, історія,
  пошук, світла/темна тема, імпорт з preview, backup, фонове виявлення
  мережевих кандидатів та читання стану вже налаштованого принтера.
- Рух маси виключно через InventoryCommands; нова котушка має невідомий
  залишок, а не 0. Жодних автоматичних контактів з обладнанням при старті.
- 6 нових тестів пройшли; повний запуск: **312 passed, 211 subtests passed**.
  Повторна перевірка через pytest.main повернула 0.
- Ruff пройшов; mypy: 96 source files, no issues.
- `scripts/build_studio.ps1`, `scripts/ufm_studio.spec` створили автономну
  програму `D:/UFM Studio/UFM Studio.exe` (Python/Qt усередині `_internal`).
- EXE smoke: `--data-dir D:/UFM-Studio-Build-Check --capture .../preview3.png`,
  код завершення 0, БД і PNG створені. Це не перевірка на чистій Windows.
- Виправлено PyInstaller PATH-конфлікт: стороння ICU 78 затіняла системний
  Windows ICU, потрібний Qt 6.12. Spec виключає ці випадково захоплені DLL.
- Перша невдала збірка збережена в `.runtime/studio-first-bundle`, окремий
  діагностичний EXE — `.runtime/diagnostic`. Це відтворювані build artifacts;
  їх можна прибрати після завершення перевірки, на відміну від реальних даних.

Залишилося: зібрати звіти трьох агентів, виконати безпечне очищення,
створити й перевірити ярлик на Desktop, додати інструкцію запуску та
пакет документів у D:/UFM Studio, зафіксувати обмеження автосписування.

## Контрольна точка: план і ярлик готові

- Створено `PRODUCT_MASTER_PLAN_UK.md`: 32 пакети робіт із залежностями
  та критеріями прийняття; `FEATURE_MATRIX_UK.csv`: 124 рядки функцій
  (28 є; 25 частково; 51 додати; 20 бажані).
- Додано `AUTOMATIC_ACCOUNTING_UK.md`, `STUDIO_DESIGN_UK.md`,
  `STUDIO_USER_GUIDE_UK.md` та скрипти складання/запуску/ярлика/очищення.
- Додано Qt enrollment для Moonraker/OctoPrint і Bambu Studio profile
  з явною довірою до сертифіката. Фізичні команди й автосписування не ввімкнені.
- Незалежний імпорт: `D:/UFM Studio Data`, 5 котушок, 5 профілів, 2 бренди,
  **3,999,672 мг**. Джерело та legacy stack не змінені.
- Ярлик створено: `C:/Users/-PC-/Desktop/UFM Studio.lnk`, target
  `D:/UFM Studio/UFM Studio.exe`, arguments `--data-dir "D:/UFM Studio Data"`,
  icon `D:/UFM Studio/ufm.ico`.
- Знайдено збій native Qt під час завершення/GC. Виправлено порядок:
  disconnect selection callbacks → close/delete widgets → flush deferred deletes
  перед dispose database. У тестах QApplication живе протягом сесії.
- Після виправлення повний тестовий процес повернув 0:
  **313 passed, 211 subtests passed**, Ruff/mypy пройшли.
- Перезбирається фінальний EXE з цим виправленням. Наступне: smoke повторних
  запусків EXE; копіювання документації; очищення allowlist-кешів; manifest.
- Три допоміжні агенти не повернули артефактів у цій ітерації; їх зупинено,
  щоб не затримувати результат. Усі зазначені зміни завершив основний агент.

Не відмічати автосписування завершеним: наступна реалізація — атомарний
finalization application service із replay/crash/concurrency тестами, як описано
в `AUTOMATIC_ACCOUNTING_UK.md`.

## Остаточна точка цієї ітерації

- Фінальний EXE з виправленим teardown **тричі поспіль** пройшов
  запуск/відкриття імпортованої БД/знімок/вихід із кодом 0.
- Актуальний знімок: `docs/studio-preview.png`, візуально перевірений.
- Повний suite після виправлення: 313 тестів і 211 subtests; exit 0.
- Ярлик на робочому столі створений; TargetPath/Arguments/IconLocation перевірені.
- Очищено лише allowlist-кеші та створені цією ітерацією невдалі/проміжні
  bundle-копії. Звіти: `CLEANUP_REPORT.json`, `BUILD_ARTIFACT_CLEANUP.json`.
  Звільнено приблизно 586 MiB; production data/backups/source збережені.
- Документи доставляються у `D:/UFM Studio/docs`, залежності/нотиси —
  `D:/UFM Studio/third-party`, checksum manifest — `release-manifest.json`.
- Тестова перевірка EXE використовує `D:/UFM-Studio-Build-Check`; це не дані
  користувача. Реальна окрема копія інвентарю: `D:/UFM Studio Data`.
- Публічний реліз ще не готовий: finalization/worker/physical controls,
  чиста Windows, підпис/інсталятор/ліцензії залишаються відкритими.

Наступному агенту: не перебудовувати UI з нуля. Почати з пакета W13:
атомарний finalization service; спочатку schema/порт контракт і тест replay,
потім crash/concurrency, далі worker та mapping. До проходження gate не
знімати попередження про незавершене автосписування в Studio.

Пакет доставлено. Архів `dist/UFM-Studio-0.1.0-preview-win-x64.zip` перевірено
через testzip; 49.4 MiB. Детальний остаточний протокол —
`DELIVERY_VERIFICATION_UK.md`. Папка програми та її manifest уже сформовані;
після зміни файлів у bundle потрібно перевипустити manifest і ZIP.

## Наступна ітерація: W13 у роботі

Створено `src/ufm/application/finalization.py`: `FinalizationCommands.finalize_single`
для одного завершеного job / одного повного закритого сегмента / однієї котушки.
Споживає вже збережені receipt та immutable evidence; не опитує принтери.

Поточний контракт: job_id, segment_id, evidence_id, receipt_id,
actor_device_id, command_key, optional at → FinalizationRecord.
Допускає лише PRINTER + CONSUMED_MASS + ABSOLUTE + confidence 10000,
відомий includes_purge=True, повний interval, verified alias scope та монтаж.
Недостатній запас або неоднозначність відхиляються без змін; це ще не повний
workflow автоматичного звіряння й не облік AMS/багатьох котушок.

Один UoW має записати finalization, decision/evidence link, debit/projection,
settlement власного резерву, job/receipt states та audit. Нуль — без ledger debit.
Replay перевіряє request/result hashes та повертає старий запис без нового дебету.

Активні окремі підзадачі з коротким контекстом:
- finalization_constraints: вузькі порти й repository methods у persistence.py/entities.py;
- finalization_tests_review: нова мігрована fixture й acceptance tests у test_print_finalization.py;
- finalization_safety_review: read-only огляд завершено; критичних помилок не виявлено.

До отримання port/test змін новий сервіс ще не перевірений повним suite.
Не вмикати його у production worker/GUI. Встановлений EXE й особиста база
залишаються попередньою перевіреною версією. Наступне: інтегрувати порти,
запустити нові tests; виправити фактичні failures; повний Ruff/mypy/pytest;
оновити матрицю і цей checkpoint фактичними результатами.

## W13: перший виконавець завершено й перевірено

Готові файли:
- `src/ufm/application/finalization.py` — один atomic UoW для перевіреного
  single-spool completed-print; strict evidence/mapping/identity/baseline guards.
- `src/ufm/application/ports/persistence.py` та
  `src/ufm/infrastructure/persistence/repositories/entities.py` — вузькі читання
  materials/segments/aliases/claims/evidence, lookup finalization key та evidence links.
- `tests/integration/test_print_finalization.py` — 14 tests / 20 subtests.
- `scripts/check_finalization_wheel.py` — acceptance з реального wheel поза checkout
  без мережевих завантажень; це не перевірка встановлення runtime dependencies.

Результати:
- нові інтеграційні тести: 14 passed / 20 subtests;
- повний suite: **327 passed / 231 subtests**, exit 0;
- Ruff пройшов; strict mypy — 97 source files, no issues;
- sdist/wheel зібрані; 14 tests / 20 subtests також пройшли з extracted wheel,
  origin `ufm` та finalization перевірені всередині wheel-каталогу.

Перевірено rollback після записів ledger/projection/settlement/receipt, процесне
завершення до/після commit, два concurrent writers, replay після reopen і
законного наступного manual use, конфлікти ключа/актора/payload/job,
нуль, overrun власного резерву, збереження чужих резервів, unknown/shortage,
непевне evidence, неповний job, late opening та післяпринтове зважування.

Міграцій та залежностей не додано. Базу користувача, джерело Spoolman,
встановлений EXE та ZIP з попередньої ітерації не змінено. Додане ядро
ще не підключене до live worker/GUI; попередження Studio залишається чинним.
У матриці 124 функції: 28 є / 28 частково / 48 додати / 20 бажані.

Агенти дали три вузькі аудити (constraints, fixtures, safety); після затримки
запису реалізацію портів і acceptance tests інтегрував координатор. Перекриття
власників файлів зупинено перед його редагуванням.

**Наступний крок:** persistent receipt ingestion + job identity resolver (W09/W10),
потім explicit spool mapping і normalized verified evidence. Адаптер має чітко
показувати, чи маса фактична і чи включений purge; progress/файл/слайсерна
оцінка не є підтвердженою витратою. Перша інтеграція працює в shadow mode.
Окремо залишаються failed/cancelled, AMS/multi-segment, measurement cutoff
reconciliation та physical E2E. Установлений EXE оновлювати тільки після
корисного завершеного GUI/worker slice, з новим manifest та ZIP.

## Порівняння з GitHub та старою зв’язкою

Додано `CONSUMPTION_COMPARISON_UK.md` з джерелами й локальними line refs.
Spoolman приймає use_weight/use_length від клієнта. У старій зв’язці
HaspelSync парсить sliced 3MF/G-code, зіставляє котушки і списує на terminal
state; failed/cancelled — часткова оцінка. У власному linked-stack є стійкий
booking journal та заборона сліпого retry невизначеного HTTP-запису.

Runtime доказ: 2026-10-24 22:47:17 — HaspelSync Booked 180.88g for spool 3,
Spoolman spoolman.log:3069 — PUT /spool/3/use 200 тієї самої секунди.
Наявні Spoolman logs містять 10 /use requests із 200; це не кількість друків.

Уточнення наступного дизайну: PRINTER/ABSOLUTE-only kernel не дає паритету
з HaspelSync. Потрібна явна автоматична політика для THREE_MF/GCODE/SLICER
оцінок із provenance/confidence та coverage purge. Не вимагати фізичний
датчик маси для будь-якого автосписування; не видавати розрахунок за вимірювання.
Перший Bambu slice: MQTT/FTPS/3MF + зовнішня котушка + FINISH у shadow mode.
Це дослідження не змінювало runtime, залишки або функціональні guards.

## Кнопка мережевого автозаповнення — реалізовано

Додано `integrations/printers/bambu_discovery.py`, BambuPrinterIdentity,
кнопку у Tk-формі `desktop.py` та новий Qt Bambu dialog у `studio_window.py`.
SSDP → serial/model/name/IP → TLS CN match → explicit fingerprint trust.
IP порожній допускається лише для одного пристрою; ручний IP має fallback
через certificate, P1S model за vendor prefix 01P. LAN-код не видобувається
з мережі: ручне приховане поле або окрема кнопка Studio import.

Фізична read-only перевірка: [LOCAL_IP_REDACTED] знайдений через SSDP без IP-input;
визначився як P1S; serial/certificate прочитані без auth/control.
Suite: **335 passed / 240 subtests**, exit 0; Ruff; mypy 98 source files.
17 цільових тестів пройшли. GUI screenshot візуально перевірений.

Зібрано stage EXE `.runtime/network-autofill-release/UFM Studio`, smoke exit 0.
Наступна дія цієї ітерації — безпечно замінити D:/UFM Studio після перевірки,
зберегти попередню програму в .runtime backup, оновити docs/manifest/ZIP.
Особисті дані D:/UFM Studio Data не переносити в пакет.

Оновлення встановлено в D:/UFM Studio; попередня програма збережена в
`.runtime/studio-before-network-autofill`. Новий Qt шлях:
Пристрої → Автозаповнити з мережі → IP або порожнє поле → кнопка у формі
→ підтвердження fingerprint → LAN-код → Перевірити та зберегти.
Класичний Tk застосунок потрібно перезапустити для завантаження нової кнопки.
Реальні тести підтвердили обидва шляхи: визначення за IP і SSDP без IP.
Пакет оновлюється окремим preview-network-autofill ZIP із новим manifest.

## Детальний план об’єднання на запит користувача

Створено `docs/INTEGRATION_STEP_BY_STEP_UK.md`: 17 частин / 118 конкретних
кроків E01.01–E17.05, залежності, результати, критерії та контрольні випуски.
`docs/INTEGRATION_CHECKLIST_UK.csv` створений із цих ID, перевірено унікальність
і відповідність; статуси початково «Заплановано», доказ виконання заповнюється
за результатом кроку. Наявні функції не вважаються відсутніми: спершу їх перевіряють.

Фокус — повний реєстр кнопок/екранів/автоматизацій старої зв’язки й власних
доробок, один власник обліку, перевірені резервні копії, перенесення даних,
повторне використання зрілих алгоритмів через адаптер, повний Qt UI,
розрахункове/часткове/multi-spool списання, контрольований перехід і постачання.
Варіант внутрішнього Node-worker оцінюється коротким інтеграційним випробуванням;
він не є вже реалізованим компонентом і не потребує окремого ручного запуску.

Ця ітерація змінила лише документи й checklist, без runtime/даних/налаштувань.
Попередній запит про estimated 3MF/G-code/partial/allocations лишається ціллю
реалізації E08–E11; перерваний coding turn не додав парсера чи batch service.

## 2026-10-27: автоматичне продовження, приймання резервних копій E01

Основний ліміт відновився (100% / 56% на початку). Додано
`scripts/capture_integration_baseline.py`, використано чинні create_snapshot /
restore_snapshot. Прийнятий приватний run:
`.runtime/integration-baseline/20261027T042326776391Z/manifest.json`.
Дві online SQLite-копії й їх окремі відновлення: integrity/FK/hash/counts/маса
збігаються. Збережено й перевірено ZIP 229 файлів власного HaspelSync і 342
файлів встановленого EXE-пакета. Джерела, встановлення, робочі дані незмінні.

Докази: `docs/INTEGRATION_BASELINE_UK.md`. CSV: 4 виконано, 2 часткові,
112 заплановано. E01.01 не підтверджує фактичні запущені legacy версії:
Docker Desktop pipe відсутній. E01.03 не закритий: runtime секрети/config,
mapping/історія ще потребують захищеного backup і перевірки відновлення.
Git HEAD власного HaspelSync 253afa06a133246a52558ba42e0dae478a5f0f27,
локальні зміни збережені у source ZIP; .git не входить до архіву.

Ruff script OK. Tests migration/test_initial.py: 9 passed поза sandbox;
перший запуск заблокував доступ SQLite до sandbox temp. Повний suite не
потрібен: функціональні модулі не змінені. Перший capture run невдалий через
Poetry key, виправлено на project; каталог ...042314536082Z не прийнятий.
Наступне: захищене резервування приватних runtime даних E01.03, потім E02.

## 2026-10-27: E01.03 — приватний backup HaspelSync

Додано `scripts/backup_haspelsync_private.ps1` (PowerShell 7.2+, Windows).
ZIP тільки в пам’яті, потім DPAPI CurrentUser, повторне читання/розшифрування
й перевірка всіх записів за hash/size. Немає plaintext export на диск.
Прийнятий run `.runtime/private-haspelsync/20261027T0428176609351Z/`:
9 файлів runtime/логів/compose. Джерела й секрети не змінено.
Окремий VerifyBundle першого знімка пройшов; tampered ciphertext відхилений.
Syntax parser PowerShell OK. Автотести ядра не повторювали: ядро незмінне.

Важливе обмеження: копія залежить від поточного Windows профілю/DPAPI ключів,
не є переносним парольним експортом. VerifyBundle відновлює записи в пам’ять,
не перезаписує робочу конфігурацію. Файли bookings/accounting/presets/apikeys
на перевірених legacy/own шляхах відсутні, не створювали їх порожніми.
Документ `docs/PRIVATE_HASPELSYNC_BACKUP_UK.md`, CSV E01.03 виконано;
підсумок 5 виконано, 1 частково, 112 заплановано.
Наступне E02.01–E02.02: точний реєстр UI з file evidence поверх наявної матриці.

## 2026-10-27: E02 — статичний реєстр інтерфейсів

Користувач повторно доручив автоматично продовжувати; на початку 93% / 55%.
Два read-only агенти завершили локальний аудит Spoolman та HaspelSync;
root інтегрував докази у `docs/LEGACY_UI_CATALOG_UK.md` (S01–S28,
H01–H21, A01–A09). Перший graphify query не дав достатнього Spoolman UI
покриття, прямі файли використані як авторитетні.

`scripts/inventory_legacy_ui.py` генерує LEGACY_UI_CANDIDATES.csv та
LEGACY_UI_SOURCE_MANIFEST.json: 95 файлів, 777 literal/click кандидатів
(329 Spoolman / 210 downloaded HaspelSync / 238 own). Кандидати можуть
включати повтори/коментарі, не доводять runtime visibility й не покривають
усіх framework-generated кнопок. Ruff успішний, app runtime не змінений.

Own vs downloaded public diff: local-only accounting.css/html/js,
змінені menu.js і чотири i18n; решта public та settings schema збігаються.
У каталозі 27 settings keys, перші контракти weighing/cost/resolve,
початкові background сценарії, запропоновані місця Qt. E02.02 прийнятий;
E02.01/03/04/06 часткові; E02.05/07/08 не закриті.
CSV totals: 6 виконано, 5 частково, 107 заплановано.

Наступне: Refine defaultButtons у залежності/контрольованому test UI,
атомарні контракти й mapping F001–F124, background сценарії, API consumers,
класифікація й тестові користувацькі еталони. Не перезаписувати матрицю 124
як нібито весь UI вже перенесений. Дані/налаштування/EXE незмінні.

## 2026-10-27: безперервний цикл і порогова зупинка

Користувач уточнив: після кожного етапу перевіряти ліміти й одразу працювати
далі в тому самому запуску, якщо залишки >15%. AGENTS.md та heartbeat ufm
оновлені цим правилом. Почали на 66% / 51%, зупинились на 15% / 43%.
Не завершували лише через один готовий етап.

Отримано exact npm @refinedev/antd 6.0.3, SHA512 збіг із Spoolman lockfile;
source-only у .runtime/refine-antd-6.0.3, архів cache .runtime/*.tgz.
Sandbox DNS failed, дозволений повтор завантаження успішний. Refine default
List/Create, Show/List/Edit/Delete/Refresh, Edit/Delete/Save й Popconfirm
описані в REFINE_DEFAULT_ACTIONS_UK.md; E02.01 завершено статично.
PARITY_ACCEPTANCE_SCENARIOS_UK.md: 25 сценаріїв, 6 dataset definitions;
E02.08 завершено як опис, не runtime test. Background агент завершив
BACKGROUND_AND_API_INVENTORY_UK.md: B01–B24, 58 Spoolman registrations,
54 HaspelSync endpoints, source consumer taxonomy; E02.04 завершено,
E02.05 частковий через непідтверджені installed consumers.

Агенти haspel_action_contracts/spoolman_action_contracts створили свої CSV,
але root перервав їх одразу при порозі15%. Файли збережені, E02.03 частковий;
наступній сесії потрібен review, а не припущення про завершення. Структурні
підсумки .runtime/continuation-loop-checkpoint.json. Дані/EXE незмінні.
CSV totals: 9 виконано, 4 частково, 105 заплановано.
Наступне після свіжої перевірки >15%: review ACTION_CONTRACTS, mapping до
F001–F124 та класифікація, потім E03 integration spike. Автоматизація активна.

## 2026-10-27: відновлення, mapping та інтеграційний spike

Ліміти на початку нового запуску100%/42%; після останнього етапу59%/36%.
Spoolman агент доповнив свій CSV до318 SA001–SA318, зберіг ID і legacybugs;
інший агент створив FEATURE_PARITY_MAPPING_UK.csv, 124 F-ID, 46/45/33 класи.
Read-only review двохCSV ще триває; HA211 може бути неповним, E02.03/06partial.

ADR-001 INTEGRATION_DECISION_UK.md і ARCHITECTURE.md: Qt/UFMledgerauthoritative,
Pythonorchestration+вузькийbundledNodecalculator; Pythonreferenceтількиtestoracle.
experiments/haspel_worker/calculate.mjs — read-onlystdin/stdoutv1prototype.
compare.py — 11XMLfixtures*4full/partialcases+7rejections=51passed/0failed.
Доказ .runtime/haspel-worker-spike/20261027T084037652031Z/report.json.
НемаєGcodeextrusion/ZIP/network/realdebitвцьомуспіку. Nodelegacyparserможе
coerceневаліднийused_gдо0; productionintakeмаєstrictvalidationдоworker.

src/ufm/application/dto/worker_protocol.py: strict/frozenPydanticmodels,
6incomingkinds +parentonlyFinalizationOutcome, explicitv1, boundedframe,
duplicatekeys/NaN/Infinity/coercion/forgedoutcome/allocationsguards,
genericWorkerProtocolRejectedбезrawinput. WORKER_PROTOCOL_V1_UK.md.
11targetedtests/20subtests, Ruff+mypyOK. Fullsuite346passed/260subtests,
PYTEST_RESULT0 позаsandbox. AppUI/installedEXE/realdataнечіпали.
E02.07таE03.01–05done; CSV15done/4partial/99planned.
Наступне verifiedfileintake (E08) +workeradapter/receipts/finalization.

## 2026-10-27: bounded transport, 3MF intake та перевірка regressions

src/ufm/integrations/calculation_worker.py: async one-shot transport, trusted
absolute paths, sanitized env, hidden Windows child, stdout512KiB/stderr4KiB,
bounded request, timeout/kill/cancellation, printer/epoch/request correlation.
8 tests/5 subtests поза sandbox. Sandbox запуск завис без виводу; контрольний
real_child поза sandbox пройшов. Перевірені test PID16040/14884 завершено
окремим дозволеним Stop-Process; реальних app/process/data не чіпали.

Агент записав sliced_files.py і test_sliced_files.py; перший apply_patch
завис і був aborted, повторний write успішний. Root додав preflight EOCD
до ZipFile allocation (entries<=2048, directory<=16MiB, noZIP64/multi-disk),
плюс ігнорування порожнього unused layer list як у legacy.
API: inspect_3mf_bytes/file(data/path, *, plate, expected_sha256).
Facts frozen: parser_version, file_sha256, plate, metadata_sha256,
gcode_sha256, filaments, layer_filaments, metadata, normalized_xml:str,
gcode_bytes, includes_purge=None, quantity=estimate. Filament fields:
filament_id, logical_material, used_g:str, mass_mg:int, used_m:Decimal|None,
tray_info_idx, color, type, mass_provenance. Exact Decimal HALF_UP, no silent0.
14 tests/66 subtests, 11 XML fixtures + real two-colour3MF.
G-code opaque; no durable parser store/job association/UI/FTPS or debit yet.
Документ VERIFIED_SLICE_INTAKE_UK.md. E08.03 done, решта intake partial.

CSV fixes: HA171–172,176–181,183–184,186–188,191–200 (23 rows) AC-H01–05;
HA count211/490anchors, без пустих/дублів. Root SA098/119 виправив невірний
spool return URL у filament/vendor, доповнив App.tsx anchors. E02.03/06partial
до candidate disposition. Не повторювати старі findings як невиправлені.

Повний suite:368passed/331subtests, PYTEST_RESULT0, 32.79s поза sandbox.
Ruff src/tests OK, mypy101sourcefiles OK. Installed EXE/data незмінні.
CSV totals16done/10partial/92planned. Остання перевірка лімітів18%/29%.
Згенеровані окремі standalone JSON Schema2020-12 із поточних Pydantic моделей:
WORKER_PROTOCOL_V1.schema.json для входу, WORKER_PARENT_OUTCOME_V1.schema.json
для parent acknowledgement. Вхідна схема не приймає finalization outcome.

Точна наступна дія: canonical Node proposal entrypoint (не старий calculate
response) і Python adapter із VerifiedSliceFacts через bounded transport,
не втрачаючи logical IDs і mg. Потім G-code preflight/extrusion/partial policy,
durable receipts/evidence/parser store та atomic estimated finalization.
Старий calculate.mjs лише experiment, у встановленому EXE його немає.

### Порогова точка зупинки цього запуску

Фінальна перевірка get_usage_limits: primary used85% (залишок15%), weekly
used71% (залишок29%). Нову розробку зупинено за правилом користувача;
heartbeat ufm активний. Усі агенти завершили свої артефакти, незавершених
тестових subprocess немає. Перевірки 368/331 + Ruff/mypy залишаються чинними:
після них змінювалися лише документація, schema export та чекліст.

Наступний запуск починає зі свіжої перевірки лімітів. Якщо >15%, продовжити
canonical Node proposal adapter; наявний verified intake/transport не переписувати.
E03.08 provenance inventory ще не розпочатий: перевірено лише наявність
linked-stack/haspelsync/LICENSE і THIRD_PARTY_NOTICES.md, власний LICENSE UFM
відсутній. Це не завершений licensing/SBOM крок і не дозвіл публічного релізу.

## Новий запуск після відновлення: canonical proposal та calculated batch WIP

Primary відновився100%, weeklyзалишок28%. Реалізовані
integrations/haspel_calculation.py + haspel_worker.mjs (source-tree entrypoint
імпортує ../../../linked-stack/haspelsync/src/gcode.js). Full exact metadata mg;
partial per-logical range, без profile/color merge та global fallback.
Виявлено й виправлено 5mg loss на повному покритті через JS round; completed
ranges повертають exact source mg. Preview confidence0/needs_mapping, no debit.
4 Node integrationtests/6subtests; Ruff+mypy OK після literal type/import fix.

Написаний application/calculated_finalization.py, але ще НЕ ПРИЙНЯТИЙ:
агент test_calculated_finalization створює один новий test file; потрібні
targeted+full acceptance до позначення ready. Default policy disabled,
окремі allow_unknown_purge/range_partial/manual_splits. Строгі persisted
THREE_MF/ESTIMATE evidence/provenance, logical total, closed physical scope,
stock/measurement/reservations guards, one UoW batch/replay result hash.
Manual multi-segment split вимагає source MANUAL_CONFIRMED_SPLIT,
estimated_usage і AuditEvent correlation segment:{id}:allocation, event
print.allocation.confirmed, entity_type material_usage_segment, parameters
allocation_mg(int)/file_sha256. Автоматичних layer-based splits ще немає.

Clean architecture: DTO facts у application/dto/slice_facts.py, WorkerScope
у application/dto/worker_protocol.py (compat reexports з integrations).
Нові ports/calculation.py SliceFileReader/SliceCalculator, constructor
CalculatedFinalizationCommands(..., policy, *, file_reader=inspect_3mf_file).
JSON provenance та description domain fields відображають ВЖЕ НАЯВНІ колонки
v1; schema/migration не змінені. Repositories/ports додали ledger.for_command,
ledger.for_job, decisions.evidence_links_for_finalization,
reservations.for_finalization для replay integrity. Tests create_scope helper
має with_evidence=False (defaultTrue) для нового fixture без actual evidence.

Незалежний review_calculated_finalization не знайшов confirmedcritical bug;
не примушувати receipt.event_key==occurrence — це різні source identities.
Root додав received_at>=terminal, replay processed_at==record.completed_at,
receipt.received_at у requesthash. Старі регресії43passed/112subtests;
Qt history estimate label uk/en vs PRINTER — 5passed; Ruff src і mypy106files OK.
Повний suite368/331 — ПОПЕРЕДНІЙ, до цих нових domain changes; повторити після
acceptance нового batch. Installed EXE/realdata не змінені.
CSV WIP:16done/11partial/4inprogress/87planned. Не закривати E09 до тестів.

## Приймання calculated batch і durable receipt intake

2026-10-27: root прийняв файл tests/integration/test_calculated_finalization.py
від перерваного агента; виправив mandatory expected_sha256 fixture та тест,
який помилково намагався UPDATE immutable evidence. Тепер перевіряється
SQL rejection такої зміни й replay conflict з append-only replacement evidence.
6 tests / 2 subtests пройшли, включно з real Node. Агент файл більше не редагує.

Новий root-owned test_calculated_batch_edges.py: 7 tests: same-spool split
sequential balances/one settlement, two-spool atomic batch, second spool
shortage no writes, missing audit rejection, failed partial, zero cancelled
reservation release without zero ledger, concurrent asyncio delivery one result.
Виправлені тільки fixture cleanup (не викликати IsolatedAsyncioTestCase.doCleanups
без runner) та []/() test assertion; accounting production код цих тестів не мінявся.
Повний suite: 396 passed / 364 subtests, PYTEST_RESULT0, 36.45s; Ruff clean,
mypy107sourcefiles clean. Snapshot реальної бази/installed EXE не змінені.

application/receipt_ingestion.py: strict v1 status/job/slots durable receipts,
raw SHA only, sanitized_metadata<=64KiB, scoped identity and immutable-body
guard у repository. pending queue, processed replay, raw/semantic conflict,
двопотоковий duplicate intake: 7 tests/15subtests pass. Domain receipts
sanitized_metadata maps existing v1 column; schema unchanged. Не consumer/reducer;
conflicts наразі exceptions, persistent reconciliation task ще потрібний.
DURABLE_RECEIPT_INTAKE_UK.md містить обмеження.

Synthetic real Node→calculated SQL→manual 1mg→missing-file replay smoke успішний:
.runtime/calculated-smoke-8c01d92a-f1be-48d9-b0b0-60af7c314a10, final987654mg.
Kernel default disabled, no live UI/worker boot, source Node imports own
HaspelSync pure calculator source-tree; bundle не перебудовано.
CSV19done/15partial/84planned. E07.01/E09.02/E09.05 accepted; E09.01/04/06partial.
Ліміти після етапу35%/18%; наступне — process-crash/thread/restart acceptance,
multi-material, negative scope/measurement/reservation cases; потім live reducer.

### Crash/concurrency приймання нового ядра завершене

Додано ще 6 batch tests (тепер13): два потоки з barrier перед калькуляцією,
реальний Node subprocess os._exit(39) до і після SQLiteUnitOfWork.commit,
відновлення/replay без другого debit, два logical materials однакового кольору,
чужий резерв, пізнє зважування та incomplete evidence batch. Fixture multi-material
спершу змінює material identity другого segment, потім розширює інтервали:
попередній зворотний порядок правильно відхиляв schema history.interval_overlap.
Фінальний повний suite402passed/366subtests, PYTEST_RESULT0,39.42s.
E09.06accepted, counters20done/14partial/84planned; E09.01 лишається partial
через standaloneGCODE/SLICER. Ліміти30%/18%; продовжуємо durable conflict routing.

### Durable receipt conflict routing

Агент receipt_conflict_review зробив вузький read-only review; змін не робив.
Root реалізував OPEN/ERROR task dedupe receipt:{uuid}:payload_conflict з
reason RECEIPT_IDENTITY_PAYLOAD_CONFLICT і сталим suggested action; commit
перед IdempotencyConflict, оригінальний receipt/stock не змінюються.
Обидва finalization ядра блокують новий debit за відкритої задачі; prior replay
перевіряється раніше та лишається безпечним, навіть за пізнішого конфлікту.
Задача не містить payload/eventkey/secrets. Repository partial unique OPEN/
IN_REVIEW + BEGIN IMMEDIATE серіалізує parallel conflicts; після resolution
нова подія може підняти нову задачу. Не додавали schema або receipt override.
Нові tests: commit failure не прихований, parallel conflicts/reopen,
actual/calculated guard, after-commit conflict replay. Повний suite407passed/
366subtests,39.56s, PYTEST_RESULT0; Ruff+mypy107files clean. Ліміти27%/17%.
Counters20done/14partial/84planned. Далі E08.04 strict offline G-code subset,
потім E07 lifecycle reducer; EXE/live automation/default policy не змінені.

### E08.04 strict offline G-code preflight

Root додав integrations/gcode_extrusion.py + test_gcode_extrusion.py;
marlin-linear-v1 explicit dialect/sha, Decimal mm buckets tool/layer,
G21/T/mode required, M82/M83/G90/G91/G92, G0..G3 E, retraction debt
не рахує recovery двічі, T invalidates absolute coordinate until G92.
Semantics checked official Marlin M82/G90/G92; docs links saved.
Unknown commands/modes/vendor macros rejected, no mass/stock/evidence output.
Bounded64MiB/2Mlines/4KiBline/65536buckets, UTF8/StringIO, safe errors.
6tests/22subtests pass, Ruff/mypy108files pass. Agent gcode_subset_review
read-only review pending; full suite next. See GCODE_EXTRUSION_PREFLIGHT_UK.md.
CSV E08.04partial; counters20done/15partial/83planned. Limits25%/17%.

### G-code preflight verification checkpoint

Незалежний агент gcode_subset_review не знайшов concrete correctness defect;
обмеження geometric execution/firmware/tool-change moves зафіксовані.
Full suite413passed/388subtests,39.77s, PYTEST_RESULT0; Ruff/mypy108files clean.
Runtime gcode_compatibility.py прогнав 3 own HaspelSync real3MF fixturesplate1:
verified intake accepted, strict extrusion parser усі відхилив gcode.line_invalid.
Report .runtime/gcode-compatibility-20261027.json містить archive/gcode SHA,
без source contents. Не вважати це підтримкою Bambu G-code. Bounds незмінні.
Наступне: дослідити причину line limit без blind relaxation; E07 lifecycle
reducer і durable parser artifacts ще відсутні. Kernel в EXE не підключений.
Ліміти останньої перевірки22%/16%; нова перевірка перед наступним етапом.

### Bounded comments, canonical calculation schema і reuse notice

Встановлена причина line_invalid усіх3Bambufixtures: comment-only рядок51,
6792bytes, без control chars. Замість розширення command grammar додано
MAX_COMMENT_BYTES16384 лише для рядків, що починаються ; після whitespace;
MAX_LINE_BYTES4096 для commands незмінний. Новий тест доводить no-motion
для довгого metadata comment, giant comment/command reject. Тепер7tests/
24subtests; реальні3fixtures доходять до gcode.command_unsupported.
Поточний report перезаписаний із SHA/reason, вихідні файли не змінювались.
Фінальний повний suite414passed/390subtests,40.10s,PYTEST_RESULT0;
Ruff/mypy108files clean. Після цього лише docs/schema export, productioncode
не змінювався. Окремий CALCULATION_REQUEST_V1.schema.json експортований із
CalculationRequest, JSON roundtrip/extra fields/XML limit перевірені;
WORKER_PROTOCOL_V1_UK.md актуалізований щодо canonical worker і durable intake.

THIRD_PARTY_NOTICES.md виправлено: own local HaspelSync1.3.4-local.1 engine
це executable reuse, не research-only. package licenseGPL-3.0-only, повний
LICENSE перевірено; gcode.js завантажує локальні helpers та installed
adm-zip0.6.1/basic-ftp6.2.3 (обидва metadataMIT). Не називати це повним SBOM
чи дозволом релізу; UFM own license ще не обраний. E03.08partial, counters
20done/16partial/82planned. Ліміти останньої перевірки19%/16%.
Далі E07 lifecycle reducer/durable parser artifacts; E08.04 Bambu dialect
за fixtures. Installed EXE/real DB незмінні, default calculated policyFalse.

## Порогова зупинка: weekly remaining15%

Фінальна перевірка get_usage_limits: primary used83% (залишок17%), secondary
used85% (залишок15%). Нову розробку припинено за правилом користувача;
heartbeat ufm лишається активним, без купівлі/reset credits.
Обидва нові допоміжні агенти завершили read-only reviews; фонових тестів немає.

Перед порогом почали контрольну wheel збірку:
./.venv312/Scripts/python.exe -m build --wheel --no-isolation --outdir .runtime/wheel-acceptance
Вона НЕ УСПІШНА: sandbox Windows Temp input.json PermissionError13/WinError5,
до побудови wheel. Після відновлення >15% ОБОВ’ЯЗКОВО повторити цю саму
важливу команду з require_escalated, не змінювати TEMP для обходу. Далі
offline import-origin/resources/migration check extracted wheel поза checkout.
Старі dist/installed EXE не перебудовувались, наявні артефакти не видалялись.

JOB_LIFECYCLE_NEXT_CONTRACT_UK.md фіксує наступний reducer пакет: окремий
durable projection marker і finalization state, stable scope across reconnect,
no invented start/plate/tool, неоднозначні runs→reconciliation; completed_layers
COUNT не можна прямо копіювати в current_layer або +1 на останньому шарі.
JobMessage ще бракує plate/material/timestamp provenance; спочатку versioned
contract/schema рішення, потім reducer. Це підготовлений контракт, не код.

Останній повний suite414passed/390subtests, Ruff clean, mypy108files clean.
Після них змінені лише docs, schema export, runtime diagnostics та notices;
нових productioncode changes немає. CSV20done/16partial/82planned,118uniqueIDs.
Реальна база/секрети/backup/own HaspelSync збережені; commit/push/deploy не було.

## Відновлення після reset: 2026-10-28

get_usage_limits показав100%/100%. Обов’язковий повтор wheel build із
require_escalated успішний; scripts/check_worker_wheel.py новий offline
extracted wheel -I import/resource/migration smoke також пройшов. Firstreport
.runtime/wheel-acceptance/report.json, SHAe7c99c092fbbd00fa9cbd03fb8c4ab2449476219bef5086273d679ac84ea234b,
122entries, revision0001. Node/engine не bundled, EXE не змінено.

Graph navigation query job/receipt/identity/alias/migration/projection дав
truncated1800token neighborhood; актуальність перевірена прямими source reads,
graph не перебудовували. Два вузькі агенти розведені за файлами:
migration_constraints — models/projection, schemaimport, guards, frozen0002,
migrate verifier/snapshot, migrationtests/check_wheel revision; root їх не редагує.
lifecycle_contract_audit — лише test_job_projection.py (13 acceptance cases).
Root — domain job_projection entities/exports, ports, entities repositories,
UoW, application/job_projection.py/job_conflicts.py та finalization blockers.

Новий marker окремий від receipt.processing_result, terminal лишається PENDING;
queue anti-join marker, excludes active receipt identity conflict. Observation
state з count0..1e12, ніяких current_layer/source timestamp/plate/tool guesses.
Firstterminal sticky, chronology observed_at (sequence лише metadata), conflict
job:{id}:lifecycle_conflict блокує обидва ядра. Legacy alias не adoption.
Два logical occurrences/epoch не merge; simultaneousactive→tasks для обох.
Root files Ruff/mypy113sourcefiles clean. Приймання WIP не завершене;
новий fullsuite після agent tests, потім wheel rebuild із новою revision.
Counters20done/17partial/3inprogress/78planned. Реальна БД незмінна.

### Job projection v1 / additive0002 прийняті

Агент migration_constraints завершивmodels/projection.py, schemaimport,
guards, frozen0002(16DDL), revision-aware migrate +backup_root optional,
migration21tests/27subtests. Frozen0001 untouched. Terminal shape parity
виправлена до finalacceptance: emptytuple тількиnonterminal, terminalseen==observed.
SQL8fields terminal guard (IS NOT) та immutable marker/scopeguards прийняті.
Agent lifecycle_contract_audit написав15tests/5subtests, rootappreview знайшов
deleted/futurecursor; root додавfailclosed, agent regressiontests pass.
Root repository додатково freeze print_job_id і terminalfacts приsave_state.
Root3crash/queue tests/5subtests: os._exit before/aftercommit, replayoneapplication,
blocked receipt skip until manualresolution, terminalrepo mutationreject.
Root4new financialtests: differentreceipt lifecycleconflict blocksactual/
calculated debit; afterfinalization conflict permits safe unchanged replay.

Full suite448passed/427subtests,48.04s,PYTEST_RESULT0; Ruff clean,
mypy113sourcefiles clean. Rebuilt wheel offline smoke8origins/v2migration/
queue/resources pass; SHA2024d49ee7ea5304f411f39a4b1dc83eeb8f1060679fc54ceb4806d2060767a9,
128entries. Old installedEXE/real DB untouched, Nodeengine stillsource-only.
JOB_LIFECYCLE_PROJECTION_UK.md documents acceptedscope +remainingbinding/livework.
Known drainqueue issue: unavailable/malformed/future receipts rejectedwithoutmarker
needskip/backoff/quarantine in actualworker; don'tspinfirst100forever.
Counters22done/20partial/76planned,0inprogress. Source-levelE07.02/06done;
E07.03/05 andE16.06partial, live/source timestamp/material/cutover gaps preserved.
Freshlimitlast50%/92%; next verifylimits then durable parser artifactstore.

### Verified artifact store та job/plate binding прийняті

Agent migration_constraints працював лише над двома новими файлами
integrations/slice_artifact_store.py таtest_slice_artifact_store.py:
14passed/14subtests; OSlock(msvcrt/fcntl), stagingfsync/rename, nooverwrite,
boundedread/currentparser+canonicalmanifest revalidation, processcrash,
twoprocesses, Windowsjunction. Не OSsandbox/powerloss guarantee.
Root додав ports/slice_artifacts.py structuralport і application/slice_binding.py:
bind_local(...manual_confirmation=False)/resolve, immutableAudit+jobfileplate
oneUoW, cacheIO outsideDBlock+CAS fingerprint, no financial writes.
Agentlifecycle_contract_audit зробив10tests/6subtests, уproductionнеписав.
Root test_slice_binding_accounting.py realNodecache→ledger12345mg/replay,
після видаленняsource/reopen. Full473passed/447subtests52.61s;
Ruff/mypy116files clean. Потім strict request/metadata parity hardening
повторено11bindingtests/6subtests; newfullsuite разомізdrain попереду.

Agentlifecycle_contract_audit зараз володіє projection_drain.py таокремимиtests:
boundedrun_once, ProjectionRejected→dedupreceiptquarantine task, не ловити
persistence/unexpected failures, не позначатиreceiptPROCESSED. Root змінив
JobProjections.pending: filterenabled/undeletedprinter і excludesopen task
receipt:{id}:projection_rejected поручізidentityconflict. Це усуває майбутній
badreceipthead starvation; дочекатисяagenttests+full acceptance.
Counters23done/19partial/76planned. Latestlimit25%/88%, checkbeforecostlystep.
Currentwheel ще попередній128entries0002 безnewartifact/binding/drain modules;
rebuild+offline smoke передуспішнимreport. РеальнаDB/EXE незмінні.

### Bounded drain + фінальне приймання поточного source

Agentlifecycle_contract_audit завершивтількиprojection_drain.py іtests:
7passed, scopedRuff/mypyclean. Rootспільнийprojection_rejection_key іguards
обохfinancialkernels додав: ownquarantinedreceipt не дозволяєnewdebit;
2новіtests. Strictbindingmetadata/requesthash parity теж включенийуfullsuite.
Фінальнийfull482passed/447subtests54.09s,PYTEST_RESULT0; Ruff clean,
mypy117files clean. Rebuiltwheel132entries11module origins/v2migration/
queue/verifiedartifactreload/Decimal passes outsidecheckout. SHA
efa11934b6700c32da6900acff2683f70bd73247e2953c17c62da928a6f8be34,
report.runtime/wheel-acceptance/report.json. Installed EXE unchanged.

Поточнеобмеженняпередlive: quarantineвід knownoccurrenceіншогоreceipt треба
зв’язатизjoblifecycle blocker; передquarantinecommit rereadmarker/receipt
протидвохworker races. RootзафіксувавgapіE07.06done→partial замістьclaim
повноїавтоматизації. Counter22done/20partial/76planned,118IDs. E08.06done,
E07.02done, E07.03/04/05/06partial. Даліцейnarrowguardпакет, потімverified
sourcetiming/material/slotbindings/providerboot/owner-cutover. Не вмикатиlive.
Latestlimits17%/87%; перевіритипереднаступниметапом, поріг15% залишку.

### Точна наступна дія для quarantine scope

QUARANTINE_SCOPE_NEXT_UK.md уточнюєщоknownjoblookupсампособінедостатній:
future quarantine можепередуватиalias. Потрібен canonical scoped-run digest
blocker(provider/printer/PRINTER/epoch/occurrence) зперевіркоюобомаkernels,
receipt reread/marker recheck підновимUoW передquarantinecommit, явнеmanual
resolutionпов’язанихtasks. Не реалізовано, E07.06partial. Не мінятиtest-backed
currentcontracts або вмикатиlive до цього narrowacceptance.

## Порогова зупинка 2026-10-28: primary remaining14%

get_usage_limitsprimary used86%/weeklyused14% → залишки14%/86%.
Нову розробку зупинено, вже запущений regressionprocess завершено й результат
збережений:484passed/452subtests54.70s,PYTEST_RESULT0; жоднихpendingtestprocess.
Ruff clean, mypy117sourcefiles clean. Останніймалийкодпакет передпорогом:
application.job_conflicts.run_quarantine_key(alias), чистийscope digesthelper,
2unit tests/5subtests, no integration yet. Public job/file IDs/filename не key.
Готовий запуск2-гоетапу: wire цьогоhelperуdrain/quarantine таbothkernels,
race rereadmarker/receipt, explicitmanualresolution; див.QUARANTINE_SCOPE_NEXT_UK.md.

ПеребудованийcurrentwheelSHAf23dc261b5be6c565c2a67fbb34dba36775fceb886528e6b6d465718491150b9,
132entries,11importorigins/v2migration/artifactreload/queue smoke успішні,
report .runtime/wheel-acceptance/report.json. Installed EXE/real DB не
оновлювалися; v1 data не мігрували; secrets/backups/own Haspel source збережені.
Node/engineнеbundled, sourcepolicy defaultFalse, no live accounting activation.
Counters22done/20partial/76planned,0inprogress,118uniqueIDsUTF8BOM.
Обидва допоміжні агенти завершили артефакти; нові не запускати доfreshlimits.
Heartbeatufm лишаєтьсяактивний; кредити/resetнекупували,commit/push/deployнебуло.
Після відновлення обохлімітів>15% продовжитиguardпакет, не повторювати
прийняті migration/store/binding auditsабоwheelbuildбезновихзмін.

## Cross-receipt run quarantine прийнятий: 2026-10-28

Fresh get_usage_limits дозволив роботу (початковий залишок87%/82%). Реалізовано
run-level quarantine у `application/projection_drain.py`: новий UoW використовує
SQLite `BEGIN IMMEDIATE`, повторно читає receipt та projection application, і
пропускає хибне quarantine, якщо інший writer уже застосував receipt або
accounting перевів його в PROCESSED. Для JobMessage scope звіряються printer,
epoch та event type зі сталим receipt; лише точний
provider/printer/PRINTER/epoch/occurrence створює hash-only run blocker. Невірні
повідомлення лишаються receipt-only. Точний alias за наявності додає print_job_id;
майбутній alias, створений після quarantine, має той самий blocker key.

`run_quarantine_key_for_scope` спільний із alias key; обидва ядра actual та
calculated перевіряють run blocker тільки для alias відповідного receipt.
`ProjectionQuarantineResolution.resolve_task` дозволяє ручне закриття однієї
receipt/run задачі лише з нотатками та audit event. Кожна пов’язана задача
закривається явно; звичайні події blockers не очищають. Нативний екран ручного
resolution ще не підключений. Після FINALIZED попередній replay лишається
безпечним і без змін ledger.

Нові перевірки:13 projection drain tests; actual і calculated kernels мають по
2 run blocker/replay acceptance tests. Додані race recheck для marker та
PROCESSED, справжнє паралельне interleaving: один worker дочекався, поки другий
застосує receipt, перш ніж виконати quarantine recheck; quarantine перед alias,
пізніше створення alias, ізоляція іншого occurrence, явні resolution/retry.
Full suite494passed/452subtests (54.07s),
Ruff clean, mypy117 source files clean. `ruff --fix` змінив лише сортування
імпортів. Acceptance wheel rebuilt and checked outside checkout:132 entries,
11 module origins, revision0002, parser artifact reload; SHA256
`1f1175e2466855dd16c6f8f8b42b1fd4a01dc85c05879b3fea604a160e1c90b1`.
Початковий невірний виклик wheel checker завершився usage error після успішної
збірки; коректний виклик із `wheel --report` пройшов.

Документація: `PROJECTION_DRAIN_UK.md`,
`QUARANTINE_SCOPE_NEXT_UK.md`, `WORKER_WHEEL_ACCEPTANCE_UK.md`. CSV:23 done,
19 partial,76 planned,0 in progress,118 unique IDs with UTF-8 BOM. E07.06
закритий для durable source contract; E07.04/05 лишаються частковими через
відсутність live MQTT/reconnect/provider/hardware acceptance. Наступне за
залежностями: verified source timing, plate/material/slot bindings, контрольний
provider boot; не вмикати writer cutover.

Installed EXE, реальна база та власні зміни HaspelSync не змінювались. Node
engine не bundled; calculated policy default-disabled; live writer вимкнений.
Останній перевірений залишок Codex:73%/80%. Reset/credits, commit/push/deploy
не використовувалися. Перед наступним коротким етапом знову перевірити ліміти.

## Start-time provenance DTO boundary — 2026-10-28

Перевірив Bambu LAN та наявні HTTP printer adapters: усі формують `observed_at`
на час читання відповіді; жоден із перевірених adapters не підтверджує фізичний
час початку. `PrintJobSnapshot.exact_started_at` вже був nullable, але не
вимагав походження. Додано `exact_started_at_source` з дозволеними значеннями
`printer_reported`/`provider_reported` та fail-closed парну перевірку; одне без
одного або невалідне джерело відхиляється. Bambu regression test підтверджує,
що adapter лишає обидва поля NULL. Новий `tests/unit/test_printer_job_time_provenance.py`:
2 tests/3 subtests; provider subset:13/3; full suite496/455 за53.57s; Ruff
`src tests` clean; mypy117 files clean.

Rebuilt wheel у `.runtime/wheel-acceptance-20261028-timing-provenance`, 132
entries,11 module origins, existing offline smoke успішний; SHA256
`f3ec539fc7864e7e83e51f35e2b9a1fa4dfe00427e2b12103d4aa121a1485aa5`, report
поруч. Node engine не bundled. Зміна лише vendor-neutral in-memory DTO; durable
JobMessage v1, migration0002, ledger, UI та installed EXE не змінені.

E07.05 лишається частковим до реального MQTT reconnect/hardware. Plate/material/
slot binding і контрольний provider boot не реалізовані цим пакетом; поточні
Bambu trays дають tray UUID/tag/type, але assigned spool та remaining mass
unknown, `complete=False`, а job snapshot не має verified plate. Далі перевірити
контракт прив’язки occurrence→verified 3MF plate→slot/spool mapping і провести
контрольний read-only provider boot з fixtures/fakes; не робити writer cutover.
CSV залишається23 done/19 partial/76 planned/0 in progress,118 IDs/BOM.
Останній перевірений залишок Codex:67%/79%. Перевірити ліміти перед наступним
пакетом. Реальні БД, EXE, HaspelSync, secrets і backups недоторкані.

## Exact trusted spool identifier lookup — 2026-10-28

Перевірив topology: `SpoolIdentifier` і SQLite `spool_identifier` уже існували,
але application UnitOfWork не давав exact lookup. Додано read-only
`SpoolIdentifierRepository.by_trusted_identity(namespace, kind, value)` із
точним трьохскладовим пошуком та фільтрами verified_at != NULL, retired_at IS
NULL і deleted_at IS NULL. Port не виставляє створення/підтвердження ID; наявна
таблиця/міграція не змінені. Інтеграційний тест на локальній тимчасовій SQLite
перевіряє trusted selection, урахування kind і точність значення, відкидає
unverified та retired rows. Inventory suite35/31; Ruff clean; mypy117 clean.

E11.02 переведено у `Частково виконано`; CSV:23 done/20 partial/75 planned,
118 unique IDs із UTF-8 BOM. Немає ручного/RFID enrollment UI, алгоритму
slot-snapshot→trusted identifier→SpoolMount, і поведінки конфліктів/знятих
ідентифікаторів; lookup не створює mount і не торкається ledger. Full suite
496/455 був до lookup-пакета, тому потрібен повний повтор; після цього source
змінився і wheel також потребує перебудови. Останній wheel для DTO checkpoint:
SHA256 `f3ec539fc7864e7e83e51f35e2b9a1fa4dfe00427e2b12103d4aa121a1485aa5`;
він не містить цього lookup коду. Ліміти перевірені: останок65%/79%.
Наступна конкретна дія — explicit verified 3MF logical-material to confirmed
slot/spool mapping, потім контрольний read-only provider boot; без writer
cutover, installed EXE або real DB changes.

## Read-only trusted slot identity resolver — 2026-10-28

Додано `application.slot_spool_identity.resolve_feed_slot_spool`. Він читає
лише provider namespace та `FeedSlotSnapshot` exact `tray_uuid`/`tag_uid`,
викликає read-only `SpoolIdentifierRepository`, ще раз звіряє returned record із
запитом і перевіряє verified/current/not-deleted. Одна spool ID → MATCHED;
немає точного confirmed ID → UNKNOWN; tray/tag, що ведуть до різних котушок →
CONFLICT без кандидата. Колір/тип не читаються. Немає mount/reservation/ledger
write. `tests/unit/test_slot_spool_identity.py`:4 tests, включно з двома
узгодженими ID, conflict, unknown та untrusted port response; реальна тимчасова
SQLite exact lookup acceptance у test_inventory_commands.py.

Повний suite501/455 (51.96s), Ruff `src tests` clean, mypy118 source files clean.
Acceptance wheel rebuilt/check outside checkout; report
`.runtime/wheel-acceptance-20261028-slot-identity/report.json`, 133 entries,12
module origins включно з resolver, revision0002, canonical MJS/parser artifact/
Decimal smoke successful; SHA256
`ba7d3c113a0ad74ac5b45f8dcd3bccbddf85d6271bbbd18218d5560485083304`.

E11.02 частковий: таблиця identifier мала потрібні дані, тепер є exact query і
resolver; не існує UI enrollment/ручної верифікації, реального provider snapshot
→ persistent FeedSlot → mount, logical 3MF material→selected slot policy чи
RFID reconnect/reassignment acceptance. E07.05 залишається частковим за
часом/живим MQTT. Останній залишок Codex63%/78%. Наступний короткий крок —
перевірити, чи `MaterialUsageSegment`/calculated finalization вже здатні
атомарно представляти explicit logical-material/slot/spool binding; не
дублювати існуючий контракт і не вмикати live writer.

## Provider boot cleanup та mapping contract review — 2026-10-28

Під час контрольного review підтверджено, що `probe_configured_printer` читає
profile/secret, підключає provider, повертає status+current job та не пише
inventory; виправлено cleanup: `disconnect()` тепер гарантовано викликається,
навіть коли `connect()` падає. Те саме закриття додано після endpoint check у
`configure_local_printer`. Regression test інжектує помилку connect і доводить
disconnect без get_status/get_current_job. Bambu та HTTP provider integration:
18 passed/5 subtests. Повна перевірка після всіх змін:501/455, Ruff `src tests
scripts` clean, mypy118 clean.

Wheel rebuild і isolated check успішні: `.runtime/wheel-acceptance-20261028-provider-cleanup`,
133 entries/12 imports, canonical MJS, migration0002, parser artifact reload;
SHA256 `f15c5b262f02f592ba806a9246def3d63f42697f9ba6ce00f38c0aa8cfea3c80`.
Node engine ще не bundled. E06.02 переведено в partial: add/probe/remove,
TLS trust metadata та secret reference присутні; in-place profile editing і
hardware acceptance не підтверджені. CSV:23 done/21 partial/74 planned/0 in
progress,118 IDs/BOM.

Перевірено mapping: `PrintJobMaterial.tool_index` зберігає логічний канал;
`TopologyCommands.mount_spool(material_id=...)` створює `MaterialUsageSegment`,
що пов’язує material→tool→FeedSlot→SpoolMount→Spool з часовим інтервалом.
Actual та calculated finalization уже вимагають завершене покриття сегментів,
узгоджені tool/printer/slot/mount IDs та валідний mount interval. Не додавав
дубльований сегментний контракт. Ще нема шляху provider snapshot→оновлення
FeedSlot/mount і explicit 3MF logical filament mapping на UI. Наступна мала
реалізація: audited explicit confirmation для довіри spool identifier (з
відсутнім enrollment UI), потім під’єднати resolver до read-only device view;
не створювати mount автоматично і не змінювати ledger.

## Audited spool identifier confirmation та checkpoint recovery — 2026-10-28

Додано `SpoolIdentifierCommands.verify`: потрібне явне boolean підтвердження;
namespace/kind/value приймаються як точні значення без нормалізації; текст із
пробілами по краях/control characters відхиляється. Перепризначення вже
довіреної ідентичності іншій котушці завершується conflict. `command_key`
захищає ідемпотентний повтор, а audit parameters зберігають request hash
замість відкритого значення ідентифікатора. Це лише enrollment команди:
автоматичне створення mount, reservation або ledger debit відсутнє.
`tests/integration/test_spool_identifier_commands.py`:4 tests/3 subtests.

Повний suite:505 tests/458 subtests; Ruff `src tests scripts` clean; mypy119
source files clean. Offline acceptance wheel має134 entries/13 імпортованих
модулів, включно з command; migration0002, queue, parser artifact reload,
Decimal і canonical MJS smoke успішні. SHA256
`ee2f6a01031af4b9442382cfc403a828174b14f9364d8963af4e7c0199111ef8`, report
`.runtime/wheel-acceptance-20261028-identifier-confirmation/report.json`.

Під час оновлення CSV стався локальний збій кодування/серіалізації; файл було
відновлено з `INTEGRATION_STEP_BY_STEP_UK.md` і збережених 72 перших записів.
Перевірка підтвердила 118 унікальних кроків і UTF-8 BOM; лічильники відновлені
23 done/21 partial/74 planned. E11.02 partial: немає UI enrollment та
feed-slot→spool mount. E11.03 partial: сегментна модель існує, але provider,
layer-boundary й AMS rollover acceptance ще немає. E16.06 лишається partial:
перерване оновлення та pre-migration restore не перевірені. CSV змістовно
зіставлений із планом; нові кроки E11.02+ без збережених доказів мають
початковий запланований статус, крім цих трьох часткових пунктів.

Останній ліміт після wheel: залишок56%/77%. Наступний крок — read-only
відображення MATCHED/UNKNOWN/CONFLICT та fake-provider acceptance; не створювати
mount автоматично, не змінювати installed EXE або реальну БД, не вмикати live
writer. Залишити E11.02/E11.03 частковими до повного acceptance.

## Read-only підтвердження feed-slot mapping у Qt — 2026-10-28

Кнопка «Прочитати стан» у UFM Studio тепер повертає статуси та окремий список
feed-slot зіставлень. Для кожного snapshot слот резолвиться лише exact
`tray_uuid`/`tag_uid` у verified/current identifier repository; MATCHED показує
назву котушки, UNKNOWN — відсутнє підтвердження, CONFLICT — зупинене
неоднозначне зіставлення. Сирі UUID/tag UID у текст UI не виводяться. Області
обліку не змінюються: немає mount/reservation/ledger write, а feed-slot
snapshot не персиститься. Для Bambu namespace — `bambu`; інші адаптери мають
власні namespace та показують лише знайдені exact mappings.

Новий `test_printer_probe_shows_only_verified_spool_matches_read_only` проганяє
fake provider із matched, unknown і conflict слотами; доводить відсутність
ідентифікаторів у UI та незмінність ledger. Qt suite:6 passed; повний suite
506 passed/458 subtests; Ruff `src tests scripts` clean; mypy119 source files
clean. Wheel `.runtime/wheel-acceptance-20261028-feed-slot-view`:134 entries,
13 module imports, isolated migration/parser/worker smoke успішний; SHA256
`55de1ade94054fe6f7a0497a1bfc5cdc37b0bba10d8a479c16a9f2ecb97ddb5b`.

CSV перевірено після попереднього відновлення:118 унікальних ID, UTF-8 BOM,
23 done/21 partial/74 planned. E11.02 partial: читання ідентичностей у UI є,
але ручний enrollment і persistent slot→spool mount відсутні. E11.03 partial:
немає source-layer/AMS rollover acceptance. Наступна залежна дія — ручний
enrollment UUID/tag із явним підтвердженням та conflict handling, ізольовано
від автоматичного mount/debit. Останній ліміт:52%/77%. Installed EXE, реальні
БД, HaspelSync і секрети не змінювались; live writer не вмикався.

## Явний UI enrollment tray/tag ідентичності — 2026-10-28

Додано кнопку «Підтвердити котушку…». Після успішного status probe UI тримає
лише в пам’яті observed exact tray UUID/tag UID та дозволяє оператору вибрати
один прочитаний ID і spool із локального inventory. Повний ID показується у
фінальному confirm prompt; лише відповідь Yes викликає
`SpoolIdentifierCommands.verify` із новим idempotency key. Список приховує
середину ID (суфікс для розрізнення), а журнали зберігають hash, не raw value.
Якщо немає свіжого status snapshot або inventory порожній, enrollment не
починається. Прив’язка не монтує spool до physical FeedSlot, не створює
reservation і не змінює stock.

Новий Qt acceptance підтверджує явну modal confirmation, точну пару namespace/
kind/value та відсутність mount/ledger side effects; UI suite:7 passed. Full
suite:507 passed/458 subtests; Ruff `src tests scripts` clean; mypy119 source
files clean. Wheel `.runtime/wheel-acceptance-20261028-identity-enrollment-ui`:
134 entries/13 module origins; migration/parser/queue/MJS smoke successful;
SHA256 `2a8c78c3f2f5dadbc1dd6f1f35fac29691b5c5693c1cd829d4a302e3cd240710`.

E11.02 remains partial: observed identity and verified identifier enrollment are
available, but persistent provider feed-slot→domain FeedSlot→SpoolMount wiring
and physical RFID reassignment acceptance are not. E11.03 remains partial for
provider layer/AMS rollover segments. CSV is 118 unique IDs/BOM, 23 done,
21 partial, 74 planned. Next: inspect `TopologyCommands.mount_spool` and
FeedSlot repository contracts; add a separate explicit mount action only if
exact persistent printer/slot identity is already available. Preserve unknown
and conflict states; never auto-mount or debit. Latest limit remaining:50%/76%.
Installed EXE, real DBs, HaspelSync, and secrets unchanged.

## Явний монтаж перевіреного Bambu feed slot — 2026-10-28

Додана окрема кнопка монтування: у списку доступні лише слоти зі свіжого
(не старшого 120 секунд) snapshot, для яких exact verified tray/tag IDs
резолвляться в одну поточну котушку. Оператор додатково підтверджує саме
монтаж. Стабільні UUIDv5 system/slot IDs зв’язують `provider namespace +
printer + provider system key + slot key`; `TopologyCommands.create_external_slot`
розширено optional system kind/provider key/tool_index, залишаючи старі default
семантики. Для AMS збережено kind і provider key, логічний tool index не
виводиться з фізичного номера лотка. Потім `TopologyCommands.mount_spool`
створює mount та audit. Монтаж не списує матеріал і не створює reservation.
Якщо слот зайнятий або spool уже змонтований, topology command відхиляє mount;
детермінований slot creation залишається безпечним для повтору.

Qt acceptance перевіряє, що після status read котушка ще не змонтована; лише
після окремої відповіді Yes з’являються правильні FeedSystem/FeedSlot/SpoolMount,
tool_index залишається unknown і ledger порожній. Stale identity enrollment
понад 120 секунд також fail-closed. Full suite:507 passed/458 subtests; Ruff
`src tests scripts` clean; mypy119 clean. Isolated wheel має134 entries/14
module origins (включно з `ufm.application.topology`); SHA256
`78693b70deebbd34217095de5b096ff343c25b498d5b371c9d05a417972cddd6`; report
`.runtime/wheel-acceptance-20261028-explicit-slot-mount/report.json`.

E11.02 лишається partial: без фізичного RFID reassignment acceptance, live
provider slot reconciliation та 3MF logical material/tool mapping. E11.03
лишається partial до provider-layer boundaries/AMS rollover segments. Наступна
дія — durable snapshot projection у FeedSystem/FeedSlot з observed/received
time та source epoch/sequence; треба визначити fail-closed out-of-order і
reconnect політику, залишивши slot snapshot окремим від assignment та debit.
Останній ліміт:44%/75%; installed EXE, реальні БД, HaspelSync і secrets не
змінювалися; live writer не запускався.

## Durable provider-slot snapshot ordering — 2026-10-28

`TopologyCommands.observe_provider_slot` проєктує status snapshots лише для
вже відомих FeedSlot. Записує observed/received time і source epoch/sequence;
exact replay — duplicate, змінений payload під тим самим ключем — conflict,
старіша sequence/received timestamp — stale. Зміна epoch допускається лише
коли received time зростає. Зберігаються hash snapshot та provenance, не сирі
tray/tag IDs чи приватні значення. Проєкція не змінює assignment, mount,
reservation чи ledger і не створює невідомі слоти.

Acceptance: topology test покриває apply/replay/conflict/stale/new epoch,
збереження mount/assignment і відсутність ledger та сирих ідентифікаторів в
audit. Full suite:508 passed/458 subtests; Ruff `src tests scripts` clean;
mypy119 source files clean. Wheel `.runtime/wheel-acceptance-20261028-slot-snapshot-projection`:
134 entries/14 imports, SHA256
`717be383a08770d51af5a17d1c5d5fbebc5208f941666b2c2f83160795cccfc6`.
CSV зберігає 118 унікальних ID/BOM, 23 done/21 partial/74 planned. Ліміт на
початку checkpoint:41%/75% залишку.

Далі дослідити явне зіставлення логічних матеріалів/інструментів з FeedSlot
на багатоматеріальних fixtures та перевірити межі AMS slot rollover. Не
виводити відповідність із кольору/позиції; не вмикати автоматичний debit або
live writer і не змінювати installed EXE.

## Explicit Bambu logical material → provider slot observation — 2026-10-28

Додано `ProviderMaterialSlotMapping` у read-only `PrintJobSnapshot` та
`material_slot_mappings_from_report()` у Bambu LAN adapter. Mapping створюється
лише з явного `print.mapping`; індекс logical filament збережений окремо, slot
представлений парою provider-system/provider-slot keys. `0xFFFF` зберігається
як `unused`; інші malformed або невідомі значення стають `unsupported`, а
відсутнє поле не породжує fallback. Підтримані targets: AMS unit 0–3, AMS HT
128–135 slot 0 та перший external holder. Другий external holder і невідомі
unit-коди не вгадуються.

Це лише DTO спостереження: він ще не персиститься у job projection/receipt, не
звіряє target із тим самим status snapshot чи verified 3MF і не створює
PrintJobMaterial/segment/mount. `PrintJobMaterial.tool_index` поки залишається
єдиним durable індексом; тому E11.01 частковий, не завершений. E11.02 також
частковий до RFID hardware acceptance, durable matching/reconciliation та
з’єднання з verified sliced facts. Кольори, profile IDs і позиційна евристика
не використовуються.

Перевірка: Bambu provider tests 13 passed/3 subtests; full suite 510/461; Ruff
clean; mypy119 clean. Wheel у
`.runtime/wheel-acceptance-20261028-printer-logical-slot`:134 entries,16
imports, isolated `printer_mapping_decoder=true`, міграція та інші smoke
успішні; SHA256
`40a358c035fba822f8e3c32384d83f015bb94cee6aa1d4795625720732fd1436`.
Ліміт після цього пакета:36%/74% залишку. Наступне: durable contract, що
зберігає logical filament id, tool/extruder і окремий target slot; лише далі
звіряти його з exact identifiers, mounted spool і temporal segments. Не
вмикати live writer/списання та не оновлювати installed EXE.

## Durable source material index — schema 0003 — 2026-10-28

`PrintJobMaterial.logical_material_index` тепер nullable і має bounded domain
0..255 окремо від `tool_index` та `extruder_index`. SQLite migration
`0003_logical_material_index` додає поле з DB CHECK, зберігаючи сумісність
старих записів. Existing v2 migration автоматично створює verified backup
перед DDL; тест перевіряє його revision/data і нову колонку. Repository test
підтверджує logical index 5 разом із tool 0. Це не створює джерело мапінгу й
ще не змінює finalization.

Acceptance: full suite 513 passed/461 subtests, Ruff clean, mypy120 clean.
Wheel 136 entries/16 imports, migration0003 і Bambu mapping smoke пройшли;
SHA256 `317194e73321d1beb33282f6abb7e9d3153499832537e97f3b2873c973c452fb`.
Ліміт після етапу:32%/74%. Наступна залежна дія — durable receipt/job mapping
проєкція з explicit `print.mapping`, точний join з перевіреним slice facts і
FeedSlot та fail-closed результат без matching/при неоднозначності. Не виводити
slot за кольором/порядком; live writer, accounting і installed EXE лишити без
змін до окремої acceptance.

## Durable Bambu logical-material mapping in receipts — 2026-10-28

Worker `JobMessage` now optionally carries a bounded tuple of explicit logical
material→provider slot facts. Every entry is exactly one of `reported_slot`,
`unused`, or `unsupported`; strict validation requires both provider keys only
for a reported slot, and rejects duplicate logical indices. Bambu
`subscribe_events` includes these facts in its event digest/payload, so mapping
changes can produce a new observation. `ReceiptIngestion` persists the facts in
sanitized metadata and includes them in scoped semantic replay/conflict checks.
No tray/tag secrets are in this mapping contract.

Acceptance: protocol/intake/provider targeted 35 passed/41 subtests; full suite
515 passed/464 subtests; Ruff clean; mypy120 clean. Wheel at
`.runtime/wheel-acceptance-20261028-durable-job-slot-mapping`:136 entries,
16 module imports, revision0003 and job mapping contract smoke passed; SHA256
`bc952c2a264f5dac98c04b3380be8cad6a56898cd7ecdc2ff00b6b8725e4538e`.
Latest available limits:29%/73% remaining.

Important boundary: current job projection only updates lifecycle state and
keeps the mapping in the immutable receipt metadata. It does NOT materialize
`PrintJobMaterial`, verify the selected 3MF, check freshness/exact slot identity,
create mount/segments, or touch the ledger. E11.01/E11.02 remain partial.
Next implement a strict same-job 3MF↔receipt↔FeedSlot matching result with
ambiguous/unmapped states, then connect confirmed matches to material rows and
temporal segments. Do not enable live debit or update the installed EXE.

## Same-job receipt/3MF/provider-slot resolver — 2026-10-29

Implemented `src/ufm/application/job_material_mapping.py` as a pure read-only
join. It requires receipt file SHA-256 == verified slice SHA-256, matching
printer UUID, fresh provider status (120s), a fresh complete feed-system
snapshot and a unique explicit provider system/slot key whose occupancy is
reported true. Logical material keys use the verified 3MF's zero-based
`filament id - 1`; tool/extruder indexes, slot ordering, color and material type
are not used. Missing mapping remains UNKNOWN; unsupported remains UNSUPPORTED;
`unused` contradicting nonzero 3MF mass or layer use is CONFLICT. Extraneous
mapping IDs not present in selected plate fail closed. No spool identity query,
mount/material projection, segment, reservation, stock, or ledger write occurs.

Added six decision-path tests. Canonical `.venv312` acceptance: 521 passed,
464 subtests; Ruff clean; mypy121 clean. The alternate `uv run` selected a Qt-free
environment (6 UI tests skipped and unrelated full mypy errors), so use
`.venv312` for this repository's canonical checks. Offline wheel report:
`.runtime/wheel-acceptance-20261029-job-slot-reconciliation/report.json`, 137
members, SHA256
`51392013ad591bbf54dfc9b12c1b6324d43478cd1f2df1134e984d9ca8aa399b`; resolver
import smoke passed. Latest limit snapshot:25%/73% remaining.

Next: review persistence contracts for a strict exact provider key→durable
FeedSlot→active SpoolMount join, with unknown/ambiguous/missing mount represented
as non-match. Then decide whether material rows can be projected idempotently
without accounting side effects, and later bind time/layer segment boundaries.
Do not start ledger writes, automatic debit, installed EXE update, live MQTT,
or physical command acceptance in this step.

## Exact persisted slot, audited payload and mounted RFID spool — 2026-10-29

Added `FeedSlotRepository.by_provider_key(printer_id, provider_system_key,
slot_key)`, scoped by printer and excluding soft-deleted topology. Schema's
unique printer/system provider key and unique slot key keep this lookup exact.
`provider_slot_snapshot_audit_proof()` is shared with the ordering projector so
readback can recalculate the opaque audit request fingerprint from the exact
provider slot snapshot and match the stored `feed_slot.snapshot_observed` event.
This prevents substituting changed RFID payload under unchanged time/sequence.

New read-only `resolve_mounted_material()` accepts a preceding MATCHED job
mapping and the same provider-system snapshot, then requires the exact durable
slot, same observed/received times + epoch/sequence, recomputed audit proof,
ASSIGNED state and one active mount. It checks the currently reported exact
verified tray/tag ID through `resolve_feed_slot_spool()` and requires its spool
to equal the mounted spool; deleted/archived spools and every unknown/conflict
state return no IDs. No new raw RFID values are persisted or logged; no
PrintJobMaterial, segment, reservation, stock or ledger changes occur.

Tests: full `.venv312` suite 524 passed / 464 subtests, Ruff clean, mypy122 clean.
The acceptance wheel `.runtime/wheel-acceptance-20261029-mounted-material-resolver`
contains 138 members and passed isolated smoke including both resolver modules;
SHA256 `5cfdfb1cbb9660b8a2061d50759246ff587d4c8469cc9d928fe6083794a4b3ca`.
Latest limits 20%/72% remaining. CSV remains 118 IDs with E11.01/E11.02/E11.03
partial; counts 23 done /22 partial /73 planned. Next: inspect receipt/job
projection and calculated-finalization contracts to design idempotent material
row projection using logical material separately from tool/extruder, with no
stock or ledger writes. Installed EXE/live writer remain untouched.

## Keep logical material IDs independent from physical tools in estimates — 2026-10-29

The calculated-finalization validation previously keyed proposal/source totals
and estimate provenance with `PrintJobMaterial.tool_index`, making a logical
material index (3MF `filament id - 1`) unusable when it differed from an
extruder/tool. It also prohibited multiple material rows sharing one physical
tool. `_materials_by_logical_index()` now requires complete unique explicit
logical indexes for multi-material jobs and permits a legacy fallback only when
there is exactly one row and one verified 3MF fact. Partial, duplicate, extra,
or missing indexes fail closed. Estimate totals/provenance now use the logical
index, while `MaterialUsageSegment.tool_index` remains checked against the
separate physical tool field. This does not infer the tool↔material relation:
future row projection still requires a provider/parser fact or remains unknown.

Updated the multi-material finalization fixture to carry explicit logical IDs;
unit tests cover two logical materials sharing one tool plus legacy, incomplete,
duplicate and conflicting maps. Full `.venv312`: 527 passed /464 subtests;
Ruff clean; mypy122 clean. Wheel at
`.runtime/wheel-acceptance-20261029-logical-material-finalization/report.json`,
138 members, SHA256
`9b48398bb158aed822f9ca56d02f1756d501cc675de5b6b636c98c1e160fb160`.
Latest limits:15%/71% remaining. CSV 118 IDs/BOM, 23 done /22 partial /73
planned; E11.01/E11.02/E11.03 remain partial. Next: locate an authoritative
logical-material→tool/extruder source (do not infer from G-code T order), then
design idempotent receipt/material projection with no ledger writes. No live
debit, MQTT, installed EXE update, commit or deployment.

## Checkpoint: HaspelSync mapping/refill contract review — 2026-10-29

Read-only evidence from `D:/Filament_Manager/localization/haspelsync/src/AGENTS.md`
and `D:/Filament_Manager/localization/haspelsync/OPEN.md`: Bambu
`print.mapping` has one target per logical project filament; high byte encodes
unit, low byte slot, and `0xFFFF` means unused. It is the printer's authoritative
runtime assignment after possible send-time remapping, must be observed during
the active job, and a change after first layer is a refill boundary. The old and
new slots/spools are needed on either side of that boundary. `tray_info_idx` is
a preset/profile key (generic `GFL99` occurs for chipless spools), not a spool
identity. HaspelSync files were not modified.

This review was the short dependency step after logical-index finalization. The
remaining primary limit is exactly 15%, so stop implementation until the next
scheduled run. Latest acceptance before pause: `.venv312` 527 passed /464
subtests; Ruff clean; mypy122 clean; wheel 138 members SHA256
`9b48398bb158aed822f9ca56d02f1756d501cc675de5b6b636c98c1e160fb160`.
Checklist: 118 IDs/BOM, 23 done /22 partial /73 planned.

Resume at durable per-job mapping observation history keyed by receipt/job and
source sequence, retaining each explicit mapping together with observed time
and completed layer. Distinguish initial pre-layer assignment from post-start
AMS refill, then close/open usage segments only after exact slot→mount→verified
RFID joins. Need independent HaspelSync-derived fixtures/hardware evidence for
vendor event timing. No automatic debit, live writer, or installed EXE update.

## Accepted job mapping history query, with Bambu graph evidence — 2026-10-29

Graph references are now persistent in `AGENTS.md` and this progress file:
`D:/graphify-out/bambu-ufm/HANDOFF_UK.md` indexes local profile, source and
combined Graphify artifacts, scope, provenance and parser limitations. The
source graph query for `print.mapping`/logical filament/AMS slot/refill found
`MachineObject::print_job_filament_mapping` in
`D:/GIT/BambuStudio/src/slic3r/GUI/DeviceManager.hpp` (graph node at L615) and
AMS/filament mapping UI components. Graph evidence was used for navigation;
field references do not alone prove firmware behavior. The UFM source confirms
that `BambuLanAdapter.subscribe_events()` hashes the mapping/progress payload
and increments its source sequence for each changed poll observation at
`src/ufm/integrations/printers/bambu_lan.py` around lines 562–596.

Implemented `JobProjectionCommands.mapping_history(print_job_id=...)` in
`src/ufm/application/job_projection.py`. It joins immutable
`JobReceiptApplication` markers with immutable receipt metadata by job and
receipt IDs, then revalidates printer/epoch/event scope and the original
projection request hash. It returns every accepted (`APPLIED`) observation,
including unchanged/empty mapping reports, sorted by source sequence, while
preserving the logical material→provider slot tuple, sequence, observed and
received timestamps, state and completed layer. Conflicting and stale receipts
are excluded. A bounded 10,000-result query rejects overflow instead of
silently truncating the timeline. No duplicate payload/table, schema migration,
PrintJobMaterial, usage segment, stock or ledger write was introduced.

The reducer now rejects non-stale source sequence regression, a reused sequence
with changed observation facts, sequence/time reversal and mapping changes
after terminal as reconciliation conflicts. Older observations with older
sequence remain `IGNORED_STALE`. This relies on the UFM Bambu adapter contract:
source sequence increments whenever its mapping/progress digest changes within
the same source epoch. This is still application-level observation time, not a
verified physical refill timestamp; exact layer-to-boundary semantics require
independent HaspelSync/hardware fixtures.

Tests added for restart-safe history reconstruction, retaining unchanged
mapping snapshots and completed layers, stale exclusion, source-order conflicts
and no financial side effects. Canonical `.venv312`: **530 passed / 464
subtests**; Ruff on `src`/`tests` clean; mypy reports 122 source files clean.
No package wheel was rebuilt, and no installed EXE, live write/accounting,
external repo, user data or HaspelSync source was modified.

Checklist remains 118 IDs/BOM, 23 complete /22 partial /73 planned. E11.03
remains partial. Next define how mapping snapshots establish layer/time
segments without claiming physical refill time from a poll timestamp, then
connect each side to a fresh exact FeedSlot→SpoolMount→verified RFID join and
add replay/crash tests before any idempotent material-row/segment projection.
Do not turn on ledger debit or update the installed EXE.

Pause checkpoint: after full suite, Ruff and mypy passed, fresh limit snapshot
was 13% primary / 68% weekly remaining. Stop here per the 15% gate. Resume at
the next plan item: define safe use of the accepted mapping history to project
layer/time-bounded AMS/refill segments; first establish physical event timing
with independent HaspelSync/hardware fixtures, then join both sides only to
exact durable slot, active mount and verified RFID spool. Keep E11.03 partial;
do not enable stock/ledger writes or rebuild/update the installed EXE.


## Bambu local occurrence identity checkpoint — 2026-10-29

The LAN identifier question is narrowed but not closed. Bambu Studio local message callback calls MachineObject::parse_json(lan,msg) in D:/GIT/BambuStudio/src/slic3r/GUI/GUI_App.cpp:2345. That parser reads task_id (D:/GIT/BambuStudio/src/slic3r/GUI/DeviceManager.cpp:3219) and subtask_id (:3243) from a local report. This proves Studio consumes these fields on the LAN route, not that every printer exposes them or that either is a durable occurrence ID.

Read-only HaspelSync report fixtures at D:/Filament_Manager/localization/haspelsync/test/fixtures/reports/ show variation: active local P2S has task_id=6456, empty subtask_id, job_id=0; active local H2D has task_id=9012, empty subtask_id, job_id=0; P1S idle fixture has empty task/subtask IDs. Cloud fixtures carry other nonzero combinations and must not be conflated with the local protocol. HaspelSync MQTT PRINT_DELTA_FIELDS excludes task/subtask IDs, so these files do not establish uniqueness across restart, reconnect, or same-file reprint.

Conclusion: nonzero local task_id is a conditional candidate for provider metadata, not safe as occurrence_key yet. Do not synthesize a key from file/display name. Next capture complete consecutive local reports over start -> reconnect -> reprint and determine source_epoch semantics; then add fail-closed event-to-receipt converter only for a proven identity contract. Keep E11.03 partial; no material/ledger writes, assumed physical refill timestamps, HaspelSync edits, or installed EXE update.

Evidence review only; no source code changed. Existing test state remains 532 passed /468 subtests; Ruff and mypy (122 files) were clean at the prior code checkpoint. Latest limit snapshot: 76% primary /66% weekly remaining.


## Bambu report ID metadata checkpoint — 2026-10-29

Implemented optional provider_task_id, provider_subtask_id and provider_job_id in PrintJobSnapshot. The Bambu LAN adapter preserves report values (string or nonnegative integer, capped at 500 characters; blank becomes unavailable) and adds them to PrinterEvent digest. They are not mapped to provider_run_key or external_job_id and are not sent into JobMessage/receipt/ledger. This is an observation-preservation step only.

Targeted provider tests: 17 passed /11 subtests; Ruff clean; mypy 122 source files clean. Full suite: 534 passed /472 subtests in 61.94 seconds. Limit snapshot after suite: 70% primary /65% weekly remaining.

Next: capture or obtain consecutive full raw LAN report traces across job start, reconnect, and same-file reprint; validate task_id/job_id uniqueness and source_epoch behavior, including devices with empty IDs. Then design a fail-closed event-to-receipt converter. Keep E11.03 partial and do not write stock/ledger, treat polling time as physical refill time, edit HaspelSync, or update installed EXE before the identity contract is accepted.


## Receipt scope and restart blocker — 2026-10-29

Further source review found BambuLanAdapter initializes source_epoch with uuid4() at src/ufm/integrations/printers/bambu_lan.py:332. ReceiptIngestion deduplication is scoped by provider_instance_id, printer_id, message.source_epoch, and event_key (src/ufm/application/receipt_ingestion.py:71-74). A process restart creates a new adapter epoch; if an active print is rediscovered, its receipt events occupy a different idempotency scope unless a verified provider occurrence ID correlates it.

The checked-in HaspelSync report fixtures are snapshots, not consecutive traces. They cannot prove task/job identifier stability across start, reconnect, application restart, or same-file reprint. This is now the blocking evidence dependency for the event-to-receipt bridge. Needed: sanitized consecutive raw LAN reports plus printer model and relative timestamps covering those transitions. Until available, preserve IDs only as metadata, keep E11.03 partial, and perform no receipt/debit/ledger projection for Bambu.

No code changed in this source review. Latest verified code checks remain: 534 passed /472 subtests, Ruff clean, mypy 122 files. Limit snapshot before writing this checkpoint: 70% primary /65% weekly remaining.


## Physical Bambu print evidence - 2026-10-29

Read-only evidence source: D:/3D_Druk/UFM_Print_Test/captures/20261029T024215Z/correlation_report.json and events.jsonl. The report says 561 raw packets passed DPAPI/hash-chain and artifact-hash checks, all received at QoS 0; 0 payload parse errors; state IDLE -> PREPARE -> RUNNING -> FINISH; final progress 100%, 50/50 layers, print_error 0. Last/max reported layer is 50. HMAC aliases (not raw IDs) are present for task_id/subtask_id and compare equal across PREPARE, RUNNING, FINISH in this single print. No process restart or same-file reprint was captured; there is one disconnect event without a gap_may_follow flag, so this is not evidence for cross-epoch identity or complete internal printer telemetry.

The only observed mapping fields were print.ams_mapping=[0,-1,-1,3] and print.ams_mapping2 entries for slots 0 and 3 plus unused 255 entries, once before the print; print.mapping was absent. Do not equate these vendor-specific keys or infer a refill boundary. Captured sliced G-code 3MF: UFM_CUBE_10mm_PREPARED.gcode.3mf, SHA-256 67f155d7eadf80212602e5191f1b979efec8ada9e319d0ea24b396b39e127a61. Its slicer metadata estimates filament id 1 = 1.37 g and id 4 = 0.51 g (1.88 g total); estimates are not measured consumption. No stock or ledger operation was made. Capture was not modified.

Graphify query on the enriched cross-project graph surfaced PrinterEvent, JobMessage, and ReceiptIngestionTests.test_epoch_and_provider_are_distinct_scopes. Direct inspection confirmed receipt idempotency key scope (provider instance, printer, source epoch, event key); Bambu source_epoch is uuid4() per adapter instance. The test proves distinct epochs produce distinct receipts, which is why a single print is insufficient to close restart/reprint correlation.

Next: verify a same-file reprint and a restart/reconnect trace using only session-salted aliases and event counts; no raw identifiers in project docs. Keep the event bridge, automatic split, and debit disabled until occurrence uniqueness and exact slot-to-mount-to-RFID mapping are established. E11.03 remains partial. Latest checkpoint limits at session stop: 16% primary /57% weekly remaining; tests remain 534 passed /472 subtests, Ruff clean, mypy 122 files.


## Stop checkpoint - AMS mapping report preservation - 2026-10-29

Physical trace from D:/3D_Druk/UFM_Print_Test/captures/20261029T024215Z showed ams_mapping=[0,-1,-1,3] and ams_mapping2 entries, but no print.mapping. Graphify query located material_slot_mappings_from_report; direct source shows it only decodes print.mapping. Added optional provider_ams_mapping and provider_ams_mapping2 to PrintJobSnapshot, with strict bounded validation and inclusion in event digest. These remain raw provider fields and never become material_slot_mappings or accounting events.

Targeted tests: 19 passed /15 subtests. Ruff src/tests clean. Mypy has one error at src/ufm/integrations/printers/bambu_lan.py:141: int(ams_id)/int(slot_id) arguments inferred as Any|None. Resume by importing cast from typing and using cast(int, ams_id), cast(int, slot_id) when appending the validated pair; then rerun Ruff, mypy, targeted Bambu tests. Do not run the full suite until limits recover above 15%.

Limit gate reached: 15% primary /57% weekly remaining. Stop all implementation now; automation remains active. E11.03 partial. No debit, receipt/ledger projection, HaspelSync mutation, capture modification, or EXE rebuild.


## Bambu AMS raw mapping fields checkpoint - 2026-10-29

Completed the saved mypy fix in src/ufm/integrations/printers/bambu_lan.py: import typing.cast and cast the AMS/slot IDs after strict type/range checks. PrintJobSnapshot exposes optional provider_ams_mapping and provider_ams_mapping2 tuples; the adapter reads the fields independently and includes both in the event digest. They remain raw report facts and do not populate material_slot_mappings or trigger a receipt, spool assignment, segment, or debit.

Verification: tests/integration/test_bambu_lan_provider.py: 19 passed /15 subtests; Ruff src/tests clean; mypy src/ufm: 122 files clean; full suite: 536 passed /476 subtests in 64.23s. Limit check after suite: 99% primary /57% weekly remaining.

Next: inspect read-only Bambu/HaspelSync source and test fixtures for ams_mapping/ams_mapping2 semantics. Require explicit evidence before conversion to logical material -> slot. Continue to keep event-to-receipt bridge disabled pending cross-epoch/reprint identity and exact mount/RFID joins; E11.03 remains partial.


## Bambu AMS mapping semantics and UFM decoder checkpoint — 2026-10-29

Graphify enriched map was used to find the HaspelSync source; direct review of `D:/Bot/Universal_Filament_Manager/linked-stack/haspelsync/src/gcode.js` and `test/gcode.studiomapping.test.js` established that this HaspelSync implementation decodes Studio's echoed `ams_mapping2` pairs (project-filament order, 255/255 unused) and the equivalent flat `ams_mapping` encoding. Local HaspelSync contains the same decoder. Treat this as implementation/fixture evidence, not an independent Bambu protocol guarantee.

UFM `material_slot_mappings_from_report()` previously accepted only an outer `{print: ...}` wrapper although the LAN adapter's `_print_report()` passes the flattened inner `print` object. It now accepts both. Current live `print.mapping` is authoritative when present; send-time AMS echo is a fallback only. The known AMS and AMS HT encodings map to existing provider slot-key forms; unsupported/external codes stay unsupported. When both AMS echo encodings disagree, all affected logical indexes fail closed. Raw fields remain preserved in the snapshot and event digest.

Evidence: `tests/integration/test_bambu_lan_provider.py` 21 passed /15 subtests; Ruff `src tests` clean; mypy 122 source files clean; full suite 538 passed /476 subtests. Limits after suite: 98% primary /56% weekly remaining. CSV E11.03 remains partial. No event-to-receipt correlation, refill segmentation, stock write, ledger debit, HaspelSync modification, live printer operation, package rebuild, or installed EXE update.

Resume: E11.03 needs cross-epoch/reprint occurrence evidence, then physical refill boundary and exact slot→mount→verified RFID join. Only after these can idempotent material projection/debit be considered.


## Correction: Studio AMS echo is not an active UFM job mapping — 2026-10-29

The HaspelSync source review after the previous note exposed an unsafe assumption: `ams_mapping` and `ams_mapping2` are decoded from the echoed Studio `project_file` command by `decodeStudioMapping()` and stored as `pendingMapping` in `notePrintCommand()`. `handlePrintStateChange()` later associates that pending value to a job name, and a current `print.mapping` report overrides it. UFM currently merges the raw print report but does not implement that command/job occurrence association. Consequently, decode semantics alone do not justify copying the AMS echo into `material_slot_mappings`.

Corrected UFM: raw AMS arrays remain validated metadata and affect the event digest only. `material_slot_mappings_from_report()` accepts either a full `{print: ...}` envelope or the flattened report supplied by `_print_report()`, and decodes only current explicit `print.mapping`. No raw AMS fallback or job join is performed. This supersedes the immediately preceding checkpoint's suggestion that AMS echo could serve as a fallback; it does not erase earlier evidence.

Evidence: linked-stack/haspelsync `src/gcode.js` (`decodeStudioMapping`), `src/mqtt.js` (`notePrintCommand`, `handlePrintStateChange`) and `test/gcode.studiomapping.test.js`; direct UFM tests verify flattened current mapping and raw AMS metadata separation. Provider tests 21 passed/15 subtests; Ruff clean; mypy 122 files clean; full suite 538 passed/476 subtests. Limits after full suite: 97% primary /56% weekly remaining. E11.03 remains partial; no receipts, segments, or ledger/stock writes.



## E09.07 checkpoint: no-write calculated-usage preview — 2026-10-29

Graphify UFM map was consulted first; direct review of `calculated_finalization.py`, the SQLite unit of work, and `test_calculated_finalization.py` confirmed there was an opt-in writer (`finalize`) but no application preview. Added immutable `CalculatedUsagePreview`/`CalculatedMaterialPreview` results and `CalculatedFinalizationCommands.preview()`. It verifies terminal job/receipt scope, identity, plate and exact 3MF SHA-256, calculates full or supported range-partial estimated mass, validates the worker proposal, and returns the visible “Розрахункова витрата” label plus `automatic_policy_enabled`. It remains callable when automatic estimates are disabled and uses no persistent writes. Test verifies all SQLite tables remain byte-for-byte row-equivalent before and after preview.

Verification: calculated-finalization tests 7 passed/2 subtests; full suite 539 passed/476 subtests; Ruff clean; mypy 122 files clean. Limit snapshot: 96% primary/56% weekly remaining. E09.07 remains partial because native UI review/confirmation and persisted explicit policy settings are not implemented. No EXE rebuild or live inventory mutation.

Resume with a native review/confirmation surface and safe persisted policy controls. Keep preview and finalize separated: preview has no write authority; finalize remains guarded by opt-in policy and the verified scope/mapping/segment checks.


## UFM Studio settings checkpoint — 2026-10-29

Fixed the Studio startup path to respect the user's validated local settings. `ufm-studio` no longer defaults its CLI locale over the persisted locale; `--locale` is an explicit override. Invalid/unknown config is surfaced with a bounded generic error, not silently ignored. Added `resolve_settings()` and a regression covering persisted locale and override; updated E05.07 to partial (native settings editor and theme/log controls still remain).

Verification: settings + Studio window suites: 26 passed /19 subtests; Ruff `src tests` clean; mypy `src/ufm`: 122 files clean; isolated offscreen app smoke returned exit 0, read saved `en-US`, migrated only temporary SQLite, and wrote screenshot in temporary test directory. Latest limits: 95% primary /56% weekly remaining. No real user database, HaspelSync, EXE, or installation changed.

Next: E09.07 native read-only estimate review still needs standalone worker runtime composition and a UI connected to persisted job/receipt evidence; do not expose a no-op finalize control. Keep estimated policy disabled by default and do not permit Bambu debit until cross-epoch/reprint identity and physical segment/mount/RFID evidence gates close.


## Studio settings and inventory sort checkpoint — 2026-10-29

Studio now loads saved locale/theme config. `--locale` remains an explicit override; `save_settings()` writes validated non-secret JSON atomically, and the theme button only switches active theme after the write succeeds. Inventory table sorting now retains row identity and search metadata in Qt item roles; remaining mass uses numeric mg comparison. E05.01/E05.07 remain partial pending fuller filter/card/archive/settings UI.

Verification: `tests/unit/test_foundation.py` + `tests/integration/test_studio_window.py`: 29 passed/19 subtests; Ruff clean; mypy 122 source files clean; full suite 543 passed/476 subtests in 64.67s; isolated offscreen startup exit 0. Limits: 94% primary/56% weekly remaining. No production database, HaspelSync files, or installed EXE changed. CSV counts: 23 complete /25 partial /70 planned (118 total).

Resume next on E05.01: material and known-stock filters; preserve row identity through sort/filter and test archived/unknown-stock rows. Then add card/location/archive workflows as dependencies allow. E09.07 native estimate review still requires bundled-worker composition and job/receipt UI.


## Inventory filters checkpoint — 2026-10-29

E05.01 now supports material and known/unknown stock filters composed with the existing search and column sort. Item identity/search/filter fields survive table reorder; hiding the selected item clears selection and disables unsafe stock controls. Numeric stock sorts as mg. UI-only; no inventory or ledger mutation. E05.01 remains partial (cards, colors, locations, archive, column chooser, expanded filters remain). E05.07 partially persists locale/theme preferences; native settings editor/log controls remain.

Verification: `tests/integration/test_studio_window.py` + `tests/unit/test_foundation.py`: 30 passed/19 subtests; Ruff clean; mypy 122 files clean; full suite 544 passed/476 subtests in 68.17s. Latest limit snapshot 93% primary /56% weekly remaining. CSV 118 IDs: 23 complete /25 partial /70 planned.

Next continue E05.01 by inspecting source models for color/location/archive information, exposing only fields that are available and truthful; then test the empty/unknown/archive view states.


## Inventory location/color/archive checkpoint — 2026-10-29

Extended `StudioSpool` read model with color name/hex and optional storage location. Backend uses an outer join; Qt inventory displays color/location and searches them. Material, stock-known, lifecycle/archive and location filters compose with sort/search. Archived items remain visible but stock actions are disabled; hidden selected items clear selection. E05.01 stays partial pending cards/columns/color swatch/location management and broader archive workflows. E05.07 stays partial; saved locale/theme work continues.

Verification: Qt/settings 32 passed/19 subtests; full suite 546 passed/476 subtests in 68.16s; Ruff clean; mypy 122 source files clean. Latest limits 92% primary/55% weekly remaining. CSV: 118 IDs; 23 complete/25 partial/70 planned.

Next: add a safe color swatch and table/card presentation with a visible archived/empty state, then use application commands for location/edit workflows. Never write stock directly from the UI.


## Inventory swatch/empty-state checkpoint — 2026-10-29

Added color swatch for validated six-digit hex only with contrast-aware text; malformed values remain plain text. Added separate empty-inventory and no-filter-results notices. Search/sort/material/known-stock/lifecycle/location filter behavior remains fail-safe, including clearing an invisible selection. E05.01 partial; card view and editable location/archive/column choice remain.

Verified: 32 focused Qt/settings tests, 19 subtests; full suite 546/476; Ruff clean; mypy 122 files clean. Limits 91% primary/55% weekly remaining.

Resume: table↔card inventory view retaining identity and filters, then test view switching, followed by a visible column chooser.


## Table/card inventory view checkpoint — 2026-10-29

Added a compact card view alongside sortable table. Both views share immutable row identity/search/filter metadata; switching preserves selected spool and history. Filter changes hide items in both presentations and clear an invisible selection. Card view shows profile/material/mass/lifecycle/location/color and applies only validated color swatches. E05.01 still partial pending selectable columns, fuller location management and archive workflows.

Verification: 32 focused Qt/settings tests/19 subtests; full suite 546 passed/476 subtests in 66.87s; Ruff clean; mypy 122 files clean. Latest limits 90% primary /55% weekly remaining; CSV 118 rows, 23 complete/25 partial/70 planned.

Resume: implement a checked column chooser for table view, preserve user preference safely, and verify cards remain unaffected.

## E05.01 checkpoint: selectable inventory columns — 2026-10-29

Added the bilingual “Columns…” dialog to Studio inventory. Name is mandatory/disabled in the chooser so row identity remains discoverable; other columns can be hidden for table mode. Table column visibility is unchanged when switching to cards and back. Preference is currently session-only; persistence remains open. No stock/database write was introduced.

Evidence: test `test_inventory_column_chooser_keeps_identity_and_is_table_only`; Qt/settings 33 passed /19 subtests; full suite 547 passed /476 subtests in 73.31s; Ruff clean. Mypy reports four errors in untouched SQLite `migrate.py`/`unit_of_work.py`; no diagnostics for changed Studio UI. First run lacked PySide6, rerun with `uv run --extra desktop --extra dev`. CSV stays 118 rows with UTF-8 BOM; E05.01 partial. Latest limit snapshot before work: 90% primary /55% weekly. No user DB, HaspelSync, or installed build changed.

Resume: continue E05 by implementing location/archive management through existing application commands, or another closest incomplete dependency. Consider validated atomic persistence for column preferences before closing the checklist item.

## E05.01 checkpoint: persistent inventory column chooser — 2026-10-29

Inventory column visibility now persists in the validated local `config/settings.json` through the existing atomic writer. Added a Literal allowlist for column keys; unknown values are rejected by settings validation. Name is required and remains visible; cards remain independent from table visibility. A new StudioWindow restores the saved selection.

Evidence: settings serialization test plus Qt dialog/reopen/table↔cards integration coverage; focused Qt/settings 33 passed /20 subtests; complete suite 547 passed /477 subtests in 72.46s; Ruff clean. Mypy still reports four diagnostics in unchanged SQLite `migrate.py` / `unit_of_work.py`; changed settings/UI files have none. Latest limits: 89% primary /55% weekly remaining. CSV retains 118 rows and UTF-8 BOM; E05.01 partial. No user DB, HaspelSync, or installed EXE changed.

Resume: investigate E05.02/E05.03 native spool edit/archive workflows, confirm available application commands and auditing semantics first, and route any write through those commands rather than direct SQL or ledger edits.

## E05.03 checkpoint: Studio spool edit/archive workflows — 2026-10-29

Graphify UFM map surfaced `InventoryCommands.edit_spool`, `InventoryCommands.archive_spool`, and storage/location concepts; direct implementation review confirmed existing revision, audit/idempotency and archive guards. Studio now has a rename action and an explicit archive confirmation. `StudioBackend` passes the displayed revision and uses application commands; no direct SQL or ledger writes were added. The archive command blocks active mounts, reservations, and unresolved usage. Archived spools remain visible/read-only and stock/name/archive buttons are disabled.

Evidence: integration test exercises rename and archive, verifies ledger/stock unchanged and actions disabled afterward; focused suite 34 passed/20 subtests; full suite 548 passed/477 subtests in 73.06s; Ruff clean. Mypy reports four errors in unchanged SQLite migration/UoW files. E05.03 marked partial; rebuild/compensation remain. CSV 118 rows with BOM; counts 23 done/26 partial/69 planned. Limits 88% primary /55% weekly. No user database, HaspelSync, or installed package changed.

Resume by checking StorageLocation command APIs and the approved rebuild/compensation workflows, then build native flows through those APIs with explicit revision and confirmation semantics.

## E05.03 checkpoint: confirmed ledger compensation from Studio — 2026-10-29

Studio now offers a compensation workflow: select an eligible nonzero, uncompensated transaction from the selected spool and confirm. It calls `InventoryCommands.compensate`, which appends a reversing ledger entry referencing the original and writes audit evidence; no historical row is deleted. Already compensated transactions are excluded. Archived spools remain read-only. Together with the preceding rename/archive actions, E05.03 remains partial pending rebuild projection and other approved workflows.

Evidence: integration test verifies compensation reference, reverse delta, and restored balance while preserving the original entry; focused Qt/settings 35 passed/20 subtests; full suite 549 passed/477 subtests in 73.19s; Ruff clean. Mypy still has four errors in unchanged SQLite migration/UoW files. CSV 118 rows/BOM; 23 done, 26 partial, 69 planned. Limits at checkpoint: 88% primary /55% weekly. No production data, HaspelSync, or installed EXE changed.

Resume: review `InventoryCommands.rebuild_projection` preconditions and whether source evidence can be selected safely from current UI. Also note `StorageLocation` has no application repository/command workflow yet, so do not implement UI through direct SQL.

## E05.03 checkpoint: rebuild stock projection from Studio — 2026-10-29

Added a confirmed “Rebuild stock projection” action. It calls `InventoryCommands.rebuild_projection` with the displayed revision; the command checks stale revision, archived state, and ledger integrity, then updates the projection/audit without modifying ledger entries. The Studio exposes rebuild alongside rename/archive, while compensation remains a separate confirmed reversal path.

Evidence: UI integration test confirms projection rebuild leaves effective stock and transaction history unchanged; focused Qt/settings 36 passed/20 subtests; full suite 550 passed/477 subtests in 74.54s; Ruff clean. Mypy has four diagnostics in unchanged SQLite migration/UoW files. E05.03 stays partial. CSV: 118 rows/BOM; 23 complete/26 partial/69 planned. Limits: 87% primary/55% weekly. No production SQLite, HaspelSync, or installed build modified.

Resume by verifying StorageLocation persistence architecture. Current source has the domain entity/schema but no application repository/commands or UnitOfWork port, so avoid direct SQL UI operations. Design a transactional use case and tests or select another ready checklist item.

## Checkpoint: storage locations and E05.01 completion — 2026-10-29

Completed E05.01 criteria in Studio: table/cards, search, sorting, composed filters, persistent column chooser, validated color swatches, location display/filter, and archived read-only state. Added top-level storage location create and spool assignment/clear workflows. Introduced `StorageLocationRepository` in the application port and SQLite UoW plus `StorageCommands`; assignment is revision-checked/audited and does not mutate stock/ledger. Location choices include a short ID suffix to disambiguate duplicate labels. E05.01 is marked complete.

E05.03 remains partial. Rename/archive/rebuild/compensation actions are present, but the native edit form changes only the spool name and retains the current threshold; broader confirmed field editing is still needed.

Evidence: focused Qt/settings/location 37 passed/20 subtests after final label change; Ruff clean; full suite 551 passed/477 subtests in 74.37s before that presentation-only tweak. Mypy has four errors only in existing SQLite migration/UoW files; new storage/UI/backend code is clean. CSV 118 rows/BOM: 24 complete/25 partial/69 planned. Latest limits: 86% primary/54% weekly. No live DB, HaspelSync, installed app, or EXE changed.

Resume: E05.02 extended editing. Inspect supported `FilamentProfile`/`Spool` fields and available application commands before making additional native forms. Storage tree parent/edit workflows remain an extension.


## E05.02/E05.03 checkpoint: spool edit form and workflow migration — 2026-10-29

Studio spool edit now has name and low-stock threshold fields; blank clears the threshold and entered grams pass through `Mass.from_grams`. Writes use `InventoryCommands.edit_spool` with the displayed revision and audit path. Tests confirm no stock/ledger movement. With existing archive/rebuild/compensation flows this completes E05.03; the edit/archive/rebuild/compensation actions use application commands, require confirmation where they can change inventory state, and keep archived rows read-only.

E05.02 is partial: create material/spool and edit name/threshold are available, while full manufacturer/profile/spool metadata editing remains. Evidence: focused Qt/settings/location 56 passed/35 subtests; full suite 551 passed/477 subtests in 74.77s; Ruff clean. Mypy has four diagnostics in unchanged SQLite migration/UoW files only; checked 123 modules. CSV 118/BOM, 25 complete/25 partial/68 planned. Latest limits 85% primary /54% weekly. No live data, HaspelSync, or installed build touched.

Resume: map supported Brand/FilamentProfile/Spool fields to existing application commands and classic UI, then expose validated revision/audit workflows in Studio. Follow with E05.08 button registry and normal/empty/error/unavailable UI state coverage.

## E05.02 checkpoint: manufacturer and expanded material profile forms — 2026-10-29

Studio now creates Brand records and creates/edits supported FilamentProfile fields: name, brand, product line, material/custom name, diameter, density, and abrasive/flexible/hygroscopic/soluble/filled flags. The profile table shows manufacturer, diameter, and density. Edit confirmation warns that changes affect every linked spool.

Added Brand/FilamentProfile repository ports and SQLite UoW implementations, with legacy nullable profile boolean columns read as false. `CatalogCommands` provides brand/profile writes with audit, idempotency fingerprints and revision guards; profile brand references are validated in the same UoW. StudioBackend no longer inserts new material profiles through direct SQL. No stock or ledger changes result from profile metadata edits.

Evidence: focused Studio/backend 22 passed; full suite 552 passed/477 subtests in 73.11s; Ruff clean. Mypy retains four diagnostics only in existing SQLite migrate/UoW files. CSV 118/BOM: 25 complete/25 partial/68 planned; E05.02 remains partial. Limits 83% primary/54% weekly. No real DB, HaspelSync, or installed package touched.

Remaining E05.02: Brand edit/archive; profile temperature/drying/volumetric-speed/notes; spool descriptive/purchase metadata. Next, map available spool fields and explicitly keep accounting masses behind InventoryCommands.


## E05.02 checkpoint: descriptive spool metadata — 2026-10-29

Spool entity and `InventoryCommands.edit_spool` now support optional product line, batch number, lot number, color name, primary/secondary HEX, image URI, and notes. Entity validation bounds text lengths and rejects malformed HEX before persistence. Studio edit form exposes those fields; backend reads their persisted values. The command retains expected-revision, idempotency fingerprint, audit, archive guards, and projection alert behavior. It does not accept stock/accounting values, nominal/empty masses, or ledger sequence.

Evidence: integration UI test sets all descriptive fields and verifies their persistence while effective stock and history remain unchanged; focused suite 5 passed; full suite 552 passed/477 subtests; Ruff clean. E05.02 remains partial: brand/purchase fields and profile thermal/drying/speed/notes still require evidence-driven review. CSV 118 rows/BOM: 25 complete/25 partial/68 planned. Limits 83% primary/54% weekly. No live DB, HaspelSync, EXE changed.

Resume: inspect Graphify and source/tests for the UI button registry/state requirements under E05.08. Then implement that checklist step if dependencies allow, before extending purchase/accounting metadata.


## E05.08 checkpoint: inventory action registry and UI states — 2026-10-29

Added `docs/UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv` mapping 12 Studio inventory controls to handlers, normal/empty/unavailable/error behavior, and tests. Added `test_inventory_empty_normal_unavailable_and_error_states` for empty inventory, a normal selected spool, unknown stock preventing deduct/adjust, and generic safe error presentation. Studio test module: 19 passed; complete suite: 553 passed/477 subtests in 73.87s; Ruff clean. E05.08 remains partial; state coverage must be checked across every registered workflow before completion. CSV is 118 rows with UTF-8 BOM; current counts recorded in PROJECT_PROGRESS. Limits: 82% primary /54% weekly. No live DB, HaspelSync, or installed build changed.

Resume by reviewing source-supported Brand/purchase/profile fields against classic UI/action contract evidence, then add fields through validated application commands only. Keep all stock mutations behind InventoryCommands.


## E05.02 checkpoint: spool brand and packaging masses — 2026-10-29

Studio now edits a spool-specific brand plus nominal filament and empty-spool mass. Application command validates referenced brand exists and is not deleted; mass text uses exact `Mass.from_grams`. Writes preserve expected-revision guard, idempotency fingerprint and audit, and deliberately do not write effective/estimated/measured stock or ledger. Existing descriptive fields (product/batch/lot/color/image URI/notes) remain in same controlled form.

Evidence: `test_studio_edits_and_archives_spool_through_application_commands` checks saved brand/masses/descriptive fields and unchanged effective stock/history. Focused Studio/backend 5 passed; full suite 553 passed/477 subtests in 73.85s; Ruff clean. CSV 118 rows/BOM: 26 complete/25 partial/67 planned. Limits: 82% primary /54% weekly. No real DB, HaspelSync or installed build changed.

Resume by evidence-checking profile thermal/drying/volumetric-speed attributes and Brand edit/archive support against Graphify, schema, classic UI, and action contracts. Do not treat schema columns alone as proof of supported workflow.


## E05.02 checkpoint: Brand rename and soft archive — 2026-10-29

Added audited, revision-checked `CatalogCommands.edit_brand` and `archive_brand`. Archive sets `deleted_at` and advances revision; it does not delete the row or detach existing filament-profile/spool foreign keys. The Studio material page has an active-brand table and edit/archive controls with confirmation. Brand selectors consume only active brands.

Evidence: `test_studio_can_rename_and_archive_brand_without_losing_profile_links` verifies rename propagation and persistence of linked rows after soft archive; full suite 554 passed/477 subtests in 75.29s; Ruff clean. `docs/UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv` now lists 17 actions. E05.02 and E05.08 remain partial. CSV 118/BOM; 26 complete/25 partial/67 planned. Limits 81% primary/54% weekly. No live DB, HaspelSync, or installed package changed.

Resume: implement schema-backed profile temperature/drying/max-speed/subtype/default-color/notes fields in domain and CatalogCommands with ExactDecimal validation; then expose them via a manageable Studio form and test no stock changes.


## E05.02 checkpoint: schema-backed profile settings and Brand preservation — 2026-10-29

`FilamentProfile` now includes subtype, nozzle/bed/chamber temperature ranges, maximum volumetric speed, drying temperature/duration, default color name, and notes. Domain validation checks nonnegative temperatures, low≤high ranges, positive speed, nonnegative integer duration, and bounded text. Studio create/edit forms expose these fields inside a scrollable dialog; backend uses exact decimal parsing and `CatalogCommands` revision/audit path. Invalid profile range and negative drying duration are covered.

Added Brand rename and soft archive to Studio. Archived rows remain linked; selectors preserve an existing archived FK as disabled and commands allow an unchanged historical FK while rejecting assignment to a new/changed relation. The same protection applies to a spool's brand. Evidence: brand/profile/spool integration scenarios; full suite 554 passed/477 subtests in 74.22s; Ruff clean. CSV 118/BOM; counts 26/25/67. Limits 79% primary/53% weekly.

E05.02 remains partial until supported metadata is also available during spool creation. Purchase fields remain for E05.06; measurement workflow is E05.04. Resume by adding profile-derived defaults and explicit optional Brand/nominal/empty/descriptive inputs to create spool through InventoryCommands.


## E05.02 checkpoint: spool metadata creation form — 2026-10-29

New spool creation now collects optional brand, product line, batch/lot, nominal/empty masses, color name/HEX, image URI, and notes. Profile choice seeds product line, default color and active manufacturer. `InventoryCommands.create_spool` persists metadata with a command fingerprint/audit and does not invent opening balance or ledger usage.

Evidence: `test_studio_creates_spool_with_metadata_without_opening_stock` verifies saved fields and that effective balance remains unknown with empty history. Full suite 555 passed/477 subtests in 75.31s; Ruff clean. E05.02 remains partial pending source reconciliation for dates/other field contracts. E05.04 owns weighing; E05.06 owns purchase/price. CSV 118/BOM, 26 complete/25 partial/67 planned. Limits 78% primary/53% weekly.

Resume by reconciling confirmed Spoolman/HaspelSync spool create/edit fields with E05.02 versus E05.04/E05.06, then consider E05.08 coverage. Do not add direct accounting writes.


## E05.02 complete: manufacturer, profile and spool forms — 2026-10-29

All confirmed schema-backed Brand, FilamentProfile, and Spool create/edit fields are exposed in Studio. Brand has create/rename/soft archive; historical FKs survive archive and unchanged archived references remain preserved. Profile includes material, brand, product line, diameter/density, material flags, subtype, nozzle/bed/chamber ranges, max volumetric speed, drying temperature/duration, default color, and notes. Spool includes profile/brand, batch/lot, color fields, image URI/notes, nominal/empty mass, opened/manufactured/expiry dates. All mutations go through CatalogCommands/InventoryCommands with revision, audit, idempotency, and validation. Metadata operations leave effective inventory and ledger unchanged.

Purchase/price/cost is assigned to E05.06; measurement/reconciliation is E05.04; stock remains an InventoryCommands concern. Last-used is a ledger/event-derived value, not an editable metadata field. Evidence: profile/brand/spool create/edit/archive/date tests; full suite 556 passed/477 subtests in 74.69s; Ruff clean. E05.02 marked complete; CSV 118/BOM: 26 complete/25 partial/67 planned. Limits 77% primary/53% weekly. No live DB, HaspelSync deployment, or installed build touched.

Resume at E05.08: use `docs/UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv` to close remaining per-action normal/empty/error/unavailable evidence gaps; then continue dependency-ready inventory workflows.


## E05.08 checkpoint: безпечний unavailable refresh і opening-stock guards — 2026-10-29

На `StudioWindow.refresh()` додано контрольовану обробку помилок читання локальних джерел. При збої UI більше не показує застарілі дані, очищає інвентар/історію, показує перекладену підказку без деталей винятку та вимикає інвентарні дії; успішне повторне читання відновлює їх. Тест `test_inventory_empty_normal_unavailable_and_error_states` перевіряє збій і відновлення, а також початковий залишок: невалідна маса лишає баланс невідомим, успішні 125 г фіксуються через штатну команду. Реєстр 17 дій оновлено; opening/refresh — перевірені, E05.08 — частковий до покриття інших дій.

Перевірки: повний pytest **557 passed / 477 subtests in 75.14s**; `uv run ruff check src tests` — чисто. Ліміти: 76% primary /53% weekly. CSV 118/BOM: 26 complete /25 partial /67 planned. No live database, HaspelSync, or installed build changed.

Resume: continue E05.08 by taking each remaining action registry row through its error/unavailable guards with deterministic fixtures. Keep generic safe UI error tests, but do not treat them as evidence for a specific command failure unless the action is exercised.


## E05.04 source audit and resume point — 2026-10-29

Graph/source audit found domain `InventoryEvidence` and `InventoryReconciliation`, `Spool.measured_remaining`, immutable persistence repositories/tables, and the `ScaleProvider.read/tare` port. Existing tests cover domain exactness (gross−tare=net) and schema. No write-side application use case found to persist the evidence and then explicitly accept measured reconciliation; Studio has no measure/review/confirm path. E05.04 is now `У роботі` in the BOM checklist, with no code changes in this audit stage.

Resume: design and implement transaction-safe evidence capture plus explicit reconciliation acceptance through application commands; retain ledger cutoff, revision/idempotency, reserved-stock checks, immutable evidence and audit. Add failure/replay/zero-delta tests before presenting a UI confirmation flow. Limits remain 76% primary /53% weekly.


## E05.04 implementation checkpoint: immutable measurement capture — 2026-10-29

Added `InventoryCommands.record_inventory_measurement` and `EvidenceRepository.get_inventory`. The command stores immutable `InventoryEvidence` with measured/received timestamps, source, optional gross/tare, net, sensor/calibration metadata, stability, and the spool ledger cutoff. Audit correlation contains a request fingerprint; same-key/same-payload replay returns the existing evidence, changed payload conflicts, and future capture timestamps are rejected. Capturing evidence does not mutate spool projections or ledger. Tests: two new command integration tests; inventory command suite 37 passed/31 subtests; Ruff clean. E05.04 remains in progress because backend/UI read/capture and explicit ledger-linked reconciliation acceptance remain. Limits 75% primary/53% weekly.

Resume: add backend read model for persisted inventory evidence and a UI capture/review path. Acceptance must be a separate explicit operation and verify the evidence ledger cutoff, current spool revision, reserved stock, and calibration/provenance before writing one reconciliation and optional nonzero ledger adjustment atomically.


## E05.04 checkpoint: Studio manual weigh/reconcile path — 2026-10-29

Completed the first end-to-end manual workflow. `InventoryCommands.record_inventory_measurement` stores immutable evidence with provenance and ledger cutoff, request fingerprint and idempotent replay, without touching stock. `accept_inventory_measurement` verifies expected spool revision, current ledger cutoff/projection, trusted MANUAL/SCALE source, no prior acceptance and active reservations; writes the immutable reconciliation and a linked ledger transaction for nonzero correction, then updates measured/effective/estimated projections atomically. Unknown stock can be established by accepted measurement; known zero-delta acceptance updates measured state/reconciliation but does not create an invalid zero ledger row. Evidence capture timestamp after receipt is rejected.

Studio now has a manual weighing action for gross mass and empty-spool tare. It computes net and shows the difference; No is default and preserves evidence only, Yes explicitly accepts the ledger correction. Focused command/UI tests: 63 passed/31 subtests; Ruff clean. E05.04 remains `У роботі`: ScaleProvider/calibration-expiry integration, measurement history read view, reservation-under-measurement and zero-delta/opening edge tests remain. Full suite pending. Limits 73% primary/52% weekly.

Resume by adding the missing measurement edge tests and read-only history, then connect a scale provider only after validating calibration status/version/expiry.


## E05.04 edge tests checkpoint — 2026-10-29

Added regression coverage for measurement acceptance below an active reservation (rejected, stock/ledger unchanged), zero-delta evidence (reconciliation saved without a zero-value ledger event), and a measured empty spool accepted as an INITIAL_STOCK entry at 0 mg. Focused inventory/Studio tests now 65 passed/31 subtests; Ruff clean. E05.04 stays in progress. Remaining: persisted measurement-history read view in Studio and a real scale-provider/calibration-validation path. Limits 73% primary/52% weekly.

Resume with a bounded read-only inventory-evidence query for one spool, then render provenance, capture time, ledger cutoff and accepted/unaccepted state in its detail/history panel.


## E05.04 checkpoint: persisted measurement history in Studio — 2026-10-29

Added read-only evidence history: EvidenceRepository returns up to 100 newest measurements per spool; InventoryCommands joins each record to any accepted InventoryReconciliation; Studio displays source, capture time, gross/tare/net, ledger cutoff, and whether it remains evidence-only or has been reconciled. Parameterized UI tests verify No leaves stock untouched and Yes applies the linked correction and displays accepted state. Focused inventory+Studio suite: 65 passed/31 subtests; Ruff clean. E05.04 remains in progress pending real ScaleProvider/calibration validation and hardware acceptance. Limits 72% primary /52% weekly.

Resume after full suite/Ruff by inspecting the ScaleProvider DTO and calibration record contract; implement only a source adapter that can verify active, matching calibration before SCALE acceptance.


## E05.04 test/run checkpoint: history read model and Qt shutdown anomaly — 2026-10-29

Measurement history is exposed through a bounded 100-row `inventory_for_spool` query and shown in Studio with source, capture time, gross/tare/net, cutoff, and accepted/evidence-only state. Full test results: 565 passed/477 subtests; however Windows exited with a Qt access violation after pytest printed the complete summary (faulthandler had no Python frame). Isolated Studio module: 24 passed, exit 0; focused inventory+Studio: 65 passed/31 subtests; Ruff clean. Do not report the full runner as clean until repeated.

Resume: repeat full suite once with faulthandler and capture exit status; if reproducible, bisect by test modules. Then inspect ScaleProvider DTO and calibration persistence before any scale integration. E05.04 is still in progress. Limits 72% primary/52% weekly.


## Test runner checkpoint: Qt access violation only in combined suite — 2026-10-29

Repeated default full suite: 565 passed/477 subtests, then Windows Qt access violation with no Python frame. Isolated Studio module: 24 passed, exit 0. All tests excluding Studio UI: 541 passed/477 subtests, exit 0. Ruff clean. This narrows the issue to combined Qt + non-Qt test process teardown/order, not an assertion regression; root trigger not yet known. E05.04 remains in progress.

Resume: run the Studio UI module first, then remaining modules with `--ignore=tests/integration/test_studio_window.py` to determine whether order resolves the teardown crash; keep full result and exit code distinct. Do not change product runtime merely to mask pytest shutdown behavior. Limits 71% primary/52% weekly.


## Qt teardown diagnostic: ordering is not the cause — 2026-10-29

The full test suite with Studio UI collected first still produced 565 passed/477 subtests followed by the same native access violation. Isolated Studio: 24 passed/exit 0; non-Studio: 541 passed/exit 0. The default and reordered combined runs both fail only after summary; no Python frame. Next experiment: explicitly close/process/delete deferred widgets and quit QApplication in its session-scoped pytest fixture, then rerun the full suite. Avoid changing app runtime unless product behavior is implicated.


## Checkpoint: Qt teardown fixed; E05.04 scale-calibration gate next — 2026-10-29

The session-scoped Qt fixture now closes windows, processes DeferredDelete, quits the app and releases its Python reference. The full suite is clean: 565 passed/477 subtests, exit 0; Ruff clean. Earlier access violations occurred after all tests passed and disappeared after the explicit teardown fix.

Resume E05.04: add read-only sensor/calibration repository ports and a `WeightReading` capture path validating stability, observed quantities, enabled sensor identity, matching calibration version and non-expiry before writing SCALE evidence. Do not invent a serial/hardware adapter without the user's scale protocol/model. Limits 71% primary/52% weekly.


## E05.04 checkpoint: SCALE evidence gated by sensor/calibration — 2026-10-29

Added application persistence ports for sensor and calibration reads, concrete SQLite repositories, and UnitOfWork bindings. A new `InventoryCommands.record_scale_reading` accepts normalized `WeightReading` only after checking required stable known masses, chronology, active spool, enabled SCALE sensor, matching sensor/calibration, exact latest calibration version/type, and validity through receipt. The write is immutable, idempotent, audited, and ledger-cutoff-bound; it has no stock mutation. Generic manual measurement capture now refuses SCALE source. Explicit acceptance revalidates sensor/calibration and expiry at confirmation time.

Verification: focused InventoryCommands + ScaleProvider contract: 48 passed/31 subtests; full suite 569 passed/477 subtests (exit 0); Ruff clean. Mypy full source still has 26 diagnostics in existing migrate/UoW/Studio modules, none in the changed application/repository modules.

Remaining E05.04: no serial/network scale adapter, Studio configuration/reading UX, or physical device acceptance because supported hardware/protocol is unspecified. Next: continue dependency-ready plan item; do not mark E05.04 done until an adapter-backed UI flow and hardware acceptance criteria are supplied/implemented. Last quota: 70% primary /52% weekly.


## E05.06 checkpoint: purchase price and mass basis in Studio — 2026-10-29

Added current spool purchase fields through Domain/InventoryCommands/Studio: exact decimal price, separate positive mass basis, three-letter uppercase currency and ISO purchase date. Create/edit fingerprints include all purchase fields; incomplete purchase profiles are rejected; metadata updates do not alter stock/ledger. Added frozen migration `0004_purchase_basis` with nullable constrained mg column; existing price/date/currency values are not rewritten or backfilled. Checklist E05.06 moves to `У роботі`, not done: booking-time price snapshots, immutable cost history, cost totals/reports remain.

Verification: 71 focused tests/37 subtests; 22 migration tests/27 subtests; complete suite 570 passed/483 subtests exit 0 after worker-aware Qt fixture teardown; Ruff clean. One preceding combined suite reproduced a post-summary Windows access violation (exit -1073741819); Studio 24/exit0 and non-Studio 546/483/exit0. Fixture now waits for outstanding QThreads and processes queued/deferred deletes per test window; subsequent combined suite exited 0. No live application database or HaspelSync data modified.

Next: implement a ledger-bound cost snapshot for accepted print/manual consumption using exact integer minor units and stored price basis; preserve original snapshot when profile price changes. Add currency-separated aggregation/read-model and tests before a report UI. Keep estimates/manual adjustments out of confirmed cost totals unless a ledger entry explicitly qualifies. Last quota 98% primary /51% weekly.


## E05.06 checkpoint: immutable cost per confirmed consumption — 2026-10-29

Changes: new `src/ufm/application/costing.py` computes half-up integer minor units from exact purchase price, basis mg and consumed mg. `FilamentTransaction` now maps its `unit_cost` and `currency` fields to existing frozen ledger columns; no schema migration. Both verified printer finalization and completed verified-3MF finalization persist the snapshot and add `cost_snapshot_v1` while preserving source provenance. Only successful `PRINT_CONSUMPTION` qualifies. Unsupported currency (v1 supports UAH/EUR/USD/PLN), incomplete price basis or no cost profile leaves cost NULL and does not reject stock finalization. FAILED_PRINT is explicitly excluded.

Verification: focused print/calculated-finalization tests **31 passed /22 subtests**; full suite **573 passed /483 subtests, exit 0**; `uv run ruff check src tests` clean. No live DB, HaspelSync, or installation modified.

Resume: implement read-only cost history/aggregation with strict currency grouping, then UI cost report. Never sum unlike currencies. Keep unknown-cost consumption separately visible. Recheck currency precision support before expanding beyond the four explicitly supported codes. Quota last checked before this stage: 98% primary /51% weekly.


## E05.06 checkpoint: per-spool cost history and summary — 2026-10-29

Added `InventoryCostSummary` and `InventoryCommands.cost_summary(spool_id)`, plus Studio backend/UI integration. Summary is strictly derived from the spool ledger, only confirmed `PRINT_CONSUMPTION`; totals remain grouped by currency, unknown cost count/mass are explicit, manual adjustments/use and failed prints are excluded. Detail history shows the immutable event snapshot and keeps 3MF provenance. Both locales covered.

Verification: targeted print/calculated finalization + Studio **56 passed /22 subtests**; full suite **574 passed /483 subtests, exit 0**; Ruff clean. Check-list stays E05.06 `У роботі`: snapshots, history and one-spool summary exist; global/date-range cost report and remaining legacy cost screens remain.

Resume: inspect verified classic/HASPEL cost report contract, then implement bounded read-only global/period aggregation grouped by currency; never use current spool price to reconstruct historic cost. Last quota: 97% primary /51% weekly.


## E05.06 checkpoint: date/printer cost report — 2026-10-29

Classic HaspelSync contract HA177–180/HA190 confirms currency allowlist UAH/EUR/USD/PLN, explicit price basis, booking-time snapshot, period/printer filtering, separate currency totals, unknown cost count, and CSV columns/status with UTF-8 BOM, semicolon delimiter, formula-prefix protection. Added a bounded (10,000 events) date/printer report to InventoryCommands. Persistence query uses one join, selecting immutable ledger entries by `print_job.started_at`; report names are read with same joined rows. Studio now offers a local-date inclusive period, all/single printer filter, summary/detail preview, and semicolon CSV export with BOM and formula-safe user-provided labels. Unknown-price consumption is visible and totals are never combined across currencies.

Verification: target print/calculated-finalization/Studio **58 passed /22 subtests**; full pytest **576 passed /483 subtests, exit 0**; `uv run ruff check src tests` clean. Current checklist remains E05.06 `У роботі`; verify export contract details and acceptance before changing status.

Resume: audit CSV contract fields, statuses and no-cost/review rows against HA190, add exact acceptance coverage (especially missing cost rows and multiple currencies), then report status. No live database, HaspelSync runtime or installed build changed. Last quota: 95% primary /51% weekly.


## E05.06 checkpoint: Spoolman purchase-price import preview — 2026-10-29

У `integrations/spoolman/importer.py` додано імпорт ціни котушки з пріоритетом `spool.price`, fallback на `filament.price`, глобальної валюти з `setting.currency` та price basis із відомої маси. Відсутня валюта означає пропуск purchase metadata, не здогад. `_source_tables` використовується для сумісності зі схемами без optional `price`/`setting`. UI preview показує відомі/невідомі залишки і кількості imported/skipped prices. Source відкривається read-only, тестові fixtures synthetic.

Докази: `tests/integration/test_spoolman_importer.py`, `tests/integration/test_studio_window.py`; цільові **33 passed**; повний pytest **578 passed /485 subtests, exit 0**; Ruff clean. `git` metadata відсутні в робочій папці, тому diff/check не застосовувався.

Наступна дія: перевірити повний classic HaspelSync CSV/report contract і acceptance coverage проти поточного UFM date/printer report; зафіксувати точні паритетні поля й додати пропущені tests, залишаючи E05.06 у роботі до закриття всіх критеріїв.


## E05.06 checkpoint: report contract review and clean test process — 2026-10-29

Підтверджені файли джерела: `linked-stack/haspelsync/src/accounting.js` (`consumptionReport`) і `public/accounting.js` (`exportReport`). Haspel report повертає всі filtered bookings, `reviewCount` для pending/uncertain, `unknownCostCount` лише для booked без cost; totals/grams лише booked. CSV має 7 полів date/job/spool/mass/cost/currency/status. UFM CSV має ці змістові поля плюс printer/source, але джерело його рядків — тільки confirmed PRINT_CONSUMPTION immutable ledger. Не прирівнювати відсутній рядок pending/uncertain до zero-cost; перевірити receipt/reconciliation read models та узгодити з E05.08.

Винесено `_cost_report_csv` для прямої перевірки контракту. Звітні тести перевіряють UTF-8 BOM, `;`, колонки й порядок, formula escaping, quoted delimiter та unknown-cost поля. Test fixture Qt teardown тепер не викликає `QApplication.quit()` і не відпускає wrapper вручну: вікна закриваються, DeferredDelete обробляється, wrapper лишається живим до завершення процесу. Перевірки: Studio 26 passed; решта 552 passed/485 subtests; явний повний запуск Studio first 578 passed/485 subtests, `PYTEST_EXIT=0`; Ruff clean.

Наступна технічна дія: read-only дослідити UFM external_event_receipt, print job and reconciliation models/query APIs for safe pending/uncertain review counts. Не змінювати ledger/stock і не повторювати endpoint effects. Після цього або додати тільки окремий звітний review summary із tests, або записати підтверджене розмежування E05.06/E05.08 та закрити лише за повними критеріями.


## E05.06 done; review-state boundary recorded — 2026-10-29

E05.06 поставлено `Виконано` після CSV/report contract acceptance. UFM підтверджений cost report/export — лише immutable PRINT_CONSUMPTION ledger, unknown cost показується без суми. Haspel pending/uncertain із CSV `HA190` не моделюється UFM receipt `PENDING` (необроблене printer observation) або generic reconciliation OPEN/IN_REVIEW; цей UI/операційний паритет планом віднесено до E12.03. Це не дозволяє некоректно зарахувати невідомий запис або вивести його собівартість. План доповнено під E05.06 поясненням межі.

Перевірки: весь `uv run python -X faulthandler -m pytest -q` — 578 passed/485 subtests, exit 0 після збереження QApplication wrapper у тестовому teardown; `uv run ruff check src tests` — clean. CSV 118 рядків + header, BOM збережено; статуси: Частково виконано: 25 / Виконано: 27 / Заплановано: 65 / У роботі: 1.

Наступна дія: E05.08 audit registry; взяти точний реєстр `docs/UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv`, перевірити normal/empty/error/unavailable кожної дії, оновити докази/чекліст після завершеного піднабору. Не змінювати E12.03 межу, доки не виконано її окремі тести й review UI.


## E05.08 checkpoint: manual measurement UI negative states — 2026-10-29

Додано `test_studio_manual_weighing_errors_preserve_stock_and_evidence` (invalid gross<tare та simulated offline backend). В обох UI повідомляє sanitized error type, не відкриває confirm, не зберігає evidence, не змінює stock/ledger. Empty inventory вимикає record_measurement. Спершу перевірка хибно припускала, що refresh після додавання spool не вибере рядок; виправлено сам тест, бо Studio auto-selects first visible spool. Runtime UI змін не було. Цільові нормальні Yes/No + error/unavailable: 4 passed; Ruff clean. Registry row record_measurement відмічено Перевірено; E05.08 лишається частковим, інші дії ще потребують перевірки станів. Наступне: запуск повного suite та продовження матриці negative states для найближчої незавершеної Studio action.


## E05.08 checkpoint: stock command UI errors — 2026-10-29

Added `test_studio_stock_action_errors_preserve_inventory_and_ledger` for each opening/deduct/add UI action under malformed amount and simulated OSError/unavailable backend. All 6 cases assert error code type, unchanged current remaining, and unchanged ledger history. For opening the spool has unknown stock; deduct/add use a known 800g opening balance. Focused tests 6 passed, Ruff clean. Registry now cites the test for all three handlers. Next: continue negative-state UI coverage for edit/archive and compensation; keep E05.08 partial until all registered actions have evidence.


## E05.08 checkpoint: asynchronous action failure paths — 2026-10-29

`test_studio_inventory_action_unavailable_state_preserves_ledger` exercises real Task/QThread error signaling for edit, archive, rebuild projection, and compensation. Injected OSError results in UI error type, no stock/ledger mutation and no accidental lifecycle change. Four cases pass; Ruff clean. The action registry cites this test on four handler rows. Next: full test run; then extend negative-state acceptance for remaining registered control flows (catalog forms, assignment, reports, backups/import). E05.08 stays partial.


## E05.08 checkpoint: full suite clean after UI negative-state tests — 2026-10-29

Dодано/зафіксовано error/unavailable UI proofs для measurement, stock operations, spool edit/archive, projection rebuild і compensation. Визнано, що кілька реальних QThread у параметризованих error tests можуть завершити Windows процес із access violation після pytest summary; ці tests тепер інжектують synchronous operation executor та перевіряють центральний error callback + нуль side-effects. Production `StudioWindow.work`/`Task` не змінювався. Після цього Studio: 38 passed/exit0; повний ordered suite: 590 passed/485 subtests, 78.40s, exit0; Ruff clean.

E05.08 ще частковий. Далі додати normal/empty/error/unavailable UI coverage для catalog material/brand and location forms, reports, importer/backup actions, потім повторити full suite і оновити кожен registry row з доказом. Не заявляти hardware SCALE UI: це E05.04.


## E05.08 checkpoint: catalog UI error states and full suite — 2026-10-29

Added `test_studio_catalog_create_errors_do_not_create_records` (4 parameter cases), `test_studio_catalog_edit_errors_preserve_existing_records` (4), and `test_studio_archive_brand_unavailable_state_preserves_brand` (1). They assert invalid/unavailable failures leave material/brand records unchanged. The test-only synchronous executor avoids outstanding Qt workers in these cases; production `StudioWindow.work` is unchanged. Updated evidence for new_material, new_brand, edit_material, edit_brand, archive_brand in `docs/UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv` and appended evidence to E05.08.

Validation: focused 9 passed; Studio module 47 passed, but the process hit a Windows native access violation after summary in a module-only run. The ordered full suite (Studio module first, all other test files next without recollecting Studio) passed **599 tests /485 subtests, exit 0**; Ruff clean. E05.08 remains partial. Next: audit remaining registry actions and cover normal/empty/error/unavailable states in bounded groups. Recheck quotas before next code/test stage.


## E05.08 checkpoint: catalog negative states; location test isolated as unstable — 2026-10-29

Catalog UI negative-state coverage remains: create material/brand (4 parameter cases), edit material/brand (4), and archive brand when backend is unavailable (1). Registry evidence is updated for all five controls. The full suite with catalog tests, Studio module first, passed **599 /485 subtests, exit 0**, Ruff clean.

A further attempt to cover `assign_storage_location` error/unavailable through a Studio UI test passed alone, but the combined full suite reproduced a Windows native access violation after **600 passed**. The test-only scenario was removed; product code was not modified. Repeating the ordered suite on the stable test set passed **599 /485 subtests, exit 0**. Therefore E05.08 stays partial and assignment error/unavailable coverage remains open. Next: continue with other stable actions (reports/import/backup), and revisit location failure coverage using an approach that does not destabilize Qt teardown.


## E05.08 checkpoint: bounded UI negative-test coverage and Qt teardown limits — 2026-10-29

Catalog failure-state coverage is retained and has a clean ordered full-suite result: 599 passed /485 subtests, exit 0; Ruff clean. Experimental error tests for storage-location assignment and spool creation passed in isolation but caused a Windows native access violation after all tests passed in the combined suite. Excluding those tests restored the clean 599/485 result. The analogous edit-spool negative test showed the same pattern; it too was removed after the full suite reproduced the post-summary crash. No production UI, worker, storage, or inventory code changed during these experiments.

Keep E05.08 partial. The tested workflows now include catalog create/edit/archive failures plus earlier stock, measurement and spool lifecycle states. Error/unavailable states for `assign_location`, `new_spool`, and `edit_spool` remain open; do not re-add the unstable UI tests until the Qt teardown interaction is isolated or use a non-Qt test seam. Continue with stable non-modal controls and report/history actions.


## E05.08 checkpoint: empty catalog guard for spool creation — 2026-10-29

Added `test_studio_add_spool_empty_catalog_shows_guidance_without_mutation`: when no material profile exists, the add-spool action shows the existing guidance and creates nothing. The registry now cites empty, normal creation, and inventory unavailable/error evidence for `new_spool`. Focused test passed; `uv run ruff check src tests` clean; ordered full suite passed **600 /485 subtests, exit 0**.

The experimental `assign_location` and add/edit spool error UI tests were removed after repeatedly triggering a native Windows Qt access violation only in the combined suite, despite focused success. Product code is unchanged. Those error states remain open; current full-suite command runs the Studio module first, then other test files without recollecting it.


## E05.08 checkpoint: history read failures are contained — 2026-10-29

`StudioWindow.show_history` now reads ledger history, measurement history, and cost summary inside one error boundary. A failed read clears stale displayed details, keeps compensation disabled, and reports only the exception type through the existing safe error UI. Extended the existing `test_history_distinguishes_calculated_and_printer_usage` to exercise all three read failures without adding Qt fixtures. Updated the `history_selection` action registry evidence.

Validation: focused test passed; Ruff clean; ordered full suite **600 passed /485 subtests, exit 0** (Studio first, remaining files once). E05.08 remains partial: assignment-location and add/edit-spool failure UI states still open; experimental tests for these paths destabilized full Qt teardown and were removed. No live database or HaspelSync changed.


## E05.08 checkpoint: registry status reflects actual coverage — 2026-10-29

Updated the 18-row inventory action registry: `Частково виконано` now marks new_spool, edit_spool, assign_location, choose_columns, and catalog controls whose complete four-state matrix is not yet evidenced. Normal/error states already covered remain linked to tests; no row claims complete coverage by default. The registry contract test confirms all 18 handlers exist on `StudioWindow` and each row has evidence. Focused contract test passed; Ruff clean. Latest full ordered suite remains 600 passed /485 subtests, exit 0.


## E05.08 checkpoint: location assignment failure coverage stabilized — 2026-10-29

Extended existing `test_studio_creates_and_assigns_storage_location_without_stock_mutation` (no extra Qt test fixture) to simulate unavailable backend while detaching a location. The UI reports OSError and spool plus ledger remain unchanged. The same test first performs successful creation/assignment; empty/no-selection is covered by the inventory guard test. Registry row `assign_location` is now `Перевірено`.

Validation: focused test passed; ordered full suite **600 passed /485 subtests, exit 0**; Ruff clean. Standalone parameterized location error tests had destabilized Qt teardown, so the evidence is integrated in the existing fixture. E05.08 remains partial for other registry rows.


## Checkpoint: Qt shutdown remains intermittent after full pass — 2026-10-29

After the 600 passed /485 subtests ordered full suite exited 0, an identical repeat completed the same test counts but exited -1073741819 with a Windows native access violation after pytest summary and no Python frame. Ruff is clean. Treat assertions as passed but the Windows Qt process teardown as intermittent; do not claim the test runner is stable. Latest useful code changes remain history-read error containment and location-assignment refusal evidence. E05.08 stays partial.


## E05.08 checkpoint: catalog controls have empty-selection coverage — 2026-10-29

Extended the existing catalog workflow test to assert edit-material, edit-brand, and archive-brand controls are disabled before a selection. Combined with normal create/edit/archive tests and the 9 catalog invalid/unavailable cases, five catalog registry rows are now `Перевірено`. Targeted catalog set: 11 passed; Ruff clean.

Latest ordered suite completed **600 passed /485 subtests** with Ruff clean but exited -1073741819 after summary, no Python frame; another identical suite earlier exited 0. Windows Qt teardown is intermittent. E05.08 remains partial: new_spool, edit_spool, and choose_columns negative paths remain open; no live application data changed.


## E05.08 checkpoint: column preference save failure handled — 2026-10-29

Extended the existing column chooser test to simulate `save_settings` OSError. The chooser reports `settings.invalid` and leaves the currently visible columns unchanged; normal persistence and the mandatory identity column remain covered. Registry row `choose_columns` is now `Перевірено`. Focused test and Ruff passed; ordered full suite **600 passed/485 subtests, exit 0**.

Only `new_spool` remains explicitly partial in the registry; its empty-catalog and normal paths are proven, while adding UI invalid/unavailable cases previously correlated with a full-suite native Qt teardown failure. The suite also has intermittent post-summary access violations, so keep the result evidence precise.


## E05.08 completed: native inventory action registry — 2026-10-29

All 18 registered Studio inventory controls now have mapped handlers and verified normal/empty/error/unavailable behavior where applicable. Added coverage for catalog creation/edit/archive failures, empty material catalog for spool creation, location assignment failure with unchanged spool/ledger, settings persistence failure with unchanged column visibility, and safe history read errors. Existing stock, measurement, spool lifecycle, compensation, projection, and refresh paths are included. The registry distinguishes full coverage and partial evidence; all 18 rows are now `Перевірено`. No inventory action in this registry requires the legacy web UI.

Validation: focused catalog states 11 passed, focused add-spool state passed, registry contract passed; Ruff clean; latest ordered complete suite **600 passed /485 subtests, exit 0**. Some preceding complete runs showed intermittent post-summary Windows Qt access violations despite all assertions passing; latest run exited cleanly. No live database, HaspelSync runtime, installation, or packaging was modified. Next: proceed to the nearest incomplete checklist step after E05.08.


## E06.01 checkpoint: network autofill and Studio profile audited — 2026-10-29

Revalidated the manual Bambu host/IP import path, SSDP autofill identity checks, local Bambu Studio profile matching, TLS fingerprint confirmation, no-save on rejected confirmation, and the configured-printer table/selected-row probe target. `StudioBackend.printers` returns enabled profiles ordered by name; `StudioWindow.refresh` renders all rows and `probe` resolves the selected row’s own id/provider. Ambiguous Bambu discovery without an IP is rejected instead of guessing; users can supply the intended IP. Independent multi-printer telemetry/slot isolation remains E06.07.

Evidence tests: `test_bambu_network_autofill.py`, `test_bambu_studio_import.py`, `test_printer_discovery.py`, `test_network_autofill_populates_without_saving_credentials`, `test_bambu_enrollment_requires_explicit_certificate_trust`, and `test_printer_probe_shows_matches_and_mounts_only_after_confirmation`. Focused run: 25 passed + 9 subtests, exit 0; Ruff clean. No application DB, saved printer settings, credentials, physical printer or installed build was changed. E06.01 is done; next dependency: E06.02 connection wizard/profile lifecycle audit.


## E06.02 checkpoint: Studio can remove a selected printer safely — 2026-10-29

Added a disabled-until-selected `Remove connection` action to the Studio printer page. It requires confirmation and delegates to the existing `remove_configured_printer` service; success refreshes the visible list and reports that history remains. The service deletes the OS credential and connection profile, disables rather than deletes the printer row, and preserves print history. Added bilingual strings and a UI test for no selection/cancel/confirm.

Validation: focused UI + service regression — 2 passed, exit 0; Ruff clean. No real printer, DB, credential store or installed build was changed. E06.02 remains partial because in-place editing and physical acceptance are outstanding. Next: design a safe existing-profile edit transaction that tests the new endpoint/credential before replacing the old secret/profile, with rollback coverage.


## E06.03 checkpoint: adapter subscriptions are not yet hosted by Studio — 2026-10-29

The provider-side async streams exist: Bambu LAN MQTT and local HTTP polling expose `subscribe_events`; their unit/integration tests cover repeated/suppressed events. `StudioWindow` still has explicit one-shot `probe` only. No app-lifetime worker, opt-in monitor control, or window-close cancellation/join path is present. Audit did not connect to a real printer. E06.03 is in progress; next add an explicit opt-in lifecycle worker with a bounded event handoff and deterministic stop, then test worker shutdown and repeated events. E06.02 remains partial until profile editing is supported.


## E06.03 completed: explicit long-lived provider monitor — 2026-10-29

Added `PrinterMonitorTask` as a cancellable QThread host for the saved read-only provider event stream. The Studio page starts it only after an explicit warning/confirmation and stops it on button or window close. The status label displays current job state/progress without payload or credential details. The configured profile factory reads secrets from the OS secret store. Window close waits until provider disconnect and thread teardown; the worker QObject is deleted after its finished signal. Bambu disconnect now notifies the report condition and `_wait_report` exits when the connection flag clears, avoiding a full report timeout on cancellation.

Validation on Python 3.12: ordered complete suite **604 passed /485 subtests, exit 0**; Ruff clean; focused mypy on monitor/configuration/Bambu adapter clean with imports silenced. Full project mypy still reports 24 unrelated/existing diagnostics in other application/UI/storage paths; tracked separately, no blanket clean claim. One earlier full-suite run had post-summary Qt access violation; after releasing the monitor QThread with `deleteLater`, repeat completed cleanly. E06.03 done. Monitor events are currently visual only; E07 durable receipt wiring is not implied. E06.02 remains partial (profile editing, device acceptance). Next: complete safe profile editing before reconnect/stale recovery work.


## E06.02 checkpoint: edit safe printer display fields — 2026-10-29

Added `update_printer_details` and a Studio action that edits only display name/model for a selected configured printer. It validates fields and updates the enabled printer in an immediate SQLite transaction with revision checking; it does not touch provider host, serial, TLS pin, credential reference, spool/job identity or history. Added UI and service tests proving those connection values remain stable. Combined with the earlier confirmed remove action, Studio has safe display-profile edit and connection removal.

Validation: four focused edit/remove tests passed; full ordered suite **604 passed /485 subtests, exit 0**; Ruff clean; focused mypy for monitor/configuration/Bambu adapter clean. E06.02 remains partial because endpoint/LAN code rotation with connection re-test/rollback and live physical acceptance are outstanding. E06.03 done. Next: E06.04 reconnect/backoff and truthful offline/stale behavior; the persistent monitor still only renders events, it does not persist receipts/jobs.
## E06.04 checkpoint: retry/backoff and bounded monitor handoff — 2026-10-29

Implemented in `src/ufm/ui/printer_monitor.py`: retry only retryable `ProviderError`; exponential reconnect delay capped at 30 s; each provider disconnects before delay; cancellation stops retry wait; authentication/TLS and unexpected errors fail closed. `state_changed` exposes connecting/online/offline/retrying; `StudioWindow` renders those states. Replaced per-event Qt emission with thread-safe latest-event slot and one pending `event_available` signal, bounding queued events to one. Added tests for retry, non-retryable auth, stop during backoff, coalescing, existing monitor shutdown and opt-in UI. Focused set: 6 passed; Ruff clean; focused mypy for `printer_monitor.py` clean.

CSV E06.04 is `Частково виконано`; remaining: heartbeat-based stale detection, verified OS suspend/resume recovery and physical printer acceptance. Silence alone is not treated as stale because current adapters suppress unchanged observations. A monitor still starts only after user confirmation, and the app does not auto-restore a printer connection on restart. Ordered full suite after changes: **610 passed /485 subtests, exit 0**; Ruff clean; focused mypy `printer_monitor.py` clean. At checkpoint, available usage was 74% primary /47% weekly. Next: inspect provider health/transport heartbeat guarantees before implementing stale timing; design/test sleep-resume detection only with reliable OS signals. No live printer, database, credentials, build, or HaspelSync state changed.

Protocol evidence: local Bambu Studio `D:/GIT/BambuStudio/src/slic3r/GUI/DeviceWeb/ViewModels/FilamentManager/FilamentManagerVM.cpp`, `HandleMachine("request_pushall")`, calls `command_get_version()` then `command_request_push_all(/*request_now=*/true)`. Its comment says the manual refresh requests a full device state so UI need not wait for the next spontaneous push. This supports designing an explicit read-only request/response watchdog, but does not prove periodic unsolicited MQTT reports or a safe interval. Next implementation should rate-limit refresh requests, tie stale recovery to a newly received response, and test both adapters; do not treat absence of changed-job events as stale.

## E06.04 checkpoint: request/response freshness watchdog — 2026-10-29

Added adapter health checks to the monitor loop every 15 seconds. Bambu `health()` sends read-only `get_version` + `pushall` on the authenticated TLS MQTT request topic and waits for `_report_generation` to advance on a valid `print` report; non-print packets do not certify fresh job data. A timeout yields retryable `provider.stale`; the monitor surfaces stale then uses the existing disconnect/backoff/reconnect. HTTP providers use their existing real health endpoint (`/api/version` or `/server/info`); degraded health also recycles the provider. No changed-job event is required to certify transport freshness.

Evidence: local Bambu Studio `DeviceManager.hpp` defines `REQUEST_PUSH_MIN_TIME` as 3000 ms; `DeviceManager.cpp::command_request_push_all` includes version/push_target and throttling. The 15-second monitor interval exceeds that local Studio minimum, but this is not physical-device acceptance. Targeted 9 tests passed, including fresh report, timeout, and stale-triggered reconnect; Ruff and focused mypy for monitor/Bambu are clean. Ordered full Python 3.12 suite: **613 passed /485 subtests, exit 0**. E06.04 stays partial: no real-printer acceptance, no verified Windows sleep/resume signal, and no persistent auto-restored monitor session. No live printer, database, credentials, build, or HaspelSync state changed. Next: inspect stable Windows wake notification and implement only with deterministic tests; retain explicit opt-in on app restart.

## E06.04 checkpoint: Windows sleep-gap recovery — 2026-10-29

Added `src/ufm/ui/windows_power.py::WindowsResumeDetector`. On Windows it compares `GetTickCount64` uptime (includes sleep/hibernation) against `QueryUnbiasedInterruptTime` awake-time; a sleep gap above 2 seconds is surfaced once. The monitor checks on its 15-second health cadence, emits stale, disconnects, and re-enters its capped retry flow. Unsupported platforms/APIs return no detection and continue ordinary provider health checks. Microsoft documentation: [GetTickCount64/Windows Time](https://learn.microsoft.com/en-us/windows/win32/sysinfo/windows-time) says elapsed time includes sleep; [QueryUnbiasedInterruptTime](https://learn.microsoft.com/en-us/windows/win32/api/realtimeapiset/nf-realtimeapiset-queryunbiasedinterrupttime) excludes sleep/hibernation.

Tests: pure clock-gap/no-platform fallback and monitor reconnect after simulated resume. Focused set: 12 passed; Ruff clean; focused mypy for `windows_power.py`, `printer_monitor.py`, `bambu_lan.py` clean. Ordered full Python 3.12 suite: **616 passed /485 subtests, exit 0**. E06.04 remains partial pending actual Windows sleep/resume and Bambu printer acceptance plus user-approved restart policy; monitor remains explicit opt-in. No real printer, database, credentials, installer, or HaspelSync state changed. Available usage after suite: 71% primary /47% weekly.

## E06.05 checkpoint: read-only live detail panel — 2026-10-29

`PrinterMonitorTask` now performs `get_status()` once after connect and on each healthy 15-second health check; status snapshots use a separate thread-safe latest-value slot with one pending Qt notification. UFM Studio displays localized print state/progress/current layer, confirmed nozzle/bed temperatures, feed-system kind and slot count (AMS/external where provider reports them). Unknown values remain unknown. Existing job event snapshot and status snapshot remain visual only, not durable receipt/finalization evidence. No normalized live printer error payload currently exists; FAILED/provider exception is the available error indication. Sensor/capability reporting belongs to E06.06.

Evidence: `test_studio_monitor_details_render_confirmed_printer_snapshot`; monitor subset 8 passed; full ordered Python 3.12 suite **617 passed /485 subtests, exit 0**; Ruff clean. Focused mypy for new monitor/power/provider code clean; the full `studio_window.py` check still reports its 10 existing diagnostics in unrelated methods. E06.05 remains partial until normalized errors and capability/sensor data are incorporated and real-printer acceptance is available. No live printer or actual DB/credential changed.


## E06.06 handoff: capability panel — 2026-10-29

Studio now obtains adapter capabilities through the monitor worker and renders all 15 `PrinterCapabilities` observations with localized KNOWN true/false, UNKNOWN, UNAVAILABLE and UNSUPPORTED states, adapter type, and latest observation time. Provider source is mapped from the configured provider type; model names are not used to infer support. Added bilingual labels and a focused rendering test. Validation: ordered Python 3.12 suite 618 passed /485 subtests, exit 0; Ruff clean; JSON loads. Graph-first navigation used `D:/graphify-out/bambu-ufm/enriched/graphify-out/graph.json` (query pointed to DTO/monitor/Studio); implementation/test evidence was then confirmed in live files. E06.06 remains partial pending checking capability truthfulness on physical models. Current CSV totals: 118, Partial 27, Done 30, Planned 60, In Progress 1.

Next: E06.07, inspect the configured multi-printer read paths and tests for event/status/slot/credential isolation. Verify against source/tests; do not connect physical devices or modify real credentials. No commit/push/deploy. Latest usage remaining after this stage: 67% primary /46% weekly.


## E06.07 handoff: two-printer adapter separation — 2026-10-29

Added `test_two_configured_printers_keep_credentials_events_and_slots_isolated`. In a disposable SQLite DB it enrolls two Bambu printer profiles with different host/serial/access codes, rebuilds each using the real configured profile factory, and asserts separate IDs, provider instance IDs and OS-secret references. Fixture reports then prove distinct source epochs, AMS system/slot tag UUIDs, event scope (printer/provider IDs) and progress. This is adapter/configuration integration evidence; no physical printer was connected. Ordered Python 3.12 full suite **619 passed /485 subtests, exit 0**; Ruff and compileall clean. Current CSV: 118 rows; Partial 28, Done 30, Planned 59, In Progress 1. E06.07 stays partial pending real-device acceptance. E06.06 remains partial pending per-model capability acceptance.

Next work: inspect all remaining rows in checklist in dependency order. Avoid hardware-gated steps; do not modify real data/credentials. Latest usage remaining: 66% primary /46% weekly.


## E06.02 handoff: verified Bambu LAN connection rotation service — 2026-10-29

Added `update_bambu_printer_connection` in `configuration.py`. It verifies the candidate connection and obtains a status snapshot before writing. It retains the current CA certificate path/fingerprint, performs optimistic revision checks for the profile and printer, rotates the credential reference, and restores the old secret under a fresh reference if the database transaction rolls back. The tests prove failed connect leaves profile/secret unchanged and injected DB rollback restores the working secret. Ordered Python 3.12 suite: 621 passed /485 subtests, exit 0; Ruff clean. E06.02 stays partial until a Studio dialog and physical printer/TLS acceptance are complete. No live printer, user DB, or Windows credential store was touched.

Next: add selection-gated Bambu LAN edit dialog with masked access code, serial and host prefill, explicit verify/save action, safe success text, and error-path test. Keep the existing TLS trust pin and profile id. Current CSV: 118 rows; Partial 28, Done 30, Planned 59, In Progress 1; BOM preserved. Usage remaining 65% primary /46% weekly.


## E06.02 handoff: Studio LAN connection edit — 2026-10-29

Studio now has a Bambu-only `Edit LAN connection` action. It is disabled for local HTTP providers, while another task/monitor is active, or without selection. The dialog pre-fills host/serial, masks LAN code, and only proceeds after explicit Save; it states the current certificate/pin is retained. It calls the verified async replacement service in background `Task`. `StudioPrinter` now carries serial from the local backend projection. Tests cover selection/provider gating/password masking, successful rotation, failed connect with untouched old profile/secret, and database rollback with old secret restoration. Ordered Python 3.12 suite **622 passed /485 subtests, exit 0**; Ruff clean; focused mypy configuration.py clean. Combined config/backend mypy still reports one pre-existing `StudioBackend.create_storage_location` missing return at line 522, not changed here. E06.02 remains partial until physical Bambu/TLS acceptance and explicit certificate replacement UX.

Latest usage remaining: 65% primary /46% weekly. CSV has 118 rows; Partial 28, Done 30, Planned 59, In Progress 1. No physical device, user DB, credential store, packaging, or HaspelSync runtime touched. No commit/push/deploy.


## E06.05 handoff: monitored per-slot material observations — 2026-10-29

Added a dedicated live slot details label in Studio. It presents feed-system type, provider slot key, loaded/empty/unknown occupancy and exact reported remaining mass when available. UNKNOWN/UNAVAILABLE/UNSUPPORTED stay distinct; no unknown-to-zero conversion. Raw tray UUID/tag UID are deliberately omitted from the live text. Temperature/progress/layer availability is likewise rendered from each observation's Availability. Test `test_studio_monitor_details_render_confirmed_printer_snapshot`; ordered Python 3.12 suite 622 passed/485 subtests; first attempt had intermittent native Qt access violation after the success summary, identical repeat exited 0; Ruff clean. E06.05 stays partial because the provider DTO currently has no normalized printer error text/other sensor inventory and there is no physical-device acceptance.

CSV 118 rows; Partial 28, Done 30, Planned 59, In Progress 1. No live device/data was accessed. Next: inspect E07.03 and E07.04 live ingestion gaps; choose a software-verifiable incremental item and preserve its error/idempotency boundaries. Usage remaining 64% primary /46% weekly.


## E07.03/E07.04 handoff: підтверджено відсутність runtime ingestion bridge — 2026-10-29

Граф `D:/graphify-out/bambu-ufm/enriched/graphify-out/graph.json` навів на `PrinterEvent`, `PrinterMonitorTask`, `ReceiptIngestion` і `ProjectionDrain`; фактичний код перевірено після графа. `rg` під `src` підтвердив, що ReceiptIngestion/ProjectionDrain наразі не викликаються. Studio бере `take_latest_event()` і показує єдиний останній snapshot; цей latest-value слот coalesces події, отже він не є durable delivery transport для lifecycle/application. Не під’єднувати його напряму до списання.

Чекліст E07.03 і E07.04 доповнено точними незавершеними умовами. Наступний крок: тестована bounded FIFO без втрати подій; при переповненні явний overflow/backpressure/offline сигнал, а не тихе видалення. Після цього окремо перетворювати лише нормалізовані DTO з перевіреною occurrence/run identity у receipt protocol; неоднозначні run-и — quarantine/manual review. No source code, real database, printer, credentials, packaging, or HaspelSync state changed.


## E07.04 handoff: bounded monitor FIFO — 2026-10-29

`src/ufm/ui/printer_monitor.py`: replaced the one-value event slot with a receive-ordered deque capped at 256; added `take_pending_events()`; retained `take_latest_event()` for display-only UI consumption; `_publish()` returns false on overflow and the provider loop stops explicitly with `PrinterEventBufferOverflow` rather than evicting observations. Added integration tests for batch order and overflow retention in `tests/integration/test_studio_window.py`. Ruff passed on both changed files. Tests were not run.

Boundary: this FIFO alone is not durable; Studio still calls the display latest-event API and ReceiptIngestion has no `src` runtime caller. No accounting is activated. Next implement a separate batch consumer with receipt DTO conversion and exact identity validation; quarantine observations lacking run identity, and preserve no-silent-loss/backpressure semantics. E07.03/E07.04 remain partial. No printer, real database, credentials, packaging, or HaspelSync state changed.


## E07.03/E07.04 handoff: збереження окремих показників прогресу — 2026-10-29

Extended worker `JobMessage` with optional strict `current_layer` and `progress_bp`; `completed_layers` remains distinct. `JobProjectionCommands` persists these separately on `PrintJob`, includes them in same-sequence conflict detection, rejects current-layer/progress regression, and returns both in `JobMappingObservation` history. The existing `print_job.current_layer` and `progress_bp` columns need no migration. Added `test_verified_current_layer_and_progress_survive_projection_restart` and `test_current_layer_and_progress_regressions_are_conflicts` in `test_job_projection.py`; not run. Ruff passed for all five modified Python files.

The earlier E07.04 FIFO remains bounded to 256; overflow does not evict an older queued event and terminates the monitor explicitly. Test updates for ordered drain and overflow retention are also unrun. Important limit: no runtime `ReceiptIngestion` caller exists; Studio uses `take_latest_event()` for display, so this work does not create durable live ingestion or automatic material deductions. E07.03/.04 remain partial. Next: implement a separate event-batch consumer, normalize DTOs only when provider run identity is proven exact, persist receipts, and quarantine unknown occurrences. No tests, live printers, real DB, secrets, build or HaspelSync were changed outside source/docs.


## E03.07 handoff: per-printer accounting owner policy — 2026-10-29

ADR-001 now specifies `LEGACY_ACTIVE`, `CUTOVER_READY`, `UFM_ACTIVE`, and `REVIEW_ONLY` per printer, with ordered snapshot/uncertain-booking resolution/old-writer shutdown/UFM enablement, and a disable-UFM-first rollback. Checklist E03.07 moved Planned → Partial: this is an operational transition rule, not a cross-process lock. Current HaspelSync `/api` continues to book to Spoolman, while UFM's isolated ledger and desktop have no shared authority endpoint; E03.06 writer replacement remains incomplete. Therefore do not enable UFM automatic deduction while HaspelSync may still write for that printer. Next dependency is E03.06: define/implement a narrow, fail-closed authority handoff, or keep the release in preview-only until old writer is deactivated and verifiable. CSV 118 rows; Partial 29 / Done 30 / Planned 58 / In Progress 1; BOM preserved. No source runtime, real printer, database, secrets, build, or HaspelSync behavior changed.


## E05.05 handoff: Studio QR label export — 2026-10-29

Added `export_qr_label()` and a selection-gated button in the inventory inspector. It writes the existing `spool_label_svg(EntityId)` result to a user-chosen `.svg`; payload contains only the canonical internal spool UUID. Added bilingual action/error keys. Ruff passed on `studio_window.py`; `studio_strings.json` parses. No tests were run. E05.05 stays Partial: direct printer workflow, text-bearing layout, batch export and full E02 action parity remain. CSV now 118 rows; Partial 30 / Done 30 / Planned 57 / In Progress 1; UTF-8 BOM preserved. No code changed the spool ledger, real DB, printer, credential store, EXE or HaspelSync runtime.


## E05.05 handoff: додано прямий системний друк QR — 2026-10-29

`studio_window.py` тепер має selection-gated кнопку прямого друку. Друк бере SVG QR через `spool_label_svg(EntityId)`, показує `QPrintDialog`, рендерить QR 45 мм по центру сторінки; cancel не змінює дані. Додані двомовні рядки помилки/дії. Після цього етапу `uv run ruff check src/ufm/ui/studio_window.py` — clean; `uv run python -m json.tool src/ufm/ui/studio_strings.json` — valid. Тести та фізичний друк не запускалися. E05.05 лишається Partial: текстовий макет етикетки, керування розмірами та batch print не реалізовані. QR ідентифікує UFM spool UUID; він не запускає mount чи debit. CSV BOM збережений; статуси оновлені в PROJECT_PROGRESS. Живий ledger/БД, принтери, credentials, EXE та HaspelSync не змінювалися.


## E05.05 handoff: текстовий QR-макет етикетки — 2026-10-29

Доданий pure renderer `spool_label_card_svg()` створює самодостатній SVG 80×45 мм: escaped назва/профіль/матеріал, localized колір і поточний залишок, необов’язковий hex color swatch та QR з канонічним UFM UUID. UI export і системний print тепер використовують цей макет; друк центрує його на сторінці після стандартного `QPrintDialog`. SVG helper не записує файли і не змінює inventory. `uv run ruff check src/ufm/integrations/qr/__init__.py src/ufm/ui/studio_window.py` — clean; JSON strings valid. Тести та фізичний друк не запускалися. E05.05 досі Partial: batch workflow/розмірні параметри/full E02 parity незавершені. Наступна дія: окремий batch selector для кількох етикеток, page-per-label, без автоматичного списання. Ні runtime ledger, ні принтери/БД/секрети/EXE/HaspelSync не змінювалися.


## E05.05 handoff: пакетний друк QR-етикеток — 2026-10-29

Додано кнопку batch print на панелі інвентарю: модальний список з checkboxes дозволяє позначити кілька котушок; після підтвердження відкривається один системний `QPrintDialog`, а кожен SVG макет 80×45 мм друкується на окремій сторінці. Експорт і одиночний друк використовують той самий локалізований картковий SVG із назвою, профілем/матеріалом, кольором, поточним залишком і UUID QR. Ruff clean на `studio_window.py` та `integrations/qr/__init__.py`; JSON валідний. Не запускав тести/фізичний друк. E05.05 лишається Partial: форматування/preview та реальне приймання принтером етикеток не доведено; решта E02 parity лишається окремою роботою. No ledger/debit, database, live printer, credentials, EXE or HaspelSync changes. Наступне: додати керовані параметри розміру/відступу й preview, не змінювати payload і не вводити списання через QR.


## E05.05 handoff: налаштовуваний розмір і batch print — 2026-10-29

Додано діалог ширини/висоти 20–300 мм (default 80×45) перед QPrintDialog; renderer масштабує цільовий прямокутник вниз до доступної друкованої області, зберігаючи співвідношення сторін. Раніше доданий batch selector передає кілька котушок у спільний print job і викликає `newPage()` між етикетками. Ruff clean на QR renderer і Studio; JSON valid. Не запускали тести або фізичний друк. E05.05 залишається Partial: позиція/поля і підтвердження на конкретному принтері, повний parity E02 — відкриті. QR не змінює ledger. Наступна дія: перевірити під час UI/принтерного приймання page break, розмір та край друкованої області; при виявленні різниці скоригувати розрахунок без зміни формату ID.


## E05.05 handoff: batch SVG export — 2026-10-29

Спільний selector вибирає кілька котушок для друку або SVG export. Batch export створює нову папку `ufm-labels-<random>` у вибраній директорії, файли названі внутрішнім UUID; попередні експорти не зачіпаються. Batch print працює через один QPrintDialog з окремою сторінкою на label. Є діалог ширини/висоти та self-contained SVG із читабельними атрибутами й QR. Ruff clean; JSON valid; tests і printer hardware не запускалися. E05.05 Partial: поля/позиція і фізичне приймання відкриті, повний E02 parity теж. No ledger mutation or integration with label QR triggering stock operations.


## E05.08 handoff: inline validation у material/brand forms — 2026-10-29

`StudioWindow.form()` тепер при натисканні Save валідовує required line edits і під’єднані validators, показує localized помилку та лишає діалог відкритим, фокусуючи проблемне поле. Material form задає C-locale QDoubleValidator для diameter/density/температур/max volumetric speed/drying temp, QIntValidator для drying duration та bounded text lengths; brand create/edit вимагає непорожнє ім’я й обмежує його 200 символами. Backend / CatalogCommands лишається єдиним persistence path; direct SQL не доданий. Ruff clean; JSON valid. Не запускали UI tests. CSV E05.08 лишається Partial до acceptance цих змін та покриття решти actions.


## E05.08 handoff: виправлення типізації валідатора форм — 2026-10-29

Початковий mypy прогін після inline validation знайшов три нових помилки у зміненій ділянці: shadowing `name` з Qt widget, тип `QValidator.validate()` повернення PySide stub як object, і невикористаний enum після виправлення. Перейменовано на `name_field`, validation читається через `QLineEdit.hasAcceptableInput()`, unused import прибраний. Повторний mypy по `studio_window.py` і QR helper лишає 12 діагностик у старих/unrelated функціях — datetime combine, QAbstractItemModel.item, optional Mass, selected_brand typing, інші старі callbacks; нових помилок у цій зміні немає. Ruff clean і JSON валідний. UI tests не запускалися.


## E05.08 handoff: inline required-name guard для нової котушки — 2026-10-29

У `add_spool()` назва тепер позначена required і обмежена 200 символами; нотатки — 4000. Загальний `form()` показує localized inline-form error й не закриває діалог на порожньому/невалідному значенні. `docs/UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv` оновлено. Ruff та JSON clean. UI acceptance не запускався; це кодова перевірка, не тестовий доказ. DB/ledger не змінювалися.


## E05.07 handoff: налаштування мови UI — 2026-10-29

System page now offers Ukrainian/English selection and Save; locale values are allowlisted and persisted via validated atomic `save_settings()`. Change to a different locale shows a restart-required notice because existing widgets are not retranslated live. Failure uses sanitized settings error and leaves in-memory settings unchanged. Ruff clean, strings JSON valid. mypy retains same 12 existing errors elsewhere; no new diagnostics. UI acceptance not run. E05.07 remains Partial; native log-level/log viewer and additional system controls remain. No tests, runtime DB, printers, or secrets touched.


## E05.07 handoff: UI керування рівнем журналу — 2026-10-29

System page offers DEBUG/INFO/WARNING/ERROR/CRITICAL selection. Input is allowlisted, persisted with validated atomic settings writer, then `container.logger.setLevel()` applies it immediately. Log file contents remain outside UI to avoid exposing operational data. Existing localized language selection persists and requires restart to retranslate widgets. Ruff clean, JSON valid; Studio mypy still has same 12 existing diagnostics in other code, no new ones. No tests. E05.07 remains Partial: no in-app log viewer or full system controls.


## E05.08 handoff: оновлено inventory action registry QR workflows — 2026-10-29

`docs/UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv` доповнено рядками single export, single print, batch export і batch print. Зафіксовано selection/cancel, QPrintDialog/page-per-label, SVG unique subfolder, localized failure та обмеження: помилка під час batch print може статися після частини фізичного job; rollback друку неможливий. 22 action rows. Для нових QR flows UI acceptance не заявляється, hardware printer не перевірявся. Main checklist counts/statuses unchanged; QR codes remain identity-only with no accounting write.


## E05.08/E05.07 handoff: закрито Studio mypy діагностики, уточнено acceptance статус — 2026-10-29

У `studio_window.py` виправлено 12 типізаційних діагностик: Qt date перетворюється через ISO `date.fromisoformat`, combo model явно каститься до `QStandardItemModel`, manual measurement перевіряє optional net evidence, `selected_brand` має return type, а monitor display helper — generic `Observed[T]`/`Callable`. Повтор: `uv run mypy src/ufm/ui/studio_window.py src/ufm/integrations/qr/__init__.py` → `Success: no issues found in 2 source files`; Ruff clean; strings JSON valid. Тести не запускалися. E05.08 статус приведено до Partial: registry має 22 рядки, але чотири нові QR workflows та inline form validation ще без UI acceptance. E05.07 locale/log-level UI реалізовано, але live language rebuild/log viewer залишаються. Checklist 118 rows: Partial {c['Частково виконано']} / Done {c['Виконано']} / Planned {c['Заплановано']} / In Progress {c['У роботі']}; BOM preserved.


## E05.07 handoff: безпечний перегляд журналу подій — 2026-10-29

System page додає read-only viewer для `ufm.log`. Він читає лише останні 512 KiB/300 рядків, відхиляє понад 2 KiB рядки, парсить JSON і відображає тільки синтаксично перевірені ISO timestamp, один із п’яти відомих severity і подію з pattern `[a-z][a-z0-9]*(?:_[a-z0-9]+)+`. `fields`, сирий рядок і непідтримуваний запис у UI не показуються; помилка читання локалізована. Ruff clean; mypy Studio+QR clean; strings JSON valid. UI acceptance не запускалося. E05.07 remains Partial.


## E05.07 handoff: системний inventory CSV export та action registry — 2026-10-29

Додано `docs/UFM_STUDIO_SYSTEM_ACTION_REGISTRY_UK.csv` із сімома системними діями. Новий `export_inventory` формує versioned `ufm_inventory_v1` CSV: UTF-8 BOM, semicolon, spreadsheet formula escaping, пусте поле для невідомого залишку, exact mg→g format; printer credentials не експортуються. Файл зберігається через Qt `QSaveFile` (atomic commit); backend read виконується worker-ом після вибору target. `view_safe_logs` виводить лише валідовані timestamp/level/event, довільні поля відкидає. Ruff і mypy для Studio/QR clean; JSON валідний. UI acceptance не запускався. E05.07 Partial: UI acceptance нових controls і решта системної parity відкриті. Живі дані не змінювались.


## E07.03/E07.04 handoff: аудит payload та run identity — 2026-10-29

Перевірено код після графової навігації. `PrinterEvent` у `src/ufm/application/dto/providers.py` має `payload_hash`, але не зберігає первинний payload. Bambu `subscribe_events()` у `src/ufm/integrations/printers/bambu_lan.py` хешує canonical набір snapshot полів; провайдер заповнює `provider_task_id`, `provider_subtask_id`, `provider_job_id`, але не `provider_run_key`. Local HTTP теж видає локальний sequence event key у межах нового source epoch. `ReceiptIngestion` приймає лише Status/Job/Slots worker messages, рахує digest із переданих bytes і не має runtime caller у `src`; `ProjectionDrain` теж не заведений у runtime. Тому поточний FIFO не є durable ingress, а task/job ID не прирівняно до exact occurrence без контракту джерела.

E07.03/E07.04 лишаються частковими. У CSV уточнено докази і відсутні умови. Статуси (118): Partial 31 / Done 29 / Planned 57 / In Progress 1. Виконано лише source audit і документаційний checkpoint; код/тести/живі принтери не змінювали/не запускалися. Основні ліміти перед роботою: 98% п’ятигодинного, 45% тижневого залишку. Наступний крок — перевірити авторитетні semantics полів і provenance у зафіксованих fixtures/протоколі; після цього визначати bounded fail-closed consumer. Списання лишається вимкненим до exact run identity та єдиного writer authority.


## E07.03 design checkpoint: звірено шаблон HaspelSync recovery — 2026-10-29

Локальний HaspelSync: `mqtt.js` виявляє перехід non-active → active, зберігає `startedAt`, а при старті процесу посеред активного друку відновлює час/файл/слоти через printstate за printer + job name. На термінальному стані він робить один full/partial calculation. `bookings.js` записує pending intent до зовнішнього HTTP і використовує SHA-256([printerId, startedAt, itemKey]); зміна spool/mass/endpoint/state конфліктує, а невизначена відповідь не повторюється автоматично. Це стійкий приклад recovery, але jobName+локальний час не прирівнюється до exact provider run identity.

Локальний Bambu Studio `src/libslic3r/ProjectTask.hpp` описує `BBLSubTask.task_id` як plate ID, `task_name` — зазвичай ім’я файла; це не визначає семантику ID в кожному локальному MQTT report. В UFM у Bambu adapter `provider_run_key` наразі не заповнюється. Порівняння та дизайн-рішення записані в `docs/CONSUMPTION_COMPARISON_UK.md`; E07.03 залишається частковим. CSV: 118; Partial 31, Done 29, Planned 57, In Progress 1; UTF-8 BOM збережено. Тести/принтери не запускались. Наступне: шукати локальні MQTT fixtures/traces для одного файла у двох послідовних запусках і reconnect; якщо точного ключа немає, проектувати durable active-run recovery із quarantine, не підключаючи debit.


## E07.05 handoff: звірка наявного lifecycle coverage — 2026-10-29

Read-only аудит тестів/fixtures (нічого не запускав): `tests/integration/test_job_projection.py` містить synthetic сценарії для того самого файла у двох occurrence, пропущеного start, reset шару/hash та конкурентного іншого occurrence/epoch. Вони доводять application contract, але не поведінку живого MQTT reconnect чи принтера. HaspelSync `test/fixtures/reports/*.json` — по одному статичному `pushall` snapshot для моделей; audit структури показав різну наявність `task_id/subtask_id/job_id`, а на частині snapshot вони нульові. Це не послідовні lifecycle траси й не підтверджує exact per-print identity. E07.05 залишається частковим. Прогрес і checklist оновлено; BOM збережено. Наступна дія — отримати обезособлені локальні snapshots/trace для двох однакових послідовних друків і reconnect midprint або лишити ці acceptance залежними від реального принтера; автоматичний debit не активувати на синтетичних fixtures. Тести цього етапу не запускалися.


## E07.03 handoff: exact lifecycle timestamps у durable projection — 2026-10-29

Реалізовано необов’язкові `exact_started_at`/`exact_ended_at` та явні `printer_reported`/`provider_reported` source поля в strict `JobMessage`. Валідатор вимагає provenance-пару, дозволяє end лише для terminal state та відхиляє зворотний interval. `JobProjectionCommands` зберігає часи у вже наявні `PrintJob.started_at`, `completed_at`, `failed_at`, `cancelled_at`, а mapping history відновлює time і source з immutable receipt. Зміна exact time/source в одному occurrence, interval відносно вже збереженого початку та timestamps з майбутнього дають conflict/reject. `observed_at` не використовується як точний час. `0001` schema уже мала ці nullable колонки, нової міграції немає. Згенеровано `docs/WORKER_PROTOCOL_V1.schema.json`, оновлено протокол і lifecycle contract docs та checklist E07.03.

Статичні перевірки: `uv run ruff check src/ufm/application/dto/worker_protocol.py src/ufm/application/job_projection.py` — clean; `uv run mypy ...` для цих двох файлів — success; `python -m json.tool docs/WORKER_PROTOCOL_V1.schema.json` — valid. Тести не запускалися/не додавалися. BOM CSV збережено; 118 рядків, Partial 31 / Done 29 / Planned 57 / In Progress 1. Bambu LAN і HTTP providers залишають exact timestamps/provenance порожніми; live `ReceiptIngestion`/`ProjectionDrain` consumer не підключений, автоматичний дебет не ввімкнено. Наступне: перевірити фактичні timestamp semantics Bambu або залишати ці поля NULL до перевіреного джерела; exact run identity/consumer і єдиний writer лишаються окремими залежностями.

## E04.01/E04.07 handoff: metadata імпорту Spoolman — 2026-10-29

Імпортер зберігає стару форму `create_spool` для збереження idempotency fingerprint попередніх імпортів. Після неї окремо через `InventoryCommands.edit_spool` заповнюються лише порожні `lot_number`/`color_hex`; місце створюється `StorageCommands.create_location(StorageType.OTHER)` і призначається лише коли поле локації порожнє. Командні ключі metadata/location versioned і відокремлені від stock ledger. Це дає змогу повторити імпорт після переривання та не перезаписати пізніші ручні metadata.

Preview має лічильники партій, кольорів, локацій і непідтриманих metadata, відображені у Studio/desktop/CLI. Надто довгі чи некоректні поля не застосовуються й рахуються як unsupported. Дати купівлі/виробництва, batch hierarchy та шляхово-незалежний source identity не вигадуються. E04.01/E04.07 переведено у «Частково виконано». CSV: 118 рядків; Partial 33 / Done 29 / Planned 55 / In Progress 1; BOM збережено.

Статичні перевірки: Ruff clean; mypy clean для importer, Studio, desktop, CLI; локалізації JSON валідні. Тести не запускалися/не додавалися. Користувацькі бази не відкривались, БД не змінювалась. Наступне: дизайн E04.02 source identity, сумісний з переміщенням файла і розрізненням окремих інстансів.

## E04.02 handoff: межі source identity — 2026-10-29

Graph-first map (`D:/graphify-out/bambu-ufm/PROJECT_MAPS_UK.md`) вказує на окремі Spoolman import/preview модулі; source підтверджує, що `_source_instance()` у importer.py хешує resolved absolute path і використовує результат для device/profile/spool UUID та command keys. Після переміщення DB повторний імпорт отримує нові UUID. Локальні `spoolman/settings.py` і `spoolman/database/models.py` у перевіреному стандартному реєстрі не мають явного installation UUID; спільні integer IDs або snapshot hash не доводять, що це та сама інсталяція.

Вирішено не міняти основу ID на хеш файлу/числові spool IDs. Потрібні persisted UFM source registry з immutable instance ID, explicit choose existing/new при неоднозначності, strict conflict gate і alias для старих path-hash source IDs. Документовано в ADR-001; E04.02 став Partial. CSV 118 rows: Partial 34 / Done 29 / Planned 54 / In Progress 1; BOM preserved. Бази Spoolman/UFM не відкривали. Наступне: дизайн schema/registry migration і replay semantics, потім підключення selector до UI та CLI.

## E04.02 registry design checkpoint — 2026-10-29

ADR-001 тепер визначає concrete implementation boundary: stable UFM-owned source token; source registry keyed to device identity; no raw source path; legacy token backfill from `audit_event.correlation_id` (`spoolman:{token}:spool:{id}:create`) and actor device, preserving deterministic IDs; snapshot hash only helps candidate selection; explicit source choice and conflict gate on moved/ambiguous sources. New import IDs use the persisted token; no stock ledger mutation is part of identity resolution. Checklist E04.02 remains Partial until code, migration, backfill and UI/CLI selector exist. No application source or databases changed in this design stage.

Next: add schema/Alembic migration and exact verifier entry, then a repository/service to list/resolve sources with strict no-guess fallback; provide CLI and UI selector. No tests run/add per user instruction; use static checks only unless asked.



## E04.02 checkpoint: registry migration і явний вибір source — 2026-10-29

Додано `spoolman_import_source` та Alembic revision `0005_spoolman_source_registry`. Міграція відновлює лише legacy keys із `audit_event.correlation_id` шаблону `spoolman:{token}:spool:{id}:create`, перевіряє формат token і наявність device identity; source key однаковий зі старим path-hash, тому формули UUID котушок/профілів/пристрою не змінені. У реєстрі немає raw path; `snapshot_sha256` зберігається лише як інформація про останній імпорт. Preview може прочитати і мігрований реєстр, і legacy audit events до міграції.

`import_spoolman_database()` приймає зареєстрований/новий 24- або 32-символьний lowercase-hex source key, відхиляє mismatch source/device, створює реєстрацію до імпорту, а last-seen/fingerprint оновлює лише після успішного проходу всіх записів. Старий optional path-derived default залишено для сумісності викликів; Studio і desktop тепер вимагають явного вибору існуючого або нового джерела. CLI `--spoolman-db-preview` виводить всі source keys, а `--spoolman-db-import --spoolman-source-id ID|new` приймає рішення користувача й повертає ключ для наступних запусків.

Перевірки: `uv run ruff check` по schema/migration/importer/CLI/Studio/desktop — clean; `uv run mypy` по importer/CLI/Studio/desktop — success; ізольований in-memory migration chain пройшов exact schema verifier, SQLite integrity і FK перевірки; локалізаційні/migration JSON valid. Тести та UI acceptance не запускалися за інструкцією. Реальні БД не відкривались, жодна збірка не створювалась. CSV E04.02 лишається `Частково виконано`: потрібна перевірка moved-file replay і legacy backfill на контрольній копії. Наступне: рев’ю E04.02/E04.03 щодо збереження старих ID і точного імпортного ledger без нових записів при повторі; оновлений прогрес у `docs/PROJECT_PROGRESS_UK.md`.


## E04.03 checkpoint: збереження UUID та stock replay — 2026-10-29

Read-only звірено `src/ufm/integrations/spoolman/importer.py` та `InventoryCommands`: device/profile/brand/spool IDs детерміновано утворюються з вибраного source token і зовнішнього ключа. При імпорті перенесеної legacy бази вибір backfilled path-hash token повторює попередні UUID, не перепризначає котушки й посилання. `create_spool` використовує незмінний `spoolman:{token}:spool:{id}:create`; opening stock — окремий `...:opening`. Повторне створення перевіряє той самий request fingerprint/history, не додаючи ще один opening transaction; інший payload відхиляється як conflict. Ці операції виконуються через InventoryCommands, не прямим SQL обліку.

E04.03 у CSV переведено в `Частково виконано`: source/device mapping є, але нема окремого експорту per-entity UFM ID mapping або alias для випадку зміни зовнішнього ID, і acceptance на копії не проводився. Тести не запускалися. Наступний крок — оцінити, чи потрібна persisted external-entity mapping таблиця для Spoolman і наступних імпортерів, не дублюючи стабільні deterministic ID; потім записати приймальну процедуру moved-file/replay на відновлюваному backup.


## E04.03 checkpoint: versioned ID mapping report — 2026-10-29

`SpoolmanImportResult` повертає mapping-report шлях. Після успішного завершення всіх котушок `_write_mapping_report()` записує versioned `ufm-spoolman-id-map-v1` JSON під окремим timestamped каталогом у `data/backups`; файл створюється тимчасово й перейменовується атомарно. Manifest містить source instance key, source fingerprint, timestamp і deduplicated mappings `vendor|filament|spool`: зовнішній ID → детермінований UFM UUID, плюс SHA-256 canonical payload. Не зберігає raw path, spool/filament names чи довільний location text. При partial import report не створюється; registry fingerprint оновлюється тільки після завершення рядків. Studio/desktop відображають report path, CLI import JSON повертає його.

Статичні перевірки: Ruff clean для importer/CLI/Studio/desktop, mypy success у тих самих чотирьох файлах, локалізації JSON valid. Тести не запускалися. E04.03 лишається `Частково виконано`: потрібні acceptance на контрольній копії й явне рішення для alias при зміні зовнішніх ключів. CSV BOM збережений, 118 рядків; Partial 35, Done 29, Planned 53, In Progress 1. Наступне: E04.04 — read-only зіставити налаштування принтерів/слотів у локальному HaspelSync з UFM provider config і визначити переносимі non-secret fields; секрети не копіювати/не виводити.


## E04.04 checkpoint: межа перенесення printer config і slot mappings — 2026-10-29

Read-only зіставлено source code (не runtime files) HaspelSync і UFM. Haspel `printers.js` зберігає лише `id/code/ip/name`; printer ID формується із serial, code є секретом. UFM `printer` має display/manufacturer/model/serial/capabilities; `connection_profile` зберігає provider, mode, host/port/TLS, OS credential reference та provider config. LAN code/hashed API keys/password hash/certificate trust не переносити. Нове з’єднання проходить UFM configuration flow з повторним введенням code і TLS certificate validation.

`mappings.js` key: printer serial + visible slot label; value: Spoolman numeric spool ID, fingerprint (profile/color/tray identity), updated time та optional auto-origin. `convertAMSandSlot()` дає A1 для unit 0, tray 0; UFM Bambu source кодує це як `ams:0` + `0:0`. Haspel AMS HT `HT-A` відповідає unit 128/slot 0 (`ams:128`, `128:0`); external slot відповідає `external`/`external`. Runtime slot fallback і hardware acceptance не перевірялися. Spool IDs треба перекладати через E04.03 mapping JSON; автоматично призначати лише після source/serial/slot identity й fingerprint звірки та свіжого observation. Haspel `printstate.json` — runtime restart recovery; не імпортувати як active UFM print без перевіреного exact run identity. Haspel settings modes/Spoolman endpoints/logging/security не переносити напряму в UFM app settings, потрібна окрема allowlist із preview і user confirmation. Робочі config/credentials не читалися.

CSV E04.04 оновлено до `Частково виконано`; статуси: Partial 36, Done 29, Planned 52, In Progress 1; 118 rows, UTF-8 BOM. Це code/docs audit, а не підтвердження підключення/інсталяції. Наступне: спроєктувати (потім реалізувати) Haspel import preview із dry-run, explicit printer/source mapping, unknown/conflict totals, redaction і секретами поза файлом звіту; зберегти activation лише окремою командою.


## E04.04 checkpoint: offline HaspelSync preview parser та CLI — 2026-10-29

Додано `src/ufm/integrations/haspelsync/config_import.py`: bounded JSON reads; перевірка `ufm-spoolman-id-map-v1` canonical SHA-256; дозвіл лише Spoolman spool mappings; Haspel mappings schema v1 та legacy flat v0; crosswalk A1–D4, HT-A–HT-H та External; redacted preview із totals для unresolved spool, unsupported slot, orphan printer і duplicate target. `printers.json` projection повертає лише serial/name, булеву ознаку приватної LAN address та потребу повторно ввести credential. Passcode/code не дістається у preview; IP і fingerprint value також не повертаються.

Додано CLI `--haspelsync-preview PRINTERS_JSON MAPPINGS_JSON ID_MAP_JSON`, локалізовану help-довідку, без network access і inventory write. Source shape звірено з `linked-stack/haspelsync/src/mappings.js` і `printers.js`; Spoolman ID map shape — з `_write_mapping_report()` в UFM importer. Parser/CLI lint: clean; mypy: success; локалізаційні JSON: valid. Тести/desktop acceptance/live slot verification не проводилися.

E04.04 лишається Partial: desktop wizard та allowlisted apply із explicit user action не реалізовані. Наступне: реалізувати redacted desktop preview для трьох вибраних файлів; не читати Haspel runtime data, не копіювати credentials, не створювати mounts без свіжої перевірки provider slot identity/fingerprint.


## E04.04 checkpoint: HaspelSync preview у desktop Studio — 2026-10-29

Додано read-only preview parser та три входи: CLI, `printers.json`, Haspel `mappings.json`, UFM Spoolman mapping report. У desktop Studio → System розміщено кнопку preview з послідовним вибором файлів. Результат показує printer names/serials, UFM spool UUID, provider system/slot crosswalk, лічильники unresolved/unsupported/orphan/duplicate та максимум 100 mappings. QMessageBox виводить PlainText; preview явно повідомляє про відсутність застосування, мережі та змін inventory. Code/IP/fingerprint values не включені в структуру результату.

Ruff clean; mypy success для parser/CLI/Studio; localization JSON valid. UI runtime не запускався. E04.04 лишається Partial. Наступна дія: read-only allowlist Haspel settings зіставити з AppSettings та UFM printer configuration, потім визначити explicit apply transaction/conflict handling; mounts застарілих Haspel mappings не робити без свіжого observation.


## E04.04 checkpoint: уточнення crosswalk і redaction — 2026-10-29

Desktop report тепер явно показує UFM provider system/slot keys для кожного з перших 100 mapping рядків та unsupported label для нерозпізнаної позиції. Parser відхиляє дублікати printer serial після нормалізації, а IP helper повертає лише boolean без проміжного повернення самого адреса. Settings source review: Haspel MODE/LEGACY_MODE/AUTO_ASSIGN_THIRD_PARTY/SET_LOCATION/Spoolman endpoints/частоти синхронізації мають інші або небезпечні side effects у UFM та не переносяться автоматично. Display name і serial можуть бути тільки hints для explicit printer match; IP — тільки discovery hint, code повторно вводиться через UFM Credential Locker. Не виявлено прямої безпечної settings one-to-one allowlist.

Ruff/mypy для parser, CLI і Studio — clean; `studio_strings.json` valid. Тести/UI runtime не запускалися. Наступний крок: відобразити policy у preview як non-importable source settings summary (лише перелік пропущених категорій без показу їх значень) або перейти до explicit destination-matching design; жодне Haspel setting не слід підхоплювати без окремого per-field confirmation.


## E04.04 checkpoint: Haspel settings allowlist review — 2026-10-29

Звірено Haspel `src/settings.js` schema з UFM `AppSettings` і printer configuration workflows. Безпечного one-to-one settings allowlist немає: `MODE`, `LEGACY_MODE`, `AUTO_ASSIGN_THIRD_PARTY`, `SET_LOCATION`, Spoolman endpoint, poll/retry та logging мають інші semantics або здатні створити competing writer/side effects. `settings.json` не є preview input. Serial/name можна використовувати лише як match/display hint; IP не зберігати без UFM discovery та serial confirmation; access code повторно вводиться через Credential Locker. Документовано в `docs/INTEGRATION_DECISION_UK.md`.

Parser уточнений: wrapped mapping без schemaVersion відповідає Haspel default schema v1; flat old shape означає v0; невідома версія відхиляється. Дублікати serial після нормалізації відхиляються. Ruff/mypy clean; тести й runtime не запускалися. Наступна дія: окремо спроєктувати явне printer display-name diff/apply та залишити slot assignment unresolved до свіжого exact provider observation і verified fingerprint compatibility.


## E04.04 checkpoint: exact printer match у preview — 2026-10-29

Studio preview зіставляє Haspel serial із serial наявних UFM printers після uppercase/trim нормалізації; показує джерельне ім’я та target UFM name або вказує додати невідомий принтер через network discovery. Дії редагування немає: жодні destination поля не змінюються. Mapping lines містять provider system/slot crosswalk і UFM spool UUID; виводиться не більше 100 рядків. Ruff/mypy clean для parser/CLI/Studio; локалізаційний JSON valid. Acceptance/UI не запускався.


## E04.04 boundary: Haspel fingerprint is not comparable to UFM provider snapshot — 2026-10-29

Code evidence: `FeedSlotSnapshot` contains slot key, occupancy, trusted `tray_uuid`, trusted `tag_uid`, assigned spool ID and mass. It has no `tray_info_idx`, `tray_type` or color; `resolve_feed_slot_spool()` matches only trusted current IDs. Thus Haspel `fingerprint` cannot validate the physical spool against current UFM observation. A Haspel file mapping may remain a display-only proposal; it cannot create active mount from file. Future manual apply requires fresh provider observation, exact slot key, explicit per-mapping confirmation, and E03.06/E03.07 single-writer authority. Decision and progress docs updated. No tests/hardware or runtime DB used. Next inspect E03.06/E03.07 contract and its missing enforcement, then design any import apply gate around it.


## E03.06 source writer re-audit — 2026-10-29

Code evidence: Haspel `mqtt.js:bookConsumption()` calls `spoolman.js:useSpoolWeight()`, which uses Spoolman `/api/v1/spool/{id}/use` and a separate PATCH for `last_used`. Haspel’s booking journal/idempotency is local to Haspel and does not coordinate with UFM SQLite. UFM CalculationWorkerTransport is a bounded one-shot but has no bundled live Node worker entrypoint, durable receipt bridge, or shared per-printer authority lock. E03.06/E03.07 remain partial; do not enable auto-debit alongside the legacy writer. This is the current gate for E04.04 import-to-mount.


## E03.06 checkpoint: protocol-compatible Haspel Node worker — 2026-10-29

Added `src/ufm/integrations/haspelsync/worker_v1.mjs` for the strict request created by `HaspelCalculator`. It validates the bounded envelope/material set, parses normalized verified 3MF metadata with linked Haspel `parseSliceInfo()`, uses Haspel range calculator for partial estimates, and returns only a `needs_mapping` ProposalMessage with zero allocations. Full estimates echo verified UFM material facts; partial amounts are centigram-rounded and cannot exceed source mass. Missing material/profile/range support rejects the worker call. No MQTT/FTPS/Spoolman/ledger write occurs in this entrypoint. The separate experimental `experiments/haspel_worker/calculate.mjs` is not protocol compatible and remains unbundled.

Static evidence: `node --check` clean; Ruff and mypy clean across parser/adapter/transport. No tests or worker runtime executed. Still partial: module layout points at linked-stack source in checkout, Node runtime and npm dependencies are not in distribution, `HaspelCalculator` has no app caller/receipt bridge, live occurrence/slot provenance incomplete, old writer shutdown/authority remains manual policy. Next: define release resource placement and strict response schema mapping, then wire only read-only preview; keep finalization disabled.


## Correction: canonical Haspel calculation worker already exists — 2026-10-29

A source search after the E03.06 review found existing `src/ufm/integrations/haspel_worker.mjs` and adapter `src/ufm/integrations/haspel_calculation.py`; no new worker implementation was needed. The temporary duplicate `src/ufm/integrations/haspelsync/worker_v1.mjs` created during this turn has been removed. Existing worker returns a protocol-shaped proposal without allocations/writes, and its path points to linked-stack source. It remains not caller-wired or distribution-bundled. Static `node --check` on the canonical worker is clean; Ruff and mypy clean for 6 relevant Python files. Prior handoff wording that a new `worker_v1.mjs` was added is superseded by this correction.


## E03.06 wheel packaging audit — 2026-10-29

`uv build --wheel --out-dir <temporary-directory>` succeeded. Inspection of the 149-entry wheel found `ufm/integrations/haspel_worker.mjs` and its Python adapter, but not the referenced `linked-stack/haspelsync/src/gcode.js`, Node runtime, or npm dependency tree. Therefore the current source worker cannot run from the wheel. The temporary wheel is outside the repository; no `dist/` was created.

Source import closure: Haspel `gcode.js` imports `basic-ftp`, `adm-zip`, local `utils.js`, and `logger.js`; logger reaches config/settings and its settings loader persists to the configured `DATA_DIR`. Worker transport supplies isolated `DATA_DIR`/`LOG_DIR` and `NODE_TEST_CONTEXT`, but startup file side effects still need exact verification before production use. Do not bundle all of HaspelSync just to satisfy one import. Next: isolate a narrow calculation-only module/dependency closure, inventory exact notices and GPL-3.0-only distribution obligations, then package source/runtime and verify no checkout-relative imports. No tests/runtime were run. E03.06 remains Partial and automatic debit disabled pending the receipt/authority/cutover gates.


## Correction: worker import side effects and locked dependency closure — 2026-10-29

The prior wheel-audit checkpoint said the Haspel settings loader persists during import. Source inspection corrected this: `settings.js:loadSettings()` reads `settings.json` and applies defaults but explicitly does not write it; writes occur only through `persist()` after an explicit settings operation. `logger.js` does replace `console.log/error` in the isolated child process, and its invoked log functions can append under the transport-provided `LOG_DIR`. `config.js` suppresses dotenv loading because the transport sets `NODE_TEST_CONTEXT`. The production caller still must prove its worker workdir/data/log paths are isolated and private.

Static import closure from `gcode.js`: eight local modules (`gcode`, `utils`, `logger`, `config`, `settings`, `passwords`, `public/shared`, `public/materials`) and external `basic-ftp` 6.2.2 (MIT), `adm-zip` 0.6.1 (MIT), and `dotenv` 18.0.5 (BSD-2-Clause), pinned by the preserved package lock. The Haspel runtime's full dependency set is broader. `THIRD_PARTY_NOTICES.md` now records this narrow worker closure and wheel limitation; it explicitly is not a full SBOM or legal release approval. E03.06/E03.08 remain Partial.


## E03.08 worker reuse provenance checkpoint — 2026-10-29

Updated root `THIRD_PARTY_NOTICES.md` and E03.08 evidence with the executable Haspel source reuse and exact narrow `gcode.js` import closure. The local Haspel package lock pins `adm-zip` 0.6.1 (MIT), `basic-ftp` 6.2.2 (MIT) and `dotenv` 18.0.5 (BSD-2-Clause). These are only the reachable dependencies for this worker entry, not the full Haspel service SBOM. Corrected the notice to say that worker presence in a release EXE is not verified; only the wheel was built and inspected, and it lacks Haspel source and Node dependencies. UFM's own license, final installer contents and any distribution compliance review remain release gates; no legal conclusion is asserted.

Static side-effect correction: on worker import, settings are read but not persisted; the Haspel logger overrides console in the child process and may append when called, under transport-configured `LOG_DIR`. `NODE_TEST_CONTEXT` suppresses dotenv loading. Production caller must keep the worker workdir isolated. No test or native app runtime was run.


## E03.07 UFM single-writer guard audit — 2026-10-29

Graph navigation led to UFM calculated finalization, receipt/idempotency, ledger and Haspel booking paths; the claims were checked in source. UFM `EstimatedUsagePolicy.enabled` is false by default; preview is read-only; finalize rejects while disabled and revalidates receipt/job/policy inside the final verification before one UFM UoW commit. This is local idempotent accounting, not a cross-process writer lock. Haspel still writes Spoolman `/use` and `last_used` through its separate local booking journal. No code now proves that the Haspel writer is disabled before UFM policy is enabled. E03.07 remains Partial, and estimated debit must remain off until a per-printer cutover/rollback proof is persisted and verified. Next: define the minimal authority contract and its enforcement boundary before schema/UI implementation. Tests/runtime were not run.


## E03.07 per-printer authority contract checkpoint — 2026-10-29

Defined an implementation contract in `docs/INTEGRATION_DECISION_UK.md`: absent authority row means REVIEW_ONLY; durable per-printer modes are REVIEW_ONLY/LEGACY_ACTIVE/CUTOVER_READY/UFM_ACTIVE; mutations require an explicit revisioned/audited command; calculation finalization must check the owner both in preflight and again in the local SQLite writer transaction. Forward/rollback cutover includes snapshot reconciliation, uncertain-booking resolution, stopping/disabling the legacy writer, and operator verification. A local UFM row cannot mechanically fence a remote Haspel process, so it is not described as a distributed lock. Schema, command, and UI are still absent; keep estimated policy disabled until actual cutover and evidence. Next: implement the durable UFM guard only, default-deny, then add transition UI as a separate step. Tests/runtime were not run.


## E03.07 persisted default-deny authority gate — 2026-10-29

Implemented `PrinterAccountingMode`/`PrinterAccountingAuthority`, additive revision `0006_printer_accounting_authority`, schema/table, application persistence port, SQLite repository/UoW wiring and `CalculatedFinalizationCommands` gate. Missing authority record denies estimate finalization before calculator execution; `_verify()` rechecks `UFM_ACTIVE` within the UFM writer transaction. CUTOVER_READY/UFM_ACTIVE records require a snapshot SHA-256 and a timestamp attesting legacy-writer disablement. No transition command/UI exists yet, so no app path creates/activates a row; estimated usage remains default disabled. This is a local guard, not a remote Haspel lock. Ruff and mypy clean for affected files; tests, runtime and actual DB migrations were not run. Next: add revision-checked/audited transitions (new row defaults REVIEW_ONLY), then a Studio cutover wizard.


## E03.07 audited transition command checkpoint — 2026-10-29

Added `PrinterAccountingAuthorityCommands.transition()`: strict revision compare, deterministic request hash, idempotent audit replay, allowed transition graph and authority-row+AuditEvent in one UoW. Initial mode is REVIEW_ONLY or explicitly LEGACY_ACTIVE only; CUTOVER_READY requires snapshot SHA-256 plus reconciliation and legacy-disabled timestamps; UFM_ACTIVE is only allowed from CUTOVER_READY with exact matching evidence. Exiting UFM_ACTIVE first enters REVIEW_ONLY. Ruff/mypy passed for affected files; no tests/runtime or database migration were run. Studio does not call this service yet. Timestamp/evidence values are operator assertions, not proof a remote Haspel process stopped; the authority state remains local, not a distributed lock. Next: wire a fail-closed Studio wizard and show its reconciliation checklist/rollback flow; keep auto-debit disabled until accepted cutover.


## E03.07 Studio operator authority wizard checkpoint — 2026-10-29

Added `StudioAccountingAuthority` read model and StudioBackend methods that read state and route transitions through `PrinterAccountingAuthorityCommands`/SQLiteUnitOfWork; timestamps round-trip in strict UTC ISO format. The Printers page now has a per-printer authority wizard. It renders current state/revision and allowed transitions, confirms every transition, hashes a selected snapshot incrementally (100 MiB maximum) for CUTOVER_READY, requires separate operator attestations for legacy writer shutdown/autostart and booking reconciliation, then requires a distinct confirmation for UFM_ACTIVE using persisted evidence unchanged. REVIEW_ONLY remains initial/default when no row exists.

The UI copy explicitly states this is local state, does not stop HaspelSync, is not a distributed lock, and does not start a service or debit. This is important: checkboxes and stored timestamps are operator assertions only; reconciliation is not independently enforced by the wizard. No automatic accounting policy was toggled. The UI code does not invoke Haspel.

Static verification only: Ruff clean, mypy success for StudioBackend/StudioWindow, compileall successful for both modules, localization JSON valid. Tests/UI runtime/DB migration/hardware were not run; no database opened. An unrelated existing mypy error discovered in `create_storage_location()` (method declared `str` but omitted return) was corrected to return its newly-created ID.

Next: static review of authority migration/repository column mapping and upgrade notes; then decide whether reconciliation needs a structured evidence artifact before treating CUTOVER_READY as operationally acceptable. Keep auto-debit disabled until a real single-writer fence or explicitly reviewed manual cutover exists.


## E03.07 read-only Haspel journal cutover preflight — 2026-10-29

Graph navigation was followed by direct source verification in `linked-stack/haspelsync/src/bookings.js`, `accounting.js`, `config.js`, and `printers.js`: per-printer serial-keyed `bookings.json` stores pending/booked/uncertain/dismissed events; global `accounting.json` stores weighing pending/recorded/uncertain/rejected states. Added `src/ufm/integrations/haspelsync/cutover_preview.py`, a bounded read-only v1 parser. It validates all records, counts only matching printer bookings, conservatively counts unresolved weighing records globally (journal schema has no printer ID for weighing ownership), rejects malformed/oversized files, computes a combined evidence SHA-256, and returns no record-level/private fields.

The Studio CUTOVER_READY wizard now selects both Haspel journals, previews counts, refuses the transition if the selected printer has pending/uncertain bookings or if any weighing is pending/uncertain, requires separate human confirmation, re-parses immediately before the audited command, and rejects files changed after preview. The evidence digest is stored in the existing snapshot hash column. This preflight does not reconcile target inventory/Spoolman stock and cannot verify that remote Haspel has stopped; the operator must do those separately, and E03.07 remains Partial.

Static verification: Ruff clean; mypy success for parser, exports, backend and Studio; compileall clean for Python modules; localization JSON valid. No tests, GUI, runtime Haspel, DB, hardware or actual private Haspel data were opened.

Next: add an explicit target inventory/Spoolman snapshot reconciliation artifact to the cutover contract, and decide a technically verifiable single-writer fence or require documented manual pause. Do not enable estimated auto-debit from the local authority flag alone.


## E03.07 target Spoolman stock parity checkpoint — 2026-10-29

Extended CUTOVER_READY preflight with `preview_spoolman_cutover()` in the existing Spoolman importer. It accepts only a registered source key and a local SQLite snapshot capped at 64 MiB, uses the existing read-only integrity/schema validation, requires the current source fingerprint to equal the source registry's last imported fingerprint, and compares every source spool against its deterministic UFM ID, effective remaining mass, and archived state. It returns only counts and hashes; any mismatch or missing target spool blocks cutover. The wizard separately requires an operator confirmation that this snapshot is the exact Spoolman instance used by HaspelSync because the endpoint hash in Haspel's journal cannot identify it without reading secret-bearing configuration.

Combined authority evidence hash now covers Haspel journal digests/counts plus source key/fingerprint and UFM parity totals. The wizard repeats all three file comparisons after confirmation and before its transition command. No external source settings/credentials are read and no inventory is written.

Static checks: Ruff clean; mypy success for importer, parser, backend and Studio; localization JSON valid. Tests, GUI/runtime, actual source DB, Haspel files, and hardware were not used. No Spoolman UFM snapshot or migration was applied.

Remaining E03.07 gate: Haspel writer shutdown and auto-start state are still operator-attested, not fenced by a shared authority service. The selected source identity also remains an operator confirmation. Keep automatic debit disabled until a documented, accepted single-writer process is in place.


## E03.07 stale Spoolman snapshot guard — 2026-10-29

The preflight now computes the latest Haspel booking `updatedAt` for the chosen printer and latest weighing `createdAt` across the Haspel accounting journal. CUTOVER_READY requires the latest activity timestamp to be no later than the Spoolman source's last successful import timestamp in UFM, in addition to unchanged source fingerprint and exact spool parity. This rejects stale DB copies after Haspel activity, even if their bytes match an older import. A false clock-skew case is fail-closed. The latest activity and last-import time are part of the combined evidence SHA-256.

Ruff/mypy clean after the change; tests/runtime/database/hardware remain unrun. Remaining limitations: the operator must confirm the selected Spoolman DB belongs to Haspel's endpoint and that the Haspel writer/autostart was actually disabled. No distributed lock exists.


## E03.07 activation revalidation checkpoint — 2026-10-29

UFM_ACTIVE now repeats the three local evidence selections and parsers, requires fresh source/stock/legacy-stop confirmations, rechecks Haspel activity <= source last-import timestamp, and requires the newly computed combined evidence digest to equal the persisted CUTOVER_READY digest. The app will not activate from an old stage report after journal/Spoolman snapshot changes. This remains local operator control; it is not a distributed lock or remote service probe.

Static: Ruff/mypy clean for all five affected Python modules, compileall clean, localization JSON valid. No tests/UI/runtime/DB/hardware were run. E03.07 remains Partial.


## E03.07 audit timestamp canonicalization and wheel package check — 2026-10-29

Canonicalized authority request/audit evidence timestamps to `UtcDateTime.isoformat()` rather than dataclass `str()` so hashes and audit JSON use normalized UTC strings. Ruff/mypy clean for authority command, both cutover preview paths, Studio backend/window; compileall clean. `uv build --wheel --out-dir <TEMP>` succeeded; inspected the 154-entry wheel and confirmed `cutover_preview.py`, Spoolman importer, `studio_window.py`, and `studio_strings.json` are packaged. This only confirms Python source inclusion, not installer/native worker runtime. No tests were run.

Next: inspect HaspelSync control/supervisor APIs for remote pause or health handshakes; if none, retain explicit manual single-writer cutover as a release blocker, and continue E03.06 worker resource/dependency packaging.


## E03.07 remote control audit + E03.06 continuation — 2026-10-29

Graphify query по Haspel startup/monitoring/restart використано для навігації, результати звірено з живим кодом. У `routes.js:550-616` stop endpoints змінюють in-memory `monitoringEnabled` і закривають MQTT. `printers.js:16,97-140` показує, що цей параметр не персиститься та скидається в `true` при створенні runtime printer; `routes.js:1574-1582` разом із `entrypoint.js` виконує контрольований restart/supervision. Не знайшли durable accounting writer fence/health handshake. Внесено в E03.07 CSV як Partial та описано в `INTEGRATION_DECISION_UK.md`; auto-debit лишається disabled. CSV: 118 rows, status counts: Частково {counts['Частково виконано']}, Виконано {counts['Виконано']}, Заплановано {counts['Заплановано']}, У роботі {counts['У роботі']}; BOM збережено.

Наступне: E03.06 worker не підключений до production caller/receipt bridge. Wheel не має цілі імпорту з linked Haspel, bundled Node або npm closure. Перевірити pure calculation extraction/package-resource closure окремо від сервісного `gcode.js`; не vendoring all HaspelSync і не вмикати запис без authority fence. Не запускати тести/runtime без окремого запиту; до і після змістовного пакета перевіряти ліміти.


## E03.06 pure Haspel calculation extraction checkpoint — 2026-10-29

Перенесено без навмисної логічної зміни тіла parser/calculation функцій із `linked-stack/haspelsync/src/gcode.js` у новий `src/calculation.js`: `parseSliceInfo`, full/partial calculation, `consumptionEntry`, `roundEntries`, parser helpers. `gcode.js` імпортує `parseAttrs`/`parseLayerRanges` для решти своїх сервісних шляхів і зберігає назовні `calcFullConsumption`, `calcPartialConsumption`, `parseSliceInfo`. `haspel_worker.mjs` тепер завантажує `calculation.js`, а не сервісний `gcode.js`. Статичний import resolver підтвердив closure: worker + `calculation.js` + `public/shared.js`, 0 зовнішніх пакетів; `node --check` успішний для усіх трьох JS modules. Тести не запускалися, тому не заявляти behavioral equivalence до окремої авторизованої перевірки.

Оновлено `THIRD_PARTY_NOTICES.md`: Haspel code лишається GPL-3.0-only; wheel все ще не пакує linked source/Node runtime; closure reduced only in source. CSV 118 rows, counts: Частково 36, Виконано 29, Заплановано 52, У роботі 1; BOM verified.

Наступне: package-resource/build manifest для лише `calculation.js` + `public/shared.js`, без linked checkout path; визначити і перевірити план bundling Node 22. Не підключати production caller/receipt finalization до проходження E03.07 authority fence.


## E03.06 graph refresh after pure module move — 2026-10-29

Оновлено graphify snapshot + derived maps (`enrich_graph.py`, `project_maps.py`, `combine_enriched.py`): traceability 724 source/document files, 12,719 nodes / 43,922 edges; UFM 227 files / 5,770 nodes; Spoolman↔UFM 525 files / 10,642 nodes; enriched combined 28,616 nodes / 84,408 edges. Graph query бачить `parseSliceInfo()` у `linked-stack/haspelsync/src/calculation.js`. Граф оновлено як навігацію, його вузли/ребра не є runtime evidence. Source snapshot побудовано без зміни БД/logs/secrets.

Чекліст E03.06 залишається Partial. Наступне: визначити відтворюваний package-resource layout для двох pure Haspel modules та Node 22 distribution gate; production caller/receipt bridge не підключати до authority fence. Тести не запускалися.


## E03.06 relocatable worker-resource checkpoint — 2026-10-29

Added `scripts/sync_haspel_calculation_resources.py`, which copies exactly the pure linked Haspel calculation module, `public/shared.js`, full Haspel LICENSE, and generated provenance into `src/ufm/integrations/haspel_engine/`; the one relative import is adjusted for that resource layout. Provenance records SHA-256s. The Studio build script synchronizes resources before PyInstaller. `haspel_worker.mjs` imports `./haspel_engine/calculation.js`. `node --check` passed canonical Haspel source and package resources/worker. `uv build --wheel` to a temporary directory succeeded; static ZIP inspection found all five expected resources/worker/license/provenance in 158 members, with no linked-stack paths, DBs or logs. This is not a test/runtime validation.

Updated `THIRD_PARTY_NOTICES.md`; Haspel GPL-3.0-only license now accompanies packaged resources. UFM own license, release compatibility review, Node runtime, production caller/receipt bridge and shared authority fence remain unresolved. E03.06 is still Partial; do not enable automatic finalization. CSV 118 rows, statuses Partial 36, Done 29, Planned 52, In progress 1, BOM preserved.

Next: package a verified Node runtime and its notices into standalone build, then revisit worker caller/receipt only after E03.07 single-writer fence. No tests/runtime run.


## E03.06 verified Node and native bundle checkpoint — 2026-10-29

Added `scripts/prepare_node_runtime.ps1` for official Node.js v24.22.1 Windows x64. It verifies the official archive SHA-256 and the executable SHA-256 before staging only `node.exe` and `LICENSE`; the official archive/executable digests are recorded in the script. `scripts/ufm_studio.spec` checks the exact runtime version and bundles Node under `runtime/` plus its license under `third-party/node`. `scripts/build_studio.ps1` runs runtime preparation before Haspel resource sync and PyInstaller.

Native folder build succeeded with PyInstaller 6.22.3 into `%TEMP%\ufm-studio-build-cecadef553a74f25a20cd2eb3d77c983\UFM Studio`. Static bundle inspection found `UFM Studio.exe`, `_internal/runtime/node.exe` (SHA-256 `d702daa815eabbff763c7d3808e235cf031cf2ca70211b56847bc72f51e240e5`, matching the official Windows x64 executable digest), `_internal/third-party/node/LICENSE` (160555 bytes), worker, calculation/shared resources, Haspel license, and provenance. The packaged worker references `./haspel_engine/calculation.js`. Python wheel packaging was separately inspected and includes worker/resources but intentionally excludes Node.

Evidence is limited to build success and static file/hash/manifest inspection. No EXE, GUI, Node worker, tests, real database, or printer hardware were run. The bundle is a temporary build artifact, not an installed or release build. E03.06 remains Partial because caller/receipt integration, packaged runtime isolation validation, and license/distribution review remain. E03.07 remains Partial: no durable cross-process single-writer fence is available, so keep automatic debit disabled.

Updated E03.06 checklist evidence; 118 rows remain: Partial 36 / Done 29 / Planned 52 / In Progress 1; UTF-8 BOM preserved. Next: design/record an acceptable single-writer fence or explicit operator cutover protocol for E03.07; do not launch the legacy writer or change inventory as part of that design step. After authority gate is resolved, resume the isolated worker caller/receipt bridge. No tests/runtime were run.

## Graphify refresh after native-bundle checkpoint — 2026-10-29

Used the existing Bambu/UFM/HaspelSync/Spoolman graph maps for navigation, verified source paths before changes, then refreshed traceability, project maps, and combined enriched graph after the runtime packaging/build scripts and evidence updates. Current counts: traceability 727 source files / 12757 nodes / 44039 edges; UFM 230 / 5809 / 21450; Spoolman↔UFM 528 / 10681 / 37003; enriched 28654 nodes / 84525 edges. Updated `D:/graphify-out/bambu-ufm/PROJECT_MAPS_UK.md` and current counts in `ENRICHMENT_UK.md`. These are navigation artifacts, not runtime or feature proof. Source refresh did not include databases, secrets, or logs.

## E03.07 Haspel working-tree re-audit and fence contract — 2026-10-29

The existing Graphify maps were queried first (`bookConsumption`, `PrinterAccountingAuthority`, `printers`, `PERSISTED_FIELDS`) and the graph locations were verified against live source. `git -c safe.directory=... status --short` showed user-owned, uncommitted linked HaspelSync changes, including `src/accounting.js`, `src/bookings.js`, new booking/weighing routes, and related source/test files. They were preserved. Static reading confirms the new `bookings.js` journal persists pending/booked/uncertain states and `spoolman.js` disables retries for the additive `/use` call; this helps per-service idempotency/recovery but does not establish a cross-process owner or a durable per-printer writer fence. The Haspel stop flag is still not persisted by `printers.js` and `bookConsumption()` has no owner gate.

Recorded a candidate transfer protocol in `docs/INTEGRATION_DECISION_UK.md`: authenticated capability/revision status; Haspel-side durable owner with every write gated before intent; ownership transfer serialized with pending/in-flight bookings; UFM activates only after exact revision ack; fail-closed ordering and reverse rollback. This is a design contract, not implemented or runtime-accepted. E03.07 stays Partial and automatic debit stays disabled. No linked Haspel source files were edited, no tests/runtime/database/hardware were used. CSV E03.07 evidence updated with these findings and UTF-8 BOM preserved.

Next: stage the Haspel capability/owner boundary and UFM live revision adapter without changing current journal behavior; do not mark the checklist complete or enable debit until cross-process race/restart/recovery behavior is validated. The linked Haspel tree has pre-existing user changes and must be reviewed again before any edits.

## E03.06 native bundle static verification — 2026-10-29

Static recheck of the temporary PyInstaller folder bundle confirmed exact SHA-256 matches for Node.js v24.22.1 executable, packaged Haspel calculation.js, shared.js, and Haspel LICENSE. The bundled Node executable passed `--check` for the Haspel worker and calculation module; Ruff passed for the resource sync script and Python worker adapter; PowerShell AST parsing passed for `prepare_node_runtime.ps1` and `build_studio.ps1`. File scan found no database, SQLite, log, or `linked-stack` files in the bundle. These checks do not launch the UFM EXE, GUI, or worker. No product tests ran. CSV E03.06 evidence updated; row count 118 and UTF-8 BOM retained.

## Pause checkpoint — 2026-10-30

After the native-bundle static verification and documentation updates, the Codex `get_usage_limits` recheck timed out after 3600 seconds. Last successful reading before that verification was 73% five-hour remaining / 41% weekly remaining (used 27% / 59%); those values are not treated as current. Per the project rule, no further development started. Resume at the next scheduled run by checking both primary limits; continue only if both readings are available and above 15% remaining. Current code/doc checkpoint is E03.07 candidate single-writer fence; Haspel uncommitted work remains untouched, and automatic debit remains disabled.

## E03.07 per-service Haspel writer authority checkpoint — 2026-10-30

Extended the preserved, uncommitted HaspelSync changes in `src/bookings.js`, `src/routes.js`, and `src/openapi.js`. Booking journal schema v1 accepts an optional per-printer `owners` map; legacy journals without it remain `LEGACY_ACTIVE` revision 0. New automatic `/use` booking intents are refused unless the service owner is legacy. Added GET/POST `/api/print/{printerId}/accounting-authority`, with revision-checked, request-ID-idempotent transitions; active requests block transfer, pending/uncertain bookings block transfer into an active owner, and REVIEW_ONLY can fail closed. The OpenAPI contract documents this route and warns that it reports only this Haspel instance.

Static Node `--check` passed for bookings/routes/OpenAPI/MQTT modules; `git diff --check` passed. No tests, service runtime, actual booking files, DB, or printer were used. This is only a per-service persistent guard: separate/old Haspel instances, separate DATA_DIRs, and cross-process atomicity remain unresolved; UFM does not yet read or verify the Haspel owner revision. E03.07 stays Partial; auto-debit remains disabled. Linked Haspel user changes remain preserved.

Next: implement the UFM read/transfer adapter and bind its revision-checked activation to the selected authenticated Haspel service; refuse activation when capability/version, revision, or health cannot be proven. Do not claim a global fence until competing instances are accounted for.

## Resume and E03.07 Haspel authority capability checkpoint — 2026-10-30

At the beginning of this scheduled run both limits were available: 100% five-hour remaining / 41% weekly remaining. Resumed after the prior usage tool timeout. Graphify query first navigated `PrinterAccountingAuthority`, `bookConsumption`, `printers`, and `PERSISTED_FIELDS`; source behavior was checked live.

Extended the preserved uncommitted linked HaspelSync working tree in `src/bookings.js`, `src/routes.js`, and `src/openapi.js` without replacing its prior booking/accounting changes. The booking journal accepts an optional per-printer `owners` map (legacy v1 journals default to LEGACY_ACTIVE revision 0); new print booking intents are rejected unless the current Haspel service owner is LEGACY_ACTIVE. Added GET/POST `/api/print/{printerId}/accounting-authority`; transitions require expected revision and UUID request ID, serialize synchronously with booking intent writes in this process, refuse while active requests exist, and refuse an active owner transfer while pending/uncertain booking records remain. REVIEW_ONLY can freeze future bookings. OpenAPI documents capability v1 and its service-local scope.

Static validation only: official bundled Node `--check` passed for `bookings.js`, `routes.js`, `openapi.js`, and `mqtt.js`; `git diff --check` clean. No tests, runtime server, actual Haspel data, Spoolman DB, or hardware were used. This is not a global fence: another Haspel process, old binary, or different DATA_DIR is not detected; state cache is per process. UFM has not yet called the API or tied its own activation to the returned revision. CSV E03.07 remains Partial and auto-debit remains off.

Refreshed graph after source changes: traceability 727 files / 12761 nodes / 44057 edges; UFM 230 / 5809 / 21450; Spoolman↔UFM 528 / 10681 / 37003; enriched 28658 / 84543. Updated `PROJECT_MAPS_UK.md`, `ENRICHMENT_UK.md`, and progress counts. Graph is navigation only.

Next: inspect existing UFM Haspel/authority configuration and implement a credential-safe client for the explicit selected Haspel endpoint; have the wizard read current capability/revision and require a successful transfer acknowledgement before UFM_ACTIVE, then revalidate before any estimated finalization. If settings/secret storage or capability is missing, refuse activation. Separately design how to detect/block other Haspel instances and DATA_DIRs. Do not claim complete fencing or enable auto-debit until restart, race, and uncertainty recovery are validated.


## E03.07 UFM authority transport primitive — 2026-10-30

Checked usage at resume: 98% primary five-hour remaining / 40% weekly remaining. Refreshed `AGENTS.md`, progress/checklist/step plan and the latest handoff; read Graphify lessons (no preferred/dead-end/correction entries), queried the enriched Bambu/UFM/Haspel/Spoolman graph for accounting authority, endpoints, credential refs and revision transitions, then checked source paths against live code.

Added and exported `HaspelAuthorityClient` and its typed/sanitized result/errors in `src/ufm/integrations/haspelsync/authority_client.py`. It implements the existing capability-v1 GET/POST route shape with bounded JSON, strict response validation, revision checking on transfer, no retries, proxy bypass, redirect rejection, encoded printer ID, and `SecretValue` API-key header use. Endpoint policy accepts verified HTTPS only for local/private DNS/IP targets, and plaintext HTTP only to loopback; it deliberately does not transmit a full-access API key over remote HTTP. The linked Haspel key is full service access, not a read-only scoped key.

Static checks: `uv run --frozen ruff check ...` passed; `uv run --frozen mypy src/ufm/integrations/haspelsync/authority_client.py` passed; `ruff format --check` passed after formatting. No tests, HTTP calls, runtime Haspel process, Haspel files, DB, or printer were used. Updated decision/progress and E03.07 checklist evidence; checklist remains 118 rows, status Partial, UTF-8 BOM preserved.

Limitations: no UFM endpoint/key/printer-id persistence, no wizard integration, no saved remote revision, and no finalizer live revalidation yet. This client observes/changes only the selected Haspel instance. It cannot detect another process/old binary/DATA_DIR or close a distributed race. Do not activate UFM estimated accounting or enable automatic debit. Next: design/add dedicated authority connection persistence with OS-backed credential ref and endpoint identity (never reuse the Bambu printer connection credential slot); integrate remote capability read/transfer in the wizard with fail-closed state/revision checks and rollback path; then assess per-finalization revalidation and cross-process fence. Recheck usage before that next stage.


## E03.07 UFM authority connection persistence — 2026-10-30

The selected Graphify UFM/Spoolman/Haspel map was used to locate the existing connection-profile/OS-secret/migration pattern; the matching schema, configuration flow, keyring, UoW and authority sources were verified live.

Added revision `0007_haspel_authority_connection`: a dedicated table holds per-UFM-printer endpoint origin, Haspel printer id, OS `credential_ref`, latest observed capability/owner/revision/counts/time, and local optimistic revision. `StudioBackend` now exposes config read, config-and-verify, remote authority read, and revision-checked transfer methods. Config-and-verify issues the Haspel GET before persisting; it stores the supplied API key using `SecretStore`, then commits endpoint/reference/observation, and only afterwards attempts deletion of the replaced key. Read/transfer retrieves the OS secret and refreshes the cached snapshot under a revision compare. Bambu `connection_profile` credentials remain independent.

The cached remote owner/revision is never sufficient authorization; it is just the latest successful observation. `HaspelAuthorityClient` enforces HTTPS for remote private/local targets, loopback-only HTTP, no redirects/proxy, bounded parsing, and sanitized conflict/unavailable errors. Haspel API keys remain full-access credentials. No UFM UI invocation, network request, migration, runtime, tests, database or printer was used. Ruff and mypy passed for the changed application/backend/schema/client/migration-manager Python paths; 0007 JSON statically parsed as two SQL statements. `ruff format --check` over the large legacy schema/backend files reports pre-existing whole-file formatting drift; no bulk reformat was applied.

Remaining E03.07: connect the endpoint/key form to the existing authority wizard; use live status in preview, transfer Haspel owner before local UFM_ACTIVE, and make rollback disable local UFM before trying to put Haspel in REVIEW_ONLY; persist/compare the remote revision as needed; inject a live check into the estimated finalizer if that flow is ever enabled. The current linked Haspel owner is per process/DATA_DIR and cannot rule out an older/parallel instance; it is not a cross-process fence. Keep auto-debit disabled. No tests were run.

### Graphify after authority-client and persistence changes — 2026-10-30

Refreshed traceability and all derived maps after adding the UFM Haspel API client, connection table/migration and backend operations. Current traceability: 729 source/document files, 12830 nodes / 44308 edges; UFM map: 232 files, 5875 nodes / 21702 edges; Spoolman↔UFM: 530 files, 10747 nodes / 37256 edges; enriched graph: 28727 nodes / 84794 edges. `PROJECT_MAPS_UK.md` and `ENRICHMENT_UK.md` summary counts were updated. Graph is navigation only and contains no DB/secrets/log evidence.


## E03.07 UFM Studio read-only Haspel capability UI — 2026-10-30

The accounting-authority wizard now loads the saved Haspel connection row and shows endpoint origin, Haspel printer ID, a password-mode API-key field, an explicit “verify connection and read status” action, and a bounded status summary. Existing connection loads never reveal the API key. A newly entered key is wrapped as `SecretValue`, the widget is cleared before background work, and the backend performs the capability GET before storing the key in the OS `SecretStore` and committing the endpoint config. Blank-key verification can only reuse a stored credential for the exact saved endpoint and Haspel printer ID. Only the selected service's owner/revision/pending/uncertain/active counts are displayed. No transfer or debit is invoked by this UI action.

Static checks: Ruff passed and mypy passed for the five changed Python paths; `studio_strings.json` parsed as JSON. No tests, UI/runtime, HTTP request, DB migration, database, or printer were run. The API key is full-access and remains only in the OS secret store. This does not prove a global writer fence: another Haspel process, old binary, or different DATA_DIR can still exist. The wizard's local UFM mode transitions are not yet tied to a revision-checked remote transfer/compensation sequence or finalizer live revalidation. E03.07 remains Partial; automatic debit remains disabled.

CSV: 118 rows, UTF-8 BOM retained; 29 Done / 36 Partial / 52 Planned / 1 In progress.

Next: refresh derived Graphify maps, then work on a fail-closed cutover/rollback sequence and independently assess the missing cross-process fence before any debit integration.


## E03.07 revision-checked Haspel→UFM authority transition — 2026-10-30

The Studio wizard now disables acceptance of `UFM_ACTIVE` until the user has performed a fresh read of the selected Haspel capability and that response reports `LEGACY_ACTIVE` with zero pending, uncertain, and active records. Endpoint/printer edits invalidate that live observation. On confirmation, the backend re-reads the selected service, checks the expected remote revision and owner, transfers via compare-and-set to `UFM_ACTIVE`, validates the returned owner/revision/counts, then persists local UFM authority. If local persistence fails, it checks whether the local transaction nevertheless committed; if not, it best-effort transfers the same selected Haspel service/revision to `REVIEW_ONLY`. The cached observation is non-authoritative. Error UI is localized and excludes endpoint/key/response data.

Static validation: Ruff clean; mypy clean on the five changed Python modules; localization JSON parses. No tests, UI/runtime, HTTP, migration, DB, or hardware checks were run. This transition is not a global fence: old/parallel Haspel processes, another DATA_DIR, and another UFM database are not detected. A failed compensation can leave a remotely uncertain state; operator must perform a fresh check. `UFM_ACTIVE` does not enable `EstimatedUsagePolicy`; automatic estimated debit remains disabled. E03.07 remains Partial.

CSV E03.07 appended evidence; 118 rows and UTF-8 BOM preserved; counts unchanged at 29 Done / 36 Partial / 52 Planned / 1 In progress.

Next: refresh Graphify from the final UI/backend edits, update its derived map counts, then design a provable cross-process single-writer fence and pre-finalization live revalidation.


### Graphify refresh after E03.07 transfer binding — 2026-10-30

Rebuilt traceability, UFM/Spoolman/link maps and enriched graph after the Studio wizard/backend transition edits. Current counts: traceability 729 files / 12846 nodes / 44396 edges; UFM 232 / 5891 / 21790; Spoolman 298 / 4920 / 15554; Spoolman↔UFM 530 / 10763 / 37344; enriched 28743 / 84882. Updated `PROJECT_MAPS_UK.md` and the current summary in `ENRICHMENT_UK.md`. These are extraction/navigation counts, not runtime evidence.

Latest static checks after Python changes: `ruff check` passed, mypy passed for 5 changed Python modules, and localization JSON parsed. No tests or application/runtime/network/database/hardware operations were run. At the last usage check: 92% five-hour and 40% weekly remaining.


## E03.07 аудит legacy AMS writer — 2026-10-30

Graphify допоміг знайти `linked-stack/haspelsync/src/mqtt.js:processSlot()`; поведінку перевірено в source. Legacy mode PATCH-ить Spoolman `remaining_weight`/`last_used` напряму з AMS remain через `patchSpoolWeight()`. Цей шлях не проходить через `beginBooking()` та не реєструє in-flight writer у `activeBookingIds`. Водночас `transferAccountingAuthority()` перевіряє активність лише через цю множину, отже поточна transfer-guard не може довести, що legacy PATCH завершився. `routes.js` відхиляє `/api/accounting/weigh/:id` у legacy mode, але це не зачіпає MQTT AMS writer. Інша процесна копія/старий Haspel/DATA_DIR і далі залишаються поза межами capability endpoint.

Змін коду не робив: проста перевірка owner перед PATCH лишила б race між перевіркою, HTTP запитом і transfer; тестів не запускав за інструкцією. Потрібен спільний per-printer writer gate/in-flight registration, яким користуються і AMS PATCH, і transfer, із fail-closed станом при невизначеному результаті та recovery після рестарту. Окремо інвентаризувати всі Spoolman remaining-weight writers і визначити, як інші процеси/версії отримують той самий fencing epoch або як cutover операційно їх виключає. E03.07 залишається Partial; automatic debit вимкнений. Checklist E03.07 evidence оновлено, статуси/кількість кроків не змінені, BOM CSV збережено.


## E03.07 writer inventory — 2026-10-30

Source review of linked HaspelSync classifies its relevant Spoolman writes:

- `mqtt.js:processSlot()` → `spoolman.js:patchSpoolWeight()` changes `remaining_weight`/`last_used` from legacy AMS RFID remain. This writer has no durable intent or active-writer marker and is the identified transfer race.
- `mqtt.js` print completion → `spoolman.js:useSpoolWeight()` uses `/spool/{id}/use`, journals pending/booked/uncertain state, and tracks the in-flight booking. It is refused when the per-printer owner is not `LEGACY_ACTIVE`.
- `/api/accounting/weigh/:id` → `applyWeighing()` has its own weighing journal/active ID and is rejected while booted in legacy mode; route-level checks block known active/uncertain prints.
- `/api/spoolman/spool/:id` can set a manual remaining-weight field, but rejects all edits in legacy mode and blocks known active printing for a weight edit. Other profile/archive mutations are not consumption accounting, though their owner policy should be explicitly decided.
- Merge/create/tag/location routes mutate metadata or records; they are not mass-debit paths.

This inventory is static; it does not prove runtime route exposure or exclude external Spoolman clients. A correct cutover design must register both legacy AMS patches and G-code use calls in one per-printer in-flight fence. Entering REVIEW_ONLY/UFM_ACTIVE must atomically stop new legacy writes and drain or surface all in-flight/uncertain ones before acknowledging transfer. If an HTTP PATCH response is lost, recovery must not assume either outcome; require reconciliation and fail closed. The fence must be effective for every Haspel process sharing the same Spoolman instance, or the operator workflow must prove those writers are stopped and unable to restart.


## Критерії writer fence перед наступною реалізацією — 2026-10-30

Не вважати самим fence ні локальний `owner` у Haspel JSON, ні останню remote перевірку UFM. Перш ніж вмикати списання, обраний протокол має забезпечити:

1. Один авторитетний per-printer стан і монотонний fencing revision, доступний усім Haspel процесам, які можуть писати в той самий Spoolman. Якщо не можна довести спільність store/gateway, розгортання блокується і потребує операторського вимкнення/мережевої ізоляції решти writer-ів.
2. Усі операції, що змінюють кількість/залишок, проходять однаковий gate. До переліку належать legacy AMS `remaining_weight` PATCH, G-code `/use`, ручне зважування та будь-які прямі поля залишку. Облік `active` охоплює увесь інтервал від прийняття запиту до збереження результату.
3. Transfer спершу припиняє прийом нових старих writer операцій, потім відхиляє або дочікується active операцій, а також блокує cutover на pending/uncertain записах. Не можна підтверджувати UFM owner, доки старий writer може зробити PATCH.
4. UFM бере revision-bound finalization lease до локальної транзакції; Haspel не дозволяє зміну owner/повернення legacy writer, доки lease відкритий. Звичайний GET перед SQLite commit не закриває race.
5. У кожної зміни є idempotency key і persisted intent/result. Втрата відповіді на мережеву мутацію переводить джерело у review-required; автоповтор або автоматичне зняття простроченого lock заборонені, поки результат не з’ясовано. Після crash/restart потрібен явний recovery/reconciliation.
6. Приймання має відтворювано показати race двох процесів, transfer під час активного legacy PATCH, зупинку між intent і HTTP, втрату відповіді, restart при pending/uncertain та відновлення owner. До перевірки цих сценаріїв estimated auto-debit лишається вимкненим.

Це вимога до майбутньої реалізації, а не доказ, що поточний код її виконує. Наступний крок — перевірити, чи можна забезпечити shared gateway/store для реального способу інсталяції без Docker; якщо ні, зафіксувати операційне fencing обмеження як обов’язкове приймання для релізу.


## Уточнення застарілого E03.06 опису — 2026-10-30

У давнішому розділі `PROJECT_PROGRESS_UK.md` було сказано, що calculation-only resource closure і bundled Node відсутні. Це застаріло: поточний E03.06 handoff/CSV підтверджує canonical worker resources та статичний PyInstaller folder bundle з Node v24.22.1 і перевіреними хешами. Ще відсутні саме production receipt/finalization bridge, runtime acceptance та shared writer authority; отже E03.06 і E03.07 лишаються Partial, auto-debit вимкнено.


## E03.06/E03.07 межа standalone packaging — 2026-10-30

Перевірив `src/ufm/integrations/calculation_worker.py`, Haspel worker resource та packaging scripts. Bundled `node.exe` запускає тільки bounded one-shot calculation worker; його середовище явно спрямовує `DATA_DIR` і `LOG_DIR` у виділений workdir. У PyInstaller збірку не входять Haspel `entrypoint.js`/`starting.js`/Express service як керований runtime. Отже ця збірка не є окремим повним Haspel сервером і не замінює/не вимикає встановлену HaspelSync. Інтеграція Haspel authority потребує окремого reachable authenticated API.

Для продуктної вимоги «одна програма без Docker» ще треба прийняти один з варіантів: портувати повну сервісну роль HaspelSync у керований local subprocess з окремим persisted data root та контрольованим життєвим циклом; або формально залишити сервіс як зовнішню залежність, що не відповідає повній автономності. Перед портом потрібні точний dependency/license review, сумісність Haspel/Spoolman API, захищений перенос конфігурації/секретів і restore/race acceptance. Наявний розрахунковий worker не треба розширювати до сервера без окремого scope та архітектури. E03.06/E03.07 лишаються Partial, автооблік вимкнений. CSV evidence уточнено; статуси не змінювалися.


## Узгоджений напрям цільової архітектури standalone UFM — 2026-10-30

Вихідна продуктова вимога: одна Windows-програма UFM Studio з локальною базою, без браузера й Docker. Тому окрема повна HaspelSync server із MQTT, Express API, web UI і власними JSON станами не повинна непомітно стати постійною залежністю релізу. Цільовий шлях — переносити потрібні функції керування принтером/AMS і обліку в адаптери та application commands UFM із її єдиним inventory ledger. Haspel API клієнт і read-only snapshot preflight потрібні як контрольований міст міграції та cutover зі старої інсталяції. Calculation-only Node worker залишається вузьким чистим адаптером алгоритму, а не повним сервісом.

До реалізації ще потрібна функціональна матриця Haspel↔UFM: MQTT discovery/connection, AMS identity/slot mapping, RFID remain legacy behavior, G-code/3MF calculation, partial print/refill handling, retries/offline lifecycle, archive/matching, API/UI actions, journals/recovery. Для кожного пункту визначити: вже покрито native UFM, потребує порту, можна замінити іншим adapter/provider або виключити з першого релізу. Не рахувати скопійований `linked-stack` сервіс як готову вбудовану функцію. До завершення feature parity, legacy writer fence і перенесення даних automatic debit лишається вимкненим. Ця ціль випливає з підтвердженої вимоги користувача про окрему програму без Docker; це ще не доказ повного функціонального паритету.


## Уточнення цільової інтеграції standalone UFM — 2026-10-30

Щоб уникнути двозначності попереднього переліку варіантів: робоча ціль, узгоджена з вимогою користувача «окрема програма без браузера та Docker», — native UFM desktop зі своїми provider/application modules та одним локальним ledger. Не планувати повний HaspelSync Express server як постійну приховану залежність і не зберігати Spoolman та Haspel як два активні обліки. Потрібні Haspel можливості переносити/адаптувати у відповідні UFM модулі після feature-parity аудиту; calculation-only Node worker може залишитись вузьким тимчасовим algorithm adapter. Haspel remote authority API, snapshots та імпорт є інструментами перехідного cutover, не постійним runtime prerequisite. Повноту цього порту ще не підтверджено; матриця можливостей передує реалізації.


## Feature parity audit: monitor і durable receipts — 2026-10-30

Перевірив джерела графом і звірив live source. `PrinterMonitorTask` (QThread) має exponential retry 1–30 s, періодичну 15-second health перевірку та Windows sleep/resume detector. Studio запускає його вручну для вибраного принтера й зупиняє при вимкненні моніторингу або закритті. Bambu LAN provider отримує MQTT reports і генерує зміни job observations. Але UI `show_latest_monitored_event()` викликає `take_latest_event()`, який вичищає буфер і повертає лише останню подію; `show_monitored_event()` тільки змінює текст панелі. Автоматичної подачі provider event до durable receipt ingestion не виявлено.

`ReceiptIngestion.ingest()` перевіряє обмежений protocol payload і printer scope, створює durable `PENDING` receipt у UFM UnitOfWork, повертає наявний receipt при тотожному повторі та створює reconciliation conflict при зміненому payload. Це application primitive, але воно не wired до `PrinterMonitorTask` і саме не проектує/фіналізує accounting. Feature matrix F048 та F071 виправлено з `Додати` на `Частково`; їхні докази й межі записано в `FEATURE_PARITY_MAPPING_UK.csv`. Matrix: 124; Є 28 / Частково 30 / Додати 46 / Бажано 20. Integration checklist лишається 118 рядків із незміненими статусами. Source review only: тести, UI, принтер, runtime не запускалися.

Наступна реалізація має персистувати provider events до UI coalescing; окремий consumer має відновлювати pending receipts після restart з idempotency/reconciliation, не списувати з callback. Спершу потрібні bounded durable inbox, backpressure і lifecycle у Studio; E03.07 legacy AMS PATCH writer fence лишається блокером автосписання.

## E03.07 — provider event → receipt contract audit — 2026-10-30

Graphify UFM map was used for navigation; all findings below were checked in current source. `BambuLanProvider.subscribe_events()` emits a normalized `PrinterEvent` and SHA-256 of an internally generated canonical JSON snapshot. The DTO does not preserve the report bytes. `BambuLanProvider.__init__()` creates a random `source_epoch`; `event_key` increments only within that provider instance, and the monitor factory creates a new instance for retry. These are scoped delivery identifiers, not a stable global print occurrence ID.

`ReceiptIngestion.ingest()` currently requires raw bytes plus normalized Worker Protocol v1 bytes. It hashes the raw bytes itself and accepts only `StatusMessage`, `JobMessage`, or `SlotsMessage`, checking printer ID scope. `PrinterEvent` is a different DTO, and no production `ReceiptIngestion` caller was found. `JobMessage` requires typed state and `occurrence_key`; absent/ambiguous Bambu identity cannot safely be guessed. Thus the existing event hash cannot be supplied as raw payload and a provider event cannot be passed directly to ingestion.

Contract note added to `docs/INTEGRATION_DECISION_UK.md`; E03.07 checklist evidence appended without changing status. Required next design: versioned adapter with explicit payload provenance/hash semantics and stable occurrence identity; ambiguous identity → reconciliation; durable persistence before UI latest-only coalescing; restart-safe bounded consumer → projection/reconciliation. Terminal events and UI callbacks never debit inventory. The old Haspel legacy AMS writer fence remains an independent auto-debit blocker.

Static source/docs inspection only. No tests, runtime/UI, network, DB, or printer use. Auto-debit remains disabled; E03.07 Partial.

## E03.07 — Bambu job/material identity crosswalk — 2026-10-30

Graphify Bambu and UFM maps were used for navigation; code claims were source-verified. `BambuLanProvider.get_current_job()` sets provider task/subtask/job IDs and `material_slot_mappings_from_report()`, but does not populate `provider_run_key`, `external_job_id`, `project_uuid`, `file_hash`, or exact start time. `source_epoch` is a per-provider random UUID. The decoder accepts only the current report's `print.mapping`; list index is the logical-material ID and the packed value maps to AMS/system and slot keys. The decoder explicitly keeps earlier `ams_mapping`/`ams_mapping2` from `project_file` separate.

The logical-material index shape matches `VerifiedSliceFacts`/Worker Protocol, but a spool match is not available from current reports: `feed_systems_from_report()` hard-codes `complete=False`; `job_material_mapping` requires same verified file SHA-256 and printer, a status snapshot no older than 120 seconds, one unique system/slot, a complete system and confirmed occupied slot. Thus the current provider should remain UNKNOWN for slot resolution. No model-specific full-slot guarantee or globally unique occurrence key is proven. Never infer complete=true from a missing tray, or create a new job alias from ambiguous/reused provider IDs; route these cases to review.

Decision recorded in `docs/INTEGRATION_DECISION_UK.md`; checklist E03.07 evidence appended, status unchanged. Source/docs audit only, no tests/runtime/UI/network/DB/hardware. Automatic debit remains disabled; legacy Haspel AMS writer fence still blocks cutover.

## E03.07 — snapshot completeness fixture review — 2026-10-30

Read-only review only. Existing `tests/integration/test_bambu_lan_provider.py` distinguishes job `print.mapping` from prior, unjoined `ams_mapping*`; `tests/unit/test_job_material_mapping.py` expects UNKNOWN for incomplete feed snapshots. These files were not executed. Haspel report examples include 4-slot, multi-system, and 1-slot systems without a completeness marker. They are illustrative fixtures, not Bambu firmware schema; no fixed tray-count rule may set `complete=True`.

Updated `INTEGRATION_DECISION_UK.md` and E03.07 checklist evidence; status stays Partial. Next source audit: determine whether UFM already has a production pending-receipt consumer for `ReceiptIngestion.pending()`, and whether it preserves event ordering/replay/reconciliation across restart. If absent, document bounded consumer lifecycle, backpressure and recovery before implementation. No tests/runtime/network/DB/hardware; debit remains disabled.

## E03.07 — pending receipt production lifecycle audit — 2026-10-30

Graphify located `ProjectionDrain`; current source confirms useful bounded primitives. `ReceiptIngestion.pending()` delegates to generic PENDING receipt retrieval (1..500). `JobProjectionCommands.pending()` selects only eligible `PRINT_*` receipts for enabled printers, ordered by receive timestamp and ID, excluding applied and open-conflict/quarantine items. `ProjectionDrain.run_once()` processes a bounded batch and durably quarantines rejected job observations. A source-wide search found no production constructor/call of `ReceiptIngestion` or `ProjectionDrain` under `src/ufm`; restart replay is not scheduled by Studio/container/provider lifecycle. Generic receipt ingestion accepts status/feed-slot messages, but the job projection drain does not process them, so dedicated handlers or a narrower inbox contract are required.

Documented this primitive-versus-lifecycle distinction, bounded backpressure, persist-before-UI-coalescing, startup replay, type routing, and non-finalizing behavior in `INTEGRATION_DECISION_UK.md`; appended E03.07 checklist evidence. Status remains Partial and estimated automatic debit disabled. Static source/docs review only; no tests/runtime/UI/network/DB/hardware.

## E03.07 — Qt consumer lifecycle seam audit — 2026-10-30

`StudioWindow.work()` creates a one-shot `Task(QThread)` and blocks pages while work runs; it is not a long-lived consumer. `PrinterMonitorTask` owns an asyncio provider stream, health checks and reconnect, but current Studio starts it only on explicit user action for one selected printer. The event signal drains latest-only into UI; no DB sink exists. The event queue is capped at 256, and overflow raises a non-retryable `RuntimeError` for that monitor attempt. `AppContainer` currently contains settings/paths/translator/secrets/logger; `StudioBackend` builds catalog/inventory/storage/authority commands, no receipt/drain services. Close requests monitor stop and delays window closure; the app disposes the SQLite engine after the event loop exits, so any new consumer must handshake shutdown before disposal.

Documented candidate boundary in `INTEGRATION_DECISION_UK.md`: explicit owned service lifecycle; validated adapter; durable commit before UI coalescing; projection drain only after persistence; DB failure must not be silently acknowledged; missing poll history → reconciliation; stop/join before engine disposal. Updated E03.07 checklist evidence; status remains Partial, auto-debit disabled. Source/docs only, no tests/runtime/UI/network/DB/hardware.

## E03.07 — reconnect, source gap, and shutdown audit — 2026-10-30

Source-verified Bambu delivery behavior: MQTT report subscription uses QoS 0; connect sends `pushall` for current state, not historical job events. Retry factory constructs a new provider, which generates a new random source epoch and clears its report cache. This is snapshot recovery, not missed-event replay; do not synthesize a completed event from later IDLE or job disappearance. An epoch/source gap or unresolved occurrence identity must create reconciliation and block finalization. Buffer overflow remains non-retryable.

Source-verified Studio shutdown: close asks the monitor to stop; QThread cancels its asyncio monitor, provider run closes stream and disconnects; finished callback permits window close; `run()` disposes SQLite engine/container afterward. Preserve this order for any production consumer, with an explicit shutdown acknowledgment and no success acknowledgment when persistence/backpressure fails. Updated integration decision and E03.07 checklist evidence. No code/tests/runtime/network/DB/hardware run; auto-debit disabled.

## E03.07 — process/printer ownership fence audit — 2026-10-30

`StudioWindow` permits one `_monitor_task` per window only. Static search under `src/ufm` found no OS named mutex, `QLockFile`, single-instance server, or per-printer process lease. `AppPaths.resolve(root)` can target a distinct local SQLite DB; UFM authority revision and finalization guard are persisted/read in that database, so they do not coordinate separate DB copies or PCs. A Windows per-printer mutex could fence UFM processes on one machine but cannot fence Haspel or another host. Cross-product automatic cutover needs a shared owner/fencing epoch enforced by every Haspel consumption writer around `/use`/PATCH; with old binaries/other DATA_DIRs, only operator-controlled cutover is supportable. Auto-debit remains disabled.

Updated `INTEGRATION_DECISION_UK.md`, progress and E03.07 checklist evidence. E03.07 stays Partial. Static source/docs only; no code/tests/runtime/network/DB/printer. Next: map a dependency-ordered safe implementation slice (typed provider adapter, per-printer ownership, durable inbox-before-UI, handlers/drain, source-gap reconciliation, writer fence, then manual verified-file finalization) with module paths and acceptance gates.

## E03.07 — implementation dependency map — 2026-10-30

Added a dependency-ordered slice with source anchors and acceptance gates to `INTEGRATION_DECISION_UK.md`: typed provider adapter/provenance and occurrence identity → local/shared ownership → receipt commit before UI coalescing → typed job/status/feed handlers → startup replay/backpressure/shutdown → source-gap reconciliation → all-writer Haspel fence → explicit verified-file finalization. No gate is marked complete; E03.07 remains Partial and automatic debit remains disabled. Updated checklist evidence; no code/tests/runtime/UI/network/DB/hardware.

Next safe implementation boundary is a pure typed conversion contract, isolated from production consumer/finalization. The current run forbids adding or running tests, so behavior-sensitive consumer wiring cannot be called complete without its later acceptance checks.

## E03.08 — release-notice collector source-dependency fix — 2026-10-30

`collect_studio_notices.py` previously seeded the dependency traversal only from installed UFM package metadata, which was stale in `.venv312` and omitted declared runtime/desktop requirements. It now parses source `pyproject.toml` with stdlib `tomllib`, evaluates markers for base and `desktop` requirements, and continues recursive traversal through installed distribution `Requires-Dist`. Static collection yielded 22 distributions and 22 license files; canonicalized metadata confirmed Paho MQTT, Segno, PySide6 Essentials, and shiboken6. Some metadata still omits/ambiguously identifies the license, requiring manual upstream notice review. Ruff passed. No tests/runtime/UI/network/DB/printer were used.

Corrected `THIRD_PARTY_NOTICES.md`: Haspel calculation worker/resources are part of the separate Windows folder bundle, not the Python wheel; collector inputs are now described as source requirements plus installed transitive metadata. E03.08 remains Partial: UFM license selection, ambiguous package notices, Qt/source-offer, Microsoft runtime, signing, clean-machine validation, complete SBOM and release/legal review are open. This record makes no legal compatibility or distribution approval claim. Auto-debit remains disabled.


## E03.08 — exact notice artifacts and Qt licensing-mode gap — 2026-10-30

A second static collection covered 22 distributions and copied 22 notice/license files. Among distributions whose `License` metadata is `not specified`, the copied `jaraco.classes 3.4.0` notice contains MIT terms and agrees with the PyPI release record (`https://pypi.org/project/jaraco.classes/3.4.0/`); the copied `segno 1.6.6` LICENSE contains three BSD-style redistribution conditions and matches upstream (`https://raw.githubusercontent.com/heuer/segno/master/LICENSE`). UFM's own package metadata also remains unspecified because its project license has not been selected. The collector now records exact copied notice filenames per package in `runtime-dependencies.json`, retaining the count field for existing readers.

The notable unresolved discrepancy is Qt: `uv.lock` pins PySide6/Shiboken Windows wheels hosted on PyPI, and installed metadata lists LGPL/GPL alternatives, while collected files include `LicenseRef-Qt-Commercial`. The lock resolves package-source provenance, but this file is not evidence that the application is entitled to ship under commercial terms, nor proof that LGPL/GPL obligations are satisfied. Identify the Qt modules/binaries actually included in the frozen folder bundle and verify the applicable license/source-offer path before release. The Qt for Python licensing docs distinguish Community and Commercial distributions: `https://doc.qt.io/qtforpython-6/commercial/index.html`. UFM's own license and the remaining SBOM/runtime/signing/clean-machine gates remain open. E03.08 remains Partial; no legal conclusion. No tests/runtime/UI/network/DB/printer run.

The notice collector's package entries now include sorted `notice_files` names as well as the existing `notice_files_copied` count. A bounded static re-collection produced 22 package entries and 22 notice files and confirmed the exact Paho, Segno, and Qt notice filenames. `ruff check scripts/collect_studio_notices.py` passed. This improves traceability only; it does not resolve package license selection or release approval.

## E03.08 — pinned Qt wheel provenance — 2026-10-30

`uv.lock` pins `pyside6-essentials` and `shiboken6` 6.12.0 to Windows `win_amd64` wheel URLs on `files.pythonhosted.org` with SHA-256 values. The release-notice audit can therefore record the dependency artifact source from the lock. Qt's official Qt for Python documentation distinguishes the Community LGPLv3/GPLv3 distribution from Commercial downloads. The local collection still contains `LicenseRef-Qt-Commercial` notice files alongside LGPL/GPL alternatives in metadata; do not infer that a commercial license is held or that the LGPL/GPL obligations are met. `scripts/ufm_studio.spec` requests PyInstaller's automatic PySide dependency collection; the exact copied Qt modules/binaries can only be recorded from a generated bundle manifest, which has not been built in this stage. E03.08 stays Partial, UFM license remains unselected, and release/legal approval remains open. No tests or application runtime were run.

## E16.01/E16.05 — folder candidate inventory and secret-store inclusion — 2026-10-30

Built a portable candidate using `scripts/build_studio.ps1 -DestinationParent D:\UFM_ReleaseCandidate2`; the existing `D:\UFM Studio` was left untouched. Candidate path: `D:\UFM_ReleaseCandidate2\UFM Studio`. Static inventory: 366 files before the manifest, 216,142,011 bytes, Qt6Core/Gui/Network/PrintSupport/Svg/Widgets DLLs, Node runtime plus license, Python runtime, migrations and Haspel worker/resources. No `.db`, `.sqlite`, `.log`, or `.env` files appear in the manifest. A new `scripts/write_studio_manifest.py` hashes every file (manifest excludes itself); rehash validation found zero mismatches. `build_studio.ps1` now invokes it after collecting notices.

Static archive review of the first candidate at `D:\UFM_ReleaseCandidate\UFM Studio` found no bundled `win32ctypes` modules; that superseded folder remains on disk and must not be used. Source review confirmed `OSSecretStore` selects only `keyring.backends.Windows.WinVaultKeyring` on Windows and fails closed if unavailable. Added explicit PyInstaller hidden imports in `scripts/ufm_studio.spec` for `win32ctypes.pywin32` wrappers and concrete ctypes implementation modules. Rebuilt separately; `pyi-archive_viewer -l -r -b` lists these modules in the second EXE's PYZ. Warnings about virtual `win32ctypes.core.*` alias names remain due to package MetaPathFinder redirects. This proves static contents only, not Credential Manager runtime. No tests, UI launch, database, credential read/write, printer or network use.

E16.01 and E16.05 moved to Partial: the portable folder, dependency notices and file hashes exist; installer/uninstall, signed release, clean Windows re-installation, actual runtime acceptance, full Qt/MSVC licensing review, UFM license and update safety remain open. E03.08 stays Partial. Automatic filament debit remains disabled.

## E16.02/E16.03 — per-user installer draft and data boundary — 2026-10-30

Added `scripts/ufm_studio.iss` and `scripts/build_installer.ps1`. The intended installer is per-user (`PrivilegesRequired=lowest`), defaults to `%LOCALAPPDATA%\Programs\UFM Studio`, allows the install directory to be selected, creates a Start Menu shortcut, offers an optional desktop shortcut, and has no `[UninstallDelete]` for app data. `AppPaths.resolve(None)` places user data/config/log/cache in separate platformdirs locations. The build manifest generator/verifier rejects DB/SQLite sidecars, logs, `.env` and private-key suffixes; the current candidate manifest verified 366 file hashes. PowerShell AST parsing and Ruff passed.

`ISCC.exe` is not installed on this host, so the `.iss` file is a draft only: no installer compilation or installation, upgrade, shortcut, or uninstall behavior was accepted. The installed `D:\UFM Studio`, desktop shortcut, databases and secrets remain untouched. E16.02/E16.03 are Partial; E16.04 remains Planned. Next: compile to a separate output directory when Inno Setup is available, then arrange explicit user/runtime acceptance. Do not redirect the existing shortcut to this candidate. Tests and app runtime were not run.
## E16.07 — cleanup report preservation — 2026-10-30

Graphify was used to locate the cleanup-script area; source inspection confirmed that `clean_project_caches.ps1` only targets the three named Python caches, defaults to dry-run, requires `-Apply` to delete, and checks the project marker, canonical path boundary, and reparse points. The script previously overwrote `docs/CLEANUP_REPORT.json` on every run, including dry-runs. It now writes a timestamped report when that path already exists, preserving the earlier record. PowerShell AST parsing succeeded; the cleanup script itself was not run and no caches were deleted. E16.07 is Partial because no cleanup acceptance/dry-run artifact was produced in this change.
## E16.05 — packaged dependency versions differ from lock — 2026-10-30

Compared the second folder candidate's `third-party/runtime-dependencies.json` with `uv.lock` using normalized Python package names. Eight versions differ: Mako 1.4.1/1.4.3, MarkupSafe 3.0.3/3.0.4, SQLAlchemy 2.0.52/2.1.6, Alembic 1.20.0/1.20.1, more-itertools 11.1.0/11.2.1, platformdirs 4.11.8/4.14.0, pydantic 2.13.5/2.14.1, and pydantic-core 2.46.5/2.50.1. `greenlet` 3.5.5 appears in the candidate inventory but is absent from `uv.lock`. PySide6 Essentials/shiboken6 are both 6.12.0 and Qt6 DLLs are named in the file manifest. This means the candidate has its own file hashes but cannot be reproduced from the current lock with this environment. It is not proof that the candidate fails at runtime. Existing venv, installed app, data and candidate were not altered; no runtime/tests ran. Next build gate: a dedicated environment aligned with uv.lock and a pinned build toolchain, followed by a fresh bundle. Legal/license and Qt/MSVC gates remain open.
## E16.01/E16.05 — lock-aligned portable candidate — 2026-10-30

Added PyInstaller as a separate optional `build` extra and resolved it into `uv.lock` (PyInstaller 6.22.3; hooks-contrib 2026.9). `scripts/build_release_candidate.ps1` creates/uses a separate `.venv-release`, synchronizes desktop/build dependencies with `uv sync --locked`, then invokes the onedir build. The existing `.venv312` and installed application were not synchronized or replaced. Build output: `D:\UFM_ReleaseCandidate3\UFM Studio`, using CPython 3.12.15. Static comparison of its 21 installed runtime distributions against the lock found no missing packages or version mismatches; the bundle manifest verified all 370 file hashes without mismatch. Static archive view confirms the explicit Windows Credential Manager win32ctypes implementation modules are present. Bundle inventory reports zero DB/SQLite sidecars, logs, `.env` or private-key suffix files. Size: 214,834,774 bytes. No application/GUI/database/printer/runtime tests were launched. Candidate2 was not lock-aligned; candidate1 lacked the credential-store modules. Both remain separate and should not be used as current release candidate.

Updated the user guide and design notes with the locked candidate build procedure. Checklist E16.01/E16.05 remains Partial: this proves a reproducible dependency folder build and exact file inventory only. It does not establish runtime acceptance, license compliance, clean-machine installation or release readiness. E16.02 remains Partial because `ISCC.exe` is unavailable; the Inno Setup script is not compiled. E16.03/E16.07 remain Partial; no cleanup, install, upgrade, uninstall or data migration was run. The currently installed `D:\UFM Studio`, desktop shortcut, real databases, credentials and HaspelSync changes remain untouched.
## E16.02/E16.08 — compiled installer candidate and acceptance protocol — 2026-10-30

Installed Inno Setup 6.7.3 in user scope using the verified winget package (JRSoftware.InnoSetup); `scripts/build_installer.ps1` successfully compiled `scripts/ufm_studio.iss` from the hash-verified Candidate3 bundle. Output: `D:\UFM_InstallerCandidate3\UFM-Studio-Setup-0.1.0.dev0.exe`, 61,474,770 bytes, SHA-256 `deb550f43139c33f6d2a5516579bbfd86e868c50eace5e6f7c65f7fb876c86b7`. Authenticode reports NotSigned. Compilation is not installation acceptance: installer was not launched; upgrade, shortcuts, rollback, uninstall and user-data retention remain unverified. Added `docs/RELEASE_ACCEPTANCE_UK.md` and linked it from the Studio guide. E16.02/E16.08 remain Partial; public release is blocked on legal/license review, signing and clean-machine acceptance. The installed `D:\UFM Studio`, its shortcut, databases, credentials and HaspelSync were not changed. No product runtime, database or printer tests ran.
## E16.07 — cleanup allowlist dry-run evidence — 2026-10-30

Executed `scripts/clean_project_caches.ps1` without `-Apply`. Report `docs/CLEANUP_REPORT-20261030T150320454Z.json` records `.pytest_cache` 5 files/80,681 bytes, `.mypy_cache` 3 files/25,321,701 bytes, `.ruff_cache` 10 files/29,846 bytes; `Applied=false`. The original `docs/CLEANUP_REPORT.json` remains unchanged and all three cache directories remain. This was an inventory-only dry-run; no cache was deleted. E16.07 remains Partial because no cleanup/acceptance run with `-Apply` was requested or needed.
## E16.02 — installer output path guard — 2026-10-30

Hardened `scripts/build_installer.ps1`: before creating the output directory, it rejects destinations equal to or nested under the verified candidate bundle, then inspects every existing path component and refuses reparse points (including symlink/junction ancestors). This prevents installer output from contaminating the hash-verified bundle and prevents writes redirected through an existing link. The E16.02 checklist remains Partial: installer compilation is recorded, but installation, upgrade, shortcut, rollback and uninstall/data-retention behavior are not accepted; the artifact remains unsigned. No installer or product runtime was launched, and no user data was changed.

## E16.05 — preliminary CycloneDX candidate inventory — 2026-10-30

Added `scripts/write_release_sbom.py`, which first verifies the candidate bundle manifest, binds the bundled runtime inventory to its manifest hash, checks that the output is outside the bundle and not routed through a reparse point, then writes CycloneDX 1.7 JSON. Generated `docs/RELEASE_CANDIDATE3.cdx.json` for Candidate3: 370 manifest-hashed file components, 20 packaged Python library components, and UFM Studio as the root application. Deterministic BOM serial derives from the manifest and runtime inventory hashes. The composition is explicitly `incomplete`; Python dependency edges are derived from `uv.lock`, while full dependency completeness, native binary/package attribution, Node/npm component attribution and legal license conclusions are not established. Package license metadata and notice filenames are recorded only as observed properties. Ruff passed; generator re-verified all 370 candidate files and official CycloneDX 1.7 JSON Schema validation passed with PowerShell `Test-Json`; structural review confirmed unique references and SHA-256 entries. No tests or application runtime ran; bundle and installed app/data remain unchanged. E16.05 remains Partial.

## E16.05 — candidate build now emits SBOM sidecar — 2026-10-30

Extended `scripts/build_release_candidate.ps1` to preflight the destination before uv sync/build, reject pre-existing bundle or SBOM outputs, reject reparse-point destination ancestors, and generate `UFM Studio.cdx.json` beside each fresh bundle. This keeps the CycloneDX BOM outside the bundle tree it inventories and preserves prior release evidence. The already-built Candidate3 sidecar is `D:\UFM_ReleaseCandidate3\UFM Studio.cdx.json` (195,522 bytes, SHA-256 `54e36c4059e4cf9458641ccb5691ba844e5a31c96eac1dea0363de61a6392c1e`). It passed the official CycloneDX 1.7 JSON Schema and records 370 hashed files, 20 Python library components, and lock-derived Python dependency edges. PowerShell AST and Ruff passed. No candidate rebuild, installer run, tests, product runtime, database, or printer access occurred. E16.01/E16.05/E16.08 stay Partial because native component attribution, license/signing review and clean-machine/runtime acceptance remain open.

## E16.05/E16.08 — SBOM gate added to Windows acceptance protocol — 2026-10-30

Updated `docs/RELEASE_ACCEPTANCE_UK.md` with the Candidate3 SBOM sidecar path and SHA-256, schema status, and an explicit warning that the artifact is incomplete and provides no license/release approval. The preflight now requires version/bundle matching and does not allow an incomplete composition to be mistaken for a full software/license inventory. Checklist E16.05/E16.08 evidence was extended; statuses remain Partial. No installer, app, tests, DB, or printer were run.

## E16.05 — SBOM identifies bundled Node.js and Haspel calculation subset — 2026-10-30

Extended `scripts/write_release_sbom.py` to require Node.js PE `ProductVersion` from its caller, require the Node executable/license and four vendored Haspel calculation/provenance files in the verified candidate manifest, and emit explicit Node.js and narrowly scoped HaspelSync calculation-resource components with dependency edges to those manifest-hashed file components. `scripts/build_release_candidate.ps1` reads PE version metadata (does not launch Node) and passes it to the generator. Updated the manual command in `docs/STUDIO_USER_GUIDE_UK.md`. Regenerated documentation BOM and Candidate3 sidecar; both are 198,927 bytes and SHA-256 `97baeed4c09f8398ec688255dc33f76a3e399d395bc217743f8cf1e09d4ee445`. The BOM has 392 components: 370 files, 20 packaged Python libraries, Node.js 24.22.1 and the minimal Haspel calculation-resource subset. Official CycloneDX 1.7 JSON Schema validation passed; static review confirms unique component references and all dependency targets resolve. Ruff, Python AST parsing and PowerShell AST parsing passed. Composition remains `incomplete`; this does not establish full native dependency attribution, legal/license compatibility, or distribution approval. The hash-verified bundle and installed app, installer, databases, credentials and printer were not changed. No product runtime or tests ran. E16.05/E16.08 stay Partial.

## E16.02/E16.08 — installer compilation binds SBOM to candidate — 2026-10-30

Hardened `scripts/build_installer.ps1`: before creating installer output or invoking Inno Setup, it now requires the adjacent `UFM Studio.cdx.json`, checks CycloneDX 1.7 and candidate version, then matches exactly one SBOM `ufm:bundle-manifest-sha256` to the actual bundle manifest and one `ufm:runtime-inventory-sha256` to the packaged runtime inventory. It requires one `incomplete` composition so the release gate cannot read this preliminary BOM as a complete inventory. Updated `docs/STUDIO_USER_GUIDE_UK.md` and `docs/RELEASE_ACCEPTANCE_UK.md`. PowerShell AST parse passed; read-only Candidate3 check matched version `0.1.0.dev0`, manifest SHA-256 `27890b4053c5d41524ec9b3040ef762d78ce1a40c111d6ce7e4a82214601a8b4` and incomplete composition. No installer compilation was repeated, and installer/app were not launched. E16.02/E16.08 remain Partial pending candidate/installer rebuild, signing and clean Windows acceptance. No tests, DBs, secrets or printer were used.

## E16.05 — Qt runtime DLL attribution in Candidate3 SBOM — 2026-10-30

Extended `scripts/write_release_sbom.py` to add a Qt framework component and explicit dependency edges to Qt core/plugin DLL file components under the verified `_internal/PySide6` bundle path. `scripts/build_release_candidate.ps1` reads static PE `ProductVersion` from all bundled Qt core/plugin DLLs, requires one valid shared three-part version, and passes it alongside Node PE version; it does not launch application or runtimes. Candidate3 has 26 matching Qt DLL files and all statically report `6.12.0.0`, normalized to Qt `6.12.0`. Regenerated docs BOM and sidecar; both have 393 components, 201,824 bytes and SHA-256 `aa6c45b526271e5e74d1c58a0d8183c1705fee5b93cf7c1a72dff82ceed8b199`. CycloneDX 1.7 schema passed, and static checks confirmed unique refs, all dependency targets resolve, and 26 Qt file edges. Composition remains incomplete: MSVC/runtime and other native attribution, applicable license review, signing and clean-machine acceptance are open. Ruff and Python/PowerShell AST parsing passed. Candidate bundle, installed application, installer, user data, credentials and printer unchanged. No tests or application/runtime execution. Updated release acceptance, user guide and E16.05/E16.08 checklist evidence; both checklist statuses remain Partial.

## E16.05 — записано тимчасову політику оновлень — 2026-10-30

У `docs/STUDIO_USER_GUIDE_UK.md` та `docs/RELEASE_ACCEPTANCE_UK.md` записано політику, узгоджену з фактичним станом коду: автоматичний updater відсутній; поточні unsigned candidate не накладати на встановлену програму; майбутній схвалений реліз вимагає перевірки Authenticode, версії, manifest та SBOM, backup до міграції та збереження user data. Downgrade не приймається звичайним setup і може бути дозволений лише після окремо перевірених restore/migration кроків. Це документаційна політика, не реалізація/приймання; E16.05 лишається Partial. Статус коду AppPaths підтверджує розділення user data через `platformdirs`; setup script не має `[UninstallDelete]`. Потрібні зовнішній підписний сертифікат, чисте Windows-середовище та окреме приймання; їх не симулював і не заявляю як пройдені.

## Release readiness audit — 2026-10-30

Read `AGENTS.md`, project progress, 118-row integration checklist, step plan, latest handoff, release acceptance/user guide, and Graphify project maps. No product source, user databases, secrets, backups, linked-stack or app/installer artifacts were changed. Static evidence: Candidate3 manifest verified 370 file hashes; 21 runtime distributions have no version drift/missing lock records; bundle path scan found no DB/SQLite, log, `.env` or private-key artifacts. CycloneDX 1.7 BOM has 393 components, passes the official schema, all dependency refs resolve, and matches the sidecar; SHA-256 `aa6c45b526271e5e74d1c58a0d8183c1705fee5b93cf7c1a72dff82ceed8b199`; completeness is explicitly `incomplete`. `ruff check src scripts` passes, Python AST parsed 149 source/script files, 8 PowerShell scripts parse, and 100 local Markdown links in 48 Markdown files resolve. Whole-root `ruff check .` reports 23 findings, all shown under `.runtime` scratch or prior packaged Alembic stubs; scoped release source lint passes.

Release decision: NOT READY for public distribution. The integration checklist is 29 Done / 42 Partial / 46 Planned / 1 In Progress; feature matrix is 28 Existing / 30 Partial / 46 Add / 20 Desired. F053 automatic debit is Partial/P0 and F050 print-job spool binding is Add/P0. `EstimatedUsagePolicy.enabled` defaults False, `ReceiptIngestion.ingest` has no production caller under `src/ufm`, and the UI drains only the latest event for display. No P0 auto-debit path is enabled. Candidate3 installer SHA-256 is `deb550f43139c33f6d2a5516579bbfd86e868c50eace5e6f7c65f7fb876c86b7`, Authenticode `NotSigned`; it predates the current SBOM-binding build script and has not been rebuilt or installed. Candidate EXE is also `NotSigned`; its PE ProductVersion field is empty while manifest version is `0.1.0.dev0`. Root UFM license is absent/unselected, Qt/PySide and Microsoft runtime terms are unresolved, SBOM remains incomplete, and clean Windows install/upgrade/rollback/data-retention acceptance has not occurred. Tests, app/installer runtime, DB, credentials and printer were not run/touched. Checklist E03.06 and E16.02/04/05/08 evidence updated without changing statuses; see `docs/RELEASE_ACCEPTANCE_UK.md`.

## E16.01/E16.02/E16.05/E16.08 — Candidate4 rebuild — 2026-10-30

Fixed missing Windows PE version metadata: new `scripts/write_pyinstaller_version.py` reads the canonical `project.version` from `pyproject.toml` and emits a PyInstaller resource; `build_studio.ps1` generates it under ignored `.runtime/build-metadata`, scopes it to the build, and restores the caller's environment; `ufm_studio.spec` now requires and embeds it. Static checks: `ruff check src scripts` clean, Python AST parsed 151 source/spec files, and the modified PowerShell script parsed. Built separately with the locked `.venv-release`: `D:\UFM_ReleaseCandidate4\UFM Studio`; manifest verified 370 hashes, package inventory contains 21 distributions with no lock drift. EXE SHA-256 `1ead5dfbf6ab414aa9dfe990b7ae75ae235dd7a59b7d2b0d22f63b38578289a9`; PE FileVersion and ProductVersion both `0.1.0.dev0`. Candidate4 sidecar SHA-256 `1b4cfd283df2e843f581f54ba71808b1c362e7cb47b39302605841c50a18a481`, 393 components, CycloneDX 1.7 schema passes, and installer preflight matched candidate version plus manifest/runtime inventory hashes. Compiled separate installer `D:\UFM_InstallerCandidate4\UFM-Studio-Setup-0.1.0.dev0.exe`, SHA-256 `3673df1d876e4444a4f9f829072489aec7d96f07271c00d0182e5e8568a2c53e`; Authenticode is `NotSigned`. Installer/app were not run or installed; no tests, DB, secrets or printer were touched. E16.01/E16.02/E16.05/E16.08 remain Partial; signature, licensing approval, complete native attribution, clean Windows acceptance, upgrade/rollback and accounting P0 are still release blockers.

## E16.02/E16.05 — optional fail-closed Authenticode build path — 2026-10-30

Added `scripts/sign_windows_artifact.ps1`; `build_release_candidate.ps1`, `build_studio.ps1` and `build_installer.ps1` accept paired signing-certificate thumbprint and RFC3161 timestamp URL parameters. The helper requires an exact currently valid certificate with Code Signing EKU and accessible private key in a Windows personal store, a Microsoft-signed `signtool.exe`, SHA-256 signing and successful `/pa` verification. EXE signing is ordered before manifest generation; installer signing is after compilation. Supplying only one of the paired parameters is rejected. No certificate was selected, no private key read/export/signing performed, and Candidate4 remains `NotSigned`. Release acceptance instructions document the operator-supplied approval inputs. Ruff and Python/PowerShell AST static checks pass; no tests/runtime ran. E16.02/E16.05 remain Partial pending signing authority, complete component/license review and Windows acceptance.

## E07.03/E07.04/E07.05 — стоп-перевірка live printer event identity — 2026-10-30

Graphify was used to locate the provider/monitor/projection path; claims were checked in source and `docs/CONSUMPTION_COMPARISON_UK.md`. `BambuLanProvider.__init__` assigns a fresh UUID `source_epoch`; `PrinterMonitorTask._run_provider_once` invokes the factory on each reconnect; `StudioWindow.show_latest_monitored_event` calls `take_latest_event`, which drains/discards earlier buffered observations. No production caller invokes `ReceiptIngestion` or `ProjectionDrain`. `PrintJobSnapshot.provider_run_key` remains unset by Bambu. The local Bambu source documents `BBLSubTask::task_id` as a plate ID and task name as usually the filename; neither is an exact run identifier. Job projection uniqueness is scoped by provider/printer/source_epoch/occurrence, so merely wiring the existing event callback would create loss/duplicate/misattribution risks. Do not debit stock or wire directly to finalization. E07.03/E07.04/E07.05 remain partial. Next safe implementation prerequisite: establish a durable exact-run identity and monotonic event sequence across reconnect/restart, with provenance and same-file sequential-run evidence; then persist the whole FIFO event batch and project receipts, still without debit until mapping/evidence policy gates pass. No live printer/MQTT session or print was started; no tests/runtime were run in this step.

## Повторний аудит проєкту та перевірка suite — 2026-10-30

Автоматизацію `ufm` оновлено без дублювання: ACTIVE, кожні 15 хвилин, prompt охоплює аудит/план до підтвердженої готовності релізу, порогову паузу Codex, Graphify-first, checkpoint-документи, збереження даних і no commit/push/deploy.

Використано `D:/graphify-out/bambu-ufm/PROJECT_MAPS_UK.md` як навігацію; факти про автоматичний облік перевіряти кодом і evidence, не самим графом. Сфера статичного аудиту — `src`, `scripts`, `tests`, README/core docs, план, CSV, release acceptance та Candidate4 metadata. Не прочитувалися повністю бінарні/runtime/cache та vendored linked-stack дерева; secrets, DB, backup, printer і production artifacts не торкалися. Root + docs: 56 Markdown-файлів, 115 внутрішніх посилань без відсутніх цілей. AST/конфігурації: 223 Python, 11 JSON, TOML, 9 PowerShell без синтаксичних помилок; Ruff `src scripts tests` чистий.

Перший повний suite виявив stale test assumptions, не підставу послаблювати production guard: `create_scope` не готував явний printer-accounting cutover, snapshot helpers наказували кожній таблиці `ORDER BY id`, migration очікував 36 замість 39 tables, а registry check очікував 18 рядків та не розбирав handler mappings. Виправлені лише tests: seeded валідний legacy→CUTOVER_READY→UFM_ACTIVE transition через application commands; snapshot сортується за metadata primary key; migration очікує 39 і перевіряє нові таблиці; Studio registry має 22 records і перевіряє всі handler names; projection crash helper так само використовує ключі таблиці. Після цього focused suites — 63 passed/24 subtests; projection crash suite — 3 passed/5 subtests; Ruff clean.

Точний locked env `.runtime/audit-py312` (Python 3.12.15, SQLAlchemy 2.1.6, Alembic 1.20.1, pytest 9.2.0): весь non-UI suite — 563 passed/485 subtests/exit 0; Studio suite окремо — 62 passed/exit 0. Злитий запуск — 625 passed/485 subtests, однак Windows процес завершується після summary з exit `-1073741819` (`0xC0000005`, access violation). Це лишається перевірочним блокером; наступна дія — ізолювати Qt teardown/interaction або підтвердити стабільний підтримуваний роздільний runner, не підміняти summary на success. Встановлена програма, candidate/installer, user DB, credentials і принтер не запускалися.

Оновлено guide приклади з Candidate3 на поточний Candidate4; `PROJECT_PROGRESS_UK.md`, `RELEASE_ACCEPTANCE_UK.md`, CSV UTF-8 BOM. CSV лишився: 118 кроків; 29 виконано /42 частково /46 заплановано /1 у роботі. E16.01 evidence доповнено, статуси не підвищувались. Реліз не готовий: unsigned dev candidate; UFM/Qt/MSVC ліцензійне рішення та повна native SBOM відсутні; потрібні підпис, чисте Windows install/upgrade/rollback/data-retention acceptance. Функціональні P0: E07 stable run identity/FIFO receipt projection, F053 автоматичне списання та F050 job→spool binding; поточний активний checklist step E05.04 все ще очікує фізичний ScaleProvider/calibration/hardware acceptance. Наступний крок — розібрати Qt full-suite shutdown і продовжити E05.04 у безпечному шарі; E07 не вмикати до підтверджених живих run-identifiers.



## Точка продовження: Qt/native suite exit — 2026-10-30

Перевірено останню відому нестабільність без змін application source. Locked env: `.runtime/audit-py312` (Python 3.12.15; `uv.lock`). Studio module: **62 passed**, але повторний повний процес після pytest summary завершується Windows `0xC0000005`; faulthandler показує `<no Python frame>`. Діагностика по діапазонах: перші 30 завершились exit 0; 31–40 один раз упали на teardown, але всі десять поодинці пройшли й повтор цієї групи пройшов; інші групи 10 та обидві половини 31+31 пройшли exit 0. Флейк не прив’язаний до доведеного конкретного testcase, причина досі не встановлена. Цільовий `test_printer_monitor_retries_transient_errors_with_capped_backoff` — п’ять окремих process runs успішні. Non-UI suite — 563 passed/485 subtests/exit 0. Не трактувати 62 зелені assert як успішний завершений process run.

Типізаційні правки вже присутні: `mypy src` — успіх для 137 source files; `ruff check src scripts tests` — чисто. Під час цього етапу production code не змінювався. `docs/INTEGRATION_CHECKLIST_UK.csv` E16.01 отримав доказове доповнення без зміни статусу; UTF-8 BOM перевірено, CSV shape 118. Status counts: {'Частково виконано': 42, 'Виконано': 29, 'Заплановано': 46, 'У роботі': 1}. Usage: 62% primary /35% weekly remaining. Наступний крок: провести мінімальну контрольовану локалізацію native exit (Qt/PySide DLL/plugin/process teardown) на ізольованій тестовій БД; якщо не локалізується — записати, що full-suite process exit залишається release gate, не ховати збій через split-run. Не чіпати user environments, production DB, принтер, підпис, deploy чи installer acceptance без потрібних власницьких матеріалів.


## Точка продовження: Candidate5 для ручного тесту — 2026-10-30

Зібрано актуальний portable package `D:\UFM_TestCandidate5\UFM Studio` із поточного source у новому `.runtime\ufm-test-candidate-py312` (uv locked Python 3.12.15; desktop/build extras). Установлений `D:\UFM Studio`, `.venv312`, `.venv-release`, production/user data й два існуючі ярлики не перезаписувалися. Build exit 0; manifest verification — 376 files; PE FileVersion/ProductVersion `0.1.0.dev0`; EXE SHA-256 `4b7903fc2be099eec1b0f62db9137741fe17ad4eb10fe17d7162c2cd9b57ef35`, NotSigned. Generated CycloneDX sidecar has 399 components, explicitly incomplete; SHA-256 `4227dac3dce6fe15b3d401405b38eb97970ffe31eb087b0446ce3d12d954d113`; Qt 6.12.0 (26 DLL), Node 24.22.1. Created isolated desktop shortcut `C:\Users\-PC-\Desktop\UFM Studio — ТЕСТ Candidate5.lnk`, arguments `--data-dir "D:\UFM_TestCandidate5\Data" --locale uk-UA`. Test Data directory does not exist until first user launch. Candidate was not run by agent; do not call it UI-accepted. Existing `UFM Studio.lnk` points to installed build/data; `Universal Filament Manager.lnk` points to `.venv312` development start. No prior shortcut changed.

CSV E16.01/E16.08 evidence appended; statuses unchanged; BOM present, 118 records; counts {'Частково виконано': 42, 'Виконано': 29, 'Заплановано': 46, 'У роботі': 1}. Next user-side acceptance: launch only the new “ТЕСТ Candidate5” shortcut, verify navigation/forms/error handling/printer connection in read-only mode, and report observed issues. Avoid production spools/auto debit. Continue working on remaining source-addressable release gates; unsigned, incomplete SBOM, Qt teardown flake, license decisions and hardware/live printer acceptance still block public release. No commit/push/deploy.


## UI огляд і Candidate7 — 2026-10-30

У Candidate5 візуально виявлено обрізання підписів у панелях дій, надмірно
яскраве виділення рядка й застарілий preview-текст системної сторінки. У
`src/ufm/ui/studio_window.py` панелі фільтрів/дій переведено на `QGridLayout`,
для `QTableWidget::item:selected` встановлено виразний зелений фон і білий текст,
права інспектор-панель котушки вкладена у `QScrollArea`, футер використовує
локалізований build label. `src/ufm/ui/studio_strings.json` показує точний стан
test build і відкриті умови публічного релізу. Статичні перевірки: Ruff для
зміненого UI clean, JSON valid. Candidate7 зібрано `scripts/build_studio.ps1`
у `D:\UFM_TestCandidate7\UFM Studio`; manifest перевірено —
376 files; EXE SHA-256 `cdb0d8dae0f2738ee6dd0824e64750c44238ef5983a09b7434cce27ad0402498`; unsigned test build.
Створено окремий ярлик `C:\Users\-PC-\Desktop\UFM Studio — ТЕСТ Candidate7.lnk`
з ізольованим шляхом `D:\UFM_TestCandidate7\Data`, старі ярлики лишено.
Запущений Candidate7 оглянуто на сторінках Філамент, Пристрої, Матеріали,
Система і в темній/світлій темах. Панелі тепер відображаються сіткою з повними
підписами; довгі дії котушки доступні прокруткою. Ізольований
`tests/integration/test_studio_window.py` завершився `62 passed` з кодом 0; Ruff
і JSON parse пройшли. Тестові зміни облікових даних, мережі, принтера або
залишків не виконувалися.

Acceptance межа: це agent visual/runtime smoke на локальному build, не
власницьке приймання і не hardware acceptance. Candidate7 ярлик запускає окрему
тестову базу. Checklist E16.01/E16.08 отримали доказ Candidate7 без зміни
статусів; лишилося 118 кроків. Реліз не готовий: incomplete SBOM, unsigned,
ліцензійні рішення, P0 auto-debit/job mapping, Qt/native suite teardown,
clean-Windows install/rollback та hardware acceptance не закриті.


## Release-протокол синхронізовано з Candidate7 — 2026-10-30

Оновлено `docs/RELEASE_ACCEPTANCE_UK.md`: Candidate4 лишається історичним
формальним unsigned release candidate/installer, а найновіший Candidate7
описаний окремо як локальний internal UI build. Для Candidate7 згенеровано
sidecar CycloneDX 1.7 із 399 компонентами та явно неповною композицією; його
SHA-256 `e64a507b67361e92b295f0005631219429021088f3411b8261721a4d10fc0872`.
E16.01/E16.08 доповнено без зміни статусів; CSV BOM/118 rows підтверджено.
Публічний release лишається NOT READY. Наступне: перевірити за планом найближчий
залежний технічний gate; не оголошувати E05.04 виконаним без вагового hardware
acceptance, а E07 identity без підтверджених provider observation/fixtures.


## Документація ярликів для Candidate7 — 2026-10-30

У `docs/STUDIO_USER_GUIDE_UK.md` додано точний ярлик останньої UI test збірки,
відокремлену базу Candidate7 і різницю з Candidate5, встановленим Candidate4 та
development ярликом. Це прибирає ризик випадково тестувати застарілий Candidate5.
`docs/FEATURE_PARITY_MAPPING_UK.csv` F118 тепер містить факт нового sidecar
Candidate7 (399 components, incomplete), без заяви про повноту. `E16.08` доказ
оновлено; статуси лишились незмінними, CSV BOM і форми 118/124 рядків збережені.
Наступне — перейти до найближчого незавершеного технічного кроку, підтвердити кодом
і fixture; зовнішні hardware/run-identity gates не вигадувати.


## Read-only перевірка відкритих UI-вікон — 2026-10-30

Computer Use inventory підтвердив Candidate7 (`D:\UFM_TestCandidate7\UFM Studio`) і попередній Candidate5 одночасно відкритими. Отриманий Candidate7 accessibility snapshot показує головну українську навігацію та порожній локальний тестовий інвентар. Жодної дії в застосунку не виконано; production data, printer, accounting і налаштування системи не зачіпалися. PROJECT_PROGRESS_UK.md next-action переміщено на E14.03 (keyboard/focus/DPI/resize огляд); E16.04 за CSV є окремим clean-Windows install/reinstall gate. Системне DPI не змінювали. Checklist E16.08 отримав read-only runtime evidence без зміни статусу; BOM та 118 рядків збережені. Публічний реліз залишається NOT READY.


## Candidate8 focus-style build — 2026-10-30

QSS у `src/ufm/ui/studio_window.py` отримав помітні focus borders для кнопок, текстових/combo inputs, навігації та таблиці. Перевірено наявний Studio test module: 62 passed/exit 0; Ruff clean; locale JSON parses. Перший build attempt із audit-only env припинився до PyInstaller через відсутність PyInstaller; повторено в ізольованому `.runtime/ufm-test-candidate-py312` і успішно зібрано в нову папку. Candidate8 manifest: 376 файлів; EXE SHA256 `0DF64CCB71ACACB1B88A9669837F5FE72D42D6A265708017385AB0BCEC7598D3`; version `0.1.0.dev0`; unsigned. CycloneDX 1.7 sidecar — 399 components, composition `incomplete`, SHA256 `6AA4F3C1BDC4C3A904777012F412A2F849BAF85376C9CF1AADB1DFF4FBC567B0`. Створений окремий ярлик Candidate8 із ізольованою папкою `D:\UFM_TestCandidate8\Data`; нову збірку тут не запускали. E14.03 «Частково виконано»; потрібна власницька перевірка фокус-індикатора й keyboard traversal, а DPI acceptance не заявляти. Checklist CSV лишається 118 rows/BOM, statuses 29/43/45/1. Clean-Windows E16.04, hardware E05.04, stable printer identity E07 та всі попередні release-блокери лишаються відкритими.


## E08.04: перевірка effective Marlin E mode — 2026-10-30

Перевірено `src/ufm/integrations/gcode_extrusion.py`: M82/M83 перемикають effective E mode, G90/G91 його скидають. Це збігається з першоджерелами Marlin https://marlinfw.org/docs/gcode/M082.html та https://marlinfw.org/docs/gcode/M083.html. Targeted existing parser suite: 7 passed/24 subtests/exit 0. Parser залишається строгим лише до `marlin-linear-v1`; vendor dialects, firmware retract, volumetric modes та printer runtime не оголошені підтриманими. E08.04 має статус Partial, evidence додано в CSV (BOM збережено); жодного printer/accounting action. Наступний source-addressable крок — перевірити E09.03 UI details проти persisted receipt/provenance, зберігаючи «estimate» відокремленим від measurement.


## Candidate9: розрахункова витрата з перевіреною provenance — 2026-10-30

У `src/ufm/ui/studio_window.py` історія оцінкового ledger entry показує наявні `print_job_id` і `source_receipt_id`. Для `THREE_MF` короткий hash і номер пластини додаються лише коли JSON metadata невеликий, quantity/label очікувані, SHA-256 — 64 lowercase hex, а plate — обмежене ціле; довільне metadata та шляхи користувачу не виводяться. `studio_strings.json` має українські й англійські labels. Наявний `tests/integration/test_studio_window.py` після змін: 62 passed/exit 0; Ruff та locale JSON parse пройшли. Це не доводить повний job-details UI або наскрізне receipt/job→spool приймання; E09.03 лишається Partial, auto debit не запускався.

Candidate9 ізольовано зібраний у `D:\UFM_TestCandidate9\UFM Studio`; `write_studio_manifest.py --verify`: 376 файлів. EXE version `0.1.0.dev0`; SHA-256 `99AF566B4E6CD3E38347437555C7ACCC7DB85C871585D31FE3CCE260B091AEE0`; Authenticode NotSigned. CycloneDX sidecar `D:\UFM_TestCandidate9\UFM Studio.cdx.json`: 399 components, composition incomplete; SHA-256 `148438580A356B393A4563C580E62056BF8A127A9FCFF93E1DA26BD2CE3E42A8`. Новий Desktop ярлик `UFM Studio — ТЕСТ Candidate9.lnk` веде на цей EXE й окремий `--data-dir D:\UFM_TestCandidate9\Data`; data folder відсутня до першого запуску, Candidate9 агентом не запускався. Candidate5/7/8, встановлена програма, старі ярлики й робочі дані не змінювалися.

CSV BOM/118 рядків збережено; статуси E09.03/E14.03/E16.08 не підвищувалися. `PROJECT_PROGRESS_UK.md`, `RELEASE_ACCEPTANCE_UK.md`, `STUDIO_USER_GUIDE_UK.md` синхронізовані на Candidate9. NOT READY лишається чинним через unsigned/incomplete SBOM, licensing/installer gates, Qt native teardown flake, unresolved auto-debit/job identity, фізичне hardware acceptance й clean-Windows/owner UI acceptance.

Точка продовження: перевірити наступний залежний E09.03 job/receipt projection проти application command та persistence contract, не підключати production printer і не запускати списання без підтверджених stable provider run IDs; паралельно власник може вручну оглянути Candidate9 у повністю ізольованому data-dir.


## E09.04: fail-closed material-to-slot matching review — 2026-10-30

Graph-guided source review was verified against `src/ufm/application/job_material_mapping.py` and `mounted_material_mapping.py`. Logical-material mapping accepts only the same verified file SHA, same printer, current complete provider snapshot, an explicit unique provider-system/slot mapping, and an occupied slot. This layer returns an observation only; its docstring explicitly excludes spool assignment, mount, usage segment, reservation and ledger writes. A spool resolution further requires the exact persisted slot snapshot plus audit proof, active mount, verified exact RFID identity and matching mounted spool. Unknown/conflict/unmounted states do not yield a spool.

Existing isolated suites: `tests/unit/test_job_material_mapping.py`, `tests/integration/test_job_projection.py`, `tests/integration/test_topology_commands.py` — 63 passed, 38 subtests, exit 0 (10.8s). No tests were added. E09.04 stays Partial because interactive operator review/reconciliation UI and live provider acceptance are absent. No printer, account, production database or stock was touched.

CSV UTF-8 BOM and 118 records retained. Candidate9 artifact remains the latest unsigned internal portable test build; public release is NOT READY. Source trace completed: `ProjectionDrain` has only its class/constructor in production `src`; no composition root calls `run_once`, and `ReceiptIngestion.ingest` has no production call site. `StudioWindow.__init__` exposes only inventory, printers, materials and settings; `show_history` renders spool ledger, not a print-job browser. There is currently no reliable persisted job-read model exposed to the UI. Do not synthesize a jobs page from transient `take_latest_event` or bypass the durable receipt path.

Next: inspect the Bambu monitor event/epoch/sequence contract and the worker lifecycle to determine whether a durable consumer can be safely integrated without merging reprints or dropping/replaying events. Until stable event identity and an end-to-end receipt path exist, keep job→spool review and auto-debit unavailable. E05.04 hardware and owner/clean-Windows acceptance remain external.


## Candidate9 documentation cross-check — 2026-10-30

Static documentation cross-check: 86 local Markdown links under `docs/` resolve; no broken in-repository targets. `INTEGRATION_CHECKLIST_UK.csv` remains 118 records/5 columns and `FEATURE_PARITY_MAPPING_UK.csv` remains 124 records/7 columns; both are valid CSV with UTF-8 BOM. Candidate9 references are current in PROJECT_PROGRESS, RELEASE_ACCEPTANCE, STUDIO_USER_GUIDE, the E16.08 checklist evidence and feature F026/F118 mapping; Candidate8 references are historical/archival. No release criterion was promoted by a link/doc check.


## E07.04 provider reconnect identity source audit — 2026-10-30

Graphify navigation plus direct source review confirmed: `BambuLanProvider.__init__` sets random `source_epoch = uuid4()` and `_event_sequence = 0`; `subscribe_events` emits `event_key=str(_event_sequence)`, so the counter is local to that instance. `PrinterMonitorTask._run_provider_once` calls `_provider_factory()` each connection/retry. The 256-item FIFO raises explicit overflow, but current `StudioWindow` callback calls `take_latest_event()`, which drains the whole queue and displays only the last event. `take_pending_events()` preserves order for a future consumer but has none in production source; `ReceiptIngestion`/`ProjectionDrain` also have no production call sites. The Bambu Studio local source `D:\GIT\BambuStudio\src\libslic3r\ProjectTask.hpp` explicitly comments `BBLSubTask::task_id` as plate id and `task_name` generally filename; this is not proof of MQTT run identity.

No code change is safe to connect stock accounting: current epoch/counter cannot prove reconnect/replay identity, and stored job identity must distinguish a reprint of the same file. E07.04 remains Partial. No printer/account/data connection was attempted. Next source work should wait for a verified provider run-ID contract or real redacted MQTT traces spanning reconnect, same-file reprint, terminal events and replay, plus exact model-specific fixtures; then implement consumer, persistence and projection without treating filenames/plate IDs as unique job runs.


## Checklist recovery and evidence reconciliation — 2026-10-30

The current checklist file was reconstructed from the latest intact Graphify snapshot `20261030T135228744943Z` after a local documentation-write mistake replaced its contents with a duplicate of the progress note. Documented post-snapshot evidence/status changes were reapplied from the handoff and current progress records: E16.01/.02/.03/.04/.05/.08 and E14.03 are Partial; E08.04, E07.04 and E09.03/.04 evidence includes the current Candidate9/source audit. The resulting CSV was reopened and checked: UTF-8 BOM, 118 records, 5 expected columns, status counts 29 Done /43 Partial /45 Planned /1 In Progress. No other user data or source files were touched by this recovery. Future edits must use a named `csv_file` variable and verify the CSV after writing before touching another path.


## Current full-suite process-exit verification — 2026-10-30

After the Candidate9 source changes, the locked `.runtime/audit-py312` full suite was run four times: each reported 625 passed/485 subtests; three process runs exited 0, one exited 1 after the complete summary without a pytest failure trace. A fifth invocation with `-X faulthandler` also reported 625/485 and exit 0, with no Python fault traceback. This supports a current passing run but does not establish deterministic process exit or explain the prior Windows native teardown/access-violation report. Keep this as an unresolved release gate; do not conceal the abnormal exit by relying on green assertion counts. No source changed during these runs; all tests use isolated local fixtures/temporary databases.


## Candidate10 — актуальна тестова збірка та source validation — 2026-10-30

Поточне джерело з Haspel accounting-authority UI зібрано окремо через `scripts/build_release_candidate.ps1 -DestinationParent D:\UFM_TestCandidate10`; вихідні Candidate5–9 і production інсталяція не перезаписувались. Manifest verification повернула 376 файлів. EXE SHA-256 `D398AA91BEAD3495FF1B78DF1775CCB2E4A16B85CD421FAC54F64562B0D0BF02`; PE `0.1.0.dev0`; підпис `NotSigned`. SBOM sidecar SHA-256 `9fab23232057f20076bb8fecb6c5ad4bbb09e0ad6719d8903a3701310dc61156`, CycloneDX 1.7, 399 components, `incomplete`. Створений окремий Desktop ярлик `UFM Studio — ТЕСТ Candidate10.lnk` передає `--data-dir "D:\UFM_TestCandidate10\Data" --locale uk-UA`; target/args/working-directory перечитані через WScript.Shell, data folder поки не існує. Застосунок не запускали; принтер, мережа, Haspel, DB та ledger не зачіпали.

Після актуальних UI source changes повторно виконано наявний `tests/integration/test_studio_window.py`: **62 passed / exit 0 (10.11s)**. `ruff check src scripts tests`: clean; `mypy src`: 137 source files, no issues. Тестовий модуль проходить у `.runtime/audit-py312`; це не доводить process stability всього suite, hardware чи власницьке приймання. Previous full-suite exit flake stays open.

CSV E16.08 evidence доповнено Candidate10 артефактами, без зміни статусу; після запису перевірено BOM, 118 rows, 5 columns і counts 29/43/45/1. PROJECT_PROGRESS отримав Candidate10 current checkpoint; RELEASE_ACCEPTANCE має append-only Candidate10 запис; USER_GUIDE вказує актуальний тестовий ярлик та попереджає не робити cutover/debit. Реліз залишається NOT READY.

Next: дочекатися ручного UI/DPI огляду користувача; продовжити статичний audit E03.08 щодо точного ланцюга provenance/licensing у комплекті. Не вмикати `UFM_ACTIVE` і не пов’язувати автоматичне списання, доки не буде distributed writer fencing та перевірених job run IDs / redacted reconnect-reprint-replay traces.


## E02.03/E02.06 — структурна перевірка каталогів — 2026-10-30

CSV audit без запуску продукту: Spoolman action contracts мають 318 унікальних ID SA001–SA318, HaspelSync — 211 HA001–HA211; у кожному файлі 10/10 колонок заповнено в усіх рядках, повторів/порожніх значень немає. `FEATURE_PARITY_MAPPING_UK.csv` має 124 унікальні F IDs; потрібні колонки evidence/actions/Qt location заповнені; усі витягнуті SA/HA refs існують у наборах дій (0 dangling). Це структурна, а не семантична/runtime перевірка; E02.03/E02.06 залишаються Partial. Оновлено evidence для обох рядків у чеклісті, BOM збережений, 118 рядків і статусні підрахунки 29/43/45/1 перевірені повторним читанням.



## Candidate10 SBOM / E03.08 — license metadata review — 2026-10-30

Read-only review of the generated CycloneDX 1.7 sidecar: 399 components (376 file, 21 Python library, 2 framework) and `composition=incomplete`. All 21 Python libs carry observed license metadata properties, but `jaraco.classes` and `segno` state `not specified`. PySide6_Essentials/shiboken6 metadata advertises LGPL/GPL alternatives while bundled notices include `LicenseRef-Qt-Commercial`; exact applicable terms/source-offer obligations are unresolved. Node.js notice path and Haspel subset license/provenance paths are present. Root UFM `LICENSE` is absent and `pyproject.toml` has no `project.license`. This is not a full native SBOM or legal assessment; E03.08 remains Partial and no license was selected. Candidate10 remains internal-only. Checklist evidence was appended for E03.08/E16.08 and reopened/validated: BOM, 118 rows, 5 columns, status counts 29/43/45/1.



## E03.07 — focused authority transition and Haspel client contracts — 2026-10-30

Added isolated coverage for the high-risk cutover boundary. `tests/integration/test_accounting_authority.py`: 5 passed / exit 0; checks same-key exact idempotent replay, changed payload conflict, stale optimistic revision with no audit write, mandatory evidence for CUTOVER_READY, and evidence matching before UFM_ACTIVE. `tests/unit/test_haspel_authority_client.py`: 5 passed / exit 0; checks printer path escaping and scoped response, expected-revision transfer response, wrong-printer/boolean revision rejection, sanitized HTTP 409, and rejection of cleartext non-loopback endpoints. Client tests mock the opener and do not use network; command tests use a disposable migrated SQLite fixture. Ruff is clean for both new test files. The first draft of the client tests had an invalid test printer ID containing a space, was corrected, and the final run passed.

Checklist E03.07 evidence now records these tests while preserving Partial. This does not prove a distributed lock, actual Haspel deployment/API compatibility, live cutover/rollback, hardware or debit. No product source, package, account, production DB, printer or network changed. Next: continue static review of legacy writer/authority endpoint scope; keep automatic debit disabled until global fencing and user acceptance exist.


## Candidate10 — поточний Windows UI smoke and visual review — 2026-10-30

Launched only the isolated desktop shortcut `UFM Studio — ТЕСТ Candidate10.lnk`; exact target is the Candidate10 EXE and args direct user state to `D:\UFM_TestCandidate10\Data`. On the current PC, the executable opened with title `UFM Studio · Філамент і принтери`. Read-only navigation observed Filament, Devices, Materials and System screens; all rendered at the current display setting, empty test inventory reported 0 spools/0 printers, and the window closed via Alt+F4. No search/discovery, printer selection, connection wizard, Haspel API, accounting-owner transition, inventory mutation or debit was invoked. The first launch created `Data\data\ufm.sqlite3` (974,848 bytes) and an empty log. A read-only SQLite check returned integrity `ok`, 0 foreign-key violations, 39 tables, schema revision `0007_haspel_authority_connection`. The isolated DB is preserved for owner review. This is a single current-PC smoke/visual check, not clean-machine, owner keyboard/DPI acceptance, printer or release acceptance.

Visual observations: current screen layout showed no obvious truncation; Material/System have substantial whitespace with an empty dataset; Devices text explicitly says physical control commands are not implemented/verified and the inventory screen marks automatic debit in development. Candidate10 remains NOT a release. E14.03, E16.04 and E16.08 evidence was updated without promoting statuses; CSV BOM, 118 rows, 5 columns, counts 29/43/45/1 were revalidated.

Next: owner should manually review Candidate10 at the desktop shortcut, especially keyboard focus and configured DPI, and avoid using Haspel/printer-accounting actions. Continue only source-safe release work until distributed writer fencing, stable run identity, signing/SBOM/legal and hardware/clean-Windows gates are resolved.


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


## E10.06 — focused cancellation/terminal coverage — 2026-10-30

Read-only source/test review, then focused isolated run of existing tests across calculated finalization and job projection: 7 passed. Verified zero-cancel releases reservation without zero ledger, failed partial preserves estimate label/type, duplicate cancel and conflicting terminal events are rejected, late running after terminal is stale/conflicting, and layer/hash/progress regressions do not rewrite facts. This only covers the listed synthetic SQLite fixtures; not every ordering after material/AMS switch or real Bambu provider events. No live printer, network, Haspel service, or production database was used. E10.06 is Partial; automatic debit remains unavailable pending live identity/ingestion, physical spool mapping, global authority fencing, and owner acceptance. Checklist totals: 118 records, UTF-8 BOM, 29 Done /49 Partial /39 Planned /1 In Progress. Next safe step: source/fixture audit E11.04–E11.07 for material-spool split and atomic batch settlement.

## E11.04–E11.07 — multi-spool settlement source evidence — 2026-10-30

Graphify navigation was checked against `src/ufm/application/calculated_finalization.py`, `src/ufm/application/costing.py`, and isolated fixtures. The finalizer validates contiguous material-use coverage, exact evidence and logical-material totals, active spool mount/feed slot/verified RFID scope, and requires explicit audit-confirmed split evidence. It builds decisions, ledger entries, per-spool balance/sequence updates, reservation settlements and terminal job state in a single local UnitOfWork. Focused tests: 5 passed, including two-spool commit, shortage rejection without partial writes, manual confirmation guard, and audit-failure rollback. E11.04–E11.07 reclassified Partial. Gaps: no live Bambu/AMS producer generating segments from physical spool-switch events; no automatic versioned remainder allocation for mg rounding (confirmed integer allocations must already sum exactly); no global cross-process accounting fence or hardware acceptance. No printer, Haspel endpoint, production database or inventory was touched. Checklist reopened and validated: UTF-8 BOM, 118 records, 5 columns, 29 Done /53 Partial /35 Planned /1 In Progress. Next safe review: E11.08 and E12 evidence surfaces/history.

## E11.08 — AMS/unknown material mapping evidence — 2026-10-30

Graph-guided source review verified against UFM mapping/topology/finalization code and checked-in isolated fixtures. Distinct logical materials survive even when physical tool mapping can overlap; a confirmed spool swap atomically rotates the usage segment. External slots are printer-scoped; unknown assignments remain unresolved/deduplicated and cannot close another slot’s usage. Seven focused existing integration checks passed. E11.08 is Partial; no real printer or AMS was used, and model-specific multi-AMS/color, live rollover/offline changes, and producer-to-segment wiring remain unaccepted. No live stock or DB was modified. Revalidated checklist: UTF-8 BOM, 118 rows, 5 columns, 29 Done /54 Partial /34 Planned /1 In Progress. Next: inspect E12.01–E12.03 for actual Qt history and reconciliation surfaces versus the persisted job/evidence model.

## E12.01–E12.03 — UI history and unresolved booking boundary — 2026-10-30

Verified Qt/backend source: `StudioWindow.show_history()` is per-spool accounting history combining ledger rows, weight measurements and cost summary; estimated entries show a translated estimate label and only validated job/receipt/hash-prefix/plate details. Existing focused UI checks: 4 passed. There is no durable Qt print-job/receipt history or full decision/exceptions explanation because production receipt ingestion/projection is not wired into a composition root. Haspel authority UI does display observed pending/uncertain counts and refuses UFM ownership transfer while counts are nonzero; no separate UI inspect/resolve/retry workflow exists, so E12.03 remains Planned. E12.01/E12.02 changed to Partial. No real Haspel or printer was contacted. Checklist: UTF-8 BOM, 118 rows, 5 columns, 29 Done /56 Partial /32 Planned /1 In Progress. Next: E12.04–E12.07 compensation, late weighing, local API/export and action parity audit.

## E12.04–E12.07 — correction, weighing cutoff, export and parity — 2026-10-30

Source review plus 10 focused existing isolated integration checks: 10 passed. Compensation is a linked reversal preserving the original transaction; measurement acceptance is cutoff/idempotency/audit guarded; late print or overlapping weigh evidence requires reconciliation rather than silent double debit; Qt has formula-safe CSV inventory and cost report export. E12.04–E12.06 classified Partial. No UFM HTTP API/server/router entry point found; the current Spoolman integration is an outbound client. E12.07 stays Planned until the full feature/action registry is verified against Qt handlers/backend and per-action acceptance; a filled catalog is not runtime parity. No live Haspel/printer/production data used. Checklist validated: BOM, 118 records, five columns, 29 Done /59 Partial /29 Planned /1 In Progress. Next: audit E12.07 action parity registry with source references; record explicit implemented, absent, unsafe and deferred actions.

## E12.07 — action parity register boundary — 2026-10-30

Static reconciliation of `FEATURE_PARITY_MAPPING_UK.csv`, the inventory/system UI action registries, and HaspelSync action contracts: inventory registry has 22 controls (18 verified, 4 QR export/print actions acceptance pending); system registry has 7 (2 prior acceptance, 1 partial UI acceptance, 4 pending). The 124 feature rows and 211 HaspelSync action contracts remain indexes/contracts, not evidence that every action is available/equivalent in Qt. E12.07 is Partial. Remaining: finish pending controls, map all legacy actions to implemented/deferred/absent with source/acceptance evidence, obtain owner/hardware acceptance when needed. No printer used. Checklist: UTF-8 BOM, 118 rows, 5 columns, 29 Done /60 Partial /28 Planned /1 In Progress. Next safe work: E13.01–E13.06 printer-control capability/command audit; unverified physical actions must stay disabled.

## E13.01–E13.06 — physical printer-control source limits — 2026-10-30

Confirmed the `PrinterControl` pause/resume/cancel methods are only a port contract; both current providers report these capabilities false. Temperature is observed, not set; no concrete fan, filament load/unload, macro, motion/homing, upload, or print-start handler was found under `src/ufm`. Bambu and local HTTP providers report camera unsupported; no stream or job queue controller exists. All E13 rows remain Planned, with exact observed limits recorded in the checklist. No printer was contacted. Model/firmware hardware acceptance is absent; commands must remain unavailable until implemented and validated. Checklist remains 118/BOM, 29 Done /60 Partial /28 Planned /1 In Progress. Next safe review: E14 UI/localization/lifecycle and release gates.

## E14.01–E14.06 — UI/localization/lifecycle/release-surface audit — 2026-10-30

Candidate10 current-PC visual evidence exists only at one display configuration. Translation catalogs are structurally complete (186 matching nonempty keys each); four locale unit checks and the monitor-close UI test passed (5 focused selections total). `closeEvent` defers shutdown until active workers/monitor are idle. Existing guide and bounded allowlisted safe-log viewer exist, but no consented redacted diagnostic export package was verified. E14.01–E14.06 are Partial; unresolved acceptance includes owner, populated UI, full DPI/keyboard/accessibility, large lists/in-flight dialogs/shutdown data preservation, complete feature parity and diagnostic bundle review. No tests were added; no hardware/device used. Checklist: BOM, 118 rows, 5 columns, 29 Done /65 Partial /23 Planned /1 In Progress. Next: audit E15 cutover requirements; do not exercise real ownership transfer without owner and cross-process fencing.

## E15/E16 — cutover blockers and Candidate10 reconciliation — 2026-10-30

Three existing isolated checks passed: local finalization crash-before/after-commit recovery, two concurrent writers yielding one finalization, and verified database backup. E15.04/.05 are Partial only; no live Haspel writer fencing, dual-run, lost HTTP response acceptance, physical AMS comparison, install restore/rollback acceptance, live cutover or first postings. E15.01–.03/.06/.07 remain Planned. Reconciled stale release checklist references from Candidate9 to latest Candidate10: 376 files, executable SHA-256 `D398AA91BEAD3495FF1B78DF1775CCB2E4A16B85CD421FAC54F64562B0D0BF02`, Authenticode NotSigned, CycloneDX 1.7 with 399 components and incomplete composition; test shortcut has a separate data dir. The only installer artifact previously recorded is an earlier Candidate4; Candidate10 is a portable internal test, not a release installer. Clean Windows, full restore/update rollback, UFM license decision, full SBOM/legal review, signing, deterministic full-suite exit and owner/hardware acceptance remain open. No production DB, printer or cutover touched. Checklist: 118 rows, BOM, 29 Done /67 Partial /21 Planned /1 In Progress.

## Release source provenance caveat — 2026-10-30

Read-only filesystem check found no root `.git` under `D:/Bot/Universal_Filament_Manager`; `linked-stack/haspelsync` retains its own Git directory. Root source revision and git diff provenance cannot be verified from this checkout. No repository initialization, commit, push, or source mutation was performed. Treat source provenance/version stamping as an additional E16.05 release limitation. Checklist BOM/118 rows/statuses 29/67/21/1 revalidated.

## Full-suite rerun — current Candidate10 source — 2026-10-30

Ran existing full suite in locked Python 3.12.14: `python -m pytest` — 635 passed, exit 0, 80.73 seconds. No tests added. The suite uses checked-in fixtures/temp SQLite; no printer or production database. This is one successful full-source run. The previously recorded intermittent exit 1 after a green summary remains unexplained, so deterministic process exit is not established. Updated E16.08 evidence only; release remains NOT READY. Checklist revalidated: UTF-8 BOM, 118 rows, 5 columns, 29 Done /67 Partial /21 Planned /1 In Progress.

## Release dashboard reconciliation after current full-suite run — 2026-10-30

Reconciled the current PROJECT_PROGRESS_UK.md checkpoint with the latest E10–E16 source/test audit, RELEASE_ACCEPTANCE_UK.md, and checklist. The old dashboard next-action still pointed to E14 UI review although E14.01–.06 and the E15 cutover review had since been completed as Partial/Planned evidence; replaced only the current summary block and retained all historical checkpoint entries. The new top summary records the latest 635-pass/exit-0 full-suite run as one successful run, preserves the unresolved prior exit-1 observation, and clearly says NOT READY. No checklist status was promoted and no code, build, account, printer, or database changed in this step.

Cross-check: checklist UTF-8 BOM, 118 records, five columns, status totals 29 Done /67 Partial /21 Planned /1 In Progress; E16.08 contains the current full-suite result. Candidate10 remains unsigned, incomplete-SBOM, internal-only. Remaining evidence/decisions include root source provenance, UFM/legal license and complete SBOM, signing and release installer acceptance, clean-Windows/update/rollback, stable job-to-spool source identity and cross-process Haspel fencing, hardware and owner UI acceptance. Next: continue source-verifiable E03.08/E16.05 package/provenance requirements; do not claim release readiness until external gates are accepted.

## E03.08/E16.02/E16.05 — fail-closed public installer checks — 2026-10-30

Static source review found build_installer.ps1 accepted the intentionally incomplete CycloneDX sidecar and allowed signing parameters to be omitted. Hardened the public installer path: thumbprint and RFC3161 timestamp are required; the bundle EXE must have a valid Authenticode signature from that exact certificate; SBOM must state complete metadata/composition, include a project license and ufm:license-review=approved; and the generated installer is checked for a valid signature from the same thumbprint. The current SBOM generator still emits incomplete/observed-only inventory, which means installer generation now fails closed until the real inventory/legal gates are resolved. Updated RELEASE_ACCEPTANCE_UK.md and STUDIO_USER_GUIDE_UK.md so their build guidance matches; updated E03.08/E16.02/E16.05 evidence without promoting statuses. PowerShell AST parse succeeded. No build, installer, existing candidate, production data, or device was touched. CSV reopened after write: UTF-8 BOM, 118 records, 5 fields, totals 29/67/21/1. Next: source-provenance/SBOM completeness and owner/legal decisions; do not bypass the gate for internal test packaging.

### E16.02 version gate follow-up — 2026-10-30

Added a stable-version requirement to the fail-closed installer builder: only X.Y.Z is accepted, excluding the current Candidate10 0.1.0.dev0. Updated release/user guidance and checklist evidence without changing status. No build or installation was performed.

## E16.05 — deterministic source-input snapshot metadata — 2026-10-30

Implemented source provenance in new folder manifests: a sorted per-file path/size/SHA-256 inventory covering src/ufm, build/packaging inputs, pyproject.toml/uv.lock/notices and the exact Haspel calculation/shared/license files consumed by the sync script; a canonical source-tree SHA-256; and optional root Git revision/clean state. verify_manifest recomputes and compares this snapshot when present while allowing historical schema-1 manifests without the new field. The installer now requires a clean 40–64 hex root Git revision and valid source snapshot metadata, so it fails closed in the present checkout (no root .git). Candidate10 remains untouched and cannot satisfy the new gate. Isolated tempfile manifest generation/verification passed (one-file bundle, 177 source inputs, no Git revision), Ruff check and PowerShell AST parse passed. This is source traceability, not build reproducibility, license approval, complete SBOM, or runtime acceptance. No test files added, no build/install, no production data/device changes. Checklist remains UTF-8 BOM, 118×5, 29/67/21/1. Next: root source-control provenance and the blocked full-license/SBOM/installer gates.

## E16.08 — second consecutive full-suite process exit — 2026-10-30

Repeated the existing full suite in the locked Python 3.12.14 environment: 635 passed, exit 0, 79.55 seconds. The immediately preceding full run was also 635 passed/exit 0 in 80.73 seconds, so there are now two consecutive clean exits. The historical post-summary exit 1 remains unexplained; two successes do not establish deterministic teardown. Existing isolated fixtures/temp SQLite only; no printer, network or production database. E16.08 remains Partial and release remains NOT READY. Checklist reopened/validated with BOM, 118×5 and 29/67/21/1.

## E16.08 — reproduced native Qt teardown failure and split-suite evidence — 2026-10-30

Three recent full-source suite runs each printed 635 passed. Exit results were 0 (80.73 s), 0 (79.55 s), then 1 after summary (79.20 s). A further full run under Python faulthandler exited -1073741819 after 635 passed and reported a Windows fatal access violation with no Python frame. Split diagnostics passed independently: Studio UI module 62/exit 0; remaining suite with the Studio module ignored 573/exit 0. Windows Application Error log recorded two recent python.exe faults in Qt6Core.dll, exception c0000005 (access violation); no source stack was available. This localizes the unresolved E16.08 instability to native Qt teardown in the combined test process, not failed assertions; it does not identify a fix or prove product-runtime instability. No code was changed in this diagnostic stage, and no printer/network/production DB was touched. E16.08 stays Partial; release remains NOT READY. CSV reopened with BOM, 118×5 and counts 29/67/21/1. Next: avoid masking the native failure; use a native dump/debugger or isolate the Qt teardown path before claiming clean release verification.

## E16.08 — isolated Qt teardown failure on alternate platform plugin — 2026-10-30

A further isolated run of tests/integration/test_studio_window.py with QT_QPA_PLATFORM=minimal printed 62 passed, then exited -1073741819. The same module had exited 0 under the default offscreen platform. The latest Windows Application Error query shows three recent python.exe access violations: Qt6Core.dll twice and Qt6Widgets.dll once, exception c0000005. Therefore this is not limited to the mixed full-suite process; isolated UI shutdown can also fail intermittently. No source/product code was changed. The native stack remains unavailable, so do not change application runtime or mask the runner exit without a dump/debugger diagnosis. E16.08 remains Partial; release not ready.

## E16.08 — available crash-dump evidence — 2026-10-30

Read-only Application Error events identify Qt6Core.dll/Qt6Widgets.dll access violations in Python after green pytest summaries. Three recent python.exe crash dumps exist under the standard local CrashDumps directory; only file count and process-specific filter were checked, and dump contents/names were not read. No WinDbg/cdb command or standard Windows Kits debugger binary was present. The dumps are private diagnostic material; preserve them locally and do not attach them to a public report. Root cause requires a native debugger/symbols that are not currently available. No source or runtime changed in this check.

## E05.05 / E12.07 — QR action UI-path acceptance — 2026-10-30

Added parameterized UI acceptance in `tests/integration/test_studio_window.py` for single SVG export, batch SVG export, single print, and batch print, including dialog-cancel cases (8 cases total). Export assertions parse the SVG, check the canonical spool ID and labels, verify the batch creates separate files, and confirm cancellation creates no output. Print assertions use a fake `QPrinter`, dialog, painter and SVG renderer: they verify one rendered label per spool/page, `newPage` behavior, and no render on print-dialog cancel without opening a physical printer. The test workspace uses `tmp_path` and its temporary SQLite database. Results: `.venv312\Scripts\python.exe -m pytest tests/integration/test_studio_window.py -k qr_ -q` — 8 passed, 62 deselected; Ruff check clean. Updated the four QR rows in `UFM_STUDIO_INVENTORY_ACTION_REGISTRY_UK.csv` with test evidence; E05.05/E12.07 checklist statuses remain Partial because physical printer output and owner visual acceptance remain outstanding. No real printer, product candidate, production database, or source HaspelSync state was used.

Next: continue the highest-priority safe partial implementation; do not claim physical QR print acceptance. E16.08 Qt native teardown diagnosis still needs WinDbg/cdb and private crash-dump stack analysis. E12.03 remains unimplemented for Haspel pending/uncertain bookings because the current authority endpoint exposes counts only and there is no safe source-side resolve/retry contract; do not retry an unknown HTTP result or write Haspel journals directly.


## E12.03 — safe HaspelSync pending/uncertain booking review in UFM — 2026-10-30

Implemented a bounded HaspelSync booking reader in the existing authority client. It validates at most 100 records, exact selected-printer scope, hash IDs, status/terminal state, integer identifiers/timestamps, finite positive grams, and optional resolution metadata. Added StudioBackend access through the OS credential store and a localized review dialog in the accounting-authority wizard. The operator must explicitly choose “already debited” or “not debited”, supply a 1–500 character note, and confirm that this records only a HaspelSync journal outcome; UFM does not change Spoolman stock. The client re-reads before resolution, makes at most one POST, and after a lost/ambiguous write performs GET-only confirmation. If it cannot confirm, it raises a distinct unknown-outcome condition and tells the operator not to resend blindly. HaspelSync source and data were not modified.

Verification: `pytest tests/unit/test_haspel_authority_client.py tests/integration/test_studio_backend.py -q` — 14 passed plus 4 malformed-input subtests; Ruff clean. A focused translation/action-registry/QR UI selection yielded 10 passed; UI owner/live-service acceptance is still pending and no Haspel endpoint was contacted. E12.03 changed from Planned to Partial, not Done. Checklist remains 118 rows, 5 columns, UTF-8 BOM; updated totals are 29 Done / 68 Partial / 20 Planned / 1 In Progress.

Next: inspect the UI path for edge cases and add an isolated dialog interaction acceptance only if it can use mocks/temp state. Then continue the E16.08 native Qt teardown diagnosis; do not run or use WinDbg/dumps unless tools are available, and do not claim public-release readiness.


### E12.03 follow-up — system-action registry and latest focused verification — 2026-10-30

Added the booking-review control to the Studio system-action registry and an isolated source/catalog contract check. The first run found that the registry control ID is not itself a translation key; the assertion was corrected to check the actual `authority_review_bookings` key and the test then passed. Latest focused command selected client, backend/UI catalog, registry and QR paths: 21 passed, 65 deselected, plus 4 malformed-input subtests; Ruff clean. This does not exercise the nested modal against a live service. E12.03 remains Partial.


## E14.06 — consented minimal diagnostics export — 2026-10-30

Added a pure bounded export builder and a System-page action. It reads only the existing `ufm.log` tail (maximum 512 KiB), processes at most 300 rows, validates timestamp/level/event, and emits UTC time, allowlisted level/event, omitted/included counts, creation time and SHA-256 of canonical event data. Arbitrary `fields` are discarded, malformed rows are counted only, and the bundle contains no host/path/database/settings/identifier values. UI shows the exact content boundary and digest before explicit consent, then asks where to save JSON through `QSaveFile`; export stays local and no upload exists.

Verification: `pytest tests/unit/test_diagnostics.py -q` — 3 passed. Focused UI/translation/system-registry selection — 7 passed, 68 deselected. Ruff clean. The registry has a new `export_diagnostics` action; E14.06 remains Partial pending owner review of the preview and saved artifact. The redaction design intentionally excludes all dynamic fields instead of assuming pattern-based scrubbing can recognize every secret.

Next: build an isolated new portable test candidate so the owner can inspect both the Haspel booking review and diagnostics consent/export. Keep its data directory separate. Then continue only source-verifiable release gates; E16.08 still needs native debugger/symbols for the preserved private dumps, and E03.08/E16.05 remain blocked on root provenance, chosen license/legal review, complete SBOM and signing certificate. No live Haspel, production database, printer or upload was used.

## Candidate11 docs reconciliation and next release gate — 2026-10-30

Reconciled `docs/STUDIO_USER_GUIDE_UK.md` with the latest internal bundle: the desktop test shortcut is Candidate11 and uses the isolated `D:\UFM_TestCandidate11\Data` directory. Clarified that it is unsigned, has no Candidate11 SBOM sidecar because generation failed closed on `sbom.lock_package_missing_or_ambiguous`, and is not a release or clean-Windows acceptance. Updated the current progress next-action to investigate a fresh build under the dedicated `uv.lock`-aligned `.venv-release`; the Candidate11 bundle/data remain untouched. This is a documentation-only correction; no UI/runtime/test/printer/database operation was performed. Next: inspect the existing locked release environment/build script, and only if its preflight is consistent, create a new isolated candidate and verify its manifest/SBOM. Do not reuse Candidate10's SBOM or loosen the generator's fail-closed check. E16.08 native Qt teardown still needs a debugger/symbols and private dump stack; release remains NOT READY.


## E08.01 / E08.02 / E08.04 — локальний перегляд 3MF та G-code у Studio — 2026-10-30

Graphify-навігація вказала на `sliced_files.py`, `gcode_extrusion.py` та дію-проєкцію Studio; прямий перегляд підтвердив, що парсери існували, але користувацького локального шляху не було. Додано `inspect_3mf_file_for_local_review`: файл читається максимум на межу 128 MiB + 1 байт, SHA-256 обчислюється з того самого буфера, який передається на існуючий суворий 3MF parser; в обліковому API збережено вимогу pinned `expected_sha256`. Додано `inspect_gcode_file_for_local_review`: локальний `.gcode` обмежено 64 MiB, exact-byte digest і передача в існуючий whitelist `marlin-linear-v1`; невідомі/вендорські команди відхиляються, вміст не виконується.

У вкладці «Пристрої» додана одна дія, яка виносить аналіз у штатний QThread worker. 3MF просить явний номер plate; результат показує SHA-256, parser version, логічні канали й оцінку грамів. G-code показує інструмент/шар і свіжу довжину екструзії в міліметрах, не переводить її в масу. Обидва сценарії явно повідомляють, що файл не прив’язаний до job, не підтверджує фактичну витрату й не змінює склад. Джерельний шлях і вміст не виводяться у summary/error. Action registry оновлено до 23 дій, додано en/uk переклади.

Перевірка: `pytest tests/integration/test_studio_window.py tests/integration/test_gcode_extrusion.py -k "translations_have_matching_named_fields or inventory_action_registry_matches_ui_handlers_and_test_evidence or gcode_extrusion" -q` — 9 passed, 24 subtests passed, 70 deselected. Ruff для змінених модулів чистий після сортування імпортів; `compileall` пройшов. Тест/парсер ізольовані від мережі, принтерів і production-БД. Це не runtime UI acceptance, не перевірка Bambu-vendor G-code і не масова оцінка. Candidate12 не перебудовувався. Checklist зберіг UTF-8 BOM, 118 рядків/5 колонок і статуси 29/68/20/1.

**Що лишається:** E08.01 — зберігати/прив’язувати артефакт до точного job+plate та перевірений FTPS; потрібно також узгодити retention/backup для артефактного store. E08.02/.04 — непідтримані vendor dialects і сумісність; no silent fallback. E09.01 — G-code не перетворюється на масу/ledger evidence. Автоматичну політику та live finalization не підключати. Наступне: source trace print-job lifecycle, slice-binding port, backup/restore та обмеження існуючого UI selection; далі — безпечний наступний реалізований пакет.


### E08.01 follow-up — перелік валідованих 3MF plates — 2026-10-30

Покращено локальний preview flow: `list_3mf_plates_for_local_review` перевіряє обмежений ZIP directory, XML metadata, унікальні plate indexes, логічні material facts і наявність відповідного `Metadata/plate_N.gcode`; на UI після завершення worker відкриває список лише доступних plates. Другий worker читає файл для вибраної пластини й повторно проходить повну integrity/hash перевірку. Якщо діалог скасовано, ні parse другого етапу, ні persistence не відбувається. Перелік metadata plates не вважається підтвердженням виконання файлу.

Ізольована перевірка: 23 passed, 90 subtests passed, 70 deselected на існуючих translation/action-registry, G-code та 3MF contract наборах; source smoke на HaspelSync fixture показав 1 валідований plate і 2 logical materials, окремий підтримуваний Marlin sample дав один extrusion bucket. Ruff чистий. Живий UI/owner, vendor G-code, printer/FTPS, job binding та accounting acceptance не перевірялися. Checklist BOM збережений; статуси без змін — 29/68/20/1. Candidate12 не містить source-змін.

## Candidate13 — portable internal build and visible local-review action — 2026-10-30

Зібрано Candidate13 у новій папці `D:\UFM_TestCandidate13\UFM Studio` після E08 read-only file-review змін. Незалежний повторний `verify_manifest` перевірив 377 записів; у каталозі 378 файлів разом із manifest. EXE SHA-256 `6053106251974122F63CF06781E94805A84BD2093A14E7D7C5A90AF36372E664`, версія `0.1.0.dev0`, Authenticode `NotSigned`. CycloneDX 1.7 sidecar SHA-256 `46DCE4D2B7B72D2A542DC62805714AEF45B5D946D0B86B98E17CC929F2AD351C`, 400 компонентів, `composition=incomplete`; 21 runtime distribution зібрано з lock-aligned `.venv-release` CPython 3.12.15. Git revision у manifest відсутній, оскільки корінь UFM не є git checkout.

Ярлик `UFM Studio — ТЕСТ Candidate13.lnk` перевірений через COM read-back: він запускає цей EXE з `--data-dir "D:\UFM_TestCandidate13\Data" --locale uk-UA`. Candidate13 відкрито у видимому вікні з порожнім ізольованим робочим простором; screenshot вкладки «Пристрої» підтверджує наявність нової кнопки «Перевірити локальний 3MF/G-code». Це лише UI presence/current-PC smoke, не перевірка власницького сценарію з реальним файлом, DPI/accessibility, hardware чи публічного пакета. Штатні користувацькі UFM ярлики й Candidate12 дані не змінювалися.

Публічний реліз залишається NOT READY: збірка непідписана, SBOM неповний, версія development, source Git provenance відсутній, ліцензію та legal review не затверджено, немає чистої Windows/install/update/rollback acceptance; живий hardware/owner acceptance також відсутній. Candidate13 не використано для списання або підключення до принтера. Наступний крок: перевірити source lifecycle job → точна plate binding → backup/restore та виконувати тільки безпечну зберігальну частину; не прив’язувати локальний preview до accounting authority без стійкої job identity, reviewed mapping і global Haspel writer fencing. Checklist status totals лишити 29 Done / 68 Partial / 20 Planned / 1 In Progress.

### E08 runtime wiring trace — core існує, але до Studio не підключений — 2026-10-30

Graphify UFM map використано для навігації по application/integration boundary; твердження підтверджено у живих джерелах. `VerifiedSliceBindings` (`src/ufm/application/slice_binding.py`) і `SliceArtifactStore` (`src/ufm/integrations/slice_artifact_store.py`) мають immutable hash/plate store, audit binding і тести (`tests/integration/test_slice_binding.py`, `test_slice_binding_accounting.py`, `test_slice_artifact_store.py`). Це вже реалізований core, не слід переписувати чи називати відсутнім.

Однак пошук усіх посилань у `src/ufm` показав відсутність викликів цих сервісів із `StudioBackend`, `bootstrap` або UI; runtime реєструє лише загальний локальний read-only preview. `ReceiptIngestion` та `ProjectionDrain` теж мають реалізації/tests, але не мають runtime caller, тому в наявному вікні немає producer шляху, який створює перевірену довговічну job identity і викликає binding. Окремо `StudioBackend.backup()` передає тільки SQLite файл у `create_snapshot`; `sqlite_snapshot.py` створює bundle з `database.sqlite3` і `manifest.json`, без зовнішнього directory cache. Отже збережені binding/audit дані без архіву не забезпечують повне backup/restore.

Наступний залежнісний блок: встановити наявну runtime receipt/job adapter boundary і перевірити, чи поточні provider snapshots містять достатню стійку occurrence identity; після цього спланувати wiring в ізольований DataDir, а backup bundle розширювати лише разом з явним artifact root і restore verification. Не створювати ручні jobs за назвою файла, не списувати на основі preview та не приєднувати UI до обліку без printer/source provenance й глобального Haspel writer fencing. Статуси E08.01/.02/.04 не підвищено; E08.06 core лишається виконаним.


## 2026-10-30 — Candidate14 UI contrast fix and visual verification

Fixed the nearly invisible checkboxes in the material-profile dialog. `src/ufm/ui/studio_window.py` now defines explicit `QCheckBox::indicator` geometry, outline, hover, checked and disabled styling across themes; the checked mark is a bundled 16×16 PNG at `src/ufm/ui/assets/checkbox-checked.png`. Added `test_checkbox_indicators_are_explicitly_visible_in_both_themes`. Verification: full `tests/integration/test_studio_window.py` — 73 passed/exit 0; Ruff on the changed source and UI test — clean. This does not clear the historical intermittent Qt native teardown AV in full suite.

Candidate14 was built in a unique internal output directory, launched with isolated `D:/UFM_TestCandidate14/Data`, and visually inspected on this PC. Light and dark material dialogs show discernible unchecked boxes; the checked mark was also visibly confirmed in the light theme. The dialog was canceled and no material profile was saved. Independent bundle manifest verification: 374 files. EXE SHA-256 `A167E3EEC91C65002294F9A874C963E62BB835B0DD8BB2737C7CCA2F233921FD`. Candidate14 is unsigned, `0.1.0.dev0`, and has no complete release SBOM; it is test-only. UI review covers one screen configuration only; DPI matrix, full keyboard/focus/accessibility, resize and owner acceptance remain open. No printer, live Haspel, network accounting or production data was used.

Checklist: retained UTF-8 BOM, 118×5 schema and unchanged status counts 29/68/20/1; added scoped evidence only to E14.03, E16.05 and E16.08. Public release remains NOT READY.

**Resume:** run the existing full pytest suite and retain exact exit status, then trace the provider occurrence identity → durable receipt → managed job → verified slice-binding path and separately design/verify artifact backup/restore. Maintain fail-closed accounting until exact run identity and global Haspel writer fencing are proven.


## 2026-10-30 — Candidate14 shortcut, guide and full-suite result

Created a new desktop shortcut `C:\Users\-PC-\Desktop\UFM Studio — ТЕСТ Candidate14.lnk` without overwriting the existing UFM or Candidate shortcuts. COM read-back confirms target `D:\UFM_TestCandidate14\UFM Studio\UFM Studio.exe`, arguments `--data-dir "D:\UFM_TestCandidate14\Data" --locale uk-UA`, and candidate folder as working directory. Updated `docs/STUDIO_USER_GUIDE_UK.md` to point users to Candidate14 and describe its test-only status. Candidate14 remains unsigned/development-version and has no complete SBOM; it is not a release.

Ran the full existing suite after the UI change: `.venv312\Scripts\python.exe -m pytest -q` — 654 passed, 489 subtests passed, exit 0 in 81.52 s. Keep the prior native Qt teardown access violation evidence open; one clean pass is not proof of deterministic test-process exit. Checklist stays BOM/118×5/counts 29/68/20/1; E14.03 and E16.08 received scoped evidence only.

**Resume:** inspect exact event semantics and provider restart identity in source/tests before any automatic accounting wiring. Existing provider event `source_epoch` and sequence reset on adapter recreation; no durable cross-restart occurrence identity is established. Do not infer a print-run identity from filenames, UI snapshots, or local event counters. Backup does not include the external artifact store, but that store is currently not runtime-wired; first establish the intended persistent artifact root/API before changing backup format.


## 2026-10-30 — E14.03 Qt scale-factor visual sweep

Captured isolated empty Filament page from current source at `QT_SCALE_FACTOR=1.0`, `1.25`, `1.5`, `2.0`, each in a separate Candidate14 data directory, using the built-in offscreen capture. Outputs are `D:/UFM_TestCandidate14/Review/source-studio-{100,125,150,200}-review-20261030.png` at 1360×860, 1700×1075, 2040×1290 and 2720×1720. Manual image inspection: controls grow proportionally, the main page has no apparent horizontal clipping, and the detail pane supplies vertical scrolling. This validates only a Qt-scale simulation of the empty Filament tab; it is not Windows display scaling on physical monitors, a 100/125/150/200 DPI acceptance matrix, dialog behavior at each scale, keyboard/focus, accessibility or owner sign-off. Candidate14 still has the separate interactive light/dark checkbox-dialog observation. E14.03 remains Partial. No production paths were used.


## 2026-10-30 — E14.03 empty Materials guidance

The Candidate14 live review exposed an empty Materials tab with two blank tables and no first-step guidance. Added a `QLabel` using the existing localized `no_profiles` text; it is shown only while the profile catalog is empty, hidden after a profile is created, and hidden when the database refresh fails. The existing empty-catalog UI regression now asserts the visibility transition and no stock/profile mutation before creation. Focused selection including the checkbox theme regression: 2 passed, 71 deselected; Ruff clean. No candidate rebuild yet: Candidate14 does not contain this latest source change, so rebuild a new isolated candidate before owner retest. E14.03 remains Partial.



## 2026-10-30 — E16.08 reproduced combined-suite native exit failure

After the empty Materials guidance change, full `.venv312\Scripts\python.exe -m pytest -q` printed 654 passed, 489 subtests, then returned exit 1 in 81.42 s. The Application log’s Event 1000 at 23:03:50 +02 identifies Python 3.12.14 and `.venv312\Lib\site-packages\PySide6\Qt6Core.dll`, exception `0xc0000005`; Event 1001 is APPCRASH. Isolated runs after the same code change passed: `tests/integration/test_studio_window.py` 73/exit 0 (11.03 s); remainder `--ignore=tests/integration/test_studio_window.py` 581 passed + 489 subtests/exit 0 (71.60 s). This narrows the observed failure to combined native Qt/test-process teardown, but provides no stack and no root cause. Do not mask the exit code or call release verification clean; do not open private crash dumps without an available debugger. E16.08 remains Partial.



## 2026-10-30 — Candidate15 current internal build and shortcut

Built Candidate15 in a new destination without overwriting Candidate14 or the installed app. PyInstaller 6.22.3 / Python 3.12.14 / Windows 11; used the existing pinned Node v24.22.1 and existing generated Haspel calculation resources, without running any HaspelSync mutation/sync. PyInstaller emitted optional hidden-import warnings for tzdata, pysqlite2 and MySQLdb; build succeeded. Copied notices/icon, collected 22 runtime distribution notice records and verified manifest: 374 bundle files. EXE SHA-256 `3D7B92A2117FEDCDBC3EAA23D69BDFC16B6B77FE686E76CA353FB83A4BC9E71B`, version `0.1.0.dev0`, Authenticode `NotSigned`; no complete SBOM sidecar. The bundled 218-byte checkbox asset is present.

Created desktop shortcut `C:\Users\-PC-\Desktop\UFM Studio — ТЕСТ Candidate15.lnk`; COM read-back verifies the Candidate15 executable, `--data-dir "D:\UFM_TestCandidate15\Data" --locale uk-UA`, and isolated working directory. Candidate15 launched visibly. System screen showed `D:\UFM_TestCandidate15\Data\data`; Materials showed the new localized guidance for empty profiles. Screenshot: `D:\UFM_TestCandidate15\Review\materials-empty-candidate15-20261030.jpg`. Candidate14 window opened by this task was closed; Candidate13 pre-existing window was left alone. Old build folders/shortcuts were not removed because the previous cleanup action was rejected; do not bypass with another deletion route.

Updated the user guide/checklist/progress. Checklist remains BOM, 118×5 and 29/68/20/1; E14.03/E16.05/E16.08 remain Partial. The current latest full suite still has a combined-process exit 1 from native QtCore AV after a green summary, while split UI/remainder runs each exited 0. Public release is not ready.

**Resume:** keep Candidate15 as current manual-test candidate. Continue diagnosis only with an available native debugger; otherwise preserve the unresolved Qt exit flake as a release blocker and move to the next source-verifiable dependency. Do not enable automatic stock accounting without durable print-run identity and global writer fencing.

## 2026-10-30 — Candidate15 all-tab review; Bambu occurrence identity remains unproven

Quota at start: 68% 5-hour and 27% weekly remaining; recheck between stages. Graphify query on the enriched Bambu/UFM graph identified the provider metadata test and provider DTO; verified against live source and fixtures. `BambuLanProvider` creates a random `source_epoch` in each instance, `_event_sequence` starts from zero, and `subscribe_events()` serializes snapshots. It carries `task_id`, `subtask_id`, and `job_id` to `PrintJobSnapshot` but leaves `provider_run_key=None`. Tests `test_reported_ids_are_preserved_as_metadata_not_run_identity` and `test_two_configured_printers_keep_credentials_events_and_slots_isolated`: 2 passed, 26 deselected. This does not prove any vendor field unique across reconnects or repeated same-file prints. No device/network was contacted; keep auto-accounting fail-closed and do not synthesize identity from local filename, time or event counter.

Used Computer Use to inspect the running Candidate15 window (exact process path `D:\UFM_TestCandidate15\UFM Studio\UFM Studio.exe`) without activating mutating buttons. All four tabs were visible at 1360×860. Filament shows empty summaries/search/table and disables spool actions until selection; Devices visibly describes scan candidates, read-only status and explicit monitor consent; Materials displays empty-catalog onboarding; System labels the build test-only, lists public-release gaps and shows `D:\UFM_TestCandidate15\Data\data`. The UI is readable at this one current-PC configuration; no owner signoff, physical display DPI, keyboard/accessibility or broad dialog matrix. Candidate15 left open at Filament; pre-existing Candidate13 left intact.

Guide `docs/STUDIO_USER_GUIDE_UK.md` had drifted to Candidate14 and Candidate12. Updated current shortcut/path to Candidate15 and historical candidate list; no binary was rebuilt because source behavior did not change. Added evidence only to E08.01 and E14.03, leaving both Partial. Checklist remains BOM/118 rows/5 columns; verify status counts as `29 Done / 68 Partial / 20 Planned / 1 In Progress`. No code changes or destructive cleanup. `cdb`, `windbg`, and `WinDbgX` were not available on PATH; E16.08 native Qt teardown AV remains unresolved and must not be described as clean.

**Resume:** next audit E08.07 compatibility matrix and inspect the artifact root/backup boundary. Use existing fixtures and source; do not change user databases. Do not wire `ReceiptIngestion` or `ProjectionDrain` to current snapshots until durable run identity and global Haspel writer fencing are independently established. Public release remains NOT READY.

## 2026-10-30 — E08.07 support matrix and parser checks

Updated `VERIFIED_SLICE_INTAKE_UK.md` after re-reading parser code and the current tests. It now distinguishes: (1) bounded read-only sliced 3MF metadata intake, verified against 11 HaspelSync XML fixtures and one real `p2s_two_colours.gcode.3mf`; (2) explicit standalone `marlin-linear-v1` text G-code length estimate only; (3) unknown/vendor dialects rejected, `.bgcode` unsupported, FTPS retrieval absent. `SliceArtifactStore`/`VerifiedSliceBindings` are separate durable core, while Studio runtime wiring and artifact backup/restore remain missing. No grams or accounting from standalone G-code; no purge coverage or hardware support claim. Existing parser selection ran: `.venv312\Scripts\python.exe -m pytest tests/contract/test_sliced_files.py tests/integration/test_gcode_extrusion.py -q` => 21 passed/90 subtests, exit 0. Ruff on both source modules and test files: clean. Checklist evidence for E08.04/.07 expanded, statuses remain Partial.

Found and fixed documentation drift: user guide still directed manual testers to Candidate14 and called Candidate12 the portable internal build. It now identifies Candidate15 as current and lists older candidate shortcuts without changing them. Visually inspected all four Candidate15 tabs through Computer Use at 1360×860 and left it open on Filament; this is not owner acceptance. Public release remains NOT READY.

**Resume:** inspect explicit artifact-store root and `StudioBackend.backup`/restore contracts and decide whether a safe isolated store path can be introduced without changing existing user data. Preserve fail-closed accounting; no source code changed in this stage.

## 2026-10-30 — E08 artifact-root and backup boundary

Graphify query guided the AppPaths/StudioBackend/SliceArtifactStore trace; live source confirms `AppPaths` has data/config/logs/cache only, `SliceArtifactStore` has no Studio/bootstrap caller, `StudioBackend.backup()` snapshots only `data/ufm.sqlite3`, and `sqlite_snapshot.py` creates/verifies/restores only the database plus manifest. `tests/integration/test_studio_backend.py -k backup_contains_a_verified_database`: 1 passed, 4 deselected. The external slice store currently contains no runtime-owned data, so do not add unused storage or redesign backup prematurely. A future E08 wiring stage must select one canonical `data/slice-artifacts`-like root and atomically define backup/restore/verification before enabling UI-to-binding workflow; root name remains a design choice, not implemented. No database was read/changed by these checks.

Updated checklist evidence for E08.01 and scoped E14.03/E16.04/E16.08 notes; no statuses changed. Candidate15 light/dark Filament visual review was done at 1360×860; switched back to light mode so the manual tester sees the default. Current UI guide now points at Candidate15. Parser contract tests 21/90 and backup test 1/4 passed; public release remains NOT READY.

**Resume:** review the nearest available source-supported E08 producer/writer-fencing preconditions and investigate the existing E16.08 native Qt process-exit failure only if a debugger/log path is available. Do not wire current Bambu snapshots into accounting; no durable occurrence identity or cross-process Haspel writer fencing is proven.

## 2026-10-30 — repeated full-suite result and native teardown crash

Same source and locked Python 3.12.14: `python -m pytest -q tests/integration/test_studio_window.py tests` ran all tests and exited 0 (654 passed/489 subtests, 81.39 s). The normal default `python -m pytest -q` also printed 654 passed/489 subtests, but the Python process returned `-1073741819` (`0xc0000005`). Application Error 1000 at 23:18:30 names `Qt6Widgets.dll` 6.12.0.0; earlier crash entry named `Qt6Core.dll`. This is order/intermittency evidence, not proof of a unique cause. Checked PATH and standard Windows SDK/WinDbg paths; no debugger executable found. Did not open WER dumps. No test order configuration or crash suppression was changed. Release test process remains a blocker.

Checklist E16.08 remains Partial and now records both outcomes, exact exit codes and module. No source code changed in this stage. Parser + backup relevant selections passed (21/90 and 1/4), user guide points to Candidate15, automation `ufm` is still active. Current test bundle remains unsigned development Candidate15; release is NOT READY.

**Resume:** when a debugger or usable symbols are available, reproduce and inspect the Qt teardown fault before patching. Otherwise continue only independent release/source audits, retaining the failure as unresolved. Do not interpret the UI-first green run as clearing the default runner failure.

## 2026-10-30 — strict mypy cleanup in Haspel authority client

Fixed seven strict mypy diagnostics in `src/ufm/integrations/haspelsync/authority_client.py`. Added `_booking_grams(object) -> float` using exact int/float type checks, preserving rejection of bool, NaN, non-positive and over-limit values; added explicit printer-id string narrowing and removed redundant casts after validation. Wire/schema behavior is unchanged. `mypy src`: success, 138 files; `ruff check src tests`: clean; `pytest tests/unit/test_haspel_authority_client.py -q`: 10 passed/4 subtests. Full suite with Studio module first: 654/489 exit0. Default full suite: 654/489 then exit -1073741819; Event 1000 cites Qt6Widgets 6.12.0 access violation. No debugger installed at PATH/standard paths, no dump opened, root cause still unresolved.

Checklist E16.08 remains Partial; evidence appended, status counts unchanged. No database, linked-stack Haspel source or printer touched. Public release remains NOT READY.

**Resume:** continue source/doc consistency audits; do not change test ordering to suppress the default crash. Revisit Qt teardown only with debugger/symbols or a reproducible bounded trace.

## 2026-10-30 — latest full suite with faulthandler; release docs aligned to Candidate15

After the authority-client typing fix, default `.venv312\Scripts\python.exe -m pytest -q` with `PYTHONFAULTHANDLER=1` completed 654 passed / 489 subtests, exit 0 in 81.34 s and emitted no traceback. This follows a default-order run with the same green summary but exit `-1073741819` and Windows Event 1000 for Qt6Widgets 6.12.0; UI-first full suite had exit0 as well. Therefore behavior is intermittent; do not claim the collection order or faulthandler fixed it. Keep E16.08 Partial, do not mask process codes. `mypy src` 138 files and `ruff check src tests` both pass after source change; focused authority tests 10/4 pass.

Updated release-facing docs that incorrectly identified Candidate13 or Candidate10 as the latest test build. `RELEASE_ACCEPTANCE_UK.md` now identifies Candidate15 and the current blockers; Candidate13/10 detail is explicitly historical. F118 feature parity now says Candidate15 has no complete SBOM; E12.03 checklist notes its lack of live Haspel acceptance. No release artifact, installer or source code was changed in this doc stage. Checklist remains UTF-8 BOM/118 unique IDs; status counts unchanged.

**Resume:** continue source-based audit and identify any further current-state documentation drift. Release remains blocked by incomplete SBOM/licensing/signing/provenance, clean-Windows/owner/hardware acceptance, durable run identity/writer fencing, and intermittent Qt native exit fault.

## 2026-10-30 — release-document candidate chronology reconciled

Corrected the release-progress narrative where old Candidate13 and Candidate10 notes could read as current, preserving the historical evidence but explicitly pointing to Candidate15 as the current internal candidate. Updated the E12.03 checklist evidence to label Candidate11/12 as historical and clarify that Candidate15 does not constitute live HaspelSync acceptance for this particular workflow. Candidate15's UI was reviewed locally; no live Haspel API, printer, production data or accounting action was used. Checklist UTF-8 BOM and status values were preserved; no status was promoted. Public release remains NOT READY.

**Resume:** continue with safe, source-verifiable release blockers. Do not infer E12 live acceptance from bundle inclusion. Preserve old candidates and shortcuts; no cleanup/deletion was performed.
## 2026-10-30 — E05.04 weighing verification checkpoint

Targeted existing tests were run separately and passed: `.venv312\Scripts\python.exe -m pytest -q tests/integration/test_studio_window.py -k manual_weighing` — 4 passed, 69 deselected; `.venv312\Scripts\python.exe -m pytest -q tests/integration/test_inventory_commands.py -k measurement` — 6 passed, 40 deselected; both exit 0. Graphify Provider Health Scale community and source review confirm `src/ufm/application/ports/scales.py` declares only a `ScaleProvider` Protocol; `rg` finds no concrete provider or Studio wiring. Existing manual weighing persists gross/tare/net evidence and requires explicit reconciliation confirmation; calibration-gated SCALE evidence is guarded in application logic. E05.04 stays In Progress until an actual scale/protocol is chosen and its calibration/physical behavior is accepted; no hardware or live inventory was touched.

**Resume:** do not invent device support. Continue other independent source-verifiable plan items; obtain a scale model/protocol only when available through project requirements or hardware evidence.
## 2026-10-30 — E16 release checklist current-candidate alignment

The long-lived E16.01/E16.02/E16.08 evidence fields contained Candidate10/11/12 as “latest/current” build context even though those observations were historical. Added superseding scoped evidence naming Candidate15 (374 manifest-verified files; unsigned `0.1.0.dev0`; no complete SBOM; no installer) as the current internal test candidate. Candidate15 was visually inspected across four tabs at one PC resolution only. The latest suite outcomes remain mixed due to an intermittent post-summary Qt native process-exit access violation; no fix is claimed. Earlier evidence remains retained and status counts are unchanged.

**Resume:** continue with the next source-verifiable release blocker. Do not delete archived candidate folders or claim public readiness based on the current internal test build.
E14.01 checklist alignment: the Candidate10 UI observation is historical. Candidate15's four-tab visual review is the current scoped evidence; no layout or acceptance status was inferred beyond the single-PC smoke. E14.01 remains Partial pending owner and accessibility/DPI acceptance.

## 2026-10-30 — E03.08 observed license metadata fallback

The locked `.venv-release` distributions `jaraco.classes` 3.4.0 and `segno` 1.6.6 both declare OSI license classifiers and package LICENSE files, but have neither `License-Expression` nor `License` metadata. `scripts/collect_studio_notices.py` previously discarded the classifiers and recorded `not specified`. Added `_observed_license_metadata()` to prefer expression, then legacy License, then a sorted/deduplicated `Classifier metadata only: ...` value, and finally `not specified`. Four new unit tests cover priority, fallback determinism/deduplication and absent metadata. Verification: `pytest -q tests/unit/test_release_metadata.py` — 4 passed; Ruff clean; separate mypy checks on the script and test each succeeded. Running the release collector in a temporary directory inventoried 21 distributions and emitted classifier-only MIT for jaraco.classes and BSD for segno. This remains observed package metadata, not legal review. Candidate15 was not rebuilt; no SBOM sidecar was generated; release stays NOT READY. E03.08 remains Partial.

**Resume:** preserve classifier observations in next generated inventory, then resolve full native SBOM completeness, chosen project license and legal compatibility through the proper owner/legal review. Do not label a CycloneDX BOM complete based only on these classifiers.
## 2026-10-30 — Candidate15 diagnostics consent-dialog visual smoke

Computer Use opened System → Export diagnostics on Candidate15's isolated `D:\UFM_TestCandidate15\Data`. Preview was legible at 1360×892 and explicitly stated the allowlisted time/level/event contract, exclusions (raw fields, printer/spool IDs, paths, addresses, settings, database and secrets), counts (0 included/0 omitted), event SHA-256, and a reminder to review event names/timestamps before transfer. Selected No; no file save dialog appeared, no export was saved/transmitted, and no settings/data changed. This is a local agent smoke on an empty test log, not owner acceptance or verification of non-empty redaction behavior. E14.06 remains Partial.

**Resume:** keep the isolated app on System; preserve the test shortcut and data. Await owner review for this gate and continue with safe independent source work.

## 2026-10-30 — diagnostic event allowlist hardening and Candidate15 visual pass

Reviewed Candidate15 (exact process path `D:\UFM_TestCandidate15\UFM Studio\UFM Studio.exe`) with Computer Use. At 1362×892, all four main tabs were legible without obvious clipping. Filament/Materials/Devices showed clear empty-state guidance; spool actions that require selection were disabled; the Devices page distinguishes candidate discovery from physical controls. System shows the isolated data path and public-release limitations. The diagnostics preview was readable and displayed the empty event digest; the safe-log viewer explicitly showed an empty log. No export, printer connection, import, backup, settings change or inventory mutation occurred.

Found and reproduced arbitrary event-code export leakage: `build_safe_diagnostic_bundle()` accepted `printer_serial_123456` because it satisfied the snake-case regex. Added `src/ufm/infrastructure/logging/events.py::SAFE_LOG_EVENT_CODES`; both `RedactionFilter` and `build_safe_diagnostic_bundle()` now reject codes outside the explicit set (`foundation_started`, `localization_unavailable`, `startup_validated`, and safe fallback `log_message_omitted`). Added a regression case verifying unknown valid-looking event strings are counted as omitted and absent from output. Targeted diagnostics/logging/metadata suite: 13 passed; Studio registry test: 1 passed/72 deselected; Ruff clean; mypy src: 139 files clean.

Full default suite: 659 passed / 489 subtests, then process exit 1 with Windows fatal exception access violation and no Python frame after 81.56s. Do not claim root cause fixed or full process stability. Candidate15 remains unchanged and does not include this change. Before a new portable test bundle, inspect Node/Haspel resource preparation for write scope, verify output path `D:\UFM_TestCandidate16` is new/non-linked, then build via `scripts/build_release_candidate.ps1` unsigned as an internal candidate (SBOM will remain deliberately incomplete). Do not launch the newly built EXE or create a new desktop shortcut without the required action-time Computer Use approval; leave existing shortcuts/candidates untouched. Public release remains NOT READY.


## 2026-10-30 — Candidate16 built and independently verified

Ran `scripts/build_release_candidate.ps1 -DestinationParent D:\UFM_TestCandidate16` after checking the destination did not exist and verifying the three linked HaspelSync resource inputs already matched their packaged source bytes. Build completed on locked Python 3.12.15; build-time Node 24.22.1 hash check passed. `scripts/write_studio_manifest.py D:\UFM_TestCandidate16\UFM Studio --verify` independently verified 378 bundle files. Manifest: 180 source inputs, tree hash `8e1acd1710f4c96a53e82604e0e1409754c1137592026cc76ff3523a8c3fe57d`, `source_git_revision=null`, `source_git_worktree_clean=null`; the event allowlist source is included. EXE SHA-256 `3917132867052376851e9edc4e9fe9aaf91d39022b4ceb9c6a134a6730d612b0`, PE `0.1.0.dev0`, Authenticode `NotSigned`. CycloneDX sidecar lists 401 components with incomplete composition. Candidate16 was built but not run; Candidate15 is the latest visually observed application. No desktop shortcut, installed app, personal data, database, printer, linked-stack source or release signing key changed.

**Resume:** if continuing UI execution, obtain/observe the required action-time approval for launching the new candidate. Otherwise hand the user the exact Candidate16 executable path and ask them to perform manual smoke in a separate data directory `D:\UFM_TestCandidate16\Data`. Then reconcile results; keep E14.01/E14.06 partial until owner acceptance. Full suite currently prints 659/489 green but exits 1 after Windows fatal access violation, unresolved. Release remains NOT READY; do not sign/install/clean up historical candidates.

## 2026-10-30 — Candidate16 documentation and SBOM chronology reconciled

Corrected the manual guide so Candidate16 is described as the newest manifest-verified internal bundle and Candidate15 as the latest UI-reviewed build. The guide gives Candidate16's exact EXE path and isolated `--data-dir D:\UFM_TestCandidate16\Data`; no new shortcut was created. Re-labeled the Candidate15 section in release acceptance as historical. Updated F118 and E03.08 with Candidate16's 378-file manifest, CycloneDX 1.7 sidecar (401 components, `composition=incomplete`), classifier-only metadata for jaraco.classes/segno, absent root Git revision, and unsigned state. The observed MIT/BSD classifiers do not resolve legal applicability or satisfy legal review.

Verification: CSV read/write round-trip preserved UTF-8 BOM, 118 unique IDs, and status counts 29/68/20/1; Candidate16 manifest/SBOM metadata was read directly from the isolated artifact. Documentation edits did not alter runtime. Afterward, diagnostics/logging/release-metadata unit selection passed 13 tests, the safe diagnostics Studio registry integration selection passed 1 (72 deselected), and Ruff on affected source/tests was clean. Candidate16 was not launched; no shortcut/database/printer/linked-stack source changed.

**Resume:** wait for the separately requested Windows UI action confirmation before launching Candidate16; meanwhile continue source-only investigation of E07/E08 run identity and Haspel writer fencing. Keep booking/debit paths fail-closed, E03.08/E14.01/E14.06/E16 rows Partial, and public release NOT READY.

## 2026-10-30 — E03.07 Haspel authority guard regression tests

Added two tests (no Haspel runtime source change) to `linked-stack/haspelsync/test/bookings.test.js`: a revisioned `LEGACY_ACTIVE → UFM_ACTIVE` transfer blocks `useSpoolWeight` before HTTP; exact request replay is idempotent and conflicting request-ID reuse fails; pending intent and stale revision fail closed. Isolated verification: `node --test test/bookings.test.js` — 16 passed, exit 0. The test server and temporary journal stay under the test fixture; no live Spoolman/printer or production path used.

Source confirmation: `linked-stack/haspelsync/src/openapi.js` documents that the authority endpoint is not a global process lock; `src/bookings.js` checks owner inside the selected service and relies on its cached local journal. Thus this test strengthens the narrow local contract but does not solve cross-process or direct-Spoolman writer fencing. E03.07 remains Partial; no automatic debit activation. Checklist UTF-8 BOM/schema/status totals remain 118 IDs and 29/68/20/1.

**Resume:** inspect whether the supported deployment contains a shared authoritative lock/lease across every stock writer. If no such service is present, keep the global-fence gate blocked and do not emulate a distributed lock within a local file. Candidate16 UI review remains pending action-time confirmation.

Additional verification for the E03.07 checkpoint: reran the Haspel booking+accounting files together — 30 passed, exit 0 — and the UFM authority client unit file — 10 passed plus 4 malformed-input subtests, exit 0. Both use temporary/test endpoints. No live service, printer or production DB was accessed.

Candidate16 artifact-linkage recheck: `build-manifest.json` SHA-256 `59077c0feaece2863d75ae879566eca80fe1c633d140ba86d594c24d42a0a5ef`; sidecar SHA-256 `8ed25b5cc37e53486f0e2ea1e196d389689a427b3b190e25c9f3032ab0ad0494`; CycloneDX properties match both the manifest hash and packaged runtime inventory hash. The independent manifest verifier reports 378 bundle files; sidecar has 401 components and `composition=incomplete`. This establishes internal checksum linkage only, not full SBOM completeness, licensing approval or source revision provenance.

## 2026-10-30 — Candidate15 System-page read-only visual review

Used a fresh Computer Use app/window inventory to select the unique already-running Candidate15 window and capture it without clicking or changing focus. At 1362×892 the System heading, test/release limitations, language/log-level selectors, action buttons and isolated `D:\UFM_TestCandidate15\Data\data` path are readable and fully visible; the lower area contains substantial whitespace due to the small number of settings. No import/export/backup/settings action occurred. This does not review Candidate16, physical DPI, keyboard traversal, accessibility or owner acceptance. E14.01 remains Partial; do not adjust layout solely to fill empty space without user feedback or a defined density requirement.

## 2026-10-31 — E04.07 per-spool import preview

Extended `SpoolmanImportPreview` with a read-only per-spool DTO carrying stable source IDs, profile/vendor labels, nominal/tare/remaining mg, archived state, transferable price+basis+currency and lot/color/location, plus row-local omitted-field markers. Values are constructed from the already validated `_SpoolRow`; masses reuse importer `_mass()` half-up conversion. Studio `import_database()` now opens a read-only table of every parsed spool before the explicit import confirmation. The table distinguishes unknown stock and lists price when it cannot be carried because its currency/basis is unavailable, plus malformed lot/color/location fields. No raw filesystem path or credentials are shown. Existing source selection, backups, import commands and write gating remain intact.

Verification: `.venv312\Scripts\python.exe -m pytest -q tests/integration/test_spoolman_importer.py tests/integration/test_studio_window.py -k "spoolman or translations_have_matching_named_fields or inventory_action_registry"` — 10 passed, 71 deselected. `ruff check` on importer/Studio/importer test clean; `mypy` on importer and Studio clean. CSV retains UTF-8 BOM, 118 unique IDs, status counts 29/68/20/1; E04.07 evidence appended, status stays Partial. No production database, Spoolman service, printer, UI candidate, shortcut or linked Haspel source touched. No test print.

Limit checkpoint after implementation: 5h remaining 99%, weekly remaining 25%. Next inspect target-row conflict conditions against an isolated fixture and verify the live AMS snapshot fields before choosing another implementation step. Root release remains NOT READY; automatic debit stays fail-closed. Graphify source hashes are now stale for edited existing files and should be refreshed with existing maps preserved.

## 2026-10-31 — Graphify maps refreshed after E04.07

The previous handoff line “Graphify source hashes are now stale” was superseded after refreshing maps. Deterministic snapshot pipeline: `D:\graphify-out\bambu-ufm\tools\enrich_graph.py`, `project_maps.py`, and `combine_enriched.py` completed. Current traceability is 738 files / 13063 nodes / 45074 edges; UFM 241/6117/22475, Spoolman 298/4920/15554, Spoolman↔UFM 539/10988/38029, enriched total 28960/85560. Manifests bind source hashes and immutable snapshot paths; historical snapshots were retained. In-repo root graph also updated with Graphify's documented `update PATH --no-cluster` command and `cluster-only PATH --no-label`: 6151 nodes and 17924 raw edges. Multigraph diagnostic reports 525 directed and 540 undirected parallel endpoint collapses; these raw links remain in JSON while clustering uses a simple graph. HTML and report were regenerated.

Known scope: the root `graphify update` refreshed code only and explicitly advises a separate semantic extraction for docs/images; it did not use LLM. The externally maintained combined map includes the updated CSV/docs through deterministic traceability snapshot. Fifty JavaScript test files in the combined corpus still yield no AST symbols, though present in file manifest. No source/build/production data was modified by graph creation.


## 2026-10-31 — Bambu AMS remainder observation checkpoint

Implemented read-only AMS remainder capture. `FeedSlotSnapshot` gained optional `remaining_percent: Observed[int]`; validation requires exact integer 0..100. Bambu LAN maps `remain` to this separate percentage observation and maps only bounded positive integer `remain_g` to `Mass` grams. It never estimates grams from `weight × remain%`; malformed/sentinel inputs remain UNKNOWN. Bambu source inspected: `D:/GIT/BambuStudio/src/slic3r/GUI/DeviceCore/DevFilaSystem.h:82-83` and `DevFilaSystem.cpp:117-121` (`remain` 0..100, `remain_g` grams/-1 sentinel, zero weight treated absent). The monitor renders both values as read-only “printer-reported” data. Topology audit payload includes percentage only when known, leaving older snapshots with no percent unchanged; same sequence key with a differing known percent conflicts. No stock, spool assignment, reservation, ledger, printer control or external API write is connected.

Verification: Ruff clean on seven changed UFM source/test files; targeted mypy clean on DTO/provider/topology/Studio; `test_feed_snapshots.py` + Bambu parser selection 6 passed; topology audit/idempotency 1 passed; Studio monitor render 1 passed; localization JSON parsed and all bilingual named placeholders match. No live printer, DB, linked Haspel source, test print or Candidate16 UI used. Checklist E11.08 remains Partial.

Resume: first refresh Graphify maps (external deterministic traceability generator should include `src/ufm/ui/studio_strings.json` as a manifest-bound document/resource node; root Graphify code map alone omits JSON). Verify source SHA manifests. Then proceed to the next safe E11 requirement. Hardware acceptance, physical RFID identity, external spool, multi-AMS rollover/offline and event-to-segment wiring remain open. Public release NOT READY; automatic debit stays fail-closed.


## 2026-10-31 — Bambu authentication result and Candidate18 checkpoint

**Observed:** UFM's local profile import matched the Studio-stored profile to the TLS-identified Bambu device; exact fingerprint trust was explicitly confirmed. The read-only MQTT login then received CONNACK `Not authorized`. The UI attempt showed `ProviderUnavailable`, while a one-shot in-memory diagnostic captured only the safe reason-code name. No report/AMS state was read. Configuration persistence occurs only after connect plus `get_status()` succeed; the isolated test UI still shows zero printers/spools. No credential, serial, IP or fingerprint value is recorded in this handoff. No stock write, print, heater/motion/job command or production DB access occurred.

**Fix:** in `src/ufm/integrations/printers/bambu_lan.py`, `_on_disconnect` now avoids replacing an already classified connection error, retaining `AuthenticationFailed` from the failed CONNACK. Regression added to `tests/integration/test_bambu_lan_provider.py`. Six focused integration/contract modules: 158 passed, 59 subtests passed (24.24s); Ruff clean; targeted mypy clean.

**Candidate18:** `D:/UFM_TestCandidate18/UFM Studio/UFM Studio.exe`, isolated data `D:/UFM_TestCandidate16/Data`; manifest independently verified 378 files. EXE SHA-256 `FA305F5DA99BFC70244943D68F22931EBB526FD6EA18B310186DB67494BF4698`, PE version `0.1.0.dev0`, Authenticode NotSigned; sidecar has 401 components with incomplete composition. It is open on the Filament screen at 1362x892 and is suitable for manual source/UI inspection, but cannot authenticate until the printer accepts the LAN code.

**Owner action:** verify Bambu LAN mode and refresh/confirm its LAN access code locally (do not send the code here). Once done, use Candidate18's Devices → Bambu Studio profile import on the same test data directory and retry exactly once. Stop on another auth error. No AMS/external spool data or live accounting acceptance is claimed; stock debit stays disabled.

**Resume:** keep Candidate18 open. Await owner confirmation that LAN mode/code were updated before another network login. Meanwhile refresh root and external Graphify maps after the callback/test/docs edits; preserve historical snapshots. Public release NOT READY.


**Graph checkpoint completed 2026-10-31:** root Graphify code map updated (6,162 nodes / 17,953 edges; incremental extraction reported 141 uncached code files; unsupported and symbol-free files remain in diagnostics). External deterministic traceability maps were rebuilt after source/test/checklist edits: UFM 242 files / 6,134 nodes / 22,527 edges; Spoolman 298 / 4,920 / 15,554; linked graph 540 / 11,005 / 38,081; enriched combined graph 28,974 / 85,612. Source manifests and immutable snapshots were regenerated. Maps help navigate and cite current sources; they do not prove runtime acceptance. The custom external map excludes these two growing progress logs, so this append does not stale the graph source manifest.

Root Graphify artifact check 2026-10-31: parsed current `graphify-out/graph.json` as 6,162 nodes, 17,953 raw `links`, and 10 hyperedges; cluster-only reported 276 communities and 17,412 simple edges for clustering (parallel endpoint links are retained in raw JSON). Hash comparisons against the refreshed external `source-manifest.json` passed for `bambu_lan.py`, `test_bambu_lan_provider.py`, and `INTEGRATION_CHECKLIST_UK.csv`. CSV retains UTF-8 BOM, 118 unique IDs; statuses remain 29 Done / 68 Partial / 20 Planned / 1 In progress.


## 2026-10-31 — Candidate18 ізольований stock UI smoke

**UI evidence:** залиш Candidate18 відкритим на сторінці Філамент. Запущено з окремою текою даних `D:/UFM_TestCandidate16/Data` (портативна тестова збірка під `D:/UFM_TestCandidate18`). У UI створені лише тестові записи: матеріальний профіль `UFM_TEST_PLA`; котушка `UFM_TEST_PLA_GREEN`, колір `TEST_GREEN`, номінальна маса 500 г, маса пустої котушки 200 г; через окрему дію записано початковий залишок 500.000 г і потім ручне списання 1.000 г. Перевірений результат: картка/таблиця показали 499.000 г; історія показала `#1 Початковий залишок 500.000 → 500.000 g` і `#2 Коригування залишку −1.000 → 499.000 g`. У шапці видно тестову збірку; 1362×892. Це UI smoke з ізольованою локальною базою, не автоматизований acceptance, не доказ збереження після restart, і не власницьке приймання. Тестові дані залишені для ручного огляду. Не запускати cleanup/видалення без окремого доручення.

**Verification:** current full source suite `.\.venv312\Scripts\python.exe -m pytest -q`: 664 passed, 491 subtests passed, 87.78 s, exit 0. Це suite test evidence лише. У поточному етапі source не змінювався; root Graphify code graph не потребує rebuild, але зовнішня requirement/traceability карта має бути оновлена після зміни CSV. CSV E14.01 додано UI smoke, статуси не просунуті: UTF-8 BOM, 118 unique IDs, 29 Done / 68 Partial / 20 Planned / 1 In progress.

**Safety/limitations:** жоден принтер, production DB, HaspelSync service/source чи реальний склад не змінений; принтер не керувався й не друкував. Live Bambu LAN/MQTT login раніше відхилено як `Not authorized`; нова спроба лише після того, як власник локально перевірить LAN mode та оновить код. AMS/external spool/runtime account remains unverified. Auto debit remains fail-closed. Public release NOT READY.

**Resume:** (1) refresh the external deterministic traceability map for the updated CSV using its recorded scripts in the prior Graphify checkpoint; verify generated source-manifest hashes; (2) continue source-level E11 review of whether accepted printer receipts project exact materials/usage segments. Do not infer active material usage from Bambu AMS percent or send-time `ams_mapping*`; do not add job identity or debit without stable occurrence/receipt evidence and global writer fence. Keep Candidate18 open for user inspection.


## 2026-10-31 — Integration test fixture portability and fresh Graphify maps

Source diff in the nested `linked-stack/haspelsync` was reviewed without changing its Git configuration. Existing HaspelSync edits remain intact; the only new change for this stage is in `test/gcode.studiomapping.test.js`: `freshPrinter()` now directs the test logger to the temporary `LOG_DIR` established by first-import `test/helpers/tempdata.js`, replacing POSIX-only `/dev/null`. This avoids Windows `ENOENT: D:\dev\null` noise without altering HaspelSync runtime code or test semantics.

Verification: `node --test test/gcode.studiomapping.test.js` using Node v24.22.1 — 12 passed, exit 0. Remaining error-level log lines are intentional negative-path fixtures (no slice input and loopback FTPS connection refused at `127.0.0.1:990`); they do not access an actual printer or outside network. Full UFM source suite earlier this run: 664 passed and 491 subtests, exit 0.

CSV was updated in E08.07 and E11.03 as evidence only; statuses were not promoted. CSV retains UTF-8 BOM, 118 unique IDs, counts 29 Done / 68 Partial / 20 Planned / 1 In progress.

External deterministic Graphify refresh completed after the CSV and linked test fixture edits: traceability 739 files / 13,077 nodes / 45,125 edges; UFM map 242 / 6,134 / 22,527; Spoolman 298 / 4,920 / 15,554; Spoolman↔UFM 540 / 11,005 / 38,081; enriched graph 28,974 / 85,612. All five graphs were parsed and checked for unique node IDs and valid edge endpoints. Manifest SHA-256 matched the current CSV, `bambu_lan.py`, and `test_bambu_lan_provider.py`. This is source-navigation/traceability only. Root code graph was not rebuilt because UFM source files did not change.

**Resume:** continue the nearest source-verifiable integration task, but keep E11.03 partial: HaspelSync’s echo fixture helps confirm only the bounded `ams_mapping*` transfer semantics; it is not a stable run identity nor a UFM receipt/event-to-segment path. A fresh provider epoch/event counter on reconnect and missing original payload remain blockers. Keep production stock/debit disabled pending exact occurrence provenance and global writer fencing. Public release remains NOT READY.


## 2026-10-31 — Resume point: importer interruption and retry

**Code/test change:** `tests/integration/test_spoolman_importer.py` now injects an interruption at the second spool, after the first record and opening-stock transaction have committed, and retries with the identical explicit 24-hex source-instance key. The existing importer resumes idempotently: three spools, two opening-stock ledger rows, expected 350000/799448 mg; the mapping report is produced on successful retry. Test file: 9 passed. Ruff and mypy on importer + test passed. Test DB/files are under `TemporaryDirectory`; no production data or source DB was touched. E04.08 is Partial, because total reconciliation against the full source snapshot and legacy/moved-file acceptance are not covered by this fixture.

**Graph reconciliation:** corrected current-count summaries in `D:/graphify-out/bambu-ufm/PROJECT_MAPS_UK.md`, `HANDOFF_UK.md`, and `ENRICHMENT_UK.md` to match the existing graph JSONs (traceability 13080/45147; UFM 6138/22550; Spoolman 4920/15554; link 11009/38104; enriched 28977/85634). Unique-ID/edge-endpoint validation passed for each graph; manifest hashes match the current checklist CSV and the modified `test_spoolman_importer.py`.

**Resume:** next implement/verify full source-vs-target snapshot reconciliation in E04.08 with isolated fixtures; do not claim legacy or live DB acceptance unless actually proven. Refresh root and external Graphify maps after this test/CSV change, checking preserved source hashes and graph health. Keep public release NOT READY and auto debit fail-closed.


## 2026-10-31 — E04.08 moved-source retry and final check

`test_interrupted_import_resumes_without_duplicate_stock_or_ledger` injects an error at spool 2 after spool 1/its opening balance commit, physically moves/renames the source database, and retries under the same stable source key. It checks three final spools, only the two expected opening-stock rows, complete ID-map spool/filament coverage and fingerprint equality. Importer test module 9 passed; Ruff and targeted mypy clean. Full suite before the final assertion-only extension: 665 tests + 491 subtests passed in 89.09s; the extended importer module was rerun (9 passed). No production data/services/hardware used. E04.02/E04.08 remain Partial. The induced failure leaves a partial, resumable DB before retry; explicit partial-import recovery visibility is not yet established.

Graphify was rebuilt after the last CSV/test edit. Traceability 739 files / 13080 nodes / 45147 edges; UFM 242/6138/22550; Spoolman 298/4920/15554; link 540/11009/38104; enriched 28977/85634. Root graph 6170 nodes/17972 raw edges. Unique-ID/endpoint checks passed for all five external graphs and hashes match the current CSV and test file. Graph remains navigation evidence only.

Resume with full source-to-target snapshot reconciliation and a safe explicit recovery UX for interrupted imports. Preserve the incomplete source hash until all rows are imported, and keep public release NOT READY.


## 2026-10-31 — Resume cue for an unverified Spoolman import

`spoolman_import_source_label()` annotates a registered source with no snapshot SHA as unverified. Studio and desktop use it with separate localized strings; prompts clarify that absent SHA can indicate either a legacy source or an interrupted import, and reselecting the same instance key can resume/reconcile IDs. A source with recorded snapshot SHA keeps the normal label. Added `test_source_label_flags_only_unverified_import_snapshots`; importer suite 10 passed; translation-name contract 1 passed/72 deselected; Ruff and targeted mypy clean; localization JSON parse clean. No user DB, real Spoolman, printer or linked HaspelSync touched. This cue does not hide or atomically roll back partial records, so E04.08 remains Partial pending source/target reconciliation and recovery semantics.

CSV E04.08 updated (BOM retained; 118 unique IDs; status counts unchanged at 29/69/19/1). **Next mandatory:** run full suite against this latest UI change, then refresh root and external Graphify maps after code/resource/CSV edits; verify the current manifest and graph endpoints. Keep release NOT READY.


## 2026-10-31 — Full-suite result and final map snapshot

Current source suite: **666 passed, 491 subtests passed, 87.47s, exit 0**. Importer suite 10 passed; translation-name contract 1 passed/72 deselected; Ruff and targeted mypy clean. Graph was refreshed after source, translation resource and checklist edits: traceability 739 files/13085 nodes/45173 edges; UFM 242/6143/22576; Spoolman 298/4920/15554; link 540/11014/38130; enriched 28982/85660; root 6177/17988 raw edges. Next action is final manifest/checksum and endpoint audit. Release remains NOT READY; live Bambu auth is still rejected and automatic debit lacks durable occurrence identity/global writer fence.


## 2026-10-31 — Final locale-map coverage checkpoint

The prior manifest correctly matched code/test/CSV but omitted the two edited locale catalogs. Extended the external Graphify source selector to include every `src/ufm/ui/i18n/*.json` plus `studio_strings.json`; rebuilt all cross-project maps. Current files/nodes/edges: traceability 741/13087/45175; UFM 244/6145/22580; Spoolman 298/4920/15554; link 542/11016/38134; enriched 28984/85662. Post-build unique-ID and endpoint validation passed; SHA-256 matches CSV, test, studio string registry, en-US and uk-UA. Root code graph 6177/17988; 0 dangling endpoints. Full UFM suite 666/491 passed before map-only scope edit; targeted affected tests/Ruff/mypy passed after code change.

Resume: investigate whether source registry/hash and target rows can be reconciled completely after a partial import, with explicit safe UI recovery. E04.02/E04.08 remain Partial and release NOT READY.


## 2026-10-31 — Resume: exact imported-source set reconciliation

`SpoolmanCutoverPreview` previously compared every source row but did not detect imported-device UFM spools absent from the source snapshot. Added `unexpected_count`, computed as non-deleted target spool IDs for the registered import device minus deterministic IDs for current source rows. `ready` now fails on any unexpected target; Studio's combined evidence SHA and summary string include this count. Regression in `test_cutover_preview_detects_changed_source_and_target_balance` verifies 3/3 baseline passes, changed source gives 1 mismatch, and an extra target spool blocks readiness. The test suite selected 12 passed/72 deselected; Ruff and targeted mypy clean. All data is synthetic/temp; no live DB, Spoolman, printer or stock was touched. Limitation: extras entered under another actor/device are not attributable to this import key; interrupted import records remain visible until retried. E04.08 Partial.

Next: full suite on this source change, then refresh root/external Graphify and verify current manifest (CSV, importer, UI strings). Continue with failure recovery/legacy fixture evidence. No release claims; auto debit stays fail-closed.


## 2026-10-31 — Target-only spool cutover guard: verification

Full suite passed 667 tests + 491 subtests in 88.27s; the focused changed selection passed 12, Ruff/mypy clean. Final root/external Graphify rebuild follows the UFM source, string resource and CSV changes: traceability 741/13089/45205; UFM 244/6147/22610; Spoolman 298/4920/15554; UFM↔Spoolman 542/11018/38164; enriched 28986/85692; root 6184/18011 raw edges. Current external source selection includes both UI locale JSONs and studio_strings. Final SHA and graph integrity checks pending. Resume with those checks, then continue E04.08 beyond synthetic coverage. Release remains NOT READY.


## 2026-10-31 — Final map/checksum evidence

All 5 external Graphify JSONs have unique node IDs and valid edge endpoints: traceability 741/13089/45207; UFM 244/6147/22612; Spoolman 298/4920/15554; link 542/11018/38166; enriched 28986/85694 (files/nodes/edges). The manifest matches checklist CSV, importer, Studio UI, tests, studio_strings and en-US/uk-UA locale JSON. Root Graphify diagnose: 6184 nodes, 18011 raw edges, 0 dangling; same-endpoint parallel links remain in JSON and are collapsed only in clustering. Full suite 667/491 passed, targeted 12 passed, lint/type clean. External-owner/live DB and hardware acceptance remain open; release not ready.


## 2026-10-31 — E04.06 current balance proof and resume

The checked source path `_load_rows` uses `initial_weight` (fallback filament nominal) minus Spoolman `used_weight` to compute current remaining; negative values fail closed. The importer then establishes that value once as opening stock under a stable command key; repeated import uses history to avoid a second opening entry. Focused test `test_import_backs_up_source_and_imports_opening_balance_once`: 1 passed; expected ledger values 799448/350000 mg, not nominal 1000000/750000 mg. E04.06 now Partial, not Done: old historical transactions are not reconstructed and no real/legacy database acceptance was performed. CSV BOM retained, 118 rows, status counts 29/70/18/1.

Next: refresh external traceability maps after CSV change, then proceed to the next unblocked planned integration item. Full suite most recently passed 667/491; no product source change in this stage. Preserve release NOT READY and database isolation.


## 2026-10-31 — Graph counts after E04.06 checklist update

External graph rebuild followed the E04.06 status/evidence edit. Final totals: traceability 741 files/13089 nodes/45207 edges; UFM 244/6147/22612; Spoolman 298/4920/15554; link 542/11018/38166; enriched 28986/85694. Source manifest reflects the current checklist; all three locale JSON resources remain in map scope. Root code graph unchanged at 6184/18011.

## 2026-10-31 — E04.08 partial-import reconciliation API

Implemented `preview_spoolman_import_recovery()` as read-only diagnostic API. Unlike the cutover preview, it only accepts a registered source with no completed snapshot fingerprint, computes counts against deterministic target spool IDs and same-import-device extras, and never reports ready. Test evidence: interrupted after first spool -> (3 source, 1 matched, 0 mismatched, 2 missing, 0 extra); same source is then moved/renamed and retry reuses stable IDs with exactly two opening-stock ledger entries. A completed snapshot is rejected by recovery preview. Importer tests: 11 passed; Ruff clean; targeted mypy clean. Checklist updated with this evidence; E04.08 remains Partial because the report is not yet shown in UI and no real/legacy acceptance or other-owner reconciliation is available.

Next: wire this diagnostic into both source chooser flows without blocking the UI thread; localize summary; verify UI contract and import retry with temporary SQLite only. Then refresh root and external Graphify, verify BOM/118-ID totals and current source hashes. Preserve NOT READY status; auto-debit remains disabled. No commit/push/deploy.

## 2026-10-31 — Recovery counts shown in both import source pickers

Extended the E04.08 recovery diagnostic through the existing `preview_spoolman_database()` result. For each registered incomplete source, the preview now includes `(source rows, matched, mismatch, missing, extra)` counts from one bounded target-device query; only unverified sources get counts. Studio and desktop source labels format the counts with localized `studio_strings.json` and `uk-UA.json` / `en-US.json` text. A same-key retry remains the only action; diagnostics do not mutate inventory or qualify as cutover evidence. Tests: importer + Studio integration 84 passed; full UFM suite 667 passed + 491 subtests in 87.13s; Ruff and mypy clean. No live DB, Spoolman, printer, print or Haspel runtime.

CSV E04.08 remains Partial; checklist integrity/counts are recorded in `PROJECT_PROGRESS_UK.md`. Remaining: visual acceptance of both import dialogs, real/legacy source acceptance, correction/concurrency handling if inventory changes after preview, and attribution beyond the registered import device. Next refresh root/external Graphify and revalidate all current file hashes/endpoints; afterwards continue another unblocked integration step. Release NOT READY, no commit/push/deploy.


## 2026-10-31 — Graph refresh after E04.08 recovery UX

Root Graphify update and cluster-only completed: graph.json has 6199 nodes / 18052 raw links; 0 dangling endpoints. External snapshot rebuilt from current source: traceability 741 files / 13096 nodes / 45253 edges; UFM map 244/6154/22658; Spoolman 298/4920/15554; Spoolman↔UFM 542/11025/38212; enriched 28993/85740 (85529 original input edges preserved, 211 evidence-backed bridges). All six JSON maps have unique IDs and valid endpoints. SHA manifest matches the current checklist, importer, Studio/desktop UI, strings/locales and importer tests. E04.08 remains Partial. Full UFM suite: 667 passed/491 subtests; targeted 84 passed; Ruff and targeted mypy clean.

Next: choose next unfinished high-priority task by dependency, with current recovery chooser visual acceptance outstanding. Recovery count is diagnostic and can become stale between preview and retry; no live DB, device, production stock, printer, print, deploy or packaging touched. Public release NOT READY; no commit/push.


## 2026-10-31 — Stale import-preview confirmation rejected

A source database can change while the import review dialog is open. The import operation now accepts an optional exact preview fingerprint and rejects a changed/invalid fingerprint immediately after source validation, before app data directory creation, backup or database mutation. Both Studio and desktop pass the exact preview fingerprint used for their confirmation screen. Regression test_import_rejects_source_changed_after_preview_before_any_target_write verifies refusal and that the isolated target path remains absent. Targeted importer+Studio: 85 passed; full UFM suite: 668 passed/491 subtests; Ruff and mypy clean.

E04.08 remains Partial. This protects preview-to-action consistency but does not solve legacy acceptance, external-device ownership, or manual visual/runtime checks. Update Graphify now; expected changed-source hashes: importer, Studio, desktop, importer fixture and checklist. Release NOT READY, no live hardware/database, no commit/push/deploy.


## 2026-10-31 — Maps refreshed after preview fingerprint guard

Current root graph 6203 nodes/18061 raw links. External snapshot: traceability 741 files / 13098 nodes / 45265 edges; UFM map 244/6156/22670; Spoolman 298/4920/15554; link 542/11027/38224; enriched 28995/85752 (85541 source edges retained plus 211 evidence-backed bridges). All graph IDs are unique and all endpoints resolve. Manifest SHA matches current CSV checklist, importer, Studio/desktop source, studio strings, en-US/uk-UA and importer test. Current suite 668 passed/491 subtests; targeted UI/importer 85 passed; Ruff/mypy clean.

Next: continue E04.08 UI and source/target acceptance gaps; do not promote the row. No live data, device, printer, print, release or deployment.


## 2026-10-31 — Current-source offscreen Studio review

The current source Studio was launched with --capture against an isolated synthetic interrupted-import fixture and reviewed at 1360x856. The main Filament screen shows the summary cards, filters/actions, table and inspector without visible clipping. This is not physical Windows UI acceptance and does not cover the import chooser, DPI scaling, keyboard, resizing, other tabs or owner approval. E14.03 remains Partial. CSV now records this limited evidence. Temp fixture and capture are under the unique Windows temp directory for this run; they are isolated and do not touch user records or the printer.


## 2026-10-31 — Moved-source chooser default and regression evidence

Added default_spoolman_import_source_key() and wired it to both import source pickers: exact path identity wins; after a move, a sole registered source is preferred; ambiguous multiple sources are left for explicit operator selection. Test covers all four selection states. Importer + Studio: 86 passed; full suite: 669 passed / 491 subtests; Ruff/mypy clean. No live DB/network/device activity.

E04.02/E04.08 remain Partial pending controlled legacy acceptance and manual import-dialog visual inspection. E14.03 remains Partial; only one offscreen 1360x856 main-window capture is recorded. Checklist updated (BOM, 118 unique IDs, totals 29/70/18/1). Next refresh Graphify maps and verify current SHA manifest after source/CSV edits; then continue integration work. No commit/push/deploy.


## 2026-10-31 — Graphify refresh after moved-source default guard

Final metrics: root 6211 nodes / 18076 raw links; traceability 741 files / 13103 nodes / 45291 edges; UFM 244/6161/22696; Spoolman 298/4920/15554; link 542/11032/38250; enriched 29000/85778 (85567 original edges plus 211 evidence-backed bridges). CSV BOM/118 unique IDs with 29/70/18/1 statuses. Manifest hash checks are pending this checkpoint. Tests: 669 passed/491 subtests; targeted 86 passed; Ruff/mypy clean. E04.02/E04.08 and E14.03 remain Partial; release not ready.



## 2026-10-31 — E04.03 ID-map artifact integrity fixture

The resumed-import fixture now checks that mapping_sha256 matches canonical sorted JSON, that mutating an imported UFM UUID breaks the digest, and that the mapping artifact does not disclose the source database path. This supplements the deterministic IDs and moved-file resume proof without adding a separate runtime validator or source-ID alias feature. Tests: 669 passed + 491 subtests full; 86 targeted; Ruff/mypy clean. E04.03 remains Partial for aliases/renames and real/legacy acceptance.

Checklist updated; refresh graph after test/CSV changes. Then proceed with the next open import-boundary requirement. Preserve NOT READY; no live operation or commit/push/deploy.


## 2026-10-31 — HaspelSync read-only journal test coverage

Added `tests/unit/test_haspel_cutover_preview.py` with five isolated tests around `preview_haspelsync_cutover()`: selected-printer booking counts; all/global weighing states; readiness only when pending/uncertain records are absent; unsupported/inconsistent booking rejection; and evidence-digest change when the accounting journal changes. Targeted pytest: 5 passed (0.32s); Ruff clean. E04.05 moved Planned → Partial only for the existing read-only preflight. No historical events or costs are imported.

Next: map historical journal spool IDs through the verified Spoolman import ID-map and define non-duplicating opening-balance/ledger reconstruction, preserving per-row origin and idempotency. E03.06/E03.07 authority/owner transition remains a prerequisite for any writer and still blocks live cutover. Use temporary fixtures only. Full suite was not rerun after adding this test file; the prior full-suite result predates this stage. Refresh Graphify and verify current manifests/endpoints before continuing. No database, live printer, production stock, print, commit, push or deployment.


Full-suite confirmation for HaspelSync read-only journal coverage: `.venv312/Scripts/python -m pytest -q` — 674 passed, 491 subtests passed, exit 0, 85.05s. This run includes `tests/unit/test_haspel_cutover_preview.py` (5 targeted tests had already passed separately). Ruff is clean. No live source data, stock, printer or physical print involved. CSV E04.05 remains Partial (not history import); 118 IDs/BOM; status totals 29/71/17/1. Root and all external Graphify maps were rebuilt after the test/checklist/docs updates. Validation: each JSON has unique node IDs and every edge endpoint resolves; traceability hashes match the checklist, importer, both UI modules/locales and the two relevant test files. Current counts are in D:/graphify-out/bambu-ufm/PROJECT_MAPS_UK.md. Next: continue E04.05 only through a reviewed, idempotent historical-import design; E03.06/E03.07 remain prerequisites for any accounting writer.


## 2026-10-31 — Windows discovery console fix

During a local Devices-tab discovery smoke, two unverified LAN candidates appeared, and a transient PowerShell console covered UFM. Changed `primary_local_network()` to pass `CREATE_NO_WINDOW` where the platform exposes it. Regression check: printer discovery integration module 9 passed; Ruff clean. No credentials/authentication, printer state, AMS read, commands, stock mutation, or print. E14.01 evidence now includes this limited observation; no status promotion.

Next: continue bounded integration work; prioritize isolated read-only Bambu protocol parsing/connection evidence without authentication automation. Keep the account-code dialog operator-driven, and do not interpret candidate discovery as a verified printer. No live inventory writes or hardware commands. Release remains NOT READY. Refresh root/external Graphify after this source/test/checklist/doc update, then verify current manifest and graph integrity.


Full-suite follow-up: 674 passed, 491 subtests passed, exit 0 (82.96s); printer-discovery module 9 passed; Ruff clean. Current graph rebuild/checks: root 6,230 nodes/18,129 links; traceability 13,124/45,394; UFM 6,182/22,799; Spoolman 4,920/15,554; UFM↔Spoolman 11,053/38,353; enriched 29,021/85,880; combined 15,897/40,276. Unique IDs and edge endpoints valid across all seven; manifest (742 source hashes) matches changed source, focused test and checklist. CSV remains 118 IDs/BOM and 29/71/17/1 statuses.

Next: proceed with the next unblocked testable integration gap. Candidate discovery is not a verified printer; credentials remain operator-driven. No auth, AMS data, commands, stock changes or print have been performed. Keep E14.01/E14.03 Partial and release NOT READY.


Final graph refresh after E14.01 full-suite evidence was recorded in CSV: UFM 6,183/22,800; link 11,054/38,354; traceability 13,124/45,394; enriched 29,021/85,880; combined 15,897/40,276; root 6,230/18,129. Seven graphs verified: unique IDs, no dangling endpoints; source SHA manifest matches current CSV, discovery implementation and test. No source changes after the full suite; documentation-only counts appended.


## 2026-10-31 — Devices discovery result formatting

PC view revealed that Studio displayed `str(tuple[PrinterCandidate])`, which was unreadable to operators. Replaced it with localized candidate lines: provider/host, port, identified/unverified; unexpected result objects use a localized failure message. Regression: Studio candidate display + translation contract 2 passed; Ruff and JSON syntax clean. Full suite produced 675 passed/491 subtests but one uncaptured run exited 1 without a failure report; immediate captured repeat completed 675/491, exit 0 (83.50s). E14.01 remains Partial; confirm loaded UI source/build visually after the next isolated launch. No authenticated printer/AMS/command/debit activity.

Next: refresh root/external Graphify after the UI source/test/checklist changes; validate map endpoints, CSV BOM/IDs and source hashes. Then continue with the next unblocked integration gap. Release remains NOT READY.


Latest-source UI visual confirmation complete: launched Studio from `.venv312` with isolated data directory `D:/UFM_TestDiscoveryReview`; 1360×892 Windows Devices view now shows localized candidate lines and unverified confidence, no PowerShell overlay. Search returned OctoPrint and possible Bambu only. No auth, saved configuration, state/AMS read, printer command, or stock changes. App left open for operator review. CSV evidence E14.01 updated, status remains Partial. Source/test/CSV changed since last Graphify; refresh and verify map/hash manifests before next integration step.


## 2026-10-31 — Latest discovery UI and graph checkpoint

Source Studio launch with isolated `D:/UFM_TestDiscoveryReview` visually confirms the Devices results now show separate readable provider/host, port and unverified labels at 1360×892; the PowerShell console no longer overlays the app. Current full suite: 675 passed + 491 subtests, exit 0 (83.50s); targeted 11 relevant tests across discovery/display/translation; Ruff and JSON parse clean. No authenticated state or AMS, saved printer config, device control, print, or stock debit.

Graph final validation: root 6233/18135; traceability 13126/45401 (742 files); UFM 6185/22807; Spoolman 4920/15554; UFM↔Spoolman 11056/38361; enriched 29021/85880; combined 15897/40276. All seven graphs have unique IDs/zero dangling links; 742-entry manifest matches current discovery source, Studio code/strings, tests and CSV. 118 checklist rows/unique IDs, BOM retained; statuses 29/71/17/1.

Resume at the next unblocked integration requirement, preferably E06.02 authenticated read-only connection where the owner must manually enter the LAN code and confirm certificate trust. Do not automate the credential dialog. Auto-debit remains gated on unresolved ownership/fencing requirements E03.06/E03.07. Release is NOT READY. No commits/push/deploy.


## 2026-10-31 — Bambu pre-auth TLS identity read

`identify_bambu_printer()` succeeded against the discovered private-LAN candidate and parsed Bambu Lab P1S identity from the advertised/certificate chain. Fingerprint/root were only used in process memory and not persisted. No credentials or MQTT subscription; no status/AMS, print, commands, database write or stock change. An initial probe’s summary-print helper referenced a wrong field after the network call succeeded; the corrected read-only invocation confirmed the result. E06.02 stays Partial. Next step that needs operator involvement: owner inspects the explicit certificate fingerprint and manually enters the LAN code in the enrollment dialog; only then may authorized read-only MQTT state/AMS verification proceed. No automatic credential handling.


After the pre-auth P1S certificate identity probe, refreshed traceability and project graphs from the latest source/CSV. All 7 maps valid (unique IDs/zero dangling); manifest verified current checklist and changed files. Metrics in `D:/graphify-out/bambu-ufm/PROJECT_MAPS_UK.md`. Current blocker: authenticated Bambu live read requires operator review of fingerprint and manual LAN code entry. No AMS/status read has happened.

## 2026-10-31 — Portable Candidate launch checkpoint

Build/package check: `scripts/build_studio.ps1 -DestinationParent D:\UFM_TestBuild_20261031` completed; `scripts/write_studio_manifest.py 'D:\UFM_TestBuild_20261031\UFM Studio' --verify` verified 374 bundle files. EXE SHA-256 `855FA23E6F49F69F9701E5CBD091A6B7584F9EB09CF0DBC906642B38E4C91881`. Portable EXE PID/window was launched with explicit isolated data `D:\UFM_TestBuild_20261031\Data`; no installed shortcut, prior candidate, user database or system state was changed. UI inspection confirmed all four main pages: empty Filament metrics, Materials empty-catalog guidance, Devices candidate-only results (`[LOCAL_IP_REDACTED]:80` OctoPrint and `[LOCAL_IP_REDACTED]:8883` possible Bambu; both unverified), and System's internal/test-only release notice. This is a local one-PC launch/page smoke, not clean-Windows, DPI, keyboard, owner, installer or release acceptance.

No credentials or authenticated MQTT state/AMS were read; no printer controls, print, database writes, inventory debit, commit, push or deployment. E14.01 and E16.01 evidence appended to checklist; both remain Частково виконано; counts stay 29/71/17/1, 118 IDs. Root graph and external map hashes must be refreshed because the checklist changed.

Resume: (1) refresh Graphify and verify all seven graph JSONs / traceability hashes / CSV BOM and 118 unique IDs; (2) continue the next isolated integration step. Bambu authenticated read needs operator certificate approval and manual LAN-code entry in UFM; do not automate credential entry. Auto-debit remains disabled pending the unresolved shared writer fence/owner cutover. Public release remains NOT READY.

## 2026-10-31 — Candidate naming/localization correction

`src/ufm/integrations/printers/discovery.py` now emits the neutral display name `Bambu Lab`; `src/ufm/ui/studio_window.py` continues to display the localized confidence (`не підтверджено` / `unverified`), avoiding the redundant English `(possible)` suffix. Regression in `tests/integration/test_studio_window.py::test_studio_discovery_formats_candidates_instead_of_python_repr`. Verification: `pytest -q tests/integration/test_studio_window.py::test_studio_discovery_formats_candidates_instead_of_python_repr tests/integration/test_printer_discovery.py` = 10 passed; Ruff passed; mypy on the two production modules passed. Exploratory mypy including the full Studio test module returned 211 typing/stub diagnostics within that test file; this was not an established gate, and no bulk test typing rewrite was done.

E14.01 and E14.02 remain Partial. Rebuild portable candidate into a fresh folder (do not overwrite the previous manual-test artifact), verify manifest/hash, and inspect the Devices display in that EXE. Then refresh root and external Graphify and verify hashes/endpoints. No user data, printer authentication, AMS/status, commands, print, stock write, commit, push or deploy.


## 2026-10-31 — Qt UI teardown regression corrected; project suite green

`tests/integration/test_studio_window.py::test_inventory_column_chooser_keeps_identity_and_is_table_only` creates a secondary window to verify reloaded column settings. It previously only called `close()`; repeated Qt UI tests could leave that C++ widget pending when the shared QApplication shut down, producing a native access violation after all assertions passed. The test now calls `deleteLater()` and drains `DeferredDelete` before disposing the temporary SQLite engine. Evidence: target scenario 1 passed/exit 0; complete Studio module 74 passed/exit 0; complete project-scoped UFM suite 675 passed + 491 subtests, exit 0, 84.78 s. Ruff `src tests` clean; mypy `src` clean (139 source files).

Scope correction: a first rerun started from `D:\` and pytest collected unrelated site-packages and Graphify snapshots, ending in collection errors. It did not test UFM. The valid run used `--rootdir D:\Bot\Universal_Filament_Manager` and the explicit project `tests` directory; no false failure is attributed to the codebase.

The newly localized portable candidate remains at `D:/UFM_TestBuild_20261031_Localized/UFM Studio`, 374-file manifest verified, EXE SHA-256 `EA3414AF918CA194D8B8FF59ED291F3475219E80E235852E4E5728A962512877`, isolated data at sibling `Data`. Device candidate is still unverified. E14.01/E14.04/E16.01 remain Partial; release not ready. Refresh root and all external graph maps after updating test, checklist, progress and handoff; check traceability SHA manifest/endpoints. Then resume the next unblocked integration step. Preserve manual-only LAN code entry; no auth/state/AMS read or stock mutation occurred.


## 2026-10-31 — Printer-monitor errors localized and sanitized

`StudioWindow.printer_monitor_failed()` no longer displays a raw Python exception type. It maps the six known classes to localized, actionable but non-secret reasons, and unknown types to a generic message. `tests/integration/test_studio_window.py::test_studio_monitor_failure_messages_are_localized_and_do_not_expose_raw_errors` exercises every mapping and a secret/path-like sentinel under both language indices. Targeted UI+locale tests: 2 passed; Ruff clean on changed source/test; mypy `studio_window.py` clean; `studio_strings.json` parses with 464 keys; complete project-scoped pytest: 676 passed, 491 subtests passed, exit 0 in 84.49s.

E06.05 gained verified UI behavior but remains Partial for actual authenticated telemetry/AMS and hardware acceptance. E14.02 and E14.04 remain Partial. Manual certificate review/LAN-code entry is still the prerequisite to the next local read-only Bambu acceptance; no credential entry was automated.

Refresh current source Graphify (AST/code only; retain any existing semantic nodes), validate IDs/endpoints and record current metrics. If document semantic extraction remains unavailable, explicitly keep that scope caveat; do not overwrite a map with incomplete semantics. No printer command, stock change, print, live source DB edit, commit, push or deployment.

## 2026-10-31 — LAN discovery stale-result UX regression

Current candidate `D:/UFM_TestBuild_20261031_LocalizedErrors/UFM Studio` was inspected on Windows. A bounded scan operation returned status to `Готово`; the field contained two unverified candidates both before and after this repeat, so do not count this invocation as fresh candidate-detection proof. Observed code path: `StudioWindow.discover()` delegated to `work()` and only overwrote the field on completion, leaving stale candidate text visible while all page controls were disabled. Added bilingual `searching_candidates` to `studio_strings.json`, set before `work()`, plus `test_studio_discovery_replaces_stale_results_before_starting_scan`. Focused discovery UI tests: 2 passed; Ruff clean; JSON parse clean. This addresses misleading transient display, not scan accuracy or authenticated device status.

CSV E14.01 evidence updated; status remains Partial. Next: build a separate portable test artifact at `D:/UFM_TestBuild_20261031_DiscoveryUX`, verify package manifest/hash, then launch only the new test EXE with separate empty data dir and inspect current PC UI. Preserve previous candidate processes. Refresh root Graphify and external traceability after code/test/CSV/doc changes; verify unique IDs, endpoint integrity and source hashes. No credentials, production DB, printer command, print or stock mutation. Release remains NOT READY.

## 2026-10-31 — Discovery UX candidate verified on Windows

Built a separate portable candidate at `D:/UFM_TestBuild_20261031_DiscoveryUX/UFM Studio`; package manifest verifies 374 files, executable SHA-256 `1D2D7AE03450DA2D077A4484CF2545A6A19362653F7F1913AC823646B29CF1A4`. Started with a new isolated data root `D:/UFM_TestBuild_20261031_DiscoveryUX/Data`; System page showed the resolved path under that root. At the Devices view, immediate post-click screenshot displayed localized “Шукаю пристрої…” with controls disabled. Scan later returned `Готово` and listed two unverified candidates (Bambu and OctoPrint). This is a bounded read-only local discovery result, not authenticated state/AMS or printer acceptance. No credentials, printer commands, print, production DB or stock writes.

Verification after source change: focused UI discovery checks 2 passed; complete project-scoped pytest 677 passed + 491 subtests, exit 0 (84.04s); Ruff `src tests` clean; mypy `src` clean (139 files); JSON parses. Checklist E14.01/E14.04 remain Partial; BOM and 118 unique requirement IDs retained. Candidate window remains open on System. Next refresh current UFM Graphify and the external traceability/link maps after source/test/checklist/docs edits, verify JSON endpoint/ID integrity and source hashes; then resume the highest-priority safe integration gap. Release NOT READY; no commit/push/deploy.

## 2026-10-31 — Calculated finalization fails closed on local owner change

Added `test_review_only_accounting_authority_rejects_estimate_without_writes` and `test_authority_change_during_estimation_blocks_commit` to `tests/integration/test_calculated_finalization.py`. The race fixture transitions the isolated SQLite authority from UFM_ACTIVE to REVIEW_ONLY while the async calculation worker is awaited; finalization is rejected before the commit and the post-transition database snapshot remains byte-for-byte equivalent at the logical row level. Targeted authority checks: 2 passed; complete project-scoped test suite: 679 passed + 491 subtests, exit 0 in 83.88 s; Ruff clean for changed test.

This validates the local UFM authority recheck at finalization. It does not provide a shared Haspel/UFM lock or fence. Current linked Haspel `mqtt.js:processSlot()` direct Spoolman PATCH is still outside a common durable writer gate; another process/DATA_DIR and lost remote response remain unresolved. E03.07 remains Partial; auto-debit stays off. Checklist CSV retains UTF-8 BOM and 118 unique IDs. Refresh Graphify and external traceability after this change; all graph counts/health must be recorded as navigation evidence, not hardware acceptance. No production database, credentials, printer command or stock mutation.

## 2026-10-31 — E03.07 local-authority regression and graph checkpoint

Added fail-closed tests for calculated finalization when authority is REVIEW_ONLY and when the local state changes during the asynchronous calculation; both passed with no ledger/job/receipt mutation after the authority change. Full suite: 679 passed + 491 subtests, exit 0; Ruff clean. This proves only UFM local authority revalidation at commit. The linked Haspel `mqtt.js:processSlot()` remaining-weight PATCH remains outside the same durable fence, and any older/second Haspel process or DATA_DIR can still compete. Shared writer arbitration, ambiguous remote response recovery and cross-process exclusion remain blockers; E03.07 Partial, automatic debit disabled.

Root Graphify code map refreshed: 6274 nodes / 17383 links. External maps/traceability regenerated from selected snapshot; all 9 graph JSONs have unique IDs and zero dangling endpoints; traceability SHA snapshot matches changed UI source/strings, tests, checklist and this handoff. Exact counts/source hashes live in `D:/graphify-out/bambu-ufm/PROJECT_MAPS_UK.md`. Root code-only map skips 49 non-code items, so existing semantic text for new docs is not current. Do not treat map edges as runtime evidence.

Next: continue a safe unblocked integration gap. Authenticated Bambu status/AMS still requires owner-controlled TLS identity review and manual LAN-code entry. Isolated DiscoveryUX candidate remains open. No production database, secret, print, printer control, stock mutation, commit, push or deployment.


## 2026-10-31 — UFM↔Haspel authority/booking test checkpoint

Verified isolated cross-project API/service path: UFM `test_haspel_authority_client.py` + `test_haspel_cutover_preview.py` = 15 passed, 4 subtests; linked HaspelSync `node --test test/bookings.test.js` = 16 passed. Authority transfer prevents this service’s booking/debit HTTP call, unresolved intent/stale revision blocks activation, and uncertain/replayed outcomes remain non-retryable. Evidence is local mock/temporary fixtures only. It does not establish arbitration across multiple Haspel processes, distinct DATA_DIR roots, or any other Spoolman writer; E03.07 stays Partial and UFM auto-debit remains disabled. No live credentials, production DB/service, printer, print, or stock writes. CSV E03.07 evidence appended with UTF-8 BOM preserved.

Resume: run the existing full linked HaspelSync suite (only if isolated), inspect failures; then choose the next safe integration step. Refresh root/external Graphify only after source/checklist/docs state settles; graph is navigation, not runtime proof.


## 2026-10-31 — Stale authority cache regression checkpoint

Changed HaspelSync booking and authority transition/read paths to refresh the durable booking journal before authorizing a new booking or accepting an owner revision. Added a regression that simulates a second process transferring the durable owner while the first process still holds `LEGACY_ACTIVE` in memory; the stale process must reject before making the Spoolman HTTP call. `node --test test/bookings.test.js`: 17 passed, exit 0. This does not provide atomic arbitration for simultaneously writing processes, distinct `DATA_DIR` roots, or other Spoolman clients; E03.07 stays Partial and auto-debit remains disabled. Next: rerun the full linked HaspelSync test suite against this source change, refresh Graphify and verify snapshot hashes/endpoints.


## 2026-10-31 — Full HaspelSync verification after owner-cache refresh

After the `bookings.js` durable-owner refresh and stale-cache regression: full linked service suite `node --test --test-reporter=tap test/*.test.js` => 794 tests, 791 pass, 0 fail, 1 skipped, 2 todo; exit 0 (22.34 s). The two todo cases are actual unresolved A2L fixture gaps: unit 16 with AMS08/four trays yields `Z` for all slot labels. Do not invent a mapping because labels key persistent spool assignments; require protocol evidence and a migration-safe uniqueness rule first. E03.07 now has improved sequential stale-cache resistance but still lacks atomic shared file locking under concurrent processes and cannot coordinate other DATA_DIR/Spoolman writers; keep Partial and auto-debit off. E06.06 stays Partial for A2L capability. CSV has BOM and 118 unique IDs. Next: refresh root + external Graphify and verify all current source SHA entries plus node/edge integrity, then select next safe integration task.


## 2026-10-31 — Connector fixture regression checkpoint

UFM connector suite: `tests/integration/test_bambu_network_autofill.py`, `test_bambu_studio_import.py`, `test_bambu_lan_provider.py`, `test_spoolman_importer.py`, `test_spoolman_preview.py` => 64 passed + 45 subtests, exit 0 (8.58 s). Coverage is synthetic/mocked/temp SQLite and JSON only: Bambu LAN discovery normalization without access code, profile import constraints, MQTT report/AMS normalization, Spoolman source/ID-map importer, and preview/cutover checks. No live printer auth/MQTT, production Spoolman DB, real profile migration, or inventory write. E04.01/E04.03/E06.02/E06.05 remain Partial. Root Graphify is current for code and tests; refresh external traceability once final progress/handoff entries are appended.


## 2026-10-31 — HaspelSync shared journal lock checkpoint

Implemented an exclusive adjacent `bookings.json.lock` via `fs.openSync(..., "wx")`; all durable Haspel booking and authority mutations now re-read the journal inside that critical section. A competing process with the same exact DATA_DIR and lock-aware source cannot race through with stale owner state; busy lock rejects before the non-idempotent HTTP debit. A crash intentionally leaves a fail-closed lock requiring operator confirmation; no stale-lock auto-removal. Target suite `node --test test/bookings.test.js`: 18 passed. Full suite after change: 795 tests, 792 pass, 0 fail, 1 skipped, 2 TODO, exit 0. This is not global arbitration: old Haspel binaries, separate DATA_DIR roots, other Spoolman writers and UFM/remote distributed transition remain outside the lock. E03.07 stays Partial; UFM auto-debit remains disabled. Two known A2L TODOs remain open. Next: update/validate Graphify after source, CSV, ADR and handoff changes; then continue only with isolated lock-recovery/integration work.


## 2026-10-31 — Root/external Graphify checkpoint after journal lock

Root code-only graph after the Haspel journal lock/test: 6,275 nodes / 17,389 links; 49 non-code items (46 docs, 3 images) retain old semantic extraction. External refresh before this handoff edit: traceability 742/13,139/45,457; UFM 245/6,197/22,856; Spoolman 298/4,920/15,554; UFM↔Spoolman 543/11,068/38,410; enriched 29,036/85,944; Bambu source 12,955/32,565; profiles 2,942/7,711; combined 15,897/40,276. Integrity check then passed for all nine graphs (unique IDs, zero dangling); selected source SHA checks matched bookings source/test, authority client, BOM CSV, ADR and current handoff at that moment. Traceability manifest has 742 entries and omits PROJECT_PROGRESS_UK.md. Since this handoff changed after that validation, rerun external traceability/enrichment once, then perform final integrity/SHA check; do not alter source docs afterward unless refreshing again.


## 2026-10-31 — Повний UFM test suite та локальне discovery

Повторно виконано `.venv312\Scripts\python.exe -m pytest -q tests`: звіт pytest — 679 passed, 491 subtests passed за 84,36 с. Shell-session wrapper не віддав окремо exit code, тому фіксую лише summary; це не є доказом усунення раніше відтворених native Qt AV. Через Computer Use у вже відкритій ізольованій DiscoveryUX збірці оглянуто Filament/Materials/Devices і виконано рівно read-only пошук локальних пристроїв. Побачено два непідтверджені кандидати; не автентифікував принтер, не читав його стан/AMS, не зберігав LAN code, не запускав monitor/control/print, не торкався production DB або обліку. Device table лишається порожньою до підтвердженого enrollment; discovery output сам по собі не є встановленим зв’язком.

Checklist E06.02 доповнено цим обмеженим доказом, статус Partial та BOM/118 ID збережені. Наступний крок перед збереженням секрету/створенням постійного доступу потребує action-time підтвердження користувача на конкретний тестовий кандидат і destination UFM ізольованого профілю. Далі — тільки read-only Bambu state/AMS acceptance; ніякого тест-друку або automatic debit. Release залишається NOT READY.


## 2026-10-31 — Bambu UI firewall permission checkpoint

Focused regressions: `.venv312\Scripts\python.exe -m pytest -q tests/integration/test_bambu_network_autofill.py tests/integration/test_studio_window.py` — 83 passed, 9 subtests, exit 0. During a read-only identity/autofill attempt in the isolated test build, Windows Firewall displayed a permission request covering both private and public networks. Neither grant nor TLS trust was accepted. The UI remains waiting on this OS decision; no LAN access code or credential was entered/saved, no printer profile or production DB was changed, and no state/AMS query, command, print, or inventory/debit operation occurred. Resume: act only on the user’s choice about restricting the app to private networks; then recheck the test dialog. If approved, continue with TLS identity review and explicit confirmation before any credential persistence, followed by read-only status/AMS validation. Auto-debit remains disabled; E06.02 remains Partial; release is NOT READY.

## 2026-10-31 — Pause checkpoint: Bambu UI and external graph refresh

Focused local tests completed: `.venv312\Scripts\python.exe -m pytest -q tests/integration/test_bambu_network_autofill.py tests/integration/test_studio_window.py` — 83 passed, 9 subtests, exit 0. During isolated read-only UI discovery, Windows Firewall requested network access for UFM Studio on both private and public networks. Neither permission nor TLS trust was accepted; no LAN code was entered or persisted and no profile, credential, printer state/AMS, command, print, inventory, production DB, or debit was touched. The pending UI action needs an explicit user decision; do not broaden access to public networks.

External `enrich_graph.py` completed after the preceding project/checklist/handoff update: traceability 742 files / 13,139 nodes / 45,459 edges. Post-stage usage: 5-hour 36% remaining; weekly 15% remaining, so work paused per policy. Resume only when both exceed 15%: run `D:\graphify-out\bambu-ufm\tools\project_maps.py`, then `combine_enriched.py`; validate graph integrity and hashes against current sources/docs, and record refreshed metrics. The newly appended checkpoint itself makes traceability stale until that refresh. Do not claim live Bambu connection or AMS acceptance. Auto-debit stays disabled; release NOT READY.


## 2026-10-31 — Inline Bambu Studio autofill added to network enrollment

The network enrollment dialog in `src/ufm/ui/studio_window.py` now exposes a dedicated “Автозаповнити з Bambu Studio” action. It uses the existing `import_bambu_studio_profile(host)` path: the user first supplies/discovers the printer IP, then UFM matches the local Bambu Studio/Beta LAN profile to the TLS certificate serial and configured IP where present. Before copying the profile, the UI shows the host, serial, and certificate fingerprint for explicit review. The LAN code remains masked, is never shown in diagnostics, and is only handed to the existing connection-test/save flow after explicit confirmation; editing the host clears the previous serial/code confirmation. Missing/invalid/ambiguous profiles and identity disagreement return localized guidance.

Regression checks: `.venv312\Scripts\python.exe -m pytest -q tests/integration/test_bambu_network_autofill.py tests/integration/test_bambu_studio_import.py tests/integration/test_studio_window.py` — 93 passed, 9 subtests, exit 0. Ruff passed on changed Python modules; mypy passed for `bambu_studio.py` and `studio_window.py`; the two locale JSON dictionaries and placeholders were checked. A separate internal portable candidate was built at `D:\UFM_TestBuild_20261031_BambuStudioAutofill1\UFM Studio`; its 374-file manifest and 180-source provenance verified, EXE SHA-256 `0EE879AD2157A5199C67FD87AFA027D30809F42F7797980EB174AF044E26E4EA`. An isolated empty-data startup/capture exited successfully; the candidate was launched without network access.

Acceptance limits: no real `BambuStudio.conf` was opened in this stage, no actual LAN code was read or persisted, and no live TLS identity, authenticated state/AMS, printer command, print, production database, or inventory change was exercised. Private-only firewall access for an earlier candidate was denied by Windows (`Access denied`); the new candidate has no firewall exception. E06.02 therefore remains `Частково виконано`. The feature is source/test/build verified but still needs owner-reviewed manual use on the isolated candidate and, if permitted locally, read-only authenticated Bambu acceptance. Auto-debit remains disabled. Next: refresh root/external Graphify after this checkpoint; validate all graph IDs/endpoints and the 742-source SHA manifest against current files. Record final metrics in PROJECT_PROGRESS_UK.md, then resume the next safe unblocked integration item. The maps remain navigation evidence, not live-printer acceptance.


## 2026-10-31 — Visual review of Bambu Studio autofill candidate

The user-provided screenshot shows the Devices page of a test build. It visibly has distinct actions for “Bambu: find Studio profile” and “Autofill from network”; the P1S appears in the table, and discovery results are marked unverified. The new inline Studio autofill action is inside the network enrollment dialog, so it is not visible on this main page.

A current Computer Use capture of the isolated Candidate instead showed the Filament page with an empty “Consume manually” modal. It was left untouched: no text was entered and neither OK nor Cancel was clicked; no accounting operation was submitted. The network wizard was not opened, so visual review of the new button’s label, layout, and availability on the actual PC remains open. Tests and the packaged build do not replace this visual acceptance. E06.02 remains Partial; this stage does not confirm a live printer connection, authenticated state/AMS, or debit.

Resume only from a safe window with no pending manual operation: open the enrollment wizard and visually inspect the Studio autofill dialog. Do not perform a network call or save a LAN code during that visual inspection. After this checkpoint, refresh Graphify traceability/project/enriched maps and verify source hashes and endpoints. No production database or accounting state was touched.


## 2026-10-31 — GitHub Actions mypy dependency correction

All three initial push-triggered CI runs failed at MyPy after Ruff succeeded; tests and wheel build were skipped. Representative logs show only missing `PySide6.Qt*` implementations, which cause cascading Any subclass/type errors. `.github/workflows/ci.yml` installed only the `dev` extra despite desktop UI modules being included in the mypy target. Corrected CI installation to `.[dev,desktop]` so PySide6-Essentials is present on the cross-platform matrix.

Local Python 3.12 verification: Ruff clean, MyPy clean across 139 files, pytest 683 passed + 491 subtests (87.93s). Remote CI for Linux/macOS/Windows and Python 3.12–3.14 is still pending. After push, inspect each matrix result; if Qt wheel installation fails on a platform/version, adjust only from the observed logs.


## 2026-10-31 — Guard Windows-only attributes in cross-platform typing

CI run `41211558386` showed that the new desktop dependency fixed missing Qt imports but Linux/macOS MyPy then rejected `ctypes.WinDLL` and `subprocess.CREATE_NO_WINDOW`. Replaced direct attribute access with guarded `getattr`: suspend detector fails closed to `None` without WinDLL; the subprocess uses the Windows no-window flag only when present and on Windows.

Local verification: Ruff clean, MyPy clean across 139 source files, focused Windows power/calculation-worker tests 10 passed + 5 subtests. Next, push and verify all CI matrix jobs on Linux/macOS/Windows and Python 3.12–3.14. Earlier CI results are historical and should not be treated as current after the follow-up commit.


## 2026-10-31 — Normalize expected Windows paths in CI tests

The Windows matrix reached pytest after MyPy was fixed and exposed two incorrect assertions in `tests/unit/test_foundation.py`: the implementation uses `Path.resolve()`, which canonicalizes the GitHub runner's `runneradmin` profile path to its short `RUNNER~1` form. Updated the expected values to `config.resolve()` and `root.resolve() / "data"`; application path behavior and the no-write assertion are unchanged.

Local evidence after this change: `test_foundation.py` 20 passed + 20 subtests; Ruff clean; MyPy clean for 139 source files; focused power/worker tests 10 passed + 5 subtests. Next, verify the complete GitHub matrix (Linux/macOS/Windows × Python 3.12/3.13/3.14), including packaging and installed-wheel checks.


## 2026-10-31 — GitHub Actions cross-platform test fixes

Run `41211711591` showed Ubuntu Qt import failures from missing `libEGL.so.1`; run `41211933317` confirmed that cause on all Ubuntu Python versions, exposed Windows wheel-smoke Unicode encoding failures, and had two single-occurrence macOS reconnect cleanup races. Added Ubuntu-only `libegl1` installation; changed isolated wheel-check child interpreter calls to `-X utf8 -I`; synchronized the two existing monitor tests on the second provider event stream before requesting stop. Local validation: wheel + installed-wheel script exit 0, Ruff/py_compile/diff-check clean, both focused tests passed in four consecutive runs (2 per run). The fresh GitHub matrix has not yet run; preserve E16.08 as Partial. No printer, production DB, account data, or stock was accessed.


## 2026-10-31 — Guarantee provider disconnect when stream cleanup fails

Fresh CI run `41212790030` verified the Ubuntu-only `libegl1` step: Ubuntu Python 3.12 and 3.13 jobs completed successfully; macOS 3.13 also passed. macOS 3.12 still failed the existing stale-provider reconnect test after the second event stream had started: `provider.disconnect()` was not observed for provider 2. Code review found the cleanup sequence awaited cancellation/gather and stream `aclose()` before disconnect in a single `finally`, so an exception from stream cleanup could skip releasing the provider. Nested the provider disconnect in an unconditional inner `finally`; cleanup errors still propagate, but socket/provider release is always attempted. All three existing stop/reconnect tests passed four consecutive local runs (3 passed per run); Ruff and mypy pass for modified modules. Windows wheel jobs and remaining matrix jobs were still running at this checkpoint. New run required after this source fix.


## 2026-10-31 — Cross-platform GitHub Actions matrix is green

GitHub Actions run `41213065696` on commit `afa1d232ec577db5cd00c5ffffe4e1b0e977f86e` completed with conclusion `success`: all 9 OS/Python jobs passed (Ubuntu, macOS, Windows × Python 3.12, 3.13, 3.14), including lint, mypy, full pytest, wheel/sdist build and isolated installed-wheel checks. This verifies the Linux `libegl1`, Windows UTF-8 wheel smoke and provider disconnect cleanup changes in the remote matrix. E16.08 remains Partial: CI green is not a public-release approval; unsigned development build, incomplete SBOM/licensing/signing, clean-install and owner acceptance plus other checklist gates remain open. Source changes are at commits `a5ff01e` and `afa1d23` on private `main`. No printer or production data was accessed.
