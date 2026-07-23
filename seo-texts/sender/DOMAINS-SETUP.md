# Домены-двойники рассылки — реестр и состояние подготовки

Домены КУПЛЕНЫ владельцем (июль 2026). Реестр (машиночитаемый) —
`config/domains.json`; проверка DNS+редиректов — `python3 sender/tools/check_domains.py`
(DoH, работает и из песочницы за прокси, и с боевого сервера).
Старый план закупки с другими именами устарел и заменён этим файлом.

## Реестр: 14 доменов

| Домен | Регистратор | Хост ящиков | Напр. | Редирект на |
|---|---|---|---|---|
| compressor-pro-systems.ru | RU-CENTER | Яндекс 360 | КЦ | prokompressor.ru |
| kompressor-trade.ru | RU-CENTER | VK WorkSpace | КЦ | prokompressor.ru |
| rentgen-detektor.ru | RU-CENTER | VK WorkSpace | Meyer | meyer-corp.ru |
| kompressor-air-trade.ru | Beget | Яндекс 360 | КЦ | prokompressor.ru |
| kompressor-pro-expert.ru | Beget | Яндекс 360 | КЦ | prokompressor.ru |
| kompressor-air-expert.ru | Beget | VK WorkSpace | КЦ | prokompressor.ru |
| sort-inspection.ru | Beget | VK WorkSpace | Meyer | vsefotoseparatory.ru |
| compressor-air-expert.ru | REG.RU | Яндекс 360 | КЦ | prokompressor.ru |
| optic-sort.ru | REG.RU | Яндекс 360 | Meyer | vsefotoseparatory.ru |
| zernosort.ru | REG.RU | Яндекс 360 | Meyer | vsefotoseparatory.ru |
| kompressor-expert.ru | REG.RU | VK WorkSpace | КЦ | prokompressor.ru |
| kompressor-pro-trade.ru | Timeweb | Яндекс 360 | КЦ | prokompressor.ru |
| sort-systems.ru | Timeweb | Яндекс 360 | Meyer | vsefotoseparatory.ru |
| compressor-store.ru | Timeweb | VK WorkSpace | КЦ | prokompressor.ru |

Сплит: 8 Я360 + 6 VK; 10 КЦ + 4 Meyer. Провайдер-сплит пулов (яндекс-домены →
яндекс-получатели, vk-домены → mail.ru) — уже заложен в сендере.

## Проверка 2026-07-23 (итог: 0/14 полностью готовы)

Почтовый DNS (MX/SPF/DKIM/verification) **сделан на 11 из 14** — Beget, REG.RU,
Timeweb в порядке. Дырки:

1. **RU-CENTER — все 3 домена ПУСТЫЕ** (только NS). Не добавлены даже в панели
   почты: нет verification-TXT, MX, SPF, DKIM. Настроить с нуля (шаблоны ниже).
2. **DMARC нет на 13 из 14** (есть только у compressor-store.ru).
3. **Редиректы на основные сайты не работают НИГДЕ (0/14)**:
   - Beget (4): отвечает заглушка хостинга на самом домене, https не поднят;
   - Timeweb (3): парковка `vh276.timeweb.ru/parking`;
   - REG.RU (4) и RU-CENTER (3): нет даже A-записи, сайт не отвечает.
4. **kompressor-expert.ru: ЛИШНИЙ MX** — торчат оба `emx.mail.ru` И
   `mx.yandex.net`. Домен на VK → запись `mx.yandex.net` УДАЛИТЬ, иначе часть
   входящих (ответы клиентов!) уедет на Яндекс, где домен не обслуживается.

## Что доделать (по регистраторам)

### RU-CENTER — compressor-pro-systems.ru (Я360), kompressor-trade.ru + rentgen-detektor.ru (VK)

1. Добавить домен в админку почты (Я360: admin.yandex.ru → Домены;
   VK WorkSpace: biz.mail.ru) → получить verification-код → TXT на корень.
2. После подтверждения — MX/SPF/DKIM по шаблонам ниже + DMARC.
3. Редирект корня → целевой сайт (см. «Редиректы»).

### Beget (4 домена)

- Добавить DMARC (шаблон ниже).
- Заглушку хостинга заменить 301-редиректом на целевой сайт + выпустить
  бесплатный SSL (Let's Encrypt в панели), чтобы https://домен тоже работал.

### REG.RU (4 домена)

- Добавить DMARC.
- kompressor-expert.ru: удалить MX `mx.yandex.net` (оставить только `emx.mail.ru`).
- Редиректа нет совсем (нет A): в панели REG.RU включить «Перенаправление домена»
  на целевой сайт (301, с https).

### Timeweb (3 домена)

- DMARC: добавить на kompressor-pro-trade.ru и sort-systems.ru
  (compressor-store.ru — уже есть).
- Снять парковку: 301-редирект на целевой сайт + SSL.

## Шаблоны записей

**Домены на Яндекс 360:**
```
MX     @    10 mx.yandex.net.
TXT    @    "v=spf1 redirect=_spf.yandex.net"
TXT    mail._domainkey   "<DKIM из панели Я360>"
TXT    _dmarc   "v=DMARC1; p=quarantine; rua=mailto:dmarc@<домен>; adkim=s; aspf=s"
TXT    @    "yandex-verification: <код из панели>"
```

**Домены на VK WorkSpace:**
```
MX     @    10 emx.mail.ru.
TXT    @    "v=spf1 redirect=_spf.mail.ru"
TXT    mailru._domainkey   "<DKIM из панели VK>"
TXT    _dmarc   "v=DMARC1; p=quarantine; rua=mailto:dmarc@<домен>; adkim=s; aspf=s"
TXT    @    "mailru-domain: <код из панели>"
```

- MX у домена должен быть РОВНО ОДИН (своего хостинга). SPF — одна запись.
- `rua=mailto:dmarc@<домен>` требует, чтобы адрес существовал → на каждом домене
  завести алиас `dmarc@` на основной ящик (иначе отчёты в никуда).
  compressor-store.ru уже шлёт rua на postmaster@ — тоже ок, если ящик есть.
- DMARC: старт `p=quarantine`; после 2-3 недель чистой статистики → `p=reject`.

## Редиректы

Корень каждого домена → **301 на https://целевой-сайт** (КЦ → prokompressor.ru,
Meyer → meyer-corp.ru / vsefotoseparatory.ru). Зачем: домен выглядит живым для
получателя и постмастера, клик по домену из письма ведёт на реальный сайт.
Обязательно и для http, и для https (нужен SSL-серт на домене-двойнике —
у всех четырёх хостеров есть бесплатный Let's Encrypt).

## Постмастера (после DNS)

- **postmaster.mail.ru** — добавить ВСЕ 14 доменов (статистика по доставке в
  ящики Mail.ru нужна и яндекс-доменам). VK-домены с включённым DKIM
  подтверждаются автоматически по подписи; остальные — DNS-записью.
  Интеграция в сендер уже есть: `postoffice.py` (нужен токен, см. модуль).
- **Почтовый офис Яндекса** (postoffice.yandex.ru) — добавить все 14; Я360-домены
  уже верифицированы в Яндексе (`yandex-verification` TXT стоит) — добавятся в
  пару кликов, VK-доменам понадобится своя верификация.

## Дальше по плану

1. DNS добит → `python3 sender/tools/check_domains.py` показывает 14/14.
2. Ящики: ~2-3 на домен, человеческие имена, пароли приложений + IMAP
   → в конфиг сендера (`mailboxes`, пароли только через env `BOX*_PASSWORD`).
3. Прогрев по `warmup.py` (ramp-план), смоук доставляемости на 2 ящиках:
   SPF/DKIM/DMARC pass + инбокс на своих тестовых ящиках Яндекс/Mail.ru.
4. Гейты уже настроены: complaint <0.1%/домен, bounce 2-3%, канарейки.
