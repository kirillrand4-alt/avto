# Панель: фиксы UX/безопасности отправки + DKIM-чекер (2026-07-24)

Правки поверх ветки инженера `claude/persona-prompt-seo-sender-vi4tcq`
(HEAD `3c705e4`). Собрано в `panel-update.zip`, развёрнуто через дроп-раннер
(`op panel_zip_deploy`); фронт пересобран в песочнице (`npm run build`).
Все тесты: **955 passed** (953 инженера + 2 новых A4).

## Что и почему

### A1–A3. Одиночный Enter больше не отправляет письмо — `Confirm.tsx`
Раньше глобальный оконный хоткей `Enter` = approve. В live-режиме случайный
Enter (или связка «Enter подтвердил стоп-флаг → Enter отправил») пробивал
предупреждение и слал реальное письмо, в т.ч. на конкурента/mismatch. Теперь:
- отправка только по **Ctrl/Cmd+Enter** и без автоповтора (`e.repeat`);
- из хоткеев исключены `SELECT` и `contentEditable` (смена получателя не шлёт).

### A4. Повторный approve не отправляет письмо второй раз — `confirm.py` + `store.py`
`_send_live` мог отправить дважды (повторный клик / гонка двух параллельных
approve: оба видели `pending`). Добавлен атомарный захват:
- `store.confirm_claim_sending(id)` — `UPDATE ... SET status='sending_live'
  WHERE id=? AND status='pending'`; `rowcount==1` = захватили, иначе False;
- `_send_live` захватывает перед SMTP, при сбое `confirm_release_sending`
  возвращает в `pending` (письмо не теряется, второй раз не уходит);
- `confirm_decide` принимает решение и из `sending_live`.
Тесты: `test_live_approve_sends_once_and_second_is_blocked` (первый approve =
1 SMTP, второй = ConfirmBlockedError, счётчик отправок остался 1);
`test_live_claim_blocks_concurrent` (второй claim = False, release возвращает).

### B1. Пустая инфо-панель не роняет экран «Подтвердить» — `Confirm.tsx`
Исходящее без `panel.contact/company/compliance` (напр. ИНН не из enrich)
раняло весь React-экран (белый экран у оператора). Добавлены `if (!c) return
null` в `ContactCard`/`CompanyCard`/`ComplianceCard` + `(c.banned_phrases ||
[])`. Карточка без данных просто не рисуется — остальной экран жив.

### DKIM. Ложный крестик у mail.ru-доменов — `dns.py`
Панель проверяла селекторы `[mail, default, dkim, mx]`, а VK WorkMail
(mail.ru) публикует DKIM на селекторе **`mailru`** (`mailru._domainkey.<домен>`,
проверено DoH: записи есть и валидны). Добавлен `mailru` в
`_DEFAULT_DKIM_SELECTORS` — крестик у kompressor-air-expert.ru /
kompressor-expert.ru / compressor-store.ru станет галочкой.

## Также в этой поставке (из отдельного фикса)
- confirm-очередь: оркестратор кладёт исходящие в pending_review (не шлёт
  напрямую) — `sender-patches/CONFIRM-QUEUE-FIX.md`;
- `store.confirm_golden` по `edited_body IS NOT NULL` (live-правки не теряются).
