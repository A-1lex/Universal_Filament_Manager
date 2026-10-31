# Фонові сценарії та сумісність API legacy

Статичний аудит локальних snapshot, 2026-10-27; деталізація E02.04–E02.05.
Мережу, контейнери, принтери, реальні БД й конфігураційні секрети не читали
і не змінювали. Наведений endpoint означає реалізацію в джерелах, а не
перевірену доступність сервісу чи прийнятий контракт нового UFM.

Позначення джерел: **S/** = `D:/Filament_Manager/localization/spoolman/`;
**H/** = `D:/Bot/Universal_Filament_Manager/linked-stack/haspelsync/`;
**D/** = `D:/Filament_Manager/localization/haspelsync/`.
Посилання `файл:рядок` прив'язані до поточного локального вмісту.
Контекст екранів: [LEGACY_UI_CATALOG_UK.md](LEGACY_UI_CATALOG_UK.md).

## E02.04: фонові сценарії

### HaspelSync та власні доповнення

| ID | Тригер, поведінка, завершення / відмова | Точні докази H/ | Вимога перенесення |
|---|---|---|---|
| B01 | Старт чекає healthy Spoolman, готує spool extra field `tag`, запускає монітори. Bambu vendor вирішується ліниво перед створенням filament | src/service.js:27,52,67; src/spoolman.js:285,340,361 | Явний статус bootstrap, помилка підготовки не має виглядати як робочий моніторинг |
| B02 | MQTT підписується на `device/{id}/report`; delta та повні повідомлення накопичують стан, обробка AMS прив'язана до доступності Spoolman | src/mqtt.js:528,1621,2520,2551 | Зберегти джерело/час спостереження й керовану паузу обробки |
| B03 | RFID: нормалізація `tray_uuid`, material/color, читання JSON-encoded `extra.tag`; existing match вимагає material+tag+точний набір кольорів | src/ams.js:275,288,295,303; src/mqtt.js:2003,2010 | Не видавати збіг кольору за фізичний RFID-доказ |
| B04 | External catalogue matching, потім internal filament через external_id. Merge має слабші евристики material/color; mass у діапазоні ±15%, або empty/never-used; NEVER_MERGE_IF_TAG блокує tagged candidate | src/ams.js:310,412,439,461,470; src/mqtt.js:2166 | Показати походження та впевненість matching; евристика merge не дорівнює точному existing match |
| B05 | Automatic mode виконує merge/create/create-with-filament; manual лише пропонує дію. Перед create очікує remain, щоб частково використана котушка не стала повною. Merge записує тільки tag. Після успішної мутації перечитує стан | src/mqtt.js:1883,2003,2155,2176,2191,2196,2206,2217; src/spoolman.js:387,420,470,525 | Зберегти режим, очікування й truthful success; невдалий HTTP-запис не вважати успіхом |
| B06 | Архівні котушки читаються для tag lookup, але не для merge/location; third-party mapping та auto-assignment окремі від RFID | src/spoolman.js:110,120; src/mqtt.js:2369,2391,2406,2445 | Не створювати дубль лише через архівність; ручна прив'язка має пріоритет і походження |
| B07 | Location claim/release, звільнення зниклих слотів, перейменування локацій принтера; archive-empty за налаштуванням і threshold | src/location.js:55,84,116,193,211; src/mqtt.js:1182,1848 | Зберегти власника локації, не очищати чужі локації |
| B08 | TCP probe 8883 перед reconnect. Після невдач експоненційна затримка `min(base*2^failures,max)`; успіх скидає backoff. MAX_RETRIES=0 означає безліміт, інше значення вимикає monitoring після ліміту | src/utils.js:337; src/mqtt.js:2735,2744,2752,2783,2830,2847 | Стани offline/retrying/disabled та явне відновлення, без циклу гарячих повторів |
| B09 | Монітор MQTT продовжує reconnect, навіть коли Spoolman down. Health Spoolman: стартовий цикл 30 с, background 60 с. Зміна endpoint скидає vendor/lastSpoolData, ставить first_run та запускає bootstrap | src/mqtt.js:2830,2931,2954; src/service.js:98 | Не зв'язувати доступність принтера з доступністю складу; не змішувати кеші різних джерел |
| B10 | SSE clients реєструються на /api/events, видаляються при close; зміни slot/state передаються broadcast, environment throttled, незмінні слоти не транслюються повторно | src/routes.js:376,384; src/mqtt.js:57,69,98,2475; src/ams.js:515 | SSE є каналом оновлення UI, не durable журналом подій і не гарантією replay |
| B11 | Кеш external filaments використовує TTL; невдалий fetch не кешується. Update-check кеш 6 год; snapshot AMS та Spoolman скорочує зайву обробку | src/spoolman.js:147,154; src/update.js:15,76,117; src/state.js:1; src/ams.js:485 | Розрізняти cache/observed state/обліковий факт; invalidation при зміні джерела |
| B12 | Logger серіалізує записи по файлу, ротує за maxBytes/keep; читання перетинає rotated files; raw MQTT trace окремий, керований налаштуванням | src/logger.js:55,351,404,413,446,486; src/mqtt.js:2561; src/settings.js:195 | Зберегти обмеження диска, рівні/категорії та server/printer/raw розділення |
| B13 | Початок друку, sliced path і історичні slot mapping/refills/spools зберігаються та відновлюються після старту; reset має окрему поведінку | src/printstate.js:60,87,100,114,129,148,170; src/mqtt.js:611,1027,1261 | Durable ідентичність job та історична прив'язка, а не поточний slot як доказ минулого |
| B14 | FTPS шукає slice в root/cache за кандидатом/часом, перевіряє facts/plate/job; bounded retry: 3 спроби, 30 с | src/gcode.js:34,71,254,513,556,720,761,1454,1456,1476,1514; src/mqtt.js:126,162 | Не приймати випадковий 3MF за поточну роботу; невизначеність лишати видимою |
| B15 | Full/partial consumption; partial враховує layers/extrusion; Studio mapping та refills розбивають витрату між слотами; matchConsumption ранжує кандидатів, ручні mapped мають пріоритет | src/gcode.js:859,898,1031,1112,1197,1246,1319,1383,1416; src/ams.js:661; src/mqtt.js:1377 | Зберегти оцінюваність витрати, unmatched/ambiguous не списувати сліпо |
| B16 | Власний booking journal зберігає intent перед non-idempotent HTTP, request hash конфліктує при зміні параметрів; pending/uncertain блокують автоматичне повторне списання; resolve фіксує рішення оператора | src/bookings.js:17,33,63,100,122,132,137; src/spoolman.js:663,670,675 | Обов'язково зберегти локальні safeguards; це власне доповнення, не весь downloaded upstream |
| B17 | Власний accounting фіксує ціну на момент операції, weighing intent/result, uncertain review та звіт за період | src/accounting.js:74,89,104,111,134,143,156; src/routes.js:646,666,685,701,715 | Не втратити вартість, історію зважувань та конфлікти revision |
| B18 | Restart спершу закриває MQTT, затримує exit на 300 мс для HTTP-відповіді, використовує code 75; supervisor допускає 3 рестарти/60 с | src/service.js:132,140; src/supervisor.js:17,20,21,36; src/routes.js:1574 | У native UFM переноситься кероване відновлення worker; Docker/process restart не зобов'язаний копіюватися буквально |

Побайтове порівняння `H/src/*.js` з D/: лише локально `accounting.js`,
`bookings.js`; відрізняються `config.js`, `mqtt.js`, `openapi.js`, `routes.js`,
`spoolman.js`, `state.js`. Решта JS у цій множині однакові. Отже B16–B17 —
підтверджені власні доповнення; B02/B05/B15 містять і локальні зміни.
Не називати весь змінений файл повністю власною розробкою чи upstream.

### Spoolman

| ID | Сценарій | Точні докази S/ | Межі |
|---|---|---|---|
| B19 | Startup створює scheduler для DB та external DB | spoolman/main.py:206,236,238,239 | Реєстрація задач у source; фактичний запуск не перевірений |
| B20 | External DB sync одразу та циклічно за configured interval; 0 вимикає periodic sync; результат записує filaments/materials cache | spoolman/externaldb.py:140,233,234,243,257,259,261,263 | Каталог доступний через мережу лише в runtime, у цьому аудиті мережевих викликів не було |
| B21 | Hishel disk cache з fallback у RAM при PermissionError; parsed catalogue memoized за mtime+size | spoolman/externaldb.py:27,38,186,190,202; spoolman/filecache.py:9 | Не тотожний durable inventory |
| B22 | Optional metrics щохвилини; automatic SQLite backup о півночі, rotation збережених backup; незмінну БД не ротує, є обмеження частоти | spoolman/database/database.py:170,202,217,244,256,273,292,298 | Backup не є новим UFM snapshot/restore acceptance; для інших DB scheduled SQLite backup не виконується |
| B23 | Timed log rotation опівночі, backupCount=5 | spoolman/main.py:196 | Не плутати з HaspelSync max-size rotation |
| B24 | WebSocket subscription tree доставляє зміни й прибирає disconnected subscribers; scan relay має окремий manager та reader identity | spoolman/ws.py:30,47,83,107,126,143; spoolman/scanrelay.py:46; spoolman/api/v1/tag.py:112,229,247 | Це WebSocket, не SSE HaspelSync; це relay/API для читача, не доказ установленого RFID hardware |

### Межа legacy та нового UFM

Резервування stock, єдиний атомарний ledger, durable ingestion inbox,
нативні Qt worker/recovery, нові гарантії exactly-once та підписані оновлення
не приписуються legacy цим аудитом. Legacy booking — intent/uncertain guard
навколо зовнішнього Spoolman HTTP, а не атомарна транзакція двох сервісів.
Пошук reservation/reserve у S/spoolman та H/src не виявив реалізації резервування
складу; це обмежений негативний доказ, не твердження про всі можливі плагіни.

## E02.05: каталог API для рішення про сумісність

### Spoolman

Шляхи нижче відносні до configured base path. Монтування `/api/v1`:
S/spoolman/main.py:57. Таблиця отримана статичним AST-читанням декораторів,
без import/запуску застосунку. `WEBSOCKET` означає протокол, не HTTP-метод.
Докази таблиці відносні до `S/spoolman/api/v1/`.

| Метод / протокол | Endpoint | Доказ |
|---|---|---|
| GET | `/api/v1/export/spools` | export.py:28 |
| GET | `/api/v1/export/filaments` | export.py:46 |
| GET | `/api/v1/export/vendors` | export.py:60 |
| GET | `/api/v1/external/filament` | externaldb.py:26 |
| GET | `/api/v1/external/filament/search` | externaldb.py:37 |
| GET | `/api/v1/external/material` | externaldb.py:70 |
| GET | `/api/v1/field/{entity_type}` | field.py:33 |
| GET | `/api/v1/field/{entity_type}/{key}/values` | field.py:46 |
| POST | `/api/v1/field/{entity_type}/{key}` | field.py:69 |
| DELETE | `/api/v1/field/{entity_type}/{key}` | field.py:99 |
| GET | `/api/v1/filament` | filament.py:203 |
| WEBSOCKET | `/api/v1/filament` | filament.py:409 |
| GET | `/api/v1/filament/{filament_id}` | filament.py:427 |
| WEBSOCKET | `/api/v1/filament/{filament_id}` | filament.py:445 |
| POST | `/api/v1/filament` | filament.py:464 |
| PATCH | `/api/v1/filament/{filament_id}` | filament.py:507 |
| DELETE | `/api/v1/filament/{filament_id}` | filament.py:544 |
| POST | `/api/v1/filament/{filament_id}/tag` | filament.py:569 |
| DELETE | `/api/v1/filament/{filament_id}/tag/{uid}` | filament.py:605 |
| GET | `/api/v1/material` | other.py:23 |
| GET | `/api/v1/article-number` | other.py:50 |
| GET | `/api/v1/lot-number` | other.py:76 |
| GET | `/api/v1/location` | other.py:102 |
| PATCH | `/api/v1/location/{location}` | other.py:133 |
| GET | `/api/v1/info` | router.py:48 |
| GET | `/api/v1/health` | router.py:66 |
| POST | `/api/v1/backup` | router.py:73 |
| WEBSOCKET | `/api/v1/` | router.py:90 |
| GET | `/api/v1/search` | search.py:32 |
| WEBSOCKET | `/api/v1/setting` | setting.py:59 |
| GET | `/api/v1/setting/{key}` | setting.py:77 |
| GET | `/api/v1/setting/` | setting.py:113 |
| WEBSOCKET | `/api/v1/setting/{key}` | setting.py:151 |
| POST | `/api/v1/setting/{key}` | setting.py:176 |
| GET | `/api/v1/spool` | spool.py:183 |
| WEBSOCKET | `/api/v1/spool` | spool.py:427 |
| GET | `/api/v1/spool/group` | spool.py:445 |
| PATCH | `/api/v1/spool/field/{field}` | spool.py:649 |
| GET | `/api/v1/spool/{spool_id}` | spool.py:693 |
| WEBSOCKET | `/api/v1/spool/{spool_id}` | spool.py:711 |
| POST | `/api/v1/spool` | spool.py:730 |
| PATCH | `/api/v1/spool/{spool_id}` | spool.py:787 |
| DELETE | `/api/v1/spool/{spool_id}` | spool.py:839 |
| POST | `/api/v1/spool/{spool_id}/tag` | spool.py:853 |
| DELETE | `/api/v1/spool/{spool_id}/tag/{uid}` | spool.py:889 |
| PUT | `/api/v1/spool/{spool_id}/use` | spool.py:919 |
| PUT | `/api/v1/spool/{spool_id}/measure` | spool.py:957 |
| POST | `/api/v1/tag/scan` | tag.py:112 |
| GET | `/api/v1/tag/reader` | tag.py:206 |
| WEBSOCKET | `/api/v1/tag/scan` | tag.py:229 |
| WEBSOCKET | `/api/v1/tag/scan/{reader_id}` | tag.py:247 |
| GET | `/api/v1/vendor` | vendor.py:67 |
| WEBSOCKET | `/api/v1/vendor` | vendor.py:158 |
| GET | `/api/v1/vendor/{vendor_id}` | vendor.py:176 |
| WEBSOCKET | `/api/v1/vendor/{vendor_id}` | vendor.py:194 |
| POST | `/api/v1/vendor` | vendor.py:213 |
| PATCH | `/api/v1/vendor/{vendor_id}` | vendor.py:244 |
| DELETE | `/api/v1/vendor/{vendor_id}` | vendor.py:281 |

Поза versioned API: `GET /metrics` (S/spoolman/main.py:61),
`GET /config.js` (:88), web/static mounts (:98,:108). OpenAPI/docs задаються
FastAPI constructor у S/spoolman/api/v1/router.py:23; перевіряти їх разом із
base path. Метрики залежать від env, не є доказом установленого Prometheus.

Для сумісності суттєві JSON schema, query/pagination/filter/sort, extra поля,
архівні записи, одиниці mass/length, HTTP errors та WebSocket event payload;
самої наявності route недостатньо. Use та measure — різні операції
(S/spoolman/api/v1/spool.py:919,957). Origin guard для writes/WebSocket
встановлюється в S/spoolman/main.py:120. Схеми: S/spoolman/api/v1/models.py.

### HaspelSync, включно з власними маршрутами

Таблиця — реєстрації `H/src/routes.js`, включно з трьома spoolAction.
Path parameters збережено у синтаксисі Express. OpenAPI вручну описаний у
H/src/openapi.js; API сам пояснює цей підхід у H/docs/api.md:35.

| Метод | Endpoint | Доказ H/src/routes.js |
|---|---|---|
| GET | `/api/auth/state` | :268 |
| POST | `/api/auth/login` | :272 |
| POST | `/api/auth/logout` | :296 |
| GET | `/api/status/:printerId` | :301 |
| GET | `/api/spools/:printerId` | :330 |
| GET | `/api/printers` | :336 |
| POST | `/api/mergeSpool` | :372 (handler :356) |
| POST | `/api/createSpool` | :373 (handler :356) |
| POST | `/api/createSpoolWithFilament` | :374 (handler :356) |
| GET | `/api/events` | :376 |
| GET | `/api/logs/download` | :400 |
| GET | `/api/logs/:printerId` | :419 |
| GET | `/api/logs/:printerId/download` | :465 |
| POST | `/api/printer/:printerId/monitoring/stop` | :580 |
| POST | `/api/printer/:printerId/monitoring/start` | :591 |
| POST | `/api/monitoring/:action` | :605 |
| POST | `/api/printers/reconnect` | :623 |
| GET | `/api/accounting` | :646 |
| PUT | `/api/accounting/cost/:id` | :654 |
| POST | `/api/accounting/weigh/:id` | :666 |
| POST | `/api/print/:printerId/bookings/:id/resolve` | :685 |
| POST | `/api/accounting/weighings/:id/resolve` | :701 |
| GET | `/api/print/:printerId/report` | :715 |
| GET | `/api/print/:printerId/bookings` | :728 |
| GET | `/api/print/:printerId` | :738 |
| POST | `/api/print/:printerId/clear` | :901 |
| GET | `/api/spoolman/spools` | :933 |
| GET | `/api/spoolman/spool/:id` | :946 |
| PATCH | `/api/spoolman/spool/:id` | :965 |
| GET | `/api/mappings/:printerId` | :1042 |
| PUT | `/api/mappings/:printerId/:amsId` | :1048 |
| GET | `/api/spoolman/lookups` | :1091 |
| GET | `/api/spoolman/external/filaments` | :1122 |
| POST | `/api/thirdparty/spool/:printerId/:amsId` | :1149 |
| DELETE | `/api/mappings/:printerId/:amsId` | :1238 |
| GET | `/api/settings` | :1275 |
| PUT | `/api/settings` | :1279 |
| GET | `/api/apikeys` | :1334 |
| POST | `/api/apikeys` | :1338 |
| DELETE | `/api/apikeys/:id` | :1354 |
| GET | `/api/system` | :1374 |
| GET | `/api/update` | :1378 |
| GET | `/api/diagnostics/download` | :1386 |
| GET | `/api/notices` | :1422 |
| GET | `/api/openapi.json` | :1434 |
| POST | `/api/notices/:id/ack` | :1438 |
| GET | `/api/printers/config` | :1466 |
| POST | `/api/printers` | :1470 |
| PUT | `/api/printers/:printerId` | :1483 |
| PUT | `/api/printers/:printerId/logdetail` | :1529 |
| DELETE | `/api/printers/:printerId` | :1543 |
| POST | `/api/restart` | :1574 |
| POST | `/api/test/spoolman` | :1591 |
| POST | `/api/test/printer` | :1605 |

Власні accounting/bookings endpoints відрізняються від downloaded HaspelSync;
їх не можна втратити при заміні HaspelSync API. `GET /api/openapi.json`
не є доказом паритету нового UFM.

Доступ: API keys у Bearer або X-API-Key, Web UI session, open auth routes,
Host/origin guard описані в H/docs/api.md:7–20; реєстрації auth —
H/src/routes.js:268,272,296. Документація прямо каже, що key дає повну session;
наявність UI поля scopes не доводить granular enforcement. Реальні ключі,
паролі, allowlist і printer credentials тут не читалися.

### Підтверджені source consumers і доступні інтеграції

| Споживач / напрям | Локальний доказ | Що підтверджено; що не підтверджено |
|---|---|---|
| HaspelSync → Spoolman | H/src/spoolman.js:97,121,134,169,204,207,210,217,240,249,258,343,365,532,604,615,670,696,722 | Реалізований HTTP-клієнт: spool/filament/vendor, location/material/external, field/tag, use, health. Це source dependency; runtime connection не перевірено |
| HaspelSync Web UI → власний API/SSE | H/docs/api.md:5; H/public/frontend.js; H/public/settings.js; H/src/routes.js:376 | Вбудований споживач є в snapshot; активних browser sessions не перевірено |
| Власний accounting UI → власний API | H/public/accounting.js:61,74,134,149,210; H/src/routes.js:646,654,666,685,701,715,728 | Підтверджене локальне доповнення; показ історії UI обмежений 100, це не повнота backend journal |
| Spoolman Web client → REST/WebSocket | S/client/src/App.tsx:184; S/spoolman/api/v1/router.py:109; S/spoolman/ws.py:107 | Є source web client/backend contract; робота встановленого клієнта не тестувалася |
| Bambu printer MQTT + FTPS → HaspelSync | H/src/mqtt.js:2520,2551; H/src/gcode.js:34,71 | Є LAN-протоколи, не HTTP consumers Spoolman. Наявність configured/online принтера не встановлювалася |
| Moonraker/Klipper та Fluidd/KlipperScreen/Mainsail | S/README.md:11,32,33 | Задекларована доступна інтеграція, локальної конфігурації споживача в оглянутих джерелах немає |
| OctoPrint, OctoEverywhere, Home Assistant | S/README.md:34,35,36 | Доступні сторонні інтеграції за README; встановлення та використання не підтверджено |
| Home Assistant HaspelSync integration, scripts/home automation | H/docs/api.md:5 | Публічний контракт допускає ці clients; локального installed consumer не підтверджено |
| Prometheus | S/README.md:30; S/spoolman/main.py:61; S/spoolman/database/database.py:280 | Optional scrape endpoint; наявність scraper/історичних метрик не підтверджено |
| SpoolmanDB → Spoolman → HaspelSync | S/spoolman/externaldb.py:243; H/src/spoolman.js:169 | Підтверджений напрям каталогу та caching у source; актуальність і мережеву доступність не перевірено |

Локальний deployment manifest `D:/Filament_Manager/compose.yaml:2,3,4,13,14`
декларує сервіси Spoolman (`filament-manager/spoolman:0.27.0-uk`) та
HaspelSync (`filament-manager/haspelsync:1.3.4-uk`), залежність (:18) і
persist mounts (:12,:24,:25). Це доказ підготовленого локального stack,
**не доказ фактичного встановлення/запуску саме цих image чи відповідності
linked-stack запущеному коду**. Реальні settings і printers не читалися.
Template H/docker/compose.spoolman.yml:11,13,25 також описує пару сервісів,
але template не підвищує впевненість щодо installed runtime.

## Докази, межі та приймання

Зібрано всі literal HTTP-реєстрації H/src/routes.js плюс три spoolAction;
Spoolman routes отримано з декораторів усіх Python-модулів api/v1, включно
з кореневим versioned router. Інвентаризація не імпортувала backend і не
викликала HTTP. Порівняння H/src/*.js з D/src/*.js — побайтове SHA256;
зміст real secrets/config не потрібен для такого висновку і не читався.

E02.04 має статичну доказову базу для перелічених сценаріїв. E02.05 має
endpoint inventory та класифікацію source consumers; **installed consumers
не підтверджені**. Для остаточного рішення про API compatibility потрібна
узгоджена policy: що підтримує новий native backend, що лишається import
adapter, що замінюється. Потрібні isolated contract fixtures для schemas,
errors, filters, events, auth, uncertain/replay та local accounting extension.
Цей аудит не підтверджує їх runtime-паритет і сам не закриває ці критерії.
