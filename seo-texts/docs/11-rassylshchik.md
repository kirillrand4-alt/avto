# 11. Панель рассыльщика (`seo-texts/sender/`)

Разбор по коду на 2026-07-27. Всё, что ниже, проверено чтением файлов в
`/home/user/avto/seo-texts/sender/` и локальными прогонами тестов. Ссылки вида
`sender.py:554` — файл и строка в этом каталоге. Где я не проверял — стоит явная
пометка «НЕ ПРОВЕРЕНО» или «ПРЕДПОЛОЖЕНИЕ».

Важное про состояние репозитория на момент разбора: в рабочем дереве есть
**незакоммиченные правки** в `sender.py`, `store.py`, `cadence.py`,
`tests/test_fix_p1.py` (`git diff --stat` в корне репо). Они описаны в §6.

---

## 1. Что это и зачем

`seo-texts/sender/` — самостоятельный сервис холодной B2B-рассылки от имени
ООО «Руспром» (бренды «Компрессор Центр» / Meyer). Это НЕ часть SEO-генерации
текстов, он просто живёт в том же каталоге. ~50 700 строк кода
(`wc -l *.py api/*.py tests/*.py web/src/**/*.tsx`), из них движок — stdlib-only,
веб-транспорт — FastAPI, фронт — React SPA.

Что он делает:

1. держит базу получателей (`recipients`), импортированную из CSV базы обзвона;
2. планирует касания кампании (`cadence`), кладёт письма в очередь (`messages`);
3. генерирует текст письма — либо merge-шаблоном (`personalize`), либо
   AI-генератором через провайдерский API (`ai_letter` / `ai_quota`);
4. **не отправляет автоматически**: письмо ложится в очередь подтверждений
   `confirm_reviews`, и оператор жмёт «Отправить» в веб-панели;
5. читает входящие по IMAP (`imap_watcher`), классифицирует ответы
   (`reply_classify`), заводит лида (`leaddesk`), готовит ЧЕРНОВИК ответа
   (`reply_pipeline` → `confirm_reviews` c `kind='reply'`);
6. держит юр-заслоны: стоп-лист (`suppression`), отписку (`unsub`), журнал
   правовых оснований (`consent_log`), kill-switch по репутации (`gates`).

Ключевая архитектурная идея, повторённая в комментариях по всему коду:
**автоматика ничего не шлёт живым людям сама**. `orchestrator` при включённом
confirm-режиме переводит письмо в `pending_review` и кладёт карточку в очередь;
реальный SMTP происходит только когда оператор в панели нажал кнопку, и только
если в конфиге стоит `confirm.live_send: true` (`wiring.py:78-91`).

---

## 2. Точки входа и как запустить

Всё запускается **из каталога `seo-texts/`** (пакет называется `sender`, а лежит
он в `seo-texts/sender/`), либо при добавлении `seo-texts` в `PYTHONPATH`.

### 2.1 CLI: `python -m sender <команда>`

`__main__.py:3` → `sender/cli.py:main` (`cli.py:628-837`). Конфиг берётся из
`--config`, иначе `$SENDER_CONFIG`, иначе `./sender.yaml` (`cli.py:37-40`).
Полный список команд — словарь `cli.py:798-820`:

| Команда | Что делает | Ключевые аргументы |
|---|---|---|
| `init-db` | создать/домигрировать схему БД | — (`cli.py:49`) |
| `import <csv_path>` | импорт получателей из CSV | `--limit N`, `--map email=Col1,inn=Col2` (`cli.py:645-651`) |
| `suppress-import <file>` | залить стоп-лист | `--scope inn\|domain` (обяз.), `--reason` (`cli.py:653-662`) |
| `validate` | MX/роль/disposable-валидация адресов | `--limit`, `--all` (`cli.py:664-669`) |
| `campaign-create` | создать кампанию | `--name` (обяз.), `--segment`, `--send-order pilot_asc\|priority_desc`, `--min-priority-max N` (`cli.py:672-687`) |
| `campaign-add-step` | добавить шаг цепочки | `--campaign`, `--index`, `--subject`, `--body-file`, `--delay-hours`, `--gate all\|not_bounced\|engaged` (`cli.py:689-700`) |
| `campaign-activate` / `campaign-pause` | статус кампании | `--campaign` (`cli.py:702-708`) |
| `run` | запустить оркестратор | `--interval 60`, `--dry-run`, `--once`, `--campaigns 1,2` (`cli.py:711-717`) |
| `status` | статус ящиков и кампаний | — (`cli.py:720`) |
| `pause` | пауза | `--scope global\|mailbox`, `--target`, `--reason` (обяз.) (`cli.py:723-731`) |
| `resume` | снять паузу | `--target` (без него — все) (`cli.py:734-737`) |
| `stats` | отчёты | `--campaign`, `--json` (`cli.py:740-742`) |
| `user-create` | создать юзера панели | `--username`, `--role owner\|manager`, `--password-env` (дефолт `SENDER_NEW_USER_PASSWORD`), `--email`, `--enable-2fa` (`cli.py:745-751`) |
| `user-rotate-2fa` | перевыпустить TOTP | `--username` (`cli.py:754-756`) |
| `confirm-queue` | очередь подтверждений текстом | `--campaign`, `--limit 50` (`cli.py:759-761`) |
| `confirm-show <review_id>` | инфо-панель письма | `--json` (`cli.py:763-767`) |
| `confirm-decide <action> <review_id>` | решение оператора | action ∈ `approve\|edit\|skip\|stoplist`; `--subject`, `--body-file`, `--reason`, `--operator` (`cli.py:769-775`) |
| `confirm-golden` | выгрузка «золотых пар» правок | `--out`, `--limit 500` (`cli.py:777-780`) |
| `confirm-run` | интерактивная калибровка очереди | `--campaign`, `--operator` (`cli.py:782-785`) |
| `serve-api` | HTTP API/сайт панели | `--host 127.0.0.1`, `--port 8090`, `--static-dir <web/dist>` (`cli.py:788-794`) |

Пароль пользователя намеренно НЕ принимается аргументом — только через env
(`cli.py:419-435`).

Отдельный вход — сервер отписки и пикселя открытий:
`python -m sender.unsub_server --config <yaml> [--host 0.0.0.0] [--port 8080] [--log-level INFO]`
(`unsub_server.py:365-436`).

### 2.2 Веб-панель

Два режима (см. `deploy/README.md`):

**A. Только API (за nginx, рекомендуется для Linux):**
```
cd /home/user/avto/seo-texts
python -m sender serve-api --host 127.0.0.1 --port 8090
```
Nginx отдаёт статику `web/dist` и проксирует `/api/` → `127.0.0.1:8090/`
(`deploy/nginx-panel.conf:86-87`), systemd-юнит — `deploy/rusprom-sender-panel.service`
(ExecStart с `--port 8090`, env из `panel.env`).

**B. Сайт+API одним процессом (стейджинг, Windows):**
```
python -m sender serve-api --port 8090 --static-dir /path/to/sender/web/dist
```
Собирается `make_site_app` (`api/app.py:1333-1437`): API монтируется под `/api`,
SPA раздаётся статикой с client-side-fallback; `/healthz` в корне.
Windows-установка службы — `deploy/nssm-panel-install.ps1:38`.

**Перед первым запуском обязательно:**
```
cd sender/web && npm ci && npm run build        # соберёт web/dist
pip install -r sender/requirements-dev.txt      # fastapi+uvicorn+httpx+pytest+aiosmtpd
python -m sender init-db --config <yaml>
python -m sender user-create --username <login> --role owner   # пароль в env SENDER_NEW_USER_PASSWORD
```

**Dev-режим фронта:**
```
cd sender/web && npm run dev          # Vite на :5173
```
Vite проксирует `/api` на `process.env.SENDER_API_URL || http://127.0.0.1:8080`
(`web/vite.config.ts:13`). **Дефолт порта у Vite (8080) не совпадает с дефолтом
`serve-api` (8090)** — либо запускать API с `--port 8080`, либо задавать
`SENDER_API_URL=http://127.0.0.1:8090`.

### 2.3 Тесты

Python-сьют (запускать из `seo-texts/`):
```
cd /home/user/avto/seo-texts
python3 -m pytest sender/tests/ -q -rs
```
Проверено 2026-07-27: **1078 passed, 1 skipped за 297 с** (единственный skip —
`test_ai_letter_meyer.py:229`, «meyer-facts.json не развёрнут»). Отдельный файл:
`python3 -m pytest sender/tests/test_store.py -q`. Сьют требует
`sender/requirements-dev.txt`, иначе часть тестов молча скипается (об этом
предупреждает сам файл требований).

Фронтовые тесты: `cd sender/web && npm test` (vitest, `web/tests/`),
`npm run e2e` (Playwright; поднимает `e2e/seed_and_serve.py` на :8099 и Vite на
:5173, браузер из `/opt/pw-browsers`, см. `web/playwright.config.ts`). Прогон
фронта я НЕ делал — `node_modules` в песочнице нет.

---

## 3. Как устроено внутри

### 3.1 Сборка графа зависимостей (единственный DI-корень)

`wiring.py:39-118` `build_deps(config, store, dry_run=True)` собирает `Deps`
(`wiring.py:19-36`): config, store, auth, leaddesk, analytics, gates, sender,
suppression, warmup, dns, bitrix, confirm, reply_pipeline, cards, mailbrowser.
Эту же функцию зовут и панель (`api/app.py:32` реэкспорт, `cli.py:475`), и
оркестратор (`cli.py:224-225`) — раньше вайринг дублировался.

Тонкости, которые определяют поведение всей системы:

- Панель собирает `Sender(dry_run=True)` — сама она не шлёт (`cli.py:475`
  вызывает `build_deps` без `dry_run=False`).
- Если `confirm.live_send: true`, внутри создаётся **второй** `Sender` с
  `dry_run=False`, и он отдаётся `ConfirmSend` (`wiring.py:85-91`). Только через
  него ручное «Отправить» уходит в реальный SMTP.
- `BitrixSink` подключается только если задан env `BITRIX_WEBHOOK_URL`
  (`wiring.py:71-74`).
- `CompanyCards` строится всегда, но «активен» только при наличии индекса базы
  обзвона (`wiring.py:62-66`, `company_card.py:444-447`). От `cards.active`
  зависит гейт направлений — в песочнице он спит, на боевом обязателен.
- `ReplyPipeline` собирается ВСЕГДА (`wiring.py:100-103`), включённость
  спрашивается на каждом входящем письме через `panel_settings`.

### 3.2 Схема `sender.db`

Один SQLite-файл, путь из `service.db_path` (`cli.py:45`). Единственный писатель
— класс `Store` (`store.py:604`). PRAGMA: `journal_mode=WAL`, `foreign_keys=ON`,
`busy_timeout=5000`, `synchronous=NORMAL` (`store.py:619-624`). Транзакции —
`BEGIN IMMEDIATE` + RLock на соединение (`store.py:652-662`), поэтому Store
потокобезопасен, но пишет строго по одному.

DDL целиком — `store.py:285-596`. `init_schema()` (`store.py:626-650`)
идемпотентен и до `executescript` докатывает ALTER-миграции для боевых БД
(колонки `priority_max/priority_total/pxr/region/tz` у recipients и
`kind/in_reply_to/thread_id` у confirm_reviews).

| Таблица | Строки | Назначение и ключевые поля |
|---|---|---|
| `recipients` | 286-316 | база получателей. UNIQUE по `email`; `inn`, `domain`, `company_name`, `okved`, `segment`, `contact_name`, `mx_provider`, `valid_status` (default `unknown`), `catch_all/role_based/disposable`, `priority_max`, `priority_total`, `pxr`, `region`, `tz`, `extra_json` |
| `campaigns` | 318-331 | кампания: `status` (draft/active/paused/completed), `legal_entity`, `legal_inn`, `provider_pool`, `config_json` (сюда ложатся `segment`, `send_order`, `min_priority_max`, `letter_mode`, `manager_name`, `manager_role`) |
| `sequence_steps` | 333-345 | шаги цепочки: `step_index` (UNIQUE с campaign_id), `delay_hours`, `subject_tmpl`, `body_tmpl`, `engagement_gate` (all/not_bounced/engaged), `include_legal`, `active` |
| `messages` | 347-375 | очередь писем. UNIQUE `idempotency_key`; UNIQUE `rfc_message_id` (partial); `status`, `scheduled_at`, `claimed_at`, `sent_at`, `thread_id`, `in_reply_to`, `subject`, `body_rendered`, `unsub_token`, `attempt_count`, `last_error` |
| `events` | 377-394 | append-only журнал. UNIQUE `dedup_key`; `event_type`, `event_ts`, `detail_json`, `mailbox_id`, `provider` |
| `panel_settings` | 396-400 | key/value настроек панели (JSON в `value`) |
| `suppression` | 401-412 | стоп-лист. UNIQUE (`scope`,`value`), scope ∈ email/domain/inn, `reason`, `expires_at` |
| `mailbox_state` | 414-427 | по ящику: `day_key`, `sent_today`, `sent_total`, `ramp_day`, `daily_limit`, `last_sent_at`, `paused`, `pause_reason` |
| `warmup_state` | 429-439 | прогрев: `phase`, `ramp_day`, `warmup_target`, `warmup_sent_today`, `reputation_score`, `day_key` |
| `consent_log` | 444-456 | ФЗ-152: `action` (send/unsubscribe/complaint/consent/manual_optout/suppression_removed), `basis`, `source` |
| `users` | 461-472 | панель: UNIQUE `username`, `password_hash` (`pbkdf2$iters$salt$hash`), `role` (owner/manager), `totp_secret`, `is_active` |
| `sessions` | 474-485 | UNIQUE `token_hash` (sha256 opaque-токена; сам токен НЕ хранится), `expires_at`, `revoked`, `user_agent`, `ip` |
| `auth_throttle` | 489-494 | антибрут по username: `failed`, `locked_until` |
| `leads` | 496-521 | лид-деск. UNIQUE `dedup_key` (`lead:<thread>` или `lead:<email>`), `status` (new/assigned/taken/qualified/unqualified/closed), `reply_kind`, `phone`, `need`, `readiness`, `assigned_to`, `bitrix_lead_id`, `sla_due_at`, `version` (CAS) |
| `lead_events` | 523-533 | история лида: `action`, `from_status`, `to_status`, `detail_json` |
| `audit_log` | 535-546 | действия оператора: `actor_user_id`, `action`, `entity_type/id`, `detail_json`, `ip` |
| `confirm_reviews` | 552-578 | **очередь подтверждений**. UNIQUE `dedup_key`; `status` (pending/approved/edited/skipped/stoplist/sent/`sending_live`/`bypassed`), `subject`,`body`, `panel_json`, `edited_subject/edited_body/diff_text`, `decided_by/decided_at`, `kind` (outbound/reply), `in_reply_to`, `thread_id` |
| `send_log` | 582-595 | история контактов: `inn`, `email`, `ts`, `rfc_message_id`, `subject`, `outcome` (sent/bounced/replied/failed/`reply_sent`) |

Плюс таблица `ai_letter_log`, которая живёт в ТОМ ЖЕ файле БД, но создаётся и
пишется отдельным соединением из `ai_letter.log_results` / `ai_quota._ensure_log`
(`ai_quota.py:312-320`): `campaign_id, recipient_id, email, status (ok|brak),
subject, body, rounds_json, created_at`. Её нет в `_SCHEMA`.

Статусы `messages` (по коду, не по перечислению в схеме): `pending` (дефолт
колонки), `scheduled`, `sending`, `sent`, `failed`, `skipped`, `pending_review`
(`store.py:1160-1170`), `needs_data` (`store.py:1172-1182`).

### 3.3 Путь письма: от получателя до отправки

Ниже — реальная последовательность вызовов. Два входа в очередь подтверждений:
шаблонный (через оркестратор) и AI-квота (из панели).

**Шаг 0. База.** `importer.import_csv` (`importer.py:195`) стримит CSV,
автодетектит кодировку/разделитель/колонки (`COLUMN_ALIASES` `importer.py:36-56`),
пишет через `store.upsert_recipient`. Upsert нормализует email/домен/ИНН тем же
каноном, что и стоп-лист (`store.py:703-711`, `_normalize_recipient_identity`
`store.py:257-278`) — иначе SQL-сравнения suppression промахивались бы.
`store.upsert_recipient` не затирает непустые поля NULL-ами (`store.py:721-740`).

**Шаг 1. Планирование.** `orchestrator.tick` (`orchestrator.py:335`) для каждой
активной кампании зовёт `cadence.plan_campaign` (`cadence.py:57-113`):
- канареечная волна: пока кампания не отправила `cadence.canary_size` писем и не
  выждала `canary_hold_hours`, планируется только срез (`cadence.py:115-162`);
- таргетинг по `campaign.config["segment"]`, порядок `send_order`
  (`pilot_asc`→`pxr_asc`, `priority_desc`→`pxr_desc`) и порог
  `min_priority_max` — всё уходит в `store.iter_recipients`
  (`store.py:860-892`);
- на получателя `plan_for_recipient` (`cadence.py:386`) применяет гейт шага
  (`evaluate_gate` `cadence.py:205`): ответил → `stop`, suppression → `stop`,
  `not_bounced`/`engaged` смотрят события;
- время шага сдвигается в окно отправки и за праздники (`cadence.py:277-380`).

**Шаг 2. Гейт направлений на входе в очередь.**
`orchestrator._division_queue_block` (`orchestrator.py:295-318`): если индекс
обзвона активен и у компании нет направления (ИНН не из базы) или направление
кампании не совпало — письмо в очередь НЕ ставится вообще.

**Шаг 3. Постановка.** `store.enqueue_message` (`store.py:970-1002`),
`ON CONFLICT(idempotency_key) DO NOTHING` → `(id, created?)`.

**Шаг 4. Захват.** `store.claim_due_messages` (`store.py:1004-1073`) в ОДНОЙ
транзакции берёт `status='scheduled'` с `scheduled_at <= now`, исключая:
получателей с событием `reply` по этой кампании и всех, у кого есть активная
запись suppression по email/домену/ИНН (`store.py:1032-1052`). Отписка
(`reason='unsubscribe'`) действует всегда, даже с `expires_at`. Захваченные
переводятся в `sending` с `claimed_at` (lease). Зависшие возвращает
`recover_stale` (`store.py:685-699`) по `orchestrator.lease_ttl_sec` (дефолт 900 с).

**Шаг 5. Рендер.** `personalize.render` (`personalize.py:220-239`):
- merge-поля собираются в `_base_fields` (`personalize.py:367-400`): email, domain,
  inn, company_name/company, okved, segment, contact_name, first_name, greeting,
  `{equipment}`/`{equipment_all}` из разметки базы обзвона, произвольные `extra`,
  `legal_entity`/`legal_inn` кампании;
- юр-футер ФЗ-38 дописывается безусловно (`_ensure_attribution`
  `personalize.py:339-357`);
- незаполненные `{}` → `unfilled_fields`; при `personalization.fail_on_unfilled`
  (дефолт true) — `PersonalizationGateError`; оркестратор ловит и переводит письмо
  в `needs_data` с причиной (`orchestrator.py:438-463`), а не в `failed`;
- если у кампании `config.letter_mode == "ai"`, вместо шаблона зовётся
  `ai_letter.AiLetterGen` (`personalize.py:241-295`).

**Шаг 6. Развилка confirm-режима.** `orchestrator.py:471-492`: если
`confirm.mode() != 'off'`, письмо НЕ отправляется, а:
`_build_confirm_panel` (`orchestrator.py:267-293`) собирает JSON инфо-панели
(`infopanel.build_panel`), `confirm.submit(...)` кладёт карточку,
`store.mark_pending_review` выводит письмо из авто-отправки. Сбой постановки —
письмо остаётся в `sending` и вернётся через `recover_stale` (вслепую не шлём).

**Шаг 6-bis. AI-квота (второй вход в очередь, минуя оркестратор).**
`AiQuota.run_today` (`ai_quota.py:869-968`): читает дневную квоту из
`panel_settings['ai_daily_quota']`, считает уже сделанное по `ai_letter_log`,
подбирает кандидатов, батчами (по `self._batch`, воркеров —
`ai_quota.workers`, дефолт 15) гоняет `AiLetterGen.generate`, на каждое удачное
письмо создаёт `messages`-строку со статусом `pending_review`
(`_ensure_message` `ai_quota.py:1063-1086`) и зовёт `store.confirm_submit`.
Брак тоже пишется в `ai_letter_log` и съедает квоту.

**Шаг 7. Решение оператора.** `ConfirmSend.approve` (`confirm.py:356-392`) /
`.edit` (`confirm.py:409-448`):
- для исходящих ещё раз проверяется `_guard` (`confirm.py:179-188`): suppression
  и «повторный контакт < 90 дней» по `send_log` (`RECENT_CONTACT_DAYS = 90`,
  `confirm.py:50`);
- `_division_blocked` (`confirm.py:145-154`) блокирует красные флаги направлений;
- `force=True` (второе, личное подтверждение оператора) снимает эти заслоны и
  пишет `audit_log` c перечнем обойдённого (`confirm.py:394-407`);
- если `live` (есть боевой Sender) — `_send_live` (`confirm.py:450-472`)
  атомарно захватывает карточку (`confirm_claim_sending`, `store.py:2294-2304`),
  шлёт и фиксирует `status='sent'`; при исключении карточка возвращается в
  `pending` (`confirm_release_sending`);
- если НЕ live — `store.confirm_decide` (`store.py:2314-2375`) в одной транзакции
  ставит решение и переводит `messages` в `scheduled` (approve/edit) или
  `skipped` (skip/stoplist).

**Шаг 8. SMTP.** `Sender.send` (`sender.py:554-757`), по шагам в коде:
1. гейт незаполненных `{}` → `needs_data` + `PersonalizationGateError` (572-578);
2. идемпотентность: `status=='sent'` → выходим (581-586);
3. suppression-first; подмена адреса, если оператор сменил получателя (589-612);
4. 3b — повторная проверка «пришёл ответ» между claim и send (617-621);
5. kill-switch global → domain → mailbox (625-631);
6. 4b — жёсткий гейт направлений, последний рубеж (636-645);
7. лимит/окно/пейсинг `can_send_now` (650) + пер-регион пейсинг (657-666);
8. сборка MIME, подпись `_apply_signature` (679), пиксель открытий (681);
9. 6b — ещё одна проверка suppression прямо перед сетью, TOCTOU (689-697);
10. `_deliver` → `mark_sent` → копия в IMAP «Отправленные» (`_append_to_sent`,
    711-717) → `send_log_add` → `log_consent` → `increment_sent` →
    событие `sent`.

**Шаг 9. Входящие.** `imap_watcher.poll_once` (`imap_watcher.py:142-225`) берёт
UNSEEN, `BODY.PEEK[]`, классифицирует (`classify` `imap_watcher.py:239-289`):
dsn / complaint / reply / other. `_process_event` (`291-351`) пишет событие
(dsn → канонический тип `bounce`, автоответ → `reply_auto`, чтобы не стопить
цепочку), затем `_handle_reply` (`353-415`):
- `unsub_request` в тексте → suppression + `consent_log`, лид не заводим;
- `not_interested` → молчим;
- иначе `leaddesk.push_warm_lead` и `reply_pipeline.draft_for_incoming`.
Hard-bounce → `suppression.add_email(reason='bounce_hard')`; soft-bounce 4.x.x →
перепостановка письма с суффиксом `:sbr<N>` (`imap_watcher.py:453-...`).

**Шаг 10. Ответ клиенту.** `ReplyPipeline.draft_for_incoming`
(`reply_pipeline.py:61-98`) → `autoresponder.plan/render_reply` →
`review_chain.review_chain` (8 LLM-линз + судья) → `confirm.submit_reply`
(`confirm.py:546-576`, `kind='reply'`, дедуп `reply|<thread|email>`). Оператор
жмёт «Отправить» → `Sender.send_reply` (`sender.py:759-861`): юр-заслон отписки/
жалобы остаётся, окно и пейсинг — нет; `In-Reply-To`/`References` держат тред,
`List-Unsubscribe` в ответ не ставится.

### 3.4 Режимы подтверждения

Задаются конфигом, читаются в `ConfirmSend.mode()` (`confirm.py:163-175`):

| `confirm.mode` | Поведение |
|---|---|
| `off` (дефолт) | `submit` возвращает `bypassed`, оркестратор шлёт по-старому (`confirm.py:236-238`) |
| `all` | каждое письмо — в очередь подтверждений |
| `sample` | каждое N-е (`confirm.sample_every`, дефолт 10) — в очередь, остальные пишутся со статусом `bypassed` как аудит-след (`confirm.py:260-278`) |

Ортогонально: `confirm.live_send` (`wiring.py:85`) — что делает кнопка
«Отправить». `false` → approve только переводит письмо в `scheduled` (уйдёт
оркестратором); `true` → немедленный боевой SMTP из панели.
Третий тумблер — `confirm.allow_out_of_base` / `panel_settings['allow_out_of_base']`
(`confirm.py:87-100`): разрешать ли слать по ИНН вне базы обзвона (дефолт нет).

Заслоны на этапе ОЧЕРЕДИ (при submit) и на этапе ПОДТВЕРЖДЕНИЯ (при approve) —
разные вызовы одного `_guard`; между постановкой и решением адрес мог отписаться.

Стоп-лист из карточки: `ConfirmSend.stoplist` принимает только 4 причины
(`STOPLIST_REASONS` `confirm.py:43-48`): «конкурент» → suppression
`competitor` (+ по ИНН), «нерелевант»/«плохие данные» → `manual`, «по запросу» →
`unsubscribe` (навсегда).

### 3.5 Роли и авторизация

`auth.py`. Только stdlib, намеренно без passlib/pyjwt (`auth.py:3-11`).

- Пароли: `pbkdf2_hmac('sha256', …, 240_000)`, формат
  `pbkdf2$<iters>$<salt_hex>$<hash_hex>` (`auth.py:39,49-68`).
- 2FA: TOTP RFC 6238 на hmac-sha1, окно ±1 шаг, `otpauth://`-URI для QR
  (`auth.py:75-114`).
- Сессия: `secrets.token_urlsafe(32)`, в БД только sha256; TTL 720 часов = 30 дней
  (`auth.py:40-42, 225-228`). `resolve` проверяет revoked/expired/is_active
  (`auth.py:235-247`).
- Антибрут: durable-счётчик по username с локом (`auth.py:198-224`,
  `store.auth_throttle_bump` `store.py:2634`). Сообщение об ошибке всегда одно и
  то же — без деталей.
- Смена пароля и выключение 2FA рвут все сессии пользователя
  (`auth.py:162-185`).
- Роли: `owner` и `manager` (`auth.py:35-37`). В API `Depends(principal)` — любая
  живая сессия, `Depends(owner)` — только owner (`api/app.py:162-174`).

Owner-only эндпоинты (по `Depends(owner)` в `api/app.py`): `/leads/{id}/assign`,
`/recipients/import*`, `DELETE /suppression/{sid}`, `/mailboxes/{id}/pause`,
`/mailboxes/pause-all`, `POST /send-limits`, `POST /autoresponder`,
`POST /sending-window`, `POST /settings/out-of-base`, `POST /ai/quota`,
`POST /ai/quota/run`, `POST /confirm/{rid}/regenerate`, все `/campaigns*` (кроме
`GET /campaigns`), `/users*`, `GET /settings`, `/audit`, `/domains*`,
`/compliance`, `/subject/{email}`.

Всё остальное — под обычной сессией, **включая `POST /confirm/{rid}/decision`**
(`api/app.py:687-689`), т.е. на уровне API решение «отправить письмо» может
принять и manager. Фронт прячет экран `/confirm` за `role="owner"`
(`web/src/App.tsx:43`), но это только UI.

### 3.6 HTTP API панели

`api/app.py:158-1292` `make_app(deps)`. Транспорт тонкий: каждый эндпоинт —
обёртка над методом движка. Авторизация — `Authorization: Bearer <token>`.

Группы:
- **auth**: `POST /auth/login`, `POST /auth/logout`, `GET /me`.
- **лид-деск**: `GET /leads` (+ бейджи «уже отправляли» батчем через
  `store.sent_flags`), `GET /leads/{id}`, `GET /leads/{id}/dialog`,
  `GET /leads/{id}/reply-draft`, `POST /leads/{id}/reply`,
  `POST /leads/{id}/take|status|assign`, `GET /dialog/{recipient_id}`.
- **почта (read-only IMAP)**: `GET /mail/mailboxes|{mb}/folders|{mb}/messages|
  {mb}/message|{mb}/thread`.
- **база**: `GET /recipients`, `POST /recipients/import` (CSV сырым телом,
  `segment` — query-параметр, импорт в фоновом потоке, прогресс по
  `GET /recipients/import/{import_id}` — `api/app.py:387-444`).
- **confirm**: `GET /confirm/queue`, `GET /confirm/{rid}`, `GET /confirm/golden`,
  `POST /confirm/{rid}/decision`, `/mailbox`, `/recipient`, `/regenerate`,
  `GET /confirm/{rid}/regenerate/status`.
- **аналитика/репутация**: `/analytics/dashboard`, `/analytics/rates`,
  `/gates/active`, `/mailboxes/readiness`, `/capacity`, `/warmup`, `/events`,
  `/messages/needs-data`.
- **управление**: `/mailboxes/{id}/pause`, `/mailboxes/pause-all`,
  `/send-limits` (GET/POST), `/sending-window` (GET/POST), `/autoresponder`
  (GET/POST), `/settings/out-of-base` (GET/POST), `/ai/quota` (GET/POST),
  `/ai/quota/run`.
- **админ**: `/users`, `/users/{uid}/activate|deactivate`, `/settings`, `/audit`,
  `/domains`, `/domains/{d}/dns`, `/compliance`, `/subject/{email}`,
  `/profile/password`, `/health`.

`GET /confirm/queue` — самый нагруженный эндпоинт: при сортировке по скорингу он
тянет ВЕСЬ pending (`limit=100000`, `api/app.py:500-515`), сортирует ответы
клиентов выше исходящих, потом режет страницу; дальше на каждую строку считает
`send_as` (доступный ящик), расшифровывает ОКВЭД, пересобирает блок «кому пишем»
и превью подписи (`api/app.py:551-646`).

### 3.7 Фронт (`web/`)

React 18 + react-router 6 + @tanstack/react-query, сборка Vite
(`web/package.json`). Точка входа `web/src/main.tsx`, роутер `web/src/App.tsx`,
реестр 23+ экранов `web/src/lib/screens.ts` (у каждого — путь, роли, флаг `live`).
API-клиент `web/src/api/client.ts` (`API_BASE = "/api"`, Bearer-токен из
`AuthProvider`, `ApiError` со статусом). Экраны: `Login`, `Dashboard`, `Leads`,
`LeadCard`, `Confirm` (1118 строк — карточка подтверждения со всеми блоками
панели), `Mail`, `Recipients`, `DomainWizard`, `views.tsx` (кампании, логи,
репутация, suppression, ящики, ёмкость, статистика, профиль), `admin.tsx`
(кампании-детали, домены, прогрев, комплаенс, настройки, аудит).
Два экрана честно помечены заглушками (`/sequences`, `/templates` —
`web/src/lib/screens.ts:60-61`, причины — там же в `BACKLOG_ENDPOINTS:70-71`),
потому что отдельной сущности в движке нет.

### 3.8 Остальные модули движка (кто кого зовёт)

| Модуль | Роль | Кто вызывает |
|---|---|---|
| `store.py` | единственный писатель БД | все |
| `sender.py` | выбор ящика, гейты, SMTP | orchestrator, confirm, warmup, panel |
| `orchestrator.py` | tick-цикл | `cli run`, `tools/dryrun_basemerge.py` |
| `confirm.py` | очередь подтверждений | api/app, cli, wiring |
| `cadence.py` | планирование касаний | orchestrator |
| `gates.py` | kill-switch репутации | orchestrator, sender, wiring |
| `suppression.py` | стоп-лист | sender, confirm, imap_watcher, unsub, importer |
| `imap_watcher.py` | приём входящих | orchestrator |
| `reply_classify.py` | классификация ответа | imap_watcher, autoresponder |
| `autoresponder.py` | план + рендер ответа | reply_pipeline, review_chain |
| `review_chain.py`/`review_lenses.py` | 8 LLM-линз + судья | reply_pipeline, ai_letter, ai_quota |
| `reply_pipeline.py` | черновик ответа в очередь | wiring |
| `leaddesk.py` | очередь лидов, CAS-переходы | api/app, wiring, imap_watcher |
| `bitrix.py` | лид в Bitrix24 | wiring (только при `BITRIX_WEBHOOK_URL`) |
| `analytics.py` | read-only отчёты | api/app, cli |
| `warmup.py` | микро-прогрев ящиков | orchestrator, cli |
| `ramp.py` | единый резолвер рамп-кривой | sender, warmup, orchestrator |
| `personalize.py` | merge-рендер + гейт `{}` | orchestrator, cli |
| `ai_letter.py` | AI-генерация первого касания | ai_quota, personalize |
| `ai_quota.py` | дневная квота генерации | api/app |
| `infopanel.py` | JSON инфо-панели оператора | orchestrator, ai_quota, api/app |
| `company_card.py` | карточка по ИНН + гейт направлений | wiring, sender, confirm, orchestrator, ai_quota |
| `mailbrowser.py` | read-only IMAP-браузер | api/app, wiring |
| `unsub.py` / `unsub_server.py` | отписка RFC 8058 + пиксель | отдельный процесс |
| `tracking.py` | пиксель открытий | sender, unsub_server |
| `notify.py` | Telegram/Max алерты | orchestrator (опц.), cli |
| `validation.py` / `dns.py` / `dnscore.py` | MX/SPF/DKIM/DMARC | importer, wiring |
| `regions.py` | регион РФ → таймзона | importer, ai_quota |
| `tokens.py` | HMAC-подпись токенов | sender, unsub, tracking |
| `errors.py` / `dtos.py` | общая иерархия исключений и DTO | всё дерево |
| `snyatye.py` | стоп-лист снятых с производства серий | infopanel, autoresponder |

---

## 4. Данные и где они лежат

- **`sender.db`** — SQLite, путь из `service.db_path`. В образце конфига это
  `C:\sender\sender.db` (`config/sender.example.yaml:10`), на Linux —
  `/var/lib/sender/sender.db`. В репозитории боевой БД нет (проверено:
  `find seo-texts -name "*.db"` пусто).
- **`sender.yaml`** — боевой конфиг. В репозитории только образец
  `config/sender.example.yaml` (217 строк, все секции с комментариями) и
  `config/domains.json`. Секреты только именами env (`password_env`,
  `unsub_secret_env`, `token_env`).
- **`panel_settings`** (в той же БД) — живые настройки панели без рестарта:
  `send_limits`, `sending_window`, `autoresponder_enabled`, `allow_out_of_base`,
  `ai_daily_quota`, `ai_quota_run`.
- **Индекс базы обзвона** — отдельный SQLite (`obzvon.index_path`), строится
  `sender/tools/build_obzvon_index.py` из CSV (~161 761 юрлицо). От него зависит
  гейт направлений: нет индекса → `cards.active=False` → гейт спит.
- **`enrich.db`** (`obzvon.enrich_db` или env `ENRICH_DB`) — компании/контакты/
  сигналы для инфо-панели (`infopanel.load_enrich_lead` `infopanel.py:59`).
- **`kb/snyatye-verdict.json`** — стоп-серии, путь `seo-texts/kb/`
  (`snyatye.py:20`).
- **`web/dist/`** — сборка SPA. В git закоммичен ТОЛЬКО `web/dist/index.html`
  (`git ls-files`), а сам каталог в `web/.gitignore`. Ассетов
  (`/assets/index-*.js`) в репозитории нет — без `npm run build` панель отдаст
  index.html, который сошлётся на несуществующий бандл.
- **Отчёты/артефакты рядом с кодом**: `REVIEW-FINDINGS.json` (138 КБ),
  `module-docs.json` (199 КБ), `review-tails-report.json`,
  `autoresponder-golden-report.json`, `calibration-dryrun-report.json`,
  `overlap-analysis.json`.
- **Документация внутри `sender/`**: `CONTRACT.md` (41 КБ),
  `SENDER-ARCHITECTURE.md` (187 КБ), `SITE-DESIGN.md` (108 КБ),
  `SENDER-STATE.md` (57 КБ), `RUNBOOK-DEPLOY.md` (36 КБ), `PANEL-HOWTO.md`,
  `HOW-IT-WORKS.md`, `MAILBOXES-SETUP.md`, `DOMAINS-SETUP.md`,
  `AUTORESPONDER-ROADMAP.md`, `REPLY-TAXONOMY.md`, `MAX-NOTIFY-SPEC.md`,
  `OPEN-TRACKING-SPEC.md` и др. Часть устарела — см. §6.

Переменные окружения, которые реально читает код:
`SENDER_CONFIG` (`cli.py:39`), `<password_env>` каждого ящика — обязателен на
старте, иначе `Config.load` падает (`config.py:409-413`),
`UNSUB_SIGNING_SECRET`/`legal.unsub_secret_env` (`sender.py:1019-1021`),
`BITRIX_WEBHOOK_URL` (`wiring.py:72`), `TELEGRAM_BOT_TOKEN` (`cli.py:239`),
`MAX_BOT_TOKEN`, `POSTOFFICE_TOKEN`, `SENDER_NEW_USER_PASSWORD` (по умолчанию,
`cli.py:747`), `ENRICH_DB`, `E2E_API_PORT`/`SENDER_API_URL`/`PW_CHROME` (тесты).

---

## 5. Ограничения и грабли

1. **Панель сама не отправляет.** `build_deps` даёт ей `Sender(dry_run=True)`.
   Живая отправка из панели существует, только если в конфиге
   `confirm.live_send: true` — тогда `ConfirmSend` получает отдельный боевой
   Sender (`wiring.py:85-91`). Если владелец жалуется «нажимаю Отправить, а
   письма нет» — сначала смотреть этот ключ и `deps.confirm.live` (его же панель
   возвращает в `GET /confirm/queue` полем `live`).
2. **`confirm.mode: off` = очереди нет вообще.** Дефолт именно `off`
   (`confirm.py:165`), и тогда оркестратор шлёт напрямую.
3. **Гейт направлений выключается сам, если нет индекса обзвона.** В песочнице
   `cards.active=False` и вся защита «Meyer-клиенту не писать про компрессоры»
   молча спит (`sender.py:416-418`, `confirm.py:104-106`,
   `orchestrator.py:303-305`). На боевом индекс обязателен.
4. **Порты dev-режима не сходятся**: `serve-api` по умолчанию 8090
   (`cli.py:790`), Vite проксирует на 8080 (`web/vite.config.ts:12`).
5. **`web/dist` нужно собирать.** `--static-dir` без `npm run build` даёт белый
   экран; `make_site_app` специально отдаёт честный 404 на отсутствующий ассет и
   `no-store` на index.html (`api/app.py:1357-1399`) — это лечили дважды.
6. **Отписка по HTTP выключена по умолчанию.** `_list_unsubscribe_headers`
   (`sender.py:1101-1127`) ставит только `mailto:`; `List-Unsubscribe-Post:
   One-Click` появится, лишь если `legal.unsub_http_enabled: true` И реально
   поднят `unsub_server`. Заявить one-click и не обслужить — хуже для репутации.
7. **Дневной лимит правится только ВНИЗ.** `send_limits` из панели зажимается
   `min(рампа, потолок)` (`sender.py:926-962`) — поднять выше рамп-кривой нельзя.
8. **Окно отправки не применяется к ручной отправке.** `manual=True` пропускает
   окно и пейсинг, но пауза/лимит/kill-switch остаются (`sender.py:463-516`).
   `force=True` снимает вообще всё, включая suppression, — и обязан оставить след
   в `audit_log` (`confirm.py:394-407`, `sender.py:603-609`).
9. **Отписку нельзя снять.** `store.suppression_remove` бросает `ValidationError`
   на `reason='unsubscribe'` (`store.py:1998-2001`), API отвечает 409
   (`api/app.py:474-485`).
10. **`open`-события справочные.** Российские провайдеры проксируют картинки;
    пиксель не входит в гейты (`tracking.py:7-12`).
11. **Автоответчик по умолчанию ВКЛЮЧЁН.** `ReplyPipeline._enabled`
    (`reply_pipeline.py:42-59`) при отсутствии явной настройки возвращает True —
    осознанно, потому что конвейер только кладёт черновик, но об этом легко
    забыть.
12. **Производительность `GET /confirm/queue`**: при сортировке по скорингу
    тянется весь pending с распакованными panel_json (`api/app.py:501-502`), плюс
    `dialog_thread_company` на каждую reply-строку. На большой очереди это
    заметно.
13. **Один писатель БД.** SQLite + `BEGIN IMMEDIATE` + RLock; параллельная
    генерация в `ai_quota` пишет в очередь под общим локом (`ai_quota.py:906`,
    `922`). Держать несколько процессов, пишущих в один `sender.db`, — плохая идея.
14. **`Config` иммутабелен после `load()`** (`config.py:336-342`) — часть
    настроек (ящики, домены, пороги гейтов) меняется только правкой YAML и
    рестартом службы. Пороги kill-switch экспонированы read-only намеренно
    (`api/app.py:1213`).
15. **Прогрев по умолчанию выключен**: `warmup.enabled_providers: []`
    (`config/sender.example.yaml:133`), `Warmup._is_enabled`
    (`warmup.py:305-310`). См. §6 про то, что будет, если его включить.
16. **`recipients.import` через панель** принимает CSV сырым телом запроса, без
    multipart (`api/app.py:387-437`) — curl-ом это `--data-binary @file.csv`.

---

## 6. Что сломано или устарело

Сначала то, что я проверил по коду и считаю дефектом:

1. **Ответ из карточки лида уходит без привязки к треду.**
   `api/app.py:287` передаёт `in_reply_to=getattr(lead, "reply_to_msgid", None)`,
   но поля `reply_to_msgid` у `Lead` нет (`store.py:62-84`, `_row_to_lead`
   `store.py:2741-2763`), и во всём репозитории оно встречается ровно один раз —
   в этой строке. Значит `in_reply_to` всегда `None`, а `Sender.send_reply`
   выставляет `In-Reply-To`/`References` и добавляет «Re:» только при непустом
   `in_reply_to` (`sender.py:809-829`). Итог: письмо, написанное оператором в
   карточке лида, приходит клиенту отдельным письмом без «Re:».
2. **`In-Reply-To` черновика автоответчика указывает на НАШЕ письмо, а не на
   письмо клиента.** `reply_pipeline.py:95` берёт `ev.rfc_message_id`, а он в
   `imap_watcher.classify` (`imap_watcher.py:246-252`) заполняется из заголовка
   `In-Reply-To`/`References` ВХОДЯЩЕГО, то есть это Message-ID нашего исходного
   письма. Message-ID самого входящего сохраняется в
   `detail["in_reply_to_hdr"]` (`imap_watcher.py:314`), но в панель черновика не
   попадает. Тред у клиента, скорее всего, всё равно склеится по References, но
   формально ссылка неверная.
3. **`warmup` с реальным `Store` отправить не может.** `_build_message`
   (`warmup.py:385-403`) собирает синтетическое сообщение с `recipient_id=0`, а
   `Sender.send` на шаге (3) делает `store.get_recipient(0)` → `None` →
   `mark_failed` + `SendError` (`sender.py:589-592`). Проверено, что
   `get_recipient(0)` у настоящего Store возвращает None (запускал на временной
   БД). В тестах прогрева подставляется фейковый Sender
   (`tests/test_warmup.py:241`), поэтому сьют этого не ловит. Практического вреда
   сейчас нет: прогрев выключен пустым `enabled_providers`. **Это утверждение
   стоит перепроверить скептику** — я не запускал `warmup.run_cycle` с боевым
   Sender.
4. **`Unsub.list_unsubscribe_headers` — мёртвый код.** Вызывается только из
   тестов (`tests/test_unsub.py:193,401,447`); в письмах используется собственный
   `Sender._list_unsubscribe_headers` (`sender.py:551`). Форматы у них разные
   (в `unsub.py:99` mailto собирается из названия юрлица), так что ориентироваться
   надо на `sender.py`.
5. **`postoffice.py` (463 строки) — модуль без вызывающих.** Ни один
   продакшн-модуль его не импортирует (проверено grep-ом по всему `sender/`, вне
   `tests/`). Тест `tests/test_postoffice.py` (652 строки) есть, конфиг-секция
   `postoffice` в образце есть, но в рантайме код не исполняется.
6. **`assemble_arch.py` и `gen_module_docs.py`** — вспомогательные скрипты для
   генерации `SENDER-ARCHITECTURE.md`/`module-docs.json`, никем не импортируются.
   Это нормально (они запускаются вручную), но к работе панели отношения не имеют.
7. **`PANEL-HOWTO.md` устарел** (датирован 2026-07-20). Он утверждает, что
   «разделение КЦ/Meyer НЕ работает», что загрузки CSV в панели нет и что
   пер-регион пейсинга нет. Всё три пункта с тех пор сделаны:
   `cadence.plan_campaign` читает `campaign.config["segment"]`
   (`cadence.py:82-102`), `POST /recipients/import` существует
   (`api/app.py:417`), `send_pacing.per_region_interval_sec` применяется
   (`sender.py:657-666`). Не опираться на этот файл.
8. **`DomainWizard` ничего не создаёт.** Экран `/domains/new` умеет только
   проверить DNS (`web/src/screens/DomainWizard.tsx:26-27` → `GET
   /domains/{d}/dns`); POST-эндпоинта для добавления домена в API нет. Добавление
   домена — по-прежнему правка `mailboxes` в YAML + рестарт.
9. **Решение по письму на уровне API доступно роли `manager`** —
   `POST /confirm/{rid}/decision` висит на `Depends(principal)`
   (`api/app.py:687-689`), в отличие от `regenerate`/`ai/quota`, которые
   owner-only. Ограничение только во фронтовом роутере.
10. **Незакоммиченные правки в рабочем дереве** (`git diff` в корне репо):
    - `sender.py` — добавлены `_SENT_FALLBACKS`, `_sent_folder`,
      `_append_to_sent` и её вызов после `mark_sent` (копия письма в IMAP-папку
      «Отправленные», выключается `imap.append_sent: false`);
    - `cadence.py` — `plan_for_recipient(..., steps=)` и
      `evaluate_gate(..., replied=, suppressed=)` для экономии запросов;
    - `store.py` — из `sent_flags` убран `LOWER(email)`, чтобы работал индекс
      `ix_sendlog_email`;
    - `tests/test_fix_p1.py` — подгонка под эти правки.
    Сьют с ними зелёный (1078 passed). Но в git их ещё нет — при развёртывании
    из репозитория этих фич не будет.

---

## 7. Быстрый справочник: типовые операции

```bash
cd /home/user/avto/seo-texts            # всё запускать отсюда

# схема БД
python -m sender --config /path/sender.yaml init-db

# база получателей
python -m sender --config /path/sender.yaml import base.csv --map email=Email,segment=База
python -m sender --config /path/sender.yaml validate --limit 500

# кампания
python -m sender --config /path/sender.yaml campaign-create --name "КЦ пилот" \
    --segment кц --send-order pilot_asc --min-priority-max 4
python -m sender --config /path/sender.yaml campaign-add-step --campaign 1 --index 0 \
    --subject "Тема" --body-file touch1.txt --delay-hours 0 --gate all
python -m sender --config /path/sender.yaml campaign-activate --campaign 1

# один тик оркестратора вхолостую (ничего не уйдёт)
python -m sender --config /path/sender.yaml run --once --dry-run --campaigns 1

# очередь подтверждений из консоли
python -m sender --config /path/sender.yaml confirm-queue --limit 20
python -m sender --config /path/sender.yaml confirm-show 42
python -m sender --config /path/sender.yaml confirm-decide approve 42 --operator kirill
python -m sender --config /path/sender.yaml confirm-decide stoplist 42 --reason конкурент
python -m sender --config /path/sender.yaml confirm-golden --out golden.json

# аварийный стоп
python -m sender --config /path/sender.yaml pause --scope global --reason "всплеск баунсов"
python -m sender --config /path/sender.yaml resume

# панель
python -m sender --config /path/sender.yaml serve-api --host 127.0.0.1 --port 8090
python -m sender --config /path/sender.yaml serve-api --port 8090 --static-dir sender/web/dist

# тесты
python3 -m pytest sender/tests/ -q -rs
```

---

## 8. Что не проверено

Честный список того, чего я НЕ делал и в чём не уверен.

1. **Живую БД `sender.db` не видел.** В песочнице её нет
   (`find seo-texts -name "*.db"` пусто). Всё про схему — из `_SCHEMA` и
   миграций в коде. Реальная боевая БД может содержать колонки/таблицы, которых
   в `_SCHEMA` нет (например, `ai_letter_log` создаётся отдельно; допускаю, что
   там есть и другие следы прошлых версий). Утверждать «такой таблицы/колонки
   нет» по этому документу нельзя.
2. **Боевой `sender.yaml` не видел** — только `config/sender.example.yaml`.
   Реальные значения `confirm.mode`, `confirm.live_send`, списка ящиков,
   `obzvon.index_path`, `warmup.enabled_providers` мне неизвестны. Все выводы
   вида «по умолчанию X» — про дефолты в коде, а не про боевую настройку.
3. **Ничего не запускал против сети**: ни SMTP, ни IMAP, ни провайдерский API,
   ни `run_on_server.py`, ни `drop_client.sh`. Поведение
   `Sender._deliver`, `_append_to_sent`, `imap_watcher.poll_once`,
   `mailbrowser.*`, `bitrix.*`, `notify.*`, `dns.*`, `postoffice.*` проверено
   только чтением кода и тестами с фейками.
4. **Фронт не собирал и не запускал**: `npm ci`/`npm run build`/`npm test`/
   `npm run e2e` не выполнялись (нет `node_modules`). Утверждения про экраны —
   из чтения `.tsx`. Реально ли Playwright-сьют проходит, я не знаю.
5. **Читал целиком** `store.py` (по частям, все ключевые методы), `sender.py`
   (ключевые методы), `orchestrator.py`, `confirm.py`, `wiring.py`, `cli.py`,
   `auth.py`, `leaddesk.py`, `reply_pipeline.py`, `ramp.py`, `api/app.py`,
   `unsub.py`, `unsub_server.py` (частично). **Читал выборочно (шапка + список
   функций + отдельные места)**: `ai_letter.py` (1237 строк — промпты RULES_KC/
   RULES_MEYER и гейт я пролистал, не разобрал построчно), `ai_quota.py`,
   `infopanel.py` (1037 строк — разобраны `build_panel` и `_stop_flags`, не все
   блоки), `analytics.py`, `gates.py`, `warmup.py`, `cadence.py`,
   `personalize.py`, `imap_watcher.py`, `suppression.py`, `company_card.py`,
   `bitrix.py`, `mailbrowser.py`, `validation.py`, `notify.py`, `tracking.py`,
   `review_chain.py`, `review_lenses.py`, `autoresponder.py`,
   `reply_classify.py`, `importer.py`, `config.py`.
6. **Не проверял `tools/`**: `build_obzvon_index.py`, `calibration_dryrun.py`,
   `check_domains.py`, `dryrun_basemerge.py`, `gen_redirects_nginx.py`,
   `review_verify.py`, `run_golden_review.py`, `smoke_boxes_live.py`,
   `y360_aliases.py` — только видел их имена и то, что они импортируют.
7. **Не сверял с боевым сервером**, какие службы реально подняты (панель,
   оркестратор, unsub_server), на каких портах и под каким пользователем. Всё в
   §2.2 — из `deploy/` и кода, не из живой машины.
8. **Не проверял точность больших MD-документов** внутри `sender/`
   (`CONTRACT.md`, `SENDER-ARCHITECTURE.md`, `SITE-DESIGN.md`, `SENDER-STATE.md`,
   `RUNBOOK-DEPLOY.md`). `PANEL-HOWTO.md` устарел точно (§6.7); про остальные не
   знаю — предполагаю, что часть тоже отстала от кода.
9. **Не воспроизводил** дефекты из §6.1-6.3 в рантайме — они выведены из чтения
   кода. Особенно осторожно относиться к §6.3 (warmup): вывод построен на
   цепочке «recipient_id=0 → get_recipient вернёт None», проверен только на
   пустой временной БД.
10. **Не измерял** реальную нагрузку `GET /confirm/queue` (§5.12) — вывод
    качественный, из чтения кода.
11. **Ветки `origin/*` не сверял** построчно: возможно, в
    `origin/claude/hopeful-galileo-n8gg7o`, `origin/claude/nifty-shannon-7nw58j`,
    `origin/claude/persona-prompt-seo-sender-vi4tcq`,
    `origin/claude/rusprom-b2b-email-templates-8rrstf`,
    `origin/claude/youthful-sagan-ny4fm6` есть более новая версия части файлов.
    Я работал с текущей рабочей копией (ветка
    `claude/seo-texts-enrichment-prompt-449lyw` + незакоммиченные правки).
