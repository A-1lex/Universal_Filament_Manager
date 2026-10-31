# Протокол прийняття першого ядра фіналізації

Реалізація: `src/ufm/application/finalization.py`.
Контракт: `FinalizationCommands(unit_of_work).finalize_single(...)`.

Операція приймає UUID вже збережених job, segment, evidence та receipt,
актор і стабільний command key. Повертає незмінний `FinalizationRecord`.
Перший підтримуваний сценарій — один завершений друк і одна котушка;
доказ має бути фактичним повним PRINTER/ABSOLUTE consumed mass з явним purge.

| Сценарій | Підтверджений результат |
|---|---|
| Успішний друк | Точний дебет; decision/evidence link; terminal job/receipt; audit |
| Повтор після reopen | Той самий record без нового запису |
| Повтор після наступного ручного списання | Поточний залишок не переписується старим результатом |
| Зміна command key або актора | IdempotencyConflict без змін |
| Ключ уже використано для іншого job | Конфлікт без часткової фіналізації |
| Зміна receipt payload або пошкоджений job state | Не повертає хибний успіх |
| Збій audit після всіх основних записів | Повний rollback; повтор успішний |
| Два concurrent writers | Одна фіналізація та одне списання |
| Процес завершено перед commit | SQLite відновлює початковий стан |
| Процес завершено після commit | Replay не списує вдруге |
| Нульова маса | Decision збережено; резерв RELEASED; немає нульового ledger debit |
| Actual перевищує власний резерв | Дебет фактичний; allocation не більша за резерв |
| Інший job має резерв | Чужий ACTIVE claim збережений і забезпечений |
| Unknown або shortage | Відмова без підміни невідомого нулем |
| Додатковий material або відкритий segment | Job не фіналізується частково |
| Неправильний source epoch | Відмова через непідтверджену identity |
| Opening після початку друку | Потрібне звіряння базового залишку |
| Зважування перекриває інтервал друку | Пізнє повідомлення не списує вже враховані витрати |
| Slicer estimate / непевний purge / неповний interval | Не застосовується як фактична маса |

Новий набір: **14 tests, 20 subtests passed**.
Увесь проєкт: **327 tests, 231 subtests passed**, process exit 0.
Ruff: passed. Strict mypy: 97 source files, no issues.
Wheel/sdist: зібрані. Повтор тих самих 14 tests / 20 subtests з wheel
у тимчасовому каталозі поза checkout пройшов; origin модулів перевірений.

Команди перевірки:

```powershell
./.venv312/Scripts/python.exe -m pytest tests/integration/test_print_finalization.py -q
./.venv312/Scripts/python.exe -m pytest -q
./.venv312/Scripts/python.exe -m mypy
./.venv312/Scripts/python.exe -m build --no-isolation
./.venv312/Scripts/python.exe scripts/check_finalization_wheel.py
```

Цей протокол закриває перший вузький виконавець, а не всю фазу автоматичного
обліку. Немає live worker, автоматичного формування aliases/mapping/evidence,
AMS, failed/cancelled policy та повного reconciliation UI. За недостатнього
запасу service поки відхиляє запит; стійкі вихідні докази залишаються pending.
Фізичний принтер у цих тестах не використовувався; встановлений EXE та
production-база не змінювалися.
