# Раскладка 24 купленных доменов + шаги настройки

Куплено 24 домена (разные регистраторы), делятся по направлениям. Полные DNS-шаблоны,
прогрев, ФЗ-38 и привязка к `sender.yaml` — в `DOMAINS-PREP-PLAN.md`. Здесь — конкретное
назначение каждого домена и порядок действий.

## Раскладка по направлениям и хостингу

Правило: на домене все ящики — на ОДНОМ провайдере. Держим оба провайдера (Я360 + VK),
чтобы движок слал «свой-своему» (mail.ru-получателям с VK-ящиков, yandex — с Я360).

### Компрессор Центр — 18 доменов → редирект на `https://prokompressor.ru`

**Яндекс 360 (10):**
| Домен | Хостинг |
|---|---|
| compressor-air-expert.ru | Яндекс 360 |
| compressor-air-systems.ru | Яндекс 360 |
| compressor-pro-systems.ru | Яндекс 360 |
| compressor-pro-trade.ru | Яндекс 360 |
| kompressor-air-systems.ru | Яндекс 360 |
| kompressor-air-trade.ru | Яндекс 360 |
| kompressor-pro-expert.ru | Яндекс 360 |
| kompressor-pro-systems.ru | Яндекс 360 |
| kompressor-pro-trade.ru | Яндекс 360 |
| kompressor-ru.ru | Яндекс 360 |

**VK WorkSpace (8):**
| Домен | Хостинг |
|---|---|
| kompressor-systems.ru | VK WorkSpace |
| compressor-store.ru | VK WorkSpace |
| kompressor-air-expert.ru | VK WorkSpace |
| compressor-pro-expert.ru | VK WorkSpace |
| kompressor-trade.ru | VK WorkSpace |
| compressor-air-trade.ru | VK WorkSpace |
| kompressor-expert.ru | VK WorkSpace |
| compressor-systems.ru | VK WorkSpace |

### Meyer — 6 доменов → редирект: фотосепараторы на `vsefotoseparatory.ru`, рентген на `meyer-corp.ru`

| Домен | Хостинг | Редирект (продукт) |
|---|---|---|
| optic-sort.ru | Яндекс 360 | vsefotoseparatory.ru (фотосепаратор) |
| zernosort.ru | Яндекс 360 | vsefotoseparatory.ru (зерносортировка) |
| sort-systems.ru | Яндекс 360 | vsefotoseparatory.ru |
| rentgen-systems.ru | Яндекс 360 | meyer-corp.ru (рентген) |
| sort-inspection.ru | VK WorkSpace | vsefotoseparatory.ru / usort.ru |
| rentgen-detektor.ru | VK WorkSpace | meyer-corp.ru (рентген) |

Итого: **14 Яндекс 360 + 10 VK**. (Сплит можно двигать — важно, чтобы были оба.)

## ⚠️ Фазировать прогрев — не запускать все 24 разом

24 домена × 3 ящика = 72 ящика ≈ 18 000 ₽/мес и огромный объём прогрева. Рекомендация:
- **Волна 1 (сейчас):** 8–10 доменов (по обоим направлениям и провайдерам), 2–3 ящика
  каждый → прогрев 2 недели → боевой пуск.
- **Волна 2:** ещё 8–10, когда первая вышла на объём.
- Остальные держать зарегистрированными в резерве (DNS можно настроить сразу — прогрев позже).

Стартовая волна 1 (предложение): compressor-air-systems, kompressor-pro-trade,
kompressor-ru (Я360-КЦ); kompressor-systems, compressor-store, kompressor-trade (VK-КЦ);
optic-sort, zernosort (Я360-Meyer); sort-inspection, rentgen-detektor (VK-Meyer).

## Шаги настройки (по каждому домену)

1. **Организации в панелях** (один раз): Яндекс 360 (admin.yandex.ru) и VK WorkSpace (biz.mail.ru).
2. **Добавить домен** в нужную панель → получить **verification-запись** → вставить в DNS у
   регистратора → «Проверить».
3. **DNS** (значения из панели): MX + SPF(`redirect=`) + DKIM 2048 + DMARC(`p=quarantine`) +
   verification. Шаблоны — в `DOMAINS-PREP-PLAN.md §4`.
4. **301-редирект корня** домена → на целевой сайт (КЦ → prokompressor.ru; Meyer → по продукту).
5. **Трекинг-поддомен** (для отписки/пикселей): напр. `link.<домен>`, HTTPS/443, `unsub_server`.
6. **Ящики** (2–3 на домен), человеческие имена, IMAP/SMTP вкл., **пароль приложения** → в env.
7. **Postmaster** (Яндекс + Mail.ru) вкл. на домене — мониторинг репутации.
8. **В `sender.yaml`**: mailboxes + pools (pool_yandex/pool_mailru) + routing + division-тег.

## Что от меня после настройки

- Заполню `sender.yaml` (mailboxes/pools/routing) — кроме секретов.
- Настрою `unsub_server` + трекинг-домены.
- Запущу прогрев и мониторинг репутации (Postmaster/DMARC-агрегаты).
- Раскидаю news-лиды по направлениям (kc/meyer) под правильные ящики.

## Что от тебя

- Регистрация доменов в панелях Я360/VK + верификация.
- Вставка DNS-записей у регистраторов.
- Пароли приложений ящиков → в env (`BOX*_PASSWORD`), не в чат.
- Оплата ящиков.
