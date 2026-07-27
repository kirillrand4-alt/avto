# 09. Раннер, файлообменник и панель обогащения

Область: `seo-texts/server/` — механика «руки Claude на сервере владельца» плюс
веб-панель обогащения. Всё, что ниже, проверено по коду; ссылки вида
`файл:строка` указывают на конкретное место. Что не проверено — вынесено в
последний раздел.

Дата сверки: 2026-07-27. Ветка: `claude/seo-texts-enrichment-prompt-449lyw`,
HEAD `0e8e7fd`.

---

## 1. Что это и зачем

Сессия Claude живёт в песочнице: часть РФ-сайтов (checko, rusprofile, сайты
компаний, hh, ЕИС) оттуда либо недоступна, либо ловит Cloudflare. Сервер
владельца — Windows-машина в РФ (`C:\sender`, IP 91.206.14.169 по
`seo-texts/server/ENRICH-SALES-BASE-PROMPT.md:4`) — ходит туда нативно.

Связка из трёх кусков:

1. **Файлообменник («дроп»)** — `drop_server.py`, HTTP-хранилище плоских файлов
   на `https://parsercompressor.online/drop`, авторизация заголовком
   `X-Drop-Token`. Общая «почта» между песочницей и сервером.
2. **Раннер** — `job_runner.py`, служба NSSM `rusprom-runner` на сервере.
   Поллит дроп, находит `job-*.json`, проверяет HMAC-подпись, запускает
   **ровно один из заранее разрешённых скриптов** (не произвольный shell),
   кладёт `result-<id>.json` обратно и удаляет задание.
   Клиентская половина — `run_on_server.py` (запускается в песочнице).
3. **Панели** — веб-морды на сервере. Их две с половиной:
   - `enrich_panel/` — **панель обогащения**, порт 8013, служба `EnrichPanel`,
     за Caddy на `/enrich/*`. Ставит задания раннеру тем же протоколом.
   - панель рассыльщика `SenderPanel` (порт 8091, код в `seo-texts/sender/`) —
     не эта область, но её **выкатка** живёт здесь: `build_panel_update.sh`,
     `update-panel.ps1`, `preflight_panel.py`.
   - панель обзвона `obzvon` (порт 8012, `C:\seostat\app`) — выкатка
     `update-obzvon.ps1`.

Лаунчеры (`launch_*.py`, `mass_enrich_loop.*`) — тонкие драйверы над
`run_on_server.submit()`: режут список компаний на порции и шлют их раннеру.

Схема потока:

```
песочница                    дроп (HTTP)                   сервер владельца
run_on_server.submit()  -->  job-<id>.json      -->  job_runner.tick()
   или enrich_panel                                    -> subprocess ALLOW[task]
                                                       -> stdin = JSON args
run_on_server ждёт      <--  result-<id>.json   <--  drop_up(result), drop_del(job)
```

---

## 2. Точки входа и как запустить

### 2.1 Дроп (читать/писать файлы) — из песочницы

```bash
export DROP_URL=https://parsercompressor.online/drop   # уже в окружении
export DROP_TOKEN=...                                   # уже в окружении
bash /home/user/avto/seo-texts/server/drop_client.sh list
bash /home/user/avto/seo-texts/server/drop_client.sh down <имя> [куда]
bash /home/user/avto/seo-texts/server/drop_client.sh up <файл>
bash /home/user/avto/seo-texts/server/drop_client.sh del <имя>
```

`drop_client.sh:5-13`. `up` кладёт под `basename` файла. `list` печатает JSON
через `python3 -m json.tool`. Токена в окружении нет → скрипт печатает
«нет DROP_TOKEN в окружении» и выходит с кодом 1 (`drop_client.sh:6`).

### 2.2 Отправить задание раннеру — из песочницы

```bash
cd /home/user/avto/seo-texts/server        # ОБЯЗАТЕЛЬНО: пути относительные
python3 run_on_server.py ping '{"hi":1}'
python3 run_on_server.py verify_company '{"companies":[{"name":"КАО Азот","inn":"4205000908"}]}'
```

CLI требует ровно два аргумента: `<task> <args-json>` (`run_on_server.py:87-91`).

Программно (так делают все лаунчеры):

```python
import sys, os
sys.path.insert(0, '/home/user/avto/seo-texts/server')
import run_on_server as R
R._load_secret_from_drop()          # если JOB_SECRET нет в окружении
res = R.submit('enrich_contacts', {...args...}, wait=True, poll=15, timeout=1800)
```

Сигнатура: `submit(task, args, wait=True, poll=15, timeout=1800)`
(`run_on_server.py:51`). `wait=False` → сразу вернёт `{'submitted': <jid>}`
(`run_on_server.py:65-66`).

### 2.3 Лаунчеры (все запускаются из `seo-texts/server`)

| Скрипт | Команда и позиционные аргументы (в порядке) | Дефолты |
|---|---|---|
| `launch_sales_enrich.py` | `python3 launch_sales_enrich.py <sales_base.json> [batch] [workers] [bworkers] [channels] [only-ИНН,через,запятую] [fast]` | batch=120, workers=40, bworkers=4, channels=6, only='', fast=False (`:97-106`) |
| `launch_core_chunked.py` | `python3 launch_core_chunked.py [core396.json] [batch] [workers] [bworkers] [channels] [fast]` | batch=120, workers=40, bworkers=4, channels=6, **fast=True** (`:50-55`) |
| `launch_core_enrich.py` | `python3 launch_core_enrich.py <core396.json> [workers] [bworkers] [channels] [timeout]` | workers=60, bworkers=8, channels=6, timeout=3000 (`:17-20,:41`) |
| `launch_top1000.py` | `python3 launch_top1000.py <top1000.json> [batch] [workers]` | batch=250, workers=30 (`:18-19`) |
| `launch_refail.py` | `python3 launch_refail.py <refail_companies.json> [chunk] [workers] [bworkers]` | chunk=105, workers=24, bworkers=8 (`:24-27`) |
| `mass_enrich_loop.py` | `python3 mass_enrich_loop.py [CAP] [BATCHES] [WORKERS] [CHANNELS] [BATCH_TIMEOUT]` | 40, 0(=до опустошения), 4, 4, 900 (`:18-22`) |
| `mass_enrich_loop.sh` | `bash mass_enrich_loop.sh <CAP> <BATCHES> [WORKERS] [CHANNELS]` | 400, 0, 8, 4 (`:13`) |

`fast` принимается как `1|fast|true` (регистр не важен) —
`launch_sales_enrich.py:106`, `launch_core_chunked.py:55`.

`launch_core_chunked.py` импортирует `build_args` из `launch_sales_enrich`
(`:29`) и меняет только `stream_file`/`source` (`:63-64`).

### 2.4 Выкатка панелей

Сборка пакетов (песочница):

```bash
bash /home/user/avto/seo-texts/server/build_panel_update.sh panel    # только SenderPanel
bash /home/user/avto/seo-texts/server/build_panel_update.sh obzvon   # только обзвон
bash /home/user/avto/seo-texts/server/build_panel_update.sh          # all (по умолчанию)
WITH_WEB=1 bash .../build_panel_update.sh panel                      # + пересборка фронта
```

`build_panel_update.sh:21` (`WHAT="${1:-all}"`), `:51` (`WITH_WEB`).
Скрипт кладёт `panel-update.zip` / `obzvon-update.zip` **и оба `.ps1`** на дроп
(`:111-118`) и печатает команды для владельца (`:120-123`).

Перед сборкой (канон `PANEL-DEPLOY.md:83`):

```bash
cd /home/user/avto/seo-texts/server && python3 preflight_panel.py [путь-к-репо-панели]
```

Дефолт пути — `seo-texts/sender` (`preflight_panel.py:22-23`). Код возврата
0 = выкатывать безопасно, 1 = в репо есть файлы МЕНЬШЕ боевых (`:83-88`).
**Внимание: этот скрипт сам ходит на сервер** — он ставит два задания раннеру
(`panel_file_put`, затем `panel_py`), см. `preflight_panel.py:56-61`.

На сервере (владелец, PowerShell, по одной команде):

```powershell
$tok=(Select-String -Path C:\sender\server\runner-secrets.env -Pattern 'DROP_TOKEN=').Line.Split('=',2)[1].Trim()
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/update-panel.ps1" -Headers @{'X-Drop-Token'=$tok} -OutFile C:\sender\update-panel.ps1
powershell -ExecutionPolicy Bypass -File C:\sender\update-panel.ps1
```

### 2.5 Панель обогащения (веб)

Боевые URL: `https://parsercompressor.online/enrich/` (список + загрузка файла),
`/enrich/base` (база обзвона), `/enrich/run/<id>` (прогон),
`/enrich/run/<id>/export.csv`. Роуты — `enrich_panel.py:135,142,172,196,219,243,292`.

Локальный запуск (для разработки):

```bash
cd /home/user/avto/seo-texts/server/enrich_panel
ENRICH_USERS=kir:secret ENRICH_DB=/tmp/e.db ENRICH_ROOT_PATH= python3 enrich_panel.py
# слушает 127.0.0.1:8013 (enrich_panel.py:313-315)
```

Тесты:

```bash
cd /home/user/avto/seo-texts/server/enrich_panel && python3 -m pytest tests/ -q
```

---

## 3. Как устроено внутри

### 3.1 `job_runner.py` — служба на сервере

**Запуск.** NSSM-служба `rusprom-runner`, `AppDirectory C:\sender\server`
(`RUNNER-SETUP.md:37-46`). Руками не запускать — `PANEL-DEPLOY.md:108-113`
описывает инцидент 2026-07-24: два ручных экземпляра + служба = каждый job
исполнялся 2-3 раза.

**Секреты.** При импорте модуля вызывается `_load_env_file()`
(`job_runner.py:35-52`): читает `runner-secrets.env` **из каталога скрипта**,
не перетирает уже заданные переменные и пропускает плейсхолдеры, начинающиеся
с `<` (`:48`). Шаблон файла — `runner-secrets.env.example` (в git; сам
`runner-secrets.env` в `.gitignore`).

**Фактические константы:**

| Имя | Значение | Env-переопределение | Строка |
|---|---|---|---|
| `DROP_URL` | `https://parsercompressor.online/drop` | `DROP_URL` | `:54` |
| `POLL_SEC` | **20** сек | `RUNNER_POLL_SEC` | `:57` |
| `JOB_TIMEOUT` | **1800** сек (30 мин) | `RUNNER_JOB_TIMEOUT` | `:58` |
| `SEEN_PATH` | `<DIR>/.runner-seen.json` | — | `:59` |
| `WORKERS` | **8** | `RUNNER_WORKERS` | `:233` |
| heavy-пул | **1** воркер | `RUNNER_HEAVY` | `:326` |
| HTTP-таймаут к дропу | 90 сек | — | `:80` |

**ALLOW — точный состав** (`job_runner.py:62-73`), 9 ключей:

| task | что запускается |
|---|---|
| `verify_company` | `<DIR>/verify_company.py` |
| `enrich_contacts` | `<DIR>/enrich_contacts.py` |
| `browser_probe` | `<DIR>/browser_probe.py` |
| `dadata` | `<DIR>/dadata_client.py` |
| `news_scan` | `<DIR>/news_scan.py` |
| `enrich_db` | `<DIR>/enrich_db.py` |
| `dolphin_pool` | `<DIR>/dolphin_pool.py` |
| `lead_scoring` | `<DIR>/lead_scoring.py` |
| `ping` | `python -c` инлайн-эхо: `{"pong":true,"echo":<args>}` |

Плюс **две задачи вне ALLOW**, они перехватываются в `run_job()` ДО обращения
к словарю (`job_runner.py:193-201`):

- `pull` → `_do_pull()` — самообновление кода;
- `spawn_campaign` → `_spawn_detached('send_campaign.py')` — отдельный
  detached-процесс, переживающий таймаут задания (`:176-190`).

Итого фактический набор задач = 9 из ALLOW + `pull` + `spawn_campaign` = 11.

**PULL_ALLOW — точный состав** (`job_runner.py:145-148`), 11 имён:
`verify_company.py`, `job_runner.py`, `run_on_server.py`, `enrich_contacts.py`,
`browser_probe.py`, `dadata_client.py`, `send_campaign.py`, `news_scan.py`,
`enrich_db.py`, `dolphin_pool.py`, `lead_scoring.py`.

`_do_pull` (`:151-173`): берёт `args['files']` (или ВЕСЬ PULL_ALLOW, если не
задано), от каждого имени оставляет `os.path.basename` (обхода путей нет),
скачивает с дропа и **перезаписывает файл в каталоге раннера** (`C:\sender\server`).
Санити-чек: ответ меньше 40 байт или содержащий `X-Drop-Token` в первых
200 байтах отбраковывается (`:164`). `job_runner.py` применяется только после
`Restart-Service rusprom-runner` (`:173`).

Скрипты панели обогащения (`enrich_panel/*`) в PULL_ALLOW **не входят** —
доставлять их через `pull` нельзя, только `panel_file_put` или zip.

**Как подписывается задание.** Канон — `canonical()` (`job_runner.py:127-132`):

```python
json.dumps({'id': ..., 'task': ..., 'args': ..., 'ts': ...},
           sort_keys=True, separators=(',', ':'), ensure_ascii=False)
```

Подпись: `hmac.new(JOB_SECRET.encode('utf-8'), canonical.encode('utf-8'),
hashlib.sha256).hexdigest()` — 64 hex-символа, кладётся в поле `sig`.
Проверка — `sig_ok()` (`:135-141`), сравнение через `hmac.compare_digest`.

**Важно:** если `JOB_SECRET` в окружении раннера пуст, `sig_ok()` возвращает
`True` без всякой проверки (`job_runner.py:136-138`). Второй рубеж (allowlist)
при этом сохраняется, но подделать задание сможет любой, у кого есть
`DROP_TOKEN`. В логе старта видно, какой режим включён (`:310-311`).

Клиентская сторона повторяет формат байт-в-байт: `run_on_server.py:55-60`,
`enrich_panel/panel_core.py:440-454`. Совместимость подписи панели с боевым
`job_runner.sig_ok` покрыта тестом (`enrich_panel/README.md:16-18`).

**Как исполняется задание** (`job_runner.py:203-220`):

```python
subprocess.run(cmd, input=json.dumps(args, ensure_ascii=False),
               capture_output=True, text=True, timeout=JOB_TIMEOUT, encoding='utf-8')
```

Аргументы уходят **через stdin как JSON**, не в argv и не в shell — инъекция
команд невозможна даже при подделанном задании. Результат:
`ok = (returncode == 0)`; stdout, если он парсится как JSON, кладётся в `data`,
иначе — последние 4000 символов в `stdout_tail`; при ненулевом коде добавляется
`stderr_tail` (последние 2000). Таймаут даёт `{'ok': False, 'error': 'timeout 1800s'}`.

**Параллелизм (v2/v3).** Два пула: общий `ThreadPoolExecutor(8)` и отдельный
heavy-пул на 1 воркер (`:325-326`). Что считается «тяжёлым» — `_is_heavy()`
(`:239-246`): task `dolphin_pool`, либо в args есть `sweep` / `mass_base` /
`news_enrich` / `xmlriver_queries` / `kg_probe`, либо task `enrich_contacts`
с непустым `companies` и без `site_crawl`. **Практически это значит: любой
обычный батч обогащения по списку компаний — тяжёлый и идёт строго по одному.**

`_SEM_HEAVY` (`:234`) — мёртвая переменная: семафор создаётся, но нигде не
захватывается (проверено `grep`: единственное вхождение — строка 234). Его
роль забрал отдельный heavy-пул после инцидента 2026-07-24 (комментарий `:253-255`).

**Учёт исполненного.** `seen` — множество имён job-файлов в
`.runner-seen.json`, хранится последние 5000 отсортированных имён (`:120-124`).
Имя добавляется в seen и файл сохраняется **до** скачивания задания
(`:285-286`) — то есть даже упавшее на разборе задание больше не будет взято.
Задание удаляется с дропа только ПОСЛЕ завершения (`:268`).
На старте службы работает «v3-сброс» (`:313-324`): имена, которые ЕСТЬ на дропе
и одновременно числятся в seen, из seen удаляются — иначе после `nssm restart`
недоделанные джобы висели бы вечно (инцидент 2026-07-22, комментарий `:314-316`).

Порядок разбора очереди — лексикографический по имени файла (`:278-279`),
то есть фактически по unix-времени в id.

### 3.2 `run_on_server.py` — клиент в песочнице

- `JOB_SECRET` берётся из окружения, а если его там нет —
  `_load_secret_from_drop()` качает с дропа файл `runner-secrets.env` и
  выдёргивает строку `JOB_SECRET=` (`:25-36`). В текущей песочнице переменной
  `JOB_SECRET` НЕТ (проверено `env`), а `DROP_URL`/`DROP_TOKEN`/
  `PROVIDER_API_KEY`/`PROVIDER_BASE_URL` есть — значит подпись подтягивается
  с дропа.
- id задания: `f'{int(time.time())}-{os.getpid()}'` (`:46-48`). **Два submit'а
  в одну секунду из одного процесса дадут одинаковый id и перезатрут друг
  друга** — поэтому `launch_top1000.py:44` ставит `time.sleep(1.5)` между
  батчами.
- Ожидание: цикл `sleep(poll)` → `GET list` → если появился `result-<id>.json`,
  скачать, **удалить с дропа** и вернуть (`:69-81`). По истечении `timeout`
  возвращается `{'error': 'timeout ждали Ns', 'id': jid}` — само задание при
  этом на сервере продолжает выполняться (или ждёт очереди).

### 3.3 `drop_server.py` — сам обменник

Flask-приложение (`drop_server.py`). Ключевые факты:

- каталог хранения: env `DROP_DIR`, иначе `<каталог скрипта>/drop-storage` (`:7`);
- `TOKEN` из env `DROP_TOKEN`; **токен не задан → 503 на всё**, не совпал → 401
  (`:16-19`), сравнение через `hmac.compare_digest` (`:14`);
- лимит тела запроса 8 ГиБ (`:10`);
- имя файла обязано матчить `^[\w][\w.\-]{0,200}$` (`:11`) — проверка стоит на
  GET/PUT/DELETE (`:32,37,50`), но **не на `/list`**;
- загрузка потоковая, кусками по 1 МиБ, во временный `<name>.part`, затем
  атомарный `os.replace`; в ответе — размер и sha256 (`:39-46`);
- боевой запуск: `waitress.serve(app, host='127.0.0.1', port=8787, threads=24,
  max_request_body_size=9 ГиБ, channel_timeout=7200)` (`:56-62`); при отсутствии
  waitress — `app.run` на том же порту.

Наружу (443/`/drop`) он выставлен через обратный прокси; конфига этого прокси
в репозитории я не нашёл (см. «Что не проверено»).

### 3.4 Панель обогащения `enrich_panel/`

Два модуля: `enrich_panel.py` (315 строк, FastAPI-слой) и `panel_core.py`
(968 строк, вся логика без HTTP). Плюс Jinja-шаблоны, свой `static/style.css`,
65 тестов и подробный `README.md` (его стоит прочитать целиком — он честный).

**Принцип:** панель НЕ вызывает `enrich_contacts.py` напрямую и не имеет своей
очереди. Она кладёт подписанные `job-*.json` на дроп, а исполняет их та же
служба `rusprom-runner`. Менять `job_runner.py` для панели не нужно —
`enrich_contacts` уже в ALLOW.

**Конфигурация (env)** — `panel_core.py:38-73`, `enrich_panel.py:70,74,314`:

| Переменная | Дефолт | Смысл |
|---|---|---|
| `ENRICH_USERS` | — (**обязательна**) | `логин:пароль,логин2:пароль2`; не задана → 503 всем (`enrich_panel.py:78-79`) |
| `ENRICH_DB` | `C:\sender\enrich.db` | БД обогащения (`panel_core.py:38-40`) |
| `ENRICH_UPLOADS` | `C:\sender\enrich_uploads` | куда падают загруженные файлы (`:43-46`) |
| `OBZVON_INDEX` | `C:\sender\obzvon-index.db` | индекс базы обзвона, открывается read-only (`:49-55`, `:327`) |
| `RUNNER_ENV` | `C:\sender\server\runner-secrets.env` | ключница: оттуда берутся `DROP_URL`/`DROP_TOKEN`/`JOB_SECRET` (`:58-73`) |
| `ENRICH_ROOT_PATH` | `/enrich` | префикс за прокси (`enrich_panel.py:70`) |
| `ENRICH_PORT` | `8013` | порт (`enrich_panel.py:315`) |
| `SENDER_DIR` | `C:\sender` | база для дефолтов путей (`panel_core.py:40,55`) |

**Безопасность:** Basic-auth middleware на всё приложение
(`enrich_panel.py:76-95`, `compare_digest` даже для несуществующего логина);
CSRF — same-origin по `Sec-Fetch-Site`/`Origin`/`Referer` (`:52-63`);
имя загруженного файла в путь не попадает — файл сохраняется как
`run<id>-<unixtime>.<csv|xlsx>` (`:160-161`).

**Лимиты:** `MAX_BYTES = 10 МБ`, `MAX_ROWS = 5000` (`panel_core.py:80-81`).
Заголовки ищутся в первых 5 строках, алиасы `инн|inn` и
`название|name|наименование|краткое|краткое наименование|компания|company`
(`:84-86,:110-123`). CSV декодируется utf-8-sig, при ошибке cp1251;
разделитель — тот, которого больше в первой строке (`:126-135`).

**Конвейеры — фактические args и батчи** (`panel_core.py:591-623`).
Все идут задачей раннера `enrich_contacts`, конкретная операция выбирается
полем `args['op']` (без `op` — базовое обогащение):

| Ключ | `args` | Батч | Стадия «сделано» |
|---|---|---|---|
| `base` | `companies`, `workers=min(8,len)`, `browser_workers=2`, `channels=4`, `pace_min=2`, `pace_max=5`, `smtp_check`, `no_vk_lookup`, `write_db`, `resume`, `stream_file=enrich_panel_run<id>.jsonl`, `source=panel-run<id>` (`:500-518`) | 8 | `site`/`site_cand`/`email` |
| `etp` | `{op:'etp_fit', inns, limit:len(inns), max_cards:3}` (`:521-526`) | 8 | `etp` |
| `okved` | `{op:'checko_okveds', inns}` (`:529-533`) | 8 | `checko` |
| `best_email` | `{op:'promote_named_email', inns}` (`:536-540`) | 1000 | `best_email_v2` |
| `hh` | `{op:'hh_signals', pages:3}` (`:549-557`) | вся выборка (`WHOLE=10**9`, `:546`) | `hh` |
| `opo` | `{op:'opo_batch', companies:[{ogrn,inn,name}], out_file:panel-opo-run<id>-<инн>.csv}` (`:560-576`) | 40 | `opo` |
| `zakupki` | `{op:'zakupki_mass', cap:len(rows), max_cards:3}` (`:579-586`) | вся выборка | `zakupki` |

**Постановка** — `submit_run()` (`panel_core.py:888-923`). Два рубежа
идемпотентности: (1) берутся только строки без нужной стадии в `stage_log`
(`missing_rows`, `:805-819`); (2) пока по конвейеру есть незавершённые батчи,
новые не ставятся (`pending_batches`, `:749-759`). Id задания:
`f'{int(time.time())}-r{run_id}-{key}-b{batch_count+1}'` (`:915`) — это
отличает панельные джобы от лаунчерных на дропе. Запись в БД делается ПОСЛЕ
успешного PUT на дроп (`:919-921`).

**Прогресс** считается ТОЛЬКО по таблице `stage_log` в `enrich.db`
(`stage_counts`, `:775-784`). Статусы батчей обновляются лениво — при открытии
страницы прогона (`refresh_batches`, `:926-968`, вызов из
`enrich_panel.py:178`): есть `result-<jid>.json` → «готов»/«ошибка» и результат
УДАЛЯЕТСЯ с дропа; есть `job-<jid>.json` → «в очереди»; ни того ни другого →
«выполняется».

Свои таблицы панель создаёт сама (`_PANEL_SCHEMA`, `panel_core.py:639-657`):
`enrich_runs`, `enrich_run_rows`, `enrich_run_batches`. Таблицы обогащения
(`companies`, `emails`, `stage_log`) она только читает — их ведёт `enrich_db.py`.

**Страница «База»** (`/base`): читает `obzvon-index.db` read-only, фильтры
комбинируются AND (`ObzvonDB._where`, `:349-379`): выручка от/до **в млн ₽**
(умножается на 1e6, `:354`), хвост N по `rowid`, регион (подстрока,
регистронезависимо через питон-функцию `panel_contains`, `:332-336`),
направление `kc|meyer`, почта есть/нет, сайт есть/нет. Выручка разбирается
на лету SQL-функцией `panel_money` поверх `COALESCE(NULLIF(revenue_rub,''), revenue)`
(`:244`, `parse_money` `:219-236`) — пересобирать индекс не нужно.
50 строк на страницу (`BASE_PER_PAGE`, `:239`).

### 3.5 Операции управления панелью через раннер

Это не отдельные ALLOW-задачи, а **операции внутри `enrich_contacts.py`**,
вызываемые как `R.submit('enrich_contacts', {'op': ..., ...})`. Всего в файле
~60 таких `op` (`grep "args.get('op') =="`), из них к панели относятся:

| `op` | Что делает | Строка |
|---|---|---|
| `panel_file_put` | положить файлы в `C:\sender\...` (из дропа по имени или инлайн `b64`); режим `{get: путь}` читает файл в base64 без записи; старая версия бэкапится как `<dest>.bak-<ts>` | `enrich_contacts.py:5871` |
| `panel_py` | выполнить скрипт питоном панели | `:6229` |
| `panel_zip_deploy` | скачать zip с дропа, забэкапить `sender`+`web/dist`, стоп-распаковка-старт службы | `:6154` |
| `panel_env_set` | merge значений в `C:\sender\panel.env` + `nssm set AppEnvironmentExtra` + рестарт | `:5808` |
| `svc_probe` | статус службы, ключи env, хвост stderr-лога, HTTP-проба | `:6264` |
| `smtp_login_batch` | проверка логинов ящиков | `:5788` |

**`panel_py` — точная семантика** (`enrich_contacts.py:6229-6263`):

- `script` обязан начинаться с `c:\sender` (сравнение в нижнем регистре) и не
  содержать `..` (`:6235`), иначе `{'error': 'скрипт должен лежать под C:\\sender'}`;
- окружение = `os.environ` + пары из `C:\sender\panel.env` (комментарии после
  значения срезаются) (`:6239-6249`);
- интерпретатор — `C:\Program Files\Python311\python.exe`, фолбэк `sys.executable`
  (`:6250-6252`);
- рабочий каталог — `C:\sender` (`:6256`);
- аргументы скрипта берутся из ключа **`argv`**, не `args` (`:6254`);
- **таймаут = `int(args.get('timeout', 900))`** (`:6257`);
- возвращает `{op, rc, stdout_tail (6000), stderr_tail (3000)}`.

**Чем таймаут `panel_py` отличается от таймаута задания целиком:**

| Уровень | Значение | Кто убивает | Строка |
|---|---|---|---|
| Внутренний `subprocess` под `panel_py` | **900 с по умолчанию**, задаётся полем `args['timeout']` | `enrich_contacts.py` (сам op) — вернёт результат с `error`, задание при этом отработает штатно | `enrich_contacts.py:6257` |
| Задание раннера целиком | **1800 с** (`JOB_TIMEOUT`) | `job_runner.run_job` убивает ВЕСЬ процесс `enrich_contacts.py` и пишет `{'ok': false, 'error': 'timeout 1800s'}` | `job_runner.py:58,207-208` |
| Ожидание на стороне клиента | **1800 с** по умолчанию у `submit()` | никого не убивает, просто перестаёт ждать | `run_on_server.py:51,83` |

То есть `panel_py` по умолчанию сдаётся вдвое раньше, чем раннер, и это
осознанно: op успевает вернуть внятную ошибку вместо «timeout 1800s» без
диагностики. Задать `timeout` больше 1800 бессмысленно — раннер всё равно
срубит процесс раньше.

### 3.6 Скрипты выкатки

**`build_panel_update.sh`** (песочница, bash, `set -euo pipefail`):
`REPO` вычисляется как два уровня вверх от скрипта (`:16`), стейджинг в
`${TMPDIR:-/tmp}/panel-build` (`:19`). Питон-пакет собирается через `find`
(rsync в песочнице нет, `:33-38`), исключая `web/`, `tests/`, `__pycache__`.
Фронт кладётся **только при `WITH_WEB=1`** и **всегда пересобирается**
(`npm install && npm run build`), готовый `dist` не берётся никогда — после
инцидента 26.07, когда старый dist из репозитория раскатали поверх боевого и
получили белый экран (`:40-69`). Есть проверка, что `index.html` ссылается
только на существующие в `dist` ассеты (`:57-63`). В архив кладётся
`UPDATE-MANIFEST.txt` с укороченными sha256 (`:72-74`).
Обзвон собирается из `seo-texts/sender-patches/obzvon-pagination/`, имена с
двойным подчёркиванием разворачиваются в подкаталоги (`api__routes_obzvon.py`
→ `api/routes_obzvon.py`, `:84-95`).

**`update-panel.ps1`** (сервер): служба `SenderPanel`, health
`http://127.0.0.1:8091/api/health`, архив с
`https://parsercompressor.online/drop/panel-update.zip`. Архив меньше 10000
байт → выкатка отменяется (`:46`). Бэкап в `C:\sender\_bak-panel-<yyyyMMdd-HHmmss>`.
Живость = ЛЮБОЙ ответ не-5xx (401 — штатная Basic-авторизация, `:29-39`);
10 попыток по 3 с (`:81-85`). Дополнительно сверяется фронт: все `/assets/...`
из `index.html` должны существовать в `dist` (`:89-103`). Не поднялось или
фронт битый → автоматический откат из бэкапа (`:120-136`), exit 1.

**`update-obzvon.ps1`** (сервер): служба `obzvon`, каталог `C:\seostat\app`,
health `http://127.0.0.1:8012/obzvon/kc` (маршруты смонтированы под `/obzvon`
даже локально, `:11-13`), архив меньше 500 байт → отмена (`:44`). Бэкап
выборочный — копируются только те файлы, которые архив перезапишет
(`:47-63`). Откат — покомпонентное копирование обратно (`:92-95`).

Оба `.ps1` должны храниться в UTF-8 **с BOM**: PowerShell 5.1 без BOM ломается
на кириллице в парсере (`update-panel.ps1:15-16`, `update-obzvon.ps1:14`).

---

## 4. Данные и где они лежат

### В песочнице (репозиторий)

| Путь | Что |
|---|---|
| `seo-texts/server/core396.json` | 396 компаний ядра центробежных (in git) |
| `seo-texts/server/refail_companies.json` | список для `launch_refail.py` (in git) |
| `seo-texts/server/sales_base.json` | база продажников, 1.1 МБ — **в `.gitignore`**, лежит локально как скачанная копия |
| `seo-texts/server/runner-secrets.env` | ключница — в `.gitignore`, **в этой песочнице отсутствует** |
| `seo-texts/server/.runner-seen.json`, `job-*.json`, `result-*.json`, `*.out` | служебное, в `.gitignore` |
| `seo-texts/server/_ops_*.py` | одноразовые скрипты, которые кладутся на сервер в `C:\sender\_ops\` и запускаются через `panel_py` (пиксель, Caddy, трекинг) |
| `seo-texts/server/*.md` | `RUNNER-SETUP.md`, `PANEL-DEPLOY.md`, `ENRICH-SALES-BASE-PROMPT.md`, `NIGHT-RUN-STATUS.md`, `ENRICH-ROADMAP.md` |

### На сервере владельца (по коду и документации, не проверял глазами)

| Путь | Что |
|---|---|
| `C:\sender\` | корень; рабочий каталог службы `SenderPanel` |
| `C:\sender\server\` | раннер: `job_runner.py`, `enrich_contacts.py`, `runner-secrets.env` |
| `C:\sender\enrich_panel\` | панель обогащения |
| `C:\sender\enrich.db` | SQLite обогащения: `companies`, `emails`, `stage_log`, + таблицы панели |
| `C:\sender\obzvon-index.db` | индекс базы обзвона (~161 761 юрлицо по `enrich_panel/README.md:35`) |
| `C:\sender\panel.env` | секреты панели рассыльщика (пароли ящиков) |
| `C:\sender\enrich_uploads\` | загруженные через панель файлы |
| `C:\sender\_ops\` | одноразовые скрипты для `panel_py` |
| `C:\seostat\app\` | панель обзвона (служба `obzvon`, порт 8012) |
| `C:\seostat\drop\drop-storage\` | хранилище дропа и тяжёлые исходники (`ENRICH-SALES-BASE-PROMPT.md:57-58`) |
| `<DIR>/<script>.out` | лог detached-процесса из `spawn_campaign` (`job_runner.py:182`) |

### Живое состояние дропа на момент сверки (read-only `list`, 2026-07-27 ~15:20 UTC)

- всего файлов: **826**;
- `job-*.json` (невыполненные задания): **55**, из них **29 панельных**
  (`job-1785080855-r1-base-b*.json`, все со временем 2026-07-26 15:47) и 26
  лаунчерных/сессионных;
- `result-*.json` (незабранные результаты): **56**;
- `runner-secrets.env` на дропе присутствует — отсюда `run_on_server`
  подтягивает `JOB_SECRET`.

Проверил содержимое одного панельного задания: `id=1785080855-r1-base-b136`,
`task=enrich_contacts`, 8 компаний, `sig` длиной 64 символа,
`stream_file=enrich_panel_run1.jsonl`, `source=panel-run1` — ровно то, что
строит `_BasePipeline.build_args` (`panel_core.py:500-518`).

**Вывод: панель обогащения РАЗВЁРНУТА и использовалась** — на дропе лежат её
задания прогона №1. Это не мёртвый код.

---

## 5. Ограничения и грабли

1. **Тяжёлые задания идут строго по одному.** Любой батч
   `enrich_contacts` со списком `companies` попадает в heavy-пул из 1 воркера
   (`job_runner.py:239-246,326`). 29 панельных батчей по 8 компаний = очередь
   на часы; 625 батчей (прогон на 5000 строк) — на сутки. Об этом честно
   написано в `enrich_panel/README.md:236-239`.

2. **Джобы копятся на дропе.** Задание удаляется только после исполнения
   (`job_runner.py:268`). Если клиент отвалился по таймауту и переотправил
   порцию, старая порция всё равно останется в очереди и когда-нибудь
   выполнится повторно. На момент сверки на дропе 55 неисполненных заданий,
   самые старые — от 2026-07-26 15:47.

3. **`seen` защищает от повторного запуска, но не от зависания.** Имя
   попадает в seen ДО скачивания (`:285-286`), а «v3-сброс» невыполненных
   работает ТОЛЬКО при старте службы (`:313-324`). Если процесс раннера убит
   между взятием задания и его удалением, задание останется на дропе и в seen
   одновременно — и будет игнорироваться до `Restart-Service rusprom-runner`.

4. **Коллизия id при `wait=False`.** `f'{time}-{pid}'` (`run_on_server.py:46-48`):
   два submit'а в одну секунду из одного процесса перезапишут друг друга.
   `launch_top1000.py:44` лечит это `sleep(1.5)`; в других лаунчерах защиты
   нет, но они шлют синхронно (`wait=True`), так что коллизия маловероятна.

5. **`JOB_SECRET` пустой = подписи нет.** `sig_ok` вернёт True
   (`job_runner.py:136-138`). Проверять по логу старта службы:
   должно быть `подпись=вкл`.

6. **`panel_py` принимает аргументы в ключе `argv`, а не `args`.**
   `enrich_contacts.py:6254`. Документ `ENRICH-SALES-BASE-PROMPT.md:35`
   показывает пример с `'args': [...]` — такой ключ будет молча
   проигнорирован, скрипт запустится без аргументов.

7. **`panel_file_put` и `panel_py` жёстко ограничены `C:\sender`**
   (`enrich_contacts.py:5895,6235`). Панель обзвона в `C:\seostat\app` ими
   недостижима — только через дроп и `update-obzvon.ps1`
   (`build_panel_update.sh:6-8`).

8. **`svc_probe` и `panel_zip_deploy` жёстко проверяют HTTP на порту 8091**
   (`enrich_contacts.py:6220` в `panel_zip_deploy`, `:6315` в `svc_probe`),
   то есть панель рассыльщика. Для
   `EnrichPanel` (8013) параметр службы передать можно, а HTTP-проба всё равно
   пойдёт на 8091 и покажет чужой результат.

9. **`/list` дропа не фильтрует имена по `SAFE_NAME`, а `GET`/`PUT`/`DELETE` —
   фильтруют** (`drop_server.py:11,21-28` против `:32,37,50`). В выдаче реально есть файл
   `New Text Document.txt` с пробелами: он виден в списке, но скачать его
   через маршрут нельзя (400).

10. **401 от панелей — это норма, а не падение.** Оба `.ps1` считают живым
    любой ответ не-5xx. Инцидент: скрипт принял 401 за отказ и откатил рабочую
    выкатку (`update-panel.ps1:10-13`, `PANEL-DEPLOY.md:94-98`).

11. **`job_runner.py` руками не запускать.** Служба уже крутит его; два
    экземпляра = каждый job исполняется 2-3 раза (`PANEL-DEPLOY.md:108-113`).
    Диагноз:
    `Get-CimInstance Win32_Process | ? {$_.CommandLine -like '*job_runner*'}`.

12. **Батч должен помещаться в 1800 с.** `launch_core_enrich.py` шлёт все 396
    компаний одним заданием и ждёт 3000 с — задание гарантированно умрёт на
    JOB_TIMEOUT раньше. Об этом прямо написано в
    `launch_core_chunked.py:5-14` как о причине его существования.

13. **Модель извлечения по умолчанию.** Для обычного списка `companies` —
    `claude-fable-5`, для `mass_base`/`news_enrich` — `claude-haiku-4-5`
    (`enrich_contacts.py:6649-6650`). Автоподмена мёртвых моделей есть только в
    `gen_provider.resolve_model`; серверный путь шлёт модель как есть, поэтому
    лаунчеры задают `extract_model` явно (`launch_sales_enrich.py:89`).

14. **`opo_batch` и `zakupki_mass` не пишут стадию в `stage_log`** — их
    прогресс в панели всегда занижен, а «Докинуть» перезапускает работу
    (для ОПО это повторный дельфин-прогон). `enrich_panel/README.md:87-93,247-252`.

15. **`preflight_panel.py` — не «локальная проверка».** Он ставит два задания
    раннеру и тратит время сервера (`:56-61`). При боевом прогоне его лучше не
    дёргать.

---

## 6. Что сломано или устарело

- **`RUNNER-SETUP.md:16-20` устарел**: там сказано, что allowlist содержит
  «`verify_company`, `ping`». Фактически в `job_runner.py:62-73` девять задач
  плюс `pull` и `spawn_campaign`. Также `:39` предлагает
  `C:\Python311\python.exe`, тогда как `PANEL-DEPLOY.md:10` фиксирует боевой
  путь `C:\Program Files\Python311\python.exe`.

- **`_SEM_HEAVY` (`job_runner.py:234`) — мёртвый код**: создаётся и нигде не
  используется. Единственное вхождение имени в файле — строка объявления.

- **`launch_core_enrich.py` — фактически устаревший лаунчер.** Его заменил
  `launch_core_chunked.py`, который прямо перечисляет два дефекта предшественника
  (`:4-18`): одно задание на 396 компаний при JOB_TIMEOUT=1800 и отсутствие
  явной `extract_model`. Импортов у него нет — он вызывается только руками.
  Формально рабочий, но запускать его — заведомо получить таймаут.

- **`mass_enrich_loop.sh` дублирует `mass_enrich_loop.py`** с другими
  дефолтами (`pace 1.5..3.5` против `0.5..1.5`, CAP 400 против 40) и без
  счётчика подряд идущих сбоев. `.py`-версия новее по логике (орфан-толерантность,
  `MAX_FAIL=4`, `:23,50-52`). Какой из них «канон» — из кода не следует.

- **`ENRICH-SALES-BASE-PROMPT.md:35` («максимум ~560 секунд на процесс»)** —
  это соглашение, а не ограничение кода: `panel_py` берёт `args['timeout']` с
  дефолтом 900 (`enrich_contacts.py:6257`), а потолок задаёт JOB_TIMEOUT=1800.
  Там же неверный ключ `args` вместо `argv` (см. грабли, п.6).

- **Все `launch_*.py`, `mass_enrich_loop.*`, `preflight_panel.py`,
  `build_panel_update.sh` — точки входа без вызывающих**: ни один другой модуль
  их не импортирует (проверено `grep` по всему репо). Единственное исключение —
  `launch_sales_enrich.build_args`, который импортирует `launch_core_chunked.py:29`.
  Это НЕ мёртвый код: их запускает человек/сессия командой. Но и автоматики,
  которая бы их дёргала, в репозитории нет.

- **`run_on_server.py` используют, помимо лаунчеров, ещё три модуля вне этой
  области**: `seo-texts/night_orchestrator.py:52`, `seo-texts/heartbeat.py:15`,
  а `seo-texts/server/news_schedule/news_cron.py:46` импортирует `job_runner`
  только ради побочного эффекта — загрузки `runner-secrets.env`.
  `night_orchestrator.py:14` и `heartbeat.py:7` читают `JOB_SECRET` из
  `/tmp/rs.env`, которого в этой песочнице нет — то есть оба сейчас упадут при
  запуске.

- **Тесты панели в песочнице проходят не полностью — из-за отсутствия
  зависимостей, а не из-за кода.** `python3 -m pytest tests/ -q` в
  `seo-texts/server/enrich_panel`: **43 passed, 2 failed, 20 errors**;
  все падения — `ModuleNotFoundError: No module named 'fastapi'` (21 шт.) и
  `'openpyxl'` (1 шт.). Чистая логика (`panel_core`) проходит целиком.
  README заявляет 65 тестов — 43+2+20 = 65, сходится.

- **Скрипта, собирающего `enrich-panel.zip`, в репозитории нет.**
  `build_panel_update.sh` пакует только `sender/` и патчи обзвона; ссылок на
  `enrich-panel.zip` или `EnrichPanel` вне каталога `enrich_panel/` нет
  (проверено `grep` по всему репо). Установка панели обогащения описана в
  `enrich_panel/README.md:109-140` как ручная процедура.

---

## 7. Что не проверено

Помечаю честно — по этим пунктам новой сессии стоит проверять самой.

- **НЕ ПРОВЕРЕНО: живое состояние сервера.** Я не запускал ни одного задания
  раннера, не делал `up`/`del` на дропе и не обращался к провайдерскому API
  (прямой запрет в задании — идёт боевое обогащение). Все утверждения о
  поведении сервера — из чтения кода, кроме листинга дропа.
- **НЕ ПРОВЕРЕНО: версия кода НА СЕРВЕРЕ.** В репозитории и на сервере лежат
  разные копии `job_runner.py`/`enrich_contacts.py`, они синхронизируются
  вручную через `pull`/`panel_file_put`. `PANEL-DEPLOY.md:83-92` фиксирует
  случай 26.07, когда репозиторий отстал от боя на 11 модулей. **Значения
  JOB_TIMEOUT/WORKERS/ALLOW я привёл по репозиторию; в боевом файле они могут
  отличаться.** Проверять — `panel_file_put` в режиме
  `{'get': r'C:\sender\server\job_runner.py'}`.
- **НЕ ПРОВЕРЕНО: реальные значения env службы.** `RUNNER_WORKERS`,
  `RUNNER_HEAVY`, `RUNNER_JOB_TIMEOUT`, `RUNNER_POLL_SEC` могут быть заданы в
  `AppEnvironmentExtra` службы или в `runner-secrets.env` на сервере и
  перебить дефолты. Файла `runner-secrets.env` в песочнице нет; смотреть
  через `svc_probe` (он отдаёт только ИМЕНА ключей, не значения).
- **НЕ ПРОВЕРЕНО: почему 29 панельных заданий висят с 26.07 15:47.**
  ПРЕДПОЛОЖЕНИЕ: они в heavy-пуле (1 воркер) и/или числятся в `.runner-seen.json`
  после убийства процесса, а «v3-сброс» отрабатывает только на старте службы.
  Это гипотеза из чтения кода, не диагноз. Проверить можно логом службы и
  содержимым `.runner-seen.json` на сервере.
- **НЕ ПРОВЕРЕНО: запущена ли служба `EnrichPanel` СЕЙЧАС** и отвечает ли
  `https://parsercompressor.online/enrich/`. Доказано только то, что панель
  когда-то работала и поставила задания прогона №1.
- **НЕ ПРОВЕРЕНО: конфигурация обратного прокси для `/drop`.** `drop_server.py`
  слушает `127.0.0.1:8787`, наружу его выставляет что-то ещё (по косвенным
  признакам — Caddy: в `seo-texts/server/` есть `_ops_caddy_*.py`). Самого
  конфига я в репозитории не нашёл. Утверждать «его нет» не берусь.
- **НЕ ПРОВЕРЕНО: содержимое `enrich.db`, `obzvon-index.db`, `stage_log`.**
  Живых БД я не видел. Все названия таблиц и колонок взяты из кода панели и
  фикстур тестов (`enrich_panel/tests/conftest.py:21-31`). Реальная схема на
  сервере может содержать больше колонок.
- **НЕ ПРОВЕРЕНО: что делает `enrich_contacts.py` внутри** — файл 418 КБ,
  я читал только операции, относящиеся к панели и раннеру (`panel_py`,
  `panel_file_put`, `panel_env_set`, `svc_probe`, `panel_zip_deploy`) и хвост
  `main()`. Остальные ~55 `op` не разбирал.
- **НЕ ПРОВЕРЕНО: `verify_company.py`, `browser_probe.py`, `dolphin_pool.py`,
  `lead_scoring.py`, `news_scan.py`, `send_campaign.py`, `enrich_db.py`** —
  они только упомянуты как элементы ALLOW/PULL_ALLOW, содержимое не читал.
- **НЕ ПРОВЕРЕНО: `_ops_*.py`** — читал только шапку `_ops_pixel_e2e.py`.
  ПРЕДПОЛОЖЕНИЕ: все они предназначены для доставки в `C:\sender\_ops\` через
  `panel_file_put` и запуска через `panel_py`; ни один из них не импортирует
  `run_on_server` (проверено `grep`).
- **НЕ ПРОВЕРЕНО: работают ли `.ps1` на сервере сейчас.** PowerShell я не
  запускал; BOM-кодировку файлов в git не проверял побайтово.
- **НЕ ПРОВЕРЕНО: собирается ли фронт** (`WITH_WEB=1` → `npm install && npm run build`)
  в текущей песочнице.
