# Патч panel-pager: пейджер во всех списках панели (задача #52)

Владелец: «нужно, я же туда тоже волью всю базу в итоге». Бэкенд-пагинация
(LIMIT ? OFFSET ?) в панели была на всех списках, но фронт грузил одну фикс-порцию
без навигации — после вливания базы списки обрезались бы.

## Что меняется

| Файл | Куда деплоить | Что внутри |
|---|---|---|
| `app.py` | `C:\sender\sender\api\app.py` | + `offset` в роуты `/events` и `/suppression` (store уже умел) |
| `client.ts` | web `src/api/client.ts` | + `offset` в типах фильтров events/suppression/audit/leads |
| `views.tsx` | web `src/screens/views.tsx` | Pager на «Логи событий» и «Suppression» |
| `Recipients.tsx` | web `src/screens/` | Pager с точным total (count.total уже отдаётся) |
| `Leads.tsx` | web `src/screens/` | Pager (страница 100), сброс offset при смене фильтров |
| `admin.tsx` | web `src/screens/` | Pager на «Аудит действий» |

Компонент Pager уже был в ui.tsx редизайна (offset/shown/total, «N-M из K»,
кнопки назад/вперёд) — он просто не был подключён ни к одному экрану.

Очередь подтверждений НЕ трогаем: это карточный конвейер (первое письмо -> решение
-> очередь подтягивается), пейджер там не нужен, счётчик «в очереди N» есть.

Правило сброса: смена любого фильтра возвращает offset в 0 (иначе пустая страница).
Где бэкенд не отдаёт total (events/suppression/leads/audit) — Pager работает в
режиме «вперёд, пока приходит полная страница».

## Деплой
Фронт: собрать web (vite build) и заменить C:\sender\web\dist (бэкап автоматически
в C:\sender\_bak-webdist-*). Бэкенд: заменить api\app.py + Restart-Service SenderPanel.
Выкачено 26.07, смоук: роуты с offset отвечают, фронт 200.
