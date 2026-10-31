# Стандартні дії Spoolman, успадковані від Refine

Перевірено 2026-10-27. `client/package-lock.json:3362` фіксує
`@refinedev/antd` **6.0.3**. Завантажено саме цей npm archive без установлення
або виконання пакетного коду; SHA512 звірено з lockfile:

`sha512-adNxHZJuca3TN4y1zXpamspqc0yi5hAqlzveTKAXLDuZ8C546xPdihmpZ/bWGG1fjYzWKLctb3YIoUw6d/WDgA==`.

Приватна копія джерел: `.runtime/refine-antd-6.0.3/package/src/components/`.
Відтворення: `.runtime/fetch_refine_sources.py` (cache також перевіряється).
Це закриває невідомий склад `defaultButtons` у статичному аудиті E02.01.

| Контекст | Успадковані дії | Доказ у package/src/components/ |
|---|---|---|
| List | Create за наявності create route / canCreate | crud/list/index.tsx:48,64,65 |
| Show | List, Edit, Delete, Refresh за доступними ресурсами/permissions | crud/show/index.tsx:84,87,123–126 |
| Edit header | List і Refresh | crud/edit/index.tsx:130,131 |
| Edit footer | Delete за canDelete, Save | crud/edit/index.tsx:91,137,138 |
| Create footer | Save; custom footer може замінити | crud/create/index.tsx:58,66,113 |
| Delete | Popconfirm, OK/Cancel, onConfirm → hook mutation | buttons/delete/index.tsx:42–72 |

Spoolman `client/src/App.tsx:110–140` задає list/create/edit/show routes
і `meta.canDelete: true` для spool, filament, vendor. Їхні редактори
використовують Edit; Show зберігає defaultButtons, доповнюючи їх власними
діями. Create у локальних сторінках замінює footer на Save/Save-and-add.
У Qt треба перенести list/back, refresh, edit і підтверджене видалення всіх
трьох сутностей; не загубити Delete через відсутність literal `<DeleteButton>`
у Spoolman сторінці. Видалення з залежними записами потребує окремого
контракту помилки API; не обіцяти каскадне видалення без перевірки.

Цю поведінку також описують офіційні [Show](https://refine.dev/core/docs/ui-integrations/ant-design/components/basic-views/show/),
[Edit](https://refine.dev/core/docs/ui-integrations/ant-design/components/basic-views/edit/)
та [Delete](https://refine.dev/core/docs/ui-integrations/ant-design/components/buttons/delete-button/).
Для конкретної локальної версії авторитетним є перевірений архів 6.0.3.

Видимість на живому екрані, permission provider, візуальне підтвердження,
помилки сервера й збереження після дії тут не тестувалися. Це наступні
приймальні перевірки, а не причина приписувати невідомий склад кнопок.
