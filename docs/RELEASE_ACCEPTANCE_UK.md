## Аудит готовності станом на 2026-10-30

**Рішення: НЕ ГОТОВО до публічного розповсюдження.** Candidate16 — найновіша внутрішня portable-збірка за адресою `D:\UFM_TestCandidate16\UFM Studio`; manifest independently verifies 378 files and 180 source inputs; EXE SHA-256 `3917132867052376851e9edc4e9fe9aaf91d39022b4ceb9c6a134a6730d612b0`, version `0.1.0.dev0`, Authenticode `NotSigned`. Sidecar CycloneDX SHA-256 `8ed25b5cc37e53486f0e2ea1e196d389689a427b3b190e25c9f3032ab0ad0494` lists 401 components and composition is incomplete; its manifest/runtime-inventory hashes were independently matched. Root Git revision is absent. Candidate16 was built but not launched. Candidate15 remains the latest visually reviewed build; its four tabs were inspected at one PC resolution only. Neither is a public release or clean-Windows/hardware/owner acceptance.

Latest full default suite after diagnostic event-code hardening: 659 passed / 489 subtests in 81.56 s, followed by a Windows fatal access violation and exit code 1 without a Python frame. Targeted diagnostics/logging/metadata tests: 13 passed; Studio diagnostic registry: 1 passed /72 deselected; Ruff and mypy src (139 files) clean. This does not resolve the intermittent Qt/native teardown fault. Tests used isolated fixtures/temp SQLite; no production DB, live printer or Haspel endpoint.

Candidate16 adds a shared explicit safe event-code allowlist to structured logging and diagnostic export; arbitrary well-formed event strings are omitted. The privacy behavior was covered by isolated unit fixtures; Candidate16 has not been launched or visually inspected with non-empty log data.

Блокери релізу: root UFM Git provenance відсутній; UFM license не обрана; повний SBOM і юридична перевірка Qt/Python/Node notices не готові; installer now fails closed until complete/approved SBOM, clean source revision, stable X.Y.Z, and valid EXE/installer signing exist; clean-Windows/install/upgrade/restore, owner UI/DPI/accessibility and hardware acceptance are outstanding. Automatic debit remains disabled pending stable print-run identity, AMS-to-physical-spool provenance, and global Haspel writer fencing.

## Формальні release artifacts Candidate4

- Portable folder: `D:\UFM_ReleaseCandidate4\UFM Studio`
- Preliminary CycloneDX SBOM sidecar: `D:\UFM_ReleaseCandidate4\UFM Studio.cdx.json`
- Installer: `D:\UFM_InstallerCandidate4\UFM-Studio-Setup-0.1.0.dev0.exe`
- Перевірені на етапі складання SHA-256 записані в `build-manifest.json` та
  handoff. SBOM sidecar SHA-256:
  `1b4cfd283df2e843f581f54ba71808b1c362e7cb47b39302605841c50a18a481`.
  Candidate4 EXE SHA-256 `1ead5dfbf6ab414aa9dfe990b7ae75ae235dd7a59b7d2b0d22f63b38578289a9`;
  installer SHA-256 `3673df1d876e4444a4f9f829072489aec7d96f07271c00d0182e5e8568a2c53e`.
- SBOM відповідає офіційній CycloneDX 1.7 JSON Schema, але навмисно має
  `incomplete` composition. Він не підтверджує повний native dependency graph,
  ліцензійну сумісність чи дозвіл на розповсюдження.
- Поточний SBOM містить 393 компоненти: 370 хешованих файлів bundle, 20
  сторонніх Python бібліотек, Node.js 24.22.1, Qt 6.12.0 та лише мінімальні
  vendored HaspelSync calculation resources (`calculation.js`, `shared.js`,
  LICENSE). Node/Qt/Haspel компоненти мають явні зв’язки з
  manifest-хешованими файлами.
- PE `FileVersion`/`ProductVersion` Candidate4 дорівнюють `0.1.0.dev0`;
  EXE та installer не підписані. Збірка не має статусу публічного релізу.

## Перед запуском приймання

1. Перевірити, що версія та SHA-256 файлів збігаються з маніфестом/переданим
   handoff; перевірити SBOM sidecar для тієї самої версії й bundle. За
   невідповідності ізолювати артефакт і не запускати. Не трактувати `incomplete`
   SBOM як повний перелік компонентів або ліцензійне схвалення. Поточний
   `build_installer.ps1` відмовляє до виклику Inno Setup, якщо SBOM не має
   `composition=complete`, явного `ufm:sbom-completeness=complete`, затвердженого
   `ufm:license-review=approved` і ліцензії застосунку, або якщо не збігаються
   sidecar version, manifest/runtime-inventory hashes. Build manifest має
   підтверджувати Git revision і чистий source tree; його source-input hashes
   мають збігатися з поточними build inputs. Також installer можна створити
   лише зі stable `X.Y.Z` версією та EXE, підписаним тим самим заданим
   сертифікатом.
2. Отримати затвердження для UFM license, Qt/PySide6 та Microsoft runtime
   умов, сторонніх notices, privacy/security текстів і підпису.
3. Підготувати окрему чисту Windows VM або ПК зі звичайним користувачем,
   без Python, Node і Docker. Створити тестовий каталог даних і контрольні
   копії; не використовувати реальні бази чи secrets.

## Authenticode signing для затвердженого випуску

Build scripts підтримують підписання EXE та installer через
`scripts/sign_windows_artifact.ps1`. Для public-release installer thumbprint
затвердженого сертифіката й RFC3161 timestamp URL обов'язкові; builder перевіряє
що EXE і отриманий installer мають валідний підпис від того самого сертифіката.
Portable internal candidate може лишатися непідписаним, але не стає через це
installer/release.
Сертифікат має бути чинним Code Signing certificate у `CurrentUser\My` або
`LocalMachine\My` із доступним private key. Скрипт знаходить лише підписаний
Microsoft `signtool.exe`, підписує SHA-256 і перевіряє Authenticode після запису;
private key не експортується. EXE підписується до створення build manifest,
installer — після компіляції.

Команди прикладові; замінити placeholder лише на організаційно затверджені
значення, не передавати private key у командному рядку й не зберігати секрети у
репозиторії:

```powershell
./scripts/build_release_candidate.ps1 `
  -DestinationParent 'D:\UFM_ReleaseSignedCandidate' `
  -SigningCertificateThumbprint '<approved-certificate-thumbprint>' `
  -TimestampServer '<approved-rfc3161-timestamp-url>'
./scripts/build_installer.ps1 `
  -BundleDir 'D:\UFM_ReleaseSignedCandidate\UFM Studio' `
  -OutputDir 'D:\UFM_InstallerSignedCandidate' `
  -PythonExe '.venv-release\Scripts\python.exe' `
  -SigningCertificateThumbprint '<approved-certificate-thumbprint>' `
  -TimestampServer '<approved-rfc3161-timestamp-url>'
```

Це автоматизація процесу, не факт наявності сертифіката чи підписаного релізу.
На цьому ПК придатного code-signing сертифіката у personal stores не знайдено;
Windows SDK `signtool.exe` присутній. Candidate4 лишається непідписаним; код
підписання не запускався і потребує затвердженого сертифіката/private key та
timestamp endpoint від власника релізу.

## Політика оновлень для поточної версії

- UFM Studio зараз не має автоматичної перевірки чи встановлення оновлень.
- Не встановлювати unsigned candidate поверх робочої `D:\UFM Studio`; збирати
  новий candidate окремо й спершу пройти цей протокол.
- Після затвердження підписаного релізу оновлення виконується вручну для
  per-user установки з перевіркою Authenticode, версії, manifest SHA-256 та
  відповідного SBOM перед запуском setup.
- Перед міграцією створити й перевірити backup. Дані/налаштування в
  користувацьких каталогах не включаються в installer і не видаляються при
  штатному uninstall; перевірити це на окремому профілі.
- Downgrade не підтримується як звичайне оновлення. Повернення на старішу
  версію дозволяти лише після сумісного restore/migration у контрольному
  середовищі; при помилці міграції зупинити оновлення й відновити перевірений
  backup.

Це release policy, а не реалізована/прийнята процедура: підпис, чиста Windows,
оновлення, міграція, відкат і збереження даних ще мають пройти окреме приймання.

## Перевірки portable folder та installer

1. Перевірити portable запуск без shell-консолі; створення даних користувача
   поза каталогом програми; мову, тему, навігацію та відображення помилок.
2. Перевірити Windows Credential Manager лише з тестовим credential; після
   рестарту перевірити збереження та вилучення цього тестового credential.
3. Перевірити шлях встановлення з Unicode/пробілами та стандартний
   `%LOCALAPPDATA%\Programs\UFM Studio`; звірити іконку/ярлики Start Menu та
   необов'язковий desktop shortcut.
4. Перевірити запуск після встановлення без dev dependencies; створення
   налаштувань/бази у user-data path, окремому від `{app}`.
5. Для оновлення зробити тестову резервну копію; змоделювати перерваний setup,
   повторний запуск, попередні дані та migration error. Не приймати, якщо
   rollback/restore лишає неоднозначний обліковий стан.
6. Видалити програму через штатний uninstaller. Перевірити, що видалені
   програмні файли/ярлики, а user data та резервна копія збереглись. Після
   цього відновити копію в окремий тестовий шлях.
7. Не вмикати automatic debit і не виконувати physical printer controls в
   цьому installer smoke-check. Їм потрібен окремий accounting/hardware gate.

## Результат та критерій

Для кожного кроку зберегти ОС/build, тестовий профіль, фактичний результат,
скриншоти/логи без credentials і точні SHA-256 артефактів. Pass означає, що
крок виконаний без неочікуваного підвищення прав, пошкодження даних чи втрати
user data; fail/невизначений результат блокує release. До заповнення звіту,
ліцензійного review, підпису та окремого погодження користувача candidate
залишається непідтвердженим і не замінює встановлену програму.

## Повторний локальний suite аудит — 2026-10-30

Locked Python 3.12.15 (`uv.lock`): окремий non-UI набір — 563 passed / 485
subtests, exit 0; `tests/integration/test_studio_window.py` окремо — 62 passed,
exit 0. Разом усі 625 tests / 485 subtests проходять, але запуск у єдиному
процесі падає після pytest summary з Windows access violation `0xC0000005`.
До з’ясування Qt/native teardown не трактувати summary як успішний завершений
run. Повторювана зараз перевірка: в одному locked Python 3.12 env із
`PYTHONPATH=src` виконати `python -m pytest -q --ignore=tests/integration/test_studio_window.py`,
потім окремим процесом `python -m pytest -q tests/integration/test_studio_window.py`;
обидва результати додати, жодну групу не пропускати. Studio-first повний запуск
одного разу завершився з exit 0, але повтор у тому самому зібраному порядку
знову отримав access violation, тому collection-order hook не залишено.
Після першого аудиту виправлені застарілі fixtures, не production source:
cutover authority тепер готується через application command, DB snapshot
впорядковується за реальним primary key, migration assertion відповідає 39
таблицям, а UI action registry перевіряє 22 записи та обидві сторони mapping.
Targeted suites: 63 passed / 24 subtests; projection crash recovery: 3 passed /
5 subtests. Ruff, Python/JSON/TOML/PowerShell AST і 115 локальних Markdown
посилань пройшли. Installer, встановлений застосунок, принтер та production
дані не запускались/не змінювались. Це не знімає блокери clean-Windows
acceptance, підпису, ліцензій і P0 printer accounting.


## Додаткова перевірка Qt/native exit — 2026-10-30

У locked Python 3.12.15 середовищі Studio-модуль пройшов 62/62 pytest assertions, але процес повторно завершився після summary з Windows access violation `0xC0000005` без Python frame. Розбиття на дві половини та групи по 10 здебільшого завершується з кодом 0; один повтор діапазону 31–40 теж аварійно завершився, а окремі та повторні виконання того ж діапазону завершилися успішно. Причину не встановлено; повний UI process exit лишається нестабільним і acceptance не пройдено. Non-UI: 563 passed/485 subtests/exit 0. `mypy src` (137 files) та `ruff check src scripts tests` clean. Не робити висновок про готовність до релізу лише зі статистики зелених assertions.


## Candidate5 — власницький ручний тест

- Portable bundle: `D:\UFM_TestCandidate5\UFM Studio` (зібрано з поточного source, Python 3.12.15 locked; 376 файлів manifest verified).
- EXE SHA-256: `4b7903fc2be099eec1b0f62db9137741fe17ad4eb10fe17d7162c2cd9b57ef35`; PE version `0.1.0.dev0`; Authenticode: `NotSigned`.
- Preliminary CycloneDX 1.7: `D:\UFM_TestCandidate5\UFM Studio.cdx.json`, 399 components, composition incomplete; SHA-256 `4227dac3dce6fe15b3d401405b38eb97970ffe31eb087b0446ce3d12d954d113`.
- Desktop shortcut `UFM Studio — ТЕСТ Candidate5.lnk` runs in Ukrainian and directs user data to `D:\UFM_TestCandidate5\Data`; the directory is created by the application on first launch. It does not replace the installed app or its database.
- Candidate5 було оглянуто лише візуально; повне власницьке ручне приймання не заявляється. Він придатний тільки для ізольованого внутрішнього тесту, не для публічного встановлення/розповсюдження.

## Candidate7 — оновлений UI test build

- Portable bundle `D:\UFM_TestCandidate7\UFM Studio`, побудований зі зміненого UI source locked Python 3.12.15; manifest перевіряє 376 файлів.
- EXE SHA-256 `cdb0d8dae0f2738ee6dd0824e64750c44238ef5983a09b7434cce27ad0402498`; PE version `0.1.0.dev0`; Authenticode `NotSigned`.
- Preliminary CycloneDX 1.7 sidecar `D:\UFM_TestCandidate7\UFM Studio.cdx.json`: 399 components, `composition=incomplete`; SHA-256 `e64a507b67361e92b295f0005631219429021088f3411b8261721a4d10fc0872`.
- Desktop shortcut `UFM Studio — ТЕСТ Candidate7.lnk` запускає ізольовані дані `D:\UFM_TestCandidate7\Data`; Candidate5, встановлений Candidate4 і два старі ярлики не перезаписані.
- Candidate7 був запущений для локального візуального огляду сторінок Філамент/Пристрої/Матеріали/Система і двох тем. `tests/integration/test_studio_window.py`: 62 passed/exit 0; Ruff і JSON parse clean. Не робили приймання власником, підключення принтера чи перевірку обліку.
- Це лише UI test build: він не підміняє formal release artifacts, не має підпису і не є повною/юридично затвердженою SBOM. Реліз блокується P0 job-to-spool/auto-debit, ліцензійним рішенням, native SBOM, code signing, Qt/native suite teardown, чистим Windows прийманням та hardware acceptance.


## Candidate9 — estimated-consumption provenance UI test build

- Portable bundle `D:\UFM_TestCandidate9\UFM Studio`; `build-manifest.json` verifies 376 files. EXE SHA-256 `99AF566B4E6CD3E38347437555C7ACCC7DB85C871585D31FE3CCE260B091AEE0`; PE version `0.1.0.dev0`; Authenticode `NotSigned`.
- CycloneDX 1.7 sidecar `D:\UFM_TestCandidate9\UFM Studio.cdx.json`: 399 components, `composition=incomplete`, SHA-256 `148438580A356B393A4563C580E62056BF8A127A9FCFF93E1DA26BD2CE3E42A8`. It is not a complete native SBOM or license approval.
- Desktop shortcut `UFM Studio — ТЕСТ Candidate9.lnk` points to this bundle and isolated `D:\UFM_TestCandidate9\Data`. Data directory did not exist at verification; Candidate9 was built but not launched.
- Source includes validated, limited estimated-consumption provenance in the spool history: existing job/receipt IDs and a short 3MF hash/plate summary only for validated metadata. Raw metadata and file paths are not shown. Existing Studio integration suite: 62 passed/exit 0; Ruff clean; locale JSON valid. E09.03 remains partial because full details UI and end-to-end job/receipt-to-spool acceptance remain open.
- Current locked full suite (Python 3.12.15): 625 passed/485 subtests in 3 of 4 consecutive full-process runs; one run exited 1 after all tests passed with no pytest failure detail. A subsequent `-X faulthandler` full run exited 0 with the same counts and no Python fault trace. The historical intermittent native teardown/process-exit issue is not explained or cleared by this sample; E16.01/E16.08 stability acceptance remains open.
- Candidate9 is for internal manual UI review only; no change to NOT READY public-release decision.

## Candidate8 — клавіатурний фокус UI test build

- Portable bundle `D:\UFM_TestCandidate8\UFM Studio`; manifest перевіряє 376 файлів, EXE SHA-256 `0DF64CCB71ACACB1B88A9669837F5FE72D42D6A265708017385AB0BCEC7598D3`, PE version `0.1.0.dev0`, Authenticode `NotSigned`.
- Preliminary CycloneDX 1.7 sidecar `D:\UFM_TestCandidate8\UFM Studio.cdx.json`: 399 components, `composition=incomplete`, SHA-256 `6AA4F3C1BDC4C3A904777012F412A2F849BAF85376C9CF1AADB1DFF4FBC567B0`.
- Desktop shortcut `UFM Studio — ТЕСТ Candidate8.lnk` points to the bundle and isolated `D:\UFM_TestCandidate8\Data`; data directory has not yet been created. Candidate8 was built but not launched in this review.
- Source adds visible keyboard focus borders; `tests/integration/test_studio_window.py`: 62 passed/exit 0; Ruff clean. Actual focus appearance, keyboard traversal and DPI matrix require manual acceptance. Candidate5/7 and installed/development shortcuts were preserved.
- Candidate8 remains unsigned, with incomplete SBOM; this is an internal test build only and does not change the NOT READY public-release decision.


## Candidate10 — історична portable UI-збірка для внутрішнього приймання — 2026-10-30

- Portable bundle: `D:\UFM_TestCandidate10\UFM Studio`; manifest перевірений — 376 файлів.
- EXE SHA-256: `D398AA91BEAD3495FF1B78DF1775CCB2E4A16B85CD421FAC54F64562B0D0BF02`; PE `0.1.0.dev0`; Authenticode `NotSigned`.
- CycloneDX 1.7 sidecar: `D:\UFM_TestCandidate10\UFM Studio.cdx.json`; 399 компонентів, `composition=incomplete`; SHA-256 `9fab23232057f20076bb8fecb6c5ad4bbb09e0ad6719d8903a3701310dc61156`.
- Desktop shortcut: `UFM Studio — ТЕСТ Candidate10.lnk`, окремі дані `D:\UFM_TestCandidate10\Data`. Candidate10 було запущено та візуально оглянуто на поточному ПК; SQLite тестової БД перевірено read-only. Це не clean-Windows/owner acceptance.
- Після поточних UI source changes: наявний `tests/integration/test_studio_window.py` — 62 passed/exit 0; `ruff check src scripts tests` clean; `mypy src` — 137 files, no issues.
- Лише внутрішній тестовий артефакт. НЕ ПУБЛІКУВАТИ: неповний SBOM, непідписаний EXE, відкритий ліцензійний/installer review, відсутність clean-Windows, owner/DPI та hardware acceptance, блокери accounting-authority/job identity і нестабільний історичний повний suite process exit.


### Candidate10 historical current-PC smoke result

Candidate10 was launched from its isolated desktop shortcut and visually reviewed on the current PC. Filament, Devices, Materials and System screens opened; it closed cleanly. Its isolated test DB was checked read-only: SQLite integrity `ok`, no foreign-key violations, schema revision `0007_haspel_authority_connection`. This is not clean-Windows install, owner/DPI, printer, Haspel cutover, full-suite stability, or public-release acceptance. No public gate is cleared by this smoke check.

## Candidate11 — ручний огляд нових локальних екранів — 2026-10-30

- Portable bundle: `D:\UFM_TestCandidate11\UFM Studio`; integrity manifest verified, 372 files.
- EXE SHA-256: `2002A8A8B588D2504F5CA65DA902DE1274EFD0D1EFC78CE09BFEAA33577B2D30`; PE version `0.1.0.dev0`; Authenticode `NotSigned`.
- Built using the local Python 3.12.14 `.venv312`, not the locked release Python 3.12.15. The manifest records source-input snapshot hashes; the root source revision remains unavailable.
- No Candidate11 SBOM sidecar was created. `write_release_sbom.py` failed closed with `sbom.lock_package_missing_or_ambiguous`; Candidate10's sidecar must not be copied or treated as applicable.
- Desktop shortcut at this checkpoint: `UFM Studio — ТЕСТ Candidate11.lnk`; it then targeted Candidate11 with isolated `D:\UFM_TestCandidate11\Data` and `uk-UA`. It has since been retargeted to Candidate12; Candidate11 files remain preserved.
- This build is for manual current-PC inspection only. It has not been launched or accepted by the owner in this checkpoint. Inspect booking review only after explicitly configuring a safe Haspel test endpoint; never activate UFM accounting, perform cutover, or send production stock changes as part of visual review. Public release remains NOT READY.

## Candidate12 — lock-aligned internal build and startup smoke — 2026-10-30

- Portable bundle: `D:\UFM_TestCandidate12\UFM Studio`; release build script verified the integrity manifest, 376 files.
- EXE SHA-256: `e0b52fa0a6dfd49226bc4b1a0d7dfcac23f14d83eb520695ccde83ba83187930`; version `0.1.0.dev0`; Authenticode `NotSigned`.
- Built with `.venv-release`, CPython 3.12.15, `uv sync --locked --extra desktop --extra build`; all 21 bundled runtime distributions match `uv.lock`.
- CycloneDX sidecar `D:\UFM_TestCandidate12\UFM Studio.cdx.json`: 399 components, all dependency references resolve, composition explicitly `incomplete`, and license review is only observed metadata. It is not a complete/legal SBOM.
- Launched only with `--data-dir "D:\UFM_TestCandidate12\Data" --locale uk-UA`. The fresh test database is isolated. The app opened to the Filament workspace with zero records; accessibility tree exposes navigation for Filament, Devices, Materials and System. A separate `--capture` run exited 0 and saved `D:\UFM_TestCandidate12\Review\filament-home.png` (1360×858); it shows the empty dashboard/table, filters/actions and a scrollable spool-details panel. Other pages, buttons/forms, DPI, printer, network, Haspel endpoint or production DB were not exercised; owner acceptance remains pending.
- Desktop test shortcut `UFM Studio — ТЕСТ Candidate12.lnk` targets Candidate12 and its isolated data directory; the previous test-only shortcut was retargeted, not duplicated. Candidate11, regular UFM shortcuts, installed application and user data remain preserved. No installer was built or installed; public release remains NOT READY.

## Candidate13 — internal build with local sliced-file review — 2026-10-30

- Portable bundle: `D:\UFM_TestCandidate13\UFM Studio`; independent `verify_manifest` rerun returned 377 verified entries (the directory has 378 files because it also contains the manifest).
- EXE SHA-256 `6053106251974122F63CF06781E94805A84BD2093A14E7D7C5A90AF36372E664`; Product/File version `0.1.0.dev0`; Authenticode `NotSigned`.
- Built with `.venv-release`, CPython 3.12.15. The packaged CycloneDX 1.7 sidecar has 400 components, SHA-256 `46DCE4D2B7B72D2A542DC62805714AEF45B5D946D0B86B98E17CC929F2AD351C`, and composition `incomplete`; it is not a complete/legal SBOM.
- Desktop test shortcut `UFM Studio — ТЕСТ Candidate13.lnk` was read back and targets this EXE with `--data-dir "D:\UFM_TestCandidate13\Data" --locale uk-UA`; standard UFM/Universal Filament Manager shortcuts were not changed.
- Candidate13 was launched with the isolated data directory. Screenshot inspection confirmed the Devices tab displays `Перевірити локальний 3MF/G-code`. This proves the new UI action is present in the candidate; no user-provided file was parsed via the UI in this check, and no accounting or stock change was made.
- Current focused source checks before build: 23 passed plus 90 subtests; 70 deselected; Ruff and compileall clean. This does not override the separate intermittent native Qt teardown access violation recorded above.
- Candidate13 is for internal manual review only. No clean-Windows, hardware/printer, Haspel cutover, installer/update/rollback, owner DPI/accessibility, or public-release acceptance is claimed. Release remains NOT READY.

## Candidate15 — попередня внутрішня збірка, остання з перевіреним UI — 2026-10-30

- Portable bundle: `D:\UFM_TestCandidate15\UFM Studio`; independent manifest verification: 374 files. EXE SHA-256 `3D7B92A2117FEDCDBC3EAA23D69BDFC16B6B77FE686E76CA353FB83A4BC9E71B`; PE version `0.1.0.dev0`; Authenticode `NotSigned`; no complete SBOM sidecar.
- Desktop shortcut `UFM Studio — ТЕСТ Candidate15.lnk` was read back to verify the target, `--data-dir "D:\UFM_TestCandidate15\Data" --locale uk-UA`, and isolated working directory. System page showed resolved `D:\UFM_TestCandidate15\Data\data`; no installed user data was opened.
- Candidate15 was visually reviewed on this PC at 1360×860: Filament, Devices, Materials and System; light/dark toggle tested and light mode restored. Empty-state actions were inert/disabled as expected. This is limited local visual smoke only; no owner, physical DPI/accessibility, printer, Haspel, clean-Windows or installer acceptance.
- Current suite evidence and the intermittent Qt process-exit defect are summarized at the top of this document. Do not infer release readiness from the internal candidate or a single green suite run.
