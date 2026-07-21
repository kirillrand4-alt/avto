# Незавершённое по проекту (актуальный список, 2026-07-21)

Собрано из ВСЕХ планово-документных файлов (OWNER-TODO, ROADMAP, FEATURES-PLAN,
AUTORESPONDER-ROADMAP, OPEN-TRACKING-SPEC, MAX-NOTIFY-SPEC, ENGINEER-PROMPT-2026-07-20,
RUNNER-SETUP, email-assistant/{PLAN,PLAYBOOK,CONTACT-ENRICHMENT-PLAN,DOMAINS-PREP-PLAN,
DOMAINS-24-ASSIGN,REPLY-DESK}, kb/FILTER-PLAN, MARKUP-ROADMAP, guest-posts/pilot-report, CLAUDE.md).

Теги: **[авто]** — можно без владельца · **[влад]** — нужен владелец (оплата/DNS/ключи/данные/
решение) · **[HOLD]** — под холдом на прогрев/отправку (снимает только команда владельца).

> ⛔ СКВОЗНОЙ ХОЛД: реальный прогрев и боевые SMTP-отправки НЕ запускать. Всё «боевое» ниже висит на нём.

---

## 1. Рассыльщик / движок (ветка `persona-prompt-seo-sender-vi4tcq`, 718 тестов зелёные)
- **[авто] P1.5 БЛОКЕР — таргетинг сегмента КЦ vs Meyer:** фильтр `segment` в `iter_recipients`,
  `Campaign.segment`, проброс в `plan_campaign`. Сейчас кампания шлёт по ВСЕЙ базе — направления не развести.
- **[авто] Open-tracking (OPEN-TRACKING-SPEC, не начато):** пиксель `GET /o/<token>` в unsub_server,
  HMAC-токен, вставка в personalize, событие `open` с дедупом+отсевом префетча, `open_rate` в отчёт/панель, тесты.
- **[авто]+[влад-токен] Max-канал (MAX-NOTIFY-SPEC, P0, не начато):** `MaxSink` в notify.py,
  конфиг `channel: telegram|max|both`, общий дебаунс/тихие часы, тесты. Владелец: Max-бот + `MAX_BOT_TOKEN`.
- **[авто] P1.6 приоритеты PxR:** импортёр тянет priority_max/total/pxr; `send_order: pilot_asc|priority_desc`
  + порог `min_priority_max`; панель показывает PxR/сортировку.
- **[авто] Панель/движок пробелы:** `POST /recipients/import` (CSV+сегмент+прогресс)+экран; добавление
  домена из панели; тайминг «9:00 по зоне получателя» (хранить TZ получателя); пейсинг по региону.
- **[авто] P1 identity-баг:** `errors.py`/`dtos.py` сделать пакетно-импортируемыми (убрать fallback-копии),
  тест identity (raise в одном модуле → catch в другом).
- **[авто] P2 консолидация 6 примитивов (рефактор, отд. PR):** резолвер рамп-кривой; общий HMAC
  sign/verify (tracking+unsub); общий MX-резолвер (dns+validation); единая нормализация email/домена
  (suppression+validation); судья через review_lenses; `build_deps` для cli+api.
- *Готово:* движок 20 модулей + веб-панель (фазы 1, 2.1–2.3); smoke на `mail.parsercompressor.online`.

## 2. Автоответчик на входящие (AUTORESPONDER-ROADMAP, фазы A–F)
- **[авто] A:** свериться, что `reply_classify` реально даёт 11 классов; `autoresponder.py`
  (`plan()`, `render_reply`, русские шаблоны); тесты по классам/pilot.
- **[авто] B ревью-конвейер:** `qa_reply()` гейт; `review_lenses.py` 8 линз (провайдер, строгий JSON);
  судья `review_chain()` (qa→8 линз→SEND/FIX/ESCALATE, лимит 2); golden-тест 14 писем.
- **[авто] C пакеты:** КЦ (PLAYBOOK 7 типов + answer-kb цифры), Meyer few-shot, роутинг по кампании/сегменту.
- **[авто] D интеграция:** imap_watcher→plan()→Actions (draft/snooze/forward/flag/bitrix_push/notify);
  извлечение лида провайдером→leaddesk; состояния `deferred(until)`/`redirect` + follow-up.
- **[влад] E живая проверка:** s2→s1 имитации 7 классов на `C:\sender` — нужен `PROVIDER_API_KEY` в env
  службы; спарринг оператора, порог «отправил бы?» ≥80%.
- **[HOLD] F:** пилот-черновики (человек одобряет) → авто на «безопасных» типах.
- *Готово частично:* базовая классификация, imap_watcher, leaddesk, notify, таксономия, спека линз.

## 3. Обогащение контактов 161 761 (CONTACT-ENRICHMENT-PLAN; task #16/#19)
- **[авто] Фаза 0 (первой, защищает домен):** валидация 107k email — синтаксис→MX→SMTP-ping +
  детект **catch-all/disposable/role-мусор**, колонка `email_status`. (MX+провайдер есть, catch-all — нет.)
- **[авто] Фаза 1:** пилот enrich топ-200 по PxR С сайтом (сайт→/contacts→ролевые email→MX), цель ≥40%.
- **[авто] Фаза 2:** DaData по 54k без email (ACTIVE+директор+адрес, отсечь банкротов; 10k/день бесплатно).
- **[авто, идёт] Фаза 3:** хвост без сайта → найти сайт (xmlriver/2ГИС/Я-карты) → краул. **← активная работа сейчас.**
- **[влад] решение:** подтвердить порог топ-30% PxR + отмашка на Фазу 0+1.
- **СДЕЛАНО сверх плана (эта сессия):** xmlriver-kg discovery; добор mailto/tel/JSON-LD/обфускация;
  Dolphin пробивает защищённые сайты (sibur/severstal); dolphin_pool (персистентные профили);
  инкрементальная двойная запись enrich.db+jsonl; модель-тест (haiku на массу).

## 4. Новости-лиды (task #18)
- **[авто, идёт] Ротация мобильных IP** для Google News (обойти рейт-лимит) — перезапустить (был осиротён рестартом).
- **[авто] Посрегионный свип** 85 регионов × триггеры + **районные фиды** (малые города) в news-sources.json.
- **[авто] OK/Telegram** коллекторы (best-effort); тюнинг VK под районные паблики.
- **[авто] Раскидать news-лиды** по направлениям kc/meyer под нужные ящики; писать в enrich.db (сделано).

## 5. Домены / инфраструктура (24 домена куплены; DOMAINS-24-ASSIGN)
- **[влад]** организации в Я360/VK; верификация доменов; DNS (MX/SPF/DKIM2048/DMARC) вставка;
  301-редиректы (КЦ→prokompressor.ru, Meyer→vsefotoseparatory/meyer-corp); ~72 ящика + app-пароли;
  Postmaster; трекинг-поддомены+TLS; `legal.inn` Руспрома.
- **[авто]** генерация DNS-шаблонов; заполнение `sender.yaml` (после ящиков); настройка `unsub_server`+трекинг;
  `dry_run: true` smoke; перепроверка свободности доменов.
- **[влад] раннер на сервере (RUNNER-SETUP):** установка службы NSSM + `CAPMONSTER_KEY`; один боевой прогон
  `verify_company._fetch` (обход Turnstile, РФ-IP). *(Раннер по факту уже поднят и работает в этой сессии.)*
- **[HOLD]** прогрев волнами (Волна 1: 8-10 доменов) → bounce<2%/жалобы<0.1% → DMARC p=reject → боевой пуск.

## 6. Гост-посты (task #9)
- **[авто]** починить 2 из 5 пилотных: `dizel-na-strojke` (JSONDecodeError) + `podbor-vintovogo` (стоп-слово «берите»).
- **[влад]** вычитка 3 готовых статей владельцем → **[авто]** масштаб на 18 акцепторов.

## 7. Email-ассистент / корпус (PLAN, REPLY-DESK — ждёт владельца)
- **[влад]** выгрузка 800 исходящих + 1600 входящих цепочек ЦЕЛИКОМ на дроп; исходы из CRM (thread→сделка/
  отказ/сумма); сильнейший менеджер + матрица «что обещать без согласования»; связка «запрос→КП»;
  решения: лид-vs-сделка, роутинг менеджеров, юр-линия B2B/согласие, раскрытие ИИ, канал очереди лидов.
- **[авто, после корпуса]** разметка 2400 писем→types.json+golden-pairs+STYLE-GUIDE-EMAIL; few-shot;
  regex-скраббер ПД перед отправкой в API; валидация «прайс не старше X дней».

## 8. Прочее
- **[влад] Schema-разметка (MARKUP-ROADMAP):** починка карточек (AggregateRating внутрь Product, не рендерить
  Offer с пустой ценой, itemprop=image); Article/ImageObject на 1017 страниц проектов; заполнить поля
  NewsArticle блога; проверить/подключить YML-фид в Яндекс.Вебмастер; мелочи Service/LocalBusiness. (Правки шаблонов Битрикс/Aspro.)
- **[влад] FAQ-фильтр (FILTER-PLAN):** собрать таблицу «вопрос корзины-3 → нужные данные» и спросить Кирилла,
  есть ли данные (прайсы/паспорта/сертификаты дилерства/замеры шума), прежде чем выкидывать.
- **[влад] Bitrix/Telegram доступы (OWNER-TODO):** BITRIX_WEBHOOK_URL; TELEGRAM_BOT_TOKEN+ops_chat_id;
  POSTOFFICE_TOKEN (mail.ru); PROVIDER_API_KEY в env службы на C:\sender.

---
### Что делаю автономно сейчас (не требует владельца, HOLD соблюдён)
Обогащение Фаза 3 (прогон-500 + разбор разметок) · новости (ротация IP + регионы) · dolphin_pool ·
гост-посты фикс 2 статей. Всё пишется в enrich.db+jsonl, коммитится в ветку.
