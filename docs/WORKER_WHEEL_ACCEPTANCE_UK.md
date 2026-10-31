# Контроль пакета модулів worker

2026-10-28: повтор попередньої невдалої sandbox збірки виконаний поза sandbox
з потрібним системним дозволом. Команда build --wheel --no-isolation успішна.
Старі dist та встановлений EXE не перезаписані. Контрольний пакет лежить у
.runtime/wheel-acceptance, це перевірка вихідного Python пакета.

scripts/check_worker_wheel.py розпаковує wheel у тимчасову папку, запускає
Python -I поза checkout і перевіряє походження шести нових модулів, міграцію
нової бази й повторний no-op, canonical MJS ресурс, default-disabled policy
та точну Decimal екструзію 11мм. Завантаження залежностей не потрібне.
Пакет містить122entries; тестові SQLite/журнали/.env не включені.

Перший успішний пакет до нової міграції:
SHA256 e7c99c092fbbd00fa9cbd03fb8c4ab2449476219bef5086273d679ac84ea234b,
revision0001_initial. Report .runtime/wheel-acceptance/report.json.
Після зміни схеми або коду потрібні нова збірка та новий report.

Node engine/runtime і transitive dependencies ще не bundled. Ця перевірка
не доводить запуск на чистій Windows і не є готовим релізом чи новим EXE.

Повтор після приймання0002: SHA256
2024d49ee7ea5304f411f39a4b1dc83eeb8f1060679fc54ceb4806d2060767a9,
128entries, 8module origins, migration0002_job_projection і порожня projection
queue успішні. Поточний report.json стосується цього повтору. Перший0001
digest вище збережений лише як історичний доказ, не поточний артефакт.

Поточний повтор після artifact/binding/drain: SHA256
efa11934b6700c32da6900acff2683f70bd73247e2953c17c62da928a6f8be34,
132entries,11module origins. Порожня projection queue, повторне3MF artifact
store/load, Decimal та migration0002 пройшли поза checkout. report.json
оновлений; це актуальний wheel цього source checkpoint. Nodeengine ще відсутній.

Фінальний повтор після cross-receipt run-quarantine acceptance: SHA256
1f1175e2466855dd16c6f8f8b42b1fd4a01dc85c05879b3fea604a160e1c90b1,
132entries. 11module origins, migration0002, queue та verified-artifact
reload smoke пройшли; `projection_drain` завантажується з wheel поза checkout.
Report.json відповідає цьому digest. Node engine не включений.

Повтор після provider start-time provenance DTO: wheel у
`.runtime/wheel-acceptance-20261028-timing-provenance`, 132 entries, 11 module
origins, migration0002, projection queue, parser artifact reload та canonical
MJS smoke пройшли. SHA256
`f3ec539fc7864e7e83e51f35e2b9a1fa4dfe00427e2b12103d4aa121a1485aa5`;
report у цій самій папці. Node engine досі не bundled.

Повтор після trusted spool identity lookup/resolver:
`.runtime/wheel-acceptance-20261028-slot-identity`, 133 entries,12 module
origins, включно з `ufm.application.slot_spool_identity`; migration0002,
projection queue, verified parser-artifact reload, Decimal і canonical MJS
перевірені поза checkout. SHA256
`ba7d3c113a0ad74ac5b45f8dcd3bccbddf85d6271bbbd18218d5560485083304`, report у
цій папці. Node engine не bundled.

Після provider cleanup (`probe_configured_printer`/local setup) wheel у
`.runtime/wheel-acceptance-20261028-provider-cleanup` пройшов offline smoke:
133 entries,12 module origins, зокрема slot resolver; migration0002, canonical
MJS та parser artifact reload успішні. SHA256
`f15c5b262f02f592ba806a9246def3d63f42697f9ba6ce00f38c0aa8cfea3c80`, report у
цій папці. Node runtime не bundled.

Після explicit spool-identifier confirmation command wheel у
`.runtime/wheel-acceptance-20261028-identifier-confirmation` пройшов offline
smoke поза checkout:134 entries,13 module origins, включно з
`ufm.application.spool_identifiers`; migration0002, порожня projection queue,
verified artifact reload, Decimal extrusion та canonical MJS пройшли.
SHA256 `ee2f6a01031af4b9442382cfc403a828174b14f9364d8963af4e7c0199111ef8`;
report у цій папці. Node runtime не bundled.

Після read-only Bambu feed-slot mapping view wheel у
`.runtime/wheel-acceptance-20261028-feed-slot-view` пройшов той самий isolated
smoke:134 entries/13 module origins; SHA256
`55de1ade94054fe6f7a0497a1bfc5cdc37b0bba10d8a479c16a9f2ecb97ddb5b`, report
у цій папці. Node runtime не bundled; wheel не є готовою Windows-збіркою.

Після UI enrollment явного підтвердження wheel у
`.runtime/wheel-acceptance-20261028-identity-enrollment-ui` пройшов isolated
smoke:134 entries/13 module origins; SHA256
`2a8c78c3f2f5dadbc1dd6f1f35fac29691b5c5693c1cd829d4a302e3cd240710`, report
у цій папці. Node runtime не bundled; wheel не є готовою Windows-збіркою.

Після explicit provider-slot mount wheel у
`.runtime/wheel-acceptance-20261028-explicit-slot-mount` пройшов isolated smoke:
134 entries/14 module origins, включно з `ufm.application.topology`; SHA256
`78693b70deebbd34217095de5b096ff343c25b498d5b371c9d05a417972cddd6`, report у
цій папці. Node runtime не bundled; wheel не є готовою Windows-збіркою.

Після durable provider-slot snapshot projection wheel у
`.runtime/wheel-acceptance-20261028-slot-snapshot-projection` пройшов isolated
smoke:134 entries/14 module origins; SHA256
`717be383a08770d51af5a17d1c5d5fbebc5208f941666b2c2f83160795cccfc6`; report у
цій папці. Node runtime не bundled; wheel не є готовою Windows-збіркою.

Після explicit Bambu printer-reported logical material→provider slot DTO wheel
у `.runtime/wheel-acceptance-20261028-printer-logical-slot` пройшов isolated
smoke:134 entries/16 module imports; mapping decoder smoke, migration, projection
queue, parser artifact, Decimal extrusion і canonical worker entrypoint успішні.
SHA256 `40a358c035fba822f8e3c32384d83f015bb94cee6aa1d4795625720732fd1436`;
report у цій папці. Node runtime не bundled; mapping DTO ще не durable і не
є підставою для автоматичного assignment або списання.

Після schema `0003_logical_material_index` wheel у
`.runtime/wheel-acceptance-20261028-logical-material-index` пройшов isolated
smoke:136 entries/16 module imports; revision 0003, mapping decoder, parser
artifact, queue та canonical worker checks успішні. SHA256
`317194e73321d1beb33282f6abb7e9d3153499832537e97f3b2873c973c452fb`; Node
runtime не bundled і це не готовий EXE.

Після додавання fail-closed `resolve_job_material_slots()` wheel у
`.runtime/wheel-acceptance-20261029-job-slot-reconciliation` пройшов isolated
smoke з 137 members/17 імпортами. Resolver доступний із пакета; worker
mapping/receipt contract, migration0003, verified 3MF artifact, Bambu mapping
decoder і canonical worker entrypoint також пройшли smoke. SHA-256
`51392013ad591bbf54dfc9b12c1b6324d43478cd1f2df1134e984d9ca8aa399b`; Node
runtime не bundled. Wheel не встановлювався поверх EXE й не є готовою Windows
збіркою.

Після exact durable `FeedSlot`/active mount/verified RFID join wheel у
`.runtime/wheel-acceptance-20261029-mounted-material-resolver` пройшов isolated
smoke з 138 members/18 module imports. Обидва нові mapping resolver модулі,
logical-index migration, verified 3MF, worker receipt та canonical worker
entrypoint пройшли smoke; SHA-256
`5cfdfb1cbb9660b8a2061d50759246ff587d4c8469cc9d928fe6083794a4b3ca`.
Node runtime не bundled; installed EXE не змінювався.

Після розділення `logical_material_index` від фізичного `tool_index` у
calculated-finalization wheel `.runtime/wheel-acceptance-20261029-logical-material-finalization`
пройшов isolated smoke з 138 members/18 module imports. Модуль фіналізації,
обидва read-only mapping resolvers, міграція0003, verified artifact і canonical
worker entrypoint імпортуються; SHA-256
`9b48398bb158aed822f9ca56d02f1756d501cc675de5b6b636c98c1e160fb160`. Це не
включає запуск live списання й не є встановленим EXE.
