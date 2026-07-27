# 08. Конвейер обогащения контактов (ядро)

Область: `seo-texts/server/` — `enrich_contacts.py`, `enrich_db.py`, `verify_company.py`,
`contact_extract.py`, `browser_probe.py`, `dolphin_pool.py`, `hh_scan.py`, `lead_scoring.py`,
`dadata_client.py`.

Документ написан по чтению кода на ветке `claude/seo-texts-enrichment-prompt-449lyw`
(HEAD `57fd48b`). Живую БД сервера и живой прогон я НЕ видел — всё, что про них,
помечено отдельно. Раздел «Что не проверено» — в конце, читать обязательно.

---

## 1. Что это и зачем

Задача: по списку `{ИНН, название, город}` найти сайт компании, вытащить с него
контакты **с ролями** (снабжение/закупки, гл. инженер, директор…), проверить что сайт
действительно принадлежит этой компании, и сложить результат в долговременное
хранилище с указанием, **откуда именно** взят каждый контакт (провенанс).

Всё это нужно, чтобы отдел продаж «Руспром» слал холодные письма и звонил не в
приёмную, а конкретному ЛПР, и мог кликнуть по ссылке и увидеть страницу-источник.

Ключевой факт про исполнение: **этот код почти никогда не запускается в песочнице
Claude**. Он живёт на сервере владельца (`C:\sender\server\`), запускается службой
`job_runner.py`, а сессия кладёт подписанное задание на файловый обменник (drop).
Причина в шапке `job_runner.py:2-20`: сессии в песочнице не ходят на РФ-сайты,
а сервер в РФ ходит и решает капчу.

Два «мозга» области:

* **`enrich_contacts.py` (6814 строк)** — один-единственный вход, весь конвейер и
  ещё ~61 сервисный «op-режим» в одном `main()` (строки 2225-6811). Это де-факто
  универсальная консоль над сервером: от аудита ОКВЭД до деплоя панели рассыльщика.
* **`enrich_db.py` (513 строк)** — SQLite `enrich.db`, система-источник-истины.

---

## 2. Точки входа и как запустить

### 2.1. Как код вообще попадает на исполнение

```
сессия/лаунчер                 drop (parsercompressor.online/drop)          сервер владельца
run_on_server.submit(task,args) --PUT job-<id>.json-->  job_runner.tick() --> subprocess
                                <--PUT result-<id>.json--                     stdin=args JSON
```

* Клиент: `seo-texts/server/run_on_server.py:51` — `submit(task, args, wait, poll, timeout)`.
  Подписывает HMAC-SHA256 по `JOB_SECRET` (`run_on_server.py:55-60`), кладёт `job-<id>.json`,
  ждёт `result-<id>.json`, скачивает и удаляет.
* Сервер: `job_runner.py:62-73` — allowlist задач. Разрешены ровно:
  `verify_company`, `enrich_contacts`, `browser_probe`, `dadata`, `news_scan`,
  `enrich_db`, `dolphin_pool`, `lead_scoring`, `ping`, плюс спец-задачи
  `pull` (самообновление кода, `job_runner.py:151`) и `spawn_campaign` (`job_runner.py:197`).
* Аргументы уходят скрипту **через stdin как JSON**, не в argv и не в shell
  (`job_runner.py:203-206`). Поэтому у всех скриптов области `main()` начинается
  с `json.load(sys.stdin)`.
* Таймаут задания `RUNNER_JOB_TIMEOUT`, дефолт **1800 с** (`job_runner.py:58`).
  Это главный практический лимит: пачка должна укладываться в 30 минут.
* Параллелизм раннера: `RUNNER_WORKERS` (дефолт 8) обычный пул + отдельный пул
  «тяжёлых» на `RUNNER_HEAVY` (дефолт 1) воркер (`job_runner.py:233-234, 325-326`).
  Тяжёлым считается всё, у чего в args есть `sweep|mass_base|news_enrich|
  xmlriver_queries|kg_probe`, а также любой `enrich_contacts` со списком `companies`
  без `site_crawl`, и любой `dolphin_pool` (`job_runner.py:239-246`).
  **Следствие: два обогащающих задания подряд идут строго последовательно.**

### 2.2. Прямой запуск (то, что реально исполняется на сервере)

```bash
# на сервере / локально, если есть окружение:
echo '{"companies":[{"inn":"4205000908","name":"КАО Азот","city":"Кемерово"}],
       "workers":4,"write_db":false}' | python enrich_contacts.py
```

```bash
# из песочницы через раннер (ЗАПРЕЩЕНО, пока идёт боевое обогащение):
python seo-texts/server/run_on_server.py enrich_contacts '{"op":"stage_report"}'
```

### 2.3. Готовые лаунчеры (сторона песочницы)

| Скрипт | Что делает | Команда |
|---|---|---|
| `launch_sales_enrich.py` | база продажников `sales_base.json` (555 ИНН), порциями | `python launch_sales_enrich.py sales_base.json [batch=120] [workers=40] [bworkers=4] [channels=6] [only_inns] [fast]` |
| `launch_core_chunked.py` | ядро центробежных `core396.json`, порциями, `fast=True` по умолчанию | `python launch_core_chunked.py [core396.json] [batch=120] [workers=40] [bworkers=4] [channels=6] [fast=1]` |
| `launch_core_enrich.py` | старый лаунчер ядра — **не использовать**, см. §9 | `python launch_core_enrich.py …` |
| `launch_refail.py` | перепрогон компаний с `extract='regex-provider-fail'` | `python launch_refail.py …` |
| `launch_top1000.py` | топ-1000 без ожидания результата (`wait=False`) | `python launch_top1000.py …` |
| `mass_enrich_loop.py` | цикл `mass_base` пачками по всей базе без сайта | `python3 mass_enrich_loop.py [CAP=40] [BATCHES=0] [WORKERS=4] [CHANNELS=4] [BATCH_TIMEOUT=900]` |
| `mass_enrich_loop.sh` | то же shell-ом | — |

Профиль аргументов, который используют оба основных лаунчера, задан в
`launch_sales_enrich.py:78-93` (`build_args`) — `launch_core_chunked.py` его импортирует
(`launch_core_chunked.py:29`) и меняет только `stream_file` и `source`.

`fast=True` в `build_args` означает: `opo_check=False`, `smtp_check=False`,
`no_fallback=True`. Оставлены включёнными `zakupki_check`, `hh_check`, `no_vk_lookup=True`,
`extract_model='claude-haiku-4-5'`, `pace 2..5`, `fetch_timeout=25`.

### 2.4. Точка входа «панель обогащения»

`server/enrich_panel/panel_core.py` строит задания для тех же op-режимов:
`etp_fit` (`:526`), `checko_okveds` (`:533`), `promote_named_email` (`:540`),
`hh_signals` (`:557`), `opo_batch` (`:575`), `zakupki_mass` (`:586`).
Сама панель — отдельная область, здесь только отмечаю, что она пишет/читает
тот же `enrich.db` и тот же `stage_log`.

---

## 3. Как устроено внутри: путь одной компании

Функция `enrich_one(company, pace)` — `enrich_contacts.py:1692-1990`. Порядок:

1. **Пре-фильтр конкурента** (`:1695` → `_is_competitor`, `:1648`).
   Конкурент, если основной ОКВЭД начинается с `28.13`/`28.12` (`_COMP_OKVED`, `:1642`)
   или имя матчит `_COMP_NAME` (`:1643-1645`, «компрессормаш», «компрессорный завод»…).
   Выход сразу: `method='competitor-skip'`.
2. **ОПО-сигнал** — только если `opo_check` (`:1701` → `find_opo_signal`, `:1021`).
   SERP-эвристика, не авторитетно.
3. **hh-сигнал** — только если `hh_check` (`:1710` → `find_hh_compressor`, `:666`).
   Публичный `api.hh.ru/vacancies?search_field=company_name`; при отказе — фолбэк
   через дельфин (`:685-700`).
4. **ЕИС-закупки** — только если `zakupki_check` (`:1719` → `find_zakupki_contacts`, `:746`).
   RSS по ИНН заказчика → карточки закупок → ФИО + email + телефон снабженца.
   Даёт email с ролью «закупки (конт. лицо)», `source='zakupki:eis'`, `verified_by='inn'`.
5. **Поиск сайта** (`:1741-1771`), если сайт не задан или задан агрегатор:
   1. кэш `enrich.db` (`_site_cache_get`, `:634`), TTL `_SITE_CACHE_DAYS=90` (`:631`) → `site_source='cache:enrich-db'`;
   2. **xmlriver** (`find_site_via_xmlriver`, `:551`) — Яндекс-SERP как XML,
      сперва `website` из карточки knowledge_graph (`site_source='xmlriver-kg'`),
      затем первый «свой» домен из органики (`'xmlriver'`);
   3. list-org (`find_site_via_listorg`, `:488`) — только если `_USE_FALLBACK`;
   4. DuckDuckGo HTML (`find_site_via_search`, `:508`) — только если `_USE_FALLBACK`;
   5. `base_site` из базы обзвона (`site_source='base-site'`, `:1769`).
6. **Если сайта нет** (`:1778-1861`) — каскад доноров, каждый следующий только если
   `best_for_outreach` ещё пуст: карточка Яндекса → Я.Карты по `mapurl` (браузер) →
   ЕГРЮЛ через dadata → VK-группа → бизнес-справочник. Затем `return`.
7. **Если сайт есть**: `r['site'] = _domain(site)`, `r['site_source'] = src` (`:1866-1867`).
   При `discovery_only` — выход (`:1871`).
8. **Поиск staff-страницы через SERP** (`find_staff_via_search`, `:1109`), если не
   выключено `no_staff_search`.
9. **Краул** — `crawl_contacts(site, pace, extra_pages=staff_urls)` (`:1210-1419`), см. §3.1.
10. **Извлечение ролей** — `extract_roles(text, company)` (`:1420-1484`), см. §3.2.
11. **Верификация принадлежности сайта** (`:1906-1927`), см. §3.3.
12. **Провенанс каждого email** (`:1929-1948`), см. §7.
13. **Добор для компаний С сайтом, но без email** (`:1958-1986`): ЕГРЮЛ (`:1958`) →
    справочник (`:1970`). До правки эти доноры работали только в ветке «сайта нет».
    `[ИСПРАВЛЕНО СКЕПТИКОМ: строки пп. 11-13 были сдвинуты на 4-7; сама
    enrich_one — :1692-1988, не :1692-1990.]`
14. **SMTP-проба** (`_finalize_smtp`, `:1656`) — если `smtp_check`.

### 3.1. `crawl_contacts` (`:1210-1419`) — что именно обходится

* Главная через `_fetch_site` (`:1574`); при блоке/капче — рендер браузером
  (`_org_page_probe`, `:924`) и попытка снова (`:1225-1229`).
* Со главной берутся ссылки с хинтами `CONTACT_HINTS` (`:330-338`), максимум 10,
  статика (`.css/.js/.png/…`) отсекается `_STATIC_EXT_RE` (`:352`).
* Приоритет обхода: staff → закупки/снабжение/тендер → остальное (`:1252-1261`).
* Если на staff никто не ссылается — пробуются пути `/company/staff/` и `/staff/`
  (`_STAFF_PROBE_PATHS`, `:343`).
* **Второй уровень**: со всех собранных страниц берутся ссылки с теми же хинтами,
  бюджет +8 страниц (`:1275-1296`).
* **Пагинация** списков сотрудников (`?PAGEN_n=`, `?page=`, `/page/N/`), кап 5,
  стоп-сигнал — страница без новых email (`:1298-1334`).
* Между каждой страницей — `time.sleep(_PACE(*pace))`.
* Перед склейкой `mailto:`/`tel:` **инлайнятся в текст** (`:1358-1361`
  `[ИСПРАВЛЕНО СКЕПТИКОМ: было «:1350-1353» — там блок атрибуции url_first]`), иначе
  провайдер не может связать «ФИО + должность + email» на staff-страницах.
* Добор из мест, которые теряет вырезание тегов — `_harvest_from_html` (`:421`):
  mailto, tel, JSON-LD, деобфускация `[at]`/`(точка)`/`&#64;`.
* Если email не нашлись **нигде** — рендер главной в браузере (JS-email),
  `:1378-1401` `[ИСПРАВЛЕНО СКЕПТИКОМ: было «:1372-1400»]`.
* Финальная обрезка — `_contact_cap(txt, 24000)` (`:1152`): «умная», сохраняет
  окна ±130 символов вокруг каждого email / «доб. N» / реквизитов, дедуплицирует
  повторяющийся футер. Согласовано с `text[:24000]` в промпте.
* Возврат: `(текст, список_страниц, ошибка, csrc)`, где `csrc['emails'][email] =
  {src, local, ctx, url}` — метод находки и **URL страницы-источника**.

### 3.2. `extract_roles` (`:1420-1484`) — провайдер

* Промпт (`:1428-1461`) требует строгий JSON: `owner_match`, `owner_reason`,
  `activity`, `is_compressor_maker`, `emails[{email,role,person}]`, `phones`,
  `best_for_outreach`. Роли фиксированные: `директор|снабжение/закупки|гл.инженер|
  продажи|бухгалтерия|приёмная|общий`.
* Определение конкурента в промпте **узкое**: конкурент = тот, кто сам производит/
  продаёт/сдаёт в аренду компрессоры, генераторы азота/кислорода, мембранные и
  адсорбционные установки, фотосепараторы, рентген-инспекцию. Котлы/трубы/насосы/
  станки — это КЛИЕНТЫ.
* Транспорт: `verify_company._provider_call_stdlib` (`verify_company.py:167-217`).
  Стриминг SSE обязателен; тело gzip-ится и шлётся **chunked мелкими кусками по 1200 Б
  с паузой 0.15 с** — маршрут сервера душит большие однокусковые POST (`verify_company.py:170-177`).
  Заголовок `User-Agent: curl/8.5.0`. Фолбэк — обычный `urllib` POST.
* Модель берётся из `VC._PROVIDER_MODEL`, которую `enrich_contacts.main()` ставит
  на строке 6649-6650.
* 3 попытки; после каждой — отсев junk-адресов `_is_junk_email` (`:385`) и
  **пересчёт `best_for_outreach` кодом** через `_best_by_role` (`:405`) по порядку
  `_ROLE_RANK` (`:401`): закупки 0 > гл.инженер 1 > директор 2 > продажи 3 >
  приёмная 4 > бухгалтерия 5 > общий 6. Ответ модели — только разрешение ничьей.
* Если ключ есть и в тексте есть email, но провайдер упал 3 раза — возвращается
  `how='regex-provider-fail'`. Это специальная метка: `_done_inns` (`:2153`) её
  **не считает done**, пока не набрано 3 попытки, и такая компания переобрабатывается.

### 3.3. Верификация принадлежности сайта (`:1906-1924`)

Значение попадает в `r['verified']` и в `companies.verified`:

| verified | Условие |
|---|---|
| `inn` | ИНН компании найден в тексте сайта как отдельное слово |
| `ogrn` | ОГРН найден в цифровом слепке текста |
| `phone` | последние 10 цифр телефона из базы совпали с телефоном на сайте |
| `provider` | модель вернула `owner_match=true` |
| `mismatch` | модель вернула `owner_match=false` — сайт НЕ этой компании |
| `None` | ничего не подтвердилось |

`blocked = (verified == 'mismatch') or is_compressor_maker` (`:1927`) — при этом
emails и `best_for_outreach` обнуляются (`:1928`, `:1951`).
`[ИСПРАВЛЕНО СКЕПТИКОМ: было «:1931», «:1932», «:1957» — сдвиг на 4-6 строк.
Сам блок верификации — :1906-1927, не :1906-1924.]`

---

## 4. Полная таблица op-режимов `enrich_contacts.py`

Режим выбирается полем `op` в stdin-JSON. Каждый op — `return` в `main()`; ниже
приведены **строки диспетчера**. Всего 61 значение `op` на 61 месте диспетчера
(`base_header` объявлен дважды — см. §9).

### 4.1. Основное обогащение и мониторинг

| op | строка | Что делает |
|---|---|---|
| `coverage_probe` | 3854 | Чистый замер на выборке: гоняет `enrich_one` со всеми источниками параллельно, считает покрытие ИЗ РЕЗУЛЬТАТА. По умолчанию в БД не пишет. Ставит свои `_SEM_BROWSER`, `zakupki_check/smtp_check=True`, `no_vk_lookup=True` |
| `coverage_report` | 4517 | Покрытие по списку ИНН **из `enrich.db`**, без нового обогащения |
| `tail_stream` | 3904 | Хвост любого `*.jsonl` на сервере + агрегат по всему файлу (сайты/email/best, разбивка `extract`, VK-ошибки). `fail_inns=true` возвращает ИНН с `regex-provider-fail` и готовые строки для перепрогонки |
| `read_stream`* | 6381 | Сырые записи jsonl (не `op`, а отдельный ключ `read_stream`) |
| `export_core` | 3987 | Финальная выгрузка ядра с провенансом в CSV на дроп: лучшая запись на ИНН из jsonl-стримов, добор из `enrich.db`, пост-фильтр ОПО, защита от «общих» доменов (`shared_threshold`, деф. 2), скоринг |
| `source_selftest` | 4446 | Проверка КАЖДОГО источника по отдельности на реальных компаниях |
| `stage_report` | 5935 | Покрытие по `stage_log`: сколько ИНН прошло каждую стадию; `inns` → стадии по ИНН; `missing_stage` → кто стадию не проходил |
| `stage_backfill` | 5955 | Ретро-заполнение `stage_log` из уже накопленных колонок `companies`/`emails` |
| `envcheck` | 5754 | Какие ключи видит раннер (env + оба `runner-secrets.env`), значений не показывает |
| `provider_probe` | 2927 | Селф-тест провайдерского API С СЕРВЕРА, ошибки наружу дословно; умеет `trickle`, `gzip`, `via_dolphin_proxy`, `prompt_len` |

\* `read_stream`, `base_peek`, `base_pick`, `base_cities`, `kg_probe` — ключи верхнего
уровня, а не `op`; лежат в конце `main()` (6381, 6467, 6470, 6403, 6620).

### 4.2. База обзвона и ОКВЭД

| op | строка | Что делает |
|---|---|---|
| `base_header` | 2429 | Хедер базы обзвона с индексами колонок |
| `okved_audit` | 2264 | Аудит ОКВЭД по всей базе 161k: конкуренты, карта частота↔приоритет, «скрытые» лиды (таргет только в доп-ОКВЭД) |
| `hidden_leads` | 2666 | 649 «скрытых лидов» — таргет-ОКВЭД только в доп-кодах; выгрузка CSV |
| `okved_recheck` | 2735 | Пересчёт классификации news-пула без нового скрейпа checko; пишет `companies` + `stage_log('okved_v2')` |
| `checko_okveds` | 2796 | Полный список ОКВЭД через `checko.ru/company/<ОГРН>/activity` (dadata на тарифе доп-ОКВЭД не отдаёт); `stage_log('checko')` |
| `checko_targets` | 2896 | Кого ещё надо (пере)классифицировать через checko |
| `centrifugal_inns` / `centrifugal_export` | 3372 | ОКВЭД-воронка центробежных компрессоров из базы → CSV на дроп; `include_second`, `floor_mult` |
| `obzvon_append` | 2373 | Дописать строки в CSV базы обзвона (файл с дропа), с бэкапом и дедупом по ИНН |
| `obzvon_fix_base_label` | 2345 | Починка метки «База» у добавленных строк |

### 4.3. Новостные лиды

| op | строка | Что делает |
|---|---|---|
| `news_inn_coverage` | 2230 | Сколько новостных ИНН есть/нет в базе обзвона |
| `news_campaign` | 2439 | Сборка CSV-кампании по новостным лидам; `fit_map`, `checko_codes`, `fit_equipment`, `dadata_fill`, `out` |
| `news_funnel` | 2593 | Воронка новостного пайплайна в обратном порядке — где было отсечение |
| `ingest_noinn` | 5565 | Ингестер лидов БЕЗ ИНН из `news_stream.jsonl`: dadata-варианты → SERP «"имя" ИНН» → чексумма → обратная верификация dadata |
| `resolve_test` | 5529 | Ручной резолв имён → ИНН той же цепочкой (диагностика) |
| `resolve_leaked` | 5988 | Пере-резолв «утёкших» лидов с гейтом по совпадению города; `limit`, `offset`, `require_city` |

### 4.4. Источники контактов (пробы и массовые проходы)

| op | строка | Что делает |
|---|---|---|
| `zakupki_probe` | 5462 | Тест `find_zakupki_contacts` по списку ИНН |
| `zakupki_mass` | 5100 | Массовый ЕИС-проход сверху вниз по выручке; durable `.zk_done.txt` + `zakupki_stream.jsonl`; самочейн; стоп-файл `zakupki_stop.flag` |
| `etp_fit` | 5393 | ЭИС по fit-пулу новостных; резюм по `stage_log('etp')` |
| `etp_probe` | 4839 | Доступны ли коммерческие ЭТП с РФ-IP без логина |
| `hh_probe` | 5491 | Тест `find_hh_compressor` по именам |
| `hh_signals` | 3651 | hh без API: `hh_scan.scan()` → матч работодателя с `C:\sender\obzvon-index.db`, добор через dadata, запись `signals(source='hh', hotness=3)` + `stage_log('hh')` |
| `hh_vacancy_scan` | 3756 | Инверсия: парсинг `hh.ru/search/vacancy` через дельфин → работодатели → кандидаты |
| `vk_probe` | 5468 | Тест `find_vk_group_contacts` |
| `vk_oauth_dolphin` | 3806 | Привязка VK-токена к IP дельфин-профиля через OAuth внутри профиля |
| `opo_serp` | 3509 | Хватает ли сниппетов xmlriver для ОПО (без браузера) |
| `opo_probe` | 3532 | Разведка авторитетного источника ОПО по ИНН |
| `opo_batch` | 3235 | Боевой ОПО-прогон: N дельфин-профилей параллельно (`multiprocessing`), одна сессия на пачку, CSV на дроп. `stagger_sec`, `sleep_ms`, `total_timeout`, `max_profiles` |
| `opo_licenses` | 3312 | ОПО через лицензии Ростехнадзора на checko (`/licenses/data?source=07`) |
| `fsa_probe` | 4865 | Разведка формы API реестра `pub.fsa.gov.ru` |
| `fetch_grep` | 4673 | Скачать страницу с сервера и показать, где на ней сидит паттерн |

### 4.5. Чистка и качество данных

| op | строка | Что делает |
|---|---|---|
| `clean_bad_sites` | 4554 | Обнулить «сайты» из контент-платформ/агрегаторов; `dry_run=true` по умолчанию, `extra`, `extra_mail` |
| `clean_shared_sites` | 4604 | Обобщённый детектор ложных привязок: домен сайта/почты на ≥ `shared_threshold` (деф. 2) разных ИНН → обнулить. `dry_run=true` |
| `mark_shared_phones` | 4906 | Телефоны у ≥ `min_share` (деф. 3) компаний → `shared_phones.txt` на дроп + флаг `companies.shared_phone` (колонка добавляется `ALTER TABLE` на строке 4960) |
| `phone_match` | 4979 | Перенос email внутри групп одинаковых телефонов. `dry_run=true`, `max_group` (деф. 6), `name_gate` (деф. True). Записи помечаются `source='phone-match:<ИНН-донора>'` |
| `phone_match_rollback` | 5092 | Откат: `DELETE FROM emails WHERE source LIKE 'phone-match%'` |
| `promote_named_email` | 5217 | Пере-выбор `best_email`: именной адрес снабженца вместо `info@`. Есть `ROLE_DENY` (кадры/бухгалтерия/пресса/юристы) и отсев freemail. `stage_log('best_email_v2')`, `revert` |
| `smtp_verify` | 4704 | Тест SMTP-пробы по списку email (до 12) |
| `dnscheck` | 3587 | A-запись, редиректы, MX/SPF/DKIM/DMARC через `nslookup` |

### 4.6. Dolphin{anty}

| op | строка | Что делает |
|---|---|---|
| `dolphin_cleanup` | 3075 | Закрыть зависшие профили |
| `dolphin_stop_all` | 4824 | Погасить все профили |
| `dolphin_conn1` | 3100 | Ровно один старт + connect + goto (чистый тест) |
| `dolphin_diag` | 3145 | list → start (headless и обычный) → `connect_over_cdp`; пинпоинт где рвётся |
| `dolphin_proxy_check` | 4713 | READ-ONLY: у каких профилей стоит прокси (через Remote API) |
| `dolphin_set_proxies` | 4765 | Раскидать прокси по профилям round-robin; `skip_vk_profile=True` по умолчанию |

### 4.7. Инфраструктура панели рассыльщика (к обогащению отношения не имеет)

| op | строка | Что делает |
|---|---|---|
| `panel_env_set` | 5808 | Обновить `C:\sender\panel.env` + `AppEnvironmentExtra` службы + рестарт |
| `panel_file_put` | 5871 | Положить файлы с дропа под `C:\sender`; `{get: path}` — прочитать без записи |
| `panel_zip_deploy` | 6154 | Деплой `panel-update.zip`: стоп службы → распаковка → старт → `svc_probe` |
| `panel_py` | 6229 | Запустить скрипт питоном панели (3.11) с env из `panel.env` |
| `svc_probe` | 6264 | Диагностика службы `SenderPanel` |
| `smtp_selftest` | 6324 | Реальная отправка письма движком панели (`live=True`) |
| `smtp_login_batch` | 5788 | Проверка SMTP-логина по списку ящиков (465 SSL) |

---

## 5. Полная таблица аргументов дефолтного пути

Дефолтный путь = stdin-JSON **без** ключа `op` и без `read_stream`/`base_*`/`kg_probe`.
Строки — из `enrich_contacts.py`.

### 5.1. Что обогащать

| Аргумент | Дефолт | Строка | Смысл |
|---|---|---|---|
| `companies` | `[]` | 6476 | Список `{inn, name, city?, site?, ogrn?, phones?, okved?, okved_all?, base_site?, division?, region?, pxr?}` |
| `resume` | false | 6480 | Пропустить ИНН, уже сделанные в `stream_file` (и в `stream_file*.jsonl`) |
| `max_attempts` | 3 | 6487 | Кап безрезультатных попыток на ИНН при `resume` |
| `mass_base` | false | 6526 | Взять компании из базы обзвона (`_base_pick`) вместо `companies` |
| `no_site` | true | 6529 | Для `mass_base`/`base_pick`: только компании без сайта в базе |
| `size_col` | 34 | 6529 | Колонка ранжирования (выручка) |
| `okved_prefixes` | нет | 6531 | Фильтр по первым 2 символам основного ОКВЭД |
| `cap` | 0 | 6534, 6610 | Ограничить пачку. **Работает только для `mass_base`/`news_enrich`**, обычный `companies` не режет |
| `chain` | false | 6541, 6613 | Самочейнинг: написать следующее подписанное задание на дроп (`_chain_next`, `:2189`) |
| `news_enrich` | false | 6552 | Обогащать компании с новостным сигналом из `signals` |
| `news_retry` | 2 | 6555 | Кап попыток на «пустую» новостную компанию |

Стоп-флаги самочейнинга (`_chain_next`, `:2199`): `news_stop.flag` для `news_enrich`,
иначе `mass_stop.flag`. Файл кладётся на дроп.

### 5.2. Темп и параллелизм

| Аргумент | Дефолт | Строка | Смысл |
|---|---|---|---|
| `pace_min` | 6.0 | 6640 | Нижняя граница паузы между страницами (сек) |
| `pace_max` | 14.0 | 6640 | Верхняя граница |
| `workers` | 6 (клип 1..80) | 6641 | Потоков МЕЖДУ компаниями |
| `browser_workers` | 2 (клип 1..30) | 6673 | Размер `_SEM_BROWSER` — одновременных Chromium |
| `channels` | нет (env `XMLRIVER_CHANNELS`, деф. 4) | 6646 | Размер `_SEM_XMLRIVER` |
| `fetch_timeout` | 45 (`verify_company.py:44`) | 6652 | Таймаут GET сайта, ставится в `VC._FETCH_TIMEOUT` |

### 5.3. Флаги источников (все `bool`, все по умолчанию выключены, если не сказано иное)

| Аргумент | Дефолт | Строка | Глобаль | Эффект |
|---|---|---|---|---|
| `no_browser` | false | 6654 | `_NO_BROWSER` | Не поднимать Chromium вообще |
| `no_fallback` | false | 6655 | `_USE_FALLBACK` (инверт.) | Выключает list-org и DuckDuckGo — **снимает сериализатор**, см. §8 |
| `return_text` | false | 6656 | `_RETURN_TEXT` | Вернуть сырой текст сайта (до 24000) в результат |
| `skip_provider` | false | 6657 | `_SKIP_PROVIDER` | Только краул+regex, без вызова модели |
| `no_staff_search` | false | 6658 | `_NO_STAFF_SEARCH` | Не искать staff-страницу через SERP |
| `no_dir_lookup` | false | 6659 | `_NO_DIR_LOOKUP` | Не искать контакты в бизнес-справочниках |
| `opo_check` | false | 6660 | `_OPO_CHECK` | ОПО-сигнал |
| `discovery_only` | false | 6661 | `_DISCOVERY_ONLY` | Фаза-1: только найти сайт, без краула |
| `hh_check` | false | 6662 | `_HH_CHECK` | Адресная hh-проверка компании |
| `no_site_cache` | false | 6663 | `_NO_SITE_CACHE` | Не брать сайт из кэша `enrich.db` |
| `no_vk_lookup` | false | 6664 | `_NO_VK_LOOKUP` | Не искать VK-группу |
| `zakupki_check` | false | 6665 | `_ZAKUPKI_CHECK` | Контакт закупщика из ЕИС |
| `smtp_check` | false | 6666 | `_SMTP_CHECK` | SMTP-проба ящиков |
| `site_cache_days` | 90 | 6667 | `_SITE_CACHE_DAYS` | TTL кэша ИНН→сайт |

### 5.4. Модель, дельфин, запись

| Аргумент | Дефолт | Строка | Смысл |
|---|---|---|---|
| `extract_model` | `claude-haiku-4-5` при `mass_base`/`news_enrich`, иначе `claude-fable-5` | 6649-6650 | Модель для `extract_roles` |
| `dolphin_token` | `_read_secret('DOLPHIN_TOKEN')` | 6671 | Токен Dolphin{anty} |
| `dolphin_profiles` | live-список по токену → `dolphin-profiles.txt` | 6672 | Пул профилей (`_resolve_dolphin_profiles`, `:146`) |
| `write_db` | **true** | 6680 | Писать в `enrich.db` и jsonl |
| `stream_file` | `enrich_stream.jsonl` | 6692 | Имя append-only потока (в папке скрипта) |
| `source` | `enrich` | 6709, 6754 | Тег источника: пишется в `rec['_src']` jsonl **и в `emails.source` в БД** |
| `division` | нет | 6722 | Направление задания. **Приоритет обратный тому, что можно подумать**: `div = src.get('division') or args.get('division')` (`:6722`), и только если оба пусты — считается из ОКВЭД через `division_for_okveds` (`:6726`). То есть `args['division']` ПЕРЕБИВАЕТ вывод из ОКВЭД. `[ИСПРАВЛЕНО СКЕПТИКОМ: было «Направление, если не выводится из ОКВЭД»]` |

---

## 6. Стадии компании (`stage_log`)

Канон (`enrich_db.py:222-234`): **пишутся только успешно завершённые стадии**.
Отсутствие строки = стадию можно (пере)запускать. Повторный успех перезаписывает
`detail`/`ts`. Уникальность `(inn, stage)`.

| Стадия | Кто пишет | Detail |
|---|---|---|
| `site` | `_persist`, `enrich_contacts.py:6762` | `<домен> (<site_source>)` |
| `site_cand` | `_persist:6764`, `stage_backfill:5974` | кандидат-сайт. **Из `_persist` недостижимо** — `enrich_one` никогда не ставит `r['cand_site']` (см. §9). `[ИСПРАВЛЕНО СКЕПТИКОМ: было «stage_backfill:5969» — :5969 это общий `db.mark_stage` внутри `_m`, сам `_m('site_cand')` на :5974]` |
| `crawl` | `:6766` | секунды краула или `ok` |
| `email` | `:6768` | `N шт; how=<method>` |
| `verify` | `:6770` | `inn`/`ogrn`/`phone`/`provider` |
| `phone` | `:6772` | `N шт` |
| `opo` | `:6774` | `signal` |
| `hh` | `:6776` (и `hh_signals`, `:3747`) | `vacancy` / `вакансий=N матч=base|dadata` |
| `zakupki` | `:6778` | число карточек закупок |
| `okved_v2` | op `okved_recheck`, `:2781` | параметры вида `fit=1;…` |
| `checko` | op `checko_okveds`, `:2887` | `div=kc` и т.п. |
| `best_email_v2` | op `promote_named_email`, `:5381` | новый лучший адрес |
| `etp` | op `etp_fit`, `:5432`/`:5456` | результат или `err=…` |
| `releak_resolve` | op `resolve_leaked`, `:6140` | резолв утёкшего лида |
| `activity` | `stage_backfill`, `:5980` | ретро-метка |

**Важная тонкость:** стадия `site` ставится при любом найденном сайте, даже если в
`companies.site` он НЕ записан (не подтверждён и ушёл в `cand_site`). То есть
«стадия `site` есть» ≠ «`companies.site` заполнен».

---

## 7. Провенанс контактов

### 7.1. Значения поля `source` у email (в результате `enrich_one`)

| `source` | Строка | Когда |
|---|---|---|
| `own-site` | 1943 | email найден на сайте компании (обычная страница) |
| `own-site:staff` | 1939 | URL страницы-источника содержит staff-хинт |
| `own-site:js` | 1941 | email появился только после JS-рендера |
| `serp-card:yandex` | 1786 | из карточки knowledge_graph Яндекса |
| `maps:yandex` | 1808 | со страницы организации в Я.Картах (`mapurl`, браузерный рендер) |
| `egrul:dadata` | 1822, 1966 | из ЕГРЮЛ через dadata `findById` |
| `vk-group` | 1836 | из группы VK (описание или блок «Контакты») |
| `directory:<домен>` | 1850, 1977 | из бизнес-справочника (orgpage/cataloxy/pulscen/2gis/…) |
| `zakupki:eis` | 1729 | из карточки закупки ЕИС |
| `phone-match:<ИНН>` | op `phone_match`, `:5085` | перенесён по совпадению телефона |
| `dolphin-pool` | `dolphin_pool.py:63, 189` | из пула дельфин-браузеров |

Телефоны имеют отдельное поле `phones_source` (`serp-card:yandex` / `maps:yandex` /
`vk-group` / `directory:<домен>`), строки 1782, 1813, 1841, 1984.

Поле `verified_by` у контактов из внешних источников: `inn` (ЕГРЮЛ/ЕИС),
`card-name-match` (карточка/карты), `site`/`name` (VK), `inn|phone|name` (справочник).

`source_url` для контактов с собственного сайта берётся из `csrc['emails'][email]['url']`
— это **точная страница**, на которой email встретился впервые (атрибуция делается
до склейки текста, `crawl_contacts:1348-1353`).

### 7.2. ГРАБЛЯ: тонкий провенанс не доезжает до SQLite (по пути `enrich_contacts`)

В `_persist` (`enrich_contacts.py:6750-6755`):

```python
_db.add_email(inn, e.get('email',''), role=..., person=..., mx_ok=...,
              source=args.get('source') or 'enrich',      # <-- job-level, НЕ e['source']
              source_url=e.get('source_url') or '')
```

То есть **штатный конвейер** пишет в `emails.source` **тег задания**
(`sales-base`, `centrifugal-core`, `mass`, `enrich`…), а не `own-site:staff`/`egrul:dadata`.
Тонкий источник сохраняется только в jsonl-потоке (`stream_file`).
`source_url` при этом доезжает корректно.

`[ИСПРАВЛЕНО СКЕПТИКОМ — исходная формулировка «в таблице emails колонка source
содержит тег задания» была слишком широкой. Три поправки:`

1. **`source` пишется только при INSERT.** В `enrich_db.add_email`
   (`enrich_db.py:308-319`) в `ON CONFLICT(inn,email) DO UPDATE SET` перечислены
   `role`, `person`, `mx_ok`, `source_url`, `updated_at` — колонки `source` там **нет**.
   Значит уже существующая тонкая метка НЕ затирается тегом задания при повторном прогоне.
2. **Тонкие метки в живую БД писали другие компоненты.** `ENRICH-SALES-BASE-PROMPT.md:155`
   — контакты ЕИС лежат в `phone_contacts` и `emails` с `source='zakupki:eis'`;
   `:157` — 936 компаний со `source='checko:contacts'`.
   `obzvon-centro/build_centrifugal_db.py:143-166` (`SOURCE_LABEL`) с комментарием
   «честные (не затёртые) метки конвейера записаны техническими кодами» перечисляет
   как реально встречающиеся: `zakupki:eis`, `checko:contacts`, `egrul:dadata`,
   `egrul:dadata-releak`, `serp-card:yandex`, `maps:yandex`, `vk-group`, `staff`,
   `cache:enrich-db`, `hh`, `news`, `directory`.
3. **В БД смесь.** Там же (`build_centrifugal_db.py:129` `RUN_LABELS` и комментарий
   `:334-338`) прямо сказано: записи с меткой запуска (`enrich`/`sales-base`/
   `centrifugal-core`/`core`) — «массовые», и `nice_source()` для них восстанавливает
   источник из `source_url`. То есть колонка содержит И метки запуска, И тонкие коды.

`Практический вывод не меняется (по пути enrich_contacts тонкий source теряется),
но утверждать «в emails.source всегда тег задания» нельзя. Проверять запросом
SELECT source, COUNT(*) FROM emails GROUP BY 1 к живой БД.]`

Это объясняет, почему в git есть коммит «XLSX: восстановление источника»
(`76f6bf6`) — сборщик выгрузки вынужден добирать источник из потока/URL.

---

## 8. Семафоры и их влияние на массовый прогон

| Семафор | Объявление | Размер по умолчанию | Управление | Кто держит |
|---|---|---|---|---|
| `_SEM_LISTORG` | `:17` | **1, хардкод** | нет (только `no_fallback` целиком выключает вызов) | `enrich_one:1756` |
| `_SEM_SEARCH` | `:18` | **1, хардкод** | нет (то же) | `enrich_one:1760` |
| `_SEM_BROWSER` | `:19` | 2 | `browser_workers` (`:6673`), клип 1..30 | `:935, 1389, 1612, 1625` |
| `_SEM_XMLRIVER` | `:23` | `XMLRIVER_CHANNELS` или 4 | `channels` (`:6646`) | `:575, 963, 1041, 1127, 5601` |

Плюс `_XMLRIVER_TRIES` (`:24`, env `XMLRIVER_TRIES`, деф. 3) — лёгкий ретрай при
ответе «Нет свободных каналов».

**Главный тормоз массового прогона** — не браузер и не провайдер, а фолбэки поиска
сайта. Обоснование прямо в коде `launch_sales_enrich.py:59-76`: `time.sleep(_PACE(1.5,4.0))`
стоит **внутри** `with _SEM_LISTORG:` (`enrich_contacts.py:1756-1758`), а сам
`find_site_via_listorg` делает ещё один `time.sleep(_PACE())` = 6..14 с между двумя
запросами (`:497` `[ИСПРАВЛЕНО СКЕПТИКОМ: было «:495»]`). Слот удерживается
10-60 секунд, и **все** воркеры выстраиваются в очередь
длиной 1 — независимо от того, сколько их поставили.

Замер оттуда же (286 компаний): list-org не нашёл ни одного сайта, DuckDuckGo — три;
остальное закрыли кэш (135) и xmlriver (138). Поэтому на массе штатно ставится
`no_fallback: true`.

Второе узкое место — лимит **каналов аккаунта xmlriver**. Это не транзиент: при заливе
ответ «Нет свободных каналов» держится, поэтому ретрай сделан лёгким, а concurrency
надо держать ≤ числа каналов аккаунта (`:565-571`). Лаунчеры ставят `channels=6`.

Третье — `RUNNER_HEAVY=1` на самом раннере (`job_runner.py:234`): обогащающие задания
не идут параллельно друг другу, сколько бы их ни положили на дроп.

Практический вывод для новой сессии: увеличивать `workers` выше ~40 при включённых
фолбэках бессмысленно; сперва `no_fallback`, затем `channels`, только потом `workers`.

---

## 9. Схема `enrich.db`

Путь: `os.environ['ENRICH_DB']` или `%SENDER_DIR%\enrich.db`, по умолчанию
`C:\sender\enrich.db` (`enrich_db.py:21-22`). Режим WAL, `check_same_thread=False`,
запись сериализована внешним локом `_wlock` в `enrich_contacts._persist`.

DDL — `enrich_db.py:24-48`:

```sql
companies(inn TEXT PRIMARY KEY, name, division, okved, region, pxr REAL,
          site, cand_site, activity, is_competitor INTEGER DEFAULT 0, verified,
          best_email, phones, updated_at)
emails(inn, email, role, person, mx_ok INTEGER, source, source_url, updated_at,
       UNIQUE(inn, email))
signals(inn, source, event_type, what, sum, source_url, hotness INTEGER, ts,
        updated_at, UNIQUE(inn, source, what))
donors(domain TEXT PRIMARY KEY, rss, rss_items, event_count, status,
       first_seen, updated_at)
seen_news(k TEXT PRIMARY KEY, ts)
stage_log(inn, stage, detail, ts, UNIQUE(inn, stage))
-- индексы: ix_stage_inn, ix_stage_st, ix_comp_div, ix_comp_site, ix_email_inn, ix_sig_inn
```

Миграции в конструкторе (`:212-219`): `companies.cand_site`, `emails.source_url`
добавляются `ALTER TABLE` под `try/except`.

**Живая БД на сервере шире этого DDL.** Найденные в коде обращения к объектам,
которых `_SCHEMA` не создаёт:

* `companies.shared_phone` — добавляется `ALTER TABLE` внутри op `mark_shared_phones`
  (`enrich_contacts.py:4960`);
* `companies.revenue_rub` — читается в `build_contacts_xlsx.py:161`,
  `_ops_sources_report.py:50`, `obzvon-centro/build_centrifugal_db.py:553, 579-580, 609`
  и в `sender/infopanel.py:409-413, 691-696` («чеко-добор»); DDL в репозитории я не нашёл;
  `[ИСПРАВЛЕНО СКЕПТИКОМ: было «build_contacts_xlsx.py:129» — там разбор JSON-списков,
  обращение к revenue_rub на :161. Список читателей был неполон.]`
* `phone_contacts(inn, phone, person, role, source, source_url, updated_at)` —
  читается в `build_contacts_xlsx.py:178`, `_ops_recon_bases.py:114-127`,
  `_ops_shared_contacts.py:24, 51`, `_ops_sources_report.py:37` и
  `obzvon-centro/build_centrifugal_db.py:895`;
  по `ENRICH-SALES-BASE-PROMPT.md:159-161` она «создана ранее». DDL в репозитории нет;
  `[ИСПРАВЛЕНО СКЕПТИКОМ: было «build_contacts_xlsx.py:137» — фактически :178;
  список читателей был неполон.]`
* таблицы панели обогащения (`enrich_run_rows` и др.) — `enrich_panel/panel_core.py:650`.

Считать, что этих объектов «нет», нельзя: репозиторий содержит не весь код,
который трогал БД. Проверять только запросом к живой БД.

Отдельные БД, которых нет в репозитории, но код на них ссылается:

* `C:\sender\obzvon-index.db`, таблица `obzvon(inn, name_short, name_full)` —
  `enrich_contacts.py:3670-3679` (op `hh_signals`);
* `C:\sender\sender.db` — очередь писем панели (упоминание в `ENRICH-SALES-BASE-PROMPT.md`).

### 9.1. Правила записи (важно для понимания данных)

`upsert_company` (`enrich_db.py:252-279`): непустые поля перезаписывают, **пустые
не затирают старое**.

Логика записи сайта в `_persist` (`enrich_contacts.py:6729-6743`):

* если у компании УЖЕ есть `verified ∈ {inn,ogrn,phone,provider}` — **не трогаем
  только `verified`/`site`/`cand_site`** (`:6733-6734` ставит их в `None`);
  `[ИСПРАВЛЕНО СКЕПТИКОМ: было «не трогаем ничего». Остальные поля —
  name, division, okved, region, pxr, activity, is_competitor, best_email, phones —
  уходят в upsert_company как обычно (:6746-6752) и перезаписываются, если непусты.]`
* иначе если новый `verified` подтверждён — пишем `site`, чистим `cand_site`;
* иначе если `verified='mismatch'` — пишем метку, сайт не пишем;
* иначе — сайт идёт в `cand_site`, а не в `site`.

`add_email` (`:304-319`): роль нормализуется каноном `_ROLE_CANON` (`:284-292`) в
8 значений — `снабжение/закупки`, `продажи`, `директор`, `гл.инженер`, `бухгалтерия`,
`кадры`, `приёмная`, `общий`. Без этого `WHERE role='снабжение/закупки'` в рассылке
промахивался бы мимо «закупки»/«снабженец».

### 9.2. Двойная запись

Каждая готовая компания пишется СРАЗУ в два места (`_persist`, `:6698-6780`):

1. **`stream_file` jsonl** — append + `flush` + `fsync`, битая строка не рушит остальные;
2. **SQLite** — идемпотентно по ИНН.

Восстановление БД из потока: `python enrich_db.py` со stdin `{"op":"rebuild"}`
(`enrich_db.py:476-507`). Внимание: `rebuild` НЕ восстанавливает `verified`,
`division`, `cand_site`, `mx_ok`, `source_url` — только имя, ОКВЭД, регион, сайт,
activity, is_competitor, best_email, phones и email с ролями.

### 9.3. CLI `enrich_db.py`

stdin-JSON, ключ `op`:

| op | Что |
|---|---|
| `stats` (деф.) | компании / с сайтом / с email / конкуренты / всего email / по направлениям / сигналы |
| `export` | плоские строки компания+email |
| `snapshot` | консистентный `sqlite3.backup` → PUT на дроп (`name`, деф. `enrich_snapshot.db`) |
| `rebuild` | восстановить из `enrich_stream*.jsonl` |
| `rebuild_donors` | пересчёт доменов-доноров из `news_stream*.jsonl` |
| `donors` | выгрузка донорской базы |

### 9.4. ОКВЭД → направление

`OKVED_DIRECTIONS` (`enrich_db.py:53-131`) — 77 кодов, значение `(направление, бюджет 1-5)`,
`kc` = Компрессор Центр, `meyer` = фотосепараторы/рентген. Матч **префиксный**
(`25.11` матчит `25.11.1`). Функция `division_for_okveds(*тексты)` (`:184`) возвращает
`('kc'|'meyer'|'kc+meyer'|'', budget 0-5)` по основному И доп. ОКВЭД.

Конкуренты: `PRIMARY_COMPETITOR_OKVEDS = {28.13, 28.12}` (`:142-145`). Правило
владельца: блокирует только **основной** ОКВЭД (`is_competitor_primary`, `:155`)
либо провайдер по сайту (`is_compressor_maker`). Вторичный `28.13` — не повод:
аудит показал 1116 компаний с вторичным `28.13`, и все они клиенты.

**Расхождение, которое стоит знать:** дешёвый пре-фильтр в `enrich_contacts._is_competitor`
(`:1648-1654`) НЕ использует `is_competitor_primary`, а имеет свою копию списка
`_COMP_OKVED = ('28.13','28.12')` (`:1642`) и проверяет `okved.startswith(...)`
плюс регулярку по имени. Правила дублируются в двух местах.

`[ИСПРАВЛЕНО СКЕПТИКОМ: было «Результат тот же для основного ОКВЭД» — не всегда.
`_is_competitor` (`:1650`) делает `okv.startswith('28.13')` по СЫРОЙ строке поля
`okved`, а `is_competitor_primary` (`enrich_db.py:160-166`) сперва вытаскивает код
регуляркой `\d{2}\.\d+`. Строка вида «Производство насосов 28.13» даст False у
первого и True у второго; строка «28.130…» — наоборот. Совпадают они только когда
поле начинается ровно с кода.]`
`is_competitor_primary` реально вызывается — в op `okved_recheck` (`:2772`) и
`checko_okveds` (`:2870`).

---

## 10. Модули-спутники

### `verify_company.py` (541 строка) — фундамент, а не отдельная задача

Два режима существования:

1. **Как библиотека** — `enrich_contacts.py:286` делает `import verify_company as VC`
   и использует: `VC._fetch` (GET с детектом капчи и CapMonster-Turnstile, `:350`),
   `VC._detect_block` (`:294`), `VC._norm_url` (IDNA + percent-encode, `:328`),
   `VC.UA` (`:39`), `VC._provider_call_stdlib` (`:167`), `VC._PROVIDER_MODEL` (`:143`),
   `VC._FETCH_TIMEOUT` (`:44`). Это **основной способ его использования**.
2. **Как задача раннера** `verify_company` (`job_runner.py:63`) — проверка реквизитов
   компаний по checko/rusprofile/list-org: `{"companies":[...], "source":"checko",
   "pace_min":6, "pace_max":14, "cooldown_sec":90}`. Сперва regex (`extract_regex`, `:413`),
   провайдер как фолбэк (`extract_via_provider`, `:220`).

Прокси: при импорте строится пул из `PROXY_URLV2` (список .txt) → `PROXY_URLV3` → `PROXY_URL`
и **на весь процесс устанавливается случайный** через `install_opener` (`:108-113`).
Это глобально влияет на `urllib` во всём процессе `enrich_contacts` — кроме мест,
где явно используется `_DIRECT` (`enrich_contacts.py:529`) или `_EIS_OPENER`
(`:729`, собирается лениво в `_eis_get:732-741`)
`[ИСПРАВЛЕНО СКЕПТИКОМ: было «:530» и «:722»]`.

### `browser_probe.py` (999 строк) — браузер и капчи

Playwright + Chromium. Вызывается **как библиотека** из `enrich_contacts`
(`import browser_probe as BP` — **20 мест**: `:154, 168, 261, 690, 799, 928, 1380,
1611, 2949, 3079, 3102, 3148, 3316, 3536, 3760, 3810, 4718, 4769, 4826, 5508`)
и как задача раннера `browser_probe`.
`[УТОЧНЕНО СКЕПТИКОМ: было «в 6+ местах» — фактически 20.]`

Публичное, что реально дёргается из конвейера:

* `probe(args)` (`:734`) — универсальный рендер: `url`, `wait_ms`, `solve`,
  `return_html`, `html_cap`, `screenshot`, `extract`, `click`, `dolphin_profile`,
  `dolphin_token`, `headful`, `proxy`, `proxy_var`, `proxy_prefer`, `ignore_https_errors`;
* `dolphin_start/stop/list/is_running/close_tabs` (`:404, 422, 374, 388, 429`);
* `_CF_INIT_JS`, `_YSC_INIT_JS` — перехватчики параметров Turnstile и Yandex SmartCaptcha;
* `handle_captcha(page, url, prox)` (`:664`);
* решатели: CapMonster для reCAPTCHA v2 (`:90`) и Cloudflare (`:154`),
  2captcha для Yandex SmartCaptcha (`:250`).

`main()` завершается через `os._exit(0)` (`:995`
`[ИСПРАВЛЕНО СКЕПТИКОМ: было «:996»]`) — Chromium при teardown иногда
отдаёт rc255, и раннер счёл бы задание упавшим.

### `contact_extract.py` (163 строки) — МЁРТВЫЙ в конвейере

Детерминированный экстрактор: `extract(html)` → email с ролью по local-part
(`LOCAL_ROLE`, `:31`) и по контексту (`CTX_ROLE`, `:40`), остаток («каша») →
`resolve_roles_llm` дешёвой моделью.

**Вызывающих в конвейере нет.** Единственный импорт во всём репозитории —
`seo-texts/role_model_test.py:10` (офлайн-эксперимент). Проверено по всем веткам,
включая `origin/*`: в каждой ветке `contact_extract` упоминается только там.

`[ПЕРЕПРОВЕРЕНО СКЕПТИКОМ — подтверждается. git grep по всем 7 ссылкам
(2 локальные ветки + 5 origin/*, список сверен с git ls-remote --heads origin)
даёт `import contact_extract` только в `role_model_test.py:10`; остальные попадания —
текст в docs/. Обратное направление тоже проверено: сам `contact_extract.py:139`
импортирует `gen_provider` (это упоминание в 01-generaciya-tekstov.md:628, не вызов).
Оговорка автора про `C:\sender\` на сервере остаётся в силе: git этого не покажет.]`
`enrich_contacts.py` имеет свою, менее богатую копию логики: `_harvest_from_html`
(`:421`) для mailto/JSON-LD/деобфускации и `_ROLE_RANK`/`_best_by_role` для ролей,
но роли из local-part детерминированно НЕ выводит — за ролями всегда идёт к провайдеру.

Идея модуля («91% email в mailto, 59% ролей выводятся без LLM») в конвейер не
внедрена. Это готовая точка экономии, если владелец захочет.

### `dolphin_pool.py` (201 строка) — задача раннера, без вызывающих в репозитории

Пул персистентных дельфин-браузеров: N профилей = N процессов `multiprocessing`,
каждый держит профиль открытым на всю свою пачку (стартовая цена ~15-20 с платится
раз на профиль). stdin: `{companies, dolphin_token, dolphin_profiles, workers,
per_site_wait_ms (7000), use_provider (true), write_db (true), total_timeout (1500)}`.
Пишет `enrich_stream_pool_<profile>.jsonl` и `enrich.db`.

Разрешён в раннере (`job_runner.py:69`), но **ни один скрипт в репозитории не
отправляет задание `dolphin_pool`** — запускать только вручную через `run_on_server.py`.
Логика внутри упрощённая: своя, отдельная от `enrich_one` — нет верификации сайта,
нет ЕГРЮЛ/справочников/ЕИС, `source` всегда `dolphin-pool`.

### `hh_scan.py` (141 строка) — жив, но только через один op

Парсер публичной выдачи `hh.ru/search/vacancy` (API `api.hh.ru` отдаёт 403 без
токена приложения). Достаёт работодателей из `<template id="HH-Lux-InitialState">`
(`:53`), рекурсивно ища словари, похожие на вакансию (`:64`) — чтобы не завязываться
на путь в стейте; фолбэк — разметка `aria-label="Вакансии …"` (`:88`).

`QUERIES` (`:31-38`) — 6 компрессорных запросов. `PAGES` = env `HH_PAGES`, деф. 5;
`PAUSE` = env `HH_PAUSE`, деф. 2.5 с.

Единственный вызывающий: `enrich_contacts.py:3662` (`import hh_scan as _HH`) в op
`hh_signals`. В `job_runner.ALLOW` его нет — как самостоятельная задача не запускается.
Есть CLI для ручной пробы: `python hh_scan.py [probe|archive] [pages]` (`:130-141`).

Не путать с `find_hh_compressor` (`enrich_contacts.py:666`) — это другой,
**адресный** механизм: он ищет вакансии конкретной компании через API `/vacancies`,
а `hh_scan` идёт от вакансии к компании.

### `lead_scoring.py` (248 строк) — жив, два вызывающих

Детерминированный скоринг поверх `enrich.db` + базы обзвона. Ничего не шлёт,
LLM не зовёт.

Формула (`score_all`, `:160`): сигнал 0-40 (`_signal_pts`, по свежести) + выручка 0-20
(`_revenue_pts`) + verified 0-15 (`_VERIF_PTS`) + лучшая роль email 0-15 (`_ROLE_PTS`).
Максимум 90. Исключаются `is_competitor=1` и `verified='mismatch'` (`:185-190`).

Плюс поля: `lpr` (совпадение ФИО директора базы [13] с `emails.person`, ≥2 токена),
`budget_confirmed` (ФРП/ОЭЗ-ТОР из текстов сигналов), `capex_window` (`0-30`/`31-90`/`90+`),
`buying_power` (`micro…enterprise` из выручки, сдвиг на ступень по бюджет-баллу ОКВЭД),
`verified_domain`, `call_today` (топ-`top_pct`, деф. 20%).

Вызывающие:
* задача раннера `lead_scoring` (`job_runner.py:70`) — stdin
  `{"op":"score","top_pct":20,"cap":0,"division":"","min_score":0,"base_fields":{…}}`;
* `sender/infopanel.py:399, 633` — импортирует как библиотеку (`_days_ago`, `_signal_pts`,
  `_lpr_match`) для карточки компании.

Ни один скрипт репозитория не отправляет задание `lead_scoring` автоматически.

### `dadata_client.py` (86 строк) — ЖИВАЯ библиотека трёх ops + задача раннера

`[ИСПРАВЛЕНО СКЕПТИКОМ — заголовок был «в конвейере не используется», это ЛОЖЬ.]`

`findById/party` по ИНН → реквизиты + ФИО/должность руководителя + `okveds_all`
(полный список ОКВЭД, зависит от тарифа) + emails/phones. Пауза 0.15 с между ИНН.

Разрешён как задача `dadata` (`job_runner.py:66`).

**`enrich_contacts.py` импортирует его в трёх местах** (проверено grep-ом
`import dadata_client`):

| Строка | Где | Как |
|---|---|---|
| `:2531-2532` | op `news_campaign`, ветка `dadata_fill` | `import dadata_client as _DDc; _DDc.TOKEN = _read_secret('DADATA_TOKEN')` |
| `:2741-2742` | op `okved_recheck` | `import dadata_client as _DDr; _DDr.TOKEN = …` |
| `:2801-2803` | op `checko_okveds` | `import dadata_client as _DDk; _DDk.TOKEN = …`, дальше `_DDk.lookup(inn)` (`:2810`) |

Верно только более узкое утверждение: **дефолтный путь обогащения (`enrich_one`)
его не зовёт** — `enrich_contacts._egrul_emails_by_inn` (`:609`) делает свой прямой
POST на тот же эндпоинт, беря токен через `_read_secret('DADATA_TOKEN')`.
Дублирование кода остаётся, но модуль НЕ мёртвый.

Дополнительно: `TOKEN` — модульная глобаль, читается на импорте (`:13`); `lookup()`
использует именно её (`:24`), а `main()` перезаписывает через `global TOKEN` (`:61-62`).
Как библиотеку с токеном-в-аргументе модуль использовать нельзя — и все три вызывающих
именно поэтому присваивают `_DDx.TOKEN = …` напрямую в глобаль модуля.

---

## 11. Ограничения и грабли

1. **`_domain()` портит домены, начинающиеся на `w` или точку.**
   `enrich_contacts.py:469-471`:
   ```python
   return (m.group(1) if m else '').lower().lstrip('www.')
   ```
   `lstrip` принимает **набор символов**, а не префикс. Проверено запуском самой
   функции (регулярка `^https?://([^/]+)` — без схемы возвращает пусто):
   `http://water-service.ru/` → `ater-service.ru`, `http://wtc.ru/` → `tc.ru`,
   `https://w-t-c.ru` → `-t-c.ru`, `https://www.wwww.ru/` → `ru`.
   Обычные домены с `www.` обрабатываются правильно, поэтому
   баг проявляется, когда домен (после снятия `www.`) начинается на `w`, `.` или `-`.

   `[УТОЧНЕНО СКЕПТИКОМ — где именно бьёт. Исходная формулировка «краул идёт по
   несуществующему домену» верна не всегда, зависит от того, откуда взялся сайт:]`

   * **Сайт пришёл из discovery** (лаунчеры `launch_sales_enrich`/`launch_core_chunked`
     передают `site: ''`, значит всегда этот случай) — все три функции возвращают
     уже испорченный URL `f'http://{_domain(u)}'`: list-org `:504`, DuckDuckGo `:520, :523`,
     xmlriver `:592, :597`; кэш `_site_cache_get:655` переиспользует испорченное значение
     из `companies.site`. Здесь краул действительно идёт по несуществующему домену.
   * **Сайт задан во входных данных** (`company['site']`) **или взят из базы обзвона**
     (`base_site`, `:1767-1769`) — в `crawl_contacts` уходит исходный URL, главная
     скачивается нормально. Но `dom = _domain(site)` (`:1232`) уже битый, поэтому:
     ссылки на подстраницы собираются как `f'http://{dom}{path}'` (`:1247, :1293, :1322`)
     и не открываются; «домашний» URL для атрибуции (`:1234`) тоже битый;
     `r['site'] = _domain(site)` (`:1866`) пишет битый домен в `companies.site` и
     в `stage_log('site')`.

   То есть при прогоне лаунчеров — полная потеря, при прогоне по готовым сайтам —
   теряются только подстраницы и запись в БД. Сколько записей пострадало — НЕ ИЗМЕРЕНО.
2. **`cap` не режет обычный список `companies`** — только `mass_base`/`news_enrich`
   (`:6534`, `:6610`). Лаунчеры режут порции сами (`launch_sales_enrich.py:103-104`).
3. **Компания без `name` молча выпадает** в режиме `news_enrich` (`:6609`
   `[ИСПРАВЛЕНО СКЕПТИКОМ: было «:6607»]`).
   В лаунчерах это учтено (`launch_sales_enrich.py:52-53`, `launch_core_chunked.py:41`).
4. **`division` в БД считается из `src.get('division')` → `args['division']` →
   ОКВЭД переданного словаря** (`:6722-6728`). Лаунчеры
   `launch_sales_enrich`/`launch_core_chunked` передают только `inn/name/site/ogrn`
   (`launch_sales_enrich.py:55`, `launch_core_chunked.py:44-45`) и не задают
   `division` в args (`build_args`, `launch_sales_enrich.py:78-93`) — значит для этих
   прогонов `division_for_okveds('', '')` вернёт `('', 0)`, `division=div or None` →
   `None`, а `upsert_company` пустое не пишет: колонка `division` в `companies`
   останется как была (пустой, если её не проставил другой op).
   **Проверено скептиком, подтверждается.**
5. **`verified` требует ИНН/ОГРН/телефон во входных данных.** `enrich_one:1908-1919`
   читает `company['inn']`, `company['ogrn']`, `company['phones']`. Лаунчер продажников
   передаёт `ogrn: ''` и не передаёт `phones` — остаётся только путь `inn` и
   `provider`-судья.
6. **Тонкий `source` контакта не попадает в SQLite** — см. §7.2.
7. **Стадия `site` ≠ подтверждённый сайт** — см. §6.
8. **VK ходит через один закреплённый профиль** `_VK_PIN_PROFILE` (`:792`, env
   `VK_DOLPHIN_PROFILE`, деф. `829115401`), потому что токен привязан к его IP.
   Профиль исключён из общей ротации (`_next_dolphin_profile:249`
   `[ИСПРАВЛЕНО СКЕПТИКОМ: было «:250-251»]`). На массовом
   прогоне VK сериализуется — поэтому лаунчеры ставят `no_vk_lookup: true`.
9. **`smtp_verify` требует открытый порт 25 исходящий.** Возвращает `port25_blocked`,
   если не смог (`:1548` `[ИСПРАВЛЕНО СКЕПТИКОМ: было «:1546»]`).
   Кап 6 адресов на компанию, пауза 1.2 с (`_finalize_smtp:1667-1680`).
   Статус `smtp_reject` исключает адрес из `best_for_outreach` (`:1683-1690`).
10. **`mx_ok` вызывает системный `nslookup`** через subprocess (`:1486-1498`) — на
    каждый email. На Linux/в песочнице поведение может отличаться от Windows-сервера.
11. **`_is_own_site` — чёрный список, а не белый.** `AGGREGATORS` (`:288-329`) — ~150
    подстрок, добавляются постфактум после инцидентов (dzen.ru, cbr.ru, sky.pro,
    credinform, 1prime.ru). Новый агрегатор попадёт в данные как «сайт компании»,
    пока его не добавят руками. Частичный автоматический ответ — ops `clean_shared_sites`
    и `export_core` с `shared_threshold`.
12. **Совпадающие имена глушатся широко.** `_is_own_site` использует `any(a in d ...)` —
    подстрочный матч. Например `'gis'` в списке заблокирует любой домен, содержащий
    `gis` (`registr-gis.ru`, `logistika-gis.ru`). Ложных срабатываний я не считал.
13. **Секреты берутся из трёх мест** (`_read_secret`, `:52`): env → локальный
    `runner-secrets.env` → `C:\seostat\drop\drop-storage\runner-secrets.env`.
    Для `DOLPHIN_TOKEN` выбирается **самый свежий JWT по полю `iat`** (`:55-74`) —
    иначе env службы затенял обновлённый владельцем файл протухшим токеном.
14. **`resume` собирает done-множество из ВСЕХ файлов** `stream_file*` по glob
    (`:6489`), а не только из точного имени. Переименование потока не изолирует прогон.
15. **Записи `regex-provider-fail` считаются «не done»** до 3 попыток
    (`_done_inns:2153-2187`, `resume`-ветка `:6498-6502`). Если провайдер лежит долго,
    одни и те же компании будут перекрауливаться и жечь xmlriver-квоту.

---

## 12. Что сломано или устарело

* **Дубль `op == 'base_header'`.** Первый обработчик на строке 2429, второй —
  на 3354. До второго исполнение никогда не доходит (первый делает `return`).
  Второй богаче (отдаёт `path`, `ncols`, sample-значения) — то есть работает
  **менее полная** версия. Мёртвый код: `enrich_contacts.py:3354-3371`.
* **Ветка `site_cand` в `_persist` недостижима** (`:6763-6764`): `enrich_one`
  никогда не кладёт `r['cand_site']`. **Перепроверено скептиком** — grep `cand_site`
  по `enrich_contacts.py` даёт ровно 5 попаданий (`:5963` SELECT в `stage_backfill`,
  `:6729` комментарий, `:6748` параметр `upsert_company`, `:6763-6764` сама ветка);
  нигде `r['cand_site']` не присваивается. Плюс ветка стоит в `elif` после
  `if r.get('site')` (`:6761`), а `enrich_one` при найденном сайте всегда ставит
  `r['site']` (`:1866`). Стадия `site_cand` появляется только
  из op `stage_backfill` (`:5974`)
  `[ИСПРАВЛЕНО СКЕПТИКОМ: было «(:5969, :5980)» — :5969 это общий `mark_stage`
  внутри `_m`, а :5980 — это стадия `activity`, не `site_cand`]`.
* **`contact_extract.py` — мёртвый модуль** в конвейере (см. §10). Не удалён,
  используется офлайн-тестом.
* **`launch_core_enrich.py` устарел** — сам `launch_core_chunked.py:5-14` перечисляет
  два его дефекта: шлёт все 396 компаний одним заданием и ждёт 3000 с при
  `JOB_TIMEOUT=1800`; не задаёт `extract_model`, из-за чего берётся `claude-fable-5`
  без автоподмены мёртвых моделей (та живёт только в `gen_provider.resolve_model`,
  а серверный путь `verify_company._provider_call_stdlib` шлёт модель как есть).
* **`dadata_client.py` дублирует** `enrich_contacts._egrul_emails_by_inn`; ДЕФОЛТНЫЙ
  ПУТЬ обогащения использует свою копию, но три op-а импортируют сам модуль (см. §10).
* **`_is_competitor` дублирует** `enrich_db.is_competitor_primary` (см. §9.4).
* **Ни один скрипт репозитория не ОТПРАВЛЯЕТ задания `dolphin_pool`, `dadata`,
  `lead_scoring`, `enrich_db`, `browser_probe`, `news_scan`, `verify_company`.**
  Проверено скептиком: единственные `R.submit(...)` в репозитории —
  `enrich_contacts` (`launch_sales_enrich.py:121`, `launch_core_chunked.py:68`,
  `launch_core_enrich.py:41`, `launch_refail.py:49`, `launch_top1000.py:41`,
  `mass_enrich_loop.py:34`, `preflight_panel.py:56, 59`,
  `enrich_panel/panel_core.py:916`) и `spawn_campaign` (`night_orchestrator.py:57`).
  Эти задачи запускают вручную через `run_on_server.py`.
  `[ИСПРАВЛЕНО СКЕПТИКОМ: было «задачи dolphin_pool и dadata не имеют вызывающих
  в репозитории». Формулировка смешивала «нет отправки задания» и «модуль не
  используется». `dadata_client` как БИБЛИОТЕКА жив (enrich_contacts.py:2531, 2741,
  2801), `lead_scoring` как библиотека жив (sender/infopanel.py:399, 633).
  Без вызывающих вообще — только `dolphin_pool.py`.]`
* **`hh_scan.py:26`** делает `sys.path.insert(0, r'C:\sender\server')` — жёсткий
  Windows-путь, при запуске не на сервере просто бесполезен (не падает).
* **VK-путь регулярно не работает.** В коде явные следы: «VK токен без прав»
  (`:3860`), ошибки собираются «громко» в `_vk_last_err` (`:857`
  `[ИСПРАВЛЕНО СКЕПТИКОМ: было «:865» — там присвоение внутри обработчика]`), `tail_stream`
  отдельно считает `vk_ok`/`vk_err`/`vk_err_top` (`:3959-3968`). Насколько он
  работает сейчас — по коду не установить.
* **Провайдерский шлюз периодически «отдаёт только ping-кадры»** — по
  `ENRICH-SALES-BASE-PROMPT.md:145-150` для `claude-fable-5` и `claude-opus-5`.
  Первым делом при зависших генерациях — op `provider_probe`.

---

## 13. Быстрый чеклист для новой сессии

```bash
# 1. Что вообще накоплено
run_on_server.py enrich_db      '{"op":"stats"}'
run_on_server.py enrich_contacts '{"op":"stage_report"}'

# 2. Идёт ли прогон и что в нём
run_on_server.py enrich_contacts '{"op":"tail_stream","file":"enrich_sales.jsonl","n":10}'
run_on_server.py enrich_contacts '{"op":"tail_stream","file":"enrich_core2.jsonl","n":10}'

# 3. Ключи на месте?
run_on_server.py enrich_contacts '{"op":"envcheck"}'
run_on_server.py enrich_contacts '{"op":"provider_probe","models":["claude-haiku-4-5"]}'

# 4. Стоп массового прогона — положить на дроп файл-флаг
#    mass_stop.flag   (для mass_base)
#    news_stop.flag   (для news_enrich)
#    zakupki_stop.flag (для zakupki_mass)
```

Имена потоков, которые реально используются лаунчерами:
`enrich_sales.jsonl` (продажники), `enrich_core2.jsonl` (ядро центробежных),
`enrich_stream_mass.jsonl` (`mass_enrich_loop`), `enrich_stream.jsonl` (дефолт),
`zakupki_stream.jsonl` (op `zakupki_mass`), `enrich_stream_pool_<id>.jsonl` (`dolphin_pool`).

---

## 14. Что не проверено

Раздел обязательный. Всё ниже — то, чего я НЕ подтверждал.

**Не проверено вообще (нет доступа):**

1. **Живая `enrich.db`.** Я не выполнял ни одного запроса к ней. Всё про
   `phone_contacts`, `companies.revenue_rub`, `companies.shared_phone`, реальные
   объёмы, реальные значения `verified`/`source` — только из чтения кода.
   Утверждать «такой таблицы/колонки нет» на основании этого документа НЕЛЬЗЯ.
2. **Живой `C:\sender\obzvon-index.db`** и структура базы обзвона CSV.
   Индексы колонок (ИНН=1, кратк.имя=5, полн.имя=6, адрес=9, регион=10, директор=13,
   ОКВЭД=16, ВсеОКВЭД=17, телефоны=18, сайт=20, выручка=34) взяты из кода
   (`_base_pick:2099`, `_base_index:2054`, `lead_scoring._base_fields:129`), сам файл
   я не открывал.
   `[ИСПРАВЛЕНО СКЕПТИКОМ: было «_base_pick:2094» — на :2094 докстринг, сама строка
   индексов на :2099. Индексы сверены построчно и совпадают. Уточнение: в
   `_base_index:2054` нет ни директора [13], ни ВсеОКВЭД [17] — они только в
   `_base_pick:2099` (директор+ВсеОКВЭД), `lead_scoring:129` (директор) и
   `hidden_leads:2677`.]`
3. **Ни один прогон не запускался** — ни через раннер, ни локально. Запрещено
   правилами задачи (боевое обогащение на сервере).
4. **Работоспособность источников на сегодня**: xmlriver (есть ли каналы), dadata
   (тариф), VK-токен, дельфин-профили, CapMonster/2captcha балансы, порт 25.
5. **Числа из комментариев и `.md`-файлов** (286 компаний, 3 сайта от DDG, 1116
   компаний с 28.13, 649 скрытых лидов, 91%/59% в `contact_extract`, 936 компаний
   с checko-контактами, 3302 удалённых телефона) — это чужие замеры, я их
   не воспроизводил.

**Прочитано частично:**

6. **`enrich_contacts.py` прочитан не построчно.** Полностью разобраны:
   строки 1-700, 1100-2230, 6381-6814. Ops из диапазона 2230-6380 разобраны по
   заголовочным комментариям и точечным чтениям; тела `news_campaign` (2439-2592),
   `hidden_leads`, `centrifugal_*`, `export_core` (полностью — 460 строк),
   `ingest_noinn`, `resolve_leaked`, `panel_*` я читал выборочно.
   Описания этих ops в §4 могут быть неточны в деталях аргументов.
7. **`browser_probe.py`**: прочитаны строки 1-120 и 734-999. Внутренности решателей
   капч (120-734) — по сигнатурам и именам, не построчно.
8. **`find_opo_signal`** (`:1021-1107`) прочитан частично.
9. **`enrich_panel/`** не разбирался — это отдельная область. Утверждение «панель
   строит задания для op `etp_fit`/`checko_okveds`/…» основано на grep по
   `panel_core.py:526-586`, не на чтении модуля.
10. **`news_scan.py` (1567 строк)** не читался. Он импортируется в ops `hh_signals`
    (`dadata_suggest`, `division_of`), `resolve_test`, `ingest_noinn`. Как именно
    работают эти функции — не проверял.
11. **`sender/infopanel.py`** просмотрен только вокруг импорта `lead_scoring`.

**Утверждения, которые скептику стоит перепроверить первым делом:**

12. «`contact_extract.py` мёртв в конвейере» — я проверил grep по всем локальным и
    `origin/*` веткам; единственный импорт — `role_model_test.py:10`. Но на сервере
    в `C:\sender\` может лежать версия кода, которой нет в git.
13. «Дубль `base_header` на строке 3354 недостижим» — верно при линейном чтении
    `main()`, все ops завершаются `return`. Проверить можно вызовом
    `{"op":"base_header"}`: если в ответе НЕТ полей `path`/`ncols`/`sample` —
    отработал первый (строка 2429), значит второй действительно мёртв.
14. «Тонкий `source` контакта не доезжает в SQLite» — проверяется одним запросом
    к живой БД: `SELECT DISTINCT source FROM emails`. Если там встречаются
    `own-site:staff`, `egrul:dadata`, `serp-card:yandex` — значит либо код на сервере
    отличается от репозитория, либо их записал другой компонент.
    `[РАЗОБРАНО СКЕПТИКОМ, см. §7.2 — третий вариант оказался верным и без запроса
    к БД: тонкие метки в emails/phone_contacts писали другие компоненты, а
    add_email не затирает source при ON CONFLICT. Формулировка §7.2 сужена.]`
15. «Баг `_domain` с `lstrip('www.')`» — сам факт я воспроизвёл запуском функции.
    Не проверял, СКОЛЬКО записей в БД реально пострадало (запрос:
    компании, у которых `site` не резолвится / начинается с обрезанного токена).
    `[СКЕПТИК: баг воспроизведён повторно на самой функции; в §11 п.1 уточнено,
    где именно он бьёт. Масштаб по БД по-прежнему НЕ ИЗМЕРЕН.]`
16. «`_SEM_LISTORG`/`_SEM_SEARCH` — главный тормоз» — это утверждение автора
    `launch_sales_enrich.py:59-76` со ссылкой на замер, которое я подтвердил только
    по коду (sleep внутри `with`). Сам замер не повторял.
    `[СКЕПТИК: механика перепроверена — Semaphore(1) хардкодом на :17-18, sleep
    внутри `with` на :1756-1758 и :1760-1762, второй sleep 6..14 с на :497.
    Замер (286 компаний) — по-прежнему чужой, НЕ воспроизводился.]`

---

## 15. Ревизия скептика (что перепроверено и что исправлено)

Проведена вторым агентом по коду на том же дереве. Живая БД и живой прогон
по-прежнему НЕ трогались — все запреты §14 остаются в силе.

**Найденные и исправленные ошибки (по убыванию значимости):**

1. §10, §12 — «`dadata_client.py` конвейер не импортирует / задача без вызывающих».
   ЛОЖЬ: `enrich_contacts.py:2531, 2741, 2801` импортируют модуль в ops
   `news_campaign`(`dadata_fill`), `okved_recheck`, `checko_okveds`. Раздел переписан.
2. §7.2 — «в `emails.source` тег задания» без оговорок. Сужено: `add_email`
   (`enrich_db.py:308-319`) не обновляет `source` при `ON CONFLICT`, и тонкие метки
   в живой БД писали другие компоненты (см. `ENRICH-SALES-BASE-PROMPT.md:155,157`,
   `obzvon-centro/build_centrifugal_db.py:143-166`).
3. §11 п.1 — последствие бага `_domain` описано неточно по месту. Уточнено: бьёт
   в discovery-возвратах (`:504, :520, :523, :592, :597`) и в кэше (`:655`), а при
   заданном сайте ломаются только подстраницы и запись в БД.
4. §9.1 — «не трогаем ничего» при уже подтверждённом `verified`. На деле не трогаются
   только `verified/site/cand_site`; остальные поля перезаписываются.
5. §5.4 — приоритет `division`: `args['division']` ПЕРЕБИВАЕТ ОКВЭД, а не наоборот.
6. §9.4 — «результат тот же для основного ОКВЭД» у `_is_competitor` и
   `is_competitor_primary`. Не всегда: первый матчит `startswith` по сырой строке,
   второй сперва вынимает код регуляркой.
7. §9 — неверные строки читателей `revenue_rub` (:161, не :129) и `phone_contacts`
   (:178, не :137) в `build_contacts_xlsx.py`; списки читателей были неполны.
8. Ссылки файл:строка (сдвиги 1-8 строк), исправлены точечно: §3.1 (`:1358-1361`,
   `:1378-1401`), §3 пп.11-13, §3.3 (`:1927/:1928/:1951`), §6 и §12 (`site_cand`
   в `stage_backfill` — `:5974`), §8 (`:497`), §10 (`os._exit` — `:995`,
   `_DIRECT` — `:529`, `_EIS_OPENER` — `:729`), §11 пп.3, 8, 9, §12 (`_vk_last_err` —
   `:857`), §14 п.2 (`_base_pick:2099`).
9. §10 — «`browser_probe` импортируется в 6+ местах» → фактически 20.

**Перепроверено и ПОДТВЕРЖДЕНО (ошибок нет):**

* «61 значение `op`» — пересчитано независимо: 60 сравнений `args.get('op') ==`
  (из них дубль `base_header`) + один `args.get('op') in ('centrifugal_inns',
  'centrifugal_export')` на `:3372` = 59 + 2 = 61.
* Дубль `op == 'base_header'` (`:2429` и `:3354`), второй богаче и недостижим —
  оба обработчика прочитаны, у первого `return` на `:2438`.
* `contact_extract.py` мёртв в git по всем 7 веткам (сверено с `git ls-remote
  --heads origin`); оговорка про `C:\sender\` остаётся.
* Ветка `site_cand` в `_persist` недостижима: `r['cand_site']` нигде не присваивается,
  и ветка стоит в `elif` после `if r.get('site')`.
* `division` останется пустым для прогонов лаунчеров.
* `_SEM_LISTORG`/`_SEM_SEARCH` = `Semaphore(1)` хардкодом, `sleep` внутри `with`.
* `dolphin_pool.py` — единственный модуль области вообще без вызывающих
  (ни импорта, ни отправки задания).
* Все строки таблицы ops §4 (60 значений) сверены с `grep args.get('op')` — совпали.
* Все строки таблиц §5.1-5.4 сверены — совпали.
* Схема `_SCHEMA` (`enrich_db.py:24-48`), миграции (`:212-219`), 77 кодов
  `OKVED_DIRECTIONS`, `PRIMARY_COMPETITOR_OKVEDS` (`:142-145`), объёмы файлов
  (6814/513/541/999/163/201/141/248/86 строк) — совпали.
* `job_runner`: allowlist `:62-73`, `JOB_TIMEOUT=1800` `:58`, `WORKERS` `:233`,
  `_SEM_HEAVY`/`RUNNER_HEAVY` `:234`, `_is_heavy` `:239-246`, stdin-JSON `:204` —
  совпали. `_is_heavy` действительно true для заданий обоих лаунчеров.
* `AGGREGATORS` — 162 элемента (155 уникальных), `'gis'` в списке реально есть
  (`:302`), пример из §11 п.12 корректен.

**Что скептик тоже НЕ проверял:** живую `enrich.db`, `obzvon-index.db`, ни одного
прогона; `news_scan.py`, `enrich_panel/`, внутренности решателей капч; чужие замеры
(286 компаний, 936 checko-контактов, 3302 телефона, 1116 с 28.13, 649 скрытых лидов,
91%/59%) — не воспроизводились.
