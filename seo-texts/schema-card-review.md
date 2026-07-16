# Ревью разметки карточек товара prokompressor.ru

Дата: 2026-07-16. Проверены живые карточки (бустер AIRPOL «по запросу», Atlas Copco XAS 97,
Cross Air Borey 55-7B, турбокомпрессор ТВ-80). Три независимых ревьюера (провайдерский API).

## Google (Rich Results / GSC)

**Главное:** AggregateRating выведен ОТДЕЛЬНЫМ JSON-LD блоком, не привязанным к Product (нет вложенности и нет ссылки @id на товар). Google это считает 'висячим' рейтингом без объекта отзыва: в GSC — ошибка Product snippets/Merchant listings, а отрыв рейтинга от товара — прямой триггер ручной меры за spammy structured data (рейтинг, не относящийся к странице/товару). Чинить в первую очередь.

- Пустая цена на карточках 'цена по запросу': itemprop=price content="" (плюс, судя по всему, нет priceCurrency/availability). Пустой price = невалидный Offer → ошибка 'Missing field price'/'Offer price invalid' в GSC. Для товаров без цены Offer с price лучше вообще не выводить.
- Пустой image (''): для Product это ошибка (image — обязательное поле для товарных сниппетов), в GSC 'Missing field image'.
- Пустой brand (itemprop brand без значения, name='Airpol' болтается рядом): нужно корректно вложить Brand с name='Airpol'; сейчас разметка бренда фактически битая — предупреждение.
- Пустой url ('') у Product — предупреждение 'Missing field url' / некорректная ссылка.
- Смешение форматов: часть данных в microdata (Product), рейтинг в JSON-LD — Google не сшивает их автоматически, из-за чего рейтинг и не подхватывается товаром. Держать всё в одном формате.
- HTML-сущности &#40; &#41; в description вместо скобок — косметика, на валидность не влияет, но чистить стоит.
- Отсутствуют рекомендованные поля Offer (priceCurrency, availability, priceValidUntil) на карточках с ценой — предупреждения Merchant listings.

**Фикс:** В шаблоне Битрикса (component_template catalog.element / bitrix:sale.* ) убрать отдельный JSON-LD c AggregateRating и вкладывать рейтинг прямо в Product-microdata: <div itemprop="aggregateRating" itemscope itemtype="https://schema.org/AggregateRating"><meta itemprop="ratingValue" content="4.2"><meta itemprop="ratingCount" content="82"></div> — выводить ТОЛЬКО когда реально есть отзывы. Бренд: <span itemprop="brand" itemscope itemtype="https://schema.org/Brand"><meta itemprop="name" content="Airpol"></span>. image/url заполнять реальными значениями (?this->__component->arResult['DETAIL_PICTURE']['SRC'] и getServer HTTP_HOST + DETAIL_PAGE_URL), при пустом изображении блок не выводить. Для offers обернуть условием: если цена (arResult['MIN_PRICE']['VALUE'] или PRICE) > 0 — выводить Offer с itemprop price/priceCurrency('RUB')/availability; на 'цена по запросу' Offer и price не рендерить вовсе (иначе content='' даёт ошибку). Проверить итог в Rich Results Test.

## Яндекс.Вебмастер

**Главное:** Рейтинг (AggregateRating) отдан отдельным JSON-LD и никак не связан с Product — для Яндекса это «висячая» сущность, он не привяжет 4.2/82 к товару, и звёзды в сниппете не появятся.

- Пустой image (`itemprop=image` без значения) — для товарного сниппета Яндекса изображение фактически обязательно, без него карточка не формируется как товарное предложение.
- На карточках «цена по запросу» `itemprop=price content=""` — пустой price это невалидный Offer; Яндекс ругается на некорректную цену. Нужно либо убирать Offer целиком, либо давать корректный признак «нет в наличии».
- У Offer не видно priceCurrency и availability — Яндекс требует валюту и статус наличия для товарного предложения.
- Пустой url товара и пустой url бренда (`brand` без name-ссылки, только вложенный `name=Airpol`) — ссылки-заглушки лучше не выводить вообще.
- Смешение microdata (Product) и JSON-LD (рейтинг) на одной карточке — Яндекс склеивает хуже, чем единый блок; надёжнее держать всё в одном формате.
- В `description` остались HTML-энтити (`&#40;` `&#41;`) — в разметку должен идти чистый текст, а не экранированные скобки.

**Фикс:** В Битриксе правь шаблон компонента catalog.element (копия в /local/templates/.../components/bitrix/catalog.element/.../template.php): 1) внеси рейтинг внутрь Product тем же форматом — либо целиком собери товар в JSON-LD с вложенным aggregateRating и offers, либо в microdata добавь `<div itemprop="aggregateRating" itemscope itemtype="https://schema.org/AggregateRating">` внутрь блока Product и выводи ratingValue/reviewCount из свойств; 2) image рендери только при непустом `$arResult['DETAIL_PICTURE']`/DETAIL_TEXT картинки, отдавая абсолютный URL; 3) для Offer выводи `priceCurrency` (RUB) и `availability` (InStock/OutOfStock), а при «цене по запросу» не печатай `itemprop=price` вовсе (или ставь `PreOrder`), убрав пустой content; 4) url бери из `$arResult['DETAIL_PAGE_URL']` и делай абсолютным, brand выводи как отдельный Organization с name только если бренд заполнен; 5) прогони description через что-то вроде `html_entity_decode()`/`strip_tags()` перед выводом. После правок проверь страницы в валидаторе микроразметки Яндекс.Вебмастера.

## Антиспам-асессор

**Главное:** На карточках «цена по запросу» рендерится Offer с itemprop=price content="" (пустая цена) — это невалидный оффер, из-за которого Google/Яндекс не могут построить rich-сниппет и вся структурированная разметка товара считается битой; без валидного price звёзды рейтинга к товару не привяжутся.

- AggregateRating отдается отдельным блоком JSON-LD, не вложенным в Product-микроразметку и без @id/itemref — рейтинг не связан с сущностью товара (orphan-разметка), риск того, что оценка сочтётся неассоциированной/self-serving.
- Пустые обязательные/важные свойства Product: url="", image="", brand="" — снижают качество карточки и мешают валидации.
- Смешение форматов: товар в microdata, рейтинг в JSON-LD — лучше держать всё в одном формате для однозначной привязки.
- Фейковых рейтингов и накрутки не выявлено: 4.2/82 совпадает с видимым блоком отзывов, AggregateRating есть только на карточках с реальными отзывами — манипуляции сниппетом нет.

**Фикс:** В шаблоне компонента catalog.element (.default/template.php) выводить <meta itemprop="price"> и весь itemscope Offer только при непустой цене: if (!empty($arResult['MIN_PRICE']['VALUE']) && $arResult['MIN_PRICE']['VALUE'] > 0) — иначе оффер не рендерить вовсе (для «цена по запросу» без цены оффер не нужен). Заодно перенести AggregateRating внутрь itemscope Product (или задать Product itemid/@id и сослаться из JSON-LD), а пустые url/image/brand либо заполнять из свойств товара, либо не выводить itemprop с пустым content.
