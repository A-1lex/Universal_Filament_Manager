# Обмежений аналіз екструзії G-code

2026-10-27. `integrations/gcode_extrusion.py`: offline inspect_extrusion,
обов’язкові expected_sha256 та dialect=marlin-linear-v1. Вихід — оцінка
довжини свіжої екструзії у мм за tool/layer; це не маса й не ledger evidence.
Парсер нічого не виконує, не підключається до принтера, не змінює залишків.

Потрібні явні G21, T0–T15 та режим E. Підтримуються M82/M83, G90/G91,
G92 E, екструзія G0/G1/G2/G3, маркери ;LAYER:n з нуля. G90/G91 скидають
override E за семантикою Marlin. Absolute E потребує відомої початкової
координати G92; після T-перемикання вона знову невідома до нового G92.
Relative E не вимагає вигаданої початкової координати.

Негативний E створює retraction debt окремо для кожного tool. Подальше
повернення цього filament не рахується вдруге. G92 не списує й не скасовує
debt. Рухи до першого відомого шару мають layer=None; вони не оголошуються
повним purge-покриттям, includes_purge=None.

Відхиляються невідомі команди, firmware retract G10/G11, volumetric/flow
режими, дюйми, макроси, Bambu extensions, binary/checksummed streams,
неоднозначна ініціалізація, повторні параметри, немонотонні шари та числова
надмірність. Підтриманий невеликий whitelist температури/вентилятора/очікування.
Цей subset поки не є парсером повного Bambu/Orca/Prusa файла.

Межі: 64 MiB, 2 млн рядків, 4096 bytes/command line, 16384 bytes/comment line,
65536 tool/layer buckets,
16 tools, 6 десяткових знаків, bounded coordinates/totals. Decimal без float;
потоковий обхід рядків після bounded UTF-8 decode. Стабільні error codes
не розкривають шлях або вміст файла.

Перевірки: 7 тестів / 24 підперевірки, Ruff та mypy108files успішні.
Незалежний read-only review gcode_subset_review не знайшов конкретної помилки.
Повний набір — 414 тестів / 390 підперевірок, exit 0.
Три реальні HaspelSync Bambu fixtures (p2s_cube, p2s_refill_cube,
p2s_two_colours, plate1) пройшли перевірений 3MF intake, але strict G-code
preflight спочатку відхилив усі три з gcode.line_invalid: рядок51,
6792 bytes, comment-only, без control characters. На підставі цього виміру
введена окрема межа comment line16KiB; command line лишається4KiB.
Тест доводить, що G1/E всередині такого коментаря не створює екструзії,
а надмірний коментар або довга команда все одно відхиляються. Поточний
результат усіх трьох — gcode.command_unsupported, не підтримка Bambu dialect.
Відтворення: .runtime/gcode_compatibility.py; SHA й результати збережені в
.runtime/gcode-compatibility-20261027.json. Невідомі команди не пропускаються.
Геометрична виконуваність, firmware configuration, автоматичні рухи при
tool change й фактичне виконання не підтверджуються цим звітом.
Наступне: реальні compatibility fixtures, інші діалекти/маркери, контроль
щільності/діаметра й перетворення мм→мг, partial coverage та verified evidence.
Не підключати цей звіт прямо до calculated kernel як готову масу.

Семантику команд звірено з первинною документацією:
[M82](https://marlinfw.org/docs/gcode/M082.html),
[G90](https://marlinfw.org/docs/gcode/G090.html),
[G92](https://marlinfw.org/docs/gcode/G092.html).
