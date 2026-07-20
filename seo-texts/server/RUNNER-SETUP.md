# Раннер заданий на сервере (C:\sender) — установка и работа

Даёт Claude «руки на сервере»: сессия из песочницы кладёт подписанное задание на
дроп, сервер (РФ-IP) исполняет разрешённый скрипт, кладёт результат обратно.
Основное применение: проверка реквизитов/адресов/выручки компаний с РФ-IP через
CapMonster + провайдер, когда из песочницы сайты недоступны или ловят Cloudflare.

## Файлы
- `job_runner.py` — служба-поллер (крутится на сервере под NSSM).
- `verify_company.py` — задача из allowlist: тянет карточку компании, при
  Cloudflare решает Turnstile через CapMonster, реквизиты извлекает провайдер.
- `run_on_server.py` — клиент на стороне Claude (подписать задание, дождаться результат).
- `runner-secrets.env` — ключница (на дропе, не в git). `*.env.example` — шаблон.

## Безопасность (важно)
Раннер исполняет **только** задачи из allowlist в `job_runner.py`
(`verify_company`, `ping`) — произвольный shell невозможен, аргументы уходят
скрипту через stdin как JSON. Плюс задания подписаны HMAC (`JOB_SECRET`), чтобы
их нельзя было подсунуть, имея только `DROP_TOKEN`. Добавлять новую задачу =
дописать её в `ALLOW` и задеплоить (осознанное действие, не через дроп).

## Установка (один проход на сервере)

1. Скачать раннер и ключницу с дропа в `C:\sender\server`:
   ```
   cd C:\sender\server
   bash drop_client.sh down runner-secrets.env
   bash drop_client.sh down RUNNER-SETUP.md
   ```
   (файлы `job_runner.py`, `verify_company.py`, `run_on_server.py` уже в репо
   `seo-texts/server/` — либо тоже скачать с дропа из `runner-bundle.tar.gz`.)

2. Вписать в `runner-secrets.env`: `DROP_TOKEN` (тот же, что у drop-службы) и
   **`CAPMONSTER_KEY`** (кабинет capmonster.cloud → API key). `JOB_SECRET` уже
   вписан. `PROVIDER_API_KEY` — если ещё не в env сервера.

3. Поставить службу NSSM (env — из ключницы):
   ```
   nssm install rusprom-runner "C:\Python311\python.exe" "C:\sender\server\job_runner.py"
   nssm set rusprom-runner AppDirectory C:\sender\server
   nssm set rusprom-runner AppEnvironmentExtra ^
     DROP_URL=https://parsercompressor.online/drop ^
     DROP_TOKEN=<...> JOB_SECRET=<...> CAPMONSTER_KEY=<...> ^
     PROVIDER_API_KEY=<...> PROVIDER_BASE_URL=https://router.cheap
   nssm start rusprom-runner
   ```
   (значения удобнее задать через `nssm edit rusprom-runner` вкладка Environment,
   скопировав строки из `runner-secrets.env`.)

4. Проверка: в логе службы должно быть `runner старт: ... подпись=вкл`.

## Как Claude им пользуется (со стороны песочницы)
```
export DROP_URL=... DROP_TOKEN=...          # JOB_SECRET подтянется с дропа
python run_on_server.py ping '{"hi":1}'     # смоук: вернёт {"pong":true,...}
python run_on_server.py verify_company '{"companies":[{"name":"КАО Азот","inn":"4205000908"}]}'
```
Ответ приходит из `result-<id>.json` (клиент сам его читает и удаляет).

## Что проверить на боевом сервере (единожды)
`verify_company._fetch`: путь Cloudflare (обмен токена Turnstile на доступ)
site-specific. На сервере, где сайты реально открываются, прогнать одну компанию
и, если карточка не извлеклась, подкрутить обработку челленджа/селектор источника
(checko/rusprofile). Провайдер извлекает из HTML устойчиво к вёрстке, так что
достаточно, чтобы `_fetch` отдал страницу карточки, а не челлендж.
