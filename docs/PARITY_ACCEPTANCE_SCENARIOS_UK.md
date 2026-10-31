# Еталонні сценарії порівняння старої системи та UFM Studio

E02.08: опис тестових даних і процедур. Дата: 2026-10-27.
Нижче визначено майбутні перевірки; жодну не вважати виконаною лише через
наявність цього документа. Статус сценаріїв початково `Не виконано`.
Доказ виконання: build/hash, набір даних, кроки, actual result, журнал/скріншот,
до/після балансів і причина відхилення. Реальний принтер — окремий E2E етап.

## Ізольовані набори даних

- D1: два виробники, три профілі PLA/PETG/мультиколір, п’ять котушок:
  1000 г відомого залишку; 250 г; 0 г; невідомий залишок; архівна 100 г.
  Тара 200 г, ціна 600 UAH за 1000 г для першої; одна відкрита, одна запечатана.
  В UFM це 1000000/250000/0/NULL/100000 мг. Невідоме не перетворюється на нуль.
- D2: локації «Шафа»/«Сушарка», примітки з українськими символами,
  extra fields text/number/range/date/boolean/choice/multi-choice, пусті й заповнені.
- D3: синтетичні принтери P-A/P-B без реальних LAN-кодів, AMS 4 слоти,
  external spool, другий AMS із sparse logical IDs, унікальні та неоднозначні
  збіги RFID/profile/color. Секрет — тестова заглушка, не доступ до обладнання.
- D4: реальні форматні fixtures з `linked-stack/haspelsync/test/fixtures`:
  `four_colours.config`, `sparse_filament_ids.config`, `split_layer_ranges.config`,
  `external_spool.config`, `p2s_two_colours.gcode.3mf`. Вихідні fixtures не змінювати.
  Злоякісні/пошкоджені ZIP, XML та G-code генерувати окремо.
- D5: синтетичний job J-1, окремі receipt/segment/evidence IDs, один completion,
  його дублі, переставлені події, disconnect/restart, pending/uncertain booking.
  Повтор того самого файла J-2 має іншу job identity.
- D6: 125 записів історії, дві валюти, кілька дат і printer IDs, booked/uncertain
  та weighing records. Вартість розраховувати тільки в межах відповідної валюти.

Кожен сценарій починається з нових копій D1–D6 у тестовому каталозі.
Не перевіряти видалення, вимірювання або друк на єдиній робочій базі.
Для старого UI/API підміняти адреси принтерів fixture-сервером. Якщо потрібний
legacy runtime недоступний, записувати `Не виконано`, а не видавати статичний
аналіз за live comparison. Приватний baseline користувача не є публічним fixture.

## Сценарії

| ID | Каталог / дані | Кроки й критерій |
|---|---|---|
| P01 | S01,S02,S27 / D1 | Відкрити Home/список; звірити counts, залишки, архів, unknown; sort/filter/columns/page, закрити/відкрити. Порівняти відновлені preferences. |
| P02 | S07,S08 / D1 | Створити одну та кілька котушок, Save-and-add, clone; звірити кількість, поля й початковий облік. Ввести 0/від’ємну кількість: зафіксувати legacy, UFM відхиляє невалідне. |
| P03 | S03,S05,S08 / D1,D2 | Show/Edit/Clone, змінити дати/lot/location/notes, Save, повернутися, Refresh. Перевірити збереження й Unicode. |
| P04 | S04 / D1 | Archive/Unarchive відомої/порожньої котушки, Cancel confirmation. Сток від архівації не змінюється. Відмінність confirmation для порожньої відмітити. |
| P05 | S06 / D1 | Списати 12.345 г; окремо довжину із заданими density/diameter; виміряти gross/tare. Звірити масу, джерело, округлення. UFM повтор ключа не списує вдруге. |
| P06 | S09–S13 / D1 | Filament create/edit/clone, single/multi color, direction, temperatures, import external, Add spool, переходи. Offline external catalog має зрозумілу помилку. |
| P07 | S14,S15 / D1 | Vendor create/clone/edit/show, tare, зовнішній ID; default List/Refresh/Edit/Delete. Для видалення залежного vendor звірити API помилку, нічого не втратити. |
| P08 | Refine / D1 | Delete spool/filament/vendor: відкрити confirmation і Cancel; потім видалити лише ізольований допустимий запис. Залежності та залишки захищені за цільовим контрактом. |
| P09 | S16,S17 / D2 | Створити/перейменувати/переставити/видалити локацію, перенести картку котушки, відкрити Edit/Show; звірити результат після рестарту. |
| P10 | S18–S20 / D2 | Currency/base URL/rounding; усі типи extra fields, defaults/choices/order, Save/Cancel/Delete. Порожнє та невалідне поле не спричиняє прихованої втрати даних. |
| P11 | S21 / D1 | Fixture camera або USB input: правильний spool QR, неправильний payload, відсутня камера, denied access. Сканування саме не змінює баланс. |
| P12 | S22–S25 / D1 | Select all/archived/Continue, template preset add/duplicate/delete, content/URL/text size, copies/skip/paper/grid/margins/spacing, image export та print preview. Порівняти вміст; фізичний друк окремо. |
| P13 | S26,S28,H01,H12,H16 / D3 | Мова/світла/темна/system, keyboard navigation, допомога, printer picker; login/logout де застосовно. Browser-only сценарій у Qt має еквівалентний результат, не зайву браузерну форму. |
| P14 | H02,H08,H09 / D3 | Add/Test/Edit/Delete connection, невалідний IP/serial/code, Save/Cancel; код прихований, у логах відсутній. Тест не запускає друк. |
| P15 | H03–H05,A06 / D3 | Assign/Unassign/Create/Create-with-filament/Merge для AMS/external, кольори, card edit. Перевірити no match/multiple matches; UFM не вибирає перший неоднозначний збіг. |
| P16 | H06,H07,A01–A03 / D4,D5 | Job start, sliced file/plate lookup, summary/help/clear, reconnect і restart. Звірити job identity, mapping і evidence provenance; clear UI не повторює списання. |
| P17 | A04,A07 / D4,D5 | Успішний друк на external spool; completion двічі й після рестарту. Legacy результат зафіксувати; UFM проводить один раз із позначкою «Розрахункова витрата». |
| P18 | A05 / D4,D5 | Cancel/fail на відомому completed layer та без достовірного шару. Перевірити partial, retraction accounting, оцінку впевненості; невідомі дані не видавати за точний факт. |
| P19 | A06 / D3–D5 | Multi-color/sparse IDs/refill: розподіл кожному матеріалу й котушці, сума дорівнює загальній. Відсутній mapping не допускає непомітного часткового проведення UFM. |
| P20 | H08,H11 / D3 | Змінити всі 27 server settings, Save/Discard, restart-required flag; pause/resume/reconnect/restart service на fake worker. Не плутати monitoring toggle з pause фізичного друку. |
| P21 | H10,H15 / D3 | API key scopes/create/copy/revoke; endpoint search/params/send/download, SSE connect/disconnect. Після revoke доступ заборонений; ключ не лишається у звичайному журналі. |
| P22 | H13,H14 / D3,D6 | Server/printer/raw log, rotation, picker, download Full/Anonymized/Cancel. У redacted export не лишаються tokens/access codes/ідентифікатори за контрактом. |
| P23 | H17–H21,A08,A09 / D1,D6 | Price/basis/currency, історична вартість, gross/tare/net, review applied/not_applied/note, printer/date/only-review filters. Після зміни поточної ціни історичний snapshot незмінний. |
| P24 | H21 / D6 | Екран 100 із 125 записів, CSV усіх відповідних фільтру. Перевірити escaping Unicode/ком/лапок і суми за валютою. Не порівнювати видимі 100 із повним export як помилку. |
| P25 | Дані / D1–D6 | Import preview/cancel/repeat, backup/restore to new path, crash перед/після commit. Початкові баланси та історія не дублюються, старе джерело не змінюється. |

## Як порівнювати

Для кожного P-ID вести дві колонки actual: legacy та UFM, плюс третю
«навмисна зміна». Розрахункова витрата має порівнюватися з розрахунком
legacy, а не називатися фізично виміряною. Legacy баги (неконтрольований
retry, optimistic success без HTTP перевірки, неоднозначний merge) записуються
як виявлена поведінка; цільовий UFM має безпечніший явний результат.
Невиконаний сценарій не закриває реалізацію, а наявність відповідного тесту
не замінює перевірку повного UI workflow. Після зміни schema/fixture оновити
версію датасета й повторити лише залежні сценарії.
