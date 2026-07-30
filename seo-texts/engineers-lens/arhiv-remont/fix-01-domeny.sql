-- fix-01-domeny.sql  ---- дефект 1: lstrip("www.") снял ЛЮБЫЕ символы из набора {w, "."}
-- Проверено эмпирически: "water-service.ru".lstrip("www.") == "ater-service.ru", "wtc.ru".lstrip("www.") == "tc.ru", "wa.me".lstrip("www.") == "a.me".
-- Замер: из 2023 непустых master.site и 1604 enrich companies.site НИ ОДИН не начинается на "w" (0 из 3627).
-- Контроль: в независимом корпусе доменов почт той же базы на "w" начинаются 7 из 2300 (0,30%).
-- НИЧЕГО НЕ ВЫПОЛНЕНО. Применять владельцу. Каждый UPDATE защищён старым значением в WHERE (идемпотентен).

BEGIN;

-- 1a. Сайты компаний, восстановленные по названию + живому HTTP-ответу (7 записей).
-- ООО «ВАГЕР»; ager-lg.com не отвечает (000), wager-lg.com 200, <title>Wager — Мы возвращаем воде природную чистоту</title>
UPDATE master   SET site='wager-lg.com' WHERE inn='9402004178' AND lower(trim(site))='ager-lg.com';
UPDATE companies SET site='wager-lg.com' WHERE inn='9402004178' AND lower(trim(site))='ager-lg.com';  -- enrich.db

-- ООО «ВИ ФРАЙ»; собственная почта компании в этой же базе — info@wefry.ru, pro@wefry.ru; efry.ru 000, wefry.ru 200
UPDATE master   SET site='wefry.ru' WHERE inn='4802024211' AND lower(trim(site))='efry.ru';
UPDATE companies SET site='wefry.ru' WHERE inn='4802024211' AND lower(trim(site))='efry.ru';  -- enrich.db

-- ООО «ВЕЛЛ СЕРВИС»; ell-s.ru 000, well-s.ru 200, <title>Велл Сервис — нефтесервисная компания</title>
UPDATE master   SET site='well-s.ru' WHERE inn='7203296941' AND lower(trim(site))='ell-s.ru';
UPDATE companies SET site='well-s.ru' WHERE inn='7203296941' AND lower(trim(site))='ell-s.ru';  -- enrich.db

-- ООО «ВЭЛЛ ТЕХНОЛОДЖИ»; почта svetlana.lanina@welltechnology.com в этой же базе; elltechnology.com 000, welltechnology.com 200 <title>Well Technology</title>
UPDATE master   SET site='welltechnology.com' WHERE inn='8905062618' AND lower(trim(site))='elltechnology.com';
UPDATE companies SET site='welltechnology.com' WHERE inn='8905062618' AND lower(trim(site))='elltechnology.com';  -- enrich.db

-- ООО «ВИКОНА»; ikona.ru 200 — ЧУЖОЙ магазин резных икон, wikona.ru 200 <title>ВИКОНА — Профессиональные протирочные материалы</title>
UPDATE master   SET site='wikona.ru' WHERE inn='7709379215' AND lower(trim(site))='ikona.ru';
UPDATE companies SET site='wikona.ru' WHERE inn='7709379215' AND lower(trim(site))='ikona.ru';  -- enrich.db

-- ООО «ВОЛЬФ СИСТЕМ»; olfsystem.ru 000, wolfsystem.ru 200 <title>OOO Wolf System — Ваш специалист в строительстве ангаров</title>
UPDATE master   SET site='wolfsystem.ru' WHERE inn='4011015616' AND lower(trim(site))='olfsystem.ru';
UPDATE companies SET site='wolfsystem.ru' WHERE inn='4011015616' AND lower(trim(site))='olfsystem.ru';  -- enrich.db

-- ООО «ВИНЗАВОД ЮРОВСКИЙ»; ine-shopper.ru 000, wine-shopper.ru отвечает (403 nginx — хост жив)
UPDATE master   SET site='wine-shopper.ru' WHERE inn='2301076247' AND lower(trim(site))='ine-shopper.ru';
UPDATE companies SET site='wine-shopper.ru' WHERE inn='2301076247' AND lower(trim(site))='ine-shopper.ru';  -- enrich.db

-- 1b. Домены, которые после починки оказываются НЕ сайтом компании -> обнулить (5 записей).
-- ООО «САХИБИ»; исходник — web.archive.org, это веб-архив, а не сайт компании (eb.archive.org <- web.archive.org)
UPDATE master    SET site='' WHERE inn='2369001784' AND lower(trim(site))='eb.archive.org';
UPDATE companies SET site='' WHERE inn='2369001784' AND lower(trim(site))='eb.archive.org';  -- enrich.db

-- ООО «ГСП-7»; исходник — wa.me, диплинк WhatsApp, не сайт (в master у этого ИНН правильный сайт gsprom.ru) (a.me <- wa.me)
UPDATE master    SET site='' WHERE inn='7810474812' AND lower(trim(site))='a.me';
UPDATE companies SET site='' WHERE inn='7810474812' AND lower(trim(site))='a.me';  -- enrich.db

-- ООО «РУСАГРО-САРАТОВ»; исходник — wa.me, диплинк WhatsApp (a.me <- wa.me)
UPDATE master    SET site='' WHERE inn='6453163766' AND lower(trim(site))='a.me';
UPDATE companies SET site='' WHERE inn='6453163766' AND lower(trim(site))='a.me';  -- enrich.db

-- ООО «ЛИТ ЭНЕРДЖИ»; исходник — wa.me, диплинк WhatsApp (a.me <- wa.me)
UPDATE master    SET site='' WHERE inn='9709086205' AND lower(trim(site))='a.me';
UPDATE companies SET site='' WHERE inn='9709086205' AND lower(trim(site))='a.me';  -- enrich.db

-- ООО «ТАНАИС СЕМАНС»; исходник — wa.me, диплинк WhatsApp (a.me <- wa.me)
UPDATE master    SET site='' WHERE inn='3620014954' AND lower(trim(site))='a.me';
UPDATE companies SET site='' WHERE inn='3620014954' AND lower(trim(site))='a.me';  -- enrich.db

-- 1c. Контакт, снятый с ЧУЖОГО сайта из-за обрубленного домена. Единственная почта ООО «ВИКОНА»
--     в базе — info@ikona.ru, то есть адрес магазина резных икон. В обзвон её пускать нельзя.
UPDATE master SET best_email='', contacts='' WHERE inn='7709379215' AND best_email='info@ikona.ru';
UPDATE companies SET best_email=NULL WHERE inn='7709379215' AND best_email='info@ikona.ru';  -- enrich.db
DELETE FROM emails WHERE inn='7709379215' AND email='info@ikona.ru';  -- enrich.db

-- 1d. Донорский домен новости: signals.source хранит обрубок, а source_url цел.
--     https://www1.ru/news/... -> lstrip('www.') -> '1.ru'. Единственный такой случай на 194 сигнала.
UPDATE signals SET source='www1.ru' WHERE inn='7706107510' AND source='1.ru';  -- enrich.db

COMMIT;
