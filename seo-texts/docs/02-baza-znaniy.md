# База знаний брендов и гейт достоверности

Документ описывает область `seo-texts/kb/` + скрипты вокруг неё. Всё проверено по коду
и по локальным данным на ветке `claude/seo-texts-enrichment-prompt-449lyw` (HEAD `b2f9d5c`).
Ссылки даны в формате `файл:строка`. Всё, что не проверено, вынесено в последний раздел.

Все пути ниже — относительно `/home/user/avto/seo-texts/`, если не сказано иначе.

---

## 1. Что это и зачем

Задача области — не дать генератору текстов соврать про бренд.

Сайт prokompressor.ru продаёт технику ~66 брендов (`brands-pricelist.json`: `total: 66`,
свой бренд один — ENGER). Про большинство из них публично известно мало, а LLM охотно
досочиняет год основания, «мировое лидерство» и несуществующие серии. Поэтому в конвейер
генерации встроен **гейт достоверности**: в промпт попадает не «всё, что мы знаем о бренде»,
а только выжимка, прошедшая многоступенчатую сверку источников и adversarial-аудит,
плюс явный запретительный блок «НЕ УТВЕРЖДАТЬ».

Практически гейт — это один модуль `brand_facts_lib.py` (134 строки) поверх одного файла
`kb/brand-facts-clean.json` (41 бренд). Всё остальное в области — это либо конвейер, которым
этот файл когда-то готовили, либо отчёты о качестве данных для человека.

Важное различие, которое надо держать в голове с самого начала:

* **Работающая часть** — `brand_facts_lib.py` + `kb/brand-facts-clean.json` + два билдера
  payload'ов. Это исполняется при каждой сборке payload'ов.
* **Исторический конвейер** — `research_kb.py`, `extract_brand_pages.py`, `extract_manuf.py`,
  `enrich_kb.py`, `enrich_kb_rest.py`, `assemble_brands.py`, `synth_brands.py`, `audit_kb.py`,
  `verify_deps.py`. Он был прогнан один раз в июле 2026 в песочнице, результаты закоммичены
  как данные. Сейчас большинство этих скриптов **не запускаются as-is** (см. раздел 6).
* **Не относится к генерации текстов, но лежит в `kb/`** — `snyatye-verdict.json`,
  `kp-base-all.json`, `photo-bank.json`, `media-data.json` и др. Это активы рассыльщика и
  медиа-конвейера, они читаются из `sender/` и `email-assistant/`. Гейт брендовых фактов
  их не видит.

---

## 2. Точки входа и как запустить

### 2.1. Посмотреть, что гейт отдаёт по бренду (безопасно, без сети)

```bash
cd /home/user/avto/seo-texts
python3 brand_facts_lib.py enger        # тон + готовый блок фактуры
python3 brand_facts_lib.py atlas_copco
python3 brand_facts_lib.py              # без аргумента: сводка по всем 41 бренду
```

Реализация CLI: `brand_facts_lib.py:122-134`. Без аргумента печатает
`slug | tone | размер блока в символах`.

### 2.2. Использовать гейт из своего кода

```python
import brand_facts_lib as bf
bf.has_brand('remeza')      # True/False — есть ли бренд в базе       (brand_facts_lib.py:118)
bf.tone_for('enger')        # 'rodnoy' | 'druzhestvennyy' | 'neytralnyy' (brand_facts_lib.py:54)
bf.fact_block('remeza')     # str или None — готовый текстовый блок    (brand_facts_lib.py:83)
bf.fact_block('remeza', max_facts=8, max_deps=6, include_series=True)  # дефолты
```

`fact_block` возвращает `None`, если бренда нет в базе (`brand_facts_lib.py:86-88`).

### 2.3. Пересобрать payload'ы (единственный способ протолкнуть новые факты в тексты)

```bash
cd /home/user/avto/seo-texts
python3 build_compressor_payloads.py            # компрессорные страницы
python3 build_payloads.py                       # некомпрессорные (осушители/фильтры/…)
python3 build_payloads.py --category ref_dryer  # только одна категория
```

Обе программы кладут `gen/payload-<slug>.json`. Ключ `--category` разбирается в
`build_payloads.py:178-180` (цикл по `sys.argv`).

**ВАЖНО:** `regen_driver.py` НЕ пересобирает payload — он читает готовый
`gen/payload-<slug>.json` (`regen_driver.py:86`, `regen_driver.py:115`). Значит, правка
`kb/brand-facts-clean.json` сама по себе ничего не меняет: нужно заново прогнать билдер
payload'ов, и только потом регенерацию.

### 2.4. Пересобрать досье категорий (локально, без API)

```bash
python3 build_category_ref.py
```
Читает `kb/category-*.md`, чистит `<thinking>` и строки «[уверенность: низкая]»
(`build_category_ref.py:28-43`), пишет `kb/category-ref/<type>.md` и
`kb/category-ref/index.json` (`build_category_ref.py:54-60`). Индекс потом подкладывается
в payload некомпрессорных страниц (`build_payloads.py:52`, `build_payloads.py:161-163`).

### 2.5. Пересчитать бренды по прайсу

```bash
python3 count_brands.py          # нужен pricelist-slim.xlsx рядом со скриптом
```
`count_brands.py:8` — вход `pricelist-slim.xlsx`, `count_brands.py:84-87` — выход
`brands-pricelist.json`. **Файла `pricelist-slim.xlsx` в репозитории нет**, но он есть на
дропе (5 345 301 байт, mtime 2026-07-16) — проверено `bash server/drop_client.sh list`.
Скачать: `bash server/drop_client.sh down pricelist-slim.xlsx`.

### 2.6. Скрипты, которые ходят в провайдерский API

Все они требуют `PROVIDER_API_KEY` и жгут квоту. Запускать только осознанно.

| Команда | Вход | Выход |
|---|---|---|
| `python3 research_kb.py` | список из `research_kb.py:13-23` (62 бренда) + 4 FAQ-задачи `research_kb.py:48-59` | `kb/brand-<slug>.md`, `kb/faq-ideas-*.md`, лог `kb/research.log` |
| `python3 extract_brand_pages.py` | `kb/brand-pages-raw/*.html` (`:8`) | `kb/brand-pages-facts.json` (`:46`) |
| `python3 extract_manuf.py` | `kb/manuf-raw/*.html` (`:4`) | `kb/manuf-facts.json` (`:27`) |
| `python3 enrich_kb.py` | `katalogi/relevant-sheets.json` (`:8`) | `katalogi/kb-enrichment.json` (`:54`) |
| `python3 enrich_kb_rest.py` | `katalogi/rest-sheets.json` (`:8`) | `katalogi/kb-enrichment-rest.json` (`:52`) |
| `python3 assemble_brands.py` | 4 источника (`:6-10`) — **локально, без API** | `kb/brands-assembled.json` (`:55`) |
| `python3 synth_brands.py` | `kb/brands-assembled.json` (`:7`) | `kb/brands-synthesized.json` (`:53`) |
| `python3 audit_kb.py` | `brands-synthesized` + `brands-assembled` (`:7-8`) | `kb/kb-audit.json` (`:51`) |
| `python3 verify_deps.py` | `kb/dep-verify-tasks.json` (`:7`) | `kb/deps-verified.json` (`:52`) |
| `python3 kb_ideas.py` | ничего (промпт-инвентарь зашит в `:31-48`) | файлы в **несуществующем** каталоге, см. п. 6 |
| `python3 meyer_extract.py` | тексты в скретчпаде, см. п. 6 | там же |

`research_kb.py` резюмируемый: файл размером >400 байт пропускается
(`research_kb.py:89-91`), то есть перезапуск продолжает с места падения.

Оболочка `run_research.sh` — сторожевой запускатор `research_kb.py`; в первой строке `cd`
в скретчпад давно умершей сессии (`run_research.sh:2`), так что as-is не работает.

---

## 3. Как устроено внутри

### 3.1. Как факты попадают в промпт (полная цепочка)

```
kb/brand-facts-clean.json
        │  brand_facts_lib._load()                 brand_facts_lib.py:30-35
        ▼
brand_facts_lib.fact_block(slug) -> одна строка   brand_facts_lib.py:83-115
        │
        ▼
pl['brand_facts'] = <эта строка>                  build_compressor_payloads.py:206-207
                                                  build_payloads.py:157-158
        ▼
gen/payload-<slug>.json (обычный JSON на диске)
        ▼
gen_provider.build_prompt(): payload читается как ТЕКСТ и вставляется целиком
                                                  gen_provider.py:167, :180-181
        ▼
промпт модели, секция «=== ДАННЫЕ СТРАНИЦЫ (payload; факты бери ТОЛЬКО отсюда) ===»
```

Ключевой момент: **в `gen_provider.py` слова `brand_facts` нет вообще** (проверено грепом).
Промпт не знает про отдельное поле — он просто получает весь payload как plain text
(`gen_provider.py:167`: `payload = open(payload_path).read()`). Поэтому:

* любое поле, которое билдер положил в payload, автоматически видно модели;
* никакой пост-валидации «модель использовала только разрешённые факты» на уровне
  `gen_provider.py` нет; ограничение держится только на тексте стайлгайда
  (`gen_provider.py:23`: «Каждое число в тексте должно быть взято из payload»).

Формат самого блока (`brand_facts_lib.py:89-115`), части склеиваются через `\n\n`:

1. `positioning` (или, если пусто, `Страна производства: <country>.`) — `:90-94`
2. `Серии (подтверждённые): …` — только если гейт что-то пропустил, максимум 6 — `:96-99`
3. `Факты:` + маркированный список `safe_facts[:max_facts]` — `:101-103`
4. `Технические закономерности (подтверждены прайсом):` + `confirmed_dependencies[:max_deps]` — `:105-108`
5. `НЕ УТВЕРЖДАТЬ (нет подтверждения):` + **все** `caveats` без лимита — `:110-113`

Замеры по факту (`gen/*.json`, 759 payload'ов):

* 189 payload'ов содержат `brand_facts` — 40 брендов из 41;
* 377 payload'ов вообще без `page_brand` (фасеты);
* 193 payload'а с `page_brand`, но БЕЗ фактов — бренда нет в базе либо `page_brand`
  ложно определён (см. п. 5.4);
* 189 payload'ов содержат блок «НЕ УТВЕРЖДАТЬ»;
* в 759 готовых `gen/result-*.json` строки «НЕ УТВЕРЖДАТЬ» нет ни разу — служебный блок
  в текст не протёк.

Единственный бренд базы без страниц — `mmz` (Минский моторный завод): payload'а
с `page_brand: "mmz"` нет.

### 3.2. Что такое confidence (их ДВА, и работает только один)

**(а) Пофактовая уверенность внутри `series`** — поле `confidence` у каждого элемента серии.
Это единственная уверенность, на которую смотрит код:

```python
_GATE_OK = {'high', 'medium', 'medium-low'}   # brand_facts_lib.py:27
...
if it.get('confidence') not in _GATE_OK:      # brand_facts_lib.py:67-68
    continue
```

**(б) Общая уверенность по бренду** — поле `confidence` верхнего уровня записи
(`high` / `medium` / `medium-low` / `low`; у `et_compressors` там вовсе фраза
«medium — надёжные те…»). Это поле **нигде в коде не читается**: в `brand_facts_lib.py`
обращения к `r['confidence']` нет, `build_*_payloads.py` его тоже не трогают.
Следствие: у бренда с `confidence: low` (`ats`, `baysar`, `boge`, `coaire`, `das`, `habe`,
`harrison`, `hori`, `renner`, `souair` — 10 брендов) факты идут в промпт ровно так же,
как у `high`. Единственная защита для них — блок `caveats`, который у этих записей
обычно длиннее, чем сам список фактов.

Ещё одна «уверенность» живёт в исходниках: досье `kb/brand-*.md` пишутся с инлайн-метками
`[уверенность: высокая/средняя/низкая]` (`research_kb.py:29`). Эти метки чистятся только
для категорийных досье — `build_category_ref.py:36-39` выбрасывает строки с
«уверенность: низк» и снимает тег. Для брендовых `.md` такой чистки нет, но брендовые `.md`
и не попадают в промпт напрямую (см. п. 4).

### 3.3. Как работает отсев серий (и почему он почти всё режет)

Логика `_series_lines` (`brand_facts_lib.py:59-80`):

1. `if not isinstance(series, dict): return []` — `:61-62`. Если `series` — список,
   выходим сразу.
2. `for group, items in series.items()` — `:63`, ожидается `{группа: [элемент, …]}`.
3. `for it in (items or [])` — `:64`.
4. `if not isinstance(it, dict): continue` — `:65-66`.
5. `if it.get('confidence') not in _GATE_OK: continue` — `:67-68`.
6. Строка собирается как `prefix — name (power_kW кВт, pressure_atm атм, perf_m3min м³/мин)`
   — `:69-79`.
7. В блок идут первые 6 строк — `brand_facts_lib.py:99`.

**Замер на реальных данных.** Всего в `kb/brand-facts-clean.json` при обходе этой логикой
перебирается 4048 «элементов», из них:

* 4008 — не словари (потому что значение группы часто строка: тогда `for it in items`
  идёт по СИМВОЛАМ строки, и каждый символ отбрасывается на шаге 4);
* 28 — словари без поля `confidence`;
* 11 — `confidence: high`;
* 1 — `confidence: medium`.

Форма поля `series` по брендам:

| Форма | Брендов | Что делает гейт |
|---|---|---|
| `null` | 10 | пусто |
| список | 15 | пусто (шаг 1) |
| dict → строки | 5 | пусто (шаг 4, посимвольно) |
| dict → словари | 6 | пусто (шаг 3 перебирает КЛЮЧИ) |
| dict → списки словарей БЕЗ confidence | 3 (`abac` 18 шт., `evrazkompressor` 10 шт., + смешанный `atom`) | пусто (шаг 5) |
| dict → списки словарей С confidence | **1** (`atlas_copco`) | 12 строк, в блок идут 6 |

Итого: **серии реально проходят в промпт ровно у одного бренда — Atlas Copco.**
Подтверждается на выходе: строка «Серии (подтверждённые)» встречается в 11 payload'ах,
и все 11 — страницы Atlas Copco.

Это не падает и не логируется — тихо отдаёт пустоту. Если серии нужны в текстах,
надо либо привести `series` к единой форме, либо переписать `_series_lines`.

### 3.4. Тональные тиры

`TONE` (`brand_facts_lib.py:21-26`): `enger → rodnoy`; `berg`, `atom`, `cross_air`,
`crossair`, `dali`, `hansmann` → `druzhestvennyy`; всё остальное — `neytralnyy`
(`brand_facts_lib.py:54-56`). Тир кладётся в payload как `tier`
(`build_compressor_payloads.py:195`, `build_payloads.py:143`) и дальше трактуется стайлгайдом.

Тон и наличие фактов — независимые вещи. По факту в payload'ах:
`enger` 22 страницы, `dali` 14, `berg` 11, `cross_air` 5, `hansmann` 4, `atom` 3.
При этом `berg` и `cross_air` **отсутствуют** в `kb/brand-facts-clean.json`
(`bf.has_brand('berg') == False`), то есть 16 страниц получают «дружественный» тон
и ноль брендовой фактуры.

### 3.5. Сопоставление слуга страницы и записи базы

`_norm` (`brand_facts_lib.py:38-39`) приводит слуг к `[a-z0-9_]`. `_find`
(`brand_facts_lib.py:42-51`) сначала ищет по ключу, затем — по нормализованному полю `brand`.
Перед этим билдеры делают свою нормализацию: `build_payloads.norm_brand` (`:85-91`) срезает
суффиксы категорий (`_osush`, `_resivery`, `_filtry`, …, регексп `build_payloads.py:50`)
и хвостовой `_2`; `build_compressor_payloads.py:26-27` держит ручной `BRAND_ALIAS`
(`atlas copco → atlas_copco`, `airrus → rkz`, `зиф → zif` и т.д.).

### 3.6. Исторический конвейер сборки базы (как получилось то, что есть)

```
prokompressor.ru/info/brands/*        60 URL из brand-info-urls.txt
   └ fetch_brand_pages.sh  ──────────► kb/brand-pages-raw/*.html      (60 файлов)
       └ extract_brand_pages.py ─────► kb/brand-pages-facts.json      (60 записей)
           └ check_domains.sh / check_domains2.sh (угадать домен производителя)
               └ curl ───────────────► kb/manuf-raw/*.html            (20 файлов)
                   └ extract_manuf.py ► kb/manuf-facts.json           (20 записей)

pricelist-slim.xlsx (299 листов)
   └ (нарезка на katalogi/sheets/*.json — скрипта в репо НЕТ)
       └ enrich_kb.py     ──────────► katalogi/kb-enrichment.json
       └ enrich_kb_rest.py ─────────► katalogi/kb-enrichment-rest.json
           └ verify_deps.py ────────► kb/deps-verified.json  (852 правила)

Fable из памяти (без веб-поиска)
   └ research_kb.py ────────────────► kb/brand-<slug>.md      (62 досье)
                                      kb/faq-ideas-*.md       (4 файла)

мой веб-поиск (сессия, вручную) ────► kb/web-search-facts.md  (29 разделов)

  ВСЁ ВЫШЕ  ─ assemble_brands.py ───► kb/brands-assembled.json   (60 брендов)
                └ synth_brands.py ──► kb/brands-synthesized.json (41 бренд)
                    └ audit_kb.py ──► kb/kb-audit.json           (41 запись, 190 небезопасных фактов)
                        └ ??? ──────► kb/brand-facts-clean.json  (41 бренд)  ← СКРИПТА НЕТ
```

Иерархия надёжности источников зашита в промпты синтеза и аудита:
сайт производителя + прайс = высокая; веб-поиск = средняя-высокая; брендовая страница
нашего сайта = средняя; memory-досье Fable = НИЗКАЯ (`synth_brands.py:10-13`,
`audit_kb.py:11-13`). Классы небезопасных фактов при аудите: `hallucination`, `wrong_domain`,
`misattribution`, `numeric_artifact`, `overclaim`, `stale/contradiction` (`audit_kb.py:22-27`).
Вердикты по зависимостям: `confirmed` / `artifact` / `nuanced` (`verify_deps.py:23-26`).

Замеренные потери на переходах (посчитано по самим файлам):

* `brands-assembled.json` 60 → `brands-synthesized.json` 41: **19 брендов потеряно**.
  Это `airbox, airman, airpol, almig, ariacom, atmos, berg, bezhetskiy_zavod, ceccato,
  comaro, comprag, cross_air, dalgakiran, ekomak, fiac, kraftmachine, pneumatech, robuschi,
  zif_arsenal`. `synth_brands.py:48-52` складывает в результат только успешные фьючерсы,
  а при ошибке печатает `FAIL <slug>` и идёт дальше — то есть 19 брендов, скорее всего,
  просто упали на вызове провайдера/парсинге JSON и потерялись молча.
  ПРЕДПОЛОЖЕНИЕ: доказать это по логам нельзя, лога прогона `synth_brands.py` в репо нет.
* `brands-synthesized.json` 41 → `brand-facts-clean.json` 41: состав слугов совпадает
  один в один (проверено множествами).

Потерянные 19 брендов дают 193 брендовых страницы без фактуры; крупнейшие дырки:
`dalgakiran` 20 страниц, `comprag` 14, `airpol` 11, `berg` 11, `atmos` 10, `pneumatech` 9,
`ekomak` 9, `almig` 9, `comaro` 9, `ariacom` 8, `kraftmachine` 8, `fiac` 7, `cross_air` 5.

---

## 4. Данные и где они лежат

### 4.1. Рабочий файл гейта

`kb/brand-facts-clean.json` — 198 573 байта, dict из 41 ключа-слуга. Поля у каждой записи
ровно 8 (проверено на всех 41): `brand`, `country`, `positioning`, `series`, `safe_facts`,
`confirmed_dependencies`, `caveats`, `confidence`.

Бренды: `abac, atlas_copco, atom, ats, baysar, boge, coaire, dali, das, dnt, enger,
et_compressors, evrazkompressor, fini, fubag, global, habe, hansmann, harrison, hori,
ingersoll_rand, ingro, ironmac, kaeser, kraftmann, lupamat, magnus, mark, master_blast,
mmz, ozen, paramina, remeza, renner, rkz, souair, sullair, tamsan, ultratech, zammer, zega`.

Объёмы: 333 `safe_facts`, 148 `confirmed_dependencies`, 230 `caveats` суммарно.
Готовый блок `fact_block` — от 517 символов (`sullair`) до 2582 (`dali`).

Тексты в файле **обрезаны на этапе подготовки**: 35 из 230 `caveats` имеют длину ровно
150 символов и обрываются на полуслове (например, у `enger`: «…суффикс F у винтовых »);
9 из 41 `positioning` — ровно 250 символов. То есть охранные формулировки местами
приходят в промпт незаконченными.

### 4.2. Промежуточные данные конвейера (лежат в репо, читаются только вручную)

| Файл | Размер | Содержимое |
|---|---|---|
| `kb/brands-assembled.json` | 852 КБ | 60 брендов, сырьё по источникам |
| `kb/brands-synthesized.json` | 357 КБ | 41 бренд после синтеза |
| `kb/kb-audit.json` | 136 КБ | 41 запись аудита; 190 небезопасных фактов; risk: high 19 / medium 16 / low 6 |
| `kb/deps-verified.json` | 595 КБ | 180 листов, 852 правила: confirmed 605 / nuanced 222 / artifact 25 |
| `kb/dep-verify-tasks.json` | 171 КБ | 185 задач на верификацию; ссылается на `katalogi/sheets/NNN.json` |
| `kb/brand-pages-facts.json` | 190 КБ | 60 записей с брендовых страниц сайта |
| `kb/manuf-facts.json` | 82 КБ | 20 записей с сайтов производителей |
| `kb/brand-pages-raw/` | 60 HTML | сырые брендовые страницы |
| `kb/manuf-raw/` | 20 HTML | сырые сайты производителей |
| `brands-pricelist.json` | 12 КБ | 66 брендов / 291 товарный лист прайса, свой бренд ENGER |
| `data/kb_ideas_merged.json` | 126 КБ | 146 идей от 5 «линз» (выход `kb_ideas.py`, скопирован в репо) |

### 4.3. Человекочитаемые отчёты (для владельца, в конвейер не входят)

* `kb/BRENDY-SVODKA.md` (68 КБ) — сводка по 41 бренду: страна, серии, готовые факты,
  «чего не утверждать». Дубль лежит в `paket-baza-znaniy/`.
* `kb/RASHOZHDENIYA.md` (20 КБ) — расхождения между источниками. 3 критических помечены в
  `paket-baza-znaniy/README.md`: ММЗ (перепутанный домен), HORI (hori.jp — геймпады,
  не компрессоры), Coaire.
* `kb/ZAVISIMOSTI.md` (25 КБ) — сырые зависимости из прайса, с явным предупреждением
  об артефактах в шапке.
* `kb/ZAVISIMOSTI-CHISTYE.md` (92 КБ) — 605 подтверждённых правил, «можно в тексты».
* `kb/KACHESTVO-DANNYH.md` (40 КБ) — отчёт по качеству: классы ошибок и список 25 артефактов.
* `kb/web-search-facts.md` (10 КБ) — 29 разделов верифицированных доменов и фактов.
* `kb/brand-<slug>.md` — 62 memory-досье Fable. Источник НИЗКОЙ надёжности,
  в промпт генерации не идут (`assemble_brands.dossier()` берёт из них первые 2500 символов
  как один из 6 входов синтеза — `assemble_brands.py:34-37`).
* `kb/faq-ideas-*.md` — 4 файла идей FAQ. Правило разбора — `kb/FILTER-PLAN.md`
  (три корзины, третью не выбрасывать, а спросить владельца).
* `kb/category-*.md` (10 файлов) + `kb/category-ref/` — досье некомпрессорных категорий;
  ЭТИ попадают в payload через `index.json`.
* `KB-COVERAGE.md` — замер «что из базы подключено к конвейерам». Оттуда: `brand_facts`
  подключены к 759 текстам; КП-база, фотобанк, стоп-лист снятых серий и топ-10 фактов
  Enger — НЕ подключены.
* `KB-EXPANSION-PLAN.md` — план расширения KB рассыльщика (фаза 1/2). Упоминает
  `build_kb.py v2`, который должен собирать обе базы одним движком.

### 4.4. Файлы в `kb/`, принадлежащие ДРУГИМ областям

Лежат в том же каталоге, но к гейту брендовых фактов отношения не имеют:

| Файл | Кто читает | Кто пишет |
|---|---|---|
| `kb/snyatye-verdict.json` (29 брендов) | `sender/snyatye.py:20`, `sender/autoresponder.py:421` | производителя в репо нет |
| `kb/kp-base-all.json`, `kb/kp-base-report.md` | `email-assistant/build_kb.py:8` | `merge_kp.py:60-61` |
| `kb/photo-bank.json`, `kb/media-data.json` | `photo_verify.py:16` | `media_pipeline.py:151-152` |
| `kb/photo-models-verify.json` | — | `photo_verify.py:63` |
| `kb/gap-refuted.json` (465 записей), `kb/enger-top10-facts.json`, `kb/kp-enger-base.json` | не найдено | не найдено |

---

## 5. Ограничения и грабли

**5.1. Правка `kb/brand-facts-clean.json` не влияет на тексты сама по себе.**
Нужно пересобрать payload'ы (`build_compressor_payloads.py` / `build_payloads.py`),
потому что `regen_driver.py` читает уже готовый payload (`regen_driver.py:86`, `:115`).

**5.2. Общий `confidence` бренда ничего не фильтрует.** См. п. 3.2. Факты бренда с
`confidence: low` идут в промпт наравне с `high`. При добавлении новых брендов это
единственный неочевидный момент, на котором легко обжечься.

**5.3. Лимиты `fact_block` молча отрезают фактуру.** При дефолтах `max_facts=8` и
`max_deps=6` в промпт не попадает 69 из 333 `safe_facts` (у 21 бренда) и 56 из 148
`confirmed_dependencies` (у 13 брендов). Серии дополнительно режутся до 6
(`brand_facts_lib.py:99`). А вот `caveats` идут ЦЕЛИКОМ, лимита нет
(`brand_facts_lib.py:110-113`) — у брендов с бедной фактурой запретительный блок
получается длиннее содержательного.

**5.4. `page_brand` бывает ложным.** Среди 193 «брендовых страниц без фактов» много
не-брендов: `kompressornoe_maslo`, `mufty`, `shkivy`, `klapany`, `remkomplekty`,
`vintovye_bloki`, `datchiki` и т.п. Их «спас» гейт — `bf.has_brand()` вернул False, и блок
фактов не добавился. Но `tier` им всё равно проставляется, и логика «это бренд-страница»
в `build_compressor_payloads.py:189-190` (`tail in KNOWN`) для них может сработать по
`projects-index.json` — там KNOWN дополняется брендами из проектов и ручным списком
(`build_compressor_payloads.py:28-34`).

**5.5. Расхождение документации и кода в самом гейте.** Докстринг говорит
«series — только confidence high/medium (low выкидываем)» (`brand_facts_lib.py:7`),
комментарий — «серии ниже medium в текст не идём» (`brand_facts_lib.py:27`),
а множество на самом деле `{'high', 'medium', 'medium-low'}`. Практического эффекта
сейчас нет (значение `medium-low` в сериях не встречается ни разу), но при доработке
данных это ловушка.

**5.6. Обрезанные caveats.** 35 из 230 caveats оборваны ровно на 150 символах,
9 positioning — на 250. Модель получает недописанное предупреждение.

**5.7. Скрипты конвейера — «одноразовые», без флагов и резюмируемости.**
Кроме `research_kb.py` (`:89-91`) ни один не умеет продолжать с места падения: при сбое
провайдера запись просто теряется (`FAIL <slug>` в stdout и всё) — `synth_brands.py:50-52`,
`audit_kb.py:49-50`, `verify_deps.py:50-51`, `enrich_kb.py:51-52`,
`enrich_kb_rest.py:49-50`, `extract_manuf.py:25-26`, `extract_brand_pages.py:44-45`.
Все они пишут итог одним `json.dump` в конце, то есть падение процесса = потеря всего прогона.

**5.8. Относительные пути.** `enrich_kb.py`, `enrich_kb_rest.py`, `assemble_brands.py`,
`synth_brands.py`, `audit_kb.py`, `verify_deps.py`, `extract_manuf.py`,
`extract_brand_pages.py` открывают файлы по относительным путям (`kb/...`, `katalogi/...`).
Запускать строго из `seo-texts/`.

**5.9. Правило владельца про API.** Все перечисленные в п. 2.6 скрипты (кроме
`assemble_brands.py` и `build_category_ref.py`) идут через `gen_provider.make_client()` /
`call()` на модель `claude-fable-5` с `ThreadPoolExecutor(max_workers=6..8)`. Это тяжёлые
параллельные прогоны, они жгут квоту сессии; `make_client()` подставляет
`User-Agent: curl/8.5.0` в обход WAF шлюза (`gen_provider.py:136-146`). Про политику
использования шлюза — см. корневой `CLAUDE.md`.

---

## 6. Что сломано или устарело

**6.1. Нет скрипта, который производит `kb/brand-facts-clean.json`.**
Это самое важное. Проверено:
* грепом по всему репо: строка `brand-facts-clean` встречается ровно в двух файлах —
  `brand_facts_lib.py:4,33` и `build_compressor_payloads.py:6,24`, оба только ЧИТАЮТ;
* `git log --all -S"brand-facts-clean" --name-only` даёт единственный коммит `3614fef`
  (2026-07-16, «полный пайплайн + результаты», 5263 файла) и в нём те же два файла;
* `git grep -l "brand-facts-clean" -- '*.py' '*.sh'` по ВСЕМ шести веткам origin
  (включая `claude/hopeful-galileo-n8gg7o` и `claude/rusprom-b2b-email-templates-8rrstf`,
  которые пришлось дофетчить) — те же два файла;
* полей `safe_facts` / `confirmed_dependencies` (это имена ИЗ clean-файла, в синтезе они
  назывались `ready_facts` и `dependencies` — `synth_brands.py:29,26`) нет ни в одном
  генерирующем скрипте.

Вывод: шаг «`brands-synthesized.json` + `kb-audit.json` + `deps-verified.json` →
`brand-facts-clean.json`» был выполнен вручную/ad-hoc в утраченной сессии.
**Переименование полей и обрезка строк (150/250 символов) — следы этого шага.**
Пока он не восстановлен, обновить базу «штатно» нельзя, только править JSON руками.

**6.2. Гейт серий фактически мёртв для 40 брендов из 41.** См. п. 3.3. Формально код
исполняется, но из-за разнобоя форм поля `series` результат непустой только у Atlas Copco.

**6.3. Отсутствуют входные данные для трёх скриптов.** Каталога `katalogi/` в репозитории
нет (и никогда не было: `git log --all -- 'seo-texts/katalogi/*'` пуст), на дропе файлов
`relevant-sheets.json` / `rest-sheets.json` / `kb-enrichment*.json` тоже нет
(проверено `drop_client.sh list`, 825 файлов). Значит, as-is не запускаются:
* `enrich_kb.py` (нужен `katalogi/relevant-sheets.json`),
* `enrich_kb_rest.py` (нужен `katalogi/rest-sheets.json`),
* `verify_deps.py` (задачи ссылаются на `katalogi/sheets/*.json`),
* `assemble_brands.py` (нужны оба `katalogi/kb-enrichment*.json`).

Восстановить, вероятно, можно из `pricelist-slim.xlsx` (5,3 МБ) и/или `katalog-full.zip`
(145 МБ) с дропа, но **скрипта нарезки прайса на `katalogi/sheets/*.json` в репо нет** —
его тоже придётся написать заново. ПРЕДПОЛОЖЕНИЕ: содержимое `katalog-full.zip` я не
проверял.

**6.4. `kb_ideas.py` и `meyer_extract.py` пишут в несуществующий каталог.**
Оба хардкодят `SCR = /tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad`
(`kb_ideas.py:10`, `meyer_extract.py:10`). Каталога нет (проверено `ls`). `kb_ideas.py`
упадёт на записи результата (`:83`), `meyer_extract.py` — раньше, на чтении источников
(`:47` `SCR/'meyer_txt'`). Результат `kb_ideas.py` сохранён вручную в
`data/kb_ideas_merged.json` (146 идей). Вызывающих у обоих скриптов нет; `kb_ideas.py`
упомянут только в `KB-EXPANSION-PLAN.md:3`.

**6.5. Оболочки с мёртвым `cd`.** `run_research.sh:2`, `fetch_brand_pages.sh:2`,
`check_domains.sh:2`, `check_domains2.sh:2`, `chain_tech.sh:2` — все начинаются с `cd`
в тот же утраченный скретчпад. Плюс `run_research.sh:3-4` ждёт лог-файл задачи
`bu001dqje.output`, которого тоже нет. Запускать нельзя без правки первой строки.

**6.6. `build_kb.py v2`, обещанный в `KB-EXPANSION-PLAN.md:37`, не существует.**
`find /home/user/avto -name "build_kb*.py"` находит только
`email-assistant/build_kb.py` и `email-assistant/build_kb2.py`, и они собирают базу
рассыльщика из `kb/kp-base-all.json`, а не брендовый гейт.

**6.7. Скрипты без вызывающих (мёртвые в смысле «никто не запускает автоматически»).**
Ни один скрипт области не вызывается из другого кода. Единственная ссылка — `run_research.sh:6`
запускает `research_kb.py`. Все остальные (`audit_kb.py`, `enrich_kb.py`, `enrich_kb_rest.py`,
`verify_deps.py`, `synth_brands.py`, `assemble_brands.py`, `count_brands.py`,
`extract_manuf.py`, `extract_brand_pages.py`, `meyer_extract.py`, `kb_ideas.py`,
`build_category_ref.py`) — только ручной запуск. Это нормально для one-shot ETL, но означает,
что при изменении данных ничего не пересоберётся само.

**6.8. `brand_facts_lib` используется только двумя билдерами.**
Проверено грепом: `build_payloads.py:12,142,143,158` и
`build_compressor_payloads.py:12,195,206,207`. Третье упоминание —
`email-assistant/TEMPLATE-SESSION-PROMPT.md:49`, но это инструкция человеку/сессии,
а не вызов из кода. Ни `qa_text.py`, ни `regen_driver.py`, ни рассыльщик гейт не используют.

**6.9. Известные нерешённые вопросы по данным (из отчётов, не мной проверено).**
`paket-baza-znaniy/README.md` перечисляет 3 критических расхождения (ММЗ, HORI, Coaire) как
«на проверку владельцу»; `KB-COVERAGE.md` называет главным операционным риском неподключённый
стоп-лист снятых серий. Отметок «проверено/закрыто» в репо не нашёл.

---

## 7. Быстрый чек-лист для новой сессии

```bash
cd /home/user/avto/seo-texts

# 1. Что в базе вообще есть
python3 brand_facts_lib.py | sort

# 2. Что увидит модель по конкретному бренду
python3 brand_facts_lib.py dalgakiran      # -> None: бренда в базе нет
python3 brand_facts_lib.py remeza          # -> блок фактов

# 3. Сколько страниц реально получили фактуру
python3 - <<'PY'
import json, glob
n = sum(1 for f in glob.glob('gen/payload-*.json')
        if json.load(open(f)).get('brand_facts'))
print('payload с brand_facts:', n, 'из', len(glob.glob('gen/payload-*.json')))
PY

# 4. Протолкнуть изменения базы в тексты
python3 build_compressor_payloads.py && python3 build_payloads.py
# затем — регенерация нужных страниц через regen_driver.py
```

---

## 8. Что не проверено

Честный список того, в чём я не уверен или чего не смотрел.

1. **Содержимое `katalog-full.zip` (145 МБ) на дропе.** Не скачивал. Возможно, там и лежат
   `katalogi/sheets/*.json`, и тогда п. 6.3 решается скачиванием, а не переписыванием.
2. **Причина потери 19 брендов на шаге `synth_brands.py`.** Логов прогона нет. Версия
   «упали на вызове провайдера» — ПРЕДПОЛОЖЕНИЕ, вывод сделан из кода (`synth_brands.py:50-52`),
   а не из наблюдения.
3. **Точный способ, которым получен `brand-facts-clean.json`.** Утверждаю только то, что
   производящего скрипта нет ни в одной ветке и ни в одном коммите. Как именно человек/сессия
   переименовала поля и обрезала строки — не знаю. Возможно, файл делался частично вручную.
4. **Ни один скрипт из п. 2.6 я не запускал** (запрет на вызовы провайдерского API).
   Утверждения об их работоспособности выведены из чтения кода и проверки наличия входных
   файлов, а не из прогона. `assemble_brands.py` и `build_category_ref.py` API не требуют,
   но я их тоже не запускал (правило «не менять ничего», а они перезаписывают данные).
5. **Не проверял, отработали ли реально `fetch_brand_pages.sh` / `check_domains*.sh`**
   в том виде, в каком они лежат — сужу по наличию 60 и 20 HTML-файлов на диске.
6. **Не смотрел `bitrix/`, живую БД сайта, содержимое Битрикса.** Утверждений вида
   «такой страницы/бренда на сайте нет» я сознательно не делаю: все выводы про покрытие
   сделаны по `gen/payload-*.json`, то есть по краулу на момент генерации (июль 2026).
7. **Качество самих фактов** (правда ли Remeza основана в 2001, правда ли у Enger блоки
   BAOSI/HANBELL) я не проверял — это вне возможностей чтения кода. Отчёты
   `kb/KACHESTVO-DANNYH.md` и `kb/RASHOZHDENIYA.md` перечисляют 190 небезопасных фактов
   и 3 критических расхождения; закрыты они или нет — неизвестно.
8. **Производители `kb/gap-refuted.json`, `kb/enger-top10-facts.json`,
   `kb/kp-enger-base.json`, `kb/snyatye-verdict.json`** не найдены грепом и `git log -S`
   по всем веткам. Но эти файлы вне моей области (рассыльщик), и я не исключаю, что они
   собираются кодом, которого нет в этом репозитории (например, на сервере владельца).
   Утверждать «скрипта не существует» про них не берусь.
9. **`kb/BRENDY-SVODKA.md` и `paket-baza-znaniy/BRENDY-SVODKA.md`** — байт-в-байт ли они
   совпадают, не сверял (размер одинаковый, 68 388).
10. **Влияние `tier` на текст.** Я проверил, что `tier` попадает в payload, но что именно
    стайлгайд предписывает делать с `rodnoy`/`druzhestvennyy`/`neytralnyy` — не читал
    (`gen/STYLE-GUIDE*.md` вне этой области).
