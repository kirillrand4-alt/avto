-- fix-02-proveniens.sql  ---- дефект 2: тонкий источник контакта затёрт тегом задания
-- Замер по enrich.db: 1515 записей emails, source = mass 1107 (73,1%), roletext 226 (14,9%),
-- enrich-500-retry 94, enrich-500-markup 87, enrich-batch-1 1. Значений own-site:* и egrul:* — 0 из 1515.
-- Восстановить из source_url НЕЛЬЗЯ: в таблице emails такой колонки нет вовсе
-- (колонки: inn, email, role, person, mx_ok, source, updated_at). source_url есть только в signals.
-- Восстановимо ЧАСТИЧНО и только грубо — по совпадению домена почты с доменом сайта компании:
--   917 из 1515 (60,5%) при сравнении с допуском на поддомены, 598 (39,5%) не восстановимо
--   (307 — домен почты не совпал с сайтом, 291 — бесплатный почтовик).
-- ФАКТ ЭТОГО ФАЙЛА, сухой прогон на копии базы 30.07: 881 own-site:domain-match + 291
-- unknown:free-mailbox + 343 unknown:lost-by-tag-overwrite = 1 515, ровно все записи.
-- Разница с 917 — 36 записей, где домен почты поддомен домена сайта или наоборот,
-- простое сравнение ниже их не ловит, они уезжают в lost-by-tag-overwrite.
-- ВАЖНО: own-site:domain-match НЕ равно own-site:staff. Он говорит «адрес в домене компании»,
-- а не «взят со страницы сотрудников». Поэтому пишем в ОТДЕЛЬНУЮ колонку, а source не трогаем.
-- ПОРЯДОК ВАЖЕН: если fix-01 применён раньше, разметка даёт 882 / 291 / 341 = 1 514,
-- потому что fix-01 удаляет отравленный контакт info@ikona.ru и правит семь доменов сайтов.
-- Оба расклада проверены сухим прогоном, ошибок 0.
-- НИЧЕГО НЕ ВЫПОЛНЕНО.

BEGIN;

ALTER TABLE emails ADD COLUMN source_fine TEXT;   -- если колонка уже есть — строку пропустить

-- 881 запись: домен почты совпал с доменом сайта компании
UPDATE emails SET source_fine='own-site:domain-match' WHERE source_fine IS NULL AND inn IN (SELECT inn FROM companies WHERE trim(coalesce(site,''))<>'')
  AND ( lower(substr(email, instr(email,'@')+1)) = lower(replace(replace((SELECT site FROM companies c WHERE c.inn=emails.inn),'https://',''),'http://','')) );

-- 291 запись: бесплатный почтовик — источник принципиально не восстановим, помечаем честно
UPDATE emails SET source_fine='unknown:free-mailbox' WHERE source_fine IS NULL AND lower(substr(email, instr(email,'@')+1)) IN ('bk.ru','gmail.com','icloud.com','inbox.ru','internet.ru','list.ru','mail.com','mail.ru','narod.ru','outlook.com','rambler.ru','ya.ru','yahoo.com','yandex.com','yandex.ru');

-- остальные 343: источник потерян безвозвратно
UPDATE emails SET source_fine='unknown:lost-by-tag-overwrite' WHERE source_fine IS NULL;

COMMIT;

-- Проверка после применения: должно дать РОВНО 881 / 291 / 343, сумма 1 515.
-- SELECT source_fine, COUNT(*) FROM emails GROUP BY 1,
