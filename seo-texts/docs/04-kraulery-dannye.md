# Краулеры сайта и сбор исходных данных

Документ описывает область «сбор сырья» проекта `seo-texts/`: скрипты, которые ходят
в сеть за данными (сайт prokompressor.ru, сайты производителей), скрипты, которые
разбирают тяжёлые выгрузки (Битрикс, база обзвона), и каталоги, где лежат результаты.

Всё проверено по коду и по локальным данным на ветке
`claude/seo-texts-enrichment-prompt-449lyw`.
Ссылки в формате `файл:строка`. Всё, чего я не проверил, вынесено в последний раздел.

> **ПРАВКИ РЕВИЗИИ 2026-07-27** (второй проход, независимая перепроверка). Исправленные
> места помечены ниже как «**[исправлено]**». Перепроверка делалась на HEAD `2e67f10`
> (первая редакция писалась на `b2f9d5c` — это предок текущего HEAD, ветка с тех пор
> ушла на 9 коммитов вперёд). Крупнейшие правки: §6.2 (модули на самом деле
> установлены), §6.1 (`kb/manuf-raw/` — не выход `fetch_playwright.py`),
> §6.4 (вывод про поле `city` был неверным), §3.1 (число типов категорий и место
> дублирования `categorize`).

**Все относительные пути ниже — от `/home/user/avto/seo-texts/`.**
Многие скрипты используют относительные пути к данным, поэтому запускать их надо
именно из этого каталога (кто именно — таблица в §2.6).

---

## 1. Что это и зачем

Тексты для 759 страниц каталога нельзя было писать «из головы»: в них должны стоять
только настоящие цифры (сколько товаров в разделе, какие цены, какие модели, какая
мощность в кВт). Эта область — способ добыть такие цифры и потом ими же проверить
готовые тексты.

Четыре независимых источника сырья:

| Источник | Чем берётся | Куда кладётся |
|---|---|---|
| Живые страницы каталога prokompressor.ru | HTTP GET + regex (Aspro Max рендерит на сервере, JS не нужен) | `page-data/*.json` |
| Страницы кейсов (`/projects/...`) | то же | `projects-index.json` |
| Выгрузка Битрикса (CSV, 4.2 ГБ) | потоковое чтение csv | `diz-brands-aggregates*.json`, `props-fill-table.csv`; а также `bitrix-power.json` и `brand-power-*.json` — **но их сборщика в репозитории нет**, см. §6.5 |
| База обзвона `obzvon_all` (CSV, 679 МБ) | стрим через stdin | `segments-base.json`, `client-revenue-index.json`, `region-index.json` |

Плюс отдельная ветка: **обратные сверки** — уже сгенерированные тексты (`gen/result-*.json`)
проверяются против собранной фактуры (`scan_ranges.py`, `scan_ranges2.py`) и
дополняются перелинковкой (`link_projects.py`, `fix_enger_link.py`), а факт публикации
контролируется краулом (`check_placement.py`).

Важное общее свойство: **почти всё здесь детерминированно, без LLM**. Провайдерский API
(и, значит, квоту) жгут ровно 5 скриптов из 29 — список в §2.5.
**[исправлено]** Уточнение: «29» — это .py-файлы ядра области, без каталога `frog/`.
Если считать `frog/` (а он в §4.4 назван «формально в периметре»), то API-скриптов
шесть: шестой — `frog/title_review.py` (импортирует `gen_provider`).

Ещё одно свойство: это **one-shot ETL**. Ни один скрипт области не вызывается из другого
кода — все запускаются руками. Проверено сплошным grep по репозиторию: единственные
межскриптовые импорты внутри области — `scan_ranges2.py:6` (`from scan_ranges import claims`)
и `fix_categories.py:11` (читает текст промпта прямо из исходника `enrich_categories.py`).

---

## 2. Точки входа и как запустить

### 2.1. Краул каталога prokompressor.ru

```bash
cd /home/user/avto/seo-texts

# 1. основной краул категорий (нужен inventory/text-audit.csv, см. §4.5)
python3 crawl_pages.py            # всё, что помечено NO_TEXT / DUP* -> 763 URL
python3 crawl_pages.py --limit 20 # тестовый прогон на 20 страницах

# 2. до-краул карточек товаров для ItemList/Product-разметки
python3 crawl_products.py         # список страниц берёт из gen/payload-*.json
```

* `crawl_pages.py` **резюмируемый**: если `page-data/<slug>.json` уже есть, страница
  пропускается (`crawl_pages.py:119-120`). Чтобы перекачать — удалить файл.
* `crawl_products.py` **не резюмируемый**: каждый запуск перекачивает все 759 страниц
  и полностью перезаписывает `products-index.json` (`crawl_products.py:49`).
* Оба — 8 потоков (`crawl_pages.py:153`, `crawl_products.py:41`), User-Agent десктопного
  Chrome, таймаут 30 с.

### 2.2. Краул кейсов (`/projects/…`)

Цепочка из четырёх шагов, порядок важен:

```bash
cd /home/user/avto/seo-texts
python3 crawl_projects.py        # projects-urls.txt -> projects-index.json  (1018 записей)
python3 fix_cities.py            # ПЕРЕЗАПИСЫВАЕТ projects-index.json на месте
python3 fetch_city_prop.py       # projects-index.json -> city-prop.json
python3 crawl_project_photos.py  # used-projects.txt -> projects-photos.json (55 из 56)
```

`crawl_projects.py:6` берёт из `projects-urls.txt` только строки глубины 7
(`count('/') == 6`) — это детальные страницы кейсов; строки-разделы отбрасываются
(1035 строк в файле → 1018 детальных).

`fix_cities.py` делает две вещи: пересчитывает `city_guess` более строгим регулярным
выражением (`fix_cities.py:6,44-48`) и **докачивает** записи, помеченные `error`
(`fix_cities.py:51-56`). Он пишет в тот же `projects-index.json` — бэкапа не делает.

### 2.3. Тематические краулы (исторические, под конкретные волны генерации)

```bash
cd /home/user/avto/seo-texts
python3 crawl_diz_brands.py   # 21 дизельный бренд -> diz-brands-pages.json
python3 crawl_diz_full.py     # + пагинация -> diz-brands-models.json
python3 crawl_elektro.py      # elektricheskie-batch1.csv (124 URL) -> elektro-pages.json
```

Список дизельных слагов зашит в `crawl_diz_brands.py:7-9`, базовый URL — `:6`.
`crawl_diz_full.py:9-10` разворачивает `max_pagen` каждой страницы в список URL
с `?PAGEN_1=N` и собирает **все** имена товаров, а не только первые 20.

### 2.4. Разбор тяжёлых выгрузок

**Выгрузка Битрикса** (`bitrix/export_file_2ov3pw9ju90trsle.csv`, 4.2 ГБ в распакованном
виде — размер проверен по tar-листингу дропа):

```bash
cd /home/user/avto/seo-texts
bash server/drop_client.sh down bitrix-export-full.tar.gz
tar xzf bitrix-export-full.tar.gz -C bitrix/     # ожидаемый путь: bitrix/export_file_2ov3pw9ju90trsle.csv

python3 analyze_export.py     # -> props-fill-table.csv + export-stats.json
python3 diz_aggregates.py     # -> diz-brands-aggregates.json   (матч по названию/производителю)
python3 diz_aggregates2.py    # -> diz-brands-aggregates2.json  (матч по diz-brands-models.json)
```

**База обзвона** (`obzvon_all_2026-07-16.csv`, 679 МБ). Все три скрипта читают **stdin**,
чтобы не класть файл на диск целиком:

```bash
cd /home/user/avto/seo-texts
curl -s -H "X-Drop-Token: $DROP_TOKEN" "$DROP_URL/obzvon_all_2026-07-16.csv" \
  | python3 extract_segments.py     # -> segments-base.json
curl -s ... | python3 extract_priority.py   # -> priority-analysis.json
curl -s ... | python3 match_clients.py      # -> client-revenue-index.json
```

(`match_clients.py` формально вне списка этой области, но без него не соберутся
`region_aggregate.py` и `segment_master.py` — он их обязательный вход.)

Разделитель везде `;`, BOM с первого заголовка снимается (`extract_segments.py:13`),
лимит поля поднят до 10 МБ (`:10`). Колонки ищутся **по имени**, отсутствующая колонка
даёт индекс `-1` (`extract_segments.py:14`, `extract_priority.py:13`).

**[исправлено]** Дальше про `-1` было сказано неверно («молча пропускается»). На самом деле
поведение разное:

* `extract_priority.py` защищён — все обращения обёрнуты в `if I_X >= 0`
  (`extract_priority.py:58-62`), при пропавшей колонке будет честный ноль,
  а сам факт отражён в выходном поле `columns_present` (`:74-75`);
* `extract_segments.py` защиты **не имеет**: `row[I_REG]` при `I_REG == -1` — это
  `row[-1]`, то есть **последняя колонка строки**. Пропавшая колонка даст не пустую,
  а чужую статистику, молча и правдоподобно. Это грабля хуже, чем описано в §5.11.

Сводки поверх базы (уже без stdin, читают локальные json):

```bash
python3 region_aggregate.py   # projects-index + client-revenue-index -> region-index.json
python3 segment_master.py     # + segments-base.json -> segment-master.json
```

Оба проверены запуском 2026-07-27 в песочнице: `region_aggregate.py` даёт 80 регионов,
767/1018 кейсов с определённым регионом (75%); `segment_master.py` — 17+ отраслей,
топ «Производство (общее)» 418 кейсов.

### 2.5. Скрипты, которые ходят в провайдерский API (жгут квоту)

Ровно пять (по ядру области; про `frog/title_review.py` — см. §1). Все требуют
`PROVIDER_API_KEY` и модуль `anthropic` — **[исправлено]** модуль в этой среде
установлен, см. переписанный §6.2:

| Команда | Вход | Выход |
|---|---|---|
| `python3 extract_brand_pages.py` | `kb/brand-pages-raw/*.html` (60 файлов, `:8`) | `kb/brand-pages-facts.json` (`:46`) |
| `python3 enrich_categories.py` | 10 категорий зашиты в `:7-18` | `kb/category-<len%100>-<slug>.md` (`:44-46`) |
| `python3 fix_categories.py` | 3 категории в `:6-10`, промпт вытаскивается из исходника `enrich_categories.py` (`:11`) | `kb/category-<slug>.md` (`:18`) |
| `python3 clean_keywords.py` | XLSX вебмастера (`:10`), батчи по 150 (`:40`) | `inventory/keywords-clean.json` (`:63`) |
| `python3 classify_search_rows.py` | `inventory/search-problems.csv` + `inventory/search-results.jsonl` (`:8-9`), батчи по 30 (`:36`) | `inventory/rows-classified.json` (`:46`) |

`build_category_ref.py` API **не** трогает — это чистая чистилка markdown-досье
(`:28-43`), выход `kb/category-ref/<type>.md` + `kb/category-ref/index.json` (`:54-60`).
Подробно про досье категорий — в `docs/02-baza-znaniy.md` §2.

### 2.6. Сверки и постфиксы по уже сгенерированным текстам

```bash
cd /home/user/avto/seo-texts
python3 scan_ranges.py        # -> range-mismatch.md
python3 scan_ranges2.py       # -> range-mismatch-final.md + range-fix-queue.txt
python3 link_projects.py --dry   # предпросмотр; без --dry ПИШЕТ в gen/result-*.json
python3 link_projects.py
python3 fix_enger_link.py     # ПИШЕТ в gen/result-*.json, dry-режима нет
python3 check_placement.py    # краулит 759 живых URL -> placement-missing.txt/.json
```

Прогон 2026-07-27 в песочнице (на симлинках, репозиторий не тронут). **Ревизия
повторила все три расчёта репликой логики, без единой записи в репозиторий — цифры
сошлись точно:**

* `scan_ranges.py` → 248 несовпадений на 206 страницах (в закоммиченном
  `range-mismatch.md` записано 246 — тексты с тех пор правились);
* `scan_ranges2.py` → «проверено 116 брендовых страниц, расхождения на 12 страницах,
  12 claim-ов» — совпадает с закоммиченным `range-mismatch-final.md` и с 12 строками
  `range-fix-queue.txt`;
* `link_projects.py --dry` → «страниц изменено: 0» — правки уже применены, скрипт идемпотентен.

Очередь `range-fix-queue.txt` дальше потребляет `patch_ranges.py` (вне этой области):
он подставляет истинные границы из `payload.power_range_catalog`.

### 2.7. Скрипты, чей вход в этой среде недоступен

| Команда | Почему сейчас не запустится |
|---|---|
| `python3 fetch_playwright.py` | **синтаксическая ошибка**, см. §6.1 |
| `python3 analyze_markup.py <enrich_out.json>` | нужен выход прогона `server/enrich_contacts.py` с полем `contact_src` (`enrich_contacts.py:1888`); это область рассыльщика, не краулинга сайта |
| `python3 clean_keywords.py` | XLSX лежал в `/root/.claude/uploads/bcce55cd-…/` — каталога нет, на дропе файла с таким именем нет |
| `python3 analyze_export.py` | помимо CSV нужен XML-справочник свойств из того же удалённого каталога uploads (`analyze_export.py:7,10`) |
| `bash fetch_brand_pages.sh`, `fetch_categories.sh`, `check_domains.sh`, `chain_tech.sh`, `bitrix_noncomp.sh` | первой строкой `cd` в чужой скретчпад `/tmp/claude-0/-home-user-avto/bcce55cd-…/scratchpad`, которого нет |

---

## 3. Как устроено внутри

### 3.1. `crawl_pages.py` — сердце области (172 строки)

Что делает: берёт рабочий список URL, качает HTML, вытаскивает regex'ами компактный
слепок и кладёт по одному JSON на страницу. **Сырой HTML не хранится сознательно**
(комментарий `:3`: 664 КБ × 763 не влезает).

Рабочий список (`load_worklist`, `:138-142`): `inventory/text-audit.csv` (разделитель `;`),
берутся строки со `status == 'NO_TEXT'` или `status.startswith('DUP')`.
**[дополнено ревизией]** CSV прочитан: 787 строк данных, статусы `NO_TEXT` 368,
`DUP_x*` 395, `UNIQUE` 24. Рабочий список — **763 URL**, и их слаги 1:1 совпадают
с 763 файлами в `page-data/`.

Слепок страницы (`parse`, `:55-113`) — поля:

| Поле | Как берётся |
|---|---|
| `h1`, `title_current`, `meta_current` | regex по `<h1>`, `<title>`, `meta name="description"` (`:58-61`) |
| `count` | сперва «N товаров» из тела (`:65-68`) — надёжнее, чем meta; если нет, нижняя оценка `max(PAGEN_N) * 20` (`:70-71`); если и этого нет — число показанных моделей (`:102-103`) |
| `price_min` / `price_max` / `prices_sample` | `data-value` на price-дивах, отфильтровано диапазоном 500…100 000 000 (`:76-77`); `price_min` предпочитает «от X ₽» из meta (`:72-73`) |
| `sample_models` | `itemprop="name"`, минус хлебные крошки и h1, только строки с цифрой, максимум 20 (`:80-84`) |
| `brand_facets` | ссылки вида `<текущий URL>/<slug>/` (`:88`) **[уточнено: regex идёт по всему HTML, а не только по сайдбару — в выборку попадёт любая такая ссылка на странице]** |
| `page_brand` | хвост URL, если он не входит в список 27 «категорийных» баз `cat_bases` (`:92-100`) **[исправлено: 27, не 26 — пересчитано разбором кортежа]**; плюс три доп. условия в том же выражении: слаг из `^[a-z0-9][a-z0-9_-]*$`, без `-bar`, `-l-min` и `kompressory-` |
| `category` | функция `categorize` (`:18-44`) — **14** возможных значений **[исправлено: было «11 типов»; 11 — это число категорий, реально встретившихся в `page-data/` (§4.1); сама функция умеет вернуть ещё `n2_gen`, `o2_gen` и `other`]** |
| `status` | `OK`, если есть h1 и (count или models); иначе `PARSE_FAIL` (`:104,112`) |

`categorize` (`:18-44`) устроена по правилу «секция важнее подстроки»: смотрится второй
сегмент пути (`vozdushnye-kompressory`, `osushiteli`, `resivery`, `podgotovka-vozdukha`,
`zapasnye-chasti-i-raskhodniki`, `raskhodomery-i-datchiki`, `generatsiya-gazov`), внутри —
третий. Иначе URL вроде `kompressory-s-resiverom` ловился бы как `receiver`.
**Эта функция продублирована** — **[исправлено]** ровно в одном месте, в
`build_payloads.py:55` (там же, в докстринге `:56-57`, комментарий про этот баг).
В `build_compressor_payloads.py` функции `categorize` **нет** — первая редакция
утверждала обратное (проверено `grep -n "def categorize"` по всему репо: единственные
два определения — `crawl_pages.py:18` и `build_payloads.py:55`). Копий две, не три,
но при правке всё равно надо менять обе.

`slugify` (`:50-52`): последние три сегмента пути через `__`. Отсюда имена файлов вида
`bezmaslyanye_1__porshnevye__atlas-copco.json`.

Сетевой слой (`fetch_one`, `:116-135`): 3 попытки, таймаут 30 с, пауза `1.5 × номер попытки`,
успех = HTTP 200 **и** длина тела > 2000 (`:125`). Провал пишет запись со `status: FETCH_FAIL`
и текстом ошибки — то есть неудача тоже кэшируется, повтор потребует удаления файла.

`_index.json` (`:161-165`) пересобирается из **всех** файлов каталога, а не только из
скачанных в этом прогоне.

### 3.2. `crawl_products.py` — карточки товаров

Пары «имя ↔ ссылка» берутся одним жёстким regex по разметке Aspro
(`href="…" itemprop="url"` … `<span itemprop="name">`, `:14`), до 24 карточек на страницу
(`:27`). Цены прикрепляются **только если число найденных цен ровно равно числу карточек**
(`:29`) — иначе позиционное сопоставление ненадёжно. Отсюда фактический результат:
759 страниц с карточками, но лишь **7** с ценами (`crawl-products.log`, проверено
пересчётом по `products-index.json`). Медиана — 20 карточек на страницу.

### 3.3. Кейсы: `crawl_projects.py` → `fix_cities.py` → `fetch_city_prop.py`

`crawl_projects.py` качает страницу через `subprocess curl` (`:13`), находит блок
`class="properties"` (`:25`) и вытаскивает из него 6 полей по подписям:
`date`, `sphere`, `brand`, `equipment`, `client`, `service` (`:33-38`).
Нарратив — текст между «Услуга» и «|Товары|», до 2000 символов (`:41-47`).
Город угадывается регуляркой «г. X / в городе X» со стоп-листом (`:9,48-51`).

`fetch_city_prop.py` решает ту же задачу иначе — ищет **свойство** «Город» в таблице
характеристик (`:17-19`).

**[исправлено]** Цифры по `city-prop.json` были неверны («532 непустых из 1017»).
Фактически: в файле **1015 ключей** (URL) и **530 непустых** значений. Расхождение с
логом `city-prop.log` («…/1017») объясняется тем, что в `projects-index.json` есть
**две пары дублирующихся URL** (1018 записей → 1016 уникальных URL, из них одна с
`error` не попадает в обход). Поэтому в проекции на строки `projects-index.json`
непустое значение из `city-prop.json` получают **532 строки** — это тоже верное число,
но относится к строкам, а не к содержимому файла.

Итоговое поле `city` в `projects-index.json` заполнено у **753** записей — это больше,
чем даёт любой из двух скриптов по отдельности, и больше, чем `city_guess` (297).
**Скрипта, который сливает эти источники в поле `city`, в репозитории нет** — проверено
повторно: `city-prop.json` нигде не читается; присваивание вида `[...'city'...] =`
встречается только в `server/enrich_contacts.py:4290` и `sender/ai_quota.py:739`
(другие области, другая сущность). Поиск повторён по всем 6 веткам `origin`.

**[исправлено]** Но вывод «поле `city` собрано не из `city-prop.json`» (он был в §6.4)
данными **опровергается**. Прямое сравнение: из 1017 строк, у которых есть ключ в
`city-prop.json`, непустое значение там у 532 — и во **всех 532** случаях `city`
совпадает с ним посимвольно, расхождений **ноль**. Обратных случаев (в `city-prop.json`
значение есть, а `city` пустой или другой) — тоже ноль. То есть `city-prop.json`
почти наверняка **был** одним из источников поля `city`; остальные 221 значения
добраны откуда-то ещё.

Судя по `wf-args.json` (26 путей на `city-batches/batch-NN.json` + массив `verify`),
эти 221 доставали LLM-прогоном по батчам, запущенным ad-hoc через воркфлоу.
Каталог `city-batches/` — это его вход. **[исправлено]** Это не «26 файлов по 40 кейсов»:
25 файлов по 40 записей + последний на 17, итого ровно **1017** записей — то есть все
записи `projects-index.json`, кроме одной с `error`. Арифметика «26 × 40 ≈ 1040 ≥ 1018»
из первой редакции неверна.

`crawl_project_photos.py` — самый маленький краулер: берёт `og:image` со страницы кейса,
отбрасывает `.svg`, при неудаче берёт первую картинку из `/upload/medialibrary|iblock/`
(`:13-18`). Работает только по 56 URL из `used-projects.txt` (проекты, реально попавшие
в payload'ы), результат — 55 фото.

### 3.4. Битрикс: `analyze_export.py`, `diz_aggregates.py`, `diz_aggregates2.py`

Ключевая особенность выгрузки: **Битрикс дублирует строки на мультизначения свойств**,
поэтому «товар» — это группа строк с одинаковым `row[2]` (ID). `analyze_export.py:47-62`
буферизует текущий товар в список множеств и «сбрасывает» при смене ID; тот же приём —
в `diz_aggregates.py:35`. Реальные числа последнего прогона (`analyze.log`):
600 738 строк → 27 477 товаров, из них 20 054 компрессора.

`analyze_export.py` дополнительно расшифровывает имена колонок `IP_PROPnnn` через
XML-справочник свойств (`:10-13`) и системные имена `IE_*`/`IC_GROUP*` (`:15-19`);
выход — таблица заполненности `props-fill-table.csv` (8 колонок, `:76`).

Карта нужных свойств зашита в `diz_aggregates.py:20-23`:
`IP_PROP22562` мощность, `22571` производительность, `22573` давление, `23168` винтовой блок,
`23000`/`23013` марка/модель двигателя, `22677` топливный бак, `22662`/`23004` ресивер,
`22576` серия, `22553` производитель, `23191` страна, `22566` мобильность, `23188` гарантия,
`22580` тип. `analyze_export.py` — единственный способ понять, что означает любой другой
`IP_PROPnnn`.

Разница двух агрегаторов: `diz_aggregates.py` матчит товары по **вхождению названия бренда**
(словарь `:6-14`) плюс фильтр «дизель» в названии или типе (`:31`); `diz_aggregates2.py`
матчит по **точному имени товара** из `diz-brands-models.json` (`:6-10,27`), то есть
опирается на реальный состав тега на сайте, и дополнительно выкидывает бензиновые (`:38`).
Второй точнее; в отчёт он кладёт и расхождение «в теге / сматчено в выгрузке» (`:53-56`).

### 3.5. База обзвона: `extract_segments.py`, `extract_priority.py` + сводки

`extract_segments.py` — чистые счётчики по 5 осям: направление («База»), регион,
раздел ОКВЭД (первые 2 цифры, `:52`), категория оборудования (одна основная + все через `|`,
`:54-63`), тир по выручке (7 тиров, `:33-41`). Плюс кроссы регион×направление и
категория×направление. Отчёт в stderr, машинный вывод в `segments-base.json`.

`extract_priority.py` — распределения трёх скоринговых колонок базы («Итоговый балл
приоритета», «Макс. балл по связке», «Приоритет × выручка / 10000», `:22-24`) и рейтинг
категорий оборудования по доле высокого приоритета (порог: минимум 200 записей, `:88`).
Полезная деталь: скрипт первым делом печатает **все** заголовки CSV с индексами
(`:16-19`) — это самый дешёвый способ узнать реальную схему базы, не скачивая её целиком.

`region_aggregate.py` собирает «регион → сколько кейсов + топ-компании по выручке».
Регион берётся сначала из базы обзвона у сматченных клиентов (`:77-78`), иначе — из
зашитого словаря «город → регион» на ~150 городов (`:12-49`). Банкроты из топ-листа
исключаются (`:86`).

`segment_master.py` — то же, но осью выступает **категория кейса** (сегмент URL
`/projects/<category>/`), с русскими названиями из `:12-22`.

Оба потребителя — тексты писем, а не SEO: подробности в `email-assistant/SEGMENTATION.md`.

### 3.6. Обратные сверки диапазонов

`scan_ranges.py` ищет в готовом тексте фразы «от X до Y кВт» / «диапазон X-Y кВт»
(три шаблона, `:16-20`) и сверяет их с реальными мощностями **этой же страницы**.
Мощности берутся в три приёма (`page_powers`, `:24-39`): по URL товара из `bitrix-power.json`,
по точному имени товара оттуда же, и в последнюю очередь — «N кВт» прямо в названии.
Флаг ставится при потолке выше +30 %, ниже −30 % или **поле** («пол», нижняя граница)
ниже −30 % (`:76-79`).

`scan_ranges2.py` — тот же поиск заявок (импортирует `claims` из первого, `:6`), но
эталон другой: **полный состав каталога** по паре «бренд × подтип» из `brand-power-sub.json`.
Подтип определяется по слагу и h1 (`subtype`, `:16-22`: porshn / spiral / dizel / vint / all).
Сверяются только страницы с `category == 'compressor'` (`:33`) и только если в эталоне
не меньше 3 позиций (`:46`). Пороги мягче: +20 % / −40 % (`:52-57`).

Отсюда и разница чисел: 248 придирок у первого против 12 у второго — второй считается
финальным, его очередь и уходит в `patch_ranges.py`.

### 3.7. Постфиксы перелинковки

`link_projects.py` оборачивает первое упоминание клиента ссылкой на его кейс.
Аккуратность реализована честно: сначала текст режется по существующим `<a>…</a>`
(`wrap_first`, `:28`), затем внутри каждого куска — по тегам (`:30`), и подстановка
делается только в текстовых узлах чётных индексов. Варианты написания клиента —
полное, без ООО/ИП/АО и в двух видах кавычек (`candidates`, `:12-23`).
Ссылка-карточка проекта (у неё `style="float:right"`) намеренно не считается за интекст-ссылку
(`:58-62`). Есть `--dry` (`:9`).

`fix_enger_link.py` делает то же для бренда Enger: если у payload есть `enger_category_url`,
а в тексте `Enger`/`Энгер` без ссылки — оборачивает первое видимое упоминание
(`WORD`, `:9`; защита «не внутри тега», `:32`). **Dry-режима нет — пишет сразу.**

Состояние на 2026-07-27 (посчитано репликой логики скрипта, без записи;
**ревизия пересчитала независимо — 645 / 487 / 89, сходится**):
из 645 страниц с `enger_category_url` ссылка уже стоит на 487, скрипт при запуске
изменил бы ещё **89**, а на оставшихся 69 слова «Enger»/«Энгер» в тексте просто нет.
То есть последний массовый прогон текстов через него не проходил.

`check_placement.py` — контроль публикации: обходит все URL из `gen/payload-*.json`
и ищет в живом HTML маркер `expert-byline` либо «Материал подготовил» (`:21`).
Закоммиченный `placement-missing.txt` — 123 строки (коммит `da4da47`, 2026-07-16,
«636/759 на месте»). В `seo-effect-v2.md:102-103` это уже описано как план
«дозалить 123 → re-run → 759/759» — то есть файл отражает состояние ДО дозаливки,
а не текущее.

---

## 4. Данные и где они лежат

### 4.1. `page-data/` — 764 файла (763 слепка + `_index.json`)

Один JSON на страницу; имя = `slugify(url)`. Сводка `_index.json` — массив тех же
записей. Текущий состав (посчитано):

* по статусу: `OK` 759, `PARSE_FAIL` 3, `FETCH_FAIL` 1;
* по категориям: compressor 546, receiver 37, ads_dryer 34, spare_parts 34, ref_dryer 31,
  air_prep 27, separator 27, filter 21, flowmeter 4, dryer_other 1, gas_other 1.

Неудачные четыре:

| slug | статус |
|---|---|
| `catalog__raskhodomery-i-datchiki__difmanometry` | PARSE_FAIL |
| `po-tipu__vintovye__odnostupenchatye` | PARSE_FAIL |
| `vintovye__peredvizhnye__dizelnye_1` | PARSE_FAIL |
| `prokompressor.ru__catalog__root` | FETCH_FAIL, `HTTP 404 len=216504` — URL `/catalog/root/` собран ошибочно |

Потребители: `build_payloads.py:15` и `build_compressor_payloads.py:15` — это вход
всей генерации.

### 4.2. `city-batches/` — 26 файлов, 1017 записей

**[исправлено]** Не «26 × 40»: 25 файлов по 40 записей + `batch-25.json` на 17,
итого 1017 — все записи `projects-index.json`, кроме одной с `error` (проверено
пересчётом).

Списки `{url, client, narrative}` — нарезка `projects-index.json` для LLM-извлечения
города. Скрипта-нарезчика в репозитории нет; пути на эти батчи сохранились только в
`wf-args.json` (и указывают в удалённый скретчпад). Каталог — исторический вход, не выход.

### 4.3. `data/` — не краулерский, а «общий склад» соседних областей

| Файл | Что это | Кто читает |
|---|---|---|
| `base_settlements.json` (10 229 НП) | справочник «город → регион» из базы обзвона | `email-assistant/build_kb2.py:37-40` |
| `sweep_queries.json` (10 299 запросов) | каталог поисковых запросов для новостного sweep | `server/news_scan.py:122` — **скачивает его с дропа, а не отсюда** |
| `kb_ideas_merged.json` (146 идей) | выход `kb_ideas.py:99`, скопирован в репо | только человек |
| `meyer_kb_raw.json` (7 разделов) | выход `meyer_extract.py:105` | только человек / `sender-patches/meyer-gen/` |
| `confirm_screen_ideas.json` (5 разделов) | сырьё для `email-assistant/ENGINEER-TASKS-CONFIRM-SEND.md` | только человек |
| `okved_directions.json` (77 записей ОКВЭД → оборудование) | — | **вызывающих нет** (grep по всему репо) |
| `monotowns_1398r.json` (304 моногорода) | — | **вызывающих нет** (grep по всему репо) |

Ни один файл `data/` не читается скриптами этой области.

### 4.4. `frog/` — SEO-аналитика 17 дилерских сайтов (соседняя область)

Тоже не про краул prokompressor.ru, но каталог формально в периметре:

| Файл | Что |
|---|---|
| `urls-indexable-all.txt` (14 007 URL, 17 доменов — пересчитано) | выгрузка обхода (Screaming Frog) по всем сайтам группы |
| `acceptor_value.py` → `acceptor-value.json`, `acceptor-candidates.json` | коммерческое ранжирование страниц-акцепторов; B2B CTR-кривая `:23-30` **[исправлено: было `:22-29`]**, восстановление показов из кликов |
| `price_map.py` → `price-map.json` | медианный чек по сегментам из `pricelist-slim.xlsx` (313 листов) |
| `bitrix_prices.py` → `bitrix-prices.json` | медианы цен по категориям/брендам из выгрузки Битрикса |
| `gap_models.py` → `gap-models-by-sheet.json` | модели, которые есть у поставщиков, но нет на сайте |
| `title_review.py` → `title-review.json` | LLM-дебаты двух экспертов по плохим тайтлам (ходит в провайдерский API через `gen_provider`) |
| `DATA-VALUE-REPORT.md`, `DEVICE-BOT-FINDING.md`, `REVIEW-CONTEXT.md` | отчёты для человека |

**[исправлено]** Скриптов в `frog/` **пять** (`acceptor_value.py`, `price_map.py`,
`bitrix_prices.py`, `gap_models.py`, `title_review.py`), а не четыре. Три из пяти читают
Битрикс/прайс **по абсолютным путям в чужой скретчпад** (`bitrix_prices.py:8`,
`gap_models.py:28`) или в удалённый каталог uploads (`acceptor_value.py:18` —
**[исправлено: было `:16`]**) — в текущей среде не запускаются без правки путей.
Четвёртый, `price_map.py:11`, ходит по относительному пути `../pricelist-slim.xlsx`,
и этого файла в репо нет (он в корневом `.gitignore:11`, лежит на дропе, 5 345 301 б).

### 4.5. Чего в репозитории нет, но оно есть на дропе

Каталоги `inventory/` и `bitrix/` отсутствуют и на диске, и во всех ветках git
(перепроверено `git ls-tree -r` по **6** веткам `origin` — **[исправлено: веток шесть,
а не семь; `git ls-remote --heads origin` возвращает 6 строк]**).

**[исправлено]** Про `.gitignore` было сказано неверно. Строка `seo-texts/bitrix/`
действительно есть в `seo-texts/.gitignore:3`, но **правило не работает**: шаблон с
ведущим путём резолвится относительно каталога, где лежит сам `.gitignore`, то есть
в `seo-texts/seo-texts/bitrix/`. Проверка: `git check-ignore -v seo-texts/bitrix/x.csv`
не даёт совпадения (rc=1). Каталог не игнорируется — просто его никогда не коммитили.

Оба лежат на файловом обменнике — проверено листингом содержимого архивов прямо из потока
(перепроверено повторно 2026-07-27, цифры совпали):

```bash
cd /home/user/avto/seo-texts
bash server/drop_client.sh down inventory-crawl.tar.gz   # 61 564 575 б, 2026-07-16
tar xzf inventory-crawl.tar.gz                            # даст каталог inventory/
bash server/drop_client.sh down bitrix-export-full.tar.gz # 37 582 922 б, 2026-07-16
mkdir -p bitrix && tar xzf bitrix-export-full.tar.gz -C bitrix/
```

`inventory-crawl.tar.gz` — 826 записей, из них 788 файлов в `inventory/pages/`
(это выход `fetch_categories.sh`) плюс именно те файлы, которых не хватает скриптам:
`inventory/text-audit.csv` (вход `crawl_pages.py:139`), `inventory/categories-registry.csv`,
`inventory/keywords-clean.json`, `inventory/rows-classified.json`,
`inventory/search-problems.csv`, `inventory/search-results.jsonl`,
`inventory/fetch-errors.log`, 20+ файлов `sitemap-smart-*.xml`,
отчёты `OTCHET-poisk.md` / `OTCHET-poisk-v2.md`.

`bitrix-export-full.tar.gz` содержит ровно один файл:
`export_file_2ov3pw9ju90trsle.csv`, 4 214 568 961 байт (4.2 ГБ). Внутри архива он лежит
**в корне**, без префикса `bitrix/` — поэтому распаковывать обязательно с `-C bitrix/`,
как в §2.4 (перепроверено `tar tzvf` из потока).

Прочее сырьё на дропе, релевантное области: `obzvon_all_2026-07-16.csv` (679 315 808 б),
`pricelist-slim.xlsx` (5 345 301 б), `inventory-search-v3.tar.gz` (151 597 б).
**[исправлено]** «Всего на дропе 824 файла» — число живое: на 2026-07-27 их **841**.
Опираться на конкретное число не стоит, дроп пополняется.

### 4.6. Локальные артефакты области (всё это в git и на месте)

| Файл | Размер | Кто пишет | Кто читает |
|---|---|---|---|
| `page-data/*.json` | 764 файла | `crawl_pages.py` | `build_payloads.py`, `build_compressor_payloads.py` |
| `products-index.json` | 1.9 МБ, 759 страниц | `crawl_products.py` | `scan_ranges.py:8`, `build_schema.py` (ItemList) |
| `projects-index.json` | 2.4 МБ, 1018 записей (1016 уникальных URL, 1 с `error`) | `crawl_projects.py:65`, перезаписывает `fix_cities.py:58` | `match_clients.py:28` **[исправлено: было `:29`]**, `region_aggregate.py:65`, `segment_master.py:8`, `build_compressor_payloads.py:179` |
| `projects-photos.json` | 55 записей | `crawl_project_photos.py:27` | `build_compressor_payloads.py:167` |
| `city-prop.json` | **[исправлено]** 1015 ключей, 530 непустых (в проекции на строки `projects-index.json` — 532) | `fetch_city_prop.py:32` | программно — **никто**, но по данным поле `city` строилось в т.ч. из него (см. §3.3) |
| `diz-brands-pages.json` | 21 бренд | `crawl_diz_brands.py:53` | `crawl_diz_full.py:6`, `qa_gate.py:5` |
| `diz-brands-models.json` | 21 бренд | `crawl_diz_full.py:27` | `diz_aggregates2.py:6` |
| `diz-brands-aggregates.json` / `…2.json` | | `diz_aggregates*.py` | **никто программно** (шли в промпты руками) |
| `elektro-pages.json` | 124 страницы | `crawl_elektro.py:70` | **никто** — билдеры читают `elektro-pages-data.csv` (`build_el_payloads.py:6`), а конвертера json→csv в репо нет |
| `segments-base.json` | | `extract_segments.py:84` | `segment_master.py:10` |
| `priority-analysis.json` | | `extract_priority.py:93` | только человек (`email-assistant/SEGMENTATION.md:152`) |
| `client-revenue-index.json` | 302 КБ | `match_clients.py:106` | `region_aggregate.py:66`, `segment_master.py:9` |
| `region-index.json` / `segment-master.json` | | `region_aggregate.py:103` / `segment_master.py:50` | шаблоны писем (`email-assistant/SCENARIO-*.md`) |
| `range-mismatch.md` / `range-mismatch-final.md` / `range-fix-queue.txt` | 246 / 12 / 12 | `scan_ranges*.py` | `patch_ranges.py` берёт очередь |
| `placement-missing.txt` / `.json` | 123 строки | `check_placement.py:38-42` | человек |
| `props-fill-table.csv` / `export-stats.json` | | `analyze_export.py:74,78` | человек |
| `link-projects-report.md` | | `link_projects.py:75` | человек |
| `bitrix-power.json` | 2.9 МБ, 41 729 ключей | **производителя в репо нет** | `scan_ranges.py:10` |
| `brand-power-sub.json` / `brand-power-full.json` | 63 / 65 брендов | **производителя в репо нет** | `scan_ranges2.py:9` |

Логи прошлых прогонов (можно читать как «что реально запускалось»):
`crawl.log`, `crawl-products.log`, `city-prop.log`, `elektro-crawl.log`, `analyze.log`.

---

## 5. Ограничения и грабли

1. **Относительные пути.** Часть скриптов строит пути от `__file__`
   (`crawl_pages.py:12`, `crawl_products.py:8`, `crawl_project_photos.py:6`,
   `scan_ranges*.py`, `extract_*.py`, `region_aggregate.py`, `segment_master.py`,
   `build_category_ref.py`, `link_projects.py`, `fix_enger_link.py`), а часть —
   от текущего каталога (`crawl_projects.py:6`, `crawl_diz_*.py`, `crawl_elektro.py:8`,
   `fetch_city_prop.py:6`, `fix_cities.py:4`, `diz_aggregates*.py:16/12`,
   `analyze_export.py:26`, `check_placement.py:7`, `clean_keywords.py:63`,
   `classify_search_rows.py:8`, `extract_brand_pages.py:8`, `enrich_categories.py:46`,
   `fix_categories.py:11`). **Запускайте всё из `seo-texts/`** — иначе вторая группа
   молча создаст файлы не там или упадёт на открытии.

2. **Скрипты, пишущие поверх входа.** `fix_cities.py:58` перезаписывает
   `projects-index.json`; `fix_enger_link.py:36` и `link_projects.py:74` пишут прямо
   в `gen/result-*.json`. Ни один не делает бэкап. Бэкап генерации — отдельный каталог
   `gen-orig/` (см. `docs/01-generaciya-tekstov.md`).

3. **`fix_enger_link.py` не имеет `--dry`** — в отличие от `link_projects.py` и
   `patch_ranges.py`. Перед запуском стоит скопировать `gen/` или посчитать эффект
   репликой логики (см. §3.7).

4. **Парсинг завязан на разметку Aspro Max.** Все ключевые regex'ы (`itemprop="url"` +
   `<span itemprop="name">`, `class="price…" data-value=`, `PAGEN_1=`,
   `group_description_block bottom`, `class="properties"`) — это конкретная тема сайта.
   После обновления шаблона сайта краулеры вернут пустые поля, а не ошибку:
   `crawl_products.py:22` при исключении просто отдаёт пустой список, `crawl_pages.py`
   поставит `PARSE_FAIL`. Тихая деградация вероятнее падения.

5. **Кэшируется и неудача.** `crawl_pages.py:133-135` сохраняет `FETCH_FAIL` в тот же
   файл, а `:119` пропускает всё, что уже есть. Повторить попытку можно только удалив
   файл слепка.

6. **`_index.json` — не снимок прогона**, а склейка всего каталога (`:161-165`).
   Если в `page-data/` остались файлы от старых экспериментов, они попадут в индекс.

7. **Цены товаров почти нигде не собрались** — 7 страниц из 759, из-за строгого условия
   `crawl_products.py:29`. Это осознанный выбор в пользу «лучше без цены, чем с чужой»;
   в JSON-LD цены и так намеренно не кладут.

8. **Оценки количества товаров бывают нижней границей.** `count` из пагинации
   (`crawl_pages.py:70-71`) — это `страниц × 20`, а `crawl_elektro.py:37` считает
   `min_products = (max_pagen - 1) * len(cards)`. Числа из этих полей нельзя писать
   в текст как точные.

9. **Стоп-листы городов неполные.** `crawl_projects.py:49` и `fix_cities.py:7` отсекают
   «Заказать», «Компания», «Недавно» и т.п., но регулярка ловит любое слово с большой
   буквы после «г.»/«в городе». Отсюда мусор вроде «Кирове» (виден в `wf-args.json`,
   массив `verify`) и общая ненадёжность `city_guess` (297 из 1018).

10. **Словарь «город → регион» ручной** (`region_aggregate.py:12-49`) — покрывает
    только топ-города кейсов; 251 кейс из 1018 остаётся в корзине
    «(регион не определён)» (проверено запуском).

11. **Колонки CSV ищутся по имени — но ломается это по-разному.** **[исправлено]**
    Первая редакция сваливала базу обзвона и Битрикс в одно правило («не даст ошибки —
    даст пустую статистику»); это неверно.
    * База обзвона, `extract_priority.py`: колонка не найдена → индекс `-1`, но все
      обращения защищены `if I_X >= 0` (`:58-62`), и факт отражён в выходном поле
      `columns_present` (`:74-75`). Действительно «пустая статистика», и она видна.
    * База обзвона, `extract_segments.py`: защиты **нет** (`:46-64`). При `-1`
      питоновский `row[-1]` вернёт **последнюю колонку строки**, и статистика будет
      не пустой, а неправильной — молча. Самый опасный случай в области.
    * Выгрузка Битрикса: там **будет ошибка**, а не тишина. `diz_aggregates.py:24`
      (`C = {k: ix[v] for k, v in COLS.items()}`) и `diz_aggregates2.py:20` упадут с
      `KeyError`, `analyze_export.py:56` (`header.index('IC_GROUP0')`) — с `ValueError`.

12. **`link_projects.py:56-62` содержит мёртвую ветку**: блок `if not url or …: pass`
    ничего не делает, и при `url is None` скрипт дошёл бы до подстановки `href="None"`.
    Практически безопасно: во всех 298 проектах, разложенных по 108 payload'ам,
    `url` заполнен (проверено).

13. **`crawl_pages.py:18-44` дублирует `categorize`** из `build_payloads.py:55-83`
    **[исправлено: строка 55, не 56; и третьей копии в `build_compressor_payloads.py`
    не существует — см. §3.1]**. Расхождение этих двух копий = расхождение категории
    в слепке и в payload'е.

14. **Нагрузка на боевой сайт.** `crawl_pages.py` и `crawl_products.py` — 8 потоков,
    `check_placement.py` — 6, паузы между запросами нет (в отличие от shell-скриптов,
    где стоит `sleep 0.4`). 759 страниц в 8 потоков — заметный всплеск для магазина.

---

## 6. Что сломано или устарело

### 6.1. `fetch_playwright.py` — не запускается, синтаксическая ошибка

Проверено: `python3 -m py_compile` падает на всех 29 файлах области ровно один раз —
`fetch_playwright.py: IndentationError: unexpected indent (line 19)`.

Причина видна глазами: блок `with sync_playwright() as p:` (`:13`) содержит только
`import os as _os` (`:14`), затем строки `:15-18` дедентятся к нулевому уровню,
а `:19` снова уходит с отступом. Похоже на неудачную автоправку, которой добавляли
поддержку прокси (`_proxy`, `_kw`). Кроме того, в `:16` захардкожен путь
`/opt/pw-browsers/chromium-1194/chrome-linux/chrome` — сам каталог в этой среде **есть**,
но модуль `playwright` не установлен.

Назначение скрипта: скачать 8 сайтов производителей, которые блокируют curl
(fiac, fini, kraftmann, ekomak, renner, comprag, ironmac, zammer — `:6-11`), в
`kb/manuf-raw/`.

**[исправлено]** Первая редакция писала: «каталог `kb/manuf-raw/` существует и содержит
20 файлов — значит, результат когда-то был получен». Это неверный вывод. В каталоге
лежат `airbox, airman, ariacom, berg, ceccato, coaire, comaro, cross_air, dali, enger,
hansmann, hori, kraftmachine, lupamat, master_blast, mmz, ozen, paramina, remeza,
tamsan` — **ни одного** из восьми целевых сайтов `fetch_playwright.py` там нет
(`kraftmachine` ≠ `kraftmann`). Эти 20 файлов кладут `check_domains.sh:11-16` и
`check_domains2.sh:3,15-21` — они качают домены из `kb/brand-pages-facts.json` обычным
curl. То есть **следов успешного прогона `fetch_playwright.py` нет вообще**.

**[исправлено]** Гипотеза «рабочая версия могла существовать до правки прокси»
(п. 4 §7 первой редакции) тоже проверена и **снята**: файл затрагивал ровно один коммит,
`3614fef`, и та версия **побайтово идентична** рабочему дереву и точно так же не
компилируется (`git show 3614fef:seo-texts/fetch_playwright.py | py_compile` →
тот же `IndentationError: line 19`). Рабочей версии в истории репозитория нет.

### 6.2. Из внешних модулей отсутствует только `playwright`

**[ИСПРАВЛЕНО — самая грубая ошибка первой редакции.]** Там было написано:
«в этой среде не установлены `anthropic`, `httpx`, `openpyxl`, `playwright`, проверено
импортом». Перепроверка 2026-07-27 показывает обратное:

| Модуль | Состояние |
|---|---|
| `anthropic` | установлен, 0.120.0 |
| `httpx` | установлен, 0.28.1 |
| `openpyxl` | установлен, 3.1.5 |
| `requests` | установлен, 2.33.1 |
| `playwright` | **нет** (`ModuleNotFoundError`) |

Следствия (тоже переписаны):

* `import gen_provider` и `import qa_text` проходят — значит, все 5 API-скриптов (§2.5)
  **не падают на импорте**. Их единственное препятствие — `PROVIDER_API_KEY` и
  решение сессии о допустимости вызовов шлюза (см. корневой `CLAUDE.md`), а у
  `clean_keywords.py` — ещё и отсутствующий XLSX (§2.7);
* `clean_keywords.py:6` и скрипты `frog/`, читающие xlsx, на `openpyxl` **не падают**;
  их блокируют пути к отсутствующим файлам, а не модуль;
* `fetch_playwright.py` — по-прежнему `playwright` нет (и отступы сломаны, §6.1);
  сам каталог браузеров `/opt/pw-browsers/chromium-1194/` при этом на месте.

`requests` и `curl` есть, поэтому вся детерминированная часть работает.

**Вывод для владельца:** утверждениям вида «модуля нет» из первой редакции доверять
нельзя; состав окружения проверяйте на месте, он между сессиями меняется.

### 6.3. Мёртвые ссылки на чужие каталоги

Ни `/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad`,
ни `/root/.claude/uploads/` в этой среде не существуют (перепроверено `ls`).
На эти пути завязаны: `analyze_export.py:7`, `clean_keywords.py:10`,
`frog/acceptor_value.py:18` **[исправлено: было `:16`]**, `frog/bitrix_prices.py:8`,
`frog/gap_models.py:28`, `wf-args.json`, и первой строкой — `fetch_brand_pages.sh`,
`fetch_categories.sh`, `check_domains.sh`, **`check_domains2.sh`**
**[исправлено: его в списке не было, а это именно он наполняет `kb/manuf-raw/`]**,
`chain_tech.sh`, `bitrix_noncomp.sh`.
Вне периметра этой области тот же путь есть ещё в `centrifugal_lenses.py:16` и
`guest-posts/rebuild_xlsx.py:9` — список выше исчерпывающий только по краулерам.

Файлы `keywords_all_20260101_20260714.xlsx`, `all_sites_page_20260616_20260715.xlsx`
и XML-справочник свойств `asd_props_export_655_*.xml` **на дропе под этими именами не лежат** —
перепроверено на свежем листинге 2026-07-27 (841 файл): совпадений по подстрокам
`keywords`, `all_sites`, `props_export` — 0, файлов с расширением `.xml` на дропе нет
вообще, `.xlsx` — 27 штук, и все они из другой линии работ (выгрузки по доменам
дилеров, `pricelist-slim.xlsx`, `core-new-contacts.xlsx`). Оговорка остаётся: искали
по именам, файл мог быть переименован.

### 6.4. Модули без вызывающих (мёртвые в смысле «никто не запускает автоматически»)

Строго говоря, автоматических вызывающих нет **ни у одного** скрипта области — это
ручной ETL. Но у части ещё и выход никем не читается:

* `fetch_city_prop.py` → `city-prop.json` — программных читателей в репозитории нет.
  **[исправлено]** Но вывод первой редакции («797 совпадений из 1018, т.е. поле `city`
  собрано не из этого файла») **неверен и по цифрам, и по существу**. Точные цифры:
  совпадений (включая обоюдно пустые) — **796 из 1017** строк, у которых есть ключ в
  `city-prop.json`; из них строк с непустым значением в `city-prop.json` — 532, и
  **все 532 совпадают с `city` посимвольно**, расхождений ноль; случаев «в
  `city-prop.json` есть, а в `city` нет» — ноль. Это как раз свидетельство, что
  `city-prop.json` **был** источником поля `city`, а оставшиеся 221 добраны отдельно
  (см. §3.3). Файл — не мусор, а половина фактуры;
* `crawl_elektro.py` → `elektro-pages.json` — не читается ничем; билдеры
  (`build_el_payloads.py:6`, `build_el_payloads_r2.py:7`) читают `elektro-pages-data.csv`,
  который в репо есть (106 КБ, 14 колонок), но скрипта, превращающего json в этот csv,
  в репозитории нет;
* `diz_aggregates.py`, `diz_aggregates2.py` → `diz-brands-aggregates*.json` — программных
  потребителей нет, агрегаты уходили в промпты руками;
* `extract_priority.py` → `priority-analysis.json` — только для чтения человеком;
* `analyze_export.py` → `props-fill-table.csv` — то же (но это единственная карта
  соответствия `IP_PROPnnn` → человекочитаемое имя свойства, ценна как справочник);
* `analyze_markup.py` — вообще из другой области (разметки контактов в
  `server/enrich_contacts.py`), к краулу сайта отношения не имеет;
* `data/okved_directions.json` (77 записей) и `data/monotowns_1398r.json` (304) —
  вызывающих нет. Перепроверено: имена этих файлов **не встречаются нигде** в репозитории
  ни в одной из 6 веток `origin` (даже в .md), кроме этого документа. Оговорка та же:
  потребитель может быть на сервере владельца.

### 6.5. Сироты: файлы без производителя

`bitrix-power.json` (41 729 ключей: и «имя товара → кВт», и «/catalog/…-url/ → кВт»),
`brand-power-sub.json` (63 бренда × подтип → `[min, max, n]`) и `brand-power-full.json`
(65 брендов) — критические входы `scan_ranges*.py`, но **скрипта, который их строит,
в репозитории нет**. Перепроверено `git grep` по всем 6 веткам `origin`: имена этих
файлов встречаются только в `scan_ranges.py:10`, `scan_ranges2.py:9` (чтение) и в
`SESSION-INDEX.md:16`. Последняя строка — важная зацепка: там `brand-power-full.json`
помечен **`[scratch]`**, то есть по журналу сессий он и его сборщик жили в эфемерном
скретчпаде сессии, а не в git. Если выгрузка обновится, пересобрать эталон будет нечем
без переписывания.

### 6.6. Устаревшие артефакты

* `placement-missing.txt/.json` (123 страницы) — снимок 2026-07-16 ДО дозаливки текстов;
  `seo-effect-v2.md:102` описывает дозаливку как план. Актуальное состояние даст только
  повторный `python3 check_placement.py`.
* `range-mismatch.md` записан с числом 246, сегодняшний прогон даёт 248 — тексты
  правились после генерации отчёта.
* `city-batches/` + `wf-args.json` — вход одноразового LLM-прогона, воспроизвести
  штатно нечем.

---

## 7. Что не проверено

Явно перечисляю всё, в чём не уверен. Пункты со звёздочкой — те, где скептику стоило
перепроверить в первую очередь. **Ревизия 2026-07-27 прошла по всем звёздочкам;
результат приписан к каждому пункту.**

1. **\* «Скрипта, собирающего поле `city` в `projects-index.json`, нет».** Я проверил
   grep по всему `/home/user/avto` (`city-prop` читается только своим писателем; строка
   `['city'] =` не встречается) и по веткам git — но искал по подстрокам. Код мог
   быть выполнен как inline-скрипт в чужой сессии или лежать на сервере владельца.
   Само поле в данных есть — 753 непустых значения.
   **[РЕВИЗИЯ: утверждение «скрипта нет» подтверждено** (поиск повторён по 6 веткам
   `origin`, присваивания `['city'] =` нашлись только в `server/enrich_contacts.py:4290`
   и `sender/ai_quota.py:739` — другие сущности). **Но сопутствующий вывод «поле `city`
   собрано не из `city-prop.json`» опровергнут: 532 из 532 непустых значений совпадают
   посимвольно. См. §3.3 и §6.4.]**

2. **\* «Производителя `bitrix-power.json` / `brand-power-*.json` в репо нет».**
   То же ограничение: искал grep'ом по именам файлов. Мог быть inline-код.
   **[РЕВИЗИЯ: подтверждено по всем 6 веткам `origin`. Дополнительная зацепка:
   `SESSION-INDEX.md:16` помечает `brand-power-full.json` как `[scratch]` — файл и его
   сборщик жили в эфемерном скретчпаде сессии. См. §6.5.]**

3. **\* «`elektro-pages.json` никто не читает».** Проверено grep'ом по репозиторию.
   Конвертация в `elektro-pages-data.csv` явно происходила — значит, код где-то был.
   **[РЕВИЗИЯ: подтверждено по 6 веткам. `elektro-pages-data.csv` — 125 строк
   (124 данных + шапка), 14 колонок; состав колонок один-в-один повторяет поля
   `elektro-pages.json`, так что конвертация точно была. Конвертера в git нет.]**

4. **\* «`fetch_playwright.py` сломан».** Проверено `py_compile` — ошибка синтаксиса
   реальна и воспроизводима. Но: рабочая версия могла существовать до правки прокси;
   git-историю конкретно этого файла я не поднимал.
   **[РЕВИЗИЯ: история поднята. Файл затрагивал ровно один коммит `3614fef`; та версия
   побайтово идентична рабочему дереву и так же не компилируется. Рабочей версии в
   истории нет. Плюс опровергнут вывод про `kb/manuf-raw/` — см. §6.1.]**

5. **\* Инвентарь дропа.** Утверждения «файла `keywords_all_*.xlsx` на дропе нет»
   основаны на поиске по **именам** в листинге. Файл мог быть переименован.
   **[РЕВИЗИЯ: листинг перезапрошен 2026-07-27 — уже 841 файл (не 824). Совпадений по
   `keywords`, `all_sites`, `props_export` по-прежнему ноль; файлов `.xml` на дропе нет
   вообще. Оговорка про переименование остаётся в силе.]**

6. Я **не запускал** ни один сетевой краулер (`crawl_*.py`, `check_placement.py`,
   `fetch_city_prop.py`) — на сервере владельца идёт боевое обогащение. Все утверждения
   про их поведение — из чтения кода и из старых логов прогонов.

7. Я **не запускал** ни один скрипт с провайдерским API. Про их работоспособность
   сужу только по коду и по наличию выходных файлов. **[Ревизия тоже не запускала —
   запрет действует. Но импорт `gen_provider`/`qa_text` проверен и проходит, см. §6.2.]**

8. Я **не распаковывал** `inventory-crawl.tar.gz` и `bitrix-export-full.tar.gz` —
   читал только tar-листинг из потока. Содержимое `inventory/text-audit.csv`
   (в частности, реальные значения колонки `status`, от которых зависит рабочий список
   `crawl_pages.py`) **не видел**. Число «759 страниц к сбору» взято из готовых
   артефактов, а не из этого CSV.
   **[РЕВИЗИЯ: CSV извлечён из потока и прочитан. Он на 787 строк данных; статусы:
   `NO_TEXT` 368, `DUP_x127` 127, `DUP_x122` 122, `DUP_x75` 75, `UNIQUE` 24, плюс
   мелкие `DUP_x3…x12` (71). Рабочий список `load_worklist` даёт **763 URL**, а не 759
   — 759 это число слепков со статусом `OK` (§4.1). Все 763 слага из рабочего списка
   один-в-один совпадают с 763 файлами `page-data/`, лишних и недостающих нет.
   Листинг `bitrix-export-full.tar.gz` тоже перепроверен: один файл в корне архива,
   4 214 568 961 б.]**

9. Схему базы обзвона (`obzvon_all_2026-07-16.csv`) я **не видел**. Имена колонок
   («База», «ИНН», «Регион», «ОсновнойОКВЭД», «Оборудование по основному ОКВЭД»,
   «Все категории оборудования», «Выручка, руб.», «Итоговый балл приоритета»,
   «Макс. балл по связке», «Приоритет × выручка / 10000») взяты из кода
   `extract_segments.py:15-19` и `extract_priority.py:21-27`. Существуют ли они
   в текущей версии базы — не проверял. **Не утверждаю, что какой-либо колонки нет.**

10. Утверждение про 4.2 ГБ CSV Битрикса — из поля размера в tar-заголовке. Сам файл
    не скачивал.

11. Актуальность разметки сайта (сохранились ли `itemprop`, `data-value`,
    `group_description_block bottom`) не проверял — к боевому сайту не ходил.

12. `analyze_markup.py` разбирал только по коду; формат `enrich_out.json` с полем
    `contact_src` подтверждён косвенно (`server/enrich_contacts.py:1888`), реальный
    файл не открывал.

13. Каталог `frog/` описан обзорно. Логику `acceptor_value.py` я прочитал только в
    первых 40 строках и по докстрингу — детали CTR-кривой и сегментации могут
    отличаться от моего пересказа. **[ИСПРАВЛЕНО: в файле не «750+ строк», а 403
    (`wc -l frog/acceptor_value.py`). Остальное — по-прежнему непроверено.]**

14. Не проверял, совпадают ли 26 файлов `city-batches/` с теми, на которые ссылается
    `wf-args.json` (пути ведут в несуществующий каталог; сравнивал только количество
    и структуру записей). **[РЕВИЗИЯ: количество файлов сходится (26 и 26), но записей
    в них 1017 (25×40 + 17), а не «26 × 40» — см. §4.2. Содержимое батчей с тем, что
    видел воркфлоу, по-прежнему не сверено: путей больше не существует.]**

15. **[Добавлено ревизией]** Не проверялось, соответствует ли `frog/urls-indexable-all.txt`
    какому-то конкретному прогону Screaming Frog. Что подтверждено пересчётом: 14 007
    строк, 17 различных доменов — это согласуется с формулировкой «17 дилерских сайтов».

16. **[Добавлено ревизией]** Состав окружения (какие python-модули установлены)
    меняется между сессиями: первая редакция §6.2 утверждала отсутствие четырёх
    модулей, на деле отсутствует один. Любые выводы вида «скрипт не запустится, потому
    что модуля нет» надо перепроверять на месте перед решением.
