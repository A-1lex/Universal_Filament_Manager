# Перевірений локальний розбір sliced 3MF

Перевірено: 2026-10-30. Модуль `src/ufm/integrations/sliced_files.py`, parser version
`sliced-3mf-v1`. Це read-only intake та нормалізація фактів, без виконання
G-code, підключення до принтера або зміни обліку.

## Реалізоване

`inspect_3mf_bytes(data, *, plate, expected_sha256)` та
`inspect_3mf_file(path, *, plate, expected_sha256)` повертають frozen
VerifiedSliceFacts. SHA256 обов’язковий і звіряється з тими самими байтами,
які розбираються. Caller має отримати expected hash із перевіреної прив’язки
job/file; самостійне хешування довільного файла не підтверджує його належності
конкретному друку. Plate задається явно, збігається з XML index та G-code entry.

Нормалізуються selected plate, metadata, filament ID/logical ID=id−1,
used_g/used_m та layer ranges. Однаковий колір чи profile не об’єднує
логічні матеріали. Used_g перевіряється як скінченний невід’ємний Decimal
до 10000 г; некоректний рядок не перетворюється на нуль. Перехід у цілі mg
виконується ROUND_HALF_UP із збереженим provenance та вихідним рядком.
Відсутня довжина — None, відома нульова — Decimal(0). Quantity=estimate,
includes_purge=None; додаткове покриття не вигадується.

Результат містить file/metadata/G-code SHA256, parser_version, selected plate,
filament/layer facts, normalized XML selected plate та непрочитані як команди
G-code bytes. Сам `inspect_*` stateless і нічого не зберігає. Окремий
`SliceArtifactStore` та `VerifiedSliceBindings` реалізують незмінне сховище й
аудитовану job/hash/plate прив’язку; їхній доказ і межі наведено в
`VERIFIED_SLICE_ARTIFACTS_UK.md`. Ці core services поки не підключені в
Studio/backend/bootstrap, тому наявність core не означає доступний користувачу
наскрізний процес. «Перевірений» тут означає перевірені контейнер/metadata/hash,
а не правильність друкарських команд чи фізично виміряну витрату.

## Межі

| Об’єкт | Підтримка / межа |
|---|---|
| ZIP archive | <=128 MiB, <=2048 entries, declared total <=512 MiB |
| Central directory | Preflight EOCD до створення ZipFile objects; <=16 MiB, узгоджені offsets/counts/comment |
| Entry types | Stored/deflate; reject encrypted, symlink, absolute/traversal/backslash/colon paths, duplicate NFC/casefold names |
| Expansion | Ratio <=200; bounded member reads та CRC |
| Metadata | Точний Metadata/slice_info.config, UTF-8, <=512 KiB |
| XML | Без DTD/entities; depth<=16, nodes<=8192, attributes/довжини bounded |
| Plate | Явна, унікальна; потрібен Metadata/plate_N.gcode |
| G-code entry у sliced 3MF | <=64 MiB, checksum/CRC; 3MF intake трактує байти як opaque, окремо від G-code parser |
| Filaments | IDs 1..256, без дублікатів; strict quantities; sparse IDs збережені |
| Ranges | Валідні ordered inclusive pairs, logical references, bounded counts; empty unused list ігнорується |
| Unsupported 3MF | ZIP64/multi-disk/SFX layouts, нестандартні XML namespaces/encoding, відсутній/неоднозначний plate entry |

Ігнорування empty layer list відповідає legacy поведінці та не додає вигаданих
шарів. Нормалізація покриває лише metadata/filaments/layer ranges; project
settings, multi-color sets, extrusion shares, start/purge/flush/support/wipe
semantics ще не реалізовані в цьому intake. Невідомі поля не стають доказом
фізичного використання.

## Матриця перевіреної сумісності

| Формат/джерело | Статус | Що перевірено | Що не доведено / не підтримується |
|---|---|---|---|
| Sliced 3MF із `Metadata/plate_N.gcode` і metadata plate | Підтримувана підмножина | 11 HaspelSync XML fixtures та один реальний fixture `p2s_two_colours.gcode.3mf`; selected plate, logical filament IDs, `used_g`/`used_m`, layer ranges, hashes і bounded ZIP/XML | Не інтерпретує G-code commands; не визначає purge/flush/support/wipe coverage, execution чи фізичне споживання; не підтверджує належність до конкретного job без окремої binding |
| Standalone текстовий G-code `marlin-linear-v1` | Обмежений read-only preflight | `gcode_extrusion.py`; тільки explicit dialect, bounded UTF-8 input і SHA-256; одиниці mm, tools, M82/M83, G90/G91, G21, G92, лінійні/дугові E-переміщення, retract debt та `;LAYER:n`; результат — довжина в mm зі статусом estimate | Немає конвертації mm у грами або ledger write; не доведено сумісність конкретного firmware/фізичного друку; невідомі команди/режими відхиляються |
| Standalone G-code невідомого/vendor dialect | Не підтримується автоматично | Немає silent fallback; інші dialect labels і невідомі команди відхиляються | Не заявляється сумісність із Bambu/Orca/Prusa/Klipper vendor extensions/macros без окремих fixtures та review |
| Binary `.bgcode` | Не підтримується | Відсутня реалізація binary decoder | Не підмінювати текстовим parser і не запускати |
| FTPS printer retrieval | Не реалізовано | Немає перевіреного runtime FTPS шляху для цього intake | Потрібні TLS/identity, bounded download, checksum та owner acceptance |

Тестові файли перевіряють parser contracts і fixtures; це не firmware
compatibility matrix, hardware acceptance або доказ, що всі реальні Bambu/інші
slicer exports приймаються. Для розширення підтримки потрібні provenance-bearing
paired files з конкретних версій slicer/firmware та окремі очікувані результати.

## Перевірки та наступне

Загальний контрактний запуск 2026-10-30: `tests/contract/test_sliced_files.py`
та `tests/integration/test_gcode_extrusion.py` — 21 passed / 90 subtests,
exit 0; Ruff для обох parser modules і тестів — clean. На рівні 3MF fixtures:
11 XML fixtures HaspelSync та реальний fixture
`p2s_two_colours.gcode.3mf`, sparse/same-color IDs, multi-plate, Decimal/mg,
CRC, path/duplicate/symlink/encryption/ratio/limits, XML attacks, bad numbers,
hash/plate mismatch, directory limit до алокації та empty layer-list.
Ruff і strict mypy попереднього intake залишаються historical evidence, а не
результатом цього короткого запуску.

E08.03 завершений для підтримуваної sliced-3MF підмножини. E08.01/.02/.04/.05/.07
часткові: залишаються точна durable job identity/runtime binding, verified FTPS,
ширше ZIP/XML/vendor coverage, G-code mass/ledger evidence, purge coverage і
реальні paired file compatibility reviews. E08.06 core виконаний, але runtime та
backup/restore integration окремі. Автоматичне списування не вмикалося;
встановлений EXE не змінений.
