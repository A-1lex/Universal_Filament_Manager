# Реєстр інтерфейсів Spoolman і HaspelSync

Статичний аудит 2026-10-27. Це каталог вихідного функціоналу для перенесення,
а не твердження, що ці кнопки вже є у Qt або перевірені у працюючому сервісі.

Джерела Spoolman (нижче `S/`):
`D:/Filament_Manager/localization/spoolman/client/src/`.
Джерела власного HaspelSync (`H/`): `linked-stack/haspelsync/`.
Downloaded HaspelSync: `D:/Filament_Manager/localization/haspelsync/`.
Порівняння стосується цих локальних snapshot, не поточного GitHub upstream.

## Повнота й відтворення

Початкову матрицю [124 функцій](FEATURE_MATRIX_UK.csv) збережено.
Наведені тут S/H/A ID позначають групи сценаріїв для деталізації цієї матриці;
вони не замінюють F001–F124. Пропоноване місце у Qt — ціль перенесення.

`scripts/inventory_legacy_ui.py` створює [кандидатів елементів керування](LEGACY_UI_CANDIDATES.csv)
та [маніфест вихідних файлів](LEGACY_UI_SOURCE_MANIFEST.json) із SHA256.
Знайдено 95 файлів та 777 кандидатів: Spoolman 329, downloaded HaspelSync 210,
власний HaspelSync 238. Це поля, literal controls і click bindings, включно
з повторами та можливими прихованими/закоментованими елементами. Усі записи
мають `needs-semantic-review`; це не кількість функцій і не завершений паритет.
Динамічні кнопки React/Refine можуть не потрапити до лексичного пошуку.

## Spoolman: екрани, діалоги й дії

| ID | Підтверджена група дій | Доказ S/ | Майбутнє місце Qt |
|---|---|---|---|
| S01 | Home: лічильники, переходи до списків/створення, welcome/help | pages/home/index.tsx:22,41,98,125 | Огляд |
| S02 | Котушки: список, сортування, фільтри, колонки, pagination | pages/spools/list.tsx:211,264,275,284 | Склад |
| S03 | Show/Edit/Clone/Adjust у списку котушок | pages/spools/list.tsx:214,224 | Склад / дії котушки |
| S04 | Архів/розархівування; confirmation, крім порожнього залишку | pages/spools/list.tsx:193,198,295 | Склад / Архів |
| S05 | Картка котушки, filament link, Adjust, QR, Archive | pages/spools/show.tsx:94,118,123,137 | Картка котушки |
| S06 | Корекція: length/weight/measured_weight, OK/Cancel | pages/spools/functions.tsx:33,55,225,241,249 | Картка / Операція |
| S07 | Створення/клонування котушки, кількість ±, Save/Save-and-add | pages/spools/create.tsx:254,261,269,280 | Нова котушка |
| S08 | Дати, filament, ціна, initial/tare/used/remaining/measured, location/lot/comment | pages/spools/create.tsx:308,378,448,474; edit.tsx:234,263,291,361,422 | Редактор котушки |
| S09 | Filaments: список, колонки, фільтри, Show/Edit/Clone/Add spool | pages/filaments/list.tsx:140,146,170,183 | Матеріали |
| S10 | Картка filament → відфільтровані котушки | pages/filaments/show.tsx:48,63 | Матеріал / Котушки |
| S11 | Створення/клонування/редагування filament, Save/Save-and-add | pages/filaments/create.tsx:108,112,119; edit.tsx:84,88 | Редактор матеріалу |
| S12 | Vendor/name, single/multi color, напрям кольорів, матеріал, ціна, density/diameter, маси, температури, article/comment/external_id | pages/filaments/create.tsx:138,171,210,228,315,341; edit.tsx:335 | Редактор матеріалу |
| S13 | External filament import: пошук, вибір, OK/Cancel | components/filamentImportModal.tsx:35 | Матеріали / Каталог |
| S14 | Vendors: список, Show/Edit/Clone, фільтри/колонки/pagination | pages/vendors/list.tsx:91,96,113,126 | Виробники |
| S15 | Vendor create/clone/edit/show: назва, примітка, тара, external_id; Save-and-add | pages/vendors/create.tsx:57,61,72,83,94; edit.tsx:56,60,121; show.tsx:31 | Виробники / Редактор |
| S16 | Локації: add/rename/delete, drag reorder локацій і котушок | pages/locations/components/locationContainer.tsx:97,105,184; location.tsx:169,180 | Склад / Локації |
| S17 | Картка котушки локації: Edit/Show | pages/locations/components/spoolCard.tsx:169,172 | Локації / Картка |
| S18 | General settings: валюта, base URL, округлення цін, Save | pages/settings/generalSettings.tsx:67,82,98,108 | Налаштування / Загальні |
| S19 | Extra fields окремо для spool/filament/vendor | pages/settings/index.tsx:59,65,92 | Налаштування / Додаткові поля |
| S20 | Extra fields: ключ, порядок, назва, тип, одиниця, default/choices/multi; Add/Edit/Save/Cancel/Delete, confirmation | pages/settings/extraFieldsSettings.tsx:131,190,553,611,623,641,655,732 | Редактор додаткових полів |
| S21 | Сканер QR та інших кодів: камера, modal, пошук котушки, помилки | components/qrCodeScanner.tsx:14,35,48,49 | Склад / Сканувати |
| S22 | Друк етикеток: вибір котушок, select all, архів, Continue | pages/printing/index.tsx:51,64; spoolSelectModal.tsx:134,161,179,197 | Етикетки / Вибір |
| S23 | Presets: select/add/duplicate/delete/name/template, довідка шаблонів | pages/printing/spoolQrCodePrintingDialog.tsx:246,261,267,275,291,319,329,349 | Етикетки / Шаблони |
| S24 | QR/HTTP URL/content preview, текст і його розмір | pages/printing/qrCodePrintingDialog.tsx:81,103,112,117,126 | Етикетки / Вміст |
| S25 | Skip/copies/border/scale; папір, ряди/колонки, поля, проміжки; Save image/Print | pages/printing/printingDialog.tsx:280,306,332,351,395,411,442,468,496,622,747,778,818,821 | Етикетки / Друк |
| S26 | Мова; system/light/dark theme; scanner у header | components/header/index.tsx:23,28,58,66,71 | Верхня панель / Налаштування |
| S27 | Збереження sort/filter/page/columns, фільтри numeric/date/text, reset/apply | utils/saveload.ts:17,45,94; components/column.tsx:43,54,104,115,161,172 | Усі таблиці |
| S28 | Help, create links, integration-status link | pages/help/index.tsx:35,40,43,48 | Довідка |

Маршрути в `S/App.tsx:184–225` включають list/create/clone/edit/show для
spool/filament/vendor, `/spool/print`, locations/settings/help, home і fallback.
Стандартні Refine-кнопки перевірені за SHA512-підтвердженим пакетом 6.0.3:
List/Create, Show/List/Edit/Delete/Refresh, Edit/List/Refresh/Delete/Save,
Delete confirmation. Деталі: [REFINE_DEFAULT_ACTIONS_UK.md](REFINE_DEFAULT_ACTIONS_UK.md).
Це завершує статичний каталог E02.01; live UI приймання лишається окремим.

## HaspelSync: спільний функціонал і локальні доповнення

| ID | Підтверджена група дій | Доказ H/ | Майбутнє місце Qt |
|---|---|---|---|
| H01 | Menu, printer picker, server/printer/raw log, тема, settings/logout/mobile menu | public/menu.js:140,161,194,493,568,678 | Навігація / Пристрої / Діагностика |
| H02 | Dashboard: Spoolman/MQTT status, режим, оновлення, monitoring toggle | public/index.html:30,43,76 | Пристрої / Огляд |
| H03 | AMS expand; Create/Merge/Create with filament; Show info; Assign/Unassign | public/frontend.js:523,817,903,927,1275,1562,1689 | Пристрої / AMS |
| H04 | Existing/new spool tabs, додавання/видалення кольору | public/frontend.js:3305 | AMS / Прив’язати котушку |
| H05 | Spool/Filament tabs, редагування полів Save/Cancel | public/index.html:103; frontend.js:1955,1986,2170 | Картка котушки / Матеріал |
| H06 | Поточний/останній друк, clear, summary, sliced-file lookup help | public/frontend.js:2550,2676,2706,2858,2885 | Друки / Деталі |
| H07 | Notice/Got it/Open settings, summary/help/info dialogs | public/index.html:91,103,114,125,133 | Сповіщення / Діалоги |
| H08 | Settings: Printers/Spoolman/Tracking/Logging/Access/Web UI/System, Save/Discard | public/settings.js:20; settings.html:138 | Налаштування |
| H09 | Printer Add/Edit/Delete, name/id/IP/access code, Test/Save/Cancel, logging overrides | public/settings.html:56,149; settings.js:831,1374,1403 | Пристрої / Підключення |
| H10 | API key create/name/scopes/copy/revoke, API docs | public/settings.js:1565,1605,1646,1707; settings.html:161 | Налаштування / Інтеграції |
| H11 | Diagnostics download, reconnect, pause/resume monitoring, restart service, confirmation | public/settings.html:127,183 | Діагностика / Служба |
| H12 | Web preferences: мова, світла/темна тема | public/settings.html:84 | Налаштування / Вигляд |
| H13 | Logs: server/printer/raw MQTT, picker, download | public/logs.html:39,47; logs.js:83,109 | Діагностика / Журнали |
| H14 | Export: Full/Anonymized/Cancel, scope checkbox | public/export.js:30,61 | Експорт / Діагностика |
| H15 | API explorer: search, key, expand/collapse, parameters, send/download, SSE, copy | public/api.html:51,58,61; api.js:208,444,466 | Інтеграції / API console |
| H16 | Login/password, мова/тема | public/login.html:46,50,66 | Захист доступу / за потреби API |
| H17 | Локальний облік: printer/date/language filters, refresh, KPI, History/Spools/Reports | public/accounting.html:20,25,31,37 | Облік / Огляд |
| H18 | Локальна історія, only-review, pending/uncertain review | public/accounting.html:42; accounting.js:61,74 | Облік / Звіряння |
| H19 | Gross/tare/net, apply; price/currency/basis/save, історія зважувань | public/accounting.html:52,60,68 | Котушка / Зважування / Вартість |
| H20 | Resolve: баланс, applied/not_applied, note, cancel/confirm | public/accounting.html:78; accounting.js:134,149 | Облік / Розв’язати невизначеність |
| H21 | CSV export звіту; екран історії обмежений 100 записами | public/accounting.html:72; accounting.js:74,210,213 | Звіти / Експорт |

Побайтове порівняння `public/`: local-only `accounting.css/html/js`;
змінені `menu.js` та `i18n/{de,en,pl,uk}.js`; решта файлів однакова.
`src/settings.js` у двох snapshot також однаковий. Accounting backend routes:
`H/src/routes.js:646,654,666,685,701,715,728`.
Зберегти ці доповнення обов’язково; вони не є новими побажаннями.

### Налаштування HaspelSync, які не можна втратити

Схема `H/src/settings.js`, 27 ключів; UI генерується з неї
(`public/settings.js:14,1099`), API — `src/routes.js:1275,1279`.

- Spoolman (`:56–87`): SPOOLMAN_ENDPOINT, SPOOLMAN_IP, SPOOLMAN_PORT,
  SPOOLMAN_SUBFOLDER, SPOOLMAN_FQDN.
- Tracking (`:95–118`): MODE, LEGACY_MODE (вимагає restart),
  AUTO_ASSIGN_THIRD_PARTY, PRINT_RESET_MINUTES.
- Sync (`:127–160`): UPDATE_INTERVAL, SET_LOCATION, ARCHIVE_EMPTY_SPOOLS,
  EMPTY_SPOOL_THRESHOLD, NEVER_MERGE_IF_TAG.
- Reconnect (`:167–186`): OFFLINE_CHECK_INTERVAL, OFFLINE_MAX_INTERVAL, MAX_RETRIES.
- Logging (`:195–265`): LOG_LEVEL, LOG_CATEGORIES, MQTT_TRACE,
  MQTT_TRACE_MAX_SIZE_MB, MQTT_TRACE_KEEP, LOG_MAX_SIZE_MB,
  LOG_KEEP_SERVER, LOG_KEEP_PRINTER.
- Access (`:274–281`): AUTH_PASSWORD, ALLOWED_HOSTS.

У нативній архітектурі Spoolman endpoint, browser auth і service restart
можуть змінити форму. Зберігається потрібний сценарій: вибір джерела імпорту,
контроль доступу до зовнішнього API, відновлення внутрішнього worker.
Не залишати другу незалежну систему списування заради старої назви кнопки.

## Автоматичні сценарії без кнопок: початковий реєстр

| ID | Поведінка для перенесення | Доказ H/ | Qt / внутрішній компонент |
|---|---|---|---|
| A01 | Зберегти/відновити початок друку | src/printstate.js:60,87 | Durable job worker |
| A02 | Запам’ятати sliced file та історичний slot mapping | src/printstate.js:100,114,129,148 | Job evidence / mapping |
| A03 | Виявити й перевірити sliced file, відповідність plate/job | src/gcode.js:71,513,556,671,720,761 | Парсер / downloader |
| A04 | Повна розрахункова витрата | src/gcode.js:1031 | Політика розрахунку |
| A05 | Частковий друк, extrusion/layers | src/gcode.js:1062,1112,1197,1246,1319 | Політика часткових витрат |
| A06 | Decode Studio mapping, slots, refill split | src/gcode.js:859,898,973,1383,1416 | Сегменти / AMS |
| A07 | Стійкий booking attempt та повтор / uncertain guards | src/bookings.js:63,100,122,132,137 | Ledger finalization / review |
| A08 | Вартість на момент операції; зважування та невизначеність | src/accounting.js:74,89,104,111,134,143 | Вартість / inventory evidence |
| A09 | Звіти за період | src/accounting.js:156 | Звіти |

Це ще не повний E02.04: додати AMS/RFID matching, creation/merge,
reconnect/backoff, logging rotation, SSE, caches та Spoolman background work
з окремими доказами. Резервування UFM не приписувати legacy без доказів.

## Контракт локальних дій: перша деталізація E02.03

| Дія | Вхід і стан | Результат / помилки / повтор |
|---|---|---|
| H19: застосувати зважування | Spool, gross/tare, числове net; до підтвердження показати результат | Backend `routes.js:666`, `accounting.js:111,134`; невизначена відповідь потребує review, не сліпого retry |
| H19: зберегти ціну | Spool, price, currency UAH/EUR/USD/PLN, basis mass, expectedRevision | `accounting.js:74,89`: зберігається профіль; історична ціна операції фіксується окремо; stale revision не ігнорувати |
| H20: вирішити booking/weighing | Запис pending/uncertain, applied/not_applied, примітка, Confirm/Cancel | `routes.js:685,701`, `bookings.js:137`, `accounting.js:143`: рішення оператора; не видавати натискання за фізичний доказ |

Точні validation ranges, повідомлення, disabled states, confirmation і replay
для всіх інших дій ще потрібно описати. Тому E02.03 лишається частковим.

## Класи вимог та межі приймання

1. **Зберегти наявне:** підтверджені S/H/A сценарії, власний accounting,
   історію й safeguards. Це основа паритету.
2. **Покращити:** сучасний Qt UX, єдиний атомарний ledger, явний provenance,
   пояснення невизначеності, durable ingestion, відсутність browser/Docker.
3. **Нові побажання:** додаткове фізичне керування принтером, підписані
   оновлення, нові інтеграції/OS та інші непідтверджені legacy можливості.

Не всі 124 F-вимоги ще зіставлені з цими класами та конкретними S/H/A діями.
E02.06 частковий: ID і місця Qt є для груп, але ще не для кожної атомарної дії.
E02.07 ще потребує повного зіставлення. E02.08 описаний у
[25 еталонних сценаріях](PARITY_ACCEPTANCE_SCENARIOS_UK.md); їх виконання
не заявляється. Наступне: розгорнути групи в атомарний
реєстр, перевірити Refine defaults і завершити контракти/еталонні сценарії.
Камера, друк етикеток і реальна поведінка форм в цьому аудиті не тестувалися.
