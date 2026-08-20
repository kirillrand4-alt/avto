# Здоровье акцепторов: проверка перед закупкой (20.08.2026)

Проверил все 24 уникальных URL, на которые ведут ссылки волны. Проверка нужна была
не из осторожности: в одной статье ссылка вела на страницу, которой не существовало
(это ловили раньше), а модель однажды выдумала характеристики моделей, которые
читатель сверил бы по нашей же ссылке. Здесь то же самое, но про сами страницы.

## Итог

| Домен | Ссылок | Отдают 200 | В карте сайта |
|---|---|---|---|
| prokompressor.ru | 9 | 7 | **4 из 9** |
| enger-air.ru | 5 | 5 | 5 из 5 |
| berg-compressor.com | 3 | 3 | 3 из 3 |
| dali-kompressor.ru | 2 | 2 | 2 из 2 |
| ac-kompressor.ru | 2 | 2 | 2 из 2 |
| abac-kompressor.ru | 1 | 1 | 1 из 1 |

Спутники чистые. Все вопросы - к основному домену.

## Что требует твоего решения

### 1. Две страницы отдают антибот-заглушку вместо контента

```
403  https://prokompressor.ru/catalog/vozdushnye-kompressory/promyshlennye/
403  https://prokompressor.ru/catalog/vozdushnye-kompressory/atlas-copco/
```

Отдаётся страница «Проверка браузера» на nginx перед Битриксом. Проверил шесть раз
за десять минут, с обычным браузерным User-Agent, с Referer, с куками - стабильно 403.
Соседние страницы того же раздела в те же секунды отдают 200, так что это не блокировка
по адресу и не рейт-лимит, а правило именно на эти два пути.

**Почему это важно сейчас.** Если Googlebot получает ту же заглушку, страница
не индексируется, и ссылка, за которую мы заплатим, ведёт в никуда: вес не передаётся,
акцептор не растёт. Проверить это могу только я снаружи и без ответа - **посмотри
в Search Console** статус этих двух URL (проверка URL → «Проверить страницу
на сайте»). Ты владелец сайта, у тебя ответ будет точный.

Ссылки на эти страницы стоят в двух статьях:

| Статья | Донор | Целевая страница |
|---|---|---|
| `tsitaty-o-masterstve-i-professionalizme` | citaty.info | `/vozdushnye-kompressory/promyshlennye/` |
| `kak-delayut-veshchi-udivitelnye-fakty-proizvodstva` | twizz.ru | `/vozdushnye-kompressory/atlas-copco/` |

**Менять цель я не стал** - это решение по стратегии кампании, страницы и якоря
ты выбирал осознанно. Если Search Console покажет, что страницы не краулятся, скажи -
подменю URL и подгоню якорь под новую страницу за одну команду. Ближайшие живые
замены по смыслу: `/catalog/vozdushnye-kompressory/po-tipu/vintovye/` для первой,
`/catalog/vozdushnye-kompressory/po-tipu/vintovye/elektricheskie_1/` для второй.

### 2. Пять страниц отсутствуют в карте сайта

```
/catalog/azotnye-stantsii/
/catalog/kislorodnye-stantsii/
/catalog/kompressornye-stantsii-szhatogo-vozdukha/mks/
/catalog/vozdushnye-kompressory/atlas-copco/
/catalog/vozdushnye-kompressory/promyshlennye/
```

Карта `prokompressor.ru/sitemap.xml` - индекс из 19 вложенных файлов, всего 29 379 URL.
Этих пяти в них нет.

Само по себе это не приговор: **проверил, все пять слинкованы с главной страницы
и с каталога**, то есть Google их найдёт обходом. Но карта сайта - это ещё и сигнал
приоритета, и для страниц, под которые мы покупаем ссылки, попасть в неё стоит.
Работа на стороне сайта, не на стороне статей.

## Как перепроверить

```bash
cd seo-texts/guest-posts
JOBS_MODULE=wave-jobs python3 -c "
from gen_wave import JOBS
for j in JOBS:
    for u,_ in j['links']: print(u)" | sort -u | while read u; do
  echo "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -L "$u")  $u"
done
```
