# Спека: канал уведомлений Max (VK Мессенджер) рядом с Telegram

Решение владельца 2026-07-20: сервер в РФ, `api.telegram.org` с серверного IP
режется. Нужен второй канал — **Max (МАКС, мессенджер VK)**, который в РФ работает
нативно (без VPN/прокси). Telegram остаётся (через `HTTPS_PROXY`), Max — основной
для РФ-сервера.

## Что реализовать

1. **`MaxSink`** — отправитель по Max Bot API, тот же интерфейс, что у Telegram в
   `notify.py` (`_send_telegram` → аналог `_send_max`). Max Bot API — на платформе
   бывш. TamTam (VK); ⚠️ **эндпоинты/схему сверить с актуальной докой Max Bot API**
   при реализации (не хардкодить по памяти): base URL, метод отправки сообщения,
   формат авторизации (обычно `?access_token=<TOKEN>`), поле `chat_id`.
2. **Конфиг** (`notify` секция):
   ```yaml
   notify:
     channel: max            # telegram | max | both  (по умолчанию telegram)
     token_env: TELEGRAM_BOT_TOKEN
     ops_chat_id: "..."          # telegram chat_id
     max_token_env: MAX_BOT_TOKEN
     max_ops_chat_id: "..."      # max chat_id
   ```
   `Notifier.__init__` читает `channel`; `notify()` шлёт в выбранный(е) канал(ы).
   Обратная совместимость: без `channel` → как сейчас (только telegram).
3. **Прокси для Telegram** (уже работает через `HTTPS_PROXY` в urllib) — не ломать;
   Max ходит напрямую (РФ), Telegram — через прокси, независимо.
4. **Дебаунс/тихие часы/приоритеты (P1-P3)** — общие для обоих каналов
   (не дублировать логику, вынести из `_send_telegram`).

## Тесты
- `MaxSink` шлёт (мок HTTP), при channel=max Telegram НЕ дёргается;
- channel=both → оба; channel отсутствует → только telegram (совместимость);
- сетевая ошибка одного канала не роняет второй;
- дебаунс общий (одно событие не уходит дважды в один канал).

## От владельца
- Создать Max-бота, получить `MAX_BOT_TOKEN` (аналог BotFather у Max) и `max_ops_chat_id`
  (добавить бота в чат/группу, узнать chat_id). Инструкцию соберём отдельно, как для Telegram.
