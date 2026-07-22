# DNS доменов рассылки — проверка и что доделать

Проверено DoH-запросами (реальный DNS). Дата: 2026-07-22. ⛔ Всё это pre-warmup —
на холд не влияет, но **без этого рассылку не запускать** (DKIM/DMARC/SPF = доставляемость).

## Итог проверки (11 доменов; nic.ru-домены — отдельно, там DNS ещё не ведётся)

| Домен | Пров | MX | SPF | DKIM | DMARC | A(редирект) |
|---|---|---|---|---|---|---|
| kompressor-air-trade.ru | Я360 | ✓ | ✗ beget | ✗ | ✗ | ✓ |
| kompressor-pro-expert.ru | Я360 | ✓ | ✗ beget | ✗ | ✗ | ✓ |
| compressor-air-expert.ru | Я360 | ✗ reg.ru | ✗ reg.ru | ✗ | ✗ | ✓ |
| optic-sort.ru | Я360 | ✗ reg.ru | ✗ reg.ru | ✗ | ✗ | ✓ |
| zernosort.ru | Я360 | ✗ нет | ✗ нет | ✗ | ✗ | ✗ нет |
| kompressor-pro-trade.ru | Я360 | ✓ | ✗ timeweb | ✗ | ✗ | ✓ |
| sort-systems.ru | Я360 | ✓ | ✗ нет | ✗ | ✗ | ✓ |
| kompressor-air-expert.ru | VK | ✓ | ✓ | ✗ | ✗ | ✓ |
| sort-inspection.ru | VK | ✓ | ✗ beget | ✗ | ✗ | ✓ |
| kompressor-expert.ru | VK | ✓ | ✓ | ✗ | ✗ | ✗ нет |
| compressor-store.ru | VK | ✓ | ✓ | ✗ | ✗ | ✓ |

**Ключевые пробелы:**
- **DKIM — нет НИГДЕ (0/11).** Критично. Ключ генерится в кабинете (Я360/VK) → добавить выданный TXT.
- **DMARC — нет НИГДЕ (0/11).** Добавить `_dmarc` TXT везде.
- **SPF неправильный (хостинга) на 6**: beget / reg.ru / timeweb вместо провайдера почты.
- **MX ещё на хостинге reg.ru у 2**: compressor-air-expert, optic-sort → сменить на mx.yandex.net.
- **A-записи нет у 2** (zernosort, kompressor-expert) → 301-редирект не работает.
- **zernosort.ru — пусто вообще** (ни MX, ни SPF, ни A) → настроить с нуля.

## Что и где добавлять (не-nic.ru домены)

Ты УЖЕ ведёшь зону в панели хостинга (beget/reg.ru/timeweb — оттуда SPF в проверке).
Значит НЕ надо ничего делегировать — **добавь недостающие записи в той же панели**, A-запись
(редирект) оставь как есть. По каждому домену привести к его провайдеру:

**Я360-домены:**
- MX: `10 mx.yandex.net.`
- SPF (TXT @, заменить хостинговый): `v=spf1 redirect=_spf.yandex.net`
- DKIM (TXT): взять ТОЧНОЕ значение из `admin.yandex.ru` → домен → DKIM (селектор `mail._domainkey`).
- DMARC (TXT `_dmarc`): `v=DMARC1; p=quarantine; rua=mailto:postmaster@ДОМЕН`

**VK-домены** (biz.mail.ru / VK WorkSpace):
- MX: `10 emx.mail.ru.`
- SPF (TXT @): `v=spf1 redirect=_spf.mail.ru`
- DKIM (TXT): из кабинета VK WorkSpace → домен → DKIM (селектор обычно `mailru._domainkey`).
- DMARC (TXT `_dmarc`): `v=DMARC1; p=quarantine; rua=mailto:postmaster@ДОМЕН`

**A-запись (редирект)** — где нет (zernosort, kompressor-expert): добавить A на IP того веб-хоста,
что отдаёт 301 на целевой сайт (как на уже рабочих доменах). Без A редирект не открывается.

## nic.ru-домены — как добавить DNS

В nic.ru «нету панели» потому, что для редактирования зоны нужна услуга **DNS-хостинг
(DNS-master)** — она бесплатна для доменов, зарегистрированных в nic.ru, но её надо ВКЛЮЧИТЬ.
Два пути:

**Путь A (проще) — делегировать NS туда, где панель уже есть.**
В карточке домена nic.ru → раздел «DNS-серверы» → указать nameservers провайдера/хостинга,
где будешь вести зону (напр. NS beget/timeweb/reg.ru, где у тебя уже панель). Дальше DNS
ведёшь в привычной панели. Смена NS доступна БЕЗ активации DNS-хостинга.

**Путь B — вести зону в самом nic.ru.**
1. Личный кабинет nic.ru → «Услуги» (или карточка домена) → подключить бесплатный
   **«DNS-хостинг»** для домена.
2. Поставить nameservers nic.ru: `ns4-l2.nic.ru`, `ns8-l2.nic.ru` (DNS-master).
3. После активации в карточке домена появится **«Управление зоной»** — там добавляешь
   A / MX / TXT (значения — из таблицы выше по провайдеру домена).

nic.ru-домены по плану (6): compressor-pro-systems, compressor-pro-trade, kompressor-air-systems
(Я360-КЦ); compressor-air-trade, kompressor-trade (VK-КЦ); rentgen-detektor (VK-Meyer→**meyer-corp.ru**).

## Порядок (рекомендация)
1. Сначала A-записи где их нет (редирект должен работать).
2. MX → провайдер почты.
3. SPF → провайдер (заменить хостинговый).
4. DKIM → включить в кабинете Я360/VK, добавить выданный TXT.
5. DMARC → `p=quarantine` (на старте), позже `p=reject`.
6. Перепроверить (могу прогнать DoH-скан ещё раз).
