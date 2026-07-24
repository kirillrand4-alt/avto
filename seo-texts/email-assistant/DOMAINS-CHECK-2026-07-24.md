# Живая проверка 24 доменов (DNS/почта/редирект) — 2026-07-24

Проверено фактическими запросами: NS (регистратор), MX/SPF/DKIM/DMARC (почта),
первый HTTP-ответ (редирект). DKIM-селекторы подтверждены: Я360 = `mail`, VK = `mailru`.

## Итог одной строкой

Почта правильно стоит на **11 доменах** (ровно те, что в таблице владельца — сверка
сошлась ✓). **Редирект не настроен ни на одном из 24.** DMARC есть только у одного.
6 доменов RU-CENTER — DNS пустой совсем. 5 доменов стоят на дефолтных MX хостинга
(не Я360/VK). 2 — без почты вообще.

## ✅ Почта настроена по плану (11) — осталось добавить DMARC и 301

| Домен | Рег. | Факт |
|---|---|---|
| compressor-air-expert.ru | REG.RU | Я360 ✓ (MX+SPF+DKIM) |
| kompressor-air-trade.ru | Beget | Я360 ✓ |
| kompressor-pro-expert.ru | Beget | Я360 ✓ |
| kompressor-pro-trade.ru | Timeweb | Я360 ✓ |
| optic-sort.ru | REG.RU | Я360 ✓ |
| zernosort.ru | REG.RU | Я360 ✓ |
| sort-systems.ru | Timeweb | Я360 ✓ |
| kompressor-air-expert.ru | Beget | VK ✓ |
| kompressor-expert.ru | REG.RU | VK ✓ |
| sort-inspection.ru | Beget | VK ✓ |
| compressor-store.ru | Timeweb | VK ✓ + единственный с DMARC ✓ |

**DMARC отсутствует у 10 из этих 11** (есть только у compressor-store.ru). Добавить
всем TXT `_dmarc`: `v=DMARC1; p=quarantine; rua=mailto:dmarc@<домен>` (шаблон —
DOMAINS-PREP-PLAN §4). Без DMARC прогрев идёт хуже (Gmail/Mail.ru требуют для bulk).

## ⚠️ Почта НЕ по плану — дефолт хостинга вместо Я360/VK (5)

| Домен | Рег. | Сейчас | Должно |
|---|---|---|---|
| compressor-air-systems.ru | REG.RU | MX hosting.reg.ru | Я360 |
| kompressor-pro-systems.ru | Beget | MX beget.com | Я360 |
| kompressor-ru.ru | Timeweb | MX timeweb.ru | Я360 |
| rentgen-systems.ru | Timeweb | MX timeweb.ru | Я360 |
| kompressor-systems.ru | Timeweb | MX timeweb.ru | VK |

Это дефолтные записи хостинга — заменить на записи из панели Я360/VK
(verification → MX → SPF → DKIM → DMARC).

## ⚠️ Почты нет вообще (2)

- compressor-pro-expert.ru (Beget, план VK) — MX/SPF пусто;
- compressor-systems.ru (REG.RU, план VK) — MX/SPF пусто.

## ⛔ RU-CENTER: DNS пустой у всех 6

compressor-pro-systems, compressor-pro-trade, kompressor-air-systems,
kompressor-trade, compressor-air-trade (все КЦ), rentgen-detektor (Meyer→meyer-corp.ru).
Ни MX, ни A-записей — домены «голые». Сначала почтовые DNS (шаги из
DOMAINS-24-ASSIGN §Шаги 1-3), потом редирект.

## Редиректы: 0 из 24

- Timeweb (6): все отвечают 302 на **парковку** vh276.timeweb.ru — не редирект.
- Beget/REG.RU с A-записью: отдают 200 (заглушка), без редиректа.
- RU-CENTER + часть REG.RU: A-записей нет, сайт не отвечает.

Цели (сверено с раскладкой): КЦ (18) → `https://prokompressor.ru`;
optic-sort/zernosort/sort-systems/sort-inspection → `https://vsefotoseparatory.ru`;
**rentgen-systems и rentgen-detektor → `https://meyer-corp.ru`** (не путать с
фотосепараторными).

# Инструкция: 301-редирект по каждому регистратору

**Общие правила (все регистраторы):**
1. Тип — именно **301** (постоянный), редиректить корень и все пути на главную цели.
2. **НЕ снести почту**: включение «переадресации» должно добавить только A/CNAME
   для `@` и `www`. После включения проверить, что MX, TXT (SPF), DKIM, DMARC
   остались в зоне. Если сервис регистратора предлагает «сменить DNS-шаблон» —
   отказаться, записи вносить точечно.
3. Чтобы редиректил и **https://** — на редиректящем хосте нужен сертификат
   (Let's Encrypt бесплатно у всех трёх хостингов). Пока серта нет, https будет
   давать ошибку — допустимо на старте, но лучше закрыть.
4. Проверка после настройки: `curl -sI http://<домен>/ | grep -i "301\|location"`
   → `301` + `Location: https://<цель>/`.

## 🟩 Beget (kompressor-air-trade, kompressor-pro-expert, kompressor-pro-systems, compressor-pro-expert, kompressor-air-expert, sort-inspection)

Штатная бесплатная переадресация:
1. Панель Beget → **«Домены и поддомены»** → у домена меню (⚙) → **«Перенаправление»**.
2. Выбрать «Перенаправить на URL», вписать цель (`https://prokompressor.ru` /
   `https://vsefotoseparatory.ru`), тип **301**, применить ко всем путям.
3. Beget сам проставит A-запись на свой redirect-сервер; MX/TXT не трогает —
   но проверить по п.2 общих правил.
4. Для https-редиректа: вместо «Перенаправления» можно создать пустой сайт,
   привязать домен, включить бесплатный SSL (Let's Encrypt, галка в «Домены»),
   в корень сайта положить `.htaccess`:
   ```
   RewriteEngine On
   RewriteRule ^ https://prokompressor.ru/ [R=301,L]
   ```

## 🟧 REG.RU (compressor-air-expert, compressor-air-systems, optic-sort, zernosort, compressor-systems, kompressor-expert)

1. Личный кабинет → **«Домены»** → карточка домена → услуга
   **«Переадресация домена»** (бесплатная; работает при DNS-серверах reg.ru —
   у этих доменов они уже стоят).
2. Указать целевой URL, режим **301 («постоянная»)**, «переадресация со всех
   страниц на главную цели», и для `www` тоже.
3. Услуга добавляет A/CNAME парковки для `@`/`www` — **после включения открыть
   «Управление DNS» и убедиться, что MX (yandex/mail.ru), TXT SPF, DKIM остались.**
4. https-вариант: у REG.RU переадресация работает по http; для https проще
   перевесить A-запись на любой свой хостинг (Beget/Timeweb) с SSL и .htaccess.

## 🟨 Timeweb (kompressor-pro-trade, kompressor-ru, rentgen-systems, sort-systems, compressor-store, kompressor-systems)

Сейчас A-записи уже смотрят на хостинг Timeweb (отвечает парковка) — осталось
заменить парковку редиректом:
1. Панель Timeweb → **«Сайты»** → «Создать сайт» (пустой) → **привязать домен**
   (снимет парковку).
2. В настройках сайта включить **SSL (Let's Encrypt)** на домен.
3. Раздел **«Редиректы»** в настройках сайта/домена: с `<домен>/*` → на цель,
   тип **301**. Либо `.htaccess` в корень сайта (как в примере Beget).
4. MX у трёх доменов тут дефолтные timeweb (см. таблицу выше) — менять на
   Я360/VK отдельно, редирект их не касается.

## ⬜ RU-CENTER / nic.ru (compressor-pro-systems, compressor-pro-trade, kompressor-air-systems, kompressor-trade, compressor-air-trade, rentgen-detektor)

DNS пока пустой — порядок: сначала почтовые записи (Я360/VK verification+MX+SPF+
DKIM+DMARC), потом редирект.
1. Кабинет nic.ru → **«Услуги → DNS-хостинг (DNS-master)»** для зоны домена.
2. В зоне добавить **«HTTP-переадресацию» (web-forwarding)** корня и `www` на
   целевой URL, тип **301** (в DNS-master это отдельный тип записи; он ставит
   A-запись на redirect-сервер nic.ru).
3. Если в тарифе переадресации нет — A-запись `@` на IP любого своего хостинга
   (Beget/Timeweb) и 301 там через .htaccess (+SSL).
4. После включения проверить сохранность MX/TXT (общие правила п.2).

## Порядок работ (рекомендация)

1. Сначала 5 доменов «дефолт хостинга» + 2 «без почты» → правильные MX/SPF/DKIM.
2. DMARC на все 10 настроенных (шаблон один).
3. 301 на 11 готовых (Beget/REG.RU/Timeweb по инструкции выше) — это волна 1 прогрева.
4. RU-CENTER-шестёрка — полный цикл DNS с нуля, они в резерв волны 2.
