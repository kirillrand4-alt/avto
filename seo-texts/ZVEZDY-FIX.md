# Починка «звёзд» (AggregateRating) на карточках: инструкция для шаблона

Дата: 2026-07-16. Диагностика по живой карточке
`/catalog/kompressor-porshnevoy-dozhimnoy-buster-airpol-adp-720-4-13/`
(бустер AIRPOL, «цена по запросу», рейтинг виджета 4.2, 82 голоса).

## Что сейчас в коде (факт)

1. Карточка обёрнута в микроданные Product - и это ХОРОШО, каркас уже есть:

```html
<div class="product-container catalog_detail js-notice-block detail element_3 clearfix"
     itemscope itemtype="http://schema.org/Product">
  <meta itemprop="name" content="Компрессор поршневой дожимной (бустер) AIRPOL ADP 720/4/13" />
  <link itemprop="url" href="/catalog/kompressor-porshnevoy-dozhimnoy-buster-airpol-adp-720-4-13/" />
  <meta itemprop="sku" content="282615" />
  <link href="/upload/iblock/c76/t3a3628an7lytm78cu0zqftu6zac17yi.png" itemprop="image"/>
  ... (Brand, countryOfOrigin, Offer - тоже внутри)
</div>
```

2. А рейтинг («звёзды» виджета `votes_block nstar` в `product-info-headnote__rating`)
   выводит РЯДОМ отдельный, ни к чему не привязанный JSON-LD - Google его игнорирует
   и ругается в GSC:

```html
<script type="application/ld+json">
{ "@context": "https://schema.org", "@type": "AggregateRating",
  "ratingValue": "4.2", "ratingCount": "82", "bestRating": "5", "worstRating": "1" }
</script>
```

3. На товарах «цена по запросу» рендерится Offer с пустой ценой -
   `<meta itemprop="price" content="" />` - невалидный оффер.

Важно: виджет звёзд ФИЗИЧЕСКИ находится внутри div-а Product (проверено по DOM).
Поэтому чинится микроданными на месте, без единого JSON-LD.

## Фикс 1: привязать рейтинг к товару (~20 минут)

**Где:** файл, который генерит этот JSON-LD. Ищи по коду проекта:
`grep -r "AggregateRating" /home/bitrix/www/bitrix/templates/aspro_max/ /home/bitrix/www/local/`
- это шаблон блока голосования Aspro (рядом будет класс `votes_block nstar`).
Обычно: `aspro_max/components/.../include/element/rating.php` или include-область
шаблона catalog.element.

**Шаг 1.** Удалить весь блок `<script type="application/ld+json">{...AggregateRating...}</script>`.

**Шаг 2.** В обёртку виджета добавить микроданные (значения берутся из тех же
переменных, из которых сейчас печатается JSON-LD - средний балл и число голосов
уже есть в этом файле):

```html
<!-- КАК ДОЛЖНО БЫТЬ (живой пример для бустера AIRPOL): -->
<div class="product-info-headnote__rating">
  <?if ($votesCount > 0):?>
  <div class="rating" itemprop="aggregateRating" itemscope
       itemtype="https://schema.org/AggregateRating">
    <meta itemprop="ratingValue" content="4.2" />
    <meta itemprop="ratingCount" content="82" />
    <meta itemprop="bestRating" content="5" />
    <meta itemprop="worstRating" content="1" />
    <!-- ...существующая вёрстка звёздочек не меняется... -->
  </div>
  <?endif;?>
</div>
```

(в реале вместо 4.2/82 - `<?=$avgRating?>` / `<?=$votesCount?>` из виджета)

**Почему это работает:** div виджета лежит внутри `div[itemscope Product]`,
поэтому `itemprop="aggregateRating"` автоматически прицепляется к товару.
Ничего больше связывать не надо.

**Условие `$votesCount > 0` обязательно:** карточка без голосов не должна
выводить рейтинг вовсе - пустые/клонированные рейтинги ловят ручные меры.

## Фикс 2: Offer без пустой цены (~15 минут)

**Где:** шаблон catalog.element (там, где сейчас печатается
`<meta itemprop="price" content="...">`, поиск по `itemprop="price"`).

```php
<?if (!empty($arResult['MIN_PRICE']['DISCOUNT_VALUE']) && $arResult['MIN_PRICE']['DISCOUNT_VALUE'] > 0):?>
  <span itemprop="offers" itemscope itemtype="https://schema.org/Offer">
    <meta itemprop="price" content="<?=$arResult['MIN_PRICE']['DISCOUNT_VALUE']?>" />
    <meta itemprop="priceCurrency" content="RUB" />
    <link itemprop="availability" href="https://schema.org/InStock" />
    <link itemprop="url" href="<?=$arResult['DETAIL_PAGE_URL']?>" />
  </span>
<?endif;?>
```

Живой пример результата для карточки С ценой (Atlas Copco XAS 97 Dd, 1 250 500 ₽):

```html
<span itemprop="offers" itemscope itemtype="https://schema.org/Offer">
  <meta itemprop="price" content="1250500" />
  <meta itemprop="priceCurrency" content="RUB" />
  <link itemprop="availability" href="https://schema.org/InStock" />
  <link itemprop="url" href="/catalog/dizelnyy-kompressor-atlas-copco-xas-97-dd/" />
</span>
```

Для «цены по запросу» (наш бустер) - **Offer не выводится вообще**. Product без
offers валиден (будет предупреждение «missing offers» - это нормально и
безопасно, в отличие от пустой цены, которая ломает сниппет целиком).

## Фикс 3 (фаза 2, желательно): текстовые отзывы в разметку

На вкладке «Отзывы» карточки есть реальные отзывы - разметить каждый внутри
того же Product (шаблон вкладки отзывов Aspro):

```html
<div itemprop="review" itemscope itemtype="https://schema.org/Review">
  <meta itemprop="author" content="Сергей, г. Пермь" />
  <meta itemprop="datePublished" content="2026-05-14" />
  <div itemprop="reviewBody">Взяли бустер под выдув ПЭТ, полгода без нареканий...</div>
  <div itemprop="reviewRating" itemscope itemtype="https://schema.org/Rating">
    <meta itemprop="ratingValue" content="5" />
  </div>
</div>
```

2-3 отзывов достаточно. Google требует, чтобы отзывы были видимы на странице -
они видимы (вкладка), так что просто добавить itemprop-атрибуты в существующую
вёрстку вкладки.

## После правок

1. Сбросить кэш: виджет сидит в композитном кэше
   (`start_frame_cache_dv_...`) - «Настройки > Композитный сайт > Сбросить кэш»
   + обычный кэш компонентов.
2. Проверить карточку в Rich Results Test (search.google.com/test/rich-results):
   должен появиться Product с рейтингом БЕЗ ошибок «itemReviewed».
3. Валидатор Яндекса (webmaster.yandex.ru > Инструменты > Валидатор микроразметки).
4. Через 2-4 недели в GSC: «Вид в поиске > Описания товаров» - рост числа
   запросов (сейчас 909 за 3 мес); «Фрагменты отзывов» - рост показов
   (сейчас 52.7 тыс./год, CTR по артикульным запросам со звёздами 8-10%).

## Чего НЕ делать

- Не выводить одинаковый рейтинг (4.2/82) на всех карточках - только реальные
  голоса конкретного товара, иначе снимут звёзды по всему сайту.
- Не добавлять aggregateRating на категории/листинги - Google звёзды на
  CollectionPage не показывает, а Яндекс может счесть спамом.
- Не дублировать рейтинг и в JSON-LD, и в микроданных - оставить ОДИН формат
  (микроданные, раз каркас уже на них).
