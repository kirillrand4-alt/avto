# Рассыльщик: полный путь письма от новости до отправки

Документ собран чтением исходников: `/home/user/work/src/tree/sender/sender/` (121 файл боевого рассыльщика), `/home/user/work/rassyl/` (news_scan.py, newsco_op.py), дампа живой базы `/home/user/work/dump/sender-dump-3s.json.gz`. Все ссылки вида `файл:строка` проверены по коду. Даты и цифры в скобках - из комментариев самих авторов кода.

---

## 0. Схема пути

```
                         ДОБЫЧА ПОВОДА (сервер владельца, C:\sender\server)
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ A. news_scan.py            B. newsco_op.py                               │
   │    «широкий невод»            «переворот: от компании»                   │
   │    RSS/xmlriver/VK/hh/        обзвон-база -> имя -> xmlriver -> статья    │
   │    zakupki/ФРП                -> механическая привязка (инн/имя/ядро)    │
   │    -> fable: капекс?          -> ноль LLM-вызовов                        │
   │    -> dadata: имя -> ИНН      -> пачка .json.gz -> разбор -> apply        │
   └──────────────┬──────────────────────────────┬────────────────────────────┘
                  │                              │
                  ▼                              ▼
        ┌───────────────────────────────────────────────────┐
        │ enrich.db  (companies | signals | emails |         │  <- КЛЮЧ ВСЕГО: ИНН
        │            donors | seen_news | people | stage_log)│
        └───────────────┬───────────────────────────────────┘
                        │  + база обзвона (161 761 юрлицо, CSV -> obzvon-index.db)
                        ▼
        ┌───────────────────────────────────────────────────┐
        │ company_card.py  card(inn)  «вбил ИНН - получил всё»│
        │ infopanel.py     build_panel(inn=..., email=...)   │
        └───────────────┬───────────────────────────────────┘
                        │
     news-campaign-master.csv (сборка вручную/скриптом сессии)
                        │
                        ▼
        importer.py  ->  recipients (segment='новостные')
                        │
                        ▼
        ai_quota.py  «кому писать сегодня»: квота дня -> кандидаты по hotness
                        │  _request(): новость + город + роль + выручка + оборудование
                        ▼
        ai_letter.py  генерация: 3 варианта -> судья -> гейт -> верификатор ->
                      до 3 кругов доработки + принудительный -> брак или письмо
                        │      (провайдер: review_lenses.default_caller, claude-fable-5)
                        ▼
        confirm.py   очередь подтверждений (confirm_reviews, status=pending)
                     + messages(status=pending_review) + ai_letter_log
                        │
                        │   ЧЕЛОВЕК: approve / edit / skip / stoplist
                        ▼
        sender.py    выбор ящика -> заслоны -> подпись -> List-Unsubscribe -> SMTP
                     (orchestrator.tick() - автоматический путь, сейчас на холде)
```

Замер по дампу живой базы (`sender-dump-3s.json.gz`): recipients 582 (из них segment='новостные' 576), ai_letter_log 452 (ok 427, brak 25), confirm_reviews 458 (pending 271, skipped 153, sent 34), messages 470 (pending_review 427, sent 35), send_log 36. То есть до реальной отправки из 452 сгенерированных писем дошли 35.

---

# ЧАСТЬ 1. ДОБЫЧА ПОВОДА

## 1.1 `news_scan.py` - широкий новостной невод

`/home/user/work/rassyl/news_scan.py`, 1861 строка.

**1. ВХОД.** Не ИНН. JSON на stdin (`news_scan.py:1301-1304`). Ключи: `collectors` (google, regional, xmlriver, zakupki, hh, frp, vk, browser, rss), `queries` либо `industries`+`regions`, `days` (по умолчанию 90), `max_items` (6), `zakupki_keywords`, `hh_queries`, `hh_area` (113 = Россия), `feeds`, `vk_token`, `vk_keywords`, `dadata_token`, `enrich`, `enrich_max`, `pace_min/pace_max` (`news_scan.py:20-26`, `1210-1216`, `1635-1639`). Отдельные режимы-переключатели в том же JSON: `sweep`, `vk_sweep`, `conductor`, `rss_discover`, `site_crawl`, `re_enrich`, `seen_clear_after`, `collect_only`, `yandex_diag`.

**2. ВЫХОД.**
- stdout JSON `{events:[...], summary:{...}}` (`news_scan.py:1849-1860`);
- durable-поток `news_stream.jsonl` рядом со скриптом, append+flush+fsync на каждое событие (`news_scan.py:1737-1752`);
- `enrich.db` через `enrich_db.EnrichDB`: `companies` (upsert_company: inn, name, division, okved, region), `signals` (add_signal: inn, source, event_type, what, sum, source_url, hotness, ts), `emails` (add_email для ЕГРЮЛ-адресов из dadata, role='юрзначимый (ЕГРЮЛ)'), `donors` (bump_donor по домену источника) - `news_scan.py:1753-1783`.
- Ключ привязки: **ИНН**, полученный из названия компании через `dadata_suggest` (`news_scan.py:1156-1208`). Событие без ИНН НЕ теряется, но живёт только в jsonl (`news_scan.py:1734-1736`, счётчик `leads_no_inn_in_jsonl`).

Схема `enrich.db` (проверена по `/home/user/work/panel/enrich_snapshot.db`):
```sql
companies(inn PK, name, division, okved, region, pxr, site, activity,
          is_competitor, verified, best_email, phones, updated_at)
signals  (inn, source, event_type, what, sum, source_url, hotness, ts,
          updated_at, UNIQUE(inn, source, what))
emails   (inn, email, role, person, mx_ok, source, updated_at, UNIQUE(inn,email))
donors   (domain PK, rss, rss_items, event_count, status, first_seen, updated_at)
seen_news(k PK, ts)
```

**3. ГДЕ ЖИВЁТ.** Сервер владельца, запуск как задача раннера `task=news_scan`: «сайты компаний/гиперлокал за Cloudflare/капчей - только СЕРВЕР (РФ-IP + CapMonster). Поэтому боевой прогон - задача раннера, не песочница» (`news_scan.py:17-19`). Тянет соседние серверные модули `verify_company`, `enrich_contacts`, `browser_probe`, `enrich_db` (`news_scan.py:33-42`) - их в песочнице нет.
Нужны: `DADATA_TOKEN`, `XMLRIVER_USER`, `XMLRIVER_KEY`, `VK_TOKEN`, `DROP_URL`, `DROP_TOKEN`, `JOB_SECRET` (подпись самочейнящихся джобов, `news_scan.py:68-107`), `PROXY_URLV2` (пул мобильных IP для RSS, `news_scan.py:338-370`), ключ провайдера внутри `verify_company._provider_call_stdlib`.

**4. СКОЛЬКО СТОИТ.** Считает по НОВОСТЯМ, не по компаниям, поэтому «на одну компанию» цифры в модуле нет.
- 1 вызов провайдера (`extract_event`, промпт ~400 токенов) на каждую новость, дожившую до классификации, модель жёстко `claude-fable-5`: «haiku на этой задаче даёт is_capex=false на явные капекс-события (терялись 99% событий)», оценка авторов «~$15-20/полный прогон» (`news_scan.py:1642-1646`, `1058-1088`);
- xmlriver - платная выдача, 25 руб/1000 запросов (счётчик и ценник в `newsco_op.py:99-101`, `504-505`);
- dadata: до 6 вариантов имени x count=3, с досрочным выходом при score>=2 (`news_scan.py:1104-1136`, `1197-1199`);
- 1 HTTP GET полного текста статьи на каждый элемент, прошедший дедуп (`fetch_article`, `news_scan.py:727-747`);
- параллелизм провайдера 12 потоков, потолок 64 (`news_scan.py:1785`).

**5. ЧЕМ ОГРАНИЧЕН** (строками кода):
- `max_items = int(args.get('max_items', 6))` (`1212`) и срезы `[:max_items]` в каждом коллекторе: `446`, `468`, `531`, `544`, `591`, `612`, `642`, `977`, `1031`;
- zakupki: `&recordsPerPage=_10` (`590`);
- hh: `period = min(int(days), 30)` - «hh отдаёт максимум 30 дней» (`602`);
- RSS-доноры: `cap_feeds=60` (`997`);
- текст статьи классификатору: `FULLTEXT_CAP = 20000` (`711`);
- капекс-предфильтр по ЗАГОЛОВКУ только для лент regional/google/xmlriver (`1264-1271`) - «медиа-ленты это firehose»;
- только РФ: событие с `country` не «рф/росс/russia» отбрасывается (`1683-1686`);
- `ICP_OKVED` - 39 разделов (`56-62`) - ставит только флаг `icp_fit`, отсева нет;
- dadata: `if not best or best[0] < 1: return None` (`1200-1201`) - «лучше лид без ИНН, чем ЧУЖОЙ ИНН тёзки»; `confidence='high'` только при score>=2;
- sweep: `chunk = int(args.get('chunk', 120))` (`1621`), VK-sweep `chunk` 6 локаций x 10 фраз (`1593`, `143-150`);
- `enrich_max = int(args.get('enrich_max', 0))` - 0 значит без лимита (`1636`, `1795-1798`);
- кросс-прогонный дедуп `seen_news` ДО провайдера (`1679-1682`) - повторно новость не разберётся, пока не почистить.

**6. КАК ЗАПУСТИТЬ ПО ОДНОЙ КОМПАНИИ.** По ИНН - **нельзя**: ИНН в этом модуле появляется в самом конце, из названия в тексте новости. По ИМЕНИ - можно, одним запросом:

```bash
echo '{"collectors":["xmlriver"],
       "xmlriver_queries":["\"ХИМПРОМ\" (новый цех OR модернизация OR запуск)"],
       "days":180,"max_items":5,"write_db":false,"enrich":false}' \
  | python news_scan.py
```
Если новость уже видели, её съест дедуп `seen_news`; сброс - отдельным прогоном `{"seen_clear_after":"2026-07-01"}` (`news_scan.py:1495-1509`).

---

## 1.2 `newsco_op.py` - «новости ОТ компании» (переворот невода)

`/home/user/work/rassyl/newsco_op.py`, 805 строк. Идея владельца 23.07: «не от события, а от юрлица» (`newsco_op.py:1-12`).

**1. ВХОД.** Подкоманда + флаги, не ИНН. Команды: `targets`, `probe [--n N]`, `serp --off N --lim M [--min --max --tag --engines --articles --workers --budget]`, `measure`, `freshtest`, `abbrtest`, `pack --tag`, `apply --file`, `overlap`, `report` (`newsco_op.py:662-780`). Фактический вход `serp` - файл целей `C:\seostat\drop\newsco_targets.jsonl`, который строится из CSV базы обзвона (`построить_цели`, `166-246`).

**2. ВЫХОД.**
- durable-поток `C:\seostat\drop\newsco_stream.jsonl` (запись + flush + fsync на каждую компанию, `495-499`), запись: `{inn, имя, krat, poln, город, регион, оквэд, сайт, выручка, запрос, выдача, чистых, капекс_кандидатов, статьи[...], тег, ts}`;
- пачка `drop-storage/newsco_batch_<тег>.json.gz` (`520-534`), в каждой статье: `{url, title, passage, дата, возраст_мес, привязка{...}, наше, текст[:7000], символов}`;
- `apply` пишет в `enrich.db`: `signals` с `source='новости от компании'` и меткой даты в тексте (`561-580`), `people` (`581-591`), журнал `newsco_applied.jsonl`;
- ключ привязки: **ИНН**, известен заранее из базы, резолвить нечего.

**3. ГДЕ ЖИВЁТ.** Только сервер владельца: пути зашиты жёстко - `sys.path.insert(0, r'C:\sender\server')` (`34`), `ДРОП = r'C:\seostat\drop'`, `ХРАН = drop-storage`, `ПОТОК`, `ЦЕЛИ` (`37-40`). Нужны `XMLRIVER_USER`, `XMLRIVER_KEY` (`96-97`) и соседние модули `news_scan`, `enrich_contacts`, `enrich_db`.

**4. СКОЛЬКО СТОИТ (это самый дешёвый модуль пути).**
- ровно **1 оплаченный xmlriver-запрос на компанию** на движок (`сбор` -> `серп`, `434-437`), 0,025 руб;
- до 3 скачиваний статей на компанию (`for x in капекс[:статей]`, `461`, `статей=3`);
- **ноль вызовов LLM**: капекс определяется регуляркой `_КАПЕКС` (`125-137`), «наше оборудование» - регуляркой `_НАШЕ` (`139-144`), привязка - механически (`388-403`). Провайдер тут не участвует вообще;
- время: 6 воркеров, бюджет прогона 1150 секунд по умолчанию (`683`), в `measure` - 1000 на три страта (`692`).

**5. ЧЕМ ОГРАНИЧЕН:**
- `топ = взято[:30000]` (`231`) - целей не больше 30 000, отсортированных по выручке (колонка 34 CSV);
- `return out[off:off + lim]` (`267`), `--lim` по умолчанию 50 (`680`);
- `--articles 3`, `--workers 6`, `--budget 1150` (`682-683`);
- `'текст': (текст or '')[:7000]` (`488`) - в пачку уезжает 7000 символов статьи, не больше;
- мусорные домены (checko, rusprofile, hh, zakupki, тендерные площадки, wiki и т.д.) режутся до всего остального: `_МУСОР_ДОМЕН` (`146-157`), `мусорный()` (`160`);
- имя запроса: аббревиатуру («ТСМ») заменяет полное имя (`имя_для_запроса`, `61-77`), вложенные кавычки разбираются от первой до последней (`ядро_имени`, `79-95`);
- `быстрый_фетч` без капча-фолбэка: «одна страница съедала минуты» (`369-376`);
- резюм по потоку: компании с этим `тег` пропускаются повторно (`414-423`).

**УРОВНИ ПРИВЯЗКИ НОВОСТИ К КОМПАНИИ** - это ядро модуля, `newsco_op.py:388-403`:

| уровень | чем доказан | код |
|---|---|---|
| `инн` | ИНН компании буквально найден в тексте страницы | `инн_есть = bool(инн) and инн in t` |
| `полное_имя` | все слова полного наименования (>=2 слова, по префиксу 6 символов) есть в тексте | `полное_есть = ... all(w[:6] in t ...)` |
| `ядро` | все содержательные токены ядра имени (>=4 символов, префикс 5) есть в тексте | `попало == len(ток)` |
| `частично` | попал хотя бы один токен | `elif попало` |
| `нет` | не попал ни один | |
| `нет_текста` | страница не скачалась | ранний возврат |

В счётчик `привязка_ок` идут только `инн`, `полное_имя`, `ядро` (`480-481`). Комментарий автора: «инн_на_странице - сильнейшее; полное_имя - сильное; ядро - слабое (тёзки!)».

Отдельно живёт защита первоисточника в широком неводе: `_src_confirms` (`news_scan.py:749-776`) возвращает `match | no-match | fetch-fail` и при не-`match` ссылка-первоисточник отбрасывается, лид остаётся на VK-посте (`news_scan.py:1692-1703`).

Честный замер качества привязки лежит рядом: `/home/user/work/RASSYLSHIK-otchet-3-sessii.md` - проверены все 66 пар «компания - новость» из `news-campaign-master.csv`, под подозрением 24, подтверждённых мисматчей 16.

**6. КАК ЗАПУСТИТЬ ПО ОДНОЙ КОМПАНИИ.** Штатно **нельзя** - модуль написан под пачку (off/lim по файлу целей). Рабочий обход из двух шагов, без правки кода:

```bat
rem 1) подложить ОДНУ цель (формат строки - как пишет построить_цели, newsco_op.py:216-225)
> C:\seostat\drop\newsco_targets.jsonl echo {"inn":"2124009521","krat":"ПАО \"ХИМПРОМ\"","poln":"ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО \"ХИМПРОМ\"","city":"Новочебоксарск","region":"Чувашия","okved":"20.13","site":"","rev":0,"rev24":0,"ssc":0}

rem 2) прогнать ТОЛЬКО её; --rebuild НЕ указывать, иначе цели перестроятся из базы (674-676)
python C:\sender\server\newsco_op.py serp --off 0 --lim 1 --tag one --articles 3 --budget 300
```
Стоимость такого прогона: 1 запрос xmlriver (0,025 руб) + до 3 GET. Результат - в `newsco_stream.jsonl` и `drop-storage/newsco_batch_one.json.gz`.

---

## 1.3 `news_funnel_audit.py` / `news_reconcile.py` - счётчики воронки

**1. ВХОД.** Ничего. Оба читают файлы по зашитым путям.
**2. ВЫХОД.** Один JSON в stdout, в БД не пишут. `news_funnel_audit.py` - доноры, сигналы по source, сигналы с ИНН и без, пересечение с companies/emails, конкуренты, division, hotness, свежесть 30/90/180 дней, event_type. `news_reconcile.py` - точная сверка «ИНН-с-поводом -> куда делись»: в базе обзвона, конкурент, без email, в кампании segment='новостные', и главное `НЕ_в_кампании_и_не_конкурент` с разбивкой «из них с email (потенциально упущены)».
**3. ГДЕ ЖИВЁТ.** Сервер: `EN = r'C:\sender\enrich.db'`, `BASE = r'C:\seostat\drop\drop-storage\obzvon_all_2026-07-16.csv'`, `SDB = r'C:\sender\sender.db'` (`news_reconcile.py:4-6`).
**4. СКОЛЬКО СТОИТ.** Ноль вызовов провайдера, ноль сети. Секунды.
**5. ЧЕМ ОГРАНИЧЕН.** Пути зашиты константами, аргументов нет; `csv.field_size_limit(2**22)`; сегмент кампании захардкожен `segment='новостные'` (`news_reconcile.py:33-35`).
**6. ПО ОДНОЙ КОМПАНИИ.** Нельзя - это агрегатные счётчики по всей базе. Для одной компании эквивалент - карточка (см. 2.2/2.3).

---

# ЧАСТЬ 2. ЧТО ЗНАЕМ О КОМПАНИИ (это и есть «вбил ИНН - получил всё»)

## 2.1 `company_card.py` + `tools/build_obzvon_index.py`

**1. ВХОД.** `build_company_card(inn)` / `CompanyCards.card(inn)` - **чистый ИНН, одна компания** (`company_card.py:378-426`, `469-482`). Индекс строится один раз: `build_obzvon_index.py --out obzvon-index.db` (CSV 663 МБ, 161 761 юрлицо, стримится с дропа, на диск ложится только SQLite; `tools/build_obzvon_index.py:1-16`).

**2. ВЫХОД.** dict, тот же JSON уходит в панель подтверждения:
`inn, division (kc|meyer|None), division_source, division_guess, obzvon_available, obzvon{36 полей базы}, enrich{company, emails, signals, available}, contacts{emails[], phones[]}, site_view{site, cand_site}, fin{god_otch, revenue, profit, capital, ssch, revenue_rub}, priority{priority_total, priority_max, pxr}, product{equip_by_okved, equip_categories, found_okveds, calc_comment}`.
Правила приоритета при конфликте (`company_card.py:7-18`): направление - ТОЛЬКО из базы обзвона, enrich его не перебивает; контакты - enrich приоритетнее базы; телефоны - оба набора с пометкой источника; выручка/ОКВЭД/директор - из базы; сайт из enrich только при `verified in (inn, ogrn, phone, provider)`.

**3. ГДЕ ЖИВЁТ.** Сервер (панель). Конфиг: `obzvon.index_path`, `obzvon.enrich_db`; env-фолбэк `ENRICH_DB` (`company_card.py:298`). Для сборки индекса нужны `DROP_URL`, `DROP_TOKEN`.

**4. СКОЛЬКО СТОИТ.** Ноль вызовов провайдера. Два SQLite-запроса на компанию + LRU-кэш на 512 карточек (`company_card.py:433-437`). Миллисекунды. Разовая сборка индекса - минуты на 663 МБ.

**5. ЧЕМ ОГРАНИЧЕН.** `cache_size: int = 512` (`435`); `equip_for_okved` ищет `LIMIT 1` по префиксу кода (`251`); поля длиннее лимита обрезаются с многоточием (`186`); нет индекса - `cards.active=False`, гейт направлений спит, и на боевом это означает «направления пустые и рассылка стоит» (`wiring.py:60-66`).

**6. КАК ЗАПУСТИТЬ ПО ОДНОЙ КОМПАНИИ.** **Да, штатно.** Это единственная готовая ручка «вбил ИНН»:
```bash
python3 -c "
from sender.company_card import CompanyCards
import json
c = CompanyCards(index_path='/path/obzvon-index.db', enrich_db_path='/path/enrich.db')
print(json.dumps(c.card('2124009521'), ensure_ascii=False, indent=1))"
```

## 2.2 `infopanel.py` - карточка оператора по ИНН

**1. ВХОД.** `build_panel(inn=..., email=..., letter_subject=..., letter_body=..., card=..., store=..., signature=...)` (`infopanel.py:297-315`). Отдельно `load_enrich_lead(inn, db_path=..., email=...)` - только ИНН (`infopanel.py:59-88`).

**2. ВЫХОД.** Один JSON, который одинаково рендерят CLI и веб-панель. Верхние ключи (проверено по `panel_json` реально отправленного письма в дампе): `stop_flags, scoring, signal, emails, news_events, company_full, contact, company, letter, kb, compliance, history, reserved, actions, should`. Внутри: `scoring.parts{revenue 0-20, role 0-15, signal 0-40, verified 0-15}`, `contact.lpr`, `company.division_badge`, `company.why_equipment`, `company_full.reg{ОГРН, КПП, адрес, директор, все ОКВЭД}`, `company_full.fin`, `company_full.product.equip_categories`, `compliance.attribution_ok`.

**3. ГДЕ ЖИВЁТ.** Сервер. Читает `enrich.db` строго read-only (`file:{path}?mode=ro`, `infopanel.py:70`), путь из аргумента или env `ENRICH_DB` (`66`); подтягивает `server/lead_scoring.py`, `server/enrich_db.py`, `email-assistant/kb_retrieve.py`, `kb/snyatye-verdict.json` (`infopanel.py:1-16`, `28-34`).

**4. СКОЛЬКО СТОИТ.** Ноль вызовов провайдера, только SQLite.

**5. ЧЕМ ОГРАНИЧЕН.** Сигналы сортируются `hotness DESC, LENGTH(what) DESC, ts DESC` (`infopanel.py:80-86`); `catch_all` честно помечен «не проверялось» (`reserved`); провенанс контакта берётся только из `emails.source/source_url`, а не из `companies.verified` - разбор бага 27.07 прямо в коде (`infopanel.py:92-106`); метки прогонов (`refail`, `mass`, `panel-run`) затирают настоящий канал появления адреса, канал восстанавливается из `source_url` (`infopanel.py:135-152`).

**6. ПО ОДНОЙ КОМПАНИИ.** **Да**: `load_enrich_lead(inn)` - чистый ИНН; `build_panel(inn=..., email=..., letter_subject='', letter_body='')` даёт полную карточку без письма.

---

# ЧАСТЬ 3. ЗАВОД ПИСЕМ

## 3.1 `importer.py` - лиды становятся получателями

**1. ВХОД.** Путь к CSV. Автодетект кодировки и разделителя, автодетект колонок по алиасам: `email, inn, company_name, okved, segment, contact_name, source, priority_max, priority_total, pxr, region, tz` (`importer.py:38-57`, `122-140`). Фактический файл прошлой кампании - `/home/user/work/rassyl/news-campaign-master.csv`: 66 строк, колонки `inn;name;city;division;division_src;in_base;best_email;verified;phones;all_contacts;news_event;news_what;news_url;news_ts;hotness;activity;checko_okveds_all;база:*` (36 полей базы обзвона с префиксом `база:`).

**2. ВЫХОД.** Таблица `recipients`: `id, inn, email, domain, company_name, okved, segment, bitrix_id, contact_name, mx_provider, valid_status, catch_all, role_based, disposable, source, extra_json, created_at, updated_at, priority_max, priority_total, pxr, region, tz`. Ключ привязки - **email** (дедуп через upsert), плюс `inn` для карточки и заслонов. Новостной контекст едет в `extra_json`, пример из дампа: `{"city":"Новочебоксарск","equipment":"Генераторы азота | Генераторы кислорода","news_object":"строительство метанолового завода мощностью 1 млн тонн в год"}`.

**3. ГДЕ ЖИВЁТ.** Сервер, рядом с `sender.db`. Конфиг `SENDER_CONFIG` (по умолчанию `./sender.yaml`, `cli.py:39-40`).

**4. СКОЛЬКО СТОИТ.** Ноль вызовов провайдера. Пакетная запись по 1000 строк.

**5. ЧЕМ ОГРАНИЧЕН.** `batch_size: int = 1000`, `limit: Optional[int]` (`importer.py:200-201`); без колонки email - `ImporterError` (`249-255`); валидация синтаксиса по `EMAIL_PATTERN` (`31-33`); прогресс каждые 10 000 строк.

**6. ПО ОДНОЙ КОМПАНИИ.** **Да, но через файл.** Отдельной команды «добавь получателя по ИНН» нет; штатный путь - CSV из одной строки:
```bash
printf 'email;inn;company;segment\nefimov@himprom.com;2124009521;ПАО ХИМПРОМ;новостные\n' > one.csv
python -m sender import one.csv --segment новостные
```
(команда `import` с `--limit` и `--segment`: `cli.py:645-651`).

## 3.2 `cadence.py` - планирование волны (не-AI путь)

**1. ВХОД.** `campaign_id` + `now`. Не ИНН (`cadence.py:57`).
**2. ВЫХОД.** Список `MessageIn` для `store.enqueue_message` -> таблица `messages` (`idempotency_key, campaign_id, recipient_id, sequence_step_id, scheduled_at, status`).
**3. ГДЕ ЖИВЁТ.** Внутри оркестратора на сервере.
**4. СКОЛЬКО СТОИТ.** Ноль вызовов провайдера.
**5. ЧЕМ ОГРАНИЧЕН.** Канареечная волна `cadence.canary_size`, по умолчанию 150 (`cadence.py:125`): пока канарейка не измерена, `plan_campaign` возвращает пустой список; таргетинг по `campaign.config['segment']` (`82-97`), порядок `send_order`: `pilot_asc -> pxr_asc`, `priority_desc -> pxr_desc` (`89-90`), порог `min_priority_max` (`91-96`), лимит считается по ПОЛУЧАТЕЛЯМ, чтобы не рвать цепочку (`109-112`).
**6. ПО ОДНОЙ КОМПАНИИ.** **Нельзя.** Модуль оперирует кампанией и сегментом; фильтра по ИНН у `plan_campaign` нет.

## 3.3 `ai_quota.py` - кому пишем сегодня

`sender/ai_quota.py`, 1235 строк.

**1. ВХОД.** `campaign_id` (+ необязательные `today`, `quota`, `count`). Не ИНН (`ai_quota.py:890-893`, `1164-1172`).

**2. ВЫХОД.** На каждое удачное письмо:
- строка в `confirm_reviews` (status='pending') через `store.confirm_submit` с `panel` - полной инфо-панелью (`ai_quota.py:944-953`, `_panel` 1044-1094);
- строка в `messages` со `status='pending_review'`, ключ идемпотентности `sha256(campaign|recipient|step_index)` (`_ensure_message`, `1097-1120`) - «claim_due его не берёт, авто-поток не подхватит»;
- строка в `ai_letter_log` (status='ok' или 'brak', subject, body, rounds_json, division) (`_log`, `1122-1137`).
Ключ привязки - `recipient_id` + `email`, ИНН едет рядом.

**3. ГДЕ ЖИВЁТ.** Панель на сервере (`build_ai_quota`, `1218-1235`). Конфиг: `service.db_path`, `service.enrich_db` (иначе ищет `enrich.db` рядом с БД), `obzvon.index_path`, `ai.quota_tz` (по умолчанию Europe/Moscow), `ai_quota.best_of` (3), `ai_quota.workers` (15), `ai_quota.idea_lenses_generic` (True).

**4. СКОЛЬКО СТОИТ на одну компанию.**
- письма считает `ai_letter` (см. 3.4);
- сверх того у GENERIC-письма (без новости): 3 вызова haiku (`claude-haiku-4-5`, три линзы «снабженец/инженер/скептик») + 1 вызов боевой модели-судьи (`_add_ideas_generic`, `ai_quota.py:819-874`). В коде прямо: «pytest на каждом GENERIC-письме жёг реальные вызовы haiku (~45 с/письмо и деньги владельца)» (`827-830`);
- сеть, кроме провайдера: `enrich.db` (дайджест сигнала), индекс обзвона (карточка), `sender.db`;
- время: батчи уходят параллельно, 15 воркеров (`920-925`); «200 писем - это часы» (`892-894`).

**5. ЧЕМ ОГРАНИЧЕН:**
- `MAX_PER_DAY = 200` - «предохранитель от опечатки 30 -> 300» (`47`);
- `SCAN_LIMIT = 20000` - потолок просмотра базы при поиске кандидатов (`49`), страница `_PAGE = 500` (`50`);
- `запас = limit * 10` и финальный `return out[:limit]` (`490`, `516`) - берём с запасом, сортируем по накалу, отдаём верх;
- нецелевые ОКВЭД режутся по `stage_log` (`tgt=0` или `div=-`) и по непромышленным разделам (`_nontarget_inns`, `518-579`) - повод: «как сюда банк попал?» (ВТБ 64.19 доехал до генерации);
- порядок кандидатов - `MAX(hotness)` из `signals`, сигналы с `suspect=1` (карантин тёзок) не греют (`_hotness_map`, `580-604`);
- дайджест: `LIMIT 5` сигналов, при равном накале побеждает самый длинный `what` (`637-644`); непрофильные вакансии (кладовщик, охрана) отбрасываются регуляркой (`646-659`);
- `_already()` - кому уже делали письмо, считается по `ai_letter_log` И `confirm_reviews` (`458-475`), поэтому повторно тому же получателю не сгенерится;
- `_STALE_RUN_SEC = 1800` - прогон без пульса полчаса считается оборванным (`51`, `1146-1155`).

**6. КАК ЗАПУСТИТЬ ПО ОДНОЙ КОМПАНИИ.** **Нельзя штатно.** Ручек ровно две, и обе не про ИНН:
- `POST /ai/quota/run {campaign_id, count}` - «сгенерировать ещё N писем» кандидатам по накалу (`api/app.py:1150-1167`, `ai_quota.py:1164-1187`);
- `POST /confirm/{rid}/regenerate` - перегенерировать ОДНО уже стоящее в очереди письмо (`api/app.py:1176-1211`, `ai_quota.regenerate_review`, `773-817`). Это единственный штатный «по одной штуке», но вход - `review_id`, а не ИНН.

Обход для одной компании (кода в репозитории нет, собирается из существующих методов):
```python
from sender.ai_quota import build_ai_quota
q = build_ai_quota(store, config)
r = store.query_recipients({'inn': '2124009521'}, limit=1)[0]   # фильтр inn есть: store.py:2046-2048
req = q._request(r)          # новость + город + роль + выручка + оборудование  (ai_quota.py:676-772)
q._add_ideas_generic([req])  # только для GENERIC
res = q._gen_factory().generate([req])
print(res.ok.get(0) or res.rejected.get(0))
```

## 3.4 `ai_letter.py` - генератор письма и вся база знаний о письме

`sender/ai_letter.py`, 1382 строки.

**1. ВХОД.** `generate(recipients)` - список словарей: `{company_name, okved, activity, contact_name, mode, extra{}, division|target_division|equip_categories}`; `mode` = `NEWS | GENERIC | auto` (auto -> NEWS, если в `extra` есть и `news_object`, и `city`) (`ai_letter.py:1182-1190`). Работает и на одном элементе.

**2. ВЫХОД.** `AiLetterResult`: `ok{idx -> {subject, body, rounds, division, division_reason}}`, `rejected{idx -> [причины]}`, `divisions{idx -> (division, reason)}`, `calls` (`1121-1126`). Сам в БД не пишет; отдельная функция `log_results(db_path, campaign_id, items)` создаёт/дополняет `ai_letter_log` (`1361-1382`).

**3. ГДЕ ЖИВЁТ.** Движок stdlib, работает где угодно; боевой `caller` приходит снаружи - `review_lenses.default_caller` (`ai_quota.py:298-309`). Файлы базы знаний, `_SENDER_DIR = os.environ.get('SENDER_DIR', r'C:\sender')` (`398`):

| файл | env | что внутри | код |
|---|---|---|---|
| `kc-facts.json` | `KC_FACTS` | total_crm («больше 5580 внедрений»), published_site, region_counts_site_index, clients_verified | `400-402`, `700-717` |
| `meyer-facts.json` | `MEYER_FACTS` | proof_points, industries_typical, pains_typical | `407-408`, `673-698` |
| `product_glossary.json` | `KC_GLOSSARY` | термины оборудования КЦ (первые 12 в промпт) | `404-405` |
| `meyer_glossary.json` | `MEYER_GLOSSARY` | термины Meyer | `410-411` |
| `okved-pains.json` | `OKVED_PAINS` | «ОКВЭД -> боль»: зачем отрасли наше оборудование | `415-450` |
| `kb/snyatye-verdict.json` | - | стоп-серии, снятые с производства | `snyatye.py:1-11` |

Файла нет - работает на фолбэке без падения: «письмо без цифр честнее, чем упавшая фаза генерации» (`502-511`, `649-665`).

**БАЗА ЗНАНИЙ ПРАВИЛ** (главный ответ на вопрос «что бракует письмо»):

- `RULES_KC` (`37-155`) и `RULES_MEYER` (`157-281`) - по 13 пунктов каждый: не реклама (38-ФЗ ст.18); ровно одна опция отказа; голос («я подбираю», компания поставляет, запрещено «мы», «я поставляю»); без длинных тире; числа только из ФАКТОВ; продаём оборудование, не сервис; техническая точность (у КЦ - обратная зависимость давления и производительности, точки росы; у Meyer - фотосепаратор видит только поверхность, рентген-порог 0,3 мм, металлодетектор не заменяет рентген); структура письма; объём 50-110 слов; тема 2-5 слов; человечность; не-реклама; маршрутизация NEWS/GENERIC. Плюс у Meyer пункт 14: компрессорная тема запрещена вовсе.
- `_RULES_APPENDIX_2707` (`285-306`) - по итогам сплошной вычитки 27.07 (101 брак из 359): имя адресата только буквальное из карточки; география грамматически полная («в Пензенской ОБЛАСТИ»); один вопрос; вакансия - повод только если профильная.
- `_RULES_APPENDIX_2807` - «КАНОН РЕДАКТОРА» (`316-352`), выведен из фактических правок четырёх отправленных писем: тема «Вопрос по ...» до 10 слов; заход-пересказ новости с названием компании; связка без страшилок; открытый вопрос об актуальности; фраза о помощи; плотность 3-4 абзаца; «компрессорное хозяйство» - брак, только «компрессорный парк». При конфликте этот блок главнее правил 6, 8, 9, 10, 17.
- `_HELP_LINE_KC` / `_HELP_LINE_MEYER` (`354-362`) - чем менеджер готов помочь первым шагом.
- `NEWS_MECHANICS` (8 штук, `373-383`) и `NEWS_MECHANICS_MEYER` (8 штук, `385-394`) - пул захода, назначается детерминированно ротацией `pool[(angle_base + i) % len(pool)]` (`758-761`), чтобы соседние письма не были одинаковыми.
- `ROLE_ANGLES` (`452-468`) - о чём говорить со снабжением, гл.инженером, директором, продажами, бухгалтерией, приёмной, общим ящиком.
- `SIZE_TONE` + `company_size` (`470-494`) - тон по выручке: микро < 120 млн, малый < 800 млн, средний < 2 млрд, крупный.
- `target_division` (`595-647`) - приоритет выбора направления: explicit -> news -> needs -> base_label -> profile -> fallback kc. Случай «новость про одно, потребность про другое» помечается `news_over_needs` и виден оператору.

**СТОП-СЛОВА И МЕХАНИЧЕСКИЙ ГЕЙТ** `gate()` (`997-1081`), возвращает список причин, пустой список = чисто:
- `SUBJ_RE` (`877-878`): цифра в теме, знак `?`/`!`, маскировка `Re:`;
- тема длиннее 12 слов (`1005-1007`);
- проценты, кроме 95/97/99 (`1008-1010`);
- `STOP_RE` (`879-905`), 25 правил: длинное тире, «предлага», «скидк», «акци», «купите», «гаранти», «лизинг», «цена», «рубл», «в наличии», «закладыва», обещание скорости, эпитет-витрина, «поставляю/поставляем», «мы», канцелярит (данный, таким образом, в ассортименте, представлены, осуществля, требует пересмотра), плезантрии, подпись в теле (Руспром, prokompressor, meyer-corp, usort.ru, ИНН), `<ul`, плейсхолдеры `{...}` и `[Название компании]`, «компрессорное хозяйство»;
- `CROSS_LEX` (`910-926`) - перекрёстная лексика: в meyer-письме запрещены компрессор, сжатый воздух, осушитель, точка росы, азот, кислород, пневмо, ресивер, МКС; в kc-письме - фотосепаратор, рентген, оптическая сортировка, инородные включения, ХАССП. Комментарий: «самая дорогая ошибка направленческой рассылки»;
- `PSEUDO_NEWS_RE` (`927-929`) - «вижу, вы модернизируете» в GENERIC = брак;
- двойное заискивание (`1020-1021`);
- объём `not 45 <= words <= 140` (`1015-1017`);
- финал не «С уважением,» (`1018-1019`);
- непроверенные числа: всё, чего нет в `allowed_numbers` (техконстанты + числа фактов + числа подтверждённых кейсов + безопасные поля extra) и в собственных полях компании (`1022-1037`, `966-995`);
- больше одного числа-достижения (`1039-1044`);
- город без склонения после «в/во» (`1045-1050`);
- обрезанный регион «в Чеченской» без слова область/край/Республика (`1052-1060`);
- имя в приветствии, которого нет в карточке контакта (`1061-1075`);
- больше двух знаков вопроса (`1076-1078`).
- **Выключено осознанно:** `БРАКОВАТЬ_БЕЗ_ОТКАЗА` (`936`, env `AI_LETTER_BRAKOVAT_BEZ_OTKAZA=1`) - с 02.08.2026 отсутствие строки отказа больше НЕ бракует письмо: «Замер на 452 письмах: 656 срабатываний этого замечания, 369 писем упёрлись в предел кругов». Юридическая отписка от этого не зависит - `List-Unsubscribe` ставится всегда.
- Анти-штамп `stamp_overflow` (`1086-1116`): лимиты на 49 писем, масштабируются на размер партии - «частый случай» 4, «судя по профилю» 4, «смотрел ваш» 5, «рано или поздно» 3, «бьёт по» 3, «встаёт вопрос» 4, «под контролем» 5; у Meyer свои («посторонние включения» 4, «пищевая безопасность» 3, «ручная переборка» 4, «рекламац» 3).

**СКОЛЬКО КРУГОВ ПЕРЕПИСЫВАНИЯ** (`generate`, `1182-1357`):
1. генерация батчами внутри направления (`batch=4`);
2. best-of-N: ещё `best_of-1` независимых заходов с другой механикой, затем судья-редактор выбирает лучший по канону 19 (`1236-1276`, `judge_prompt` `818-836`);
3. цикл `for rnd in range(self.rounds + 1)` - **3 круга доработки плюс принудительный четвёртый** (`rounds: int = 3`, `1144`). В каждом круге: механический гейт -> верификатор-линза (`vf_prompt` `851-873`: юрист/тон/спам/инженер/факты/структура/человечность + линза направления, одним вызовом на 8 писем) -> анти-штамп -> вызов доработки на 4 письма;
4. на предпоследнем круге в промпт добавляется жёсткое требование дословной строки отказа (`1327-1329`);
5. не прошло после принудительного - письмо **удаляется**, причины уходят в `rejected` и в брак-лог, письма нет (`1320-1324`).

**4. СКОЛЬКО СТОИТ на одно письмо.** При батче из одного письма и `best_of=3`: 3 вызова генерации + 1 судья + 1 верификатор = минимум 5 вызовов; каждый неудачный круг добавляет 1 вызов доработки и 1 верификатор, то есть потолок около 11 вызовов. Плюс 4 вызова у GENERIC (см. 3.3). При батче из 4 писем те же 3+1 вызова делятся на четверых. Ретраи битого JSON: `json_tries=3` (`1144`, `1173-1180`).

**5. ЧЕМ ОГРАНИЧЕН.** `batch=4`, `rounds=3`, `json_tries=3`, `best_of` (боевой 3 из `ai_quota.best_of`); верификатор идёт партиями по 8 (`1293`), судья и доработка - по 4 (`1264`, `1333`); чужой `idx` от модели отбраковывается, чтобы письмо не попало в чужой слот (`1213-1222`, ревью №20); верификатор не гоняется на принудительном круге (`1291`).

**6. КАК ЗАПУСТИТЬ ПО ОДНОЙ КОМПАНИИ.** **Да, штатно** - это единственный модуль пути, который изначально умеет одну штуку:
```python
from sender.ai_letter import AiLetterGen, load_facts
from sender.review_lenses import default_caller
gen = AiLetterGen(lambda p: default_caller(p)[0], facts=load_facts(), best_of=3)
res = gen.generate([{
    'company_name': 'ПАО «ХИМПРОМ»', 'okved': '20.13', 'activity': 'химическое производство',
    'contact_name': '', 'mode': 'auto',
    'extra': {'city': 'Новочебоксарск', 'city_source': 'новость',
              'news_object': 'строительство метанолового завода мощностью 1 млн тонн в год',
              'equipment': 'Генераторы азота | Генераторы кислорода'}}])
print(res.ok.get(0) or res.rejected.get(0), 'вызовов:', res.calls)
```

## 3.5 `review_lenses.default_caller` - шлюз к провайдеру

**1. ВХОД.** Строка промпта (`review_lenses.py:294`).
**2. ВЫХОД.** `(text, использованная_модель)`. В БД не пишет.
**3. ГДЕ ЖИВЁТ.** Сервер. Лениво импортирует `gen_provider` из каталога НА УРОВЕНЬ ВЫШЕ пакета `sender` (`review_lenses.py:304-308`) - **этого файла в выгруженном дереве нет**, он остался на сервере; там же ключ провайдера. `httpx` импортируется лениво, чтобы движок оставался stdlib.
**4. СКОЛЬКО СТОИТ.** Один вызов = один запрос к провайдеру, `max_tokens=2000`, стриминг (`_raw_stream`, `318`). Модель `claude-fable-5`, фолбэк `claude-opus-4-8`.
**5. ЧЕМ ОГРАНИЧЕН.** До 8 попыток (`for attempt in range(8)`, `316`); ответ короче 20 символов считается провалом (`322-325`); после 3 подряд неудач переключение на более сильную модель (`329-332`); бэкофф `min(30.0, 2**attempt * 0.5) + jitter` (`334`); после всех ретраев - `RuntimeError` (`337`).
**6. ПО ОДНОЙ КОМПАНИИ.** Не применимо: это один вызов, компаний не знает.

---

# ЧАСТЬ 4. ЧЕЛОВЕК И ОТПРАВКА

## 4.1 `confirm.py` - очередь подтверждений

**1. ВХОД.** `submit(email, subject, body, inn, campaign_id, recipient_id, message_id, panel)` (`confirm.py:223-229`). Решения принимаются по `review_id`.

**2. ВЫХОД.** Таблица `confirm_reviews`: `id, dedup_key, campaign_id, recipient_id, message_id, inn, email, subject, body, panel_json, status, reason, edited_subject, edited_body, diff_text, decided_by, decided_at, created_at, updated_at, kind, in_reply_to, thread_id`. Статусы: `pending | skipped | bypassed | sent | approved | edited`. Ключ идемпотентности - `(ИНН, email, campaign_id)` (`confirm.py:18-19`). Правка оператора сохраняется unified-дифом - «золотые пары для дообучения промптов» (`build_diff`, `919`; выгрузка `confirm-golden`, `cli.py:777-780`).

**3. ГДЕ ЖИВЁТ.** Сервер, панель и CLI зовут один и тот же модуль (`confirm.py:22-23`). Конфиг: `confirm.mode` (`off|all|sample`), `confirm.sample_every`, `confirm.live_send` (`wiring.py:78-90`). При `live_send=true` собирается ОТДЕЛЬНЫЙ `Sender` с `dry_run=False`, независимо от режима панели.

**4. СКОЛЬКО СТОИТ.** Ноль вызовов провайдера. Оператор - единственный дорогой ресурс.

**5. ЧЕМ ОГРАНИЧЕН.**
- `RECENT_CONTACT_DAYS = 90` (`51`) - повторный контакт ближе 90 дней блокирует;
- заслон проверяется ДВАЖДЫ: при постановке в очередь и при подтверждении (`submit` `247-256`, `approve` `385-397`);
- `STOPLIST_REASONS` (`44-49`): конкурент -> competitor, нерелевант/плохие данные -> manual, по запросу -> unsubscribe (навсегда);
- гейт направлений: несовпадение направления письма и компании ставит `stop_flags` и `confirm_hold`, кнопка «Отправить» блокируется (`_division_flags` `102-144`, `_division_blocked` `145-156`);
- `force=True` - двойное подтверждение оператора снимает все заслоны, включая отписку, и обязательно пишется в аудит (`approve` `366-381`, `_audit_force` `405-418`);
- `sample`-режим: в очередь идёт каждое N-е письмо, остальные пишутся как `bypassed` (`262-283`);
- модуль **никогда не шлёт SMTP сам** в очередном режиме: «approved лишь переводит письмо в messages.status='scheduled'» (`confirm.py:25-27`).

**6. КАК ЗАПУСТИТЬ ПО ОДНОЙ КОМПАНИИ.** **Да, штатно, по одному письму:**
```bash
python -m sender confirm-queue --campaign 1 --limit 50      # cli.py:759-761
python -m sender confirm-show <review_id> --json            # cli.py:763-767
python -m sender confirm-decide approve <review_id> --operator kirill   # cli.py:769-775
python -m sender confirm-decide edit <review_id> --subject "..." --body-file new.txt
python -m sender confirm-decide skip <review_id> --reason "нерелевант"
python -m sender confirm-decide stoplist <review_id> --reason "конкурент"
```

## 4.2 `orchestrator.py` - автоматический цикл

**1. ВХОД.** `tick(now=...)`, список активных `campaign_ids`. Не ИНН.
**2. ВЫХОД.** `TickResult{planned, sent, skipped, failed, inbound, gates_tripped, warmup_sent, queued}`; пишет только через `store`.
**3. ГДЕ ЖИВЁТ.** Сервер: `python -m sender run [--dry-run] [--once] [--campaigns 1,2]` (`cli.py:711-717`).
**4. СКОЛЬКО СТОИТ.** Ноль вызовов провайдера (генерация живёт в `ai_quota`).
**5. ЧЕМ ОГРАНИЧЕН.** Порядок шагов тика жёсткий: `recover_stale -> IMAP poll -> gates -> plan -> claim -> render -> confirm/send -> warmup` (`orchestrator.py:335-560`). `claim_due_messages(..., limit=self.send_batch)`. Отказ гейтов = fail-safe: тик вообще без отправки (`orchestrator.py:366-374`). Незаполненный плейсхолдер не уходит никогда: `mark_needs_data` вместо отправки (`orchestrator.py:437-462`). В confirm-режиме письмо не отправляется, а кладётся в очередь и `messages` переводится в `pending_review` (`orchestrator.py:464-492`).
**6. ПО ОДНОЙ КОМПАНИИ.** **Нельзя.** `--campaigns` фильтрует кампании, не компании. Единственная «одна штука» - ручное подтверждение письма (см. 4.1).

## 4.3 `sender.py` - SMTP и все лимиты отправки

**1. ВХОД.** `send(message, rendered, mailbox_id, manual=False, to_email=None, force=False)` (`sender.py:573`); выбор ящика - `pick_mailbox(recipient, campaign)` (`361`).
**2. ВЫХОД.** Реальное письмо + `messages.status='sent'`, `rfc_message_id`, `sent_at`; события в `events`; строка в `send_log` (`inn, email, campaign_id, ts, message_id, rfc_message_id, subject, outcome`). Ключ привязки - `message_id`, наружу - email.
**3. ГДЕ ЖИВЁТ.** Сервер. Секреты обязаны быть в env: пароль каждого ящика (`mailbox.password_env`, `config.py:409-412`), секрет отписки (`legal.unsub_secret_env`, `config.py:589-592`). Отсутствие переменной - ошибка загрузки конфига, а не тихая работа.
**4. СКОЛЬКО СТОИТ.** Ноль вызовов провайдера. Одно SMTP-соединение на письмо, плюс необязательный IMAP APPEND в «Отправленные».
**5. ЧЕМ ОГРАНИЧЕН** (`can_send_now`, `482-535`):
- kill-switch глобальный и по ящику (`gates.check_global/check_mailbox`);
- пауза ящика;
- окно отправки: дни ISO 1..7 и часы, из конфига или живой настройки панели `sending_window` (`1022-1048`);
- дневной лимит: рамп-кривая, которую ручной потолок панели может только ПРИЖАТЬ вниз (`_daily_limit`, `984-1021`);
- пейсинг между письмами: `send_pacing.min_interval_sec` по умолчанию 90 с, `max_interval_sec` 420 с с джиттером (`529-534`, `895-901`);
- `manual=True` (оператор нажал «Отправить») пропускает окно и пейсинг, но лимит дня и kill-switch оставляет; `force=True` (второе личное подтверждение) снимает всё: `if force: return True` (`500-501`);
- подпись дописывается на отправке (`_apply_signature`, `1202-1265`), включая согласование рода письма с полом ящика (`gender_agree`) и юр-атрибуцию с ИНН; `List-Unsubscribe` + RFC 8058 ставятся всегда (`_list_unsubscribe_headers`, `1159`).
**6. ПО ОДНОЙ КОМПАНИИ.** **Только через оператора**: `confirm-decide approve <review_id>` при `confirm.live_send=true` уходит немедленно по боевому SMTP (`confirm._send_live_inner`, `488-576`). Прямой команды «отправь письмо на ИНН» нет и по устройству быть не должно.

## 4.4 Заслоны (короткие карточки)

| модуль | вход | выход | стоит | ограничен | по одной компании |
|---|---|---|---|---|---|
| `suppression.py` | email / domain / inn | таблица `suppression`, порядок проверки email -> domain -> inn | 0 вызовов | `UNIQUE(scope,value)`; истёкшие `expires_at` игнорируются; `unsubscribe` бессрочна (`suppression.py:9-16`) | да: `python -m sender suppress <файл>` (`cli.py:653-663`), одна строка в файле |
| `gates.py` | журнал `events` | паузы ящиков, domain-suppression, глобальное решение | 0 вызовов | trip только ставит паузу и НИКОГДА не снимает; guard минимального объёма выборки (`gates.py:5-23`) | нет, это статистика по домену/ящику/глобально |
| `validation.py` | получатели | `mx_provider`, `valid_status`, `catch_all`, `role_based`, `disposable` | 0 вызовов, DNS/SMTP-пробы | `python -m sender validate --limit N` (`cli.py:665-670`) | да, через `--limit 1` по очереди невалидированных |
| `snyatye.py` | текст письма | находки снятых с производства серий | 0 вызовов | `kb/snyatye-verdict.json`; `снята_заводом` - красный флаг, `снята_у_конкурента` - жёлтый (`snyatye.py:1-11`) | да: `scan_text(текст)` |

---

# ЧАСТЬ 5. Сводка «можно ли по одной компании»

| модуль | вход по ИНН? | как запустить одну штуку |
|---|---|---|
| `news_scan.py` | **нет** | по ИМЕНИ: `echo '{...xmlriver_queries:["\"ИМЯ\" (...)"]}' \| python news_scan.py` |
| `newsco_op.py` | **нет** | обход: одна строка в `newsco_targets.jsonl` + `serp --off 0 --lim 1` без `--rebuild` |
| `news_funnel_audit.py` / `news_reconcile.py` | нет | нельзя, агрегаты по всей базе |
| `company_card.py` | **да** | `CompanyCards(...).card(inn)` |
| `infopanel.py` | **да** | `load_enrich_lead(inn)` / `build_panel(inn=..., email=...)` |
| `importer.py` | через файл | CSV из одной строки + `python -m sender import one.csv` |
| `cadence.py` | нет | нельзя, план по кампании и сегменту |
| `ai_quota.py` | **нет** | штатно только `POST /ai/quota/run` (по накалу) и `POST /confirm/{rid}/regenerate` (по review_id) |
| `ai_letter.py` | **да** (через словарь получателя) | `AiLetterGen(caller).generate([{...}])` |
| `confirm.py` | **да** (по review_id) | `confirm-queue` -> `confirm-show` -> `confirm-decide approve/edit/skip/stoplist` |
| `orchestrator.py` | нет | нельзя |
| `sender.py` | нет | только через `confirm-decide approve` при `confirm.live_send=true` |

---

# ЧАСТЬ 6. Что мешает собрать «вбил ИНН - получил всё» (честно)

1. **Левая половина пути пачечная по устройству.** `news_scan` начинается с запросов, а не с компании: ИНН там появляется последним шагом (`dadata_suggest`). `newsco_op` уже идёт «от компании», но берёт её из файла целей, отсортированного по выручке, и не умеет принимать ИНН аргументом. Недостающая ручка - одна: `newsco_op.py serp --inn <ИНН>`, которая соберёт цель из индекса обзвона вместо файла. Всё остальное в модуле уже работает на одной компании (`сбор` при `lim=1`).
2. **Выбор «кому писать» не умеет адресности.** `AiQuota.candidates` (`ai_quota.py:477-516`) отбирает по сегменту кампании и сортирует по накалу; фильтра по ИНН нет, хотя нижележащий `store.query_recipients` его поддерживает (`store.py:2046-2048`). Недостающая ручка - вторая: `run_for_inn(campaign_id, inn)` поверх готовых `_request` + `_gen_factory().generate`.
3. **Между добычей и рассылкой стоит ручная сборка CSV.** `news-campaign-master.csv` (66 строк, склейка enrich.db + 36 полей базы обзвона) собран скриптом сессии, которого в выгруженном дереве нет; `importer.py` умеет только читать готовый файл. Недостающая ручка - третья: экспорт `enrich.db + obzvon-index.db -> CSV импортёра` по списку ИНН.
4. **Провайдерский клиент за пределами дерева.** `gen_provider` лежит на уровень выше пакета `sender` и в выгрузку не попал (`review_lenses.py:304-308`), поэтому в песочнице генерация письма не запускается вовсе - только на сервере владельца.
5. **Привязка новости к компании остаётся слабым местом.** Уровень `ядро` (все токены имени найдены в тексте) в `newsco_op.привязка` формально проходит, но именно он даёт тёзок; проверка 66 пар (`/home/user/work/RASSYLSHIK-otchet-3-sessii.md`) дала 16 подтверждённых мисматчей. В `ai_quota._digest`/`_hotness_map` уже есть карантин `signals.suspect=1`, но проставляется он не этими модулями.
