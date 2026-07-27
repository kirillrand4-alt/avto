# 13. Инфраструктура, окружение и доступы

Документ описывает **не бизнес-логику, а «где что подключено»**: все переменные
окружения репозитория, кто их читает, что ломается без них; раскладку каталогов
и служб на сервере владельца; файлы-ключницы; провайдерский шлюз и подмену
моделей.

Всё проверено по коду на ветке `claude/seo-texts-enrichment-prompt-449lyw`
(рабочее дерево `/home/user/avto`, дата 2026-07-27). Ссылки вида `файл:строка` —
кликабельные координаты в репозитории. Живую БД и живое окружение сервера я
**не** видел (сессия читает только код + дроп) — всё серверное помечено в
разделе «Что не проверено».

> **Ревизия скептика (2026-07-27).** Документ перепроверен по коду вторым
> проходом. Исправленные места помечены по тексту как
> `[исправлено скептиком]` / `[дополнено скептиком]` / `[уточнено скептиком]`.
> Самые важные правки: §1 (набор переменных песочницы), §3.3 (заголовки
> `verify_company` и координаты транспортного докстринга), §4.1 (пустой дефолт
> `DROP_URL` — гейты вместо ошибки), §4.5 (`ENRICH_DB` не читается
> `dryrun_basemerge.py`), §6.4 и §7.2 (координаты `resolve_model` и неверные
> примеры подмены модели), §7 (файл выкатки `services__callbase.py`),
> §8 п. 7 (число почтовых ящиков — ответ нашёлся в невыгруженной ветке
> `origin/claude/persona-prompt-seo-sender-vi4tcq`).

---

## 1. Что это и зачем

В репозитории живут два разных проекта (см. `CLAUDE.md`), и оба общаются с одним
Windows-сервером владельца. Прямого SSH/RDP у сессии нет. Вместо него —
три контура:

1. **Песочница Claude** (то, где вы читаете этот файл). Из **проектных**
   переменных сюда прокинуты четыре: `DROP_URL`, `DROP_TOKEN`,
   `PROVIDER_API_KEY`, `PROVIDER_BASE_URL`. Проверено фактически
   (`python3 -c "import os; ..."`) — `JOB_SECRET`, `XMLRIVER_*`,
   `DOLPHIN_TOKEN`, `CAPMONSTER_KEY`, `DADATA_TOKEN`, `VK_TOKEN`, `ENRICH_DB`,
   `SENDER_DIR`, `PROXY_URL*` в песочнице **отсутствуют**.
   **[исправлено скептиком]** формулировка «ровно четыре переменные» была
   неверной: в песочнице заданы ещё как минимум две переменные из таблицы §4 —
   `HTTPS_PROXY`/`https_proxy`/`NO_PROXY` (их читают `fetch_playwright.py:15`,
   `sender/notify.py:9`) и `PLAYWRIGHT_BROWSERS_PATH` (`browser_probe.py:579`).
   Они приходят от инфраструктуры Claude, а не от владельца, но код проекта
   на них реагирует. Состояние проверено в моей сессии; у другой сессии набор
   может отличаться.
2. **Дроп** — HTTP-обменник плоских файлов на сервере
   (`https://parsercompressor.online/drop`, авторизация заголовком
   `X-Drop-Token`). Через него ходят данные, обновления кода, задания раннеру,
   а также сама ключница `runner-secrets.env`.
3. **Сервер владельца** (Windows, IP `91.206.14.169` по
   `server/ENRICH-SALES-BASE-PROMPT.md:4`). Там крутятся службы NSSM, там лежат
   боевые БД, там же реально задано полное окружение со всеми ключами.

Ключевая идея всей схемы: **секреты живут на сервере**, песочница получает
только `DROP_TOKEN` (доступ к файлам) и `PROVIDER_API_KEY` (доступ к LLM-шлюзу).
`JOB_SECRET` песочница при необходимости **скачивает** с дропа на лету
(`server/run_on_server.py:25-36`).

---

## 2. Точки входа и как запустить

### 2.1 «Проверь drop и провайдера»

Фраза владельца из `CLAUDE.md`. Точные команды:

```bash
# 1) дроп: должен вернуть JSON-массив файлов
bash /home/user/avto/seo-texts/server/drop_client.sh list

# 2) провайдер: короткий вызов
cd /home/user/avto/seo-texts && python3 -c "
import gen_provider as gp
c = gp.make_client()
m = gp.call(c, [{'role':'user','content':'ответь одним словом: работает'}])
print(m)
"
```

Проверено: `drop_client.sh list` отвечает, `runner-secrets.env` в листинге
присутствует. Провайдерский вызов **не выполнялся** — запрещён правилами сессий.
**[исправлено скептиком]** число файлов было указано как «827»; дроп живой и
число дрейфует — в моей проверке пришло **840**. Ориентироваться на конкретное
число нельзя, проверять надо сам факт ответа.

### 2.2 Клиент дропа

`server/drop_client.sh` (**13** строк — [исправлено скептиком], было «17»;
целиком читается за минуту):

```bash
bash seo-texts/server/drop_client.sh list                # GET  /list  -> JSON
bash seo-texts/server/drop_client.sh up   <file>         # PUT  /<basename>
bash seo-texts/server/drop_client.sh down <name> [dst]   # GET  /<name> -> файл
bash seo-texts/server/drop_client.sh del  <name>         # DELETE /<name>
```

`U="${DROP_URL:-https://parsercompressor.online/drop}"` (`drop_client.sh:5`) —
дефолт зашит; без `DROP_TOKEN` скрипт печатает «нет DROP_TOKEN в окружении» и
выходит с кодом 1 (`drop_client.sh:6`).

### 2.3 Раннер заданий (руки на сервере)

```bash
cd /home/user/avto/seo-texts/server           # ОБЯЗАТЕЛЬНО из этого каталога
python3 run_on_server.py ping '{"hi":1}'
python3 run_on_server.py verify_company '{"companies":[{"name":"КАО Азот","inn":"4205000908"}]}'
```

Или как модуль (для длинных задач):

```python
import sys; sys.path.insert(0, '.')
import run_on_server as R
res = R.submit('enrich_contacts', {...}, wait=True, poll=15, timeout=600)
```

Сигнатура: `submit(task, args, wait=True, poll=15, timeout=1800)`
(`server/run_on_server.py:50` — [исправлено скептиком], было `:51`). Механика:
кладёт `job-<unixtime>-<pid>.json` на дроп с HMAC-подписью, опрашивает `/list`
раз в `poll` секунд, забирает `result-<id>.json`, удаляет его
(`run_on_server.py:60-82` — [исправлено скептиком], было `:61-83`).

Allowlist задач раннера (`server/job_runner.py:62-73`):
`verify_company`, `enrich_contacts`, `browser_probe`, `dadata`, `news_scan`,
`enrich_db`, `dolphin_pool`, `lead_scoring`, `ping`.
Плюс две спец-задачи, обрабатываемые до allowlist: `pull` (самообновление кода,
`job_runner.py:151-173`) и `spawn_campaign` (`job_runner.py:197-198`).

### 2.4 Панели и службы (запускаются на сервере, не из песочницы)

| Служба NSSM | Что это | Команда установки | Порт |
|---|---|---|---|
| `rusprom-runner` | поллер заданий, `C:\sender\server\job_runner.py` | `server/RUNNER-SETUP.md:39-45` | нет |
| `SenderPanel` | панель рассыльщика, `C:\sender` | `server/PANEL-DEPLOY.md:9-16` | 8080/см. Caddy |
| `EnrichPanel` | панель обогащения, `C:\sender\enrich_panel` | `server/enrich_panel/README.md:136-139` | 8013 |
| `SenderPixel` | сервер пикселя/отписки (`sender.unsub_server`) | `server/_ops_pixel_deploy.py:99-106` | 8082 |
| `obzvon` | панель обзвона, `C:\seostat\app` | `server/update-obzvon.ps1:21` | 8012 (`update-obzvon.ps1:22`) |
| `DropServer` | сам обменник (Flask/waitress) | упомянута в `server/PANEL-DEPLOY.md:107` | 8787 (`drop_server.py:59`) |
| `avto-panel` | панель корневого проекта, `C:\seostat\avto` | `RUNBOOK.md:17-19` | 8090 |

**[исправлено скептиком]** в строке `avto-panel` стояла ссылка `RUNBOOK.md:20-21` —
на этих строках описаны `src/run.mjs` и `src/login.mjs`, а служба `avto-panel`
(NSSM) названа на `RUNBOOK.md:17-19`. Порт `obzvon` взят из
`update-obzvon.ps1:22` (`$Health`), на `:21` — только имя службы.
Колонка «Команда установки» для `SenderPanel` указывает на таблицу путей
(`PANEL-DEPLOY.md:9-16`), а не на команду `nssm install`: готовой команды
установки панели в репозитории нет.

Планировщик Windows: задача `RuspromNewsScan`, ежедневно 07:00 локального
времени, обёртка `C:\sender\server\news_cron_task.cmd`
(`server/news_schedule/setup-news-schedule.ps1:23-42`).

---

## 3. Как устроено внутри

### 3.1 Цепочки загрузки секретов

Секрет можно получить **четырьмя** разными путями, и они не эквивалентны.

**(а) Раннер — `job_runner._load_env_file()`** (`server/job_runner.py:35-52`).
Читает `runner-secrets.env` из каталога самого скрипта. Правила: строки `#`
пропускаются; значения, начинающиеся с `<` (плейсхолдеры), пропускаются;
**уже заданное в окружении не перетирается** (`job_runner.py:48`). Вызывается
на импорте модуля (`:52`) — то есть достаточно `import job_runner`, чтобы
секреты попали в `os.environ` (этим пользуется `news_cron.py:45-48`).

**(б) Панель обогащения — `panel_core.load_runner_env()`**
(`server/enrich_panel/panel_core.py:58-73`). Та же семантика, но путь берётся из
env `RUNNER_ENV` с дефолтом `C:\sender\server\runner-secrets.env`
(`panel_core.py:63`). Вызывается в `create_app()` (`enrich_panel.py:69`).

**(в) Конвейер обогащения — `enrich_contacts._read_secret(key)`**
(`server/enrich_contacts.py:52-97`). Самая хитрая. Смотрит **два** файла:

```python
_SECRET_FILES = (<каталог enrich_contacts.py>/runner-secrets.env,
                 r'C:\seostat\drop\drop-storage\runner-secrets.env')
```
(`enrich_contacts.py:47-49`). Порядок: `os.environ` → первый файл → второй файл.
**Исключение для `DOLPHIN_TOKEN`**: собираются кандидаты из всех источников и
выбирается **самый свежий по полю `iat` в JWT** (`enrich_contacts.py:56-78`).
Причина в комментарии: env службы затенял обновлённый владельцем файл старым
удалённым токеном → вечный 401.

Через `_read_secret` идут только: `DADATA_TOKEN`, `DOLPHIN_TOKEN`, `VK_TOKEN`,
`VK_TOKEN_USER`. Всё остальное в `enrich_contacts.py` читается обычным
`os.environ.get`.

**(г) Генератор текстов — `gen_provider.env()`** (`seo-texts/gen_provider.py:118-133`).
Читает файл `seo-texts/.env` (его в репозитории **нет** — проверено `ls`, он в
`.gitignore:6`), затем **переопределяет** значениями из `os.environ` для четырёх
ключей: `PROVIDER_API_KEY`, `PROVIDER_BASE_URL`, `DROP_URL`, `DROP_TOKEN`
(`gen_provider.py:129-132`).

**(д) Корневой проект — свой мини-загрузчик `.env`** (`web/server.mjs:23-30` —
[исправлено скептиком], было `:24-31`), без зависимостей, регуляркой
`/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/i` (флаг `i` в документе был потерян, поэтому
ключи в нижнем регистре тоже подхватываются), тоже не перетирает уже заданное.

### 3.2 Подпись заданий (JOB_SECRET)

Канон подписи (обе стороны обязаны совпадать байт-в-байт):

```python
canon = json.dumps({'id': ..., 'task': ..., 'args': ..., 'ts': ...},
                   sort_keys=True, separators=(',', ':'), ensure_ascii=False)
sig = hmac.new(JOB_SECRET.encode(), canon.encode(), hashlib.sha256).hexdigest()
```

Стороны: `run_on_server.py:54-59` ([исправлено скептиком], было `:55-60`),
`job_runner.canonical/sig_ok:127-141`,
`panel_core` (панель обогащения ставит задания тем же форматом,
`enrich_panel/README.md:12-17`).

**Важная асимметрия:** если `JOB_SECRET` на раннере **не задан**, подпись
вообще не проверяется (`job_runner.py:136-138`), защищает только allowlist.
Если задан — задание без валидной `sig` удаляется с дропа без исполнения
(`job_runner.py:295-300`).

### 3.3 Провайдерский шлюз и подмена моделей

Шлюз: `PROVIDER_BASE_URL` (дефолт `https://router.cheap`), Anthropic-совместимый
`/v1/messages`. Ключ — `PROVIDER_API_KEY`, заголовок `x-api-key`.

**Заголовки-обманки WAF.** SDK-клиент (`gen_provider.py:138-145`) и сырой
SSE-путь (`gen_provider.py:211-215`) шлют `User-Agent: curl/8.5.0` **и** пустые
`X-Stainless-*`. Причина в коде: WAF **самого шлюза** отклоняет дефолтные
заголовки anthropic-SDK. Развёрнутая честная оценка этой практики — в
`CLAUDE.md` (раздел про `PROVIDER_API_KEY`); каждая сессия решает сама,
выполнять ли вызовы.

**[исправлено скептиком]** было написано, что stdlib-путь
`verify_company._provider_call_stdlib` (`server/verify_company.py:88-90`) шлёт
то же самое. Обе части неверны:
- строки `verify_company.py:88-90` — это `_install_one` (установка socks-opener),
  к провайдеру отношения не имеют; заголовки собираются на
  `verify_company.py:186-189`;
- `X-Stainless-*` там **нет вообще** (`grep -n X-Stainless server/verify_company.py`
  даёт ноль вхождений). Набор ровно такой: `x-api-key`, `anthropic-version`,
  `content-type`, `accept: text/event-stream`, `User-Agent: curl/8.5.0`
  (+ `content-encoding: gzip` на chunked-пути).

**Мёртвые модели и автоподмена** (`gen_provider.py:222-241`):

```python
_DEAD_DEFAULT  = 'claude-fable-5,claude-opus-5'   # :223
_ALIVE_DEFAULT = 'claude-opus-4-8'                # :224

def resolve_model(model):                          # :228
    dead  = set(os.environ.get('PROVIDER_DEAD_MODELS', _DEAD_DEFAULT).split(','))
    alive = os.environ.get('PROVIDER_MODEL') or _ALIVE_DEFAULT
    return alive if (model in dead and model != alive) else model
```

Комментарий в коде (`gen_provider.py:218-222`) фиксирует замер 27.07.2026:
`fable-5` и `opus-5` отдают только ping-кадры до дедлайна; `opus-4-8` (2.0 с),
`haiku-4-5` (1.6 с), `sonnet-4-6` (1.9 с), `sonnet-5` (10 с) отвечают штатно.
Вернуть fable-5 — задать `PROVIDER_DEAD_MODELS=''`.

`resolve_model` вызывается **только** из `gen_provider._raw_stream`
(`gen_provider.py:258`). Кто ходит мимо — см. раздел «Грабли».

**Часы против зависшего стрима:**
`PROVIDER_STREAM_DEADLINE_SEC` (дефолт 420 с, `gen_provider.py:246`) — на весь
стрим; `PROVIDER_FIRST_TOKEN_SEC` (дефолт 90 с, `gen_provider.py:249`) — на
первый текстовый кадр. Без них зависший стрим не ловится read-таймаутом httpx:
каждый ping приходит вовремя, а текста нет никогда.

**Транспортная особенность сервера** (докстринг `_provider_call_stdlib`,
`verify_company.py:168-177`; реализация — `:186-218`. [исправлено скептиком]:
было `verify_company.py:71-78`, но там `_build_pool` — разбор `PROXY_URL*`):
маршрут сервера до шлюза душит большие однокусковые POST (>~2 КБ →
RemoteDisconnected через ~60 с). Рабочий путь — стриминг-ответ + gzip-тело
кусками по 1200 Б с паузами 0.15 с; фолбэк — прямой одно-POST.

---

## 4. ПОЛНАЯ таблица переменных окружения

Собрано грепом по `os.environ` / `os.getenv` / `process.env` / `_read_secret` /
`_env(` по всему репозиторию. Колонка «Нет значения» — что реально произойдёт
по коду.

### 4.1 Дроп и раннер (ядро инфраструктуры)

| Имя | Кто читает (файл:строка) | Зачем | Нет значения |
|---|---|---|---|
| `DROP_URL` | `drop_client.sh:5`; `job_runner.py:54`; `run_on_server.py:20`; `browser_probe.py:51`; `send_campaign.py:13`; `enrich_db.py:459`; `gen_provider.py:129`; ещё ~25 мест в `enrich_contacts.py`/`news_scan.py` | базовый URL обменника | в «клиентских» точках дефолт `https://parsercompressor.online/drop`; **но** в самочейн-путях дефолт пустой — см. поправку под таблицей |
| `DROP_TOKEN` | те же файлы; на серверной стороне — `drop_server.py:8` | заголовок `X-Drop-Token` | клиент: 401 от дропа. Сервер (`drop_server.py:18`): **все** запросы → 503 «DROP_TOKEN not set» |
| `DROP_DIR` | `drop_server.py:7`; `enrich_contacts.py:1996-1997` | каталог хранения файлов дропа; альтернативный путь к базовому CSV | `drop_server.py`: `<каталог скрипта>/drop-storage`. На бою фактически `C:\seostat\drop\drop-storage` (косвенно: `enrich_contacts.py:49`) |
| `JOB_SECRET` | `job_runner.py:56`; `run_on_server.py:22`; `enrich_panel.py:113`; загрузка в `panel_core.py:58-73` | HMAC-подпись заданий | раннер: подпись **не проверяется** (`job_runner.py:136-138`), защищает только allowlist. Клиент: шлёт задание без `sig`; если у раннера секрет есть — задание молча отбрасывается |
| `JOB_HMAC` | **только** `enrich_contacts.py:5191` | секрет для самочейна `zakupki_mass` | самочейн-задание уходит **без подписи** → раннер с заданным `JOB_SECRET` его отвергнет. Похоже на опечатку вместо `JOB_SECRET` (см. §6) |
| `RUNNER_ENV` | `panel_core.py:63` | путь к ключнице для панели обогащения | `C:\sender\server\runner-secrets.env` |
| `RUNNER_POLL_SEC` | `job_runner.py:57` | пауза между опросами дропа | 20 с |
| `RUNNER_JOB_TIMEOUT` | `job_runner.py:58` | таймаут одного задания | 1800 с (30 мин) |
| `RUNNER_WORKERS` | `job_runner.py:233` | воркеров общего пула | 8 |
| `RUNNER_HEAVY` | `job_runner.py:234, 326` | воркеров «тяжёлого» пула (xmlriver/dolphin) | 1 |

**[исправлено скептиком] про пустой дефолт `DROP_URL`.** В документе стояло:
«дефолт пустой в `news_scan.py:72`, `enrich_db.py:459`, `enrich_contacts.py:2196`
→ URL вида `/list` → ошибка запроса». Неточно дважды:

1. Мест с пустым дефолтом заметно больше трёх:
   `news_scan.py:72, 122, 162, 184, 1048`;
   `enrich_contacts.py:2196, 2387, 2579, 2721, 3293, 3495, 4010, 4030, 4076,
   4436, 4777, 4946, 5189`; `enrich_db.py:459`.
2. В двух из трёх названных мест ошибки запроса **не будет**: сразу после чтения
   стоит явный гейт `if not (drop and tok): return 'no-drop-env'`
   (`news_scan.py:75-76`, `enrich_contacts.py:2200-2201`) — самочейн просто
   не поставится и вернёт `no-drop-env`. Без гейта работает `enrich_db.py:459`
   (op `snapshot`), но и он завёрнут в `try/except` и отдаёт
   `{'ok': false, 'error': …}` (`enrich_db.py:474-475`), а не падает.

### 4.2 Провайдерский LLM-шлюз

| Имя | Кто читает | Зачем | Нет значения |
|---|---|---|---|
| `PROVIDER_API_KEY` | `gen_provider.py:129` (через `env()`); `verify_company.py:178, 221`; `enrich_contacts.py:1422, 2982, 3021, 3071` | ключ шлюза | `gen_provider.make_client()` падает **KeyError**, а не понятным сообщением (`gen_provider.py:144`). `verify_company._provider_call_stdlib` возвращает `None` (`:180-181`). `enrich_contacts.extract_roles` тихо уходит в regex-фолбэк (`:1422-1425`) |
| `PROVIDER_BASE_URL` | `gen_provider.py:129`; `verify_company.py:179`; `enrich_contacts.py:2983, 3022, 3072` | адрес шлюза | у `verify_company`/`enrich_contacts` дефолт `https://router.cheap`; у `gen_provider` дефолта **нет** → KeyError |
| `PROVIDER_MODEL` | `gen_provider.py:233`; `verify_company.py:143` | **два разных смысла!** В `gen_provider` — модель-**замена** для мёртвых. В `verify_company` — модель **по умолчанию** для extract | `gen_provider`: `claude-opus-4-8`. `verify_company`: `claude-fable-5` |
| `PROVIDER_DEAD_MODELS` | `gen_provider.py:231-232` | список мёртвых моделей через запятую | `claude-fable-5,claude-opus-5` |
| `PROVIDER_STREAM_DEADLINE_SEC` | `gen_provider.py:246` | часы на весь стрим | 420 с |
| `PROVIDER_FIRST_TOKEN_SEC` | `gen_provider.py:249` | часы на первый текстовый кадр | 90 с |
| `PROVIDER_CLIENT_DIR` | `verify_company.py:124` | где искать `gen_provider.py` для импорта | порядок перебора: сам `PROVIDER_CLIENT_DIR` → `<каталог скрипта>/..` → `C:\sender` → `<каталог скрипта>` (`:124-127`, [уточнено скептиком] было `:124-126` и без первого кандидата); не нашёл → `GP = None`, работает stdlib-путь |
| `REVIEW_MODEL` | `eng_fix_review.py:37` | модель ревью | `claude-fable-5` |

**[дополнено скептиком] про `PROVIDER_MODEL` в `verify_company`.** Строка `:143`
задаёт `_PROVIDER_MODEL`, но он влияет **только** на stdlib-путь
(`_provider_call_stdlib`, `verify_company.py:183`). Основная функция
`extract_via_provider` при найденном `gen_provider` вызывает
`GP._raw_stream(..., 'claude-fable-5', 800, thinking=False)` с **жёстко зашитой**
моделью (`verify_company.py:237-238`) — `_PROVIDER_MODEL` там игнорируется
(подмена всё равно случится, но уже внутри `resolve_model`).

### 4.3 Поиск, справочники, капча, прокси

| Имя | Кто читает | Зачем | Нет значения |
|---|---|---|---|
| `XMLRIVER_USER` | `enrich_contacts.py:557, 948, 1026, 1114, 3511, 3549, 5591, 6626`; `news_scan.py:485, 1222, 1248` | логин SERP-API xmlriver | `find_site_via_xmlriver` возвращает `(None, 'no-xmlriver-key', {})` (`enrich_contacts.py:557-560`) — поиск сайта отваливается молча |
| `XMLRIVER_KEY` | те же строки | ключ xmlriver | то же |
| `XMLRIVER_CHANNELS` | `enrich_contacts.py:23` | размер семафора параллельных запросов к xmlriver | 4. **Читается при импорте модуля** — задавать из песочницы бесполезно (см. §6) |
| `XMLRIVER_TRIES` | `enrich_contacts.py:24` | число лёгких ретраев | 3 |
| `DADATA_TOKEN` | `dadata_client.py:13`; `news_scan.py:1368`; `news_schedule/news_cron.py:195`; через `_read_secret` — `enrich_contacts.py:612, 2532, 2742, 2803, 3698, 4295, 5533, 5573, 5996` | резолв «имя → ИНН», реквизиты | пустая строка; вызовы DaData отваливаются (в `news_scan` есть fallback на `args['dadata_token']`) |
| `CAPMONSTER_KEY` | `verify_company.py:37`; `browser_probe.py:92, 162` | решение Turnstile/SmartCaptcha | путь через капчу не работает; страница-челлендж не пробивается |
| `TWOCAPTCHA_KEY` | `browser_probe.py:240` | альтернативный решатель капчи | fallback на `RUCAPTCHA_KEY`, затем пусто |
| `RUCAPTCHA_KEY` | `browser_probe.py:240` | синоним 2captcha | пусто |
| `PROXY_URL` | `verify_company.py:77-79`; `browser_probe.py:41-42, 610` | статичный прокси (1 IP) | пул пуст → `PROXY_MODE='none'`, ходим с прямого IP |
| `PROXY_URLV2` | `verify_company.py:72-75`; `browser_probe.py:41-42, 610` | список asocks (`.txt`, много IP); в `verify_company` имеет **высший** приоритет | то же |
| `PROXY_URLV3` | `verify_company.py:77`; `browser_probe.py:41-42, 610` | http-прокси с 1 IP; в браузере имеет **высший** приоритет (Chromium не умеет socks-авторизацию, `browser_probe.py:39-40`) | то же |
| `HTTPS_PROXY` / `https_proxy` | `fetch_playwright.py:15`; уважается стандартными клиентами; `notify.py:9,136` (Telegram через прокси, Max — напрямую) | системный прокси | прямой доступ |
| `PLAYWRIGHT_BROWSERS_PATH` | `browser_probe.py:579` | где искать `chrome.exe` | перебирает `C:\sender\pw-browsers`, `C:\Users\Administrator\AppData\Local\ms-playwright`, `~\AppData\Local\ms-playwright`, `C:\Windows\system32\config\systemprofile\...` (`:582-585`) |
| `PW_CHROME` | `sender/web/playwright.config.ts:29` | путь к Chrome для e2e фронта | дефолтный браузер playwright |

### 4.4 Dolphin{anty} и VK

| Имя | Кто читает | Зачем | Нет значения |
|---|---|---|---|
| `DOLPHIN_TOKEN` | `browser_probe.py:355, 473`; `dolphin_pool.py:144`; через `_read_secret` — `enrich_contacts.py:691, 800, 2951, 3080, 3105, 3150, 3240, 3317, 3537, 3761, 3811, 4719, 4770, 4827, 5509` | Bearer-токен Local и Remote API дельфина | заголовок `Authorization` не ставится → 401 от дельфина. `dolphin_pool.main` печатает `{'error': 'нужны companies + dolphin_token + dolphin_profiles'}` (`:146-147`) |
| `DOLPHIN_API` | `browser_probe.py:350` | Local API дельфина | `http://localhost:3001/v1.0` |
| `DOLPHIN_REMOTE_API` | `browser_probe.py:455` | Remote API (облако аккаунта) | `https://dolphin-anty-api.com` |
| `VK_DOLPHIN_PROFILE` | `enrich_contacts.py:792` | ID профиля, к IP которого привязан `VK_TOKEN_USER` | `'829115401'` |
| `VK_USE_DOLPHIN` | `enrich_contacts.py:856` | `'1'` = VK API через дельфин (IP-привязка), иначе напрямую | `'1'` (включено) |
| `VK_TOKEN_USER` | `_read_secret` в `enrich_contacts.py:850, 3837, 5470` | user-токен VK для `groups.search` | пробуется `VK_TOKEN`, затем VK-путь возвращает `None` (`:853-854`) |
| `VK_TOKEN` | `enrich_contacts.py:850, 5470`; `news_scan.py:983` | резервный VK-токен | VK-сбор отключается |
| `VK_SLEEP` | `news_scan.py:671` | пауза между вызовами VK (RPS-лимит ~3/с) | 0.5 с |

### 4.5 БД, каталоги, панели

| Имя | Кто читает | Зачем | Нет значения |
|---|---|---|---|
| `SENDER_DIR` | `enrich_db.py:22`; `panel_core.py:40, 55`; `sender/ai_letter.py:343` | корень боевого каталога рассыльщика | `C:\sender` |
| `ENRICH_DB` | `enrich_db.py:21`; `panel_core.py:40` | путь к `enrich.db` | `<SENDER_DIR>\enrich.db` |
| `OBZVON_INDEX` | `panel_core.py:54`; `sender/tools/dryrun_basemerge.py` | индекс базы обзвона (161 761 юрлицо) | `<SENDER_DIR>\obzvon-index.db`; нет файла → страница «База» честно говорит об этом |
| `ENRICH_UPLOADS` | `panel_core.py:46` | куда класть загруженные CSV/XLSX | `C:\sender\enrich_uploads` |
| `ENRICH_USERS` | `enrich_panel.py:74` | HTTP Basic: `логин:пароль,логин2:пароль2` | **панель отвечает 503 всем** (`enrich_panel.py:78-79`) |
| `ENRICH_ROOT_PATH` | `enrich_panel.py:70` | префикс за обратным прокси | `/enrich` |
| `ENRICH_PORT` | `enrich_panel.py:315` | порт uvicorn (слушает только 127.0.0.1) | 8013 |
| `ENRICH_DB_SNAPSHOT` | `sender/tools/dryrun_basemerge.py:20` | снимок enrich.db для сухого прогона | см. код |
| `DRYRUN_WORKDIR` | `sender/tools/dryrun_basemerge.py:18` | рабочий каталог сухого прогона | `os.getcwd()` |
| `CALLBASE_DATA` | `sender-patches/obzvon-pagination/services__callbase.py:38` | каталог данных панели обзвона | см. код |
| `BASE_CSV` | `enrich_contacts.py:1995` | путь к базовому CSV обзвона | перебирает `<DROP_DIR>/obzvon_all_2026-07-16.csv` и `C:\seostat\drop\drop-storage\obzvon_all_2026-07-16.csv` (`:1996-1998`) |
| `OKVED_NAMES` | `sender/infopanel.py:535` | справочник названий ОКВЭД | перебор запасных путей там же |

**[исправлено скептиком]** в строке `ENRICH_DB` был указан читатель
`sender/tools/dryrun_basemerge.py` — это неверно: скрипт читает
`ENRICH_DB_SNAPSHOT` (`:20`), а имя `ENRICH_DB` встречается там только в
комментарии `:17`. Строка `ENRICH_DB_SNAPSHOT` ниже в этой же таблице —
корректна. `OBZVON_INDEX` из `dryrun_basemerge.py:19` — тоже корректно.

### 4.6 Рассыльщик (пакет `sender`)

Здесь важна особенность: в `sender.yaml` секретов нет — там лежат **имена**
переменных, а `Config.load` **валидирует их наличие при старте**
(`sender/config.py:409-412` для ящиков, `:589-592` для секрета отписки).
Нет переменной → `ConfigError` и служба не поднимается.

| Имя | Кто читает | Зачем | Нет значения |
|---|---|---|---|
| `SENDER_CONFIG` | `sender/cli.py:39`; `enrich_contacts.py:6354` | путь к `sender.yaml` | `./sender.yaml` |
| `BOX1_PASSWORD` … `BOX14_PASSWORD` (КЦ) | имена берутся из `mailboxes[].password_env`; читаются в `sender/mailbrowser.py:107`, `sender/imap_watcher.py:149`; валидируются `sender/config.py:409-412` | пароли приложений SMTP/IMAP | **ConfigError при старте**: «secret env var 'BOXn_PASSWORD' is not present in environment». Именно из-за этого `SenderPixel` пришлось кормить полным окружением панели (`server/_ops_pixel_fixenv.py:4-6`) |

**[исправлено скептиком]** диапазон был указан как `BOX1…BOX28` по верхней
границе из `sender/MAILBOXES-SETUP.md:129`. Фактический список ящиков КЦ —
14 штук, `BOX1_PASSWORD … BOX14_PASSWORD`, он лежит в файле
`seo-texts/sender/config/mailboxes.kc.yaml` **ветки
`origin/claude/persona-prompt-seo-sender-vi4tcq`** (в рабочем дереве этого файла
нет). Сколько ящиков Meyer — в git не нашёл, см. §8 п. 7.
| `UNSUB_SIGNING_SECRET` | имя из `legal.unsub_secret_env`; читается `sender/unsub.py:56`; валидируется `config.py:589-592` | HMAC-подпись токенов отписки и пикселя | ConfigError при старте; `Unsub.__init__` бросает `ValueError: Missing environment variable` (`unsub.py:57-58`) |
| `TELEGRAM_BOT_TOKEN` | имя из `notify.token_env`; `sender/notify.py:108-109`; `sender/cli.py:239` | уведомления в Telegram | канал помечается недоступным (`notify.py:149`) |
| `MAX_BOT_TOKEN` | имя из `notify.max_token_env`; `sender/notify.py:116-117` | уведомления в Max (VK) | то же (`notify.py:154`) |
| `POSTOFFICE_TOKEN` | имя из `postoffice.token_env`; `sender/postoffice.py:53-54` | Postmaster API Mail.ru | пробуется o2-flow через refresh-токен |
| `POSTMASTER_REFRESH_TOKEN` | имя из `postoffice.refresh_token_env`; `sender/postoffice.py:59-61` | бессрочный refresh для o2.mail.ru | Postoffice-метрики недоступны |
| `BITRIX_WEBHOOK_URL` | `sender/wiring.py:72`; имя из `bitrix.webhook_env`, `sender/bitrix.py:201-202` | синк лидов в Битрикс | `deps.bitrix = None`, синк просто не подключается (`wiring.py:32`) |
| `SENDER_NEW_USER_PASSWORD` | дефолт аргумента `--password-env`, `sender/cli.py:747`; читается `cli.py:424` | пароль при заведении пользователя панели | CLI-команда не создаст пользователя |
| `Y360_TOKEN`, `Y360_ORG_ID` | `sender/tools/y360_aliases.py:76-77` | алиасы Яндекс 360 через Directory API | скрипт печатает «нужны env Y360_TOKEN и Y360_ORG_ID» и выходит (`:79`) |
| `KC_FACTS`, `KC_GLOSSARY`, `MEYER_FACTS`, `MEYER_GLOSSARY`, `OKVED_PAINS` | `sender/ai_letter.py:345-362` | переопределение путей к базам фактов | `<SENDER_DIR>\kc-facts.json`, `product_glossary.json`, `meyer-facts.json`, `meyer_glossary.json`, `okved-pains.json` |
| `SENDER_API_URL` | `sender/web/vite.config.ts:13` | цель dev-прокси фронта | `http://127.0.0.1:8080` |
| `E2E_API_PORT` | `sender/web/e2e/seed_and_serve.py:57` | порт e2e-сервера | 8099 |

### 4.7 Мелочь: генерация текстов, hh, корневой проект

| Имя | Кто читает | Зачем | Нет значения |
|---|---|---|---|
| `REGEN_QUEUE` | `regen_driver.py:17` | имя файла очереди регенерации | `regen-queue.json` |
| `REGEN_BUDGET` | `regen_driver.py:27` | бюджет в USD | 185 |
| `REGEN_MAXROUNDS` | `regen_driver.py:121` | раундов доводки на страницу | 3 |
| `REGEN_WORKERS` | `regen_driver.py:141` | параллельных страниц | 4 |
| `SEED` | `review_all_50.py:41` | сид выборки для ревью | 2026 |
| `HH_PAGES` | `server/hh_scan.py:39` | страниц выдачи hh (по 50) | 5 |
| `HH_PAUSE` | `server/hh_scan.py:40` | пауза между запросами к hh | 2.5 с |
| `HH_USER_AGENT` | `enrich_contacts.py:679` | UA для hh API | `RuspromLeadEnrich/1.0 (kirillrand4@gmail.com)` |
| `PORT` | `web/server.mjs:32` | порт панели корневого проекта | 8090 |
| `HOST` | `web/server.mjs:33` | интерфейс | `127.0.0.1` |
| `BASE_PATH` | `web/server.mjs:34` | префикс за прокси | `/avto` |
| `ADMIN_USER` | `web/server.mjs:35` | HTTP Basic логин | `admin` |
| `ADMIN_PASS` | `web/server.mjs:36` | HTTP Basic пароль | **`changeme`** — небезопасный дефолт, панель поднимется |
| `UPSTREAM_PROXY` | `src/proxybridge.mjs:13` | вышестоящий прокси для моста | берётся `process.argv[2]`; нет ни того ни другого → выход с кодом 1 (`:17-20`) |
| `BRIDGE_PORT` | `src/proxybridge.mjs:14` | локальный порт моста | 11561 |

### 4.8 Только в тестах (в бою не задавать)

`TEST_TOKEN`, `TEST_TG_TOKEN`, `TEST_UNSUB_SECRET` — `sender/tests/test_notify.py`,
`sender/tests/test_cli.py`. `sender/web/e2e/seed_and_serve.py:16-18` сам ставит
`UNSUB_SIGNING_SECRET` и `BOX1..N_PASSWORD` в фиктивные значения через
`os.environ.setdefault`.

---

## 5. Данные и где они лежат

### 5.1 Раскладка сервера владельца (Windows)

```
C:\sender\                          рабочий каталог службы SenderPanel
  sender\                           питон-пакет панели (cli.py, store.py, api/, web/…)
  server\                           наша автоматика (служба rusprom-runner)
    job_runner.py                   поллер заданий
    runner-secrets.env              КЛЮЧНИЦА раннера (не в git)
    enrich_contacts.py              штатный конвейер обогащения
    news_cron.py, news_cron_task.cmd, news_cron.out
  enrich_panel\                     панель обогащения (служба EnrichPanel)
  _ops\                             каталог одноразовых скриптов сессий
    sales_base.json                 база продажников, 555 ИНН
    pixel.log / pixel.err.log       логи SenderPixel
  logs\orchestrator.log
  backups\, scripts\backup.ps1
  pw-browsers\                      браузеры Playwright для службы
  enrich_uploads\                   загрузки панели обогащения
  config.yaml / sender.yaml         конфиг панели (SENDER_CONFIG)
  panel.env                         СЕКРЕТЫ ПАНЕЛИ (BOX*_PASSWORD, UNSUB_SIGNING_SECRET)
  sender.db                         очередь писем, получатели
  enrich.db                         companies/emails/signals/stage_log/phone_contacts
  obzvon-index.db                   индекс базы обзвона, 161 761 юрлицо
  consent_log.jsonl
  update-panel.ps1, panel-update.zip, enrich-panel.zip

C:\seostat\
  drop\drop-storage\                ФИЗИЧЕСКОЕ хранилище дропа
    runner-secrets.env              ВТОРАЯ копия ключницы (стабильная)
    dolphin-profiles.txt            ~20 ID профилей дельфина
    centrifugal-core-inns.txt       ядро центробежных, 396 ИНН
    obzvon_all_2026-07-16.csv       базовый CSV (~679 МБ)
  app\                              панель обзвона (служба obzvon, порт 8012)
  avto\                             корневой GSC-проект (служба avto-panel, 8090)
    panel.log

C:\Program Files\Python311\python.exe   интерпретатор служб (3.11.9)
C:\nssm.exe (и C:\nssm\win64\nssm.exe, C:\tools\nssm\nssm.exe)  менеджер служб
```

Источники: `server/PANEL-DEPLOY.md:5-18`; `server/ENRICH-SALES-BASE-PROMPT.md:41-59`;
`enrich_contacts.py:47-49, 123-124, 1996-1998`; `server/_ops_pixel_deploy.py:20-26`;
`server/update-obzvon.ps1:17-21`; `RUNBOOK.md:12-13`.

### 5.2 Две копии `runner-secrets.env` — это не дублирование, а страховка

`enrich_contacts.py:47-49` прямо говорит: «два расположения runner-secrets.env:
локальный (иногда удаляется) и стабильный на дропе». Локальный —
`C:\sender\server\runner-secrets.env`; стабильный —
`C:\seostat\drop\drop-storage\runner-secrets.env` (он же виден снаружи как файл
`runner-secrets.env` на дропе — подтверждено листингом в этой сессии).

Формат файла — `server/runner-secrets.env.example`:

```
DROP_URL=https://parsercompressor.online/drop
DROP_TOKEN=<токен дропа>
JOB_SECRET=<64-hex, общий секрет подписи заданий>
CAPMONSTER_KEY=<ключ CapMonster Cloud>
PROVIDER_API_KEY=<ключ провайдера для парсинга реквизитов>
PROVIDER_BASE_URL=https://router.cheap
RUNNER_POLL_SEC=20
DADATA_TOKEN=<вставить токен DaData>
```

Файл читается кодировкой `utf-8-sig` (BOM терпится). Значения в `<угловых
скобках>` считаются плейсхолдерами и **пропускаются** всеми тремя загрузчиками.

Реальный файл на бою наверняка шире шаблона: код ждёт оттуда ещё
`XMLRIVER_USER/KEY`, `DOLPHIN_TOKEN`, `VK_TOKEN(_USER)`, `TWOCAPTCHA_KEY`,
`PROXY_URL*` — см. диагностику `browser_probe.diag_proxy` (`:636-641`) и
op `envcheck` (`enrich_contacts.py:5758-5787`).

### 5.3 Диагностика окружения сервера, не выходя из песочницы

Обе доступны как задания раннеру (**в этой сессии выполнять запрещено**, но
записываю точные вызовы для будущих сессий):

```python
R.submit('enrich_contacts', {'op': 'envcheck'})   # enrich_contacts.py:5754
```
Возвращает `in_runner_env` (что видит служба), `files` (что записано в каждом из
двух `runner-secrets.env`), `effective_available` (что реально увидит код через
`_read_secret`, `:5782`). **Значения не печатаются**, только флаги наличия.
Список проверяемых ключей жёстко зашит и короткий — 8 штук
(`enrich_contacts.py:5758-5759`): `CAPMONSTER_KEY`, `TWOCAPTCHA_KEY`,
`RUCAPTCHA_KEY`, `DOLPHIN_TOKEN`, `XMLRIVER_USER`, `XMLRIVER_KEY`,
`PROVIDER_API_KEY`, `VK_TOKEN`. Ни `DROP_*`, ни `JOB_SECRET`, ни `DADATA_TOKEN`
он не покажет.

```python
R.submit('browser_probe', {'diag_proxy': True})   # разбор args: browser_probe.py:735
```
Функция `diag_proxy` (`browser_probe.py:605`). Разбирает `PROXY_URL/V2/V3`
(схема, хост, порт, есть ли авторизация), маскируя креды и IP
(`_mask`, `:597-603`); печатает `keys` (`ЕСТЬ(len)` / `НЕТ`) по 12 ключам
(`:636-639`, включая `JOB_SECRET` и `DADATA_TOKEN`); `env_names` — имена
переменных, содержащих `DADA/VK/CAPTCHA/XMLRIVER/PROXY/DROP/PROVIDER`
(`:643-644` — **`JOB_*` в этот фильтр не попадает**); `file_keys` — имена и
длины значений **всех** строк локального `runner-secrets.env` без самих
значений (`:646-660`); `runner_python` — путь к интерпретатору службы
(`:627` — [исправлено скептиком], было `:628`).

### 5.4 Панель `panel.env` и служебное окружение

`C:\sender\panel.env` — отдельная ключница **панели** (не раннера): пароли
ящиков `BOX*`, `UNSUB_SIGNING_SECRET`. Шаблон (linux-вариант) —
`sender/deploy/panel.env.example`.

Из песочницы окружение панели правится операциями раннера
(`server/PANEL-DEPLOY.md:114-118`):

| Операция | Что делает |
|---|---|
| `{'op':'panel_env_set', ...}` | пароли → `panel.env` + `nssm AppEnvironmentExtra` + рестарт (`enrich_contacts.py:5808`) |
| `{'op':'panel_file_put','files':[{'b64':…,'dest':r'C:\sender\_ops\x.py'}]}` | положить файл (ограничено `C:\sender`, `enrich_contacts.py:5871`) |
| `{'op':'panel_py','script':r'C:\sender\_ops\x.py','argv':[…],'timeout':560}` | запустить питоном панели 3.11 с env из `panel.env` (`enrich_contacts.py:6229-6251`) |
| `{'op':'svc_probe','service':'SenderPanel'}` | статус/env/HTTP (`enrich_contacts.py:6264`) |
| `{'op':'smtp_login_batch','boxes':[…]}` | проверка SMTP-логинов (`enrich_contacts.py:5788`) |

Лимит `panel_py` — ~560 с на процесс (`ENRICH-SALES-BASE-PROMPT.md:36`),
жёсткий верх — `timeout` аргумента, дефолт 900 (`enrich_contacts.py:6257` —
[исправлено скептиком], было `:6255`). Обратите внимание: ключ аргументов —
именно `argv` (`enrich_contacts.py:6254`); в `ENRICH-SALES-BASE-PROMPT.md:35`
он назван `args` — там ошибка, `args` работать не будет.

---

## 6. Ограничения и грабли

**1. `os.environ` в песочнице не долетает до сервера.** Самая частая ошибка.
`server/mass_enrich_loop.sh:14` делает `export XMLRIVER_CHANNELS="$CHANNELS"`, а
`mass_enrich_loop.py:25` — `os.environ['XMLRIVER_CHANNELS']=...`. Обе строки
влияют только на локальный процесс. Код это знает и обходит через аргумент
задания: `enrich_contacts.py:6645` прямо пишет «env XMLRIVER_CHANNELS не долетает
до сервера» и на `:6647` пересоздаёт семафор из `args['channels']`.
**Правило: любую настройку на сервер передавать в `args` задания, не через env.**

**2. `XMLRIVER_CHANNELS` читается на импорте** (`enrich_contacts.py:23`) — то
есть даже на сервере `setx` без рестарта службы ничего не изменит.

**3. `PROVIDER_MODEL` значит разное в двух местах.** В `gen_provider` — это
модель-замена для мёртвых (`:233`); в `verify_company` — модель по умолчанию
(`:143`). Если задать `PROVIDER_MODEL=claude-haiku-4-5`, то `gen_provider`
начнёт подменять fable на haiku, а `verify_company` — использовать haiku везде.
Побочный эффект скорее полезный, но неочевидный.

**4. Не все пути к провайдеру проходят через `resolve_model`.**
`resolve_model` вызывается **только** из `gen_provider._raw_stream`
(`gen_provider.py:258` — [исправлено скептиком], было `:255`; в §3.3 стояло
верное число, здесь была опечатка). А `verify_company._provider_call_stdlib`
шлёт `model or _PROVIDER_MODEL` напрямую (`verify_company.py:183`), никакой
подмены. Значит: если на сервере `gen_provider.py` **не** нашёлся (`GP is None`,
`verify_company.py:122-138`), extract пойдёт stdlib-путём на `claude-fable-5` —
на модель, помеченную в коде как мёртвая. Лечится заданием
`PROVIDER_MODEL=claude-opus-4-8` в окружении сервера (он же подхватится и
`_PROVIDER_MODEL` на `:143`, потому что читается при импорте).

**[дополнено скептиком]** развилка внутри `extract_via_provider`
(`verify_company.py:236-243`) видна так: `GP is not None` → `GP._raw_stream(...,
'claude-fable-5', ...)`, то есть подмена срабатывает; `GP is None` →
`_provider_call_stdlib(prompt)` без модели, то есть уходит `_PROVIDER_MODEL`
как есть. Проверить, какая ветка живёт на сервере, из песочницы можно только
заданием раннеру — я этого не делал.

**5. `gen_provider.make_client()` падает KeyError без ключа.** `env()` не
подставляет дефолтов (`gen_provider.py:129-132`), и `e['PROVIDER_API_KEY']`
на `:144` бросает `KeyError`, а не понятную ошибку. Аналогично
`e['PROVIDER_BASE_URL']` в `_raw_stream` (`gen_provider.py:260`).

**6. `JOB_SECRET` в песочнице не задан** — проверено в этой сессии.
`run_on_server` тянет его с дропа: скачивает `runner-secrets.env`, ищет строку
`JOB_SECRET=` (`run_on_server.py:25-36`). Молча проглатывает любую ошибку
(`:35-36`) — если дроп недоступен, задание уйдёт **без подписи** и раннер его
отвергнет, а вы увидите только «timeout ждали 1800s».

**7. Дроп: имена файлов.** `drop_server.SAFE_NAME = ^[\w][\w.\-]{0,200}$`
(`drop_server.py:11`) применяется к download/upload/delete
(`:32, :37, :50` — [исправлено скептиком], было `:49`, на `:49` объявление
`def delete`), но **не** к `/list` (`:21-28`). Поэтому в листинге видны файлы,
скачать которые невозможно — вернётся 400.
**[подтверждено скептиком фактически]**: в текущем листинге таких имён ровно
два — `New Text Document.txt` и `drop-storage - Shortcut.lnk`.

**8. Раннер: подпись выключается «сама».** Если `JOB_SECRET` пуст, `sig_ok`
возвращает `True` для любого задания (`job_runner.py:136-138`). Единственная
защита остаётся allowlist. При старте это видно в логе:
`подпись=ВЫКЛ (только allowlist)` (`job_runner.py:311`).

**9. `job_runner.py` руками не запускать.** Инцидент 2026-07-24
(`PANEL-DEPLOY.md:108-113`): два ручных экземпляра + служба = каждое задание
исполнялось 2-3 раза параллельно. Проверка:
`Get-CimInstance Win32_Process | ? {$_.CommandLine -like '*job_runner*'}` —
должен быть ровно один процесс.

**10. Самообновление кода раннера ограничено allowlist.**
`PULL_ALLOW` (`job_runner.py:145-148`): `verify_company.py`, `job_runner.py`,
`run_on_server.py`, `enrich_contacts.py`, `browser_probe.py`, `dadata_client.py`,
`send_campaign.py`, `news_scan.py`, `enrich_db.py`, `dolphin_pool.py`,
`lead_scoring.py`. Файлы вне списка через `pull` не доставить. Сам
`job_runner.py` применяется только после `Restart-Service rusprom-runner -Force`
(`job_runner.py:173`).

**11. Питон на сервере: только `C:\Program Files\Python311\python.exe`.**
`py` без версии = 3.12 и это **не** тот интерпретатор, где стоят пакеты панели
(`PANEL-DEPLOY.md:15`, `setup-news-schedule.ps1:15-16`). В коде встречаются ещё
два варианта пути (`C:\Python311\python.exe` — 5 вхождений, в т.ч.
`RUNNER-SETUP.md:39`; `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe`
— 4 вхождения, все в `sender/RUNBOOK-DEPLOY.md:306, 335, 401`
[дополнено скептиком: адреса второго варианта раньше не были указаны]) —
какой из них живой, из репозитория не определить.

**12. `Config.load` валидирует ВСЕ ящики.**
**[исправлено скептиком]** было: «любой процесс, импортирующий `sender.config`».
Импорт модуля сам по себе ничего не требует — валидация живёт в
`Config._build_mailboxes` (`sender/config.py:388-412`), которую вызывает
`Config.load()` (`:346-356`). Требование звучит так: **любой процесс, который
вызывает `Config.load(...)`**, требует наличия каждого `BOX*_PASSWORD`, даже
если ящики ему не нужны (а `Config.load` вызывается в начале почти любой
команды CLI — `sender/cli.py:39-40`). Из-за этого службе `SenderPixel` пришлось
отдать полное окружение панели (`_ops_pixel_fixenv.py:4-6`) вместо одного
`UNSUB_SIGNING_SECRET`.

**13. `python -m sender.cli` не работает** — в `cli.py` нет `if __name__`,
получается тихий выход без вывода. Точка входа — `python -m sender`
(`PANEL-DEPLOY.md:22-24`).

**14. `.ps1` на сервере обязаны быть UTF-8 **с BOM**** — PowerShell 5.1 читает
их в системной кодировке и ломается на кириллице (`PANEL-DEPLOY.md:99-100`).
Владельцу команды давать **по одной**, без `&&` (`PANEL-DEPLOY.md:36`).

**15. `ADMIN_PASS` по умолчанию `changeme`** (`web/server.mjs:36`) — панель
корневого проекта поднимется с этим паролем и не пожалуется.

**16. Прокси для Remote API дельфина отключается принудительно**
(`browser_probe.py:467-472`): системный прокси рвёт TLS (SSL UNEXPECTED_EOF),
поэтому там свой opener с `ProxyHandler({})` и **отключённой проверкой
сертификата** (`check_hostname=False`, `verify_mode=CERT_NONE`).

---

## 7. Что сломано или устарело

**7.1 `JOB_HMAC` вместо `JOB_SECRET` — почти наверняка опечатка.**
`enrich_contacts.py:5191`:

```python
sec = os.environ.get('JOB_HMAC', '')
```

Это единственное вхождение имени `JOB_HMAC` во всём репозитории (проверено
грепом по всем расширениям). Все остальные 9 мест используют `JOB_SECRET`.
Последствие: самочейн-задание `zakupki_mass` (`enrich_contacts.py:5188-5213`)
уйдёт на дроп **без поля `sig`**, и раннер с заданным `JOB_SECRET` его
отбросит (`job_runner.py:295-300`), молча оборвав цепочку на второй пачке.
**НЕ ПРОВЕРЕНО:** возможно, владелец завёл `JOB_HMAC` на сервере как синоним —
тогда всё работает. Как проверить: `envcheck` **не покажет** `JOB_HMAC` (его нет
в жёстко зашитом списке ключей `enrich_contacts.py:5758-5759`); `diag_proxy` в
секции `env_names` тоже не покажет (фильтр по `DADA/VK/CAPTCHA/XMLRIVER/PROXY/
DROP/PROVIDER`, `browser_probe.py:643-644`). Покажет **только** секция
`file_keys` того же `diag_proxy` (`browser_probe.py:646-660`) — она перечисляет
имена всех строк локального `runner-secrets.env`. Если `JOB_HMAC` задан
переменной службы, а не файлом, из песочницы его вообще не увидеть без
самописного `panel_py`-скрипта. Код **не менять** без владельца.

**[перепроверено скептиком]** сама фактура подтверждается: `JOB_HMAC`
встречается в репозитории ровно один раз (`enrich_contacts.py:5191`), а
`JOB_SECRET` читается в `job_runner.py:56`, `run_on_server.py:22`,
`news_scan.py:74, 186, 1049`, `enrich_contacts.py:2198`,
`enrich_panel/enrich_panel.py:113` (плюс `browser_probe.py:636` — список
диагностики и `enrich_panel/tests/test_topup.py` — тест). Уточнение к
последствию: самочейн срабатывает только при `args['chain']` и
`len(rows) > cap` (`enrich_contacts.py:5188`), то есть дефект видно лишь
в длинных цепочках `zakupki_mass`. Живого окружения сервера я тоже не видел —
статус «НЕ ПРОВЕРЕНО» остаётся.

**7.2 Документация о мёртвых моделях противоречит коду.**
`server/ENRICH-SALES-BASE-PROMPT.md:146-149` утверждает: «автоподмена через
`PROVIDER_DEAD_MODELS` / `PROVIDER_MODEL` (**сейчас список пуст**)».
В коде список **не пуст**: `_DEAD_DEFAULT = 'claude-fable-5,claude-opus-5'`
(`gen_provider.py:223`), добавлен коммитом `0b4d4e4` («Полная ветка переписки,
честный провенанс контактов, защита от зависшего провайдера») — проверено
`git log -S"_DEAD_DEFAULT"`. Следствие: вызовы `claude-fable-5`, идущие через
`gen_provider._raw_stream`, фактически уходят на `claude-opus-4-8`. Это меняет
и качество, и цену. Ошибка в документе, не в коде.

**[исправлено скептиком] — примеры были подобраны неверно.**

- `review_lenses.py:310` — такого файла в корне `seo-texts/` нет. Правильный
  путь `seo-texts/sender/review_lenses.py:310` (`model = 'claude-fable-5'`,
  дальше `gen_provider._raw_stream` на `:318`) — пример подмены корректный.
- `guest-posts/gp_gen.py:108` (`gp.call(..., model='claude-fable-5')`) —
  корректный: `gp.call` ходит через `_raw_stream` (`gen_provider.py:331`).
- `news_scan.py:1381` — **некорректный пример**. Там
  `VC._PROVIDER_MODEL = args.get('extract_model', 'claude-fable-5')`, а
  `_PROVIDER_MODEL` используется только в `verify_company._provider_call_stdlib`
  (`:183`), который `resolve_model` минует. По этой строке fable-5 может уйти
  на шлюз ПО-НАСТОЯЩЕМУ (если `GP is None`) — это не пример подмены, а пример
  дыры в подмене. То же и с `enrich_contacts.py:6650`.
- Настоящий пример подмены в этой же цепочке — `verify_company.py:238`:
  `GP._raw_stream([...], 'claude-fable-5', 800, thinking=False)`.

**[уточнено скептиком] хронология.** Формулировка «устарел документ» неточна:
коммит `0b4d4e4` (список мёртвых моделей) датирован 2026-07-27 06:58 UTC, а
нынешняя редакция `ENRICH-SALES-BASE-PROMPT.md` — коммит `aa33864`
2026-07-27 10:52 UTC, то есть на четыре часа ПОЗЖЕ. Документ не отстал —
в него внесли неверное утверждение уже после появления списка.

**7.3 `BITRIX_WEBHOOK_TOKEN` в `panel.env.example` никто не читает.**
`sender/deploy/panel.env.example:23` предлагает переменную
`BITRIX_WEBHOOK_TOKEN`; в коде используется `BITRIX_WEBHOOK_URL`
(`sender/wiring.py:72`, `sender/bitrix.py:201-202`). Единственное вхождение
`BITRIX_WEBHOOK_TOKEN` во всём репозитории — эта закомментированная строка
примера. Заполнив её, Битрикс-синк не включишь.
**[перепроверено скептиком]** проверено не только по рабочему дереву, а
`git grep BITRIX_WEBHOOK_TOKEN origin/<branch>` по **всем шести** веткам
`origin` (`git ls-remote --heads origin`): совпадение везде одно и то же —
`seo-texts/sender/deploy/panel.env.example:23`. Что записано в боевом
`sender.yaml`/`panel.env` на сервере, я по-прежнему не знаю.

**7.4 `panel.env.example` описывает Linux-раскладку, а бой — Windows.**
`SENDER_CONFIG=/opt/rusprom-sender/sender.yaml`, `chmod 600`, `chown rusprom`
(`sender/deploy/panel.env.example:2-7`) — на боевом сервере это
`C:\sender\sender.yaml` и NSSM `AppEnvironmentExtra`. Файл-пример не обновляли
после переезда на Windows.

**7.5 `RUNNER-SETUP.md` отстал от кода.** Заявляет allowlist из двух задач
(«`verify_company`, `ping`», `:17-18`) и путь питона `C:\Python311\python.exe`
(`:39`). Фактически задач девять (`job_runner.py:62-73`), а питон служб —
`C:\Program Files\Python311\python.exe` (`PANEL-DEPLOY.md:10`).

**7.6 `runner-secrets.env.example` неполон.** В нём 8 переменных
(`runner-secrets.env.example:3-12`), а код ждёт ещё как минимум
`XMLRIVER_USER`, `XMLRIVER_KEY`, `DOLPHIN_TOKEN`, `VK_TOKEN`/`VK_TOKEN_USER`,
`TWOCAPTCHA_KEY`, `PROXY_URL`/`PROXY_URLV2`/`PROXY_URLV3` — они перечислены в
диагностиках (`enrich_contacts.py:5776-5777`, `browser_probe.py:637-639`).
Новая сессия, поднимающая раннер с нуля по этому шаблону, получит наполовину
неработающий конвейер.

**Про «мёртвый код» — что я НЕ считаю мёртвым и почему:**
`drop_server.py` не имеет вызывающих в репозитории, но это **точка входа
службы** `DropServer` — живая. `enrich_panel/enrich_panel.py` — точка входа
службы `EnrichPanel`; **[исправлено скептиком]** «не имеет вызывающих» неверно:
его импортируют тесты (`server/enrich_panel/tests/conftest.py:89`,
`tests/test_auth.py:30`). `hh_scan.py` вызывается ровно один раз, из
`enrich_contacts.py:3662`. `dolphin_pool.py` — в allowlist раннера
(`job_runner.py:69`). Скрипты `server/_ops_*.py` — одноразовые, доставляются на
сервер через `panel_file_put` и запускаются `panel_py`; отсутствие вызывающих
в git для них нормально. `sender/tools/y360_aliases.py` — ручной CLI-скрипт
(способ запуска описан в его же шапке, `:24-26`), тут предположение верное.

**[исправлено скептиком]** про `sender-patches/obzvon-pagination/services__callbase.py`
предположение «запускается вручную» неверно: это не запускаемый скрипт, а
**файл выкатки**. Весь каталог `sender-patches/obzvon-pagination/` пакуется
командой `bash server/build_panel_update.sh obzvon` в `obzvon-update.zip`,
кладётся на дроп и раскатывается в боевую панель обзвона скриптом
`server/update-obzvon.ps1` (см. предупреждение в `obzvon-centro/README.md:155-165`
о том, что файлы прошлой выкатки уедут вместе с новыми и **перезапишут боевые**).
Дальше модуль импортируется приложением обзвона на сервере, а не запускается сам.

---

## 8. Что не проверено

Раздел обязательный. Всё ниже — то, в чём я не уверен; проверять до того, как
принимать решения.

1. **Реальное содержимое `runner-secrets.env` на сервере.** Я видел только имя
   файла в листинге дропа. Какие переменные там заданы фактически, есть ли
   `JOB_HMAC`, `XMLRIVER_*`, `DOLPHIN_TOKEN` — не знаю. Проверяется
   `envcheck`/`diag_proxy` (§5.3).
2. **Живое окружение служб NSSM.** `AppEnvironmentExtra` каждой службы я не
   видел. Возможно, часть переменных задана там, а не в файле, и тогда
   `_load_env_file` их не перетрёт (`job_runner.py:48`).
3. **Какой питон реально запускает службы.** В репозитории три разных пути к
   Python 3.11. `PANEL-DEPLOY.md:10` утверждает, что проверено фактически
   2026-07-24, но я это не подтверждал.
4. **Живы ли службы `DropServer`, `obzvon`, `avto-panel`, `SenderPixel`
   прямо сейчас.** Есть только упоминания в документах и `_ops`-скриптах.
5. **Порт `SenderPanel`.** В `sender/web/vite.config.ts:13` фигурирует 8080, в
   `RUNBOOK-DEPLOY.md` — `serve-api`; точного боевого порта я не подтвердил.
6. **Конфигурация Caddy.** Есть только пример блока для `/enrich`
   (`enrich_panel/README.md:157-163` — [исправлено скептиком], было `:48-56`;
   на 48-56 текст про «Обогатить выбранное») и `deploy/Caddyfile.example` корневого
   проекта. Реальный `Caddyfile` сервера я не видел; в репозитории есть
   `_ops_find_caddy.py`, который его ищет — значит, даже сессиям он был неочевиден.
7. **Сколько на самом деле почтовых ящиков** — **[исправлено скептиком: ответ
   есть, он был в невыгруженной ветке]**. В рабочей ветке действительно видны
   только противоречивые числа: `sender/config/sender.example.yaml` показывает
   `BOX1..BOX4` (`:83, 95, 105, 115`; путь к файлу в исходной редакции был без
   каталога `config/`), `server/PANEL-DEPLOY.md:14` — «BOX1..14»,
   `sender/MAILBOXES-SETUP.md:129` — «BOX1_PASSWORD … BOX28_PASSWORD».
   Но в ветке `origin/claude/persona-prompt-seo-sender-vi4tcq` лежит файл
   `seo-texts/sender/config/mailboxes.kc.yaml` (коммит `f4448b1`, 2026-07-24,
   «Ящики КЦ: факт 14 адресов»), которого нет в рабочем дереве. В нём —
   **ровно 14 ящиков КЦ с `password_env: BOX1_PASSWORD … BOX14_PASSWORD`**
   (`:12, 23, 34, 45, 56, 67, 78, 89, 100, 111, 122, 133, 144, 155`), шапка
   файла: «8 Я360 + 6 VK = 14», «Meyer-ящики — отдельно». Это согласуется с
   `PANEL-DEPLOY.md:14` и объясняет расхождение: `BOX1..BOX4` — учебный пример,
   `BOX28` в `MAILBOXES-SETUP.md` — верхняя граница «на вырост».
   Смотреть так: `git show origin/claude/persona-prompt-seo-sender-vi4tcq:seo-texts/sender/config/mailboxes.kc.yaml`.
   **Остаётся непроверенным:** сколько ящиков Meyer (их файла в git нет ни в
   одной ветке) и что фактически лежит в боевом `C:\sender\sender.yaml`.
8. **Работоспособность провайдерского шлюза сегодня.** Замер «fable-5 мёртв»
   датирован 27.07.2026 комментарием в коде. Я вызовов не делал (запрещено
   правилами сессии). Возможно, модель уже ожила и подмена только вредит.
9. **Значения `PROXY_URL/V2/V3`.** Формат (socks5 с авторизацией? http?
   ротатор-ссылка?) в коде описан как «может быть и то и другое»
   (`verify_company._fetch_list`, `:59-69`). Что задано на бою — не знаю.
10. **Токен ASocks в `RUNBOOK.md:43`** ([исправлено скептиком], было `:44` —
    там текст про мост Chromium) записан открытым текстом
    (`socks5://ul01ktnhed20hmsr76jkrftt8zfb:B4wjeOlxZa3Bek9Z@89.39.105.78:11560`).
    Актуален ли он и не утёк ли — не проверял; **владельцу стоит ротировать**
    независимо от актуальности, раз он лежит в git.
11. **Есть ли на сервере файл `C:\sender\enrich_panel\` вообще** (то есть
    доставлена ли панель обогащения) — в репозитории есть только инструкция
    по установке.
12. **Не проверял ветки `origin/*` на предмет других `.env`-файлов** глубже,
    чем `git ls-tree | grep -i env` по каждой ветке: там во всех ветках только
    `runner-secrets.env.example`. Файлов с реальными секретами в git не нашёл —
    но это утверждение основано на поиске по имени, а не на скане содержимого.
    **[урок скептика]** такой фильтр по имени уже дал промах: конфиг ящиков
    `sender/config/mailboxes.kc.yaml` (см. п. 7) не содержит слова «env» в
    имени и потому не попал в поиск, хотя лежит в ветке `origin` и отвечает
    на вопрос, который считался открытым. Секретов в нём нет (только имена
    `password_env`), но искать по веткам надо шире, чем `grep -i env`.
13. **`JOB_HMAC`.** Повторю отдельно: я утверждаю, что это опечатка, но живого
    окружения сервера не видел. Если владелец завёл такую переменную —
    утверждение неверно.
