# Центробежные 1 / 2 — установка на панель обзвона

## 1. Что это и что появится на панели

На https://parsercompressor.online/obzvon/ добавляются **две новые базы**:

| Слаг | Название на панели | Что внутри | Адрес |
|---|---|---|---|
| `centro1` | Центробежные 1 | база продажников, 555 ИНН | `/obzvon/centro1` |
| `centro2` | Центробежные 2 | ядро центробежных, 396 ИНН | `/obzvon/centro2` |

Базы **`kc` и `meyer` не трогаются вообще** — ни их код, ни их данные, ни их вёрстка.
Новые страницы — отдельные маршруты и отдельные шаблоны.

Что на страницах:

* карточка компании со всеми данными: реквизиты (ОГРН, КПП, статус, адрес, директор,
  учредители), ОКВЭД основной и все, оборудование, выручка/прибыль/численность,
  приоритет, сайт;
* контакты из обогащения: телефоны и почты **с именем и должностью**, блок
  «Закупки и снабжение — звонить сюда» идёт первым;
* **у каждого телефона и почты — живая ссылка на страницу-источник** (карточка
  закупки ЕИС, staff-страница сайта компании, карточка checko). Это главное
  требование: видно, откуда номер, и это можно открыть в новой вкладке. Если
  источник неизвестен (контакт достался из базы продажников) — так и написано,
  «ссылки на источник нет», а не молчание;
* новостные поводы (сигналы) с ссылкой на новость;
* режим списка с постраничной листалкой, фильтры по региону/ОКВЭД/наличию
  контактов, поиск по имени / ИНН / адресу / директору;
* оформление ближе к панели рассылки: тёмно-синяя шапка, карточки, бейджи,
  счётчики базы. Pico CSS не выкидывался, React не появился — только свой
  `centro.css`, который подключается **только** на страницах centro.

Данные лежат в **отдельном файле** `C:\seostat\data\centrifugal.db`. Не в `seo.db`
(11 ГБ, общая с SEO-аналитикой) и не в `enrich.db` (её пишет боевое обогащение).
Панель открывает этот файл **только на чтение** (`mode=ro`) — записать в него она
физически не может, блокировок обогащению не создаёт.

---

## 2. Какие файлы куда ложатся

Пять новых файлов + правка одного боевого.

| Файл в репозитории (`seo-texts/obzvon-centro/`) | Путь на сервере |
|---|---|
| `routes_centro.py` | `C:\seostat\app\api\routes_centro.py` |
| `centro.html` | `C:\seostat\app\templates\centro.html` |
| `centro_card.html` | `C:\seostat\app\templates\centro_card.html` |
| `centro_list.html` | `C:\seostat\app\templates\centro_list.html` |
| `centro.css` | `C:\seostat\app\static\css\centro.css` |
| `build_centrifugal_db.py` | `C:\sender\_ops\build_centrifugal_db.py` (запускается вручную, в панель не входит) |

Правится ровно один боевой файл: `C:\seostat\app\obzvon.py` (две строки, см. шаг 3).

> **Внимание по путям шаблонов.** В докстрингах внутри `routes_centro.py` и
> `centro.html` написано `C:\seostat\app\web\templates\` и
> `C:\seostat\app\web\static\` — это описка. Реальные каталоги на сервере —
> `C:\seostat\app\templates\` и `C:\seostat\app\static\css\` (по ним лежат
> `obzvon.html`, `obzvon_base.html`, `app.css`, туда же клала файлы прошлая
> выкатка пагинации). Проверить одной командой:
>
> ```powershell
> Get-ChildItem C:\seostat\app\templates\obzvon_base.html, C:\seostat\app\static\css\app.css
> ```
>
> Если обе строки нашлись — кладём рядом с ними. Если нет — искать так:
> ```powershell
> Get-ChildItem C:\seostat\app -Recurse -Filter obzvon_base.html
> ```

---

## 3. Шаг 1 — собрать `centrifugal.db` (на сервере)

Сборщик читает боевые источники **строго read-only**, боевому обогащению не мешает,
запускать можно в любой момент, в том числе прямо во время прогона обогащения.

Источники (все уже на сервере, ничего качать не надо):

```
C:\sender\obzvon-index.db                                таблица obzvon, 161 799 юрлиц
C:\sender\enrich.db                                      companies / phone_contacts / emails / signals
C:\sender\_ops\sales_base.json                           555 ИНН -> centro1
C:\seostat\drop\drop-storage\centrifugal-core-inns.txt   396 ИНН -> centro2
C:\sender\server\core396.json                            необязательно, имена/выручка ядра
```

Положить скрипт и запустить:

```powershell
$tok=(Select-String -Path C:\sender\server\runner-secrets.env -Pattern 'DROP_TOKEN=').Line.Split('=',2)[1].Trim()
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/build_centrifugal_db.py" -Headers @{'X-Drop-Token'=$tok} -OutFile C:\sender\_ops\build_centrifugal_db.py
& "C:\Program Files\Python311\python.exe" C:\sender\_ops\build_centrifugal_db.py
```

Без аргументов пишет в `C:\seostat\data\centrifugal.db` (каталог создаст сам).
Внешних зависимостей нет — только стандартная библиотека, Python 3.7+.
Полный путь к python указан намеренно: `py` без версии на этом сервере = 3.12.

**Сколько ждать.** Выборки идут точечно (`WHERE inn IN (...)` по ~950 ИНН), а не
полным перебором 161k строк, поэтому ожидание — от нескольких секунд до пары минут.
Точное время скрипт печатает сам в поле `"секунд"`. Если прогон затянулся дольше
5 минут — значит, в `obzvon-index.db` нет индекса по `inn` и каждый чанк идёт
сканом; это не поломка, просто дождаться.

**Что прочитать в напечатанном JSON-отчёте:**

| Поле | Что должно быть |
|---|---|
| `базы.centro1.ИНН_в_списке` | 555 |
| `базы.centro2.ИНН_в_списке` | 396 |
| `нашлось_в_базе_обзвона` | близко к числу ИНН в списке; сильно меньше — проверить путь к `obzvon-index.db` |
| `со_ссылкой_источником` | сколько контактов получили живую ссылку — главный показатель, ради него всё делалось |
| `мусорных_телефонов_отброшено` | десятки-сотни — норма (ОГРН и расчётные счета, попавшие в телефонные колонки). Тысячи — сказать сессии, в колонки телефонов попало что-то неожиданное |
| `предупреждения` | должно отсутствовать. Если есть «нет источника: …» — путь не совпал, поправить ключом `--obzvon` / `--enrich` / `--sales` / `--core` |
| `итого` | компаний ≈ 951, контактов и сигналов — сколько нашлось |

Код возврата `2` и поле `ОТКАЗ` в отчёте = сработал предохранитель: новая сборка
получилась пустой, а в старом снимке данные были. Скрипт **не** затёр рабочий файл.
Причина почти всегда — неверный путь к источнику. Перезаписать намеренно — ключ `--force`.

Проверить, что снимок не в WAL (панель не откроет WAL-базу в режиме read-only):

```powershell
& "C:\Program Files\Python311\python.exe" -c "import sqlite3;print(sqlite3.connect(r'C:\seostat\data\centrifugal.db').execute('PRAGMA journal_mode').fetchone())"
```

Должно напечатать `('delete',)`. Если `('wal',)` — сказать сессии: панель не умеет
открывать WAL-базу в режиме read-only и покажет плашку «база не найдена».

---

## 4. Шаг 2 — доставить файлы панели

Панель обзвона живёт в `C:\seostat\app`, куда операция `panel_file_put` не пишет
(она ограничена `C:\sender`). Значит — только дроп. Два способа.

### Вариант А (рекомендуемый): пакет + `update-obzvon.ps1`

Даёт автоматический бэкап, остановку службы, распаковку и **автооткат**, если
панель не поднялась.

**Сторона песочницы** (делает сессия, не владелец). Скрипт сборки берёт файлы из
`seo-texts/sender-patches/obzvon-pagination/`, разворачивая двойное подчёркивание
в каталоги, поэтому пять файлов надо положить туда под плоскими именами:

```bash
cd /home/user/avto/seo-texts
cp obzvon-centro/routes_centro.py  sender-patches/obzvon-pagination/api__routes_centro.py
cp obzvon-centro/centro.html       sender-patches/obzvon-pagination/templates__centro.html
cp obzvon-centro/centro_card.html  sender-patches/obzvon-pagination/templates__centro_card.html
cp obzvon-centro/centro_list.html  sender-patches/obzvon-pagination/templates__centro_list.html
cp obzvon-centro/centro.css        sender-patches/obzvon-pagination/static__css__centro.css
bash server/build_panel_update.sh obzvon        # соберёт obzvon-update.zip и зальёт на дроп
```

> **Осторожно, это не бесплатно.** `build_panel_update.sh obzvon` пакует **весь**
> каталог `obzvon-pagination`, а там уже лежат четыре файла прошлой выкатки —
> `api__routes_obzvon.py`, `db__models.py`, `services__callbase.py`,
> `templates__obzvon.html`. Они уедут вместе с новыми и **перезапишут боевые**.
> Если с той выкатки боевые файлы правились на сервере, их правки пропадут
> (ровно так репозиторий однажды уже отставал от боя). Перед сборкой пакета —
> `python seo-texts/server/preflight_panel.py`, он сверяет хэши и возвращает 1,
> если файл в репо меньше живого. Если preflight ругается или доверия нет —
> брать вариант Б.

**Сторона сервера** (владелец, PowerShell, по одной команде, без `&&`):

```powershell
$tok=(Select-String -Path C:\sender\server\runner-secrets.env -Pattern 'DROP_TOKEN=').Line.Split('=',2)[1].Trim()
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/update-obzvon.ps1" -Headers @{'X-Drop-Token'=$tok} -OutFile C:\sender\update-obzvon.ps1
powershell -ExecutionPolicy Bypass -File C:\sender\update-obzvon.ps1
```

Скрипт сам: качает `obzvon-update.zip`, делает бэкап перезаписываемых файлов в
`C:\seostat\_bak-obzvon-<дата-время>`, останавливает службу `obzvon`, распаковывает
поверх `C:\seostat\app`, запускает службу, проверяет живость на
`http://127.0.0.1:8012/obzvon/kc` (401 считается успехом — это штатная
Basic-авторизация продажников), и при неудаче откатывается сам.

После этого всё равно нужен **шаг 3** — двух строк в `obzvon.py` в пакете нет,
боевой файл скрипт не правит.

### Вариант Б: прямая заливка пяти файлов

Ничего лишнего не трогает, но бэкап и откат — руками.

Сессия кладёт файлы на дроп (`drop_client.sh up <файл>`) под теми же именами, что
в репозитории. Владелец:

```powershell
# бэкап того, что перезапишем (в первый раз перезаписывать нечего — файлы новые)
$b = "C:\seostat\_bak-centro-" + (Get-Date -Format 'yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Path $b -Force

$tok=(Select-String -Path C:\sender\server\runner-secrets.env -Pattern 'DROP_TOKEN=').Line.Split('=',2)[1].Trim()
$h = @{'X-Drop-Token'=$tok}
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/routes_centro.py"  -Headers $h -OutFile C:\seostat\app\api\routes_centro.py
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/centro.html"       -Headers $h -OutFile C:\seostat\app\templates\centro.html
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/centro_card.html"  -Headers $h -OutFile C:\seostat\app\templates\centro_card.html
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/centro_list.html"  -Headers $h -OutFile C:\seostat\app\templates\centro_list.html
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/centro.css"        -Headers $h -OutFile C:\seostat\app\static\css\centro.css
```

Проверить, что все пять легли и не пустые:

```powershell
Get-ChildItem C:\seostat\app\api\routes_centro.py, C:\seostat\app\templates\centro*.html, C:\seostat\app\static\css\centro.css | Select-Object FullName, Length
```

Ожидаемые размеры примерно: `routes_centro.py` ~42 КБ, `centro.css` ~35 КБ,
`centro.html` ~13 КБ, `centro_card.html` ~16 КБ, `centro_list.html` ~10 КБ.

---

## 5. Шаг 3 — две строки в `C:\seostat\app\obzvon.py`

Правится **только этот файл**. `routes_obzvon.py`, `callbase.py`, `models.py`
не трогаются вообще.

**а)** В блок импортов, рядом со строкой

```python
from app.api import routes_obzvon
```

добавить

```python
from app.api import routes_centro
```

**б)** Внутри `create_app()`, сразу **после** строки

```python
    app.include_router(routes_obzvon.router, prefix=obz)
```

добавить (с теми же четырьмя пробелами отступа)

```python
    routes_centro.include_centro(app, obz)
```

**Обязательно выше строки `return BasicAuthASGI(app, users)`** — то есть на объекте
FastAPI, а не на обёртке авторизации. Иначе новые страницы окажутся снаружи
Basic auth и откроются без пароля.

Порядок относительно других строк не важен: `include_centro` сама ставит свои
маршруты выше боевого catch-all `/{base}` (иначе тот перехватил бы `/centro1` и
ответил «Неизвестная база обзвона»). Повторный вызов безопасен — функция
идемпотентна.

Должно получиться так:

```python
    app.mount(f"{obz}/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(routes_obzvon.router, prefix=obz)
    routes_centro.include_centro(app, obz)
```

### Необязательно: ссылки на новые базы в общей шапке

Без этого шага со страниц `kc`/`meyer` на `centro1`/`centro2` перейти нельзя (только
по прямому адресу), а обратно — можно: вкладки kc/meyer выведены на самих страницах
centro. Чтобы ссылки появились везде, в `C:\seostat\app\templates\obzvon_base.html`
сразу после существующего цикла

```jinja
        {% for slug, name in bases.items() %}
        <li><a href="{{ base_path }}/{{ slug }}" {% if slug == base %}aria-current="page"{% endif %}>{{ name }}</a></li>
        {% endfor %}
```

добавить такой же цикл:

```jinja
        {% for slug, name in (centro_bases or {}).items() %}
        <li><a href="{{ base_path }}/{{ slug }}" {% if slug == base %}aria-current="page"{% endif %}>{{ name }}</a></li>
        {% endfor %}
```

Конструкция `(centro_bases or {})` — чтобы шаблон не сломался, если роутер centro
когда-нибудь отключат.

---

## 6. Шаг 4 — перезапуск

```powershell
Restart-Service obzvon -Force
```

Перезапускается **только служба обзвона**. Основной сервис статистики (`seostat`),
рассыльщик (`SenderPanel`) и раннер (`rusprom-runner`) не трогаются, боевое
обогащение продолжает идти.

Если использовался вариант А — службу уже перезапустил `update-obzvon.ps1`, но
после правки `obzvon.py` (шаг 3) перезапуск нужен ещё раз.

---

## 7. Что проверить после установки

По порядку, всё в браузере под обычным логином продажника:

1. **`/obzvon/centro1`** открывается — тёмно-синяя шапка, счётчики базы в правом
   верхнем углу заголовка, карточка компании.
2. **`/obzvon/centro2`** открывается и показывает другую базу (396 ИНН, счётчик
   «всего» в шапке отличается от centro1).
3. **`/obzvon/kc` и `/obzvon/meyer`** работают ровно как раньше — тот же вид,
   листалка, кнопки. Их вёрстка не меняется ни на пиксель: `centro.css`
   подключается только со страниц centro.
4. **Кликабельность (главное).** В карточке centro1 у телефона нажать ссылку
   источника — должна открыться живая страница: карточка закупки на
   `zakupki.gov.ru`, страница сотрудников на сайте компании или
   `checko.ru/company/<ОГРН>`. Проверить хотя бы одну ссылку каждого типа.
5. **Блок «Закупки и снабжение — звонить сюда»** идёт первым в списке контактов,
   если закупщики у компании найдены.
6. **Режим списка**: переключить на список, полистать, проверить что телефон
   кликабелен и в таблице тоже, и что номер строки списка совпадает с той
   компанией, которая открывается по клику.
7. **Глазами 5 карточек подряд** — нет ли пустых блоков, не съехало ли что-то.
8. **`/obzvon/centro3` отдаёт 404**, а не белый экран и не 500.
9. **Переключатель скина** (кнопка 🌿/👑 в шапке) перекрашивает страницу centro
   целиком, включая шапку.
10. В логе службы при старте должна быть строка
    `centro: подключены базы centro1, centro2 (БД C:\seostat\data\centrifugal.db)`.
    Если вместо неё `centro: база … не найдена` — снимок не собран или лежит не там.

Если страница открывается, но вместо данных красная плашка вида «База центробежных
не найдена: C:\seostat\data\centrifugal.db…» — это не падение, а честное сообщение:
файла нет, он битый или в WAL. 500-й продажник не увидит ни в одном из этих случаев.

---

## 8. Как откатить

**Быстрый откат (панель работает, новые базы просто исчезают).** Убрать из
`C:\seostat\app\obzvon.py` две строки шага 3 и перезапустить:

```powershell
Restart-Service obzvon -Force
```

Всё возвращается ровно к прежнему состоянию. Файлы `routes_centro.py`,
`centro*.html`, `centro.css` можно оставить лежать — без строки `include_centro`
они никуда не подключены и ни на что не влияют.

**Если правилась шапка** — убрать из `obzvon_base.html` добавленный цикл по
`centro_bases` (или оставить: без роутера `centro_bases` не определён и
`(centro_bases or {})` даст пустой список, шапка не сломается).

**Откат самих файлов** (вариант А): `update-obzvon.ps1` кладёт бэкап в
`C:\seostat\_bak-obzvon-<дата-время>` и при неудачном старте откатывается сам.
Ручной откат из бэкапа:

```powershell
Stop-Service obzvon -Force
Get-ChildItem C:\seostat\_bak-obzvon-<дата-время> -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring("C:\seostat\_bak-obzvon-<дата-время>".Length).TrimStart('\')
    Copy-Item $_.FullName (Join-Path "C:\seostat\app" $rel) -Force
}
Start-Service obzvon
```

**Удалить всё начисто:**

```powershell
Remove-Item C:\seostat\app\api\routes_centro.py
Remove-Item C:\seostat\app\templates\centro.html, C:\seostat\app\templates\centro_card.html, C:\seostat\app\templates\centro_list.html
Remove-Item C:\seostat\app\static\css\centro.css
Remove-Item C:\seostat\data\centrifugal.db
Restart-Service obzvon -Force
```

Базы `kc` и `meyer` при любом из этих сценариев не затрагиваются: их данные лежат
в другой БД (`call_company`), их код не правился.

---

## 9. Пересборка снимка

`centrifugal.db` — это **снимок**, а не живая база. Новые контакты, найденные
обогащением, попадут на панель только после пересборки.

Пересобирать после каждой волны обогащения, той же командой:

```powershell
& "C:\Program Files\Python311\python.exe" C:\sender\_ops\build_centrifugal_db.py
```

Повторный запуск идемпотентен: таблицы пересоздаются целиком внутри одной
транзакции, поэтому панель до самого COMMIT видит **старый** снимок и никогда —
полупустой. Службу обзвона перезапускать не надо, кэш страниц протухает сам.
Можно повесить на расписание.

---

## 10. Известные риски и грабли

* **401 при проверке — это норма**, штатная Basic-авторизация обзвона, а не
  падение. Прошлая выкатка пагинации была откачена скриптом, который принял 401
  за отказ.
* **Маршруты смонтированы под `/obzvon` даже локально.** Проверять
  `http://127.0.0.1:8012/obzvon/kc`, а не `/kc` — иначе штатный 404 примем за поломку.
* **Каталог `C:\seostat\data`** должен быть доступен на запись пользователю, под
  которым запускается сборщик, и на чтение — пользователю службы `obzvon`.
* **Ни в одном новом файле нет внешних CDN** — ни шрифтов, ни скриптов, ни
  картинок с чужих доменов. Панель продолжает работать без интернета.
* **Не проверено локально и требует взгляда на сервере**: реальные числа
  `нашлось_в_базе_обзвона` против 555 и 396; версия вендоренного
  `pico.min.css` на сервере (анализ каскада делался на Pico v2); работа хотя бы
  одной ссылки-источника каждого типа.
* **Хрупкое место вёрстки**: перекраска шапки на страницах centro привязана к
  селектору `main.container > nav:first-child`. Если в `obzvon_base.html` когда-нибудь
  появится элемент перед этим `<nav>`, шапка на centro молча перестанет краситься.
  Страница при этом останется рабочей.
* **Один известный ложноположительный в фильтре телефонов**: 10-значный ИНН,
  начинающийся на 7, пройдёт как номер. Сработает, только если ИНН просочится в
  телефонную колонку источника. Поведение унаследовано от боевого
  `build_contacts_xlsx.py`, менять его в одиночку нельзя.
