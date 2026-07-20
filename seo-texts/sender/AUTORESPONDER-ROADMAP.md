# Дорожная карта: АВТООТВЕТЧИК (робот ответов на входящие) для чистой сессии

**Итог:** робот первой линии, который на КАЖДЫЙ входящий ответ по нашей рассылке
делает: классификация → план действий → генерация ответа → **прогон через 8
ревьюеров** → черновик оператору (пилот) / авто-отправка (потом) → тёплый лид с
телефоном в Bitrix + алерт продажнику. Цель — снять с людей переписку-квалификацию,
оставить им только звонки по готовым тёплым телефонам.

## КАК ПРОДОЛЖИТЬ В НОВОЙ СЕССИИ (сделать ПЕРВЫМ)

```
git fetch origin && git checkout claude/persona-prompt-seo-sender-vi4tcq
git pull origin claude/persona-prompt-seo-sender-vi4tcq
cd seo-texts/sender && pip install pytest fastapi httpx uvicorn aiosmtpd tzdata
python3 -m pytest tests/ -q          # ожидается 619 passed (база до автоответчика)
```
Читать вместе: `REPLY-TAXONOMY.md` (11 классов на живых письмах Meyer),
`REVIEW-CHAIN.md` (8 ревьюеров, решение владельца), `CONTRACT.md` (интерфейсы),
`SENDER-STATE.md` (состояние+уроки), `../email-assistant/` (КЦ-пакет: PLAYBOOK,
answer-kb, email_answer.py, dryrun-letters.json).

## КОНСТАНТЫ (соблюдать)

- **Тяжёлое (кодоген, ревью-линзы) — через провайдер** (`../gen_provider.py`,
  `claude-fable-5`), НЕ токенами сессии. Токены сессии — оркестрация.
- **Баг шлюза (проверено 2026-07-20):** upstream по fable-5 бывает флаки — 503
  «model_not_found» через раз, иногда HTTP 400 «failed after 20 attempts».
  Рецепт: `thinking=False`; effort НЕ слать; ОДИН поток; префилл ассистента для
  текстового канала; **ретраи 10-12 с бэкоффом+джиттером**; короткий ответ
  считать провалом и ретраить; контекст <50KB; кэш по стадиям (резюмируемо);
  **фолбэк-модель `claude-opus-4-8`** (тоже провайдер) после N неудач fable-5 —
  логировать, какой моделью сгенерено.
- **«Код компилится ≠ дописан»** — покрывать тестами; обрезки шлюза видны только
  тестами. Живой деплой на C:\sender уже ловил такой баг (`MailboxCfg.email`).
- **Все цифры/модели/сроки в письмах — ТОЛЬКО из базы** (answer-kb / факты
  брендов). Факт-чекер-ревьюер блокирует выдуманное.
- **ФЗ-38:** атрибуция ООО «Руспром» + ИНН 2221239841 в каждом письме (ставит
  personalize, в шаблоны не вшивать). Без длинных тире, подпись менеджера (не «ИИ»).

## СТАТУС: что УЖЕ есть (НЕ переделывать)

- `reply_classify.py` — базовая классификация (hot/interested/neutral/auto_reply/
  not_interested/unsub_request) + `classify_reply_ai` (Protocol) + extract_phone.
  imap_watcher уже зовёт `classify_reply(subject, snippet, headers)`.
- `imap_watcher.py` — приём, DSN/complaint/reply, `reply_auto` не стопит цепочку.
- `leaddesk.py` — `push_warm_lead(recipient, thread_id, snippet)`, статусы лидов, CAS.
- `notify.py` — Telegram, событие `warm_lead_created`.
- `REPLY-TAXONOMY.md` — 11 целевых классов + 7 реальных few-shot (Meyer).
- `REVIEW-CHAIN.md` — спека 8 ревьюеров + судья + петля перегенерации (лимит 2).
- КЦ-пакет в `../email-assistant/`: PLAYBOOK (7 типов + лестница контакта),
  answer-kb.json, dryrun (14 писем, скептик ловил торг №9 и цифры №3/5/12).
- Движок задеплоен на `C:\sender` (BOX1/BOX2 = s1/s2 Яндекс, БД, 39 ИНН suppression).

---

## ФАЗА A — ядро классификации + план действий (провайдер, thinking=False, тесты)

- **A.1 `reply_classify.py` → 11 классов.** Добавить бизнес-классы: `deferred`,
  `redirect`, `wrong_contact`, `objection_tech`, `objection_status_quo`,
  `competitor_in_place`. Обратная совместимость (старые kind + сигнатура
  `classify_reply(subject, snippet, headers)` не ломать). Маркеры вывести из
  реальных писем REPLY-TAXONOMY + синонимы. `ReplySignal` +поля `redirect_hint`,
  `deferred_hint` (дефолт None). Порядок: служебные → hot → redirect → deferred →
  wrong_contact → objection_* → competitor → interested → not_interested → neutral.
- **A.2 `autoresponder.py` (новый, чистая логика без I/O).** `@dataclass Action`
  (kind, payload). `plan(signal, ctx, mode='pilot') -> list[Action]` по маппингу
  из REPLY-TAXONOMY/REVIEW-CHAIN (hot→reply_auto+bitrix_push+notify; deferred→
  reply_draft+snooze(90); redirect→forward+reply_draft; wrong_contact→flag_contact+
  reply_draft; objection_*/competitor→reply_draft; auto_reply→[]; unsub→suppress).
  В `mode='pilot'` все `reply_auto` → `reply_draft`. `render_reply(kind, ctx) ->
  (subject, body)` — русские шаблоны, тон инженер-практик, подпись «{manager},
  ООО «Руспром»», без тире, безопасный format.
- **A.3 тесты**: по классу; pilot-понижение; рендер без KeyError на пустом ctx.

## ФАЗА B — ревью-конвейер (8 ревьюеров + судья + перегенерация)

- **B.1 `qa_reply()`** — механический гейт (образец `../qa_text.py`): тире,
  плейсхолдеры, длина, байлайн, подпись, стоп-слова, пустая тема.
- **B.2 `review_lenses.py`** — 8 линз (см. REVIEW-CHAIN §Слой1), каждая = вызов
  провайдера, строгий JSON `{verdict:PASS|WARN|CRITICAL, problems, fixes}`.
  Факт-чекер получает релевантный срез answer-kb/фактов; линзы параллелятся
  (но на флаки-шлюзе — по одному потоку с ретраями, не гнать 8 разом на одном ключе).
- **B.3 судья + `review_chain(email, ctx) -> (decision, final_email, verdicts)`**:
  qa → 8 линз → судья (SEND/FIX/ESCALATE). FIX → перегенерация с fixes, **лимит 2**,
  дальше ESCALATE. `reply_auto` только при SEND и пустых CRITICAL. Встроить между
  `render_reply` и Action `reply_*`.
- **B.4 golden-тест**: 14 писем `../email-assistant/dryrun-letters.json` через
  конвейер — обязан поймать торг №9 (ESCALATE) и цифры №3/5/12 (CRITICAL).

## ФАЗА C — сценарные пакеты (КЦ + Meyer) над ядром

- **C.1 КЦ-пакет**: подключить `email-assistant/PLAYBOOK.md` (7 типов, лестница
  контакта, стоп-темы эскалации) как шаблоны/правила `render_reply` для компрессоров;
  `answer-kb.json` — источник цифр для факт-чекера; лестница «крупная сделка →
  сразу звонок инженера».
- **C.2 Meyer-пакет**: few-shot из REPLY-TAXONOMY (рентген/фотосепараторы).
- **C.3 роутинг пакета** по кампании/сегменту получателя (КЦ vs Meyer).

## ФАЗА D — интеграция в приём + извлечение лида

- **D.1** `imap_watcher` → на `reply` вызвать `plan()` → исполнить Actions
  (reply_draft в очередь; snooze/forward/flag через store/leaddesk; bitrix_push;
  notify). `reply_auto` слать SMTP только вне pilot и при SEND.
- **D.2 извлечение лида** (провайдер): из ответа тянуть потребность/объём/давление/
  сроки/бюджет-сигнал/телефон/готовность 0-10 → строка очереди (REPLY-DESK формат)
  → `leaddesk.push_warm_lead`.
- **D.3 новые состояния лида**: `deferred(until)`, `redirect(new_contact)` — не
  closed, а активные с планировщиком follow-up (store + orchestrator tick).

## ФАЗА E — живая проверка на s1↔s2 (без холодной рассылки)

- **E.1** На `C:\sender` (открыт SMTP/IMAP) отправить с s2 на s1 письма-имитации
  7 классов → оркестратор ловит по IMAP → классифицирует → строит план → ревью →
  черновик. Проверить каждый класс end-to-end. `PROVIDER_API_KEY` в env сервера.
- **E.2** Спарринг: оператор играет клиента, робот отвечает, «отправил бы?» ≥80%
  (метод из REPLY-DESK go-live).

## ФАЗА F — пилот-режим → авто

- **F.1 pilot**: робот кладёт ЧЕРНОВИКИ, человек одобряет/правит/шлёт; правки →
  золотые пары → few-shot генератору и ревьюерам.
- **F.2** авто-типы (наличие/каталог/простая квалификация) → авто при SEND судьи;
  цены/торг/крупное — всегда человек. Метрики: %SEND с 1-й попытки, время 1-го
  ответа (<15 мин — козырь), конверсия ответ→телефон, жалобы.

## Порядок и зависимости

```
A (ядро) → B (ревью) → C (пакеты) → D (интеграция+лид) → E (живая s1↔s2) → F (пилот→авто)
```
Минимум для живой проверки: A + B + D.1 + E.1. КЦ-пакет (C.1) обязателен до
пилота по компрессорам. Прогрев боевого домена — ПОСЛЕ того как автоответчик
отлажен (решение владельца: сперва автоответчик).

## Артефакты владельца (когда до них дойдёт)

`PROVIDER_API_KEY` на деплой-хосте (env) для AI-разбора/ревью на сервере;
BITRIX_WEBHOOK_URL (тёплые лиды); Telegram (алерты) — см. OWNER-TODO.md.
