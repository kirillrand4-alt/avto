# Что заполнить, чтобы в выдаче появилось «В наличии»

Порядок важен: пункт 1 - единственное, что сейчас реально блокирует наличие.
Пункты 2-4 - требования merchant listing, они улучшают товарный сниппет,
но без пункта 1 не дадут ничего.

## 0. Что уже работает

Цену Google по карточкам показывает (`450 573,00 ₽` в выдаче по
`…bez-n-ce-fm/`), рейтинг тоже. Значит товарный сниппет вы получаете и
канал открыт. Не хватает одной строки - наличия.

## 1. availability - главное поле

Сейчас в разметке уходит `https://schema.org/OutOfStock` на карточках,
где `CAN_BUY: 'Y'` и живая цена. Google печатает то, что ему сказали:
о товаре «нет в наличии» строку наличия он не покажет никогда.

Допустимые значения (полный URL или короткая форма):

| Значение | Когда ставить |
|---|---|
| `https://schema.org/InStock` | есть на складе, отгружаем сразу |
| `https://schema.org/PreOrder` | принимаем заказ, товар ещё не выпущен/не пришёл |
| `https://schema.org/BackOrder` | заказан у поставщика, отгрузка после поступления |
| `https://schema.org/LimitedAvailability` | остаток ограничен |
| `https://schema.org/OutOfStock` | купить нельзя |
| `https://schema.org/Discontinued` | снят с производства |
| `https://schema.org/SoldOut` | распродан |

Строку «В наличии» в сниппете даёт только `InStock`.

Откуда брать в Битриксе (сейчас, судя по всему, берётся только остаток):

```php
$canBuy = $arResult['CAN_BUY'] === 'Y';                       // покупка разрешена
$trace  = $arResult['CATALOG_QUANTITY_TRACE'] === 'Y';        // ведётся ли учёт
$qty    = (float)$arResult['CATALOG_QUANTITY'];               // остаток

!$canBuy            -> OutOfStock
$trace && $qty > 0  -> InStock
!$trace             -> InStock      // учёт не ведётся, но купить можно
иначе               -> PreOrder     // учёт есть, остаток 0, покупка разрешена
```

Обязательное условие: то же самое должно быть видно на странице.
Если разметка говорит `InStock`, на карточке должен стоять статус наличия -
сейчас на «нулевых» карточках его нет вообще.

## 2. Идентификатор товара

Google сопоставляет товар со своим каталогом по идентификаторам. Сейчас
уходит только `sku` = внутренний ID Битрикса (`249365`) - для Google это
ничего не значащее число.

| Поле | Что писать | Обязательность |
|---|---|---|
| `mpn` | заводской артикул производителя: `G15 10P/400V CE TM`, `ВК-4Р-10-IP54`. Из свойства `CML2_ARTICLE`/`ARTICLE` | ставить всегда, когда есть |
| `gtin13` | штрихкод EAN-13, ровно 13 цифр | только если реально есть |
| `sku` | ваш внутренний код, можно оставить как есть | необязательно |
| `brand.name` | `Atlas Copco`, `BERG` | обязательно вместе с `mpn` |

Для промышленного оборудования GTIN обычно не существует - тогда работает
связка `brand` + `mpn`. Выдумывать штрихкод нельзя.

## 3. hasMerchantReturnPolicy - условия возврата

Кладётся внутрь `offers`.

```json
"hasMerchantReturnPolicy": {
  "@type": "MerchantReturnPolicy",
  "applicableCountry": "RU",
  "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
  "merchantReturnDays": 14,
  "returnMethod": "https://schema.org/ReturnByMail",
  "returnFees": "https://schema.org/ReturnFeesCustomerResponsibility"
}
```

Значения `returnPolicyCategory`:
- `MerchantReturnFiniteReturnWindow` - возврат в течение N дней (тогда нужен `merchantReturnDays`);
- `MerchantReturnUnlimitedWindow` - без ограничения срока;
- `MerchantReturnNotPermitted` - возврат не принимается (для B2B-поставок это
  нормальное честное значение).

`returnMethod`: `ReturnByMail`, `ReturnInStore`, `ReturnAtKiosk`.
`returnFees`: `FreeReturn`, `ReturnFeesCustomerResponsibility`,
`ReturnShippingFees` (тогда добавляется `returnShippingFeesAmount`).

Важно: страницы с условиями возврата на сайте сейчас нет (`/help/return/`
отдаёт 404). Сначала опубликовать условия, потом размечать - разметка должна
повторять опубликованное.

## 4. shippingDetails - условия доставки

Тоже внутрь `offers`.

```json
"shippingDetails": {
  "@type": "OfferShippingDetails",
  "shippingRate": { "@type": "MonetaryAmount", "value": 0, "currency": "RUB" },
  "shippingDestination": { "@type": "DefinedRegion", "addressCountry": "RU" },
  "deliveryTime": {
    "@type": "ShippingDeliveryTime",
    "handlingTime": { "@type": "QuantitativeValue", "minValue": 1, "maxValue": 3,  "unitCode": "DAY" },
    "transitTime":  { "@type": "QuantitativeValue", "minValue": 1, "maxValue": 14, "unitCode": "DAY" }
  }
}
```

`handlingTime` - от оплаты до отгрузки, `transitTime` - время в пути.
По вашей странице `/help/delivery/` доставка идёт транспортными компаниями
по их тарифу, фиксированной ставки нет. Поставить `value: 0` можно только
если доставка действительно бесплатная. Пока тарифа нет - блок лучше не
выводить: поле рекомендованное, а неверная цифра хуже отсутствия.

## 5. Старая цена (скидка)

Битрикс отдаёт обе: `VALUE` = 502 626 (базовая), `DISCOUNT_VALUE` = 473 798
(к оплате). В `price` идёт цена к оплате, базовая размечается отдельно:

```json
"priceSpecification": {
  "@type": "UnitPriceSpecification",
  "priceType": "https://schema.org/ListPrice",
  "price": 502626,
  "priceCurrency": "RUB"
}
```

Перечёркнутую цену в обычной выдаче Google не рисует - это для корректности
данных и Shopping-поверхностей.

## Итоговый блок целиком

```json
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Винтовой компрессор ATLAS COPCO G15 10P/400В 3ф 50 Гц без N/CE FM",
  "url": "https://prokompressor.ru/catalog/vintovoy-kompressor-atlas-copco-g15-10p-400v-3f-50-gts-bez-n-ce-fm/",
  "description": "Винтовой компрессор ATLAS COPCO G15 10P/400В 3ф 50 Гц без N/CE FM (1750 л/мин, 10 бар, 15 кВт)",
  "image": "https://prokompressor.ru/upload/iblock/354/n2jvhafsc5zkh51ht955zl2vml4rpby7.jpeg",
  "brand": { "@type": "Brand", "name": "Atlas Copco" },
  "sku": "267350",
  "mpn": "G15 10P/400V CE FM",
  "offers": {
    "@type": "Offer",
    "price": 450573,
    "priceCurrency": "RUB",
    "availability": "https://schema.org/InStock",
    "itemCondition": "https://schema.org/NewCondition",
    "priceValidUntil": "2027-09-04",
    "url": "https://prokompressor.ru/catalog/vintovoy-kompressor-atlas-copco-g15-10p-400v-3f-50-gts-bez-n-ce-fm/",
    "seller": { "@type": "Organization", "name": "ООО «Руспром»" },
    "hasMerchantReturnPolicy": { "...": "см. п.3" },
    "shippingDetails": { "...": "см. п.4" }
  }
}
```

Готовая сборка этого блока из данных Битрикса: `bitrix-product-schema.php`
(подключается в `template.php` компонента `catalog.element`).

## 6. Пошагово: как получить плашку «185 070,00 ₽ · В наличии · 5,0 (1)»

Такую плашку даёт **merchant listing** - товарный результат для страниц,
где покупатель может купить товар. Рутектор её получает, потому что это
обычный магазин с корзиной и оформлением заказа.

Проверка карточки `/catalog/vintovoy-kompressor-remeza-vk5t-10/`:

| | |
|---|---|
| `availability` | `InStock` - **верно** |
| цена | 305 619 ₽, видна на странице |
| статус на странице | «Есть в наличии» - виден |
| кнопка покупки | **нет**: «Получить КП», «Оставить заявку на лизинг» |
| корзина | отключена: блоки `*basket*` в composite-кэше пустые (`d41d8cd98f00` = md5 пустой строки), ссылок на `/personal/cart` и `/order` нет |

То есть разметка наличия на этой карточке уже правильная. Не хватает не
полей, а самого признака магазина: купить товар на странице нельзя.

### Шаг 1. Наличие по всему каталогу
`InStock` там, где товар доступен (на Remeza уже так, но на ~60% карточек
уходит `OutOfStock`). Логика и готовый файл - `bitrix-product-schema.php`,
раздел 1 этого документа. Видимый статус на странице обязателен.

### Шаг 2. Сделать карточку покупаемой
Ключевое отличие от Рутектора. Нужны кнопка «В корзину»/«Купить», рабочая
корзина и оформление заказа. Без механизма покупки страница для Google -
не merchant listing, а обычный товарный сниппет: цену и рейтинг он
показывает (и показывает), а плашку наличия - нет.

Если корзина в B2B-схеме не нужна, вариант компромисса: оформление заказа
в один шаг («Купить в 1 клик») с реальным подтверждением заказа, а не
формой заявки на КП.

### Шаг 3. Дозаполнить merchant-поля
`hasMerchantReturnPolicy` (сначала опубликовать условия возврата -
`/help/return/` сейчас 404), `shippingDetails`, `mpn`, `priceSpecification`
с базовой ценой. Разделы 2-5 выше.

### Шаг 4. Разобраться с отзывами
У Рутектора в плашке «5,0 (1)» - один настоящий отзыв. У вас в разметке
4,7 · 51 отзыв, а блок отзывов на странице пишет «Нет оценок»; реальные
отзывы - в iframe myreviews.dev, один и тот же профиль на все карточки.
Это риск: если Google снимет доверие к разметке, пропадёт и то, что сейчас
показывается. Правильный путь - вывести настоящие отзывы по товару в HTML
страницы и считать рейтинг по ним.

### Шаг 5. Проверка
Rich Results Test -> раздел «Товарные объявления» (не «Фрагменты товаров»).
Search Console -> отчёт по товарным объявлениям. Оба покажут, чего не хватает.

### Если корзину делать не планируете
Плашки merchant listing не будет. Визуально похожий эффект даёт видимый
текст с галочками через `QAPage` - `bitrix-qa-snippet.php`, разбор в
`MICRORAZMETKA-SERP.md`. Это другой тип результата, но в выдаче читается
похоже: «✅ Цены: от … ✅ В наличии ✅ Доставка».

## Проверка

1. `https://search.google.com/test/rich-results` по URL карточки. В отчёте
   два раздела: «Фрагменты товаров» и «Товарные объявления» (merchant
   listings). Смотреть надо второй - там перечислены недостающие поля.
2. Search Console -> Улучшения: отчёты идут раздельно, у merchant listings
   свои предупреждения по `hasMerchantReturnPolicy` и `shippingDetails`.
3. Сроки: после переобхода 1-4 недели. Наличие в сниппете Google показывает
   на своё усмотрение даже при полностью корректной разметке - гарантий нет.
