# Паритет CLI ↔ веб-панель (ENGINEER-TASKS-CONFIRM-SEND, Задача 4)

Требование владельца: код (CLI на C:\sender) и веб-версия умеют одно и то же.
Принцип закрытия: обе версии — ПРЕДСТАВЛЕНИЯ над общим бекендом
(`wiring.build_deps`: store/suppression/sender/confirm/...). Логика в модулях,
CLI и API её не дублируют.

Тест паритета: `tests/test_confirm_parity.py` — один сценарий калибровки
(approve + edit + stoplist «конкурент») прогоняется через CLI-команды и через
HTTP API; нормализованные дампы состояния (reviews/messages/suppression)
обязаны совпасть байт в байт. Заслон подтверждения виден одинаково
(веб 409 ↔ CLI rc=2).

## Инвентаризация (2026-07-22)

| Возможность | CLI | Веб (API) | Статус |
|---|---|---|---|
| Инициализация БД | `init-db` | автоматически при старте | ✅ паритет |
| Импорт получателей CSV | `import` | `POST /recipients/import` (+прогресс) | ✅ |
| Импорт suppress-списка | `suppress-import` | — (только просмотр/снятие) | ⚠ расхождение: массовый импорт стоп-листа только в CLI (осознанно: разовая операция инженера; в панели есть просмотр `GET /suppression` и снятие с аудитом) |
| Валидация email | `validate` | — | ⚠ только CLI (фоновый процесс; в панели статусы видны через `/recipients`) |
| Кампания: создать/шаг/статус | `campaign-*` | `POST /campaigns`, `/steps`, `/status` | ✅ |
| Запуск оркестратора | `run` | — намеренно (⛔ холд; запуск волны из браузера запрещён решением SITE-DESIGN) | ✅ осознанное различие |
| Статус ящиков/кампаний | `status` | `/mailboxes/readiness`, `/campaigns`, `/warmup` | ✅ |
| Пауза/резюм | `pause`/`resume` | гейты автоматом + `campaigns/{id}/status` | ⚠ ручная пауза ЯЩИКА из панели отсутствует (беклог) |
| Статистика | `stats` | `/analytics/*`, `/capacity` | ✅ |
| Пользователи | `user-create`, `user-rotate-2fa` | `POST /users`, activate/deactivate | ✅ (rotate-2fa только CLI — секрет не должен ходить через браузер, осознанно) |
| **Confirm: очередь** | `confirm-queue` | `GET /confirm/queue` | ✅ общий `confirm.pending()` |
| **Confirm: инфо-панель** | `confirm-show` (текстовый рендер ТЕХ ЖЕ JSON-полей; `--json` — сырые) | `GET /confirm/{id}` + экран SPA | ✅ один `build_panel()` |
| **Confirm: решения** | `confirm-decide approve/edit/skip/stoplist` | `POST /confirm/{id}/decision` | ✅ общий `ConfirmSend` |
| **Confirm: интерактивная калибровка** | `confirm-run` (клавиши Enter/e/s/x) | экран Confirm SPA (хоткеи Enter/E/S/X) | ✅ |
| **Confirm: золотые пары** | `confirm-golden` | `GET /confirm/golden` | ✅ |
| История контактов (send_log) | в панели письма (`confirm-show`) | в JSON панели + экран | ✅ |
| Стоп-лист из калибровки | `confirm-decide stoplist` | `decision stoplist` | ✅ + suppression един |

Расхождения ⚠ выше оставлены сознательно (характер операции), зафиксированы
здесь, чтобы не считались молчаливым дрейфом. Всё из пункта «Confirm» ходит
через ОДИН модуль `sender/confirm.py` + `sender/infopanel.py`.
