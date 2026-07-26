# deploy/ — артефакты развёртывания веб-панели (Фаза 2.3)

Конфиги для публикации сайта панели (`sender/web` SPA + FastAPI `serve-api`).
Полная пошаговая инструкция — в `../RUNBOOK-DEPLOY.md` §7.

Отдельная тема — 301-редиректы доменов-двойников рассылки:
`redirects-nginx.conf` (генерённый) + ранбук `REDIRECTS-RUNBOOK.md`.

## Две топологии

**Linux (nginx + systemd) — рекомендуется:**
- `nginx-panel.conf` — TLS-терминация, отдаёт статику `web/dist`, проксирует `/api` →
  `127.0.0.1:8090`. `serve-api` при этом БЕЗ `--static-dir` (API в корне; nginx срезает
  `/api` трейлинг-слэшем в `proxy_pass`, как dev-прокси Vite).
- `rusprom-sender-panel.service` — systemd-юнит для `serve-api` на localhost:8090.
- `panel.env.example` — шаблон env (SENDER_CONFIG + секреты; скопировать в `panel.env`,
  заполнить, `chmod 600`, НЕ коммитить).

**Windows (NSSM + IIS/ARR) — как движок в RUNBOOK §3.1/§4:**
- `nssm-panel-install.ps1` — служба `serve-api --static-dir web\dist` (сайт+API одним
  процессом), публикация через IIS+ARR/Cloudflare для TLS.

## Режим «сайт+API одним процессом» (`--static-dir`)

`python -m sender serve-api --static-dir <путь к web/dist>` — uvicorn раздаёт и SPA, и
API под `/api`, с client-side-fallback (перезагрузка на `/campaigns/5` не даёт 404).
Удобно для стейджинга/смоука без обратного прокси и для Windows. В проде за TLS всё
равно ставят nginx/IIS. Реализация — `make_site_app` в `sender/api/app.py`.

## Перед первым запуском

1. Собрать SPA: `cd web && npm ci && npm run build` → `web/dist`.
2. Поставить API-зависимости в venv: `pip install -r ../requirements-dev.txt`.
3. Создать owner'а: `python -m sender user-create --username <login> --role owner`
   (пароль — через env `SENDER_NEW_USER_PASSWORD`, не в командной строке).
4. Панель — внутренний инструмент 28 продажников: ограничьте доступ офисной сетью/VPN
   (блок `allow/deny` в nginx или правило IIS/файрвола). Публично не выставлять.

Плейсхолдеры (`panel.example.ru`, пути `/opt/rusprom-sender`, `C:\sender`) — заменить
под свой домен и раскладку.
