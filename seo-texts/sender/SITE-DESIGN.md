# SITE-DESIGN — проверенный макет веб-панели (Фаза 2.0)

Сгенерировано мульти-модельной панелью 2026-07-18 по ROADMAP 2.0:
8 персон-проектировщиков -> кросс-опыление -> судья -> **фактчек-линза против
реального API движка** (обязательная — без неё панель дублирует реализованное).
Сырьё всех раундов (16 файлов персон+кросс) — на drop: `site-design-panel-raw-2026-07-18.tar.gz`.

Как читать: раздел «Макет» — что строим; раздел «Фактчек» — вердикт по каждому
экрану (UI-ONLY / NEW-BACKEND / BUILD-NEW / DROP) и бэклог API Фазы 2.1.
Правило проекта: перед реализацией любого экрана сверься с вердиктом фактчека.

---

# ЧАСТЬ 1. МАКЕТ (судья)

I'm organizing the design panel structure into a unified layout: consolidating the 8 zones and cross-pollination rounds into a master screen map with deduplicated routes and role-based access, then breaking down each screen into its component blocks, key interactions, and data requirements. I'll also catalog the shared UI elements like tables and filters, then prioritize implementation across P1, P2, and P3 tiers.

Now I'm mapping out the actual screens across all zones to eliminate duplicates — the operator, sales, and IA zones all reference similar screens like the dashboard, campaigns list, and leads feed, so I need to consolidate these into a single authoritative set of routes and determine which roles access what. Reputation monitoring and warmup planning round out the mailops zone, then I'm looking at a minimal zone with just the core dashboard, campaigns, domains, mailboxes, and leads. There's also a security zone covering authentication, user management, and compliance features. Now I'm starting to consolidate these zones by identifying which routes should merge together—the dashboard endpoints across multiple zones are a natural starting point. Individual lead views at `/leads/:id`, personal dashboard at `/my-leads` and `/stats`. For the infrastructure side, I'm consolidating mailboxes, accounts, and domains into a unified cluster with warmup functionality. Reputation monitoring gets merged from two separate routes, and sequences/templates stay separate since the stakeholders explicitly rejected them.

On the editor front, there's tension around whether to build a full WYSIWYG interface—one stakeholder invested heavily in that, but most others said a simple textarea with merge fields and validation is sufficient. I'm going minimal here: textarea-based editors with spam and legal footer checks, no drag-and-drop or visual builder. A/B testing is also contentious; most zones say the segments are too small for it to matter, but I'll mark it as P3 optional rather than cutting it entirely.

Then I've got suppression lists, email logs with detailed message views, and a general settings area to round things out.

Looking at the remaining routes—users, secrets, profile, login, audit, compliance with consent tracking, and analytics provider integration—I'm seeing some overlap I could consolidate. But more importantly, there are three critical gaps that came up repeatedly across feedback: a race condition when leads are grabbed that needs optimistic locking plus real-time sync, a reverse webhook from Bitrix when deals close to keep things in sync, and what looks like an incomplete thought on a third issue. 10. **Right to be forgotten / GDPR subject export** — endpoint to retrieve and delete all subject data (p8)
11. **Unsubscribe or complaint handling on active warm leads** — mark as "do not call", halt the sequence, alert the team (p5, p7, p8)
12. **Suppression list validation before Bitrix sync** (p2, p5, p8)
13. **Provider reputation matching** — route Mail.ru recipients through mailboxes with established Mail.ru sender reputation (p6)
14. **Warmup progression tracking with ability to revert** (p6)
15. **Silent failure detection** — alert when delivery/sent ratio drops below 95% despite low bounce rates (p6)
16. **Manual intervention for provider blocks** — handle SMTP 550 errors (p6)
17. **Pre-launch capacity planning** — calculating wave size against...

Continuing with the remaining features: mailbox capacity constraints, two-factor authentication with risk-based token shortcuts for Telegram stops and PII protection, user deactivation and lead reassignment during offboarding, engagement unlock when recipients reply, live segment preview in the funnel, deduplication by INN and company, and phone number standardization.

There's tension between the design teams on mobile support — most pages argued for desktop-only, but one pushed for mobile-first on alerts and leads, so we're going with mobile for those specific areas.

On the template editor, there's disagreement about WYSIWYG versus code editing — most preferred textarea-based editing, one team built a full visual editor, so we're keeping it minimal with textarea, merge variables, spam checking, and legal footer validation. A/B testing was mostly rejected due to small segment sizes and lack of statistical power, though one team implemented it anyway — we're deferring that but keeping canary deployments as the universal safety mechanism. The sequence editor visual canvas was built by one team, though the note cuts off mid-discussion.

Kill-switch threshold editing has universal agreement to keep it hardcoded in the engine with no UI. For suppression management, there's tension between CLI-only (safer) and full UI — we're resolving with a view-only interface plus audited manual additions restricted to owners, while the engine handles automatic additions. Analytics placement differs across implementations — some built it as a separate zone, others integrated it into campaign details — so we're consolidating the funnel view into the campaign details tab and keeping the reputation monitor separate, dropping the standalone analytics dashboard.

For warmup and domain management, there's a split between rich UI and CLI-only approaches. We're going with a read-mostly UI that lets owners pause or override limits with audit trails, plus a wizard for adding new mailboxes.

Now I need to write this up concisely under the character limit. I'm aiming for roughly 550-650 lines of dense content, structured as a screen map table, detailed breakdowns by screen, shared components, and priority levels.

Starting with the screen map: I'll define roles as owner-operator, salesperson, and team lead (optional), then list each screen with its route, applicable roles, and which planning clusters it addresses. Continuing with the remaining routes — sequence previews, domain management, mailbox configuration, warmup settings, reputation monitoring, email logs, suppression lists, and compliance features, each mapped to their respective permissions and priority levels.

I'm consolidating some of these screens to stay within constraints: merging analytics and providers into reputation, folding consent into compliance, and combining users and secrets as tabs within settings. I'll defer A/B testing variants as a lower-priority feature and keep it concise — just blocks, actions, and data in compact form for each screen.# Единый макет панели «Руспром» — вердикт судьи

Синтез 8 зон + 8 кросс-раундов. Дедуплицировано, кластеры объединены, спорное разрешено. Роли: **О** — владелец-оператор, **П** — продажник (28 чел), **Т** — тимлид (опц.). Продажники видят только лид-контур.

---

## 1. Итоговая карта экранов

| # | Экран | Роут | Роль | Слит из |
|---|-------|------|------|---------|
| 1 | Вход | `/login` | все | p8 |
| 2 | Дашборд | `/` | О (П → редирект `/leads`) | p1·p3·p4·p7 |
| 3 | Кампании | `/campaigns` | О | p1·p3·p7 |
| 4 | Конструктор кампании | `/campaigns/new`, `/:id/edit` | О | p1·p3·p7 |
| 5 | Детали кампании (+воронка) | `/campaigns/:id` | О | p1·p3·p4·p7 |
| 6 | Лента лидов | `/leads` | О·П·Т | p1·p2·p3·p7 |
| 7 | Карточка лида | `/leads/:id` | О·П | p2·p3·p4 |
| 8 | Мои лиды | `/my-leads` | П (О·Т — по команде) | p2·p3 |
| 9 | Моя статистика | `/stats` | П·О(агрегат) | p2 |
| 10 | Цепочки | `/sequences` | О | p5 |
| 11 | Редактор цепочки | `/sequences/:id/edit` | О | p5 |
| 12 | Шаблоны | `/templates`, `/:id/edit` | О | p5 |
| 13 | Превью цепочки | `/sequences/:id/preview` | О | p5 |
| 14 | Домены | `/domains`, `/domains/:domain` | О | p1·p6·p7 |
| 15 | Ящики (+рамп) | `/mailboxes`, `/:id/ramp` | О | p1·p6·p7 |
| 16 | Прогрев | `/warmup` | О | p6 |
| 17 | Монитор репутации | `/reputation` | О | p4·p6 |
| 18 | Логи (+письмо) | `/logs`, `/logs/email/:id` | О | p3·p4 |
| 19 | Suppression | `/suppression` | О | p3·p8 |
| 20 | Комплаенс (+субъект ПД) | `/compliance`, `/subject/:email` | О | p8·p4 |
| 21 | Настройки (табы: команда/секреты/Bitrix/Telegram/ФЗ) | `/settings` | О | p3·p8 |
| 22 | Профиль | `/profile` | все | p8 |
| 23 | Аудит | `/audit` | О | p8 |

**Отклонено как отдельные экраны:** `/analytics` дашборд (слит в `/`), `/analytics/campaign/:id` (таб в #5), `/analytics/providers` (блок в #17), `/sequences/:id/variants` A/B (отложен, см. §5), `/users`+`/secrets`+`/consent` (табы в #21/#20).

---

## 2. Детализация экранов

### 1. Вход `/login`
**Блоки:** email/пароль, 2FA (TOTP для О обязательна), «доверенное устройство 30 дней» (для П).
**Действия:** логин → аудит `user.login` → редирект (`/` для О, `/leads` для П). 3 фейла/5мин → блок IP 10 мин + Telegram О.
**Данные:** `users`(argon2id, totp_secret, role), `sessions`(JWT+fingerprint).

### 2. Дашборд `/` (О)
**А. Светофор репутации (липкий верх):** единый кружок зелёный/жёлтый/красный = max(complaint, bounce, Постофис Mail.ru). Тап → сплит по провайдерам (M/Я/прочие). Пороги: complaint <0.08/0.08–0.1/>0.1%, bounce <2.5/2.5–3/>3%. Кнопка **«ОСТАНОВИТЬ ВСЁ»** (пауза всех + блок отправки 15 мин; на мобиле — свайп-подтверждение).
**Б. Активные кампании (3–5 карточек):** прогресс волн, лидов сегодня, ETA + **светофор ёмкости** (свободный daily_limit живых ящиков нужного пула vs размер волны). Действия: пауза / «след. волна сейчас» (если engagement выше порога).
**В. Инфра (свёрнуто по p7):** только проблемные ящики/домены (застрял в рампе, manual action, лимит ≥90%, DNS ✗); норма — «7 в норме».
**Г. Активность команды (из p8):** последние 5 `audit_log` (кто взял лид, создал кампанию, экспортировал ПД).
**Данные:** real-time агрегаты `events`(complaint/bounce/delivered) 2ч, `campaign_waves`, `leads today`, `audit_log`.
**Продажнику дашборд не показываем** — редирект на `/leads`.

### 3. Кампании `/campaigns` (О)
**Таблица:** Название · Статус · **Причина паузы** (manual/kill_switch_complaint/kill_switch_bounce/smtp/DNS — дыра p3) · Сегмент · Прогресс · Тёплых · CR%/BR% (**sparkline 7д** из p4) · Дата.
**Действия в строке:** пауза/возобновить, дублировать, детали. Tooltip на паузе: «последняя пауза 12.01 (О), причина: complaint spike» (p1). Сортировка: активные→paused→draft→completed; сортировка по CR/BR для поиска проблемных.
**Данные:** `campaigns`, `campaign_stats` daily, count `leads WHERE hot/interest`.

### 4. Конструктор кампании `/campaigns/new` (О)
Wizard 3–4 шага (компромисс p3-wizard × p1-форма):
**Шаг 1 Сегмент:** фильтры ОКВЭД/регион/размер/домен получателя (AND). **Live-превью с debounce 300ms** (p3): «4521 компания, 3890 на Mail.ru/Яндекс, −320 suppression = 4201». Suppression вычитается по умолчанию.
**Шаг 2 Цепочка:** выбор из библиотеки (`Прогрев ритейл v3 · 2.1% hot` — из p5×p1) или новая. Engagement-гейты, delays. **Симулятор охвата:** «шаг 3 увидят ~340 из 1000».
**Шаг 3 Отправка:** выбор ящиков — **dropdown отфильтрован по флагу «Готов к бою»** (p6: рамп done + DKIM/SPF/DMARC зелёные + Постофис ≥ good + нет manual action). **Провайдер-гейт:** для Mail.ru-сегмента доступны только ящики с Mail.ru-репутацией ≥good. **DNS preflight** (p1×p6): ❌ блокирует «Запустить», ⚠️ разрешает с предупреждением.
**Шаг 4 Гейты (readonly):** канарейка 50→ждём→complaint<0.05%; kill-switch пороги — hardcoded, изменение = код движка.
**Действия:** «Сохранить черновик» / «Запустить канарейку» (вкл. по умолчанию, снимается чекбоксом «сегмент проверен»).

### 5. Детали кампании `/campaigns/:id` (О)
**Шапка:** статус, крупная «Пауза/Возобновить/Убить». **Alert-баннер причины автопаузы** (p3): «Complaint 0.12% Mail.ru, порог 0.10% → [Снизить лимиты и возобновить] [Архивировать]».
**Kill-switch метрики:** прогресс-бары complaint/bounce общий + по провайдерам, цвет за 10% до порога. Клик по «Mail.ru 0.11%» → модалка: 20 последних complaint (кто), «Заблокировать Mail.ru для кампании», «→ suppression».
**Воронка (таб, из p4):** свёрнута `5000→4680(−320 suppr)→4550 delivered→347 ответ→89 тёплых(72 hot/17 инт)→34 квал→12 закрыто`. Каскад по шагам цепочки + сплит по провайдеру-получателю + сплит по домену-отправителю (клик → `/domains/:d`). Этапы кликабельны → `/leads?campaign=:id&status=hot`.
**Волны:** timeline, «форсировать» (если engagement канарейки >15%). **Confidence-бейдж** при N<100 (p4): «малая выборка, возможен шум».
**Мини-схема цепочки:** сколько отсеялось на каждом гейте (p1×p5).
**Данные:** `events`, `campaign_waves`, `sequence_steps`+гейты, `leads`.

### 6. Лента лидов `/leads` (О·П·Т)
**Фильтры (липкие):** статус лида (новый/взят/позвонил/квал/не-квал/в Bitrix) · приоритет (hot/интерес/автоответ) · дата · кампания · **волна** (канарейка/основная) · поиск ИНН/название. Для Т — «моя команда» (p3). Дефолт-сорт: hot→интерес→свежие.
**Таблица/карточки:** Компания(ИНН) · **Контакт маскирован для П до «Взять»** (Иван…, +7·····34 — p8 data-minimization) · Потребность (цитата 80 симв.) · Приоритет (🔥/⭐ бейдж, hot = красная граница 4px+bold) · **Время без движения** (жёлтый >2ч, красный >4ч) · Кампания · Взял · Статус Bitrix.
**Действия:** **[Взять]** с **оптимистичной блокировкой** (`UPDATE WHERE assigned IS NULL` → 0 строк = тост «уже взял Петров», строка гаснет у всех через WebSocket/polling 15с — дыра p1·p2·p7). Bulk: →квал/→не-квал/экспорт CSV (П — только свои, watermark, аудит). Свайп влево на мобиле = «Взять» с откатом при таймауте (p7 оффлайн).
**Live:** новый hot → push с deep-link + плашка «+2 новых» (не дёргать под пальцем).
**Флаг «ОТПИСАЛСЯ — звонить нельзя»** при suppression-хите (дыра p5·p7·p8).
**Данные:** `leads`, `lead_assignments`, `companies`, `bitrix_sync`, `suppression`.

### 7. Карточка лида `/leads/:id` (О·П)
**Шапка:** компания, ИНН (ссылка СПАРК/Контур), контакт. **[Позвонить]** (tel:, крупная — частый сценарий), [Скопировать телефон] (+ «Нормализовать» → E.164, p2), [→ Bitrix24].
**История переписки** (мессенджер-стиль): исходное письмо кампании → ответ клиента (classification) → цепочка. **Блок «Что мы писали»** (кампания/шаг/тема, p3-стык). **Блок «Предыдущие кампании»** (по ИНН — дыра p3: «уже отказывались, нет $»). Дедуп: «2 контакта: director@ (hot), sales@ (интерес)» (p2).
**Панель действий:** [Позвонил]→результат, [Квалифицировать]→форма (потребность/объём/сроки/бюджет предзаполнено из письма) → **[Создать лид в Bitrix]** с **проверкой suppression + записью основания в consent_log** (p2·p5·p8). [Не квалифицирован]→причина (dropdown). **[Переклассифицировать]** (override IMAP + аудит, p2). **Блок «Источник контакта»** (p1×p8): дата в базе, источник, consent — для быстрого ответа РКН.
**Стоп цепочки:** при квал/отказе — авто-отмена scheduled писем + `campaign_exclusions` (дыра p5); плашка «осталось 3 письма, будут отменены».
**Данные:** `leads`, `email_threads`, `campaign_emails`, `events`, `consent_log`, `bitrix_sync`.

### 8. Мои лиды `/my-leads` (П) · 9. Статистика `/stats` (П)
**My-leads:** та же таблица, фильтр по себе, колонка «последнее действие», **таймер «взят 1:47»**. Счётчики: в работе (красный >10), квал сегодня, просрочено >2ч. **SLA-возврат:** взят без действия 2ч → назад в пул + push «лид ушёл» (дыра p1·p2·p7).
**Stats:** воронка Взял→Позвонил→Квал→Bitrix, среднее время до звонка (цель <2ч), топ-5 причин не-квал, источник по домену-отправителю (p2×p6: «домен Б даёт 3% CR — довести прогрев»).

### 10–13. Цепочки/шаблоны/превью (О)
**`/sequences`:** таблица (название, статус, охват, Open%, hot, complaint, bounce M/Я/др), клон, kill-switch подсветка. Колонка «активные кампании» (блок удаления используемых, p5).
**`/sequences/:id/edit`:** вертикальный **список шагов** (НЕ drag-drop canvas — см. §5): письмо/задержка/гейт. Гейты: всем / не открыл / не ответил / не стал тёплым. **🔓 «Разблокировать цепочку при ответе»** (дыра p5: клиент проснулся из спама). Канарейка + окно 9–18 по TZ получателя (из ЕГРЮЛ-региона). **Timeline отправленных волн:** правка применяется только к неотправленным; модалка «1200 получили v2, изменить для 3800?» (дыра p1·p5).
**`/templates/:id/edit`:** textarea + merge-поля `{{company_name}}`,`{{inn}}`,`{{contact_name}}` (**НЕ WYSIWYG**). Юр-футер ФЗ-38 (ООО+ИНН) автоматический, нередактируемый. **Спам-проверка** (CAPS>30%, спам-слова, !!!). **Блокирующий комплаенс-гейт** (p8): нет атрибуции/List-Unsubscribe → «Запустить» серая. Версионирование + **аудит кто/когда** (p5×p8).
**`/preview`:** рендер на реальном юрлице (поиск ИНН), merge подставлен, тайминги по TZ, симулятор гейтов, **чек suppression получателя**, **тест-отправка себе** через рабочий ящик (проверить inbox/спам, p5×p6).

### 14–16. Домены/ящики/прогрев (О)
**`/domains`:** плитки (готовы к рассылке X/Y, в прогреве Z, проблемных N). Таблица: домен · статус · ящиков · репутация · Постофис Mail.ru · провайдер-сплит · DKIM/SPF/DMARC ✓/⚠/✗ · действия. **DNS-health — слепая зона всех** (p6): протухший ключ = тихий спам без bounce. Кнопка «Проверить DNS сейчас».
**`/mailboxes`:** свёрнуто проблемные (p7). Колонки: email · провайдер · **«Готов к бою»** (composite: рамп+DNS+Постофис+нет manual action) · лимит/отправлено · IMAP-статус. **Провайдер-матрица** (ящик × Mail.ru/Яндекс/прочие) — кормит гейт конструктора. Действия: пауза, форс волны, override лимита (**аудит** `mailbox.limit_override`), «Переподключить OAuth» (токен на бэке, на фронт — только status/last4/expires — p8).
**`/mailboxes/:id/ramp`:** история рампа по дням (плановая доза/факт/complaint/bounce/решение движка: держим/растим/**откатываем** — дыра p6), «заморозить рамп» (аудит).
**`/warmup`:** календарь готовности, wizard добавления (CSV-импорт creds, пресеты Осторожный/Стандарт/Агрессивный).

### 17. Монитор репутации `/reputation` (О)
Kill-switch дашборд реального времени (плитки общие + по провайдеру, timestamp срабатывания). График 7д complaint/bounce vs пороги с маркерами событий рампа. **Алерт «тихая деградация»** (p6): delivered/sent <95% при bounce<1% = фолдинг в спам Mail.ru — ловит то, что kill-switch пропускает. **Ротация при manual action** (SMTP 550): авто-вывод ящика + перераспределение квоты + чеклист ручного разбора в Яндекс360. Тренды по провайдерам (из p4). Suppression-счётчики.

### 18. Логи `/logs` (О) — 2 вкладки (p3×p8)
**«Отправка»:** email · кампания/письмо№ · ящик · провайдер получателя · статус · детали (bounce reason/FBL). Фильтры, экспорт CSV (аудит). `/logs/email/:id` — цепочка касаний + SMTP-метаданные + «Добавить в suppression» (hard bounce) + «Переклассифицировать».
**«Аудит действий»** (p8): ts · actor · ip · действие · объект. Сюда стекаются kill-all, пауза, правка шаблона, suppression, Bitrix-передача, смена статуса, `secret.view`, экспорт ПД.

### 19. Suppression `/suppression` (О) — ФЗ-152 центр
Табы email/домен/ИНН. Источник каждой записи (one-click RFC 8058 / жалоба / ручное / ИНН-блок). Ручное добавление — аудируемое. **Связка «тёплый отписался»:** попадание в suppression адреса с активным `lead_assignment` → флаг в `/my-leads` взявшего + Telegram ему (главная сквозная дыра p8). Экспорт для бэкапа.

### 20. Комплаенс `/compliance` + `/subject/:email` (О)
**Дашборд:** карточки (suppression по причинам, отписок за 7д тренд, **адресов без consent — красный если >0**, кампании с превышением complaint). Таблицы отписок/жалоб — **email маскирован** (u***@dom.ru).
**`/subject/:email`** (право на забвение / запрос РКН): вся история по адресу — отправки, ответы, consent (основание+timestamp+источник), жалобы, suppression-статус, факт передачи в Bitrix. «Экспорт для РКН» (CSV/PDF) + «Обезличить». Сам просмотр/экспорт — аудируется.

### 21. Настройки `/settings` (О) · 22. Профиль `/profile` · 23. Аудит `/audit`
**Settings-табы:** Команда (28 П: роль/статус/последний вход, **деактивация → рвёт сессии + переназначение взятых лидов** — офбординг, дыра p8) · Секреты (Bitrix/Telegram — маскировано last4, реаутентификация перед заменой) · Bitrix (URL, маппинг полей) · Telegram (chat_id) · Compliance (ФЗ-38 реквизиты, ФЗ-152 статистика, RFC 8058 endpoint).
**Profile:** смена пароля (инвалидация чужих сессий), 2FA (QR TOTP), активные сессии (завершить).
**Audit:** таблица с фильтрами (actor/тип/дата/email получателя), экспорт ≤100k строк, retention 3 года.

---

## 3. Общие компоненты

- **DataTable:** TanStack, виртуальный скролл, сортировка, bulk-чекбоксы, sparkline-колонки, on-row-click, пагинация/виртуализация. На мобиле → карточки.
- **FilterBar:** липкая, чипы, live-count с debounce, deep-link через query-params (`?campaign=42&status=hot`).
- **AlertBar / Светофор:** единый кружок (max метрик) + drill-down; для мобилы схлопнут. Deep-link из Telegram.
- **Status-бейджи:** кампания (Draft/Canary/Active/Paused/Completed/Killed), лид (новый/взят/позвонил/квал/не-квал/в Bitrix), классификация (🔥hot/⭐интерес/🤖автоответ/❌отказ/🚫отписка), ящик (Cold/Warming/Warm/Готов к бою/Manual action), DNS (✓/⚠/✗), провайдер (M/Я/др).
- **Прогресс-бары с порогами:** kill-switch метрики, рамп-прогресс (цвет за 10% до лимита).
- **Модалка переписки/письма:** IMAP-тело, цепочка, SMTP-детали.
- **Confirm-диалог:** для деструктивного (kill-all, убить кампанию, деактивация) + причина + аудит.
- **Optimistic-lock хелпер:** для [Взять] и любых конкурентных действий.
- **PII-mask:** утилита маскирования по роли (П видит маскировано до «Взять»).
- **Empty states:** «нет данных» + подсказка следующего действия (онбординг новичка).
- **Toast + WebSocket-канал:** live-обновления лент, гашение взятых лидов.

---

## 4. Приоритеты реализации

**P1 — прямо двигает квал-лид / скорость (MVP):**
| Экран | Обоснование |
|-------|-------------|
| `/login`+роли+аудит-каркас | Без auth нельзя пускать 28 чел к базе 161k; аудит-хуки дешевле встроить сразу. |
| `/leads` + optimistic-lock + live | Ядро для 28 продажников; гонка за лид = двойные звонки = позор перед клиентом. |
| `/leads/:id` + квал→Bitrix + suppression-чек | Квал-лид в CRM за 2 мин вместо 6; блок нарушения ФЗ до отправки в Bitrix. |
| `/` дашборд + светофор + СТОП | Оператор за 3 сек видит пожар; стоп в 1 клик спасает репутацию доменов. |
| `/campaigns` + `/campaigns/:id` + причина паузы | Запуск/контроль кампаний = источник всех лидов; без причины паузы оператор слеп. |
| `/campaigns/new` + DNS preflight + «готов к бою» гейт | Быстрый запуск + защита от старта с мёртвого домена (убивает репутацию за 10 мин). |
| SLA-возврат лида + флаг «отписался» | Остывший/забытый лид = потерянный квал; звонок отписавшемуся = жалоба. |

**P2 — усиливает качество/скорость, но не блокирует старт:**
| Экран | Обоснование |
|-------|-------------|
| `/sequences`+`/templates` (textarea) | Цепочки — ядро прогрева, но первые можно завести из CLI/дефолтов. |
| Воронка в `/campaigns/:id` | Показывает где проседает конверсия → оптимизация текста/сегмента. |
| `/reputation` + тихая деградация | Раннее обнаружение спам-фолдинга до kill-switch. |
| `/domains`+`/mailboxes` + провайдер-матрица | Правильный ящик под провайдера = меньше bounce на 74% базы. |
| `/my-leads`+`/stats` | Контроль очереди продажника, но лиды берутся и из `/leads`. |
| `/suppression` + связка «тёплый отписался» | ФЗ-152 + защита от жалоб на активных лидах. |
| Bitrix reverse-sync (webhook закрытия сделки) | Убирает вечно-«в работе» лиды, чистит ленту. |
| Мобильные версии `/`, `/leads`, `/leads/:id` | Продажник в поле, владелец реагирует на kill-switch из такси. |

**P3 — ценно на масштабе / редкие сценарии:**
| Экран | Обоснование |
|-------|-------------|
| `/warmup`+`/ramp` wizard | Прогрев работает из движка; UI нужен при масштабировании парка. |
| `/compliance/subject` + экспорт РКН | Критично при запросе, но запросы редки; первые дни можно из CLI. |
| `/logs` обе вкладки | Дебаг-инструмент; критичные события уже в аудите/дашборде. |
| `/settings` все табы | Настраивается раз; правка редка. |
| `/sequences/:id/preview` + тест-отправка | Полезно, но textarea+merge покрывает 90%. |
| A/B `/variants` | Отложено — см. §5. |

---

## 5. Спорные решения (где разошлись и мой выбор)

**Мобильный: строить или нет.** p1/p4/p5/p6 — «только десктоп, оператор за ноутбуком». p7 — «mobile-first для алертов и лидов». **Выбор: гибрид p7.** Мобильно = ровно 3 вещи: светофор+СТОП, лента лидов (свайп-взять), карточка лида (tel:-звонок). Управление кампаниями/цепочками/доменами/аудит — десктоп. Причина: продажник звонит из поля, владелец тушит пожар из такси — это реальные мобильные сценарии; конструктор кампании на телефоне не нужен.

**WYSIWYG-редактор писем.** p5 — полноценный редактор с форматированием. p1/p3/p7/p8 — «textarea, правим в коде, WYSIWYG = XSS/спам-риск». **Выбор: против p5.** Textarea + merge-поля + спам-проверка + автофутер. Причина: HTML-письма чаще летят в спам у Mail.ru/Яндекс (74% базы), plain-text проходит в 3–4 раза лучше; оператор один, пишет редко.

**Визуальный canvas цепочек (drag-drop).** p5 — рисованный canvas. p3 (обрыв текста) склонялся к «нет». **Выбор: список шагов, не canvas.** Вертикальный список письмо/задержка/гейт покрывает линейные цепочки прогрева; drag-drop и ветвления — оверинжиниринг для 5-шаговых линейных цепочек.

**A/B-тестирование.** p5 — полный модуль с автопобедителем. p1/p4/p7 — «сегменты 500–2000, нет статзначимости (нужно >10k на вариант)». **Выбор: отложить в P3.** Оставляю канарейку (универсальный консенсус) как механизм безопасности. A/B добавим при росте объёмов. Если строить — обязателен авто-rollback варианта при kill-switch (p5-кросс), иначе winning-по-open вариант с clickbait убьёт репутацию ночью.

**Suppression-правки через UI.** p8 — «только CLI, риск что удалят жалобщика → бан». p3 — полный CRUD-UI. **Выбор: просмотр + аудируемое ручное добавление (О), удаление только О с подтверждением+причиной.** Авто-добавления (жалоба/bounce/отписка) — из движка. Причина: полный запрет UI замедляет легитимные кейсы, но убирание из suppression огораживаем аудитом.

**Изменение порогов kill-switch через UI.** Все 8 зон — единогласно НЕТ. **Оставлено в конфиге движка.** Слайдер «0.05–0.2%» = риск сжечь домены одним движением; пороги выверены под микс провайдеров.

**Аналитика: отдельная зона или встроенная.** p4 — отдельные `/analytics/*`. Остальные — метрики внутри рабочих экранов. **Выбор: встроить.** Воронка → таб в `/campaigns/:id`, репутация → `/reputation`, тренды провайдеров → блок там же. Причина: оператору нужны решения в контексте («пауза/продолжить»), а не отдельный аналитический раздел; переключение экранов замедляет реакцию.

**Роль «тимлид».** Только p3 предложил промежуточную роль (команды по регионам/вертикалям). **Выбор: заложить опционально (P3).** На старте 2 роли (О/П) — граница чёткая; `team_id` добавляем в схему сразу, UI-фильтр «моя команда» включаем при делении 28 чел на группы.

**Ключевой сквозной принцип синтеза:** панель — не «труба отправки», а контур с обратной связью. Прогрев растёт и откатывается, ящики ротируются при manual action, DNS протухает молча, тёплый лид может отписаться в процессе. Поэтому экраны инфраструктуры (#14–17) кормят **гейтами** конструктор кампаний (#4), а действия в лид-контуре (#7) останавливают цепочки (#11) — зоны не изолированы.

---

# ЧАСТЬ 2. ФАКТЧЕК ПРОТИВ КОДА (ground truth — API движка)

I need to act as a fact-checking lens for the judge's mockup, going through each screen and feature to determine whether it's just a UI layer over existing backend functionality, or if it requires new engine work. For each item, I'll either mark it as UI-ONLY with the relevant method or class name, or flag it as NEW-BACKEND and specify what signature needs to be added.

Now I'm mapping out the ground-truth API across all the modules to establish what's actually available. I'm starting with the Store class and its public methods like transaction handling, recipient management, consent logging, and campaign creation.

Continuing through the message lifecycle methods — enqueueing, claiming due messages, marking delivery status, and tracking events with various filtering options. Adding more database methods... Continuing with the remaining classes... Adding more suppression methods...

The Validation class handles email validation and provider detection, while Analytics provides various reporting capabilities across campaigns, mailboxes, warmup metrics, and global statistics.

The Unsub class manages unsubscribe tokens and one-click unsubscribe handling, the Orchestrator coordinates the overall system with bootstrap, pause/resume, and tick operations, and there's a Bitrix integration for external CRM communication.

Now looking at the notification and postoffice modules — the Notifier handles event-based alerts and digest summaries, while PostofficeClient queries domain reputation metrics like spam rates and generates reports with reputation thresholds.

I'm also seeing the reply classification system that extracts signals from incoming messages and can optionally use AI for more sophisticated analysis, plus all the data transfer objects that structure the engine's internal communication.

But stepping back, I'm realizing what's fundamentally absent here — this is purely an outbound sending engine with no user management, authentication, lead assignment workflows, or the concept of salespeople managing leads.  The mockup shows a whole CRM-lite operation with 28 salespeople taking and qualifying leads, but the backend only handles sending and warming up reputation before pushing qualified leads to Bitrix. That's a massive gap between what the UI promises and what the engine actually supports. The engine has Recipients, Campaigns, SequenceSteps, and queued Messages, but nothing for the lead lifecycle management that the sales team would need. call set_campaign_status when a gate trip occurs, but that connection isn't explicit in the schema. The campaign DTO fields aren't fully visible, and pause reason is flagged as a known gap — it's captured in the gate trip record but may not be directly linked to the campaign status itself.

I need to be precise about what "UI-ONLY" versus "NEW-BACKEND" means here. The engine has no HTTP layer at all, so every screen requires an endpoint. UI-ONLY means the engine already has a method that returns the data; the API just wraps it. NEW-BACKEND means I need to write a new engine method. BUILD-NEW is for entirely new subsystems. With that framing in mind, I can categorize each screen properly. I need to structure this systematically—going through all 23 screens and their features with a verdict for each one. I'll organize it as per-screen tables showing the feature, verdict, and relevant engine method or note. Before diving into individual screens, let me map out the major subsystems that are completely missing: auth and user management (no users table, sessions, roles, or 2FA), and lead assignment workflows. Both of those are BUILD-NEW items with significant scope. Now I'm mapping the existing engine capabilities to the new system—analytics dashboards and reporting, gate evaluation for kill-switch metrics, orchestration controls for pausing and resuming, campaign CRUD operations, and cadence planning logic for sequence evaluation. I'm also tracking reply classification for engagement levels, consent history for GDPR compliance, email logs by RFC ID, event metrics and timestamps, recipient iteration with status filtering, mailbox state management including pause controls, and warmup state persistence. Now I need to figure out which backend methods are missing that would naturally extend the engine.

I'm anticipating a few key gaps: a list method for campaigns to support the `/campaigns` endpoint since we only have iter and get, an update method to edit campaigns beyond just creation and status changes, and a way to surface gate trip reasons linked to campaigns—either through an active trips reader or a dedicated method to fetch gate decisions with their associated reasons.

For leads, the mockup shows recipients who've replied and are warm prospects being managed by sales, but the engine doesn't actually persist lead records with status or assignment data—it just detects warm replies and pushes them to Bitrix. So I need to figure out whether listing leads is a new backend store method or if it's really just querying recipients with event joins. I need to be pragmatic here — theuser wants something actionable. The lead feed with take, status, and SLA is a new subsystem in this engine, so I'll mark that as BUILD-NEW, but the supporting queries that extend existing data can be NEW-BACKEND. I'm also noticing there's a `ReplyDeskSink.push_warm_lead` concept that suggests a "reply desk" pattern I should examine more closely.

So the question becomes: are warm leads living in Bitrix or in the panel? The mockup clearly wants them in-panel with optimistic locking and SLA tracking, which the engine doesn't currently support. I could argue that leads belong in Bitrix and the panel just queries them, but the assignment mechanics and SLA are panel-specific concerns, so I'm treating the lead-work subsystem as BUILD-NEW.

Now I'll go through each screen methodically and mark what needs building versus what can reuse existing infrastructure. I'm starting with the login screen and working through the feature set to determine which pieces are new builds and which have engine anchors.

For the dashboard, I'm looking at the reputation traffic light which pulls data from Analytics global rates, Gates evaluation, and Postoffice reporting—these are all existing systems, so it's just UI aggregation.

The provider breakdown uses Analytics.rates with provider targeting or count_events with the recipient_provider filter, which should support splitting by mail service—also UI-only.

Complaint and bounce thresholds come from Config.gates, and the "STOP ALL" button triggers Orchestrator.pause_all to halt sending for 15 minutes.

The pause itself is UI-only, but the 15-minute auto-resume isn't built into the engine yet—that's either a small backend addition to pause_all or handled as a timed API layer call.

For active campaign cards showing progress, leads today, ETA, and capacity, I'm pulling from Analytics.campaign_report which handles the progress and rates calculations.

Leads today would be counting reply or warm events since midnight—if those event types exist, that's UI-only via count_events. ETA needs a new backend method to estimate completion time based on cadence and analytics. Capacity light requires calculating available daily mailbox limits against the wave size, which also needs backend support.

For actions, pausing is UI-only (just updating campaign status), but forcing the next wave requires a new backend method since there's no wave-forcing capability visible. Infrastructure checks for problem mailboxes and domains would iterate through mailbox states, apply gateway checks, and filter for issues only.

The activity command needs audit log building. Real-time data aggregates events from the last two hours, campaign waves, today's leads, and audit logs—but I'm noticing "waves" keeps coming up (canary thresholds, wave sizing, forcing waves) yet there's no explicit wave entity in the store API. The engine has Cadence and Orchestrator.tick, but wave tracking appears to be missing from the backend.

Looking closer at the mockup, canary logic (send 50, wait, check complaint rate below 5%) is treated as a built-in safety mechanism, but it's not actually exposed in the API. The wave and canary orchestration features are either new backend work or need to be built fresh—they're not currently in the engine.

For the campaigns screen, I need to handle several new backend requirements: listing campaigns (the API has get and create but no list method), displaying campaign status, and managing pause reasons. The salesperson redirect to /leads also requires new role-based routing.

For the table columns, most are UI-only calculations from existing data—status, segment, progress, and warm count all derive from campaign fields or analytics. But I'm missing backend support for pause reasons (need to expose why a campaign is paused) and the sparkline data (need daily conversion and bounce rates bucketed over seven days, since the current events counter doesn't support time-series aggregation).

Row actions split between UI-only operations like pause/resume and details, versus backend work for duplicating campaigns. The pause tooltip showing last pause time and reason requires building an audit log or pause history. Sort is straightforward UI-only.

For the campaign builder's segment step, I need to query recipients based on ОКВЭД codes, region, size, and recipient domain filters combined with AND logic. The live preview should show a debounced count of matching recipients, accounting for suppressions, which requires a new backend method to count recipients minus those in the suppression list.

In step 2, I'm pulling sequence templates from the library with engagement stats, where the gates and delays are handled on the UI side through the Cadence evaluation logic. The reach simulator needs to aggregate the gate funnel across recipients to show how many would see each step—something Cadence can evaluate per recipient but doesn't currently simulate in bulk.

For step 3, I'm filtering the mailbox dropdown to show only "battle-ready" accounts. For DNS health checks, I need a new backend method to validate DKIM, SPF, and DMARC records—either as a new module in the sender package or as a dedicated build. The gates configuration has readonly thresholds for canary and kill-switch logic, plus canary-specific settings that should be exposed through the UI config layer.

On the campaigns detail screen, I'm handling status transitions (pause/resume/kill) through the set_campaign_status method, and the pause reason banner needs backend support for the pause reason itself plus actions to override mailbox limits—there's already a set_mailbox_paused method I can leverage for the "lower limits" action.

For the metrics section, I'm pulling progress bars with per-provider breakdowns that color-code when approaching thresholds using the gates evaluation and analytics rates—all UI-side logic. When clicking into a provider's complaint rate, I need a backend method to fetch the last 20 complaint events with recipient details for that campaign and provider. From there, users can either trip the gate for that provider scope or add emails to suppression, both UI-only operations.

The funnel tab shows the flow from initial sends through delivery, replies, warm leads, qualification, and closed deals, with most stages calculated from campaign analytics and event counts per stage. Qualification and closed stages pull from the lead management system (Bitrix integration), which requires new backend support for lead stats. I can also break down funnel progression by sequence step or recipient provider using event counts.

For the waves timeline, I need to handle the "force wave" feature when canary engagement exceeds 15%, which requires new backend logic for wave management. The confidence badge showing sample size will be computed on the frontend from the event counts. The mini sequence schema tracks how many leads filter through each gate, aggregating gate-level funnels similar to the reach simulator. The underlying data comes from events, campaign waves, sequence steps with gates, and the leads table.

Now moving to the leads feed screen, which is the main lead management interface with filters for lead status including new, taken, called, qualified, and not qualified states. The company table also needs recipient search for finding leads, team filtering for Т, and contact masking until assignment—which requires new backend work for role-based PII handling. The quote snippet needs to be stored and retrievable from the lead data, which means building out a backend store for lead snippets captured during the push_warm_lead process.

For the remaining fields, priority badges mirror the classification system, time-without-movement tracks assignment timestamps, taken-by records who claimed the lead, and Bitrix status pulls from the BitrixSink or requires a reverse webhook for syncing. The Take action uses optimistic locking to prevent double-assignment—if the update finds no unassigned rows, the lead's already been claimed and greys out via WebSocket or polling.

Bulk operations for qualification status and CSV exports need the new backend layer plus audit trails, and mobile swipe-to-take includes rollback capability. New hot leads trigger real-time pushes with a "+2 new" banner through the backend feed and in-app WebSocket notifications. The suppression flag marks leads as "do not call" when they hit the suppression list, linking back to the assigned lead record. I need to figure out whether phone normalization to E.164 is a backend function or handled on the UI side—extract_phone exists but I'm not sure if it normalizes, and p2 explicitly calls out phone standardization as a gap, so I'm marking this as NEW-BACKEND for a normalize_phone function. The Bitrix push uses BitrixSink.push_warm_lead with the card URL, which is UI-ONLY.

For the message history feature, I need to assemble message threads from individual messages—get_message and find_message_by_rfc_id exist per message, but thread assembly requires a new backend function. The "what we wrote" block pulls from existing functions, but showing previous campaigns by INN across all campaigns is new backend work, and deduplicating contacts across different statuses needs handling too.

The action panel has three main flows: marking calls with results, qualifying leads with a form that prefills from the email reply, and creating Bitrix leads with suppression checks and consent logging. The lead status tracking and structured field extraction from replies are new backend pieces, while the Bitrix integration, suppression check, and consent logging stay on the UI side.

For unqualified leads, I'm capturing the rejection reason as a new lead status. The reclassify action lets users override the IMAP classification with an audit trail. The contact source block displays consent history and recipient info from the database.

When a lead qualifies or gets refused, the system auto-cancels any scheduled messages for that recipient across the campaign, showing a banner warning about remaining emails before cancellation. I need to implement backend functions to cancel pending messages and mark them as skipped per message.

Now I'm looking at the data schema—leads, email threads, campaign emails, events, consent logs, and Bitrix sync. For the My Leads screen, I'm building a filtered table showing only the user's assigned leads with a last action column, a timer showing how long they've been working on it, and counters for items in progress, qualified today, and overdue items. When a lead sits untouched for two hours, it returns to the pool and triggers a push notification. The Stats screen displays a funnel from Take to Called to Qualified to Bitrix, average time to first call, top rejection reasons, and source breakdown by sender domain.

For the Sequences section, I'm working with a table showing sequence name, status, reach, open rates, and engagement metrics like complaints and bounces. There's a kill-switch to deactivate sequences and an active campaigns column that prevents deletion if the sequence is in use. The backend doesn't currently have sequences as a standalone entity—they're actually steps within campaigns—so I need to either build out a sequence library or clarify that sequences are campaign steps.

The analytics columns (open percentage, hot, complaints, bounces) are UI-only and pull from event counts tied to sequence steps. Cloning a sequence and tracking which campaigns use it both require new backend endpoints. For the edit view, I need to add update and delete operations for individual steps since the current API only supports creating them.

Gates filter by various conditions (unopened, no reply, not warm) using the existing gate fields and evaluation logic. Reactivating a sequence when someone replies after being gated or cancelled is a backend gap. The sending window respects recipient timezone and holidays at the UI level, but determining timezone by region needs backend support, as does the canary feature. For wave edits, I need to handle applying changes only to unsent messages and prompting users about the impact on already-sent recipients.

The template editor handles merge fields, preview rendering, legal footer injection, and spam detection—most of this lives in the UI layer through the personalizer, while the legal footer auto-applies and spam scoring require backend implementation.

Compliance validation checks for required headers like List-Unsubscribe and attribution, partly handled by the existing PersonalizationGate but also needs a new backend template lint. Versioning and audit trails don't exist yet and need to be built from scratch.

The preview endpoint should render against real legal entities (via INN lookup), apply merge fields, handle timezone-based timings, simulate the compliance gate, and respect suppression rules. For the domains view, I need to aggregate mailbox data by domain since there's no separate domain entity in the backend. The reputation scores come from analytics, and I'm pulling provider splits and DNS validation status (DKIM/SPF/DMARC checks) to show the authentication state. There's also a manual DNS check trigger that needs to be wired up.

For the mailboxes section, I'm listing all mailbox states with their email, provider, and a composite "battle-ready" status that the backend needs to calculate. The IMAP health status isn't currently exposed, so I'll need to add that endpoint. The provider matrix and action buttons for pausing, forcing waves, and reconnecting OAuth are all UI-driven based on the mailbox state.

For the ramp history view, I'm pulling warmup state data from the backend to show planned versus actual delivery metrics, complaint and bounce rates, and engine decisions about holding or growing the ramp. The "freeze ramp" action needs audit logging on the backend side. The warmup calendar would aggregate the schedule from the backend using daily targets, and the mailbox wizard needs to handle CSV credential imports and presets—though mailbox provisioning at runtime isn't currently supported, so that's either a new backend feature or a separate build. For the reputation monitor, I'm looking at a kill-switch dashboard showing real-time tiles for overall and per-provider metrics with trip timestamps, which would be UI-only.

The 7-day graph needs to plot complaint and bounce rates against thresholds with ramp-event markers, requiring time-series data from the backend. The silent degradation alert checks if delivered-to-sent ratio drops below 95% with bounces under 1%, which means computing that ratio from event counts—this could be UI-only if the data's already available, but the alert logic and threshold enforcement would need backend support. The deliverability ratio is computable from existing count_events calls, so this is UI-ONLY rather than a true backend gap—the raw data already exists. For the SMTP 550 rotation scenario, I'm looking at how to detect the error and trigger the manual action workflow through the UI layer. For the logs screen, I need to handle the message log list with filtering and CSV export capabilities backed by the new backend's message querying system. The email detail view chains together SMTP metadata and includes an option to add hard bounces to suppression.

For the suppression screen, I'm looking at implementing tabs for email, domain, and INN entries with a source field per entry. The backend currently has a single-key lookup function but needs a proper list/iteration method to display all suppression entries, and I need to support manual additions with audit tracking and CSV export.

I also need to handle manual removal with confirmation and reason logging through a new backend method, plus implement a "warm unsubscribed" connection that flags suppression hits when an address has an active lead assignment—this requires joining the suppression and assignment tables and triggering notifications through the existing notifier.

For the compliance dashboard, I'm building cards showing suppression breakdown by reason, a 7-day unsubscribe trend, flagging addresses without consent records, and highlighting campaigns exceeding complaint thresholds—most of this pulls from new backend stats and event queries, while the unsubscribe and complaint tables will mask emails on the UI side.

Now I'm designing the subject detail view at `/subject/:email` to display the complete history including sends, replies, consent records, complaints, suppression status, and Bitrix integration, with options to export as CSV or PDF and anonymize the record for GDPR compliance—the consent and suppression data come from the UI store, while sends and replies require backend queries, and the export and anonymization features need new backend endpoints.

For the settings screens, I'm building out the team management tab with role assignments and session controls, plus a secrets section for managing masked API credentials with reauthentication before updates, and Bitrix configuration for URL and field mapping—most of this requires new backend infrastructure for storing and managing these configurations.

The compliance section needs to handle Russian data protection requirements with legal-only UI access to configuration, backend stats processing, and RFC 8058 unsubscribe header handling. The profile section covers password changes that invalidate other sessions, TOTP-based 2FA setup, and active session termination, while the audit section needs filterable tables with export limits and three-year retention policies.

For shared components, most are frontend UI elements, though the optimistic-lock helper and PII masking utilities need backend support for assignments and role-based access. WebSocket functionality also requires backend implementation. The remaining gaps include GDPR subject export and anonymization in the backend, suppression logic to halt warm lead sequences with alerts, and pre-sync validation to check suppression status before Bitrix integration.

The suppression check already exists in the codebase — I just need to call it before pushing warm leads through BitrixSink, which is mostly UI or API-layer work. For provider reputation matching, the basic routing by provider pool is already implemented through the mailbox picker and provider pool gates, so that's partly existing. The additional layer of per-mailbox provider reputation tracking would be new backend work.

Warmup progression tracking has the infrastructure in place with WarmupState and warmup_report, but reverting warmup state isn't evident yet — that's new backend. Silent failure detection is straightforward since the event counting methods exist; I'd just need a convenience method. Manual intervention for provider blocks like SMTP 550 errors can partially reuse the existing failure marking and mailbox pausing logic, though I'd need to add a manual action state and checklist system. Now looking at pre-launch capacity planning around wave sizing versus mailbox limits. The reverse Bitrix webhook needs to sync deal closures back to the system, which is a gap that requires new build work. There's also a race condition around optimistic locking for assignments that needs handling. Now I'm tallying up which NEW-BACKEND methods appear most frequently across the different screens to identify the highest-priority implementations.

DNS health checks for domain validation show up across infrastructure, pre-flight, and domain management screens. Rate time-series analytics for sparklines and trend graphs appear in multiple places. Recipient query and count operations are needed for segmentation, lead filtering, and deduplication. Mailbox readiness checks are next on the list. Trip timestamps are also needed. For listing events, I need a method that filters by event type, campaign, provider, mailbox, with pagination and time range support—used across complaint modals, logs, and tables. Message thread retrieval pulls the conversation history between a recipient and campaign. Querying messages with filters handles the send logs and subject-level sends. Suppression lists are next on the list. ert + freeze** — retrieving warmup history, reverting changes, and freezing warmup state across screens for ramp history and rotation. **Domain report / list domains** — querying domain analytics and listing all domains used in campaigns. **Waves/canary state** — fetching wave configurations and canary status across multiple screens, though this might require building out the entire wave subsystem from scratch.

Recipient dedup by company/INN pulls contacts by tax ID and deduplicates them. Spam-check template scores message content for spam likelihood. Template compliance lint validates templates against compliance rules. IMAP mailbox health status monitors mailbox connectivity and health. Phone normalization converts phone numbers to E.164 format. Subject report with export and anonymization capabilities is next on the list.

Now looking at the most frequently used features across screens: pause reasons and active gate trips appear in about four screens, waves and canary state in four to five, DNS health in three to four, rate time-series in three to four, segment queries and counts in three to four, mailbox readiness composite in three to four, list events in three to four, suppression list management in three, capacity reporting in two to three, and warmup history with revert functionality in two to three. Rounding out the top-10 with Store.list_events, suppression list operations, Analytics.capacity_report, and Store.list_campaigns. Now I'm organizing this into per-screen tables while staying within the line limit, and I want to include a section highlighting what the engine already covers—cases where reviews flag gaps that don't actually exist. That's the real value of this fact-check approach. I'm thinking through the scope constraints—keeping this to 600 lines max, so the per-screen verdict tables will dominate. I need to be precise with each feature verdict and cite the exact engine methods. For the BUILD-NEW backlog estimates, I'm sizing out the major subsystems: authentication and user management as large, lead desk assignment and locking as large, audit logging as medium, the reverse Bitrix sync as medium, teams support as small, runtime configuration and secrets as medium, and OAuth mailbox management as medium.

Now I'm drafting the actual tables with clear verdict codes—UI-ONLY, NEW-BACKEND, BUILD-NEW, DROP—and I'll note upfront that every screen implicitly needs an HTTP endpoint so I don't repeat that per row. I'm also thinking through where the mockup contradicts itself, like the kill-switch threshold editing that's already been hardcoded and dropped. The WYSIWYG editor is a clear drop since the engine just handles text merging without HTML building. For drag-drop sequencing, that's also a drop—the steps are linear and the API already supports add_step and get_steps. Suppression deletion is more nuanced; the mockup restricts it, so removing items from suppression is a new backend method but it's gated. I'm also noting that suppression validation before Bitrix sync is just UI-only since is_suppressed already exists, and provider reputation matching is partly there through pick_mailbox and provider_pools but needs new backend work for reputation weighting.

Now checking engagement unlock on reply—the reply-based gating already works through has_reply and evaluate_gate, so that part exists, but actually re-activating a halted or cancelled sequence is new backend work since the engine doesn't support that kind of re-activation.

I'll organize this clearly: distinguishing between what's UI-only or already in the system versus what needs new backend implementation. Since this is a pure analysis piece without code changes needed, I'll write it densely and aim for around 450-550 lines, making sure the top-10 table includes method signatures, modules, affected screens, and the reasoning behind each item.# Фактчек-линза: макет судьи против реального API движка

Прогнал каждый экран против ground-truth API 18 модулей. Главный вывод сразу, чтобы задать рамку:

**Движок — это отправлятор + прогрев + репутация + комплаенс-примитивы.** В нём НЕТ: пользователей, сессий, ролей, 2FA, аудит-лога действий, и — критично — НЕТ лид-контура (назначение лида продажнику, «взять», статус позвонил/квал, SLA-возврат). Есть только детекция тёплого ответа (`has_reply` + `reply_classify` + `BitrixSink.push_warm_lead`) и выброс лида в Bitrix. Всё, что макет рисует вокруг 28 продажников — это **BUILD-NEW подсистема**, её в коде нет ни в каком виде.

Также нет HTTP/WebSocket-слоя — он подразумевается для КАЖДОГО экрана как общий BUILD-NEW (L), ниже не повторяю построчно.

---

## 0-bis. СТАТУС РЕАЛИЗАЦИИ (обновлено: Фаза 2.1b + 2.2b)

Вердикты ниже описывают, что НАДО было построить (актуальны как архитектурная карта).
Ниже — что УЖЕ построено и оживлено во фронте (`sender/web`, реестр `src/lib/screens.ts`).

**Построенные подсистемы (BUILD-NEW/NEW-BE → DONE):** HTTP-транспорт (FastAPI над движком,
`api/app.py`), auth (pbkdf2/TOTP/сессии/роли), лид-контур (assignment + CAS-take + статусы +
SLA), аудит-лог действий, кампании CRUD (create/detail/steps/status), users-менеджмент
(create/deactivate/activate + revoke sessions), домены+DNS-чек, прогрев (warmup state),
комплаенс+субъект ПД (consent_history/suppression lookup), settings (read-only конфиг+пороги),
смена пароля.

**Живых экранов: 21/23** — все, кроме `/sequences` и `/templates` (честный бэклог: отдельной
сущности «цепочка»/«шаблон» в движке нет — это шаги кампании, см. «Детали кампании»).
Живое проверено: 615 pytest + 11 vitest + 7 playwright e2e (флоу владельца и менеджера,
CAS-гонка за лид, создание кампании→шаг→запуск→аудит).

---

## 0. Легенда вердиктов

- **UI-ONLY** — метод/данные есть, обернуть в endpoint.
- **NEW-BE** — движку не хватает метода (даю сигнатуру + модуль).
- **BUILD-NEW** — новая подсистема (S/M/L).
- **DROP** — противоречит движку/данным или дубль.

---

## 1. ЛОЖНЫЕ ПРОБЕЛЫ — ревью «находит» то, что уже есть

Это ядро линзы. Ровно как было с bounce-gating/greylist/IDN — фичи из списка «дыр» уже реализованы:

| Заявленная «дыра» | Реальность | Вердикт |
|---|---|---|
| **#12 Проверка suppression перед Bitrix-sync** | `Suppression.is_suppressed(recipient)` есть. Вызвать ПЕРЕД `BitrixSink.push_warm_lead` — вопрос порядка вызовов, а не нового метода. | **UI-ONLY** |
| **#13 Провайдер-матчинг (Mail.ru → Mail.ru-ящик)** | `Sender.pick_mailbox` уже роутит по `Config.provider_pools()`, `Gates.check_recipient_provider(provider)` есть. Базовый матчинг работает. | **UI-ONLY** (репутация-взвешивание — NEW-BE, см. §7) |
| **#15 Тихая деградация (delivered/sent <95%)** | `count_events(event_type="delivered")` / `count_events(event_type="sent")` → отношение считается тривиально. Данные есть. | **UI-ONLY** (тонкий метод-обёртка опц.) |
| Классификация hot/интерес/автоответ | `reply_classify.classify_reply` + `classify_reply_ai` → `ReplySignal`, пишется через `append_event`. | **UI-ONLY** |
| Гейты цепочки (не открыл/не ответил) | `Cadence.evaluate_gate(step, recipient, campaign_id)`, `has_reply`. | **UI-ONLY** |
| Юр-футер ФЗ-38 | `Config.legal()` → `LegalCfg`, применяется в `Personalizer.render`. | **UI-ONLY** |
| Merge-поля шаблона | `Personalizer.available_fields(recipient)`. | **UI-ONLY** |
| List-Unsubscribe / RFC 8058 one-click | `Unsub.make_token`, `list_unsubscribe_headers`, `handle_one_click`. | **UI-ONLY** |
| Consent-лог / основание | `Store.log_consent(...)`, `consent_history(email)`. | **UI-ONLY** |
| Постофис Mail.ru | `PostofficeClient.report/domain_summary/spam_rate`, `reputation_alert`. | **UI-ONLY** |
| Пауза всех / СТОП | `Orchestrator.pause_all(reason)` / `resume_all()`. | **UI-ONLY** |
| Ротация ящика при manual action | `Sender.pick_mailbox` уже пропускает paused; `set_mailbox_paused` выводит ящик. | **UI-ONLY** (перераспределение квоты — NEW-BE) |
| Telegram-алерты | `Notifier.notify`, `digest`, `notify_gate_trips`. | **UI-ONLY** |

**Вывод для ревьюеров:** прежде чем писать «нет backend», грепай `count_events`, `Analytics.*`, `Gates.*`, `Suppression.*`, `Personalizer.*`, `Unsub.*`. Половина «дыр» — это порядок вызовов существующих методов.

---

## 2. Вердикты по экранам

### #1 Вход `/login`
| Фича | Вердикт | Якорь / нужный метод |
|---|---|---|
| email/пароль (argon2id) | **BUILD-NEW (L)** | нет `users`, нет auth |
| 2FA TOTP | **BUILD-NEW** | часть auth-подсистемы |
| доверенное устройство 30д | **BUILD-NEW** | sessions/fingerprint |
| редирект по роли | **BUILD-NEW** | нет ролей |
| 3 фейла → блок IP | **BUILD-NEW** | rate-limit auth |
| Telegram при блоке | **UI-ONLY** | `Notifier.notify` |

### #2 Дашборд `/`
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| Светофор = max(complaint,bounce,Постофис) | **UI-ONLY** | `Analytics.global_report` + `Postoffice.report` + `Gates.evaluate_all` |
| Сплит по провайдерам M/Я/др | **UI-ONLY** | `Analytics.rates(scope,target)`, `count_events(recipient_provider=…)` |
| Пороги complaint/bounce | **UI-ONLY** | `Config.gates()` → `GatesCfg` |
| Кнопка СТОП ВСЁ | **UI-ONLY** | `Orchestrator.pause_all(reason)` |
| Авто-разблок через 15 мин | **NEW-BE** | `Orchestrator.pause_all(reason, until: datetime)` в orchestrator.py |
| Прогресс кампаний + rates | **UI-ONLY** | `Analytics.campaign_report` |
| Лидов сегодня | **UI-ONLY** | `count_events(event_type="reply", since=midnight)` |
| ETA завершения | **NEW-BE** | `Analytics.campaign_eta(campaign_id) -> datetime` (analytics.py) |
| Светофор ёмкости (free limit vs волна) | **NEW-BE** | `Analytics.capacity_report(pool) -> CapacitySnapshot` (analytics.py) |
| «След. волна сейчас» | **NEW-BE** | `Orchestrator.force_wave(campaign_id)` (orchestrator.py) |
| Инфра: проблемные ящики/домены | **UI-ONLY** | `iter_mailbox_states` + `Gates.check_mailbox` (фильтр — UI) |
| DNS ✗ в инфре | **NEW-BE** | DNS-чек (см. §7 п.6) |
| Активность команды (5 audit) | **BUILD-NEW (M)** | нет audit-лога |
| Редирект П → `/leads` | **BUILD-NEW** | роли |

### #3 Кампании `/campaigns`
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| Список кампаний | **NEW-BE** | `Store.list_campaigns(*, status=None) -> list[Campaign]` (store.py) — есть только get/create |
| Статус | **UI-ONLY** | `Campaign.status` |
| Причина паузы (manual/kill/smtp/DNS) | **NEW-BE** | `Gates.active_trips() -> list[GateDecision]` (gates.py) — `trip()` пишет, чтения нет |
| Сегмент | **UI-ONLY** | `Campaign` поля |
| Прогресс / Тёплых | **UI-ONLY** | `Analytics.campaign_report` |
| Sparkline CR/BR 7д | **NEW-BE** | `Analytics.rate_series(*, scope, target, days) -> list[RateSnapshot]` (analytics.py) |
| Пауза/возобновить | **UI-ONLY** | `Store.set_campaign_status` |
| Дублировать | **NEW-BE** | `Store.clone_campaign(campaign_id) -> int` (store.py) |
| Tooltip «последняя пауза, кто» | **BUILD-NEW** | зависит от audit |

### #4 Конструктор `/campaigns/new`
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| Фильтры ОКВЭД/регион/размер/домен | **NEW-BE** | `Store.query_recipients(filters) -> Iterator[Recipient]` — `iter_recipients` умеет только valid_status/provider |
| Live-превью с count | **NEW-BE** | `Store.count_recipients(filters) -> dict` (store.py) |
| Вычет suppression из сегмента | **NEW-BE** | `Suppression.count_in_segment(recipient_ids) -> int` (suppression.py) |
| Библиотека цепочек + hot% | **NEW-BE** | `Store.list_sequences()` + `Analytics.campaign_report` (модель «цепочка» = шаги под campaign_id, см. §6) |
| Гейты/delays | **UI-ONLY** | `get_steps`, `Cadence.evaluate_gate` |
| Симулятор охвата воронки | **NEW-BE** | `Cadence.simulate_funnel(campaign_id) -> list[int]` (cadence.py) |
| Ящики «Готов к бою» | **NEW-BE** | `Sender.mailbox_readiness(mailbox_id) -> Readiness` (sender.py) — composite ramp+DNS+Постофис+manual |
| Провайдер-гейт в dropdown | **UI-ONLY**/NEW-BE | база: `provider_pools`+`check_recipient_provider`; матрица репутации — NEW-BE |
| DNS preflight ❌/⚠️ | **NEW-BE** | `DnsHealth.check(domain) -> DnsReport` (нов. модуль sender/dns.py) |
| Пороги kill-switch readonly | **UI-ONLY** | `Config.gates()` |
| Редактирование порогов | **DROP** | единогласно hardcoded; `Config.gates()` read-only by design |
| Канарейка config | **NEW-BE** | канареечной логики в API нет (см. §6 «волны») |
| Сохранить черновик | **UI-ONLY** | `create_campaign` + `set_campaign_status("draft")` |
| Запустить канарейку | **NEW-BE** | `Orchestrator.launch_canary(campaign_id, size)` (orchestrator.py) |

### #5 Детали кампании `/campaigns/:id`
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| Пауза/Возобновить/Убить | **UI-ONLY** | `set_campaign_status` |
| Alert-баннер причины автопаузы | **NEW-BE** | `Gates.active_trips()` |
| «Снизить лимиты и возобновить» | **NEW-BE** | `Store.set_mailbox_limit_override(mailbox_id, limit, reason)` (store.py) |
| Kill-switch прогресс-бары ± провайдер | **UI-ONLY** | `Gates.evaluate_all` + `Config.gates()` + `Analytics.rates` |
| Модалка 20 последних complaint (кто) | **NEW-BE** | `Store.list_events(*, event_type, campaign_id, recipient_provider, limit) -> list[Event]` (store.py) |
| «Заблокировать Mail.ru для кампании» | **UI-ONLY** | `Gates.trip(scope, target, reason)` |
| «→ suppression» | **UI-ONLY** | `Suppression.add_email` |
| Воронка (delivered→reply→warm) | **UI-ONLY** | `Analytics.campaign_report` + `count_events` |
| Этапы квал/закрыто | **BUILD-NEW** | лид-контур (нет в движке) |
| Каскад по шагам / провайдеру / домену | **UI-ONLY** | `count_events(sequence_step_id / recipient_provider / domain)` |
| Клик этапа → `/leads?...` | **UI-ONLY** | роутинг |
| Волны timeline + «форсировать» | **NEW-BE** | волны/канарейка (см. §6) + `Orchestrator.force_wave` |
| Confidence-бейдж N<100 | **UI-ONLY** | из `count_events` |
| Мини-схема: сколько отсеялось на гейте | **NEW-BE** | `Cadence.simulate_funnel` |

### #6 Лента лидов `/leads` — эпицентр BUILD-NEW
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| **Взять** с оптимистичной блокировкой | **BUILD-NEW (L)** | нет `lead_assignments`, нет `UPDATE WHERE assigned IS NULL` |
| Гашение строки у всех (WebSocket/poll) | **BUILD-NEW** | realtime-канал |
| Фильтр статус лида | **BUILD-NEW** | workflow статусов нет |
| Фильтр приоритет hot/интерес | **NEW-BE** | `Store.list_leads(*, classification, campaign_id, since)` поверх events |
| Фильтр дата/кампания | **UI-ONLY** | `count_events`/query |
| Фильтр волна | **NEW-BE** | волны (см. §6) |
| Поиск ИНН/название | **NEW-BE** | `Store.query_recipients(filters)` |
| Фильтр «моя команда» | **BUILD-NEW (S)** | teams (P3) |
| Компания/ИНН | **UI-ONLY** | `Recipient` |
| Контакт маскирован до «Взять» | **BUILD-NEW** | roles + assignment + PII-mask |
| Цитата потребности | **NEW-BE** | snippet хранится при `push_warm_lead`, чтения нет → lead-store |
| Время без движения (SLA-цвет) | **BUILD-NEW** | assignment timestamps |
| Взял (кто) | **BUILD-NEW** | assignment |
| Статус Bitrix | **NEW-BE** | `BitrixClient.call("crm.lead.get",…)` обёртка или reverse-sync |
| Bulk →квал/не-квал/CSV | **BUILD-NEW** | status + audit |
| Live push «+2 новых» | **BUILD-NEW** | in-app WS (Notifier — только Telegram) |
| Флаг «ОТПИСАЛСЯ — не звонить» | **NEW-BE** | `is_suppressed` есть; связка suppression↔assignment — BUILD-NEW |

### #7 Карточка лида `/leads/:id`
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| Компания/ИНН/контакт | **UI-ONLY** | `get_recipient` |
| [Позвонить] tel: | **UI-ONLY** | фронт |
| Нормализация → E.164 | **NEW-BE** | `normalize_phone(text) -> str` (reply_classify.py) — есть только `extract_phone` |
| [→ Bitrix] | **UI-ONLY** | `BitrixSink.push_warm_lead` + `card_url` |
| История переписки (тред) | **NEW-BE** | `Store.get_thread(recipient_id, campaign_id) -> list` (store.py) — есть только `get_message`/`find_message_by_rfc_id` |
| «Что мы писали» | **UI-ONLY** | `get_message` + `get_steps` |
| «Предыдущие кампании» по ИНН | **NEW-BE** | `Store.recipient_history_by_inn(inn) -> list` (store.py) |
| Дедуп «2 контакта» | **NEW-BE** | `Store.recipients_by_company(inn) -> list[Recipient]` |
| [Позвонил]/[Квалифицировать]/[Не квал] | **BUILD-NEW** | lead-статусы |
| Предзаполнение формы из письма | **NEW-BE** | `reply_classify` даёт сигнал; структурный extract — `classify_reply` расширить |
| Проверка suppression при квал | **UI-ONLY** | `is_suppressed` |
| Запись основания в consent_log | **UI-ONLY** | `Store.log_consent` |
| [Переклассифицировать] + аудит | **NEW-BE** | `Store.append_event(EventIn(manual override))` + audit-хук |
| «Источник контакта» | **UI-ONLY** | `consent_history` + `Recipient` |
| Стоп цепочки при квал/отказе | **NEW-BE** | `Cadence.cancel_recipient(recipient_id, campaign_id) -> int` (cadence.py) — есть `mark_skipped` по одному msg |

### #8 `/my-leads` · #9 `/stats`
| Фича | Вердикт | Якорь |
|---|---|---|
| My-leads: таблица по себе, таймер «взят 1:47» | **BUILD-NEW** | assignment |
| SLA-возврат 2ч → в пул + push | **BUILD-NEW** | assignment + фоновый job |
| Stats: воронка Взял→Квал→Bitrix | **BUILD-NEW** | lead-метрики |
| Source по домену-отправителю | **UI-ONLY** | `count_events(domain=…)` (но привязка к исходу — BUILD-NEW) |

### #10–13 Цепочки / шаблоны / превью
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| `/sequences` список + Open%/hot/complaint | **NEW-BE** | `Store.list_sequences()` — цепочки не first-class, привязаны к campaign_id |
| Клонировать цепочку | **NEW-BE** | `Store.clone_sequence(campaign_id)` |
| «Активные кампании» (блок удаления) | **NEW-BE** | `Store.sequence_usage(seq_id)` |
| Список шагов письмо/задержка/гейт | **UI-ONLY** | `get_steps` |
| CRUD шагов (правка/удаление/reorder) | **NEW-BE** | `Store.update_step`, `delete_step`, `reorder_steps` — есть только `add_step` |
| Гейты (не открыл/не ответил/не тёплый) | **UI-ONLY** | `Cadence.evaluate_gate` |
| 🔓 Разблокировать цепочку при ответе | **NEW-BE** | `Cadence.reactivate_recipient(recipient_id, campaign_id)` (cadence.py) — дыра p5 |
| Окно 9–18 по TZ получателя | **NEW-BE** | база `sending_window`/`holidays` есть; per-recipient TZ из региона — `Cadence.schedule_time` расширить TZ |
| Timeline волн, правка только неотправленных | **NEW-BE** | версионирование + волны (см. §6) |
| Drag-drop canvas | **DROP** | линейные шаги; `add_step`/`get_steps` линейны, ветвлений нет |
| Textarea + merge | **UI-ONLY** | `Personalizer.available_fields`/`render` |
| WYSIWYG-редактор | **DROP** | `Personalizer` рендерит текст+merge, HTML-билдера нет; plain-text консенсус |
| Автофутер ФЗ-38 | **UI-ONLY** | `Config.legal()` |
| Спам-проверка (CAPS/слова/!!!) | **NEW-BE** | `spamcheck.score(text) -> SpamReport` (нов. модуль sender/spamcheck.py) |
| Комплаенс-гейт (List-Unsub/атрибуция) | **NEW-BE** | база `Unsub`/`PersonalizationGateError`; линт шаблона — `Personalizer.compliance_check(step) -> list[str]` |
| Версионирование + аудит | **BUILD-NEW (M)** | нет версий шаблонов + audit |
| Превью на реальном ИНН | **NEW-BE** | `query_recipients` + `Personalizer.preview` (preview есть, поиск — нет) |
| Симулятор гейтов | **UI-ONLY** | `Cadence.evaluate_gate` |
| Чек suppression получателя | **UI-ONLY** | `is_suppressed` |
| Тест-отправка себе | **NEW-BE** | `Sender.send_test(step, recipient, mailbox_id)` (sender.py) — `send` есть, тест-обёртки нет |

### #14–16 Домены / ящики / прогрев
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| `/domains` плитки/список | **NEW-BE** | `Store.list_domains()` / `Analytics.domain_report(domain)` — домен не entity |
| Репутация домена | **UI-ONLY** | `Analytics.rates(scope="domain")` |
| Постофис Mail.ru | **UI-ONLY** | `Postoffice.domain_summary/report` |
| Провайдер-сплит | **UI-ONLY** | `count_events(domain, recipient_provider)` |
| DKIM/SPF/DMARC ✓/⚠/✗ + «Проверить DNS» | **NEW-BE** | `DnsHealth.check(domain)` (нов. модуль) |
| `/mailboxes` список | **UI-ONLY** | `iter_mailbox_states` + `Config.mailboxes` |
| «Готов к бою» composite | **NEW-BE** | `Sender.mailbox_readiness` |
| лимит/отправлено | **UI-ONLY** | `MailboxState` |
| IMAP-статус | **NEW-BE** | `ImapWatcher.health(mailbox_id) -> dict` (imap_watcher.py) |
| Провайдер-матрица (ящик×провайдер) | **NEW-BE** | `Analytics.provider_matrix() -> dict` (analytics.py) |
| Пауза ящика | **UI-ONLY** | `set_mailbox_paused` |
| Форс волны | **NEW-BE** | `Orchestrator.force_wave` |
| Override лимита + аудит | **NEW-BE** | `Store.set_mailbox_limit_override` + audit |
| Переподключить OAuth (front: status/last4) | **NEW-BE / BUILD-NEW (M)** | OAuth-менеджмент ящиков отсутствует |
| Ramp-история день/доза/факт/решение | **NEW-BE** | `Analytics.warmup_history(mailbox_id) -> list` — есть `warmup_report` (снапшот) |
| Откат рампа | **NEW-BE** | `Warmup.revert(mailbox_id, to_step)` (warmup.py) — дыра p6 |
| Заморозить рамп + аудит | **NEW-BE** | `Warmup.freeze(mailbox_id)` (warmup.py) |
| Календарь готовности | **NEW-BE** | `Warmup.readiness_calendar()` (агрегат `daily_target`) |
| Wizard добавления ящика (CSV creds) | **NEW-BE / BUILD-NEW (M)** | провижининг ящика в рантайме — Config файловый |

### #17 Монитор репутации `/reputation`
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| Kill-switch плитки realtime | **UI-ONLY** | `Gates.evaluate_all` |
| Timestamp срабатывания | **NEW-BE** | `Gates.active_trips()` (ts/scope/reason) |
| График 7д vs пороги + маркеры рампа | **NEW-BE** | `Analytics.rate_series` |
| **Алерт «тихая деградация»** | **UI-ONLY** | `count_events(delivered)`/`count_events(sent)` → ratio; алерт через `Notifier` (см. §1 #15) |
| Ротация при manual action (SMTP 550) | **UI-ONLY** | `mark_failed(retryable=False)` + `set_mailbox_paused` + `pick_mailbox` пропускает paused |
| Перераспределение квоты | **NEW-BE** | `Analytics.capacity_report` + логика в Orchestrator |
| Чеклист ручного разбора | **BUILD-NEW (S)** | UI-only чеклист |
| Тренды провайдеров | **UI-ONLY** | `Analytics.rates` (+ series NEW-BE) |
| Suppression-счётчики | **NEW-BE** | `Suppression.stats() -> dict` (suppression.py) |

### #18 Логи `/logs`
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| Вкладка «Отправка»: список писем | **NEW-BE** | `Store.list_messages(filters) -> list[Message]` — есть только `get_message` |
| Фильтры | **NEW-BE** | параметры `list_messages` |
| bounce reason / FBL | **UI-ONLY** | `Message`/`Event` поля |
| Экспорт CSV + аудит | **NEW-BE** | из `list_messages` + audit |
| `/logs/email/:id` цепочка | **NEW-BE** | `Store.get_thread` |
| SMTP-метаданные | **UI-ONLY** | `get_message` |
| «Добавить в suppression» | **UI-ONLY** | `Suppression.add_email` |
| Вкладка «Аудит действий» | **BUILD-NEW (M)** | нет audit-лога |

### #19 Suppression `/suppression`
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| Список email/домен/ИНН | **NEW-BE** | `Store.iter_suppression(*, scope, limit) -> Iterator[SuppressionEntry]` — есть только `suppression_lookup` (по ключу) |
| Источник записи | **UI-ONLY** | `SuppressionEntry.reason/source` |
| Ручное добавление (аудит) | **UI-ONLY** | `Suppression.add_email/add_domain/add_inn` + audit |
| Импорт конкурентов | **UI-ONLY** | `Suppression.import_competitors/import_file/import_glob` |
| Ручное удаление (О, причина) | **NEW-BE** | `Store.suppression_remove(entry_id, reason)` (store.py) + audit |
| Полный CRUD без ограничений | **DROP** | риск разбанить жалобщика; макет верно ограничивает до view+audited-add |
| Связка «тёплый отписался» → флаг+Telegram | **NEW-BE** | join suppression↔assignment (BUILD-NEW) + `Notifier.notify` |

### #20 Комплаенс `/compliance` + `/subject/:email`
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| Suppression по причинам | **NEW-BE** | `Suppression.stats()` |
| Отписки 7д тренд | **NEW-BE** | `Analytics.rate_series(event="unsubscribe")` |
| Адресов без consent (красный) | **NEW-BE** | `Store.recipients_without_consent() -> int` (store.py) |
| Кампании с превышением complaint | **UI-ONLY** | `Analytics` + `Gates.active_trips` |
| Таблицы отписок/жалоб (маска) | **NEW-BE** | `Store.list_events` + PII-mask (UI) |
| `/subject`: consent-история | **UI-ONLY** | `consent_history(email)` |
| `/subject`: отправки/ответы по email | **NEW-BE** | `Store.subject_report(email) -> dict` (store.py) |
| Suppression-статус | **UI-ONLY** | `suppression_lookup` |
| Факт передачи в Bitrix | **NEW-BE** | нет записи lead_id↔email; `Store.subject_report` включить |
| **Экспорт для РКН (CSV/PDF)** | **NEW-BE** | `Store.subject_report` → сериализация; дыра p8 #10 |
| **Обезличить (право на забвение)** | **NEW-BE** | `Store.anonymize_subject(email) -> int` (store.py); дыра p8 #10 |
| Аудит просмотра/экспорта | **BUILD-NEW** | audit |

### #21 Настройки · #22 Профиль · #23 Аудит
| Фича | Вердикт | Якорь / метод |
|---|---|---|
| Таб Команда (28 П, роли/статус) | **BUILD-NEW (L)** | users |
| Деактивация → рвёт сессии + переназначение лидов | **BUILD-NEW** | auth + assignment; дыра офбординга p8 |
| Таб Секреты (Bitrix/Telegram, last4) | **NEW-BE / BUILD-NEW (M)** | Config файловый read-only; рантайм-запись секретов отсутствует |
| Таб Bitrix (URL/маппинг) | **NEW-BE** | `Config` только `load`/`get`, записи нет → `Store.set_config(key, value)` |
| Таб Telegram (chat_id) | **NEW-BE** | то же |
| Таб Compliance (ФЗ-38 реквизиты) | **UI-ONLY** (чтение) | `Config.legal()` |
| ФЗ-152 статистика | **NEW-BE** | `Suppression.stats()` + `Analytics` |
| RFC 8058 endpoint | **UI-ONLY** | `Unsub.handle_one_click` |
| Profile: смена пароля/2FA/сессии | **BUILD-NEW** | auth |
| Audit: таблица + экспорт + retention 3г | **BUILD-NEW (M)** | audit-лог |

---

## 3. Общие компоненты

| Компонент | Вердикт | Примечание |
|---|---|---|
| DataTable (TanStack, вирт.скролл) | **UI-ONLY** | фронт |
| FilterBar + live-count | **UI-ONLY** | (count зависит от NEW-BE `count_recipients`/`list_*`) |
| AlertBar / Светофор | **UI-ONLY** | `Analytics`+`Gates`+`Postoffice` |
| Status-бейджи | **UI-ONLY** | из DTO |
| Прогресс-бары с порогами | **UI-ONLY** | `Config.gates()` |
| Модалка переписки | **NEW-BE** | `Store.get_thread` |
| Confirm-диалог + причина | **UI-ONLY** | фронт |
| **Optimistic-lock хелпер** | **BUILD-NEW** | ядро lead-desk |
| PII-mask по роли | **UI-ONLY** + **BUILD-NEW** (roles) | утилита фронт + роли на бэке |
| Empty states | **UI-ONLY** | фронт |
| **WebSocket-канал** | **BUILD-NEW (L)** | realtime лент |

---

## 4. DROP-решения (подтверждаю выбор судьи)

| Что | Почему DROP |
|---|---|
| Редактирование порогов kill-switch в UI | `Config.gates()` read-only by design; риск сжечь домены. Верно оставлено в конфиге. |
| Отдельный `/analytics` дашборд | Дубль `Analytics.dashboard`, уже кормит `/` и `/reputation`. |
| A/B `/variants` (для 2.1) | A/B-логики в движке НЕТ (была бы BUILD-NEW L); сегменты малы. Канарейка ≠ A/B. Отложить. |
| WYSIWYG-редактор | `Personalizer` рендерит текст+merge, HTML-билдера нет; plain-text лучше проходит. |
| Drag-drop canvas цепочек | `add_step`/`get_steps` линейны; ветвлений в модели нет. |
| Полный CRUD suppression без гейтов | Разбан жалобщика = бан домена; view+audited-add корректнее. |

---

## 5. BUILD-NEW подсистемы (не метод, а слой)

| Подсистема | Оценка | Экраны | Комментарий |
|---|---|---|---|
| HTTP/API + WebSocket слой | **L** | все | движок — библиотека, transport-слоя нет |
| Auth (users/sessions/roles/2FA) | **L** | 1,2,6,7,8,21,22 | нулевая база |
| Lead-desk (assignment/lock/status/SLA) | **L** | 6,7,8,20 | главная дыра p1·p2·p7; `push_warm_lead` только выбрасывает в Bitrix |
| Audit-лог действий | **M** | 2,3,5,18,20,23 | `consent_log`/`events` не покрывают actor/action |
| Reverse Bitrix-sync (webhook закрытия) | **M** | 6,8 | `BitrixClient.call` есть, приёмника вебхука нет; дыра p2 |
| Runtime-config/secrets запись | **M** | 21 | `Config` только читает |
| Teams (`team_id`) | **S** | 6,8 | P3, схему заложить сразу |

---

## 6. Спец-предупреждение: волны/канарейка

Макет опирается на «волны» и «канарейку» как на данность (форс волны, timeline, канарейка 50, фильтр по волне). **В API их НЕТ:** нет `campaign_waves`, нет метода чтения статуса канарейки, нет `force_wave`. `Cadence.plan_campaign` планирует сообщения, `Orchestrator.tick` их шлёт — но батч-волны и канареечный гейт не выделены как сущность. Это либо крупный **NEW-BE** блок методов, либо **BUILD-NEW (M)** мини-подсистема. Затрагивает экраны 2,3,4,5,6 — поэтому вынес отдельно, не растворяя в top-10.

---

## 7. ТОП-10 NEW-BACKEND — бэклог API Фазы 2.1

Отсортировано по числу экранов-потребителей. Это фактический бэклог движка (без BUILD-NEW-подсистем из §5–6, они отдельным треком).

| # | Метод (сигнатура) | Модуль | Экраны | Зачем |
|---|---|---|---|---|
| 1 | `Gates.active_trips() -> list[GateDecision]` (ts/scope/target/reason) | gates.py | 2,3,5,17 | причина паузы, alert-баннер, timestamp срабатывания — сейчас `trip()` только пишет |
| 2 | `Analytics.rate_series(*, scope, target, days, bucket) -> list[RateSnapshot]` | analytics.py | 3,5,9,17,20 | sparkline CR/BR, график 7д, тренды отписок |
| 3 | `Store.query_recipients(filters)` + `Store.count_recipients(filters) -> dict` | store.py | 4,6,7,13 | сегмент-фильтры, live-превью, поиск ИНН, дедуп |
| 4 | `Sender.mailbox_readiness(mailbox_id) -> Readiness` (composite ramp+DNS+Постофис+manual) | sender.py | 2,4,14,16 | флаг «Готов к бою» + dropdown-гейт конструктора |
| 5 | `Store.list_events(*, event_type, campaign_id, provider, mailbox_id, limit, since) -> list[Event]` | store.py | 5,6,18,20 | модалка complaint, логи, таблицы отписок/жалоб |
| 6 | `DnsHealth.check(domain) -> DnsReport` (DKIM/SPF/DMARC) | нов. sender/dns.py | 2,4,14 | preflight, слепая зона протухших ключей (тихий спам) |
| 7 | `Store.list_campaigns(*, status=None) -> list[Campaign]` | store.py | 3,4,5 | таблица кампаний, библиотека цепочек — есть только get/create |
| 8 | `Analytics.capacity_report(pool) -> CapacitySnapshot` | analytics.py | 2,4,17 | светофор ёмкости, симулятор волны, перераспределение квоты (дыра p6 #17) |
| 9 | `Suppression.stats() -> dict` + `Store.iter_suppression(*, scope, limit)` + `Store.suppression_remove(id, reason)` | suppression.py / store.py | 17,19,20 | счётчики, список, аудируемое удаление — есть только `suppression_lookup` |
| 10 | `Store.get_thread(recipient_id, campaign_id) -> list` | store.py | 7,18 | история переписки, цепочка касаний в логах |

**Почётные упоминания (следующие по частоте):** `Cadence.cancel_recipient` + `reactivate_recipient` (стоп/разблок цепочки, дыра p5 — экраны 7,11); `Store.list_messages(filters)` (логи — 18,20); `Warmup.revert`/`freeze` + `Analytics.warmup_history` (откат рампа, дыра p6 — 16,17); `Store.subject_report` + `anonymize_subject` (право на забвение, дыра p8 — 20).

---

**Итог линзы:** из ~150 фич макета значимая доля — **UI-ONLY** (движок богаче, чем кажется ревью: `Analytics`, `Gates`, `count_events`, `Suppression`, `Personalizer`, `Unsub` закрывают репутацию/комплаенс/персонализацию целиком). Реальный дефицит API — 10 методов из top-10 плюс волны/канарейка. А главный объём работ Фазы 2.1 — это не движок, а **три BUILD-NEW слоя**: HTTP/WS transport, auth и lead-desk. Три «дыры» из списка судьи (#12 suppression-check, #13 провайдер-матчинг, #15 тихая деградация) — ложные: логика уже в коде, нужен лишь правильный порядок вызовов.

---

# ЧАСТЬ 3. РЕАЛИЗАЦИЯ ФРОНТА (Фаза 2.2) — зафиксированный стек + карта экран↔эндпоинт

**Стек (зафиксирован 2026-07-19):** React 18 + Vite + TypeScript + React Router 6 +
TanStack Query 5. Обоснование: TanStack уже назван в §3 (DataTable); node 22 в
окружении; типобезопасный клиент против реального API; сборка в статику (dist/),
раздаётся nginx или FastAPI, `/api` на обратном прокси. Код — `sender/web/`.
Тесты: Vitest (юнит/клиент) + Playwright (e2e против реального `serve-api`).

**Принцип: каждый экран — к РЕАЛЬНОМУ эндпоинту `sender/api/app.py`.** Экраны
макета, чей бэкенд ещё не построен, включены в маршрутизацию как честные
заглушки (`BacklogStub`) — они НЕ имитируют данные, а называют недостающий
эндпоинт. Так навигация полная, но ничего не фейкается.

## Карта: 23 экрана SITE-DESIGN → статус реализации

| # | Экран | Статус | Реальный эндпоинт |
|---|-------|--------|-------------------|
| 1 | Вход | ✅ live | POST /auth/login, GET /me |
| 2 | Дашборд | ✅ live | /analytics/dashboard, /gates/active, /capacity, /mailboxes/readiness |
| 3 | Кампании (список) | ✅ live | GET /campaigns |
| 6 | Лента лидов (эпицентр) | ✅ live | GET /leads, POST /leads/:id/take |
| 7 | Карточка лида | ✅ live | GET /leads/:id, POST take/status |
| 8 | Мои лиды | ✅ live | GET /leads?assigned_to=me |
| 9 | Моя статистика | ✅ live | GET /leads (агрегация на клиенте) |
| 15 | Ящики (готовность) | ✅ live | GET /mailboxes/readiness |
| — | Ёмкость пулов | ✅ live | GET /capacity |
| 17 | Монитор репутации | ✅ live | /gates/active, /analytics/rates |
| 18 | Логи событий | ✅ live | GET /events |
| 19 | Suppression | ✅ live | GET /suppression, DELETE /suppression/:id |
| 22 | Профиль | ✅ live (частично) | GET /me (смена пароля/2FA — бэклог) |
| 4 | Конструктор кампании | 🔲 backlog | POST /campaigns, POST /:id/steps — не построены |
| 5 | Детали кампании (+воронка) | 🔲 backlog | GET /campaigns/:id — не построен |
| 10 | Цепочки | 🔲 backlog | GET /sequences — не построен |
| 12 | Шаблоны | 🔲 backlog | GET /templates — не построен |
| 14 | Домены (DNS) | 🔲 backlog | GET /domains/:d (dns.py есть, роут — нет) |
| 16 | Прогрев | 🔲 backlog | GET /warmup — не построен |
| 20 | Комплаенс (+субъект ПД) | 🔲 backlog | GET /compliance, /subject/:email — не построены |
| 21 | Настройки | 🔲 backlog | GET/POST /users, /settings — не построены |
| 23 | Аудит действий | 🔲 backlog | GET /audit (audit_log в БД есть, роут — нет) |

**Бэклог Фазы 2.1b (эндпоинты под оставшиеся экраны):** POST/PUT кампаний и
шагов; GET /campaigns/:id с воронкой; /sequences + /templates CRUD; /domains +
DnsHealth-роут (модуль `dns.py` готов); /warmup; /compliance + /subject/:email
(экспорт ПД для РКН); /users + /settings + POST /profile (пароль/2FA/сессии);
GET /audit. После них соответствующие заглушки заменяются живыми экранами без
изменения фронт-архитектуры.

**НЕ реализовано намеренно (DROP из §4):** WYSIWYG-редактор, drag-drop canvas
цепочек, правка порогов kill-switch в UI. WebSocket-лента заменена поллингом
(refetchInterval 15с у ленты лидов) — тот же UX гашения взятых, без WS-слоя.

**Запуск фронта:**
```
cd sender/web && npm install
npm run dev        # Vite :5173, /api → serve-api :8080 (переменная SENDER_API_URL)
npm run build      # статика в dist/
npm test           # Vitest (11)
npm run e2e        # Playwright против засеянного serve-api (4)
```
