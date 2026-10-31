# Рішення інтеграції UFM Studio: ADR-001

Дата: 2026-10-27. Рішення щодо модулів і напрямку інтеграції; не твердження
про завершений worker чи встановлений паритет.

## Один продукт і один облік

Qt/PySide6 залишається єдиним основним інтерфейсом. SQLite/UFM ledger —
єдине місце прийнятих операцій маси після контрольованого переходу.
Spoolman використовується як джерело імпорту та, за підтвердженою потребою,
як контракт сумісності. Старий API не стає другим авторитетним складом.
Зберігаються сценарії та дані, а не незалежний дубль web UI.

## E03.07 — власник списання на принтер

Для кожного принтера діє рівно один із режимів:

- `LEGACY_ACTIVE`: вибрана HaspelSync служба може проводити booking-и; UFM не
  проводить автоматичні витрати.
- `CUTOVER_READY`: локальний UFM зберіг cutover evidence та операторське
  підтвердження зупинки legacy writer. Це твердження саме по собі не зупиняє
  HaspelSync і не є міжпроцесним fence.
- `UFM_ACTIVE`: локальний UFM authority активовано після revision-checked
  переходу вибраної HaspelSync служби до `UFM_ACTIVE`; її оновлений booking path
  блокує нові списання. Це не охоплює інші процеси/DATA_DIR. Режим сам не вмикає
  `EstimatedUsagePolicy` чи automatic estimated debit.
- `REVIEW_ONLY`: локальний UFM перехід зупиняє UFM-проведення. Віддалена служба
  має власний окремий `REVIEW_ONLY`; ці два записи не складають транзакцію.

Перехід робиться по одному принтеру: snapshot → завершити/звірити активні й
uncertain друки → підтвердити cutover evidence → свіжо перевірити вибрану
HaspelSync службу → CAS-передача її owner до UFM → запис UFM_ACTIVE. Якщо локальний
запис не підтверджений, програма перевіряє його фактичний стан і best-effort
переводить ту саму службу в REVIEW_ONLY; невизначений результат вимагає свіжої
перевірки й операторського втручання. Не відновлювати LEGACY_ACTIVE, поки UFM
не вимкнений та стан не звірений.

UI та backend тепер виконують переходи послідовно через окремі локальні й
віддалені журнали. Це не розподілена транзакція і не технічний глобальний lock:
інший HaspelSync process/старий binary/DATA_DIR може не бачити owner, а інша
UFM-база теж не координується. E03.06 ще не замінив усі старі writer-шляхи.
До доказу міжпроцесного single-writer fence, recovery та live revalidation
перед finalization автоматичне списання має залишатися вимкненим. E03.07 Partial.

| Модуль | Відповідальність | Межа |
|---|---|---|
| Qt workspace | Склад, матеріали, пристрої/AMS, друки, історія, звіти, налаштування | Викликає application commands; без прямих SQL-списань |
| Catalog/inventory | Профілі, виробники, котушки, локації, identifiers | Стабільні ID, revision, unknown ≠ zero |
| Job/receipt worker | Durable receipt, identity, порядок/дублі/recovery | Спостереження не дорівнює проведенню |
| Python printer adapters | Discovery, TLS/secret storage, read/control capabilities | Незалежні від UI; діючі TLS guards не послаблюються |
| Calculation worker | Повторне використання pure HaspelSync slice/mapping/partial/refill логіки | Вихід — пропозиція розрахунку, без ledger/API credentials |
| UFM finalization | Вибір evidence, policy, атомарний розподіл, ledger, reservation/audit | Єдиний дозволений writer маси |
| History/reconciliation | Provenance, review/compensation, cost snapshots, звіти | Не переписує immutable історію |
| Packaging | Node/Qt/Python runtime, notices, manifest, installer/update | Користувачу не потрібні окремі runtime/Docker/browser |

## Перевірка E03.03

Експеримент `experiments/haspel_worker/calculate.mjs` — керований дочірній
Node-процес з одноразовим stdin/stdout JSON v1, allowlist operation calculate,
лімітом 512 KiB, відхиленням DTD/entities, bounded layer/filaments, generic
error response. Він імпортує лише calculation exports зі збереженого HaspelSync.
Батьківський Python запускає його з обмеженим набором env, окремими DATA_DIR/
LOG_DIR, timeout 5 с і NODE_TEST_CONTEXT для пропуску .env. Не викликаються
MQTT, FTPS, Spoolman mutation чи UFM inventory. Це не OS sandbox: залежності
ще містять transport exports, і для production потрібна вужча збірка worker.

`experiments/haspel_worker/compare.py` порівнює цю логіку з незалежним
ElementTree/Decimal reference на 11 тих самих XML-fixtures: full, partial до
першого шару, шар 10, повне покриття. Ще 7 перевірок відхилення: version,
operation debit, invalid layer, entities, empty, oversized, negative mass.
Результат: **51 passed, 0 failed**, Ruff успішний.
Приватний доказ `.runtime/haspel-worker-spike/20261027T084037652031Z/report.json`.

Це порівняння двох реалізацій XML full/range-partial. Воно не перевіряє
G-code extrusion, ZIP, FTPS, multi-plate selection, фізичний друк або E2E
списання. Старі 0.01 г та aggregation by profile/color залишаються лише
режимом порівняння, не новою політикою ledger. Production DTO має зберігати
logical material IDs і provenance та використовувати цілі mg. Неправильні
числові рядки legacy parser може приводити до нуля; перед worker потрібна
строга валідація фактів, а не лише перевірка нормалізованого результату.

## Обраний маршрут E03.04

Використовувати **Python orchestration/облік + вузький внутрішній Node
calculation worker** для зрілих алгоритмів HaspelSync. Не починати паралельний
повний production-порт тієї самої логіки в Python. Python reference у
експерименті лишається тестовим oracle для покритої підмножини.
Інтеграція йде поетапно: validated file facts → calculation proposal → UFM
evidence/policy → atomic finalization. Мережеві адаптери UFM та строгі TLS
перевірки залишаються у Python; не переносити rejectUnauthorized:false з legacy.

Причина: базові результати відтворюються через процесну межу; зріла бібліотека
вже має partial/extrusion/mapping/refill/model cases, перенесення всіх яких
потребувало б нового великого набору перевірок. Ціна рішення — додатковий
bundled Node та залежності, lifecycle/protocol hardening і release notices.
Вони входять у Windows installer; PATH/system Node у користувача не потрібний.
Зміна маршруту можлива лише новим ADR з результатами порівняння, без двох
паралельних production-калькуляторів для одного принтера.

## Що не закрито цим ADR

- E03.05: protocol/DTO описаний у WORKER_PROTOCOL_V1_UK.md і реалізований
  worker_protocol.py; live transport ще не підключений. Calculate v1 у spike
  лишається окремою експериментальною підмножиною.
- E03.06: живий HaspelSync writer ще не замінений на UFM boundary.
- E03.07: перед увімкненням списання потрібні власник принтера/epoch і
  відключення старого writer; жоден із них не переключався цим експериментом.
- E03.08: GPL-3.0-only HaspelSync зберігається з походженням; IPC сам по собі
  не визначає ліцензію комбінованого продукту. Умови релізу/повні source/notices
  ще потребують перевірки; це не юридичний висновок про можливість поширення.

Node worker не вбудований у Python wheel/one-file EXE; окрема Windows folder
build definition містить Node runtime та worker resources, як уточнено у
E03.08. Жоден пакетований варіант зараз не має live receipt reader і не
приймає масу в облік. Наступні кроки — complete DTO і validated file boundary,
потім адаптер до UFM evidence та захищене атомарне проведення.

## E03.08 — оновлення інвентарю релізних notices — 2026-10-30

Статичний аудит знайшов, що `collect_studio_notices.py` раніше починав список
лише з встановлених метаданих UFM-дистрибутива. У локальному `.venv312` ці
метадані не збігалися з поточним `pyproject.toml`, тому пропускалися прямі
залежності. Колектор виправлено: він читає базові залежності та `desktop`
extra з source `pyproject.toml`, потім обходить `Requires-Dist` встановлених
пакетів і збирає доступні metadata та license/notice files. `runtime-dependencies.json`
тепер зберігає і кількість, і точні імена скопійованих license/notice files
для кожного пакета, щоб ручний огляд міг відстежити конкретні артефакти. Статичний запуск
зібрав 22 дистрибутиви та 22 файли ліцензій; перевірена присутність Paho MQTT,
Segno, PySide6 Essentials і shiboken6. Для `jaraco.classes 3.4.0` встановлена
license copy містить MIT умови, що узгоджуються з версією на PyPI
(`https://pypi.org/project/jaraco.classes/3.4.0/`). Для `segno 1.6.6` копія
LICENSE містить три умови BSD-style перерозповсюдження; upstream-файл:
`https://raw.githubusercontent.com/heuer/segno/master/LICENSE`. Їхнє поле
`License` у зібраній metadata лишається порожнім, але notice files присутні.
Для PySide6 Essentials/shiboken6 `uv.lock` фіксує версію 6.12.0, Windows
wheel URLs на `files.pythonhosted.org` і SHA-256. Qt описує PyPI Community
distribution як LGPLv3/GPLv3 та окремий Commercial distribution:
`https://doc.qt.io/qtforpython-6/commercial/index.html`. Зібрані metadata
перелічують LGPL/GPL alternatives, а notice collector знаходить
`LicenseRef-Qt-Commercial`; сам цей reference-файл не доводить, що застосунок
має commercial license або що community obligations уже виконані. Походження
пакета зі lockfile встановлено, однак потрібно звірити реально включені Qt
бінарники/модулі, релевантні notices і ліцензійні умови конкретного release.
Це не повний SBOM та не юридичне схвалення.

## E16.01/E16.05 — Windows folder candidate та статичний manifest — 2026-10-30

`scripts/build_studio.ps1` успішно створив окрему збірку
`D:\UFM_ReleaseCandidate2\UFM Studio`; встановлену `D:\UFM Studio` не змінювали.
Статичний manifest містить 366 файлів до самого manifest і загальний розмір
216,142,011 bytes; повторний SHA-256 перерахунок усіх записів дав нуль
розбіжностей. У вмісті є UFM migrations, Haspel worker/resources, Node runtime
`_internal/runtime/node.exe`, його license `_internal/third-party/node/LICENSE`,
runtime dependency notices, Qt6Core/Gui/Network/PrintSupport/Svg/Widgets DLLs,
Python 3.12 та VCRUNTIME/MSVCP/UCRT DLLs. Перевірений file-list не містить
`.db`, `.sqlite`, `.log` чи `.env` файлів. Цей portable folder build є
candidate, не installer або acceptance release.

Перший candidate лишився на диску як
`D:\UFM_ReleaseCandidate\UFM Studio`; він не містить `win32ctypes` модулі й
не призначений для використання. `OSSecretStore` на Windows
викликає тільки явний `keyring.backends.Windows.WinVaultKeyring` і fail-closed
при відсутній залежності, тому Credential Manager не міг би бути підтвердженим
для того артефакту. У `scripts/ufm_studio.spec` додані явні imports для
`win32ctypes.pywin32` та його ctypes implementation. Другий build у PyInstaller
archive viewer тепер містить `win32cred`, `pywintypes` і всі відповідні ctypes
модулі. Це лише перевірка вмісту архіву; Credential Manager не запускався.
PyInstaller попередження про virtual import names лишаються, бо бібліотека
переадресовує їх своїм MetaPathFinder.

Додано `scripts/write_studio_manifest.py` і виклик після notice collection у
`build_studio.ps1`. Поточному candidate manifest створений окремим запуском
скрипта; майбутній build автоматично створюватиме його після збору notices.
E16.01 та E16.05 — Частково виконано. Не виконували запуск програми, тестування
UI/секретосховища, чисту Windows-приймальню, installer, цифровий підпис чи
ліцензійне схвалення. E03.08 залишається Partial; Qt/MSVC runtime notices,
UFM власна ліцензія і повний SBOM потребують окремого закриття.

Уточнено `THIRD_PARTY_NOTICES.md`: HaspelSync calculation worker/resources
потрапляють до окремої Windows folder distribution, але не до Python wheel;
колектор зараз базується на source dependency declarations. UFM license
залишається невибраною, а Qt/source-offer, системні runtime notices, підпис і
clean-machine validation — релізними блокерами. E03.08 лишається Partial. Було
виконано лише колектор notices і Ruff static lint; тести, runtime застосунку,
UI, мережа, БД чи принтер не запускалися.

## E04.01/E04.07 — мапінг Spoolman SQLite у UFM

Імпорт бере профіль/виробника, номінальну та порожню масу котушки, поточну масу лише як початковий залишок, ціну лише за наявності валюти й бази, а також archived. Додатково він заповнює лише порожні поля котушки номером партії та валідним hex-кольором; вільна текстова локація стає окремим `StorageType.OTHER` і призначається котушці. Переімпорт не переписує непорожні вручну змінені metadata. Всі записи лишаються audited commands, без прямого запису в ledger для споживання.

Preview лише рахує кандидати та непідтримані metadata; окремої построкової таблиці конфліктів ще немає. Не виводити дати з `registered`/`last_used`, не перетворювати вільну локацію на ієрархію, не імпортувати відсутню історію. Source-instance наразі залежить від абсолютного шляху: це відома межа E04.02, не гарантія ідентичності після переміщення.

## E04.02 — стабільний ID джерела імпорту

Історично `_source_instance(path)` у `src/ufm/integrations/spoolman/importer.py` хешував абсолютний шлях, через що переміщення файла створювало інші UFM UUID. Перевірка локального Spoolman `spoolman/settings.py` та `spoolman/database/models.py` не виявила явного ID інсталяції серед стандартних налаштувань/ідентичностей, на які можна безпечно спертися.

Реалізація використовує UFM-owned незмінний `source_instance_id` у локальному registry; шлях лишився лише для сумісного legacy-припущення. Preview перелічує наявні джерела й дає оператору вибрати попереднє або створити нове; збіг за числовими ID чи mutable content автоматично не визначається. Вибір старого path-hash token зберігає його як ключ реєстру, тому існуючі device/profile/spool UUID та ledger не перераховуються. Окрема таблиця alias для цього сценарію не потрібна, бо старий token не перейменовується: registry безпосередньо пов’язує його з попереднім device. Якщо надалі знадобиться зміна canonical token, її можна робити лише окремою міграцією явних per-entity ID mappings, а не мовчазним перепризначенням.

Реалізовано в E04.02 через `spoolman_import_source` та revision `0005_spoolman_source_registry`. Для legacy imports token відновлюється з audit correlation, для перенесеної бази оператор обирає раніше зареєстрований token. Runtime/UI acceptance лишається незавершеним.

### Реалізаційна межа source registry

- `source_instance_id` — незмінний UFM-owned token, що бере участь у детермінованих зовнішніх UUID; не шлях і не content hash.
- Нова таблиця реєстру зберігає token, UFM `device_identity`, display label, created/last-seen і лише hash останнього успішно імпортованого snapshot. Сирий шлях не зберігається.
- Для legacy imports token відновлюється з `audit_event.correlation_id` (`spoolman:{token}:spool:{id}:create`) і зв’язується з відповідним `actor_device_id`; детерміновані старі UFM ID залишаються незмінними.
- Preview перелічує зареєстровані джерела. Для переміщеного файла оператор може обрати попередній token; якщо вибір відсутній/неоднозначний, створюється новий token лише після явного вибору. Fingerprint — сигнал перевірки кандидата, не ідентичність.
- Повторні записи перевіряють існуючі deterministic UUID, source key і request fingerprint; несумісність завершує операцію конфліктом. Registry створюється перед індивідуальними записами для відновлення після обриву, але `last_seen` і fingerprint оновлюються лише після проходу всіх джерельних записів. Відомості джерела/профілю не можуть переписати ledger або відкриття залишку.



## E04.04 — HaspelSync printer/config transfer boundary

Confirmed source contracts from `linked-stack/haspelsync/src/printers.js`, `mappings.js`, `utils.js`, and `settings.js`; compare target `src/ufm/bootstrap/settings.py` and `src/ufm/integrations/printers/configuration.py`. The current import preview reads only the three user-selected files: printers, slot mappings, and UFM’s Spoolman ID-map report. It does not open Haspel `settings.json`, logs, printstate, databases, or credential files.

### Candidate fields and explicit exclusions

| Haspel value | Decision | Reason / gate |
|---|---|---|
| `printers[].id` (serial) | Match hint only | Normalize and match an existing UFM printer; never create or rewrite by import alone. Unknown printers go through UFM discovery and configuration. |
| `printers[].name` | Proposed display name only | Show as a preview difference and apply only after explicit confirmation for the exact serial. |
| `printers[].ip` | Discovery hint only | Do not persist or connect from imported data; identify the device over LAN and confirm the reported serial. |
| `printers[].code` | Never import/read into result | LAN access secret; re-enter through UFM’s OS Credential Locker workflow. |
| slot label + `spoolId` | Unresolved assignment proposal | Resolve external integer ID through the verified UFM ID-map; apply only after exact printer/slot identity and fresh provider observation. Never mount from stale file data alone. |
| `fingerprint`, `automatic` | Evidence flags only | Keep fingerprint value out of UI/report; no equivalence proof with UFM observation contract. Haspel automatic origin is not authority to enable UFM debit. |
| `MODE`, `LEGACY_MODE`, `AUTO_ASSIGN_THIRD_PARTY`, `SET_LOCATION` | Exclude | Semantics differ and can enable competing writers, RFID percentage updates, implicit spool creation or location side effects. |
| Spoolman endpoint/host/port and update/retry intervals | Exclude | Belong to another linked service and runtime network policy; they are not UFM connection settings. |
| Haspel log level/categories, trace and retention | Exclude | Different settings model and potentially sensitive diagnostic behavior; UFM values are configured independently. |

UFM `AppSettings` currently allows locale, theme, inventory columns, log level, and SQLite busy timeout, none of which forms a safe semantic one-to-one transfer from Haspel’s service settings. The Haspel modes are not a substitute for the E03.06/E03.07 single-writer/authority gate. Therefore preview explicitly states that settings are not read/imported. Any later import must be a versioned allowlist with per-field destination diff, conflict policy, explicit apply, and audited application commands.


### Slot mapping apply gate, verified against UFM provider contract

`FeedSlotSnapshot` in `src/ufm/application/dto/providers.py` contains `slot_key`, occupancy, trusted `tray_uuid`, trusted `tag_uid`, assigned spool ID, remaining-mass observation, and an independent optional remaining-percent observation. The Bambu LAN parser accepts exact positive integer `remain_g` grams and bounded integer `remain` percentages; it does not infer grams from nominal spool weight, and malformed, unsupported, or sentinel values remain unknown. The Studio monitor displays those values as read-only printer-reported information. These fields do not add Haspel fingerprint inputs `tray_info_idx`, `tray_type`, or color, and `resolve_feed_slot_spool()` deliberately matches only exact trusted RFID/tag identities. Therefore an imported Haspel fingerprint cannot be compared against the present UFM observation. Mapping import may be displayed as a user-reviewed proposal, but it must not create an active `SpoolMount` from the file alone. If a later workflow lets the operator intentionally mount a mapped spool as manual, it still requires fresh provider observation, exact provider slot identity, explicit per-mapping confirmation, and the E03.06/E03.07 single-writer authority gate. If these are unavailable, leave the proposal unresolved.


## E03.06 source writer re-audit — 2026-10-29

`linked-stack/haspelsync/src/mqtt.js:bookConsumption()` directly calls `useSpoolWeight()`. That helper writes grams to the Spoolman `/use` endpoint with a pending/booked/uncertain booking journal, then separately PATCHes `last_used`. The local retry guard protects Haspel’s own calls but does not coordinate with the independent UFM SQLite ledger. `src/ufm/integrations/calculation_worker.py` transports a bounded one-shot calculation request using a restricted environment; a calculation-only Node worker and packaged runtime/resource closure now exist (see the 2026-10-30 E03.06 handoff). This still is not a live print/receipt/proposal bridge and does not commit UFM accounting. No shared authority lock/store or cross-process guarantee is wired. Keep E03.06/E03.07 Partial, UFM auto-debit disabled, and imported Haspel mappings as display-only until writer replacement and authority enforcement are built and accepted.


## E03.06 worker compatibility clarification — 2026-10-29

Source review found the canonical worker already exists at `src/ufm/integrations/haspel_worker.mjs`, with its Python request/response adapter in `src/ufm/integrations/haspel_calculation.py`. It returns a ProposalMessage without allocations or writer commands; the protocol/transport are still not wired to a production caller and Node runtime/dependencies remain unbundled. `experiments/haspel_worker/calculate.mjs` is a separate developer spike with a different wire format. Do not add a second worker entrypoint; use the canonical one. The previously appended `worker_v1.mjs` attempt was removed before acceptance.


## E03.07 UFM local guard audit — 2026-10-29

`EstimatedUsagePolicy.enabled` in `calculated_finalization.py` defaults false. `preview()` is read-only while disabled; `finalize()` rejects `calculated.policy_disabled`, and `_verify()` rechecks the policy and receipt/job scope before the single UFM UnitOfWork commit updates ledger, spool, receipt and audit. This protects UFM's own finalization path; it does not coordinate with external Spoolman clients. HaspelSync's `mqtt.js:bookConsumption()` continues to write `/use` and `last_used` under its own local booking journal. There is no persisted per-printer owner/cutover proof or cross-process lock that establishes the legacy writer has stopped. Do not enable the policy by configuration alone. E03.07 remains Partial until explicit per-printer cutover/rollback is persisted and the old writer is verified inactive. Static source review only; no tests/runtime were run.

## E03.07 authority record contract for implementation — 2026-10-29

The next UFM-only step is a durable, revisioned record keyed by `printer_id`; absence of a record means `REVIEW_ONLY`, never an inferred active owner. Allowed states are `REVIEW_ONLY`, `LEGACY_ACTIVE`, `CUTOVER_READY`, and `UFM_ACTIVE`. Only a specific application command may change it, with expected revision, actor, timestamp, audited transition and a SHA-256 of the reconciliation snapshot; no direct SQL/UI field edit. New and imported printers stay non-writing by default.

`CalculatedFinalizationCommands.finalize()` must check `UFM_ACTIVE` in its initial preflight and recheck it inside the same `BEGIN IMMEDIATE` writer transaction that commits the ledger. A changed/missing state, disabled estimated-usage policy, open conflicting receipt or stale revision must fail closed. The durable record is an UFM guard, not a distributed lock and not proof that a separately running Haspel service is stopped.

Forward cutover is operator-attested and per printer: backup the source/target inventories; resolve active and uncertain Haspel bookings; stop Haspel's writer and disable its auto-start; verify no further writes; set `CUTOVER_READY`; reconcile the snapshot; then explicitly set `UFM_ACTIVE`. Rollback first moves UFM to a non-writing state, stops/drains UFM ingestion, resolves its pending receipts and reconciles a fresh snapshot; only afterward may the operator re-enable Haspel and record `LEGACY_ACTIVE`. If the legacy writer cannot be verified stopped, stay `REVIEW_ONLY`. This sequence reduces risk but cannot mechanically fence a remote Haspel process; a future shared authority endpoint would be needed for distributed enforcement.

The revisioned/audited transition command now exists, but Studio has no UI wired to it. The existing `enabled=False` policy remains an independent automated debit gate and must not be overridden for a printer that may still be written by HaspelSync.

## E03.07 default-deny persistence guard implementation — 2026-10-29

Added the revisioned `printer_accounting_authority` table and `PrinterAccountingAuthority` domain record. No row is treated as `REVIEW_ONLY`; a row in `CUTOVER_READY` or `UFM_ACTIVE` requires a lowercase 64-character snapshot SHA-256 plus an operator-recorded Haspel-writer-disabled timestamp. The migration is additive (`0006_printer_accounting_authority`) and no real database was opened or migrated.

`CalculatedFinalizationCommands.finalize()` now refuses an estimated write unless a row is explicitly `UFM_ACTIVE`, first before calling the calculator and again from `_verify()` inside the UFM writer transaction. Read-only preview and established non-estimated finalization are unchanged. `PrinterAccountingAuthorityCommands.transition()` creates only REVIEW_ONLY/LEGACY_ACTIVE initially, requires expected revisions, audits each transition, and only permits CUTOVER_READY → UFM_ACTIVE with the same snapshot hash, reconciliation timestamp, and legacy-writer-disabled attestation. At the time of this initial guard checkpoint Studio was not yet wired to the command; see the later Studio authority wizard and activation revalidation checkpoints. Estimated auto-debit stays disabled. This guard is local to UFM and cannot fence a separate Haspel process. Ruff and mypy passed for affected modules; tests/runtime were not run. E03.07 remains Partial.


## E03.07 Studio authority wizard checkpoint — 2026-10-29

The printer page now reads and changes the per-printer authority only through the audited revisioned command. It offers only legal next states, shows the current revision, and defaults a missing record to REVIEW_ONLY. CUTOVER_READY requires a user-selected snapshot and explicit operator checkboxes for stopping HaspelSync/autostart and reconciling uncertain/open bookings; UFM_ACTIVE is a separate confirmation using unchanged saved evidence. The file hash is streamed and bounded to 100 MiB, then recomputed immediately before transition. These are still operator assertions: the UI does not independently inspect booking reconciliation or remotely fence/stop the Haspel writer. No worker or auto-debit is launched by the wizard; E03.07 remains Partial until single-writer enforcement and an acceptable evidence procedure exist.

The Studio wizard checkpoint (2026-10-29) now routes per-printer changes through the audited command, displays the persisted mode/revision/digest/timestamps, offers only legal transitions, and requires explicit snapshot selection plus two operator attestations for CUTOVER_READY. The SHA-256 is streamed with a 100 MiB cap and recomputed before saving. UFM_ACTIVE is a distinct confirmation that reuses the stored evidence. These controls still cannot verify remote Haspel shutdown or independently reconcile open bookings; retain Partial and keep estimated auto-debit disabled until a stronger procedure/fence is defined.


## E03.07 read-only HaspelSync journal preflight — 2026-10-29

Source review of `linked-stack/haspelsync/src/bookings.js`, `accounting.js` and `config.js` confirmed that Haspel stores per-serial `bookings.json` and global `accounting.json`. The local preflight now parses these two files read-only (each bounded to 16 MiB), validates schema v1 records and counts per-printer pending/booked/uncertain/dismissed bookings plus global pending/recorded/uncertain/rejected weighings. Any pending/uncertain booking for the selected printer or weighing anywhere in the global file blocks CUTOVER_READY. It hashes the raw journals and their redacted counts into one evidence digest, rechecks immediately before persisting the transition, and exposes counts/digest but no spool IDs, endpoint hashes, notes or credentials.

This is not full inventory reconciliation: global weighing scope is conservative because the journal does not retain printer ownership; the parser does not read Spoolman stock or prove an old process is stopped. The operator must separately reconcile target stock and stop/disable Haspel. A future target-snapshot report and remote writer fence remain required before E03.07 can be accepted.


## E03.07 target inventory snapshot comparison — 2026-10-29

The cutover wizard now additionally reads a selected Spoolman SQLite snapshot (64 MiB cap) using the existing read-only importer validation/integrity checks and compares every source spool against the registered deterministic UFM spool ID, effective remaining mass and archived state. It requires the source fingerprint to match the last successfully imported fingerprint, and blocks on any missing or differing UFM spool. The operator separately confirms that the selected DB is the exact Spoolman instance configured in HaspelSync; UFM does not read Haspel credentials/endpoints. The final evidence digest includes Haspel journal hashes/counts, Spoolman source key/fingerprint and comparison totals, and is recomputed before CUTOVER_READY.

This is a per-source inventory snapshot parity check, not remote process fencing. Haspel writer shutdown/autostart disable remains an operator attestation, so E03.07 remains Partial and auto-debit must remain disabled until a technically enforced single-writer boundary is available or the manual process is explicitly accepted operationally.


## E03.07 stale snapshot guard — 2026-10-29

The Haspel journal preview now exposes latest `updatedAt` among bookings for the selected serial and latest `createdAt` among global weighings. CUTOVER_READY is blocked if any such activity is newer than the selected Spoolman source's last successful UFM import timestamp. This prevents treating a known prior-import snapshot as current after later recorded Haspel activity. It is conservative (even a dismissed/rejected later event requires fresh import) and depends on clocks; skew can only block readiness. The activity timestamp is included in the combined evidence digest. This still cannot prove endpoint identity or remote process shutdown.


## E03.07 activation revalidation — 2026-10-29

The separate CUTOVER_READY → UFM_ACTIVE Studio step now requires the operator to reselect the same Haspel booking/accounting journals and Spoolman snapshot/source, repeat the shutdown/source-identity/stock-reconciliation attestations, and repeat all bounded read-only validations. The recomputed combined evidence digest must exactly match the persisted CUTOVER_READY digest, and the Haspel activity time must still precede the last UFM import. This prevents activation on changed journals or stock between the two local steps; it still cannot mechanically prove remote Haspel shutdown.


## E03.07 — аудит remote monitoring controls HaspelSync — 2026-10-29

У `linked-stack/haspelsync/src/routes.js` є POST endpoints зупинки моніторингу одного принтера та всіх принтерів. Вони викликають `setMonitoring(false)`, що закриває MQTT і встановлює статус `Disabled`; це підтверджує лише поточну телеметрію. `linked-stack/haspelsync/src/printers.js` має `PERSISTED_FIELDS = [id, code, ip, name]`, а `createRuntimePrinter()` встановлює `monitoringEnabled: true`; stop не переживає restart. `/api/restart` штатно завершує сервіс, а `entrypoint.js` відновлює дочірній процес. Статичний пошук не виявив durable accounting pause, fencing token/epoch або handshake, що гарантує відмову старого writer після повторного запуску.

Висновок: існуючі stop routes не можна використати як single-writer proof. Майбутня інтеграція потребує окремого явного, автентифікованого та persisted accounting fence з revision/lease або еквівалентною гарантією; health response має повертати фактичну версію fence й стан writer. До цього залишається ручний cutover, а auto-debit вимкнений. Це висновок статичного огляду коду, не runtime мережеве підтвердження.


## E03.06 — pure Haspel calculation module — 2026-10-29

Винесено `parseSliceInfo`, `calcFullConsumption`, `calcPartialConsumption` і їхні helper functions у `linked-stack/haspelsync/src/calculation.js`; модуль імпортує лише pure `public/shared.js`. Worker використовує цей вузький модуль, а `gcode.js` повторно експортує попередній публічний API. Статична ESM closure: два Haspel ресурси, без npm залежностей; syntax checks clean. Це зменшує closure й прибирає service/config/logger/FTPS imports. Поведінкова еквівалентність цим етапом не тестувалася. Caller/receipt bridge, package-resource layout, Node runtime, authority fence та release/license approval лишаються незавершеними.


## E03.06 — relocatable package resources — 2026-10-29

Added `scripts/sync_haspel_calculation_resources.py`, a deterministic narrow copy from the preserved linked Haspel source into `src/ufm/integrations/haspel_engine/`. It includes only pure calculation/shared modules, Haspel LICENSE, and source/package hashes; it adjusts one relative import. `build_studio.ps1` invokes it before PyInstaller. Worker imports the package-local path. A temporary wheel build plus static ZIP listing confirmed the resources and LICENSE are packaged (158 entries) with no linked checkout path or database/log files. This confirms packaging only; no worker runtime or application caller exists. Node runtime and the E03.07 writer fence still block automatic accounting. Distribution/legal review remains open.

## E03.06 — verified Node in the standalone Windows folder — 2026-10-29

`scripts/prepare_node_runtime.ps1` fetches the official Node.js v24.22.1 Windows x64 archive, checks the official archive SHA-256 and the extracted `node.exe` SHA-256, and places only `node.exe` plus upstream LICENSE in the local runtime staging folder. The PyInstaller spec checks the exact version and includes the executable under `runtime/` and license under `third-party/node`; `scripts/build_studio.ps1` prepares this runtime before building. A folder bundle built successfully to `%TEMP%`. Static inspection found `_internal/runtime/node.exe` with the expected SHA-256, the Node license, Haspel worker, and all package-local calculation/shared/license/provenance resources. The Python wheel intentionally does not include Node. Neither the GUI nor the packaged Node worker was launched; this is not runtime validation. E03.06 remains Partial pending caller/receipt integration, runtime isolation evidence, and release/legal review; E03.07 single-writer enforcement remains a separate blocker, so automatic debit stays disabled.


## E03.07 candidate single-writer transfer protocol — 2026-10-29

Static re-audit of the current linked HaspelSync working tree found new local `bookings.js` and `accounting.js` journals, pending/booked/uncertain outcomes, and explicit no-retry handling for the non-idempotent Spoolman `/use` mutation. These strengthen Haspel's own retry/reconciliation behavior. They do not provide a cross-process owner: `bookConsumption()` has no durable per-printer authority gate, and an older Haspel build would ignore any new metadata. The Haspel working tree already contains user changes; this task has not modified those files.

Candidate contract for the next implementation step:

1. HaspelSync must expose an authenticated, versioned authority-capability/status operation per printer. It returns owner, monotonic revision, pending/uncertain write count, and whether the implementation can durably refuse non-owner bookings. Missing capability or mismatched revision means REVIEW_ONLY.
2. Every Haspel booking must atomically register its pending intent and check `LEGACY_ACTIVE` before the first Spoolman mutation. An ownership-transfer request must serialize with that check and reject while any booking is pending/uncertain/in flight. A restart must retain owner and unresolved intents; it must never reset ownership to legacy by default.
3. Transfer order is fail-closed: drain/resolve Haspel work, persist owner=UFM and a new revision in Haspel, then set UFM `UFM_ACTIVE` against that exact Haspel revision. If the second step fails, neither writer is enabled. Rollback disables UFM first, reconciles its ledger, and only then transfers ownership back to Haspel. Never enable both writers to improve availability.
4. The UFM finalizer must verify the live Haspel capability/revision before enabling and before each estimated booking, and must fail closed when Haspel is unreachable or the capability cannot be proven. Haspel rejects writes whenever owner is UFM or REVIEW_ONLY. A pre-fence Haspel version cannot pass cutover.
5. Use the existing per-printer audited UFM transition history and Haspel booking journal as evidence, but keep their independent local records distinct until a shared authenticated authority endpoint or equivalent transactional coordinator exists. The current local operator checkbox and UFM SQLite row alone are not a fence.

At the design checkpoint this was a candidate contract rather than implemented behavior. E03.07 requires the Haspel capability, persisted owner, booking-path gate, UFM adapter/revalidation, failure recovery, and acceptance evidence before it can be marked Done. Even with the partial Haspel-side implementation below, do not enable estimated debit until the end-to-end fence and recovery behavior are accepted.


## E03.07 Haspel per-service authority capability — 2026-10-30

Extended the existing Haspel booking journal with an optional `owners` map, preserving schemaVersion 1 and treating older journals without that property as `LEGACY_ACTIVE` at revision 0. The Haspel booking path now rejects a new print debit unless this service's persisted owner is `LEGACY_ACTIVE`. Added authenticated-by-existing-API-middleware GET/POST `/api/print/{printerId}/accounting-authority` endpoints and OpenAPI definitions. Transfers are revision checked and request-ID replay is bounded to the last transition; they reject while a booking is active and reject transfer into an enabled owner while that printer has pending/uncertain booking records. `REVIEW_ONLY` remains the fail-closed stop state. This adds a persistent, per-service capability only.

Limitations: the state is cached and persisted by one Haspel process in its own `DATA_DIR`; it is not an OS/interprocess lock and does not discover another Haspel instance, an old binary, or a different data directory. UFM does not yet call this endpoint or bind the returned revision into its own `UFM_ACTIVE` command. Thus this is not a completed single-writer fence. No linked Haspel user changes were replaced; the existing uncommitted `bookings.js`, `routes.js`, `openapi.js`, and related work were extended in place. Static Node syntax checks passed for changed Haspel modules and `git diff --check` was clean. Tests/runtime/DB/hardware were not run; keep automatic debit disabled.

## E03.07 UFM authority transport boundary — 2026-10-30

Added `src/ufm/integrations/haspelsync/authority_client.py`, a bounded client for the capability-v1 GET/POST contract above. It accepts only an explicit origin without embedded credentials/path/query, disables environment proxies and redirects, requires verified HTTPS for non-loopback hosts (plain HTTP is loopback-only), resolves HTTPS hostnames and rejects addresses outside local/private ranges, and sends the API key only in an Authorization header held as `SecretValue`. Responses are capped at 64 KiB and must identify the requested Haspel printer, exact capability version, valid owner/revision, and nonnegative pending/uncertain/active counts. Revision conflicts are surfaced as a sanitized application error; no retry or credential-bearing exception text is exposed. The printer path segment is percent-encoded.

The client is persisted and wired to the Studio authority wizard. The selected endpoint and Haspel printer ID are stored separately from the Bambu connection; the API key is held only in the OS `SecretStore`. The UI reads live capability and displays owner/revision/counts. For `CUTOVER_READY → UFM_ACTIVE`, the backend re-reads the selected service, checks owner/revision and empty pending/uncertain/active counts, transfers Haspel by compare-and-set, then records local UFM authority. If local persistence does not take effect, it checks local state and best-effort moves that exact Haspel service to REVIEW_ONLY. Ambiguous failures require an operator to perform a fresh read. Cached observations are not authorization. This sequence is not globally fenced and does not close races with another process, old binary, another DATA_DIR or a separate UFM database. The Haspel API key remains full-access; remote plaintext HTTP is prohibited. No tests, network calls, runtime service, database migration, or hardware were used. Automatic estimated debit remains disabled until global writer coordination/recovery and finalizer live revalidation are accepted.

## E03.07 Haspel endpoint and credential-reference persistence — 2026-10-30

Added additive migration `0007_haspel_authority_connection` and a separate `haspel_authority_connection` table. It stores the endpoint origin, Haspel printer ID, an OS credential reference, local revision, and the last validated remote capability snapshot/time. The API key itself is only placed in the injected `SecretStore`; UFM does not reuse/overwrite the Bambu `connection_profile.credential_ref`. The Studio backend verifies the capability-v1 read response before persisting a newly supplied endpoint/key, deletes a replaced OS key only after the DB transaction succeeds, and exposes read/transfer operations that fetch the secret from the OS store. A remote read/transfer refreshes a cached observation using optimistic local revision checking.

The cached owner/revision is display/history material and must never authorize accounting; live remote reads are used for transitions. Migration 0007 has not been applied to a database. The endpoint/key/status UI and revision-checked Haspel→UFM activation/compensation path are implemented, but the estimated finalizer is not live-revalidated, and no cross-process fence exists. Static Ruff/mypy passed for the backend, client, schema, migration manager and Studio UI; migration JSON parses as two SQL statements. Existing project formatting differences in the large schema/backend files mean whole-file Ruff format was not applied. No tests/runtime/DB/hardware were used. E03.07 remains Partial; automatic estimated debit stays disabled pending per-finalization live checks and accepted global fence/recovery.


## Додаткове обмеження: legacy AMS PATCH не fenced — 2026-10-30

Статичний огляд `linked-stack/haspelsync/src/mqtt.js:processSlot()` показав, що legacy режим пише `remaining_weight` із AMS RFID через `patchSpoolWeight()` окремо від G-code booking journal. `transferAccountingAuthority()` рахує активні бронювання через `activeBookingIds`, але legacy PATCH там не реєструється; отже активний HTTP запис може перетнутися з transfer. Ручний endpoint зважування відхиляється у legacy mode, але це не зупиняє цей автоматичний MQTT writer. Перевірка owner перед PATCH не буде достатньою через race між перевіркою та завершенням HTTP виклику. До створення спільного writer gate, охоплення in-flight PATCH, restart/uncertain recovery та іншого процесу/версії не можна вважати selected Haspel authority єдиним writer. Auto-debit має залишатися вимкненим. Зміни поведінки в цьому аудиті не вносилися; тести та runtime не запускалися.


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


## E03.06/E03.07 межа standalone packaging — 2026-10-30

Перевірив `src/ufm/integrations/calculation_worker.py`, Haspel worker resource та packaging scripts. Bundled `node.exe` запускає тільки bounded one-shot calculation worker; його середовище явно спрямовує `DATA_DIR` і `LOG_DIR` у виділений workdir. У PyInstaller збірку не входять Haspel `entrypoint.js`/`starting.js`/Express service як керований runtime. Отже ця збірка не є окремим повним Haspel сервером і не замінює/не вимикає встановлену HaspelSync. Інтеграція Haspel authority потребує окремого reachable authenticated API.

Для продуктної вимоги «одна програма без Docker» ще треба прийняти один з варіантів: портувати повну сервісну роль HaspelSync у керований local subprocess з окремим persisted data root та контрольованим життєвим циклом; або формально залишити сервіс як зовнішню залежність, що не відповідає повній автономності. Перед портом потрібні точний dependency/license review, сумісність Haspel/Spoolman API, захищений перенос конфігурації/секретів і restore/race acceptance. Наявний розрахунковий worker не треба розширювати до сервера без окремого scope та архітектури. E03.06/E03.07 лишаються Partial, автооблік вимкнений. CSV evidence уточнено; статуси не змінювалися.


## Узгоджений напрям цільової архітектури standalone UFM — 2026-10-30

Вихідна продуктова вимога: одна Windows-програма UFM Studio з локальною базою, без браузера й Docker. Тому окрема повна HaspelSync server із MQTT, Express API, web UI і власними JSON станами не повинна непомітно стати постійною залежністю релізу. Цільовий шлях — переносити потрібні функції керування принтером/AMS і обліку в адаптери та application commands UFM із її єдиним inventory ledger. Haspel API клієнт і read-only snapshot preflight потрібні як контрольований міст міграції та cutover зі старої інсталяції. Calculation-only Node worker залишається вузьким чистим адаптером алгоритму, а не повним сервісом.

До реалізації ще потрібна функціональна матриця Haspel↔UFM: MQTT discovery/connection, AMS identity/slot mapping, RFID remain legacy behavior, G-code/3MF calculation, partial print/refill handling, retries/offline lifecycle, archive/matching, API/UI actions, journals/recovery. Для кожного пункту визначити: вже покрито native UFM, потребує порту, можна замінити іншим adapter/provider або виключити з першого релізу. Не рахувати скопійований `linked-stack` сервіс як готову вбудовану функцію. До завершення feature parity, legacy writer fence і перенесення даних automatic debit лишається вимкненим. Ця ціль випливає з підтвердженої вимоги користувача про окрему програму без Docker; це ще не доказ повного функціонального паритету.


## Уточнення цільової інтеграції standalone UFM — 2026-10-30

Щоб уникнути двозначності попереднього переліку варіантів: робоча ціль, узгоджена з вимогою користувача «окрема програма без браузера та Docker», — native UFM desktop зі своїми provider/application modules та одним локальним ledger. Не планувати повний HaspelSync Express server як постійну приховану залежність і не зберігати Spoolman та Haspel як два активні обліки. Потрібні Haspel можливості переносити/адаптувати у відповідні UFM модулі після feature-parity аудиту; calculation-only Node worker може залишитись вузьким тимчасовим algorithm adapter. Haspel remote authority API, snapshots та імпорт є інструментами перехідного cutover, не постійним runtime prerequisite. Повноту цього порту ще не підтверджено; матриця можливостей передує реалізації.
# Межа provider event → durable receipt (2026-10-30)

Статичний аудит підтвердив окремий протокольний розрив, який потрібно закрити
перед consumer-реалізацією:

- `BambuLanProvider.subscribe_events()` у `src/ufm/integrations/printers/bambu_lan.py`
  нормалізує MQTT report у `PrinterEvent`. Внутрішній canonical JSON має digest,
  але DTO зберігає тільки `payload_hash` і snapshot; первинних байтів report
  у `PrinterEvent` немає.
- Для кожного екземпляра provider створюється новий UUID `source_epoch`, а
  `event_key` — лічильник змін у цьому epoch. Monitor factory створює provider
  знову після retry, тому цей ключ не можна трактувати як глобальний ID друку.
  Для довгострокової тотожності потрібен `occurrence_key`, що спирається на
  перевірену комбінацію task/subtask/job/run IDs та початку друку; при нестачі
  чи суперечності ID — reconciliation, не здогад.
- `ReceiptIngestion.ingest()` зараз приймає байти raw payload плюс серіалізований
  Worker Protocol v1 (`StatusMessage | JobMessage | SlotsMessage`), сам рахує
  SHA-256 та перевіряє printer scope. Наявний `PrinterEvent` не є цим wire DTO;
  `JobMessage` також вимагає occurrence key і типізованих state/timestamps.
  Отже, не можна передати event hash як raw bytes або неперевірено підмінити
  відсутні поля. Потрібен явний versioned adapter/DTO з визначеним значенням
  digest: або зберігати локально канонічну серіалізацію нормалізованого факту,
  відокремивши її від «сирого MQTT», або змінити receipt контракт так, щоб він
  приймав перевірену пару payload/hash із чітким provenance.
- `ReceiptIngestion` наразі не має production caller. UI monitor викликає
  `take_latest_event()`, який коалесує буфер до останньої події, тож durable
  ingestion має відбуватися до UI coalescing у окремому bounded consumer.

Потрібний порядок: versioned event adapter → перевірка printer/provider scope,
epoch, event identity та payload provenance → durable `PENDING` receipt →
restart-safe idempotent drain до projection/reconciliation → окремо операторська
перевірка evidence/mapping/authority → атомарне фіналізування ledger. Buffer
overflow, неоднозначна ідентичність, конфлікт payload, переповнення inbox,
помилка збереження чи невизначений writer owner мають зупиняти automatic debit.
Ні UI callback, ні надходження terminal event не можуть самі проводити масу.

Це контрактний аудит, не реалізація чи acceptance test; жоден статус E03.06/E03.07
не підвищується. Legacy AMS writer fence лишається незалежним блокером
automatic debit.

## Ідентичність завдання та прив’язка logical material → AMS slot

Додаткова звірка current source уточнила, які поля можна переносити через
adapter і що сьогодні не дозволяє отримати підтверджений spool match:

- `BambuLanProvider.get_current_job()` заповнює `provider_task_id`,
  `provider_subtask_id`, `provider_job_id` та результат
  `material_slot_mappings_from_report()`. Водночас він не заповнює
  `provider_run_key`, `external_job_id`, `project_uuid`, `file_hash` чи точний
  час початку. UUID `source_epoch` задається окремо на підключення.
- Декодер бере тільки `print.mapping` поточного report: індекс елемента стає
  `logical_material`; кодоване значення перетворюється на `ams:<id>` та
  `<ams-id>:<slot-id>`, `external`, `unused` або `unsupported`. Коментар
  декодера прямо забороняє вважати `ams_mapping`/`ams_mapping2` корельованими з
  активною job: ці поля можуть надійти раніше з `project_file`. Не змішувати їх.
- Нумерація logical material структурно відповідає індексу у `VerifiedSliceFacts`
  та Worker Protocol, але цього недостатньо для матеріального збігу. Resolver
  вимагає однаковий SHA-256 перевіреного файлу, той самий printer, свіжий
  snapshot (до 120 с), рівно один system/slot, `system.complete=True` і
  підтверджену зайнятість слота.
- `feed_systems_from_report()` зараз встановлює `complete=False` для AMS і
  external slot систем. Resolver через це повертає `UNKNOWN` ще до підтвердження
  mapping, навіть якщо report містить tray UUID/tag/type. Тому автоматично
  зіставляти logical material із котушкою або списувати через наявний provider
  не можна. `complete=True` вимагатиме доведеної повноти snapshot для конкретної
  моделі/схеми, а не припущення про кількість слотів.
- Composite `occurrence_key` можна будувати лише після визначення семантики
  повторного використання task/subtask/job IDs і наявності discriminator нового
  фізичного запуску. Поточних даних недостатньо, щоб універсально гарантувати
  унікальність; відсутній/повторний ID має створювати неоднозначність для
  reconciliation, не новий автоматичний alias.

Наступний безпечний крок — описати для кожної моделі/репорту критерій повного
slot snapshot і стабільну print occurrence identity за локальними fixtures або
підтвердженою схемою; до цього залишати resolver fail-closed. Результат цього
етапу — source audit і уточнення вимог, не реалізація; E03.07 лишається Partial,
автоматичне списання вимкнене.

Наявні fixtures уточнюють межу, але не дають підстав послабити її: локальні
перевірки `tests/integration/test_bambu_lan_provider.py` окремо перевіряють
`print.mapping` як поточний job mapping і не з’єднують попередні `ams_mapping*`;
`tests/unit/test_job_material_mapping.py` очікує `UNKNOWN` для incomplete feed.
Їх прочитано, не запускали. Збережені Haspel report fixtures (`linked-stack/
haspelsync/test/fixtures/reports/*.json`) мають різні форми систем: звичайні
4-slot, multi-system та 1-slot системи, без явного completeness marker. Це
cross-project examples, не специфікація Bambu firmware. Фіксоване припущення
«4 видимі trays = повний AMS» тому не приймається.

## Pending receipt lifecycle: primitives vs production wiring

Граф указав на `ProjectionDrain`; source перевірено. `ReceiptIngestion.pending()`
віддає bounded список усіх незавершених receipts. `JobProjectionCommands.pending()`
натомість відбирає лише `PRINT_*`, наявний enabled printer, записи без уже
створеної projection та без відкритого conflict/quarantine; порядок —
`received_at`, потім ID. `ProjectionDrain.run_once()` обробляє обмежену партію,
повторно використовує idempotent receipt application, а відхилені job facts
durably переводить у reconciliation. Це корисна restart-replay заготовка.

Проте пошук використань у `src/ufm` знайшов визначення цих класів, але не їх
production-конструювання/виклик з container, Studio чи provider lifecycle.
Тому після process restart DB-записи можна було б повторно вибрати, але наразі
ніхто не запускає drain. Крім того, status/feed-slot receipt types, допустимі
`ReceiptIngestion`, projection drain не читає; окремий consumer чи явне правило
не створювати ці записи ще відсутні. Generic `Receipts.pending()` сам по собі
не є complete processing workflow.

Consumer lifecycle перед реалізацією має визначити: постійний власник stream
для кожного enabled printer; запис provider event у DB до UI coalescing; bounded
queue/backpressure з помилкою без мовчазного відкидання; стартовий та періодичний
replay persisted receipts; роздільні handlers для job/status/feed-slot або
типобезпечне обмеження, що саме потрапляє до job receipt inbox; stop/reconnect
та source gap reconciliation. Projection/read events не фіналізують витрати;
остаточне проведення лишається окремим операторським action за чинною policy й
writer authority.

### Наявні Qt lifecycle точки

`StudioWindow.work()` створює одноразовий `Task(QThread)`: запускає одну
синхронну application-команду, повертає результат і блокує сторінки; `work()`
не запускається, поки активний інший task або monitor. Це не worker для
постійного polling/replay. `PrinterMonitorTask(QThread)` вже є окремим
довгоживучим власником asyncio provider stream і health/retry lifecycle, проте
його старт зараз ручний лише для вибраного принтера. Його event signal веде до
`show_latest_monitored_event()` → `take_latest_event()` → UI; sink у DB немає.
Buffer має межу 256; переповнення піднімає non-retryable `RuntimeError` для
поточного monitor lifecycle, а не створює durable backpressure receipt.

`AppContainer` поки містить settings/paths/translator/secrets/logger;
`StudioBackend` створює inventory, storage, catalog та authority commands, але
не ingestion/drain. `closeEvent()` просить monitor зупинитися і відкладає
закриття вікна; app лише після завершення `app.exec()` знищує вікно й тоді
dispose-ить SQLite engine/container. Consumer має мати явний shutdown handshake
до engine.dispose, а не фонове «daemon» завершення.

Найменше перетинів дає окремий керований monitor/consumer lifecycle у backend
або окремий сервісний `QThread`: provider event → перевірений adapter → DB
transaction/receipt commit → сигнал/коалесинг лише для UI → projection drain.
На помилці DB не підтверджувати обробку і не відкидати event мовчки; зупинити
подачу з видимим станом та створити reconciliation після відновлення. Коли
event poll stream пропустив проміжні стани під час офлайну, поточний snapshot
не є історією — потрібне reconciliation, а не реконструкція terminal event.

### Reconnect і межі доставки Bambu LAN

`BambuLanProvider._on_connect()` підписується на report topic з QoS 0 і надсилає
`pushall`-запит поточного стану. Він не читає історичний журнал переходів.
Monitor factory створює новий provider для retry; provider генерує новий
`source_epoch`, очищає report і `subscribe_events()` починає з першого нового
snapshot/event у цій epoch. Отже, reconnect відновлює поточне спостереження, не
послідовність пропущених job-переходів; QoS 0 також не є durable брокерною
чергою. Подію «completed» не можна синтезувати з пізнішого IDLE чи припускати
завершення через зникнення активної job. Зміна epoch без однозначної occurrence
identity, стрибок лічильника або виявлена прогалина має створювати source-gap
reconciliation і блокувати estimated finalization для цього run.

Нормальний shutdown вже має потрібну основу: Studio close просить
`PrinterMonitorTask.stop()`, QThread cancels asyncio monitor, `_run_provider_once`
закриває event stream і викликає `provider.disconnect()`, після `finished` вікно
закривається, а потім звільняються SQLite engine і container. Production consumer
має зберегти цей порядок; помилка/overflow не повинні перетворюватись на
успішне підтвердження прийому.

### Межа локального і глобального ownership

`StudioWindow` тримає лише один `_monitor_task` на вікно, але статичний пошук у
`src/ufm` не знайшов OS named mutex, `QLockFile`, single-instance серверу або
per-printer process lease. Це не забороняє другий процес/вікно, інший
`AppPaths.resolve(root)`/SQLite файл чи інший ПК. Local
`PrinterAccountingAuthority` та перевірка `UFM_ACTIVE` у finalization живуть у
тій самій UFM SQLite DB: revision check захищає записи цієї DB, але не інші копії.

У UFM можна додати Windows per-printer mutex для локального ownership одного
принтера, який тримається весь час роботи producer/consumer; окремо можна
заборонити duplicate monitor у процесі. Це не замінює мережевий fencing token.
Щоб cutover між UFM і Haspel був безпечним, token/owner epoch має перевірятися
кожним Haspel consumption writer до і після зовнішнього PATCH/`/use`, а всі
екземпляри мають координуватися на спільному авторитетному store. Старий
binary, інша `DATA_DIR`, другий ПК або legacy MQTT writer без такого gate
залишаються поза захистом. Якщо середовище не підтверджує спільне координування,
маємо лише ручний operator-controlled cutover, жодного auto-debit.

### Implementation slice та приймальні ворота

| Порядок | Наявна точка | Необхідна межа | Критерій перед переходом далі |
|---|---|---|---|
| 1. Provider DTO adapter | `integrations/printers/bambu_lan.py`, `application/dto/providers.py`, `application/dto/worker_protocol.py` | Версійований адаптер події, визначене походження/хеш payload, однозначний occurrence key або quarantine | Жодного непідтвердженого ID/hash, scope тільки вибраний printer/provider/epoch; обмежені поля та розмір |
| 2. Ownership | `ui/studio_window.py`, `ui/printer_monitor.py`, `application/accounting_authority.py` | Унікальний producer для printer у процесі/на ПК плюс окрема shared fence для Haspel/інших хостів | Другий UFM відхилено; старий/паралельний Haspel writer перевіряє той самий owner epoch; невизначений owner блокує процес |
| 3. Durable ingest | `application/receipt_ingestion.py`, `infrastructure/persistence/repositories/entities.py` | Commit observation до UI coalescing; захист від replay/conflict; source provenance не називається MQTT raw, якщо це лише normalized snapshot | Crash до commit не підтверджується; crash після commit відновлюється; той самий event не дублює receipt, змінений payload відкриває reconciliation |
| 4. Типова маршрутизація | `application/projection_drain.py`, `application/job_projection.py`, topology/status commands | PRINT_* → projection; status/feed-slot → власні snapshot handlers або не класти в job inbox | Жоден прийнятий тип не лишається без consumer; помилка/невідповідність → quarantine, не silent drop |
| 5. Replay та lifecycle | `bootstrap/app_container.py`, `infrastructure/studio_backend.py`, `ui/studio_window.py` | Startup replay, bounded poll/consumer, backpressure, stop/join до закриття SQLite engine | Restart відновлює всі persisted pending jobs; переповнення/DB outage видимі й fail-closed |
| 6. Source-gap handling | `integrations/printers/bambu_lan.py`, projection/reconciliation | Нова epoch, пропущені/повторні sequence, неактивний job без terminal report | Створюється deduped reconciliation; terminal state не реконструюється з IDLE |
| 7. Legacy cutover | `linked-stack/haspelsync/src/mqtt.js`, booking journal, owner API | Fencing token на кожному writer до і після зовнішнього облікового запису; всі процеси/сховища мають спільну координовану owner state | Legacy і UFM не можуть одночасно записати; невизначений результат блокує обидві сторони до reconciliation |
| 8. Окрема finalization | `application/calculated_finalization.py`, `application/job_material_mapping.py` | Явна команда за перевіреним 3MF/G-code, точним file hash, printer/job identity, свіжим повним slot mapping та policy | Попередній preview окремий від commit; partial/range, multi-spool allocation, idempotency, no stock/authority uncertainty; callback ніколи не списує |

Це dependency map, не завершення пунктів чи затверджена runtime-зміна.
Зберігаються вимоги: автоматичне списання вимкнене; unit/integration/acceptance
перевірки виконувати лише окремим дозволеним етапом до будь-якого release.

## E16.02/E16.03 — чернетка per-user installer і межа даних — 2026-10-30

`scripts/ufm_studio.iss` задає Inno Setup package з `PrivilegesRequired=lowest`,
окремою директорією програми за замовчуванням у `%LOCALAPPDATA%\Programs`,
вибором каталогу інсталяції, ярликом меню Пуск та необов'язковим desktop shortcut.
`[UninstallDelete]` відсутній, тому інсталятор не просить видаляти каталог даних.
`AppPaths.resolve(None)` використовує `platformdirs` для користувацьких data,
config, logs і cache окремо від `{app}`. Маніфест генератор і verifier відхиляють
DB/SQLite sidecars, журнали, `.env` та файли приватних ключів.

`scripts/build_installer.ps1` перевіряє точний набір і SHA-256 bundle перед
передачею версії та шляхів компілятору. Тут `ISCC.exe` відсутній, тому Inno
script не компілювався, setup не збирався і встановлення/оновлення/видалення не
приймалися. Кроки E16.02/E16.03 залишаються Частково виконано; E16.04 не
перевірявся. Це source/static evidence, не підтвердження роботи інсталятора.

### E16.07 — кеші й звіт очищення

Існуючий `scripts/clean_project_caches.ps1` має явний `-Apply`, allowlist лише
`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, перевіряє project marker, межі
resolved path і reparse points; за замовчуванням лише рахує вміст. Огляд виявив,
що кожен dry-run перезаписував попередній `docs/CLEANUP_REPORT.json`. Скрипт
тепер зберігає попередній звіт і для наступних запусків обирає timestamped ім'я.
Очищення кешів не запускалося; зміна перевірена лише PowerShell parser-ом.

### E16.05 — локальне середовище проти `uv.lock`

Статичне порівняння `third-party/runtime-dependencies.json` з `uv.lock` для
candidate виявило 8 різних версій (Mako, MarkupSafe, SQLAlchemy, Alembic,
more-itertools, platformdirs, pydantic, pydantic-core) та `greenlet`, якого в
lockfile немає. Отже, папка точно описана власним manifest, але збірка не
відтворює поточний lockfile. Це не доводить помилку runtime, проте є release-
reproducibility gate: наступну збірку робити з окремого синхронізованого
release environment та включеним/зафіксованим build toolchain. Існуюче venv не
пересинхронізовували й candidate не перебудовували.


### E16.02/E16.08 — installer compilation and release acceptance procedure

Inno Setup 6.7.3 was installed in the current user's scope from the winget manifest for JRSoftware.InnoSetup, whose installer hash winget verified. The standalone setup candidate compiled successfully from the lock-aligned, manifest-verified folder bundle: `D:\UFM_InstallerCandidate3\UFM-Studio-Setup-0.1.0.dev0.exe`; size 61,474,770 bytes; SHA-256 `deb550f43139c33f6d2a5516579bbfd86e868c50eace5e6f7c65f7fb876c86b7`; Authenticode `NotSigned`. Installer was not run. Added `docs/RELEASE_ACCEPTANCE_UK.md` and the developer build command/limitations to the Studio guide. E16.02 and E16.08 are Partial, not Done: install/update/shortcut/uninstall and data-preservation acceptance, clean Windows, signing and license approvals remain open. No application or user database was launched or modified.
### E16.07 — cache cleanup dry-run

Ran `scripts/clean_project_caches.ps1` with its default (no-delete) behavior. `docs/CLEANUP_REPORT-20261030T150320454Z.json` records `.pytest_cache` 5 files/80,681 bytes, `.mypy_cache` 3 files/25,321,701 bytes, `.ruff_cache` 10 files/29,846 bytes, `Applied=false`. Timestamped report creation preserved the prior `docs/CLEANUP_REPORT.json`. Cache folders remain; no `-Apply` was used. E16.07 stays Partial.


## Уточнення E03.07: shared-DATA_DIR journal serialization — 2026-10-31

`linked-stack/haspelsync/src/bookings.js` тепер бере ексклюзивний суміжний `bookings.json.lock` через атомарний `open(..., "wx")` для begin/finish/resolve booking і authority transfer, перечитує JSON усередині критичної секції та відхиляє паралельний writer до HTTP debit. Lock поширюється лише на процеси, які використовують той самий точний `bookingsPath` і новий lock-aware код. Старі binary, інші DATA_DIR або незалежні Spoolman writers не координуються; UFM/Haspel cutover не є distributed transaction. Після crash lock залишається і блокує записи до операторської перевірки; автоматичне зняття простроченого lock не реалізоване. Regression: `node --test test/bookings.test.js` — 18 passed; повний suite — 795 total, 792 pass, 0 fail, 1 skipped, 2 A2L TODO. E03.07 лишається Partial, UFM auto-debit вимкнено до recovery/live/cross-writer acceptance.
