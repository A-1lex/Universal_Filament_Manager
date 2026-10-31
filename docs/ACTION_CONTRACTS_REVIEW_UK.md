# Статичний review контрактів дій E02.03

Оновлення після review: root виправив SA098/SA119 (відсутня власна spool
return navigation у filament/vendor), доповнив App.tsx anchors. Окремий
агент виправив AC-H01–05 у 23 HA рядках, зберігши 211 ID; 490 anchors,
10 колонок, UTF-8 BOM, порожніх клітинок/дублікатів немає. Нижче збережено
початкові findings; повний candidate disposition ledger ще не прийнятий.

Точка збереження: 2026-10-27. **E02.03 залишається частково виконаним:** недостатньо доказів повного semantic coverage для кожної кнопки. Це source-only review; runtime, мережа, реальні бази та секрети не перевірялися. CSV не змінено.

Джерела: `S/` = `D:/Filament_Manager/localization/spoolman/client/src/`; `H/` = `linked-stack/haspelsync/`; `R/` = `.runtime/refine-antd-6.0.3/package/src/components/`. Прочитано AGENTS.md, LEGACY_UI_CATALOG_UK.md, REFINE_DEFAULT_ACTIONS_UK.md та критерій E02.03 у INTEGRATION_STEP_BY_STEP_UK.md:62.

## Межа перевіреного snapshot

Безпосередньо перевірено попередній Spoolman snapshot SA001–SA173 та HaspelSync HA001–HA211. За повідомленням координатора Spoolman після цього доповнено до SA318 із покриттям S01–S28. Оновлений Spoolman у цій точці збереження повторно не перевірено: попередні пропуски locations/settings/printing/header/filter не оголошуються поточними дефектами, а попередні structural totals не переносяться на 318 рядків.

У перевіреному HaspelSync snapshot: 211 рядків, 10 колонок, 0 порожніх клітинок, 0 дублікатів ID, 0 повністю однакових рядків без ID. Усі 441 входження `file:line` існують і потрапляють у діапазон файлу; посилань без номера рядка немає. Це structural validity, а не перевірка істинності кожного твердження.

## Конкретні findings HaspelSync

| Issue | Row IDs | Перевірений source і потрібне уточнення |
|---|---|---|
| AC-H01: неповна validation | HA177–HA181 | H/src/accounting.js:13–19: decimal string до 30 символів, trim, comma→dot, 1–9 цілих цифр, до 2 дробових для price і 3 для маси; знак/exponent не допускаються. :74–81: price>=0, basis>0, currency whitelist, expectedRevision safe integer>=0 і точний збіг. :111–127: UUID, expectedUsedWeight finite>=0, gross>=tare, однаковий requestId з іншим hash→conflict. Загальні required/400 не фіксують цих точних умов. |
| AC-H02: неповний replay | HA181 | Збереження requestId після невдачі описано правильно, але H/public/accounting.js:109–120 генерує новий UUID при selectSpool, зокрема після Refresh/повторного вибору. H/src/accounting.js:121–127 повертає попередній запис лише за збігу hash і блокує нову спробу за unresolved weighing. Треба описати межі збереження ID й змінений payload; не обіцяти повтор після Refresh з тим самим ID. |
| AC-H03: неповний replay resolve | HA183–HA184, HA187–HA188 | H/src/accounting.js:148 дозволяє повтор того самого resolution і trimmed note; :149 відхиляє зміну рішення після виходу з pending/uncertain. Це точніше за загальне «перед повтором звірити». Для booking також потрібна явна disposition replay за H/src/bookings.js:137; повну booking гілку в цій точці повторно не перевірено. |
| AC-H04: неописана межа weighing history | HA186–HA190 | H/src/accounting.js:68 повертає тільки останні 100 weighings; H/src/routes.js:704 шукає resolve target саме в цьому view. Старі unresolved вимірювання можуть бути недоступні через поточний view/endpoint. У CSV коректно описано іншу межу: history bookings перші100, report до10000; її не можна переносити на weighings. |
| AC-H05: placeholder замість входу | HA171–HA172, HA191–HA200 | «Вхідні поля» = «Немає» навіть для gross/tare, API key, пошуку, path/query і JSON body. Частковий опис є в результаті, але критерій E02.03 потребує фактичного входу та доступних станів. Докази: H/public/accounting.js:126–129,237–238; H/public/api.js:36,42,208,241. Значень ключів читати не потрібно. |

Це findings документації контрактів, а не твердження про нові дефекти backend. Для AC-H01–05 потрібні правки й повторна source review перед статичним прийманням цих рядків.

## Підтверджене позитивне покриття

Local accounting HA165–HA190 охоплює printer/date/language filters, only-review, spool selection, gross/tare/net, вкладки, refresh, cost profile, weighing, applied/not_applied booking та weighing, Cancel і CSV export. H/public/accounting.js:42–52 відкидає старі report responses; :88–120 зберігає вибір spool і читає current usage; :149–166 записує review без нового stock write; :168–200 використовує revision/requestId; :204–223 додає CSV BOM і захист формульних префіксів. Backend routes :654,666,685,701,715 підтверджують основні guards. Цей локальний функціонал у реєстрі збережено, з уточненнями AC-H01–04.

У перевіреній частині Spoolman усі потрібні Refine defaults уже були представлені: Create SA078/099/120; Show List/Edit/Refresh SA079–081/100–102/121–123; Edit List/Refresh SA082–083/103–104/124–125; Delete show/edit SA084–085/105–106/126–127; edit Save SA077/098/119; create/clone Save і Save-and-add SA073–076/094–097/115–118. R/crud/list/index.tsx:65, show/index.tsx:123–126, edit/index.tsx:130–138 і buttons/delete/index.tsx:42–72 підтверджують склад defaults/Popconfirm. Наявність literal DeleteButton у локальній сторінці не є необхідною умовою покриття.

У старому snapshot SA098/SA119 містили скопійований результат «spool повертає return URL або /spool» для filament/vendor; S/pages/filaments/edit.tsx:34,74,88 і pages/vendors/edit.tsx:28,47,60 цього не підтверджували. **Статус після оновлення до SA318 невідомий**, цей finding слід лише переперевірити. Те саме стосується 18 старих локальних посилань без :line у SA078–083/099–104/120–125; R anchors при цьому були валідні.

## Literal / semantic coverage та наступна перевірка

LEGACY_UI_CANDIDATES містить 777 lexical candidates: Spoolman329, own HaspelSync238, downloaded210; усі мають needs-semantic-review. Для перевіреного HaspelSync точне зіставлення нормалізованих file:line дає 50/238 збігів. Це **не відсоток функціонального покриття**: handler може бути на іншому рядку, один handler створює декілька controls, Refine генерує кнопки; кандидати також можуть бути повторними/прихованими. Downloaded snapshot не треба рахувати як додаткові незалежні функції.

Відтворення structural checks: CSV DictReader з utf-8-sig; перевірка 10 колонок, порожніх значень, duplicate IDs/rows; розділення «Доказ» за `; `; нормалізація backslash; виділення file:line; перевірка існування файлу і 1<=line<=кількість рядків. Для own candidate match видалити prefix linked-stack/haspelsync/public/ і порівняти пари file,line з project=haspelsync-own.

Повного candidate→action ID→covered/excluded-with-reason ledger не перевірено. Немає доказів вичерпного semantic coverage HaspelSync, а Spoolman318 потребує повторного structural/source review. Наступне: виправити або обґрунтувати AC-H01–05, переперевірити SA098/119 й anchors у фінальному файлі, побудувати disposition кандидатів. До цього E02.03 не позначати виконаним. Runtime приймання — окрема робота.
