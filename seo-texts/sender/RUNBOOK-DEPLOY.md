# Ранбук деплоя сервиса холодной рассылки «Руспром»

Руководство по установке, настройке и эксплуатации сервиса массовых email-рассылок на базе Python 3.11 и SQLite.

---

## 1. Требования

### 1.1. Программное обеспечение

- **Python 3.11** (обязательно именно 3.11)
  - Скачать с [python.org/downloads](https://www.python.org/downloads/)
  - При установке **обязательно** поставить галку **"Add Python 3.11 to PATH"**
  - После установки проверить в командной строке:
    ```cmd
    python --version
    ```
    Должно вывести: `Python 3.11.x`

- **Git** (опционально, для обновлений через `git pull`)
  - Скачать с [git-scm.com](https://git-scm.com/download/win)
  - Альтернатива: получать обновления вручную (архивом)

### 1.2. Системные требования

- Windows Server (любая версия, поддерживающая Python 3.11)
- Минимум 2 ГБ свободного места на диске (БД + логи)
- Постоянное подключение к интернету
- Доступ к SMTP/IMAP серверам почтовых ящиков
- Публичный IP или возможность настройки обратного прокси для отписки

### 1.3. Зависимости

**Движок (`sender/*.py`) — только стандартная библиотека Python 3.11.** Внешние
пакеты нужны лишь для веб-панели (FastAPI) и для тестов.

- Веб-панель API: `pip install -r sender/api/requirements.txt` (fastapi, uvicorn).
- **Тест-зависимости: `pip install -r sender/requirements-dev.txt`** (pytest,
  fastapi, httpx, uvicorn, aiosmtpd). ⚠️ **Критично:** без `fastapi`/`httpx`
  тесты API (`test_api.py`) молча SKIP-аются, без `aiosmtpd` — интеграционный
  SMTP-прогон; сьют выглядит зелёным, а слой не проверен. Прогон с показом
  скрытых пропусков: `python3 -m pytest sender/tests/ -q -rs` — должно быть
  603 passed / 0 skipped.
- Фронт-панель (`sender/web/`, опционально, для UX): Node.js 20+ и npm; сборка
  `cd sender/web && npm install && npm run build` → статика `dist/`. Раздаётся
  nginx (или FastAPI StaticFiles), `/api` проксируется на `serve-api`. Тесты
  фронта: `npm test` (Vitest) и `npm run e2e` (Playwright против serve-api).

---

## 2. Установка

### 2.1. Создание структуры каталогов

Откройте командную строку от имени администратора и выполните:

```cmd
mkdir C:\sender
mkdir C:\sender\logs
cd C:\sender
```

### 2.2. Получение кода

**Вариант A: через Git (рекомендуется)**

```cmd
cd C:\sender
git clone https://github.com/ваш-репозиторий/sender.git .
```

Или клонировать конкретную ветку:

```cmd
git clone -b production https://github.com/ваш-репозиторий/sender.git .
```

**Вариант B: ручное копирование**

1. Скачайте архив с кодом
2. Распакуйте содержимое в `C:\sender`
3. Убедитесь, что структура такая:
   ```
   C:\sender\
   ├── sender\           (пакет Python)
   ├── config\
   │   └── sender.example.yaml
   ├── tests\
   └── README.md
   ```

### 2.3. Установка зависимостей

```cmd
cd C:\sender
pip install -r requirements.txt
```

Проверка установки:

```cmd
python -m sender --help
```

Должна появиться справка по командам.

### 2.4. Создание конфигурационного файла

Скопируйте шаблон конфига:

```cmd
copy config\sender.example.yaml sender.yaml
```

Откройте `C:\sender\sender.yaml` в текстовом редакторе (Notepad++, VSCode) и настройте:

#### 2.4.1. Секция `service`

```yaml
service:
  db_path: C:\sender\sender.db
  timezone: Europe/Moscow
  consent_log_path: C:\sender\consent_log.jsonl
```

#### 2.4.2. Секция `mailboxes`

Для каждого почтового ящика:

```yaml
mailboxes:
  - box_id: box1
    smtp_host: smtp.yandex.ru
    smtp_port: 587
    smtp_user: box1@ваш-домен.ru
    # Пароль НЕ указываем здесь! Только через переменную окружения BOX1_PASSWORD
    imap_host: imap.yandex.ru
    imap_port: 993
    imap_user: box1@ваш-домен.ru
    # Пароль тот же — BOX1_PASSWORD
    daily_limit: 100
    warmup_enabled: true
    warmup_start_limit: 10
    warmup_increment: 5
    warmup_days: 14
```

**Важно**: используйте пароли приложений (для Yandex, Gmail и т.д.), а не основной пароль аккаунта.

#### 2.4.3. Секция `orchestrator`

```yaml
orchestrator:
  tick_interval_sec: 300  # Проверка каждые 5 минут
  send_windows:
    - start: "09:00"
      end: "12:00"
    - start: "14:00"
      end: "18:00"
  max_concurrent_boxes: 3
```

#### 2.4.4. Секция `unsub_server`

```yaml
unsub_server:
  unsub_base_url: https://unsub.ваш-домен.ru
  # Секрет для подписи токенов — ТОЛЬКО через переменную окружения UNSUB_SIGNING_SECRET
```

#### 2.4.5. Секция `legal`

```yaml
legal:
  entity_name: ООО "Руспром"
  entity_inn: "1234567890"
  entity_address: "г. Москва, ул. Примерная, д. 1"
  contact_email: info@ваш-домен.ru
  contact_phone: "+7 (495) 123-45-67"
```

#### 2.4.6. Секции интеграций (опционально)

```yaml
bitrix:
  enabled: true
  # URL вебхука — через переменную окружения BITRIX_WEBHOOK_URL
  deal_stage_on_reply: "C1:NEW"

telegram:
  enabled: true
  # Токен бота — через переменную окружения TELEGRAM_BOT_TOKEN
  chat_id: -1001234567890  # ID чата для уведомлений

postoffice:
  enabled: true
  # Токен API — через переменную окружения POSTOFFICE_TOKEN
```

### 2.5. Настройка переменных окружения

**Все секреты передаются ТОЛЬКО через переменные окружения**, не указывайте их в `sender.yaml`!

#### 2.5.1. Вариант A: через команду `setx` (постоянные, на уровне пользователя)

Откройте командную строку от имени администратора:

```cmd
setx BOX1_PASSWORD "пароль-приложения-ящика-1"
setx BOX2_PASSWORD "пароль-приложения-ящика-2"
setx UNSUB_SIGNING_SECRET "32-случайных-байта-в-hex-формате"
setx BITRIX_WEBHOOK_URL "https://ваш-битрикс.bitrix24.ru/rest/123/ключ/"
setx TELEGRAM_BOT_TOKEN "123456:ABC-DEF..."
setx POSTOFFICE_TOKEN "ваш-токен-postoffice"
```

**Важно**: после `setx` нужно **перезапустить командную строку** (или перелогиниться), чтобы переменные стали доступны.

Для генерации `UNSUB_SIGNING_SECRET` (64 символа hex = 32 байта):

```cmd
python -c "import secrets; print(secrets.token_hex(32))"
```

#### 2.5.2. Вариант B: через графический интерфейс (удобнее для постоянных настроек)

1. Win + Pause → **Дополнительные параметры системы**
2. Кнопка **Переменные среды**
3. В разделе **Переменные пользователя для Administrator** (или вашего пользователя) нажать **Создать**
4. Добавить каждую переменную:
   - Имя: `BOX1_PASSWORD`
   - Значение: `пароль-приложения`
5. Повторить для всех переменных из списка выше
6. **ОК** → **ОК** → перезапустить консоль

**Проверка** (в новой командной строке):

```cmd
echo %BOX1_PASSWORD%
```

Должен вывести пароль (не `%BOX1_PASSWORD%`).

### 2.6. Инициализация базы данных

```cmd
cd C:\sender
python -m sender init-db --config sender.yaml
```

Должно вывести:

```
Database initialized: C:\sender\sender.db
```

### 2.7. Тестовый запуск

Проверим, что всё настроено корректно, запустив «сухой прогон»:

```cmd
python -m sender run --config sender.yaml --once --dry-run
```

Должно быть примерно так:

```
[INFO] Orchestrator started (dry-run mode, single iteration)
[INFO] No campaigns ready to send
[INFO] Orchestrator finished
```

Если ошибок нет — установка завершена!

---

## 3. Автозапуск при старте Windows

Для круглосуточной работы сервису нужны два постоянно запущенных процесса:

1. **Оркестратор** — основной движок рассылки (волны, IMAP-мониторинг, прогрев)
2. **Unsub-сервер** — публичный веб-сервер для обработки отписок

### 3.1. Вариант A: NSSM (рекомендуется)

**NSSM** (Non-Sucking Service Manager) — утилита для превращения любой программы в Windows-службу.

#### 3.1.1. Установка NSSM

1. Скачать с [nssm.cc/download](https://nssm.cc/download) (выбрать архив)
2. Распаковать в `C:\nssm\`
3. Добавить `C:\nssm\win64\` в PATH или использовать полный путь

#### 3.1.2. Создание службы оркестратора

Откройте командную строку от имени администратора:

```cmd
cd C:\nssm\win64
nssm install SenderOrchestrator
```

Откроется окно настройки. Заполните:

- **Application**:
  - Path: `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe` (найти через `where python`)
  - Startup directory: `C:\sender`
  - Arguments: `-m sender run --config C:\sender\sender.yaml`

- **Details**:
  - Display name: `Sender Orchestrator`
  - Description: `Ruspromo cold email orchestrator`
  - Startup type: `Automatic`

- **I/O**:
  - Output (stdout): `C:\sender\logs\orchestrator.log`
  - Error (stderr): `C:\sender\logs\orchestrator.err.log`

- **File rotation**:
  - Поставить галку **Rotate files**
  - Rotate online: `1` (ротация при работе)
  - Restrict rotation: `10485760` (10 МБ на файл)

Нажать **Install service**.

#### 3.1.3. Создание службы unsub-сервера

```cmd
nssm install SenderUnsubServer
```

Заполнить аналогично:

- **Application**:
  - Path: `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe`
  - Startup directory: `C:\sender`
  - Arguments: `-m sender.unsub_server --config C:\sender\sender.yaml --port 8080`

- **Details**:
  - Display name: `Sender Unsub Server`
  - Description: `Ruspromo unsubscribe web server`

- **I/O**:
  - Output: `C:\sender\logs\unsub.log`
  - Error: `C:\sender\logs\unsub.err.log`
  - File rotation: включить, 10 МБ

Нажать **Install service**.

#### 3.1.4. Запуск служб

```cmd
nssm start SenderOrchestrator
nssm start SenderUnsubServer
```

Проверка статуса:

```cmd
nssm status SenderOrchestrator
nssm status SenderUnsubServer
```

Должно показать `SERVICE_RUNNING`.

Также можно проверить через GUI:

```
Win + R → services.msc
```

Найти в списке `Sender Orchestrator` и `Sender Unsub Server`, статус должен быть **Выполняется**.

#### 3.1.5. Управление службами

```cmd
nssm stop SenderOrchestrator         # Остановка
nssm restart SenderOrchestrator      # Перезапуск
nssm remove SenderOrchestrator       # Удаление службы (подтвердить)
```

Или через `services.msc` (правой кнопкой → Остановить/Перезапустить).

### 3.2. Вариант B: Планировщик заданий Windows (альтернатива)

Если NSSM не подходит, можно использовать встроенный Task Scheduler.

#### 3.2.1. Создание задания для оркестратора

1. Win + R → `taskschd.msc`
2. Правой кнопкой на **Библиотека планировщика заданий** → **Создать задачу**
3. **Общие**:
   - Имя: `Sender Orchestrator`
   - Пользователь: текущий администратор
   - Выполнять независимо от регистрации пользователя: **галка**
   - Выполнять с наивысшими правами: **галка**
4. **Триггеры** → **Создать**:
   - Начать: `При запуске`
   - Задержка: `1 минута`
5. **Действия** → **Создать**:
   - Программа: `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe`
   - Аргументы: `-m sender run --config C:\sender\sender.yaml`
   - Рабочая папка: `C:\sender`
6. **Условия**:
   - Убрать галку **Запускать только при питании от сети** (если ноутбук)
7. **Параметры**:
   - Перезапустить при сбое: **каждые 1 минуту, до 3 раз**
   - Остановить задачу, выполняющуюся более: **снять галку**

Аналогично создать задание для unsub-сервера с аргументами `-m sender.unsub_server --config C:\sender\sender.yaml --port 8080`.

**Недостатки Task Scheduler**:

- Нет встроенной ротации логов
- Сложнее управлять из командной строки
- Нет простого способа видеть stdout/stderr в реальном времени

---

## 4. Публикация сервера отписки

Unsub-сервер слушает на `http://localhost:8080`. Для работы отписок нужно:

1. Открыть порт 443 (HTTPS) на внешнем IP сервера
2. Настроить обратный прокси или использовать проксирование Cloudflare
3. Убедиться, что `unsub_base_url` в `sender.yaml` совпадает с публичным адресом

### 4.1. Вариант A: Обратный прокси через IIS + ARR

#### 4.1.1. Установка IIS и ARR

1. **Установка IIS**:
   - Откройте **Server Manager** → **Manage** → **Add Roles and Features**
   - Роль: **Web Server (IIS)**
   - Компоненты: оставить по умолчанию, добавить **WebSockets** (если нужно в будущем)

2. **Установка URL Rewrite и ARR**:
   - Скачать [URL Rewrite Module](https://www.iis.net/downloads/microsoft/url-rewrite)
   - Скачать [Application Request Routing (ARR)](https://www.iis.net/downloads/microsoft/application-request-routing)
   - Установить оба модуля

#### 4.1.2. Настройка ARR

1. Открыть **IIS Manager** (Win + R → `inetmgr`)
2. Выбрать сервер в дереве слева
3. Двойной клик на **Application Request Routing Cache**
4. В правой панели: **Server Proxy Settings**
5. Поставить галку **Enable proxy**
6. **Apply**

#### 4.1.3. Создание сайта для отписки

1. В IIS Manager: **Sites** → правой кнопкой → **Add Website**
   - Site name: `UnsubSite`
   - Physical path: `C:\inetpub\wwwroot\unsub` (создать пустую папку)
   - Binding:
     - Type: `https`
     - IP address: `All Unassigned` или конкретный внешний IP
     - Port: `443`
     - Host name: `unsub.ваш-домен.ru`
     - SSL certificate: выбрать/импортировать сертификат (Let's Encrypt, коммерческий и т.д.)

2. Создать файл `C:\inetpub\wwwroot\unsub\web.config`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="ReverseProxyToUnsub" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://localhost:8080/{R:1}" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
```

3. **Restart** сайта в IIS

#### 4.1.4. Проверка

Откройте браузер:

```
https://unsub.ваш-домен.ru/health
```

Должно вернуться `{"status":"ok"}` (если в unsub_server есть эндпоинт health).

### 4.2. Вариант B: Проброс порта + Cloudflare Proxy

Если не хотите настраивать IIS, можно использовать Cloudflare в качестве прокси-сервера с автоматическим SSL.

#### 4.2.1. Настройка Cloudflare

1. Зайдите на [cloudflare.com](https://www.cloudflare.com/) и добавьте домен (или он уже добавлен)
2. Создайте A-запись:
   - Name: `unsub`
   - IPv4 address: `внешний IP вашего VPS`
   - Proxy status: **Proxied** (оранжевая туча)
   - TTL: `Auto`
3. В настройках DNS → **SSL/TLS**:
   - Режим: **Flexible** (Cloudflare → сервер по HTTP) или **Full** (если на сервере есть самоподписанный сертификат)

#### 4.2.2. Проброс порта на Windows Server

В файрволе Windows создайте правило перенаправления 443 → 8080 (или просто откройте 8080 наружу и измените `--port 8080` на `--port 443` в аргументах unsub_server, но тогда нужны права администратора для биндинга на привилегированный порт).

**Рекомендация**: оставить unsub-сервер на 8080, а использовать Cloudflare для проксирования 443 → 80, и настроить nginx/IIS слушать на 80 и проксировать на 8080.

Упрощённый вариант: **разрешить входящие соединения на 8080** (если Cloudflare поддерживает проксирование на нестандартный порт, что зависит от тарифа).

#### 4.2.3. Изменение sender.yaml

```yaml
unsub_server:
  unsub_base_url: https://unsub.ваш-домен.ru
```

#### 4.2.4. Проверка

```
https://unsub.ваш-домен.ru/health
```

---

## 5. Эксплуатация

### 5.1. Просмотр статуса и статистики

#### 5.1.1. Общий статус системы

```cmd
cd C:\sender
python -m sender status --config sender.yaml
```

Выведет JSON с информацией:

- Активные кампании
- Состояние каждого ящика (отправлено сегодня, лимит, прогрев)
- Последние ошибки

#### 5.1.2. Детальная статистика

```cmd
python -m sender stats --config sender.yaml
```

Выведет:

- Общее количество отправленных писем
- Открытия, клики, ответы, отписки
- Статистика по кампаниям
- Срабатывания kill-switch

### 5.2. Пауза и возобновление

#### 5.2.1. Пауза всей системы

```cmd
python -m sender pause --config sender.yaml
```

Оркестратор продолжит работать, но отправки не будет.

#### 5.2.2. Возобновление

```cmd
python -m sender resume --config sender.yaml
```

#### 5.2.3. Пауза конкретного ящика

Отредактируйте `sender.yaml`, для нужного ящика добавьте:

```yaml
mailboxes:
  - box_id: box1
    paused: true
```

Перезапустите оркестратор:

```cmd
nssm restart SenderOrchestrator
```

Или через планировщик: `taskschd.msc` → правой кнопкой → **Завершить** → **Выполнить**.

### 5.3. Добавление новой кампании (полный цикл)

#### 5.3.1. Импорт получателей

Создайте CSV-файл (например, `recipients.csv`) с колонками:

```csv
email,first_name,company,position
ivan@example.com,Иван,ООО Рога и Копыта,Директор
maria@example.com,Мария,ИП Сидоров,Главный инженер
```

Импорт:

```cmd
python -m sender import --config sender.yaml recipients.csv --map "email=email,first_name=first_name,company=company,position=position"
```

При успехе выведет:

```json
{
  "imported": 2,
  "duplicates": 0,
  "invalid": 0
}
```

#### 5.3.2. Валидация email (опционально)

```cmd
python -m sender validate --config sender.yaml --limit 1000
```

Проверит синтаксис и MX-записи (если настроен валидатор в конфиге).

#### 5.3.3. Создание кампании

```cmd
python -m sender campaign-create --config sender.yaml --name "Предложение для производственников Q1 2025"
```

Выведет:

```
Campaign created: 1
```

Запомните ID кампании (в данном случае `1`).

#### 5.3.4. Добавление шагов последовательности

Создайте файлы с текстами писем:

**step1.txt**:

```
Добрый день, {first_name}!

Меня зовут Алексей, я представляю компанию «Руспром».

Видел, что вы работаете в {company} на позиции {position}. Хотел предложить...

[текст первого письма]

С уважением,
Алексей Иванов
Руспром
```

**step2.txt** (follow-up через 3 дня):

```
{first_name}, добрый день!

Писал вам в понедельник про...

[текст второго письма]
```

Добавляем шаги:

```cmd
python -m sender campaign-add-step --config sender.yaml --campaign 1 --index 0 --subject "Предложение для {company}" --body-file step1.txt --delay-hours 0

python -m sender campaign-add-step --config sender.yaml --campaign 1 --index 1 --subject "Re: Предложение для {company}" --body-file step2.txt --delay-hours 72 --gate replied_to_step_0
```

`--gate replied_to_step_0` означает: отправить шаг 1 только если **не было ответа** на шаг 0.

#### 5.3.5. Активация кампании

```cmd
python -m sender campaign-activate --config sender.yaml --campaign 1
```

Выведет:

```
Campaign 1 activated
```

Теперь кампания начнёт отправку в ближайшее окно отправки.

### 5.4. Обновление кода

#### 5.4.1. Через Git

```cmd
cd C:\sender
git pull origin production
```

#### 5.4.2. Запуск тестов

```cmd
pytest
```

Убедитесь, что все тесты прошли (`passed`).

#### 5.4.3. Перезапуск служб

```cmd
nssm restart SenderOrchestrator
nssm restart SenderUnsubServer
```

Или через `services.msc`.

#### 5.4.4. Проверка логов

```cmd
type C:\sender\logs\orchestrator.log
```

Убедитесь, что нет ошибок при старте.

### 5.5. Просмотр логов

#### 5.5.1. В реальном времени (PowerShell)

```powershell
Get-Content C:\sender\logs\orchestrator.log -Wait -Tail 50
```

Аналог `tail -f` в Linux.

#### 5.5.2. Последние N строк

```cmd
powershell -Command "Get-Content C:\sender\logs\orchestrator.log -Tail 100"
```

#### 5.5.3. Поиск ошибок

```cmd
findstr /C:"ERROR" C:\sender\logs\orchestrator.log
```

### 5.6. Ротация логов

NSSM автоматически ротирует логи при превышении 10 МБ (если настроено в секции File rotation).

Для ручной очистки старых логов:

```cmd
cd C:\sender\logs
del *.log.1
del *.log.2
```

Или настроить скрипт очистки логов старше N дней (см. раздел 6.2).

---

## 6. Бэкапы

### 6.1. Бэкап базы данных

БД SQLite хранится в одном файле (`sender.db`). Есть два способа бэкапа:

#### 6.1.1. Вариант A: Копирование файла (безопасно только при остановленном оркестраторе)

```cmd
nssm stop SenderOrchestrator
copy C:\sender\sender.db C:\sender\backups\sender_%date:~-4,4%%date:~-7,2%%date:~-10,2%.db
nssm start SenderOrchestrator
```

Формат имени: `sender_20250120.db` (год-месяц-день).

#### 6.1.2. Вариант B: Online backup через sqlite3 (можно на работающей БД)

```cmd
sqlite3 C:\sender\sender.db ".backup 'C:\sender\backups\sender_%date:~-4,4%%date:~-7,2%%date:~-10,2%.db'"
```

Для этого нужен `sqlite3.exe` (скачать с [sqlite.org](https://www.sqlite.org/download.html)).

### 6.2. Бэкап consent_log (важен юридически!)

`consent_log.jsonl` — журнал всех отписок и согласий, **обязателен для хранения по 152-ФЗ**.

```cmd
copy C:\sender\consent_log.jsonl C:\sender\backups\consent_log_%date:~-4,4%%date:~-7,2%%date:~-10,2%.jsonl
```

### 6.3. Автоматизация бэкапов

Создайте PowerShell-скрипт `C:\sender\scripts\backup.ps1`:

```powershell
$date = Get-Date -Format "yyyyMMdd"
$backupDir = "C:\sender\backups"
$dbPath = "C:\sender\sender.db"
$consentPath = "C:\sender\consent_log.jsonl"

# Создаём папку для бэкапов, если её нет
if (!(Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir
}

# Бэкап БД через sqlite3 (online)
& "C:\sqlite3\sqlite3.exe" $dbPath ".backup '$backupDir\sender_$date.db'"

# Бэкап consent_log
Copy-Item $consentPath "$backupDir\consent_log_$date.jsonl"

# Удаляем бэкапы старше 90 дней
Get-ChildItem $backupDir -Filter "*.db" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-90) } | Remove-Item
Get-ChildItem $backupDir -Filter "consent_log_*.jsonl" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-90) } | Remove-Item

Write-Output "Backup completed: $date"
```

Добавьте задание в планировщик:

1. `taskschd.msc` → **Создать задачу**
2. **Триггеры**: ежедневно в 03:00
3. **Действия**: `powershell.exe -ExecutionPolicy Bypass -File C:\sender\scripts\backup.ps1`
4. **Условия**:

---

## 7. Веб-панель (сайт для отдела продаж)

Панель — SPA (`sender/web`, React+Vite) поверх FastAPI-транспорта (`serve-api`).
28 продажников берут лиды, owner ведёт кампании/домены/комплаенс. Это **внутренний
инструмент** — публиковать в открытый интернет не нужно, доступ ограничить офисной
сетью/VPN. Готовые конфиги — в `sender/deploy/` (см. `sender/deploy/README.md`).

### 7.1. Как устроено (две топологии)

Фронт всегда бьёт в `/api/*` (`web/src/api/client.ts`, `API_BASE="/api"`). Куда это
приземляется — зависит от топологии:

- **Linux — nginx + systemd (рекомендуется).** nginx терминирует TLS, отдаёт статику
  `web/dist` напрямую и проксирует `/api/*` → `serve-api` на `127.0.0.1:8090`
  (роуты API в корне; nginx срезает префикс `/api` трейлинг-слэшем в `proxy_pass`,
  ровно как dev-прокси Vite). `serve-api` запускается **без** `--static-dir`.
- **Windows — NSSM + IIS/ARR (как движок, §3–4).** `serve-api` запускается в режиме
  «сайт+API одним процессом» (`--static-dir web\dist`): uvicorn сам раздаёт и SPA, и
  API под `/api`. Публикуется через IIS+ARR/Cloudflare (§4) для TLS — как unsub-сервер.

Обе опираются на один код: режим `--static-dir` реализован в `make_site_app`
(`sender/api/app.py`) — монтирует API под `/api` и отдаёт `index.html` на любой
неизвестный путь (client-side-роутинг React Router; перезагрузка на `/campaigns/5`
не даёт 404).

### 7.2. Сборка SPA

Нужен Node.js 18+ (только на время сборки; в рантайме — нет).

```bash
cd /opt/rusprom-sender/seo-texts/sender/web    # (Windows: C:\sender\seo-texts\sender\web)
npm ci
npm run build      # → web/dist (index.html + assets/index-XXXX.js|css)
```

`dist/` можно собрать на любой машине и скопировать на сервер — это статика.

### 7.3. Зависимости API и первый owner

```bash
# API требует fastapi+uvicorn (движок — stdlib; см. §1.3 и requirements-dev.txt)
/opt/rusprom-sender/venv/bin/pip install -r seo-texts/sender/requirements-dev.txt

# bootstrap владельца панели (пароль — через env, НЕ в командной строке)
export SENDER_NEW_USER_PASSWORD='...'
python -m sender --config /opt/rusprom-sender/sender.yaml \
    user-create --username kirill --role owner --enable-2fa
```

С `--enable-2fa` команда один раз печатает `otpauth://`-URI — привяжите в приложении
(Google Authenticator/1Password) сразу, второй раз он не показывается.

### 7.4. Linux: nginx + systemd

```bash
# 1) служба API (localhost:8090, без --static-dir)
sudo cp seo-texts/sender/deploy/rusprom-sender-panel.service /etc/systemd/system/
sudo cp seo-texts/sender/deploy/panel.env.example /opt/rusprom-sender/panel.env
sudoedit /opt/rusprom-sender/panel.env        # заполнить SENDER_CONFIG + секреты
sudo chmod 600 /opt/rusprom-sender/panel.env
sudo systemctl daemon-reload
sudo systemctl enable --now rusprom-sender-panel
systemctl status rusprom-sender-panel         # active (running)

# 2) nginx: TLS + статика + прокси /api
sudo cp seo-texts/sender/deploy/nginx-panel.conf /etc/nginx/sites-available/rusprom-panel.conf
sudo sed -i 's/panel.example.ru/panel.вашдомен.ru/g' /etc/nginx/sites-available/rusprom-panel.conf
sudo ln -s ../sites-available/rusprom-panel.conf /etc/nginx/sites-enabled/
sudo certbot --nginx -d panel.вашдомен.ru      # выпуск сертификата
sudo nginx -t && sudo systemctl reload nginx
```

Не забудьте раскомментировать `allow/deny` в `nginx-panel.conf` под свои офисные
диапазоны/VPN — панель не должна отвечать всему интернету.

### 7.5. Windows: NSSM + IIS/ARR

```powershell
# собрать SPA (см. 7.2), затем от администратора:
powershell -ExecutionPolicy Bypass -File C:\sender\seo-texts\sender\deploy\nssm-panel-install.ps1
```

Скрипт ставит службу `RuspromSenderPanel` (`serve-api --static-dir web\dist`) на
`127.0.0.1:8090` с ротацией логов (как §3.1). Дальше опубликуйте её на HTTPS через
IIS+ARR (§4.1) или Cloudflare (§4.2), указав апстрим `http://127.0.0.1:8090` и
проксируя ВСЕ пути (и `/api`, и статику — процесс один). Ограничьте доступ правилом
IIS/файрвола на офисные IP.

### 7.6. Стейджинг/смоук без прокси (`--static-dir`)

Быстро поднять сайт целиком одним процессом (без nginx/IIS) — для проверки перед
боем или на тест-домене:

```bash
python -m sender --config /opt/rusprom-sender/sender.yaml \
    serve-api --host 0.0.0.0 --port 8090 --static-dir seo-texts/sender/web/dist
```

Откройте `http://<host>:8090/` — увидите панель. Для боевого доступа с TLS всё равно
ставьте nginx/IIS перед процессом.

### 7.7. Проверка после установки

```bash
# health бэкенда (через nginx)
curl -sf https://panel.вашдомен.ru/api/health        # {"status":"ok"}
# health процесса напрямую (all-in-one режим отдаёт и /healthz)
curl -sf http://127.0.0.1:8090/health                # {"status":"ok"}
```

В браузере: логин owner'ом → дашборд-светофор → «Лента лидов» видна; создать
тестовую кампанию (Обзор → «Новая кампания») → добавить шаг → «Запустить» →
проверить, что действие попало в «Аудит действий». Менеджер видит только
ленту/статистику/профиль (ролевой гейт).

### 7.8. Обновление панели

```bash
cd /opt/rusprom-sender/seo-texts
git pull origin main                                 # или свою ветку
cd sender/web && npm ci && npm run build             # пересобрать статику
sudo systemctl restart rusprom-sender-panel          # Linux (nginx подхватит новый dist сам)
# Windows: nssm restart RuspromSenderPanel
```

nginx отдаёт `dist/` напрямую — новые хэшированные ассеты подхватываются без reload;
reload нужен только при правке самого `nginx-panel.conf`. В all-in-one режиме статику
держит процесс — его перезапуск обязателен.
