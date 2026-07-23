# Новостные события -> лиды: полная цепочка (2026-07-23)

Сверено по исходникам news_scan.py / enrich_db.py / enrich_contacts.py / lead_scoring.py /
sender/infopanel.py после правок 2026-07-23 (все задеплоены на сервер).

## Схема

Источники (8 коллекторов) -> дедуп -> капекс-предфильтр -> fable-классификация ->
ИНН (dadata v2 с расклонкой) -> мгновенная запись (news_stream.jsonl + enrich.db) ->
обогащение контактов ВСЕХ лидов -> скоринг -> лид-деск панели.
Потерянные (без ИНН) добирает ингестер ingest_noinn.

## 1. Запуск

- Обычный: run_on_server.py news_scan '{"collectors":[...],"days":90}'
- Sweep: '{"sweep":true,"chain":true,"chunk":120}' - каталог sweep_queries.json с дропа,
  чанками, самочейнинг (преемник пишется в НАЧАЛЕ чанка). Стоп: sweep_stop.flag.
- VK-sweep: отдельная параллельная цепочка, преемник в КОНЦЕ чанка, защита от
  размножения (>=2 vksweep-джобов -> копия не постится). Стоп: vk_sweep_stop.flag.

## 2. Коллекторы

vk(1) | browser/гиперлокал(1) | regional RSS 100+(1/4) | frp(2, бюджет подтверждён) |
zakupki ЕИС(3) | google news(4) | xmlriver Я+G SERP(4, движок свипа) | hh вакансии(5).
Item: {title, link, pubDate, source, tier, collector, query}.

## 3. Фильтры до провайдера

1) дедуп по канон-URL (_norm_url: без utm/yclid/www/якоря; фолбэк домен+заголовок только
   для ссылок без пути); 2) _CAPEX_KW-предфильтр для firehose (regional/google/xmlriver),
   zakupki/hh/frp без фильтра; 3) кросс-чанковый дедуп seen_news в enrich.db.

## 4. Классификация: extract_event, ТОЛЬКО claude-fable-5

(haiku терял 99% событий - инцидент). 12-64 потока. Строгий JSON:
{is_capex, company (ИМЕНИТЕЛЬНЫЙ падеж как в ЕГРЮЛ - правка 2026-07-23), event_type,
what, region, country, sum, hotness 1-5}. Отсев: жильё/дороги/соцобъекты/без компании/не-РФ.

## 5. ИНН: dadata_suggest v2 (2026-07-23)

Эмпирика: dadata НЕ понимает склонения («Северстали» -> пусто). Теперь: варианты
(как есть / ядро из кавычек / без ОПФ+предлогов / расклонка _DECL_SUF) x count=3 ->
матч-скор токенов (префиксы, переживает падежи) -> score=0 = ИНН НЕ приклеивать
(защита от тёзок) -> inn_confidence high/low в лид. + okved/полное имя/статус/регион ->
icp_fit (39 разделов реальной базы) + division (kc/meyer/kc+meyer).

## 6. Запись мгновенно, дуал-сток (_persist_event)

1) news_stream.jsonl append+fsync - ВСЁ, включая без-ИНН;
2) enrich.db: bump_donor(домен) БЕЗУСЛОВНО (все доноры, RSS не обязателен);
   с ИНН: companies upsert + signals(source,event_type,what,sum,source_url,hotness,ts).

## 7. Контакты: ВСЕ лиды (директива владельца 2026-07-23)

enrich_max=0 (без лимита), старый фильтр - опция icp_only. Путь тот же, что обзвон-база:
enrich_one = сайт -> staff-страницы (ФИО+роль+email) -> SERP staff -> справочники без
сайта. У каждого контакта source + source_url. -> emails / best_email в enrich.db.

## 8. Ингестер ingest_noinn (2026-07-23)

enrich_contacts {"op":"ingest_noinn","cap":N,"retry_unresolved":bool}.
jsonl -> дедуп имён -> dadata v2 -> SERP «"имя" ИНН» xmlriver (идея владельца) ->
чексумма ИНН -> верификация findById (матч имени) -> enrich.db. Прогресс durable в
news_stream.jsonl.resolved.

## 9. Потребление

lead_scoring.py: сигнал(свежесть) + выручка + verified + ЛПР + budget_confirmed(ФРП/ОЭЗ).
infopanel.py лид-деск: сигналы по ИНН, звёзды hotness, кликабельный source_url, контакты.

## 10. Ручки

days, max_items, collectors, queries, enrich, enrich_max(0=все), icp_only,
provider_workers, xmlriver_g/y_workers, extract_model, vk_count, chunk/offset, write_db.

## Слабости / план

- hh без привязки к оборудованию (в работе: вакансии операторов компрессоров).
- Автопетли донор->новый фид нет (по слову владельца: копим все, механику потом).
