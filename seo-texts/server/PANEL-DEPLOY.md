# Панель рассыльщика (SenderPanel): пути и процесс обновления

Проверено фактически 2026-07-24 (вывод nssm/диагностика на сервере владельца).

## Пути на боевом сервере (Windows)

| Что | Где |
|---|---|
| Служба панели | `SenderPanel` (nssm) |
| Интерпретатор службы | `C:\Program Files\Python311\python.exe` (Python 3.11.9) |
| Рабочий каталог службы | `C:\sender` |
| Код панели (пакет) | `C:\sender\sender\` (cli.py, store.py, confirm.py, api/, web/...) |
| Конфиг | `C:\sender\config.yaml` (`--config` в CLI; env `SENDER_CONFIG`) |
| Секреты панели | `C:\sender\panel.env` (пароли ящиков BOX1..14, postmaster) |
| venv | НЕТ (системный Python 3.11; `py` без версии = 3.12 — НЕ использовать) |
| Раннер (наша автоматика) | `C:\sender\server\` (job_runner.py, служба `rusprom-runner`) |
| Секреты раннера | `C:\sender\server\runner-secrets.env` (DROP_TOKEN и др.) |
| Дроп | `https://parsercompressor.online/drop` (заголовок X-Drop-Token) |

## CLI панели — правильный вызов

Точка входа — `python -m sender` (пакетный `__main__.py`).
**`python -m sender.cli` НЕ работает** (в cli.py нет `if __name__` — импорт и тихий
выход без вывода; инцидент 2026-07-24: команды «выполнялись» пусто).

```powershell
python -m sender --config C:\sender\config.yaml <команда>
# команды: init-db | import <csv> | validate | campaign-create | campaign-add-step |
#          campaign-create --segment --send-order | campaign-activate | campaign-pause |
#          suppress-import | run ...
```

## Процесс обновления панели (канон владельца)

1. Сессия кладёт файлы на дроп (`drop_client.sh up <файл>`).
2. Владелец в PowerShell (по одной команде, НЕ использовать `&&` и `::`):

```powershell
cd C:\sender
$tok=(Select-String -Path C:\sender\server\runner-secrets.env -Pattern 'DROP_TOKEN=').Line.Split('=',2)[1].Trim()
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/<ФАЙЛ>" -Headers @{'X-Drop-Token'=$tok} -OutFile C:\sender\<КУДА>
Restart-Service SenderPanel -Force
```

3. **Код панели целиком — тоже через дроп (канон владельца 2026-07-24: «всё что
   связано с панелью делаешь ты через дроп»)**: сессия собирает `panel-update.zip`
   (пакет `sender/` + собранный `web/dist/`, фронт собирается в песочнице:
   `cd web && npm install && npm run build`; в zip НЕ класть node_modules/исходники
   web, только dist) → на дроп → владелец:

```powershell
cd C:\sender
$tok=(Select-String -Path C:\sender\server\runner-secrets.env -Pattern 'DROP_TOKEN=').Line.Split('=',2)[1].Trim()
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/panel-update.zip" -Headers @{'X-Drop-Token'=$tok} -OutFile C:\sender\panel-update.zip
Stop-Service SenderPanel -Force
Expand-Archive -Path C:\sender\panel-update.zip -DestinationPath C:\sender -Force
Start-Service SenderPanel
```

   (архив несёт пути `sender\...`, Expand-Archive в `C:\sender` кладёт поверх
   `C:\sender\sender\`; службу стопать перед распаковкой.)

## Скрипты обновления (готовые, 2026-07-26)

Ручные шаги выше остаются как аварийный путь. Штатно — три файла:

| Файл | Где запускается | Что делает |
|---|---|---|
| `build_panel_update.sh` | песочница | собирает `panel-update.zip` (пакет `sender/` + собранный `web/dist`) и `obzvon-update.zip`, кладёт всё на дроп вместе со скриптами |
| `update-panel.ps1` | сервер владельца | качает пакет, бэкапит, стопает `SenderPanel`, распаковывает, стартует, проверяет живость, при неудаче САМ откатывает |
| `update-obzvon.ps1` | сервер владельца | то же для службы `obzvon` в `C:\seostat\app` (туда `panel_file_put` не пишет — он ограничен `C:\sender`) |

Владельцу — по одной команде (без `&&`):

```powershell
$tok=(Select-String -Path C:\sender\server\runner-secrets.env -Pattern 'DROP_TOKEN=').Line.Split('=',2)[1].Trim()
Invoke-WebRequest -Uri "https://parsercompressor.online/drop/update-panel.ps1" -Headers @{'X-Drop-Token'=$tok} -OutFile C:\sender\update-panel.ps1
powershell -ExecutionPolicy Bypass -File C:\sender\update-panel.ps1
```

Для обзвона — то же с `update-obzvon.ps1`.

### ОБЯЗАТЕЛЬНО перед сборкой пакета: `python preflight_panel.py`

Сверяет хэши репозитория с боевыми и возвращает 1, если хоть один файл в репо
МЕНЬШЕ живого. Причина жёсткости — случай 2026-07-26: копия панели в репозитории
отстала от сервера (11 модулей — ai_letter, company_card, ai_quota, reply_pipeline,
mailbrowser — существовали только на сервере, а confirm/sender/store в репо были
на 10–20 КБ меньше живых). Сборка zip из репозитория и раскатка стёрли бы волны
1–4 правок и Meyer-генерацию. Репозиторий тогда синхронизирован с боем; разошедшиеся
старые версии (api/app.py поколения 23.07 со старыми именами роутов) сложены в
`seo-texts/sender-divergent/`.

Проверка живости в обоих скриптах считает успехом ЛЮБОЙ ответ, кроме 5xx и обрыва:
**401 у панели и обзвона — это штатная Basic-авторизация, а не падение**
(инцидент: скрипт принял 401 за отказ и откатил рабочую выкатку пагинации).
У обзвона маршруты смонтированы под `/obzvon` даже локально — проверять
`http://127.0.0.1:8012/obzvon/kc`, иначе штатный 404 примем за поломку.
Оба `.ps1` сохранены в UTF-8 **с BOM**: PowerShell 5.1 читает `.ps1` в системной
кодировке и без BOM ломается на кириллице в парсере.

## Смежное (не панель)

- Обновление серверных скриптов раннера: `drop_client.sh up server/<f>.py` →
  job `pull {"files":[...]}` (allowlist PULL_ALLOW); сам job_runner.py — после
  `Restart-Service rusprom-runner -Force`.
- Прочие службы сервера: DropServer, seostat.
- **job_runner НЕ запускать руками** (`python job_runner.py` в консоли): служба
  `rusprom-runner` уже крутит его. Инцидент 2026-07-24: два ручных экземпляра с
  23.07 + служба = каждый job исполнялся 2-3 раза параллельно (гонки на UNIQUE,
  перезапись result-файлов «проигравшим» инстансом). Диагноз: powershell
  `Get-CimInstance Win32_Process | ? {$_.CommandLine -like '*job_runner*'}` —
  должен быть ровно ОДИН python-процесс (службы).
- Управление панелью из сессии — операции раннера (enrich_contacts):
  `panel_file_put` (файлы с дропа в C:\sender, get-режим для чтения),
  `panel_py` (скрипт питоном панели 3.11 с env из panel.env),
  `panel_env_set` (пароли → panel.env + AppEnvironmentExtra + рестарт),
  `svc_probe` (статус/env/HTTP панели), `smtp_login_batch` (проверка логинов).
