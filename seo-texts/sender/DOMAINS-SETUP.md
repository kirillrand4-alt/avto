# Домены-двойники рассылки — реестр и состояние подготовки

Домены КУПЛЕНЫ владельцем (июль 2026). Реестр (машиночитаемый) —
`config/domains.json`; проверка DNS+редиректов — `python3 sender/tools/check_domains.py`
(DoH, работает и из песочницы за прокси, и с боевого сервера).
Старый план закупки с другими именами устарел и заменён этим файлом.

## Реестр: 14 доменов

| Домен | Регистратор | Хост ящиков | Напр. | Редирект на |
|---|---|---|---|---|
| compressor-pro-systems.ru ⏸ hold | RU-CENTER | Яндекс 360 | КЦ | prokompressor.ru |
| kompressor-trade.ru ⏸ hold | RU-CENTER | VK WorkSpace | КЦ | prokompressor.ru |
| rentgen-detektor.ru ⏸ hold | RU-CENTER | VK WorkSpace | Meyer | meyer-corp.ru |
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

Сплит: 8 Я360 + 6 VK; 9 КЦ + 5 Meyer. ⚠️ Три домена RU-CENTER ОТЛОЖЕНЫ
решением владельца (`status: hold` в реестре) — чекер и nginx-генератор их
пропускают; активных 11 (7 Я360 + 4 VK, 7 КЦ + 4 Meyer). Провайдер-сплит пулов (яндекс-домены →
яндекс-получатели, vk-домены → mail.ru) — уже заложен в сендере.

## Проверка 2026-07-23 (итог: 0/14 полностью готовы)

Почтовый DNS (MX/SPF/DKIM/verification) **сделан на 11 из 14** — Beget, REG.RU,
Timeweb в порядке. Дырки:

1. **RU-CENTER — все 3 домена ПУСТЫЕ** (только NS). Не добавлены даже в панели
   почты. ⏸ Отложены владельцем (`status: hold`) — пока не настраиваем.
2. **DMARC нет на 13 из 14** (есть только у compressor-store.ru).
3. **Редиректы на основные сайты не работают НИГДЕ (0/14)**:
   - Beget (4): отвечает заглушка хостинга на самом домене, https не поднят;
   - Timeweb (3): парковка `vh276.timeweb.ru/parking`;
   - REG.RU (4) и RU-CENTER (3): нет даже A-записи, сайт не отвечает.
4. **kompressor-expert.ru: ЛИШНИЙ MX** — торчат оба `emx.mail.ru` И
   `mx.yandex.net`. Домен на VK → запись `mx.yandex.net` УДАЛИТЬ, иначе часть
   входящих (ответы клиентов!) уедет на Яндекс, где домен не обслуживается.

## Что доделать (по регистраторам)

### RU-CENTER — ⏸ ОТЛОЖЕНО (compressor-pro-systems, kompressor-trade, rentgen-detektor)

Владелец поставил эти три домена на hold — пока НЕ настраиваем. Когда решит
подключать: 1) добавить домен в админку почты (Я360: admin.yandex.ru → Домены;
VK WorkSpace: biz.mail.ru) → verification-TXT на корень; 2) после
подтверждения — MX/SPF/DKIM по шаблонам ниже + DMARC; 3) редирект корня;
4) снять `status: hold` в `config/domains.json` и перегенерить
`deploy/redirects-nginx.conf` (+ добрать имена в серт через `--expand`).

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
  завести алиас `dmarc@` на основной ящик (иначе отчёты в никуда). До создания
  ящиков запись всё равно валидна — просто отчёты теряются.
  compressor-store.ru уже шлёт rua на postmaster@ — тоже ок, если ящик есть.
- DMARC: старт `p=quarantine`; после 2-3 недель чистой статистики → `p=reject`.

### DMARC: готовые записи на 13 доменов (тип TXT, имя `_dmarc`)

Одна строка = одна запись; отличается только домен в `rua=`. compressor-store.ru
пропущен — уже стоит.

```
# RU-CENTER (⏸ hold — ставить при разморозке доменов)
_dmarc.compressor-pro-systems.ru  v=DMARC1; p=quarantine; rua=mailto:dmarc@compressor-pro-systems.ru; adkim=s; aspf=s
_dmarc.kompressor-trade.ru        v=DMARC1; p=quarantine; rua=mailto:dmarc@kompressor-trade.ru; adkim=s; aspf=s
_dmarc.rentgen-detektor.ru        v=DMARC1; p=quarantine; rua=mailto:dmarc@rentgen-detektor.ru; adkim=s; aspf=s
# Beget
_dmarc.kompressor-air-trade.ru    v=DMARC1; p=quarantine; rua=mailto:dmarc@kompressor-air-trade.ru; adkim=s; aspf=s
_dmarc.kompressor-pro-expert.ru   v=DMARC1; p=quarantine; rua=mailto:dmarc@kompressor-pro-expert.ru; adkim=s; aspf=s
_dmarc.kompressor-air-expert.ru   v=DMARC1; p=quarantine; rua=mailto:dmarc@kompressor-air-expert.ru; adkim=s; aspf=s
_dmarc.sort-inspection.ru         v=DMARC1; p=quarantine; rua=mailto:dmarc@sort-inspection.ru; adkim=s; aspf=s
# REG.RU
_dmarc.compressor-air-expert.ru   v=DMARC1; p=quarantine; rua=mailto:dmarc@compressor-air-expert.ru; adkim=s; aspf=s
_dmarc.optic-sort.ru              v=DMARC1; p=quarantine; rua=mailto:dmarc@optic-sort.ru; adkim=s; aspf=s
_dmarc.zernosort.ru               v=DMARC1; p=quarantine; rua=mailto:dmarc@zernosort.ru; adkim=s; aspf=s
_dmarc.kompressor-expert.ru       v=DMARC1; p=quarantine; rua=mailto:dmarc@kompressor-expert.ru; adkim=s; aspf=s
# Timeweb
_dmarc.kompressor-pro-trade.ru    v=DMARC1; p=quarantine; rua=mailto:dmarc@kompressor-pro-trade.ru; adkim=s; aspf=s
_dmarc.sort-systems.ru            v=DMARC1; p=quarantine; rua=mailto:dmarc@sort-systems.ru; adkim=s; aspf=s
```

## Редиректы

Корень каждого домена → **301 на https://целевой-сайт** (КЦ → prokompressor.ru,
Meyer → meyer-corp.ru / vsefotoseparatory.ru). Зачем: домен выглядит живым для
получателя и постмастера, клик по домену из письма ведёт на реальный сайт.
Обязательно и для http, и для https. Редирект живёт ТОЛЬКО на A-записях —
MX/SPF/DKIM не трогает, почта работает независимо.

**Вариант А (рекомендуемый): свой nginx-редиректор** — один сервер на все 14
доменов, честный 301 + Let's Encrypt, без зоопарка панелей и без ограничений
регистраторских переадресаций (у REG.RU/RU-CENTER https на домене-источнике
не гарантирован). Готовый конфиг: `deploy/redirects-nginx.conf`
(генерируется `tools/gen_redirects_nginx.py` из реестра). **Пошаговый ранбук —
`deploy/REDIRECTS-RUNBOOK.md`** (A-записи у 4 регистраторов → nginx → certbot →
443 → автопродление → проверка). Подходит любой свой сервер с белым IP
(например, тот же, где живёт панель сендера).

**Вариант Б: панели хостеров** — для Beget/Timeweb, где домены уже прицеплены
к хостингу: включить перенаправление на URL (301) в разделе доменов + выпустить
бесплатный Let's Encrypt в разделе SSL, чтобы https тоже редиректил. Для
REG.RU/RU-CENTER — услуга «переадресация домена» у регистратора, но проверить
https на домене-источнике: если серт не выдаётся — вариант А.

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
