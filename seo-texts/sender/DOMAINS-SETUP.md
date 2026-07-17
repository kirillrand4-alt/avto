# Домены-двойники для холодной рассылки — закупка и настройка

Проверено 2026-07-17 через DNS-over-HTTPS (NS есть → занят; NXDOMAIN → свободен).
Финальная истина — на checkout регистратора. Основной `prokompressor.ru` — на reg.ru,
поэтому двойники берём на ДРУГИХ регистраторах (декорреляция от основного домена).

⚠️ Оплата/регистрация — на владельце (карта, 3-D Secure). Я подготовил список, свободность,
распределение и DNS; тебе — оплатить и вставить записи.

## 10 доменов (все СВОБОДНЫ на дату проверки)

| # | Домен | Регистратор | Хост ящиков | Шлёт получателям |
|---|---|---|---|---|
| 1 | prokompressor-sales.ru | RU-CENTER (nic.ru) | Яндекс 360 | Яндекс + свои корп |
| 2 | prokompressor-msk.ru | RU-CENTER (nic.ru) | Яндекс 360 | Яндекс + свои корп |
| 3 | kompressor-cc.ru | Beget | Яндекс 360 | Яндекс + свои корп |
| 4 | kc-kompressor.ru | Beget | Яндекс 360 | Яндекс + свои корп |
| 5 | kompressorcenter.ru | Timeweb | Яндекс 360 | Яндекс + свои корп |
| 6 | kompressor-podbor.ru | Timeweb | Яндекс 360 | Яндекс + свои корп |
| 7 | kompressor-postavka.ru | Sprinthost | VK WorkSpace | Mail.ru |
| 8 | kompressor-zakaz.ru | Sprinthost | VK WorkSpace | Mail.ru |
| 9 | kompressor-raschet.ru | 2domains | VK WorkSpace | Mail.ru |
| 10 | air-kompressor-msk.ru | 2domains | VK WorkSpace | Mail.ru |

Сплит 6 Я360 / 4 VK — под перекос базы (Яндекс 7013 + свои 9629 vs Mail.ru/VK 5020, из
`mx-summary.json`). Резерв (тоже свободны): prokompressor-shop.ru, kompressor-center-msk.ru,
kcvozduh.ru, kompressornye-resheniya.ru, rusprom-kompressor.ru.

Исключён `enger-service.ru` — родной бренд Enger, не вязать его репутацию к холодной рассылке.

## На каждом домене (после регистрации)

1. **301-редирект корня** домена → https://prokompressor.ru (чтобы домен выглядел живым;
   основной сайт НЕ трогаем).
2. **DNS-записи** (точные значения — из панели Яндекс 360 / VK, ниже шаблон):

**Домены на Яндекс 360:**
```
MX     @    10 mx.yandex.net.
TXT    @    "v=spf1 redirect=_spf.yandex.net"
TXT    mail._domainkey   "<DKIM 2048 из панели Я360>"
TXT    _dmarc   "v=DMARC1; p=quarantine; rua=mailto:dmarc@<домен>; adkim=s; aspf=s"
TXT    @    "<verification-запись Я360>"
```

**Домены на VK WorkSpace (Mail.ru для бизнеса):**
```
MX     @    10 emx.mail.ru.
TXT    @    "v=spf1 redirect=_spf.mail.ru"
TXT    mailru._domainkey   "<DKIM 2048 из панели VK>"
TXT    _dmarc   "v=DMARC1; p=quarantine; rua=mailto:dmarc@<домен>; adkim=s; aspf=s"
TXT    @    "<verification-запись VK>"
```

3. **DMARC:** старт `p=quarantine`, через 2-3 недели чистой статистики → `p=reject`.
4. **Трекинг-домен** (для пикселей/ссылок отписки) — ОТДЕЛЬНЫЙ поддомен на одном из двойников
   (напр. `link.kompressor-cc.ru`), НЕ основной сайт.
5. **Ящики:** ~3 на домен (реальные человеческие имена под «от продажника»), пароль приложения
   + IMAP → подключить в сендер.

## Смета (ориентир)

- Домены: 10 × ~250 ₽/год ≈ **2 500 ₽/год**.
- Ящики: ~30 × ~250 ₽/мес ≈ **7 500 ₽/мес** (20 Я360 + 10 VK).
- Вход первый месяц ≈ **10 тыс ₽**.
