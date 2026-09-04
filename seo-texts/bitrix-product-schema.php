<?php
/**
 * Полная микроразметка Product для карточки товара prokompressor.ru.
 * Заменяет текущий блок JSON-LD в шаблоне catalog.element.
 *
 * Что чинит по сравнению с тем, что стоит на сайте сейчас:
 *   1. availability больше не берётся из остатка вслепую -> перестают уходить
 *      OutOfStock по товарам, которые реально можно купить (главная причина,
 *      по которой в выдаче нет строки наличия);
 *   2. старая цена размечается через priceSpecification/ListPrice;
 *   3. из description убирается двойное HTML-экранирование (&#40; -> «(»);
 *   4. добавляются поля merchant listing: mpn/gtin13, hasMerchantReturnPolicy,
 *      shippingDetails;
 *   5. aggregateRating выключен по умолчанию - включать только с реальными
 *      отзывами по товару, выведенными в HTML страницы (не в iframe).
 *
 * Подключение: include __DIR__ . '/product-schema.php'; в конце template.php
 * своей копии шаблона bitrix:catalog.element.
 */

if (!defined('B_PROLOG_INCLUDED') || B_PROLOG_INCLUDED !== true) die();

/** @var array $arResult */

// ============================ НАСТРОЙКИ ==================================
$site = 'https://prokompressor.ru';
$org  = 'ООО «Руспром»';

// Товар без складского учёта, но с разрешённой покупкой считаем доступным.
// false -> такие позиции пойдут как PreOrder (везём под заказ).
$assumeInStockWhenNoTrace = true;

// Свойства инфоблока, откуда брать заводской артикул и штрихкод.
$mpnProps  = ['CML2_ARTICLE', 'ARTICLE', 'ARTIKUL'];
$gtinProps = ['BARCODE', 'EAN', 'GTIN'];

// Политика возврата. Включать ТОЛЬКО после публикации страницы с условиями:
// разметка должна повторять то, что написано на сайте.
$returnPolicy = null;
/* $returnPolicy = [
    'applicableCountry'   => 'RU',
    'returnPolicyCategory'=> 'https://schema.org/MerchantReturnFiniteReturnWindow',
    'merchantReturnDays'  => 14,
    'returnMethod'        => 'https://schema.org/ReturnByMail',
    'returnFees'          => 'https://schema.org/ReturnFeesCustomerResponsibility',
]; */

// Доставка. У вас стоимость считается по тарифу ТК, фиксированной ставки нет,
// поэтому по умолчанию блок не выводится: выдумывать цифру нельзя.
// Включать, когда появится тариф, который можно назвать честно.
$shipping = null;
/* $shipping = [
    'rate'            => 0,          // руб., 0 = бесплатно
    'country'         => 'RU',
    'handlingDaysMin' => 1,          // от заказа до отгрузки
    'handlingDaysMax' => 3,
    'transitDaysMin'  => 1,          // в пути
    'transitDaysMax'  => 14,
]; */

// Реальные отзывы по товару. [ratingValue, reviewCount] или null.
$rating = null;
// =========================================================================

$name = (string)($arResult['NAME'] ?? '');
$url  = $site . ($arResult['DETAIL_PAGE_URL'] ?? '');

// --- цена: DISCOUNT_VALUE - к оплате, VALUE - базовая («старая») ----------
$priceNow = null; $priceList = null;
$p = $arResult['MIN_PRICE'] ?? ($arResult['ITEM_PRICES'][0] ?? null);
if ($p) {
    $priceNow  = (float)($p['DISCOUNT_VALUE'] ?? $p['VALUE'] ?? 0) ?: null;
    $base      = (float)($p['VALUE'] ?? 0);
    if ($base > 0 && $priceNow !== null && $base > $priceNow) {
        $priceList = $base;
    }
}
if ($priceNow === null && !empty($arResult['OFFERS'])) {
    foreach ($arResult['OFFERS'] as $o) {
        $op = (float)($o['MIN_PRICE']['DISCOUNT_VALUE'] ?? 0);
        if ($op > 0 && ($priceNow === null || $op < $priceNow)) { $priceNow = $op; }
    }
}

// --- наличие --------------------------------------------------------------
// CAN_BUY - разрешена ли покупка; QUANTITY_TRACE - ведётся ли складской учёт.
$canBuy = (($arResult['CAN_BUY'] ?? 'N') === 'Y') || (($arResult['CATALOG_AVAILABLE'] ?? 'N') === 'Y');
$trace  = ($arResult['CATALOG_QUANTITY_TRACE'] ?? 'N') === 'Y';
$qty    = (float)($arResult['CATALOG_QUANTITY'] ?? 0);

if (!$canBuy) {
    $availability = 'OutOfStock';
} elseif ($trace && $qty > 0) {
    $availability = 'InStock';
} elseif (!$trace) {
    $availability = $assumeInStockWhenNoTrace ? 'InStock' : 'PreOrder';
} else {
    $availability = 'PreOrder';           // учёт ведётся, остаток 0, покупка разрешена
}

// --- идентификаторы -------------------------------------------------------
$firstProp = static function (array $names) use ($arResult): ?string {
    foreach ($names as $code) {
        $v = $arResult['PROPERTIES'][$code]['VALUE'] ?? null;
        if (is_array($v)) { $v = reset($v); }
        if ($v !== null && $v !== '') { return (string)$v; }
    }
    return null;
};
$mpn  = $firstProp($mpnProps);
$gtin = $firstProp($gtinProps);

// --- сборка ---------------------------------------------------------------
$product = [
    '@context' => 'https://schema.org',
    '@type'    => 'Product',
    'name'     => $name,
    'url'      => $url,
];
if (!empty($arResult['DETAIL_TEXT']) || !empty($arResult['PREVIEW_TEXT'])) {
    $raw = strip_tags((string)($arResult['PREVIEW_TEXT'] ?: $arResult['DETAIL_TEXT']));
    // сущности декодируем: внутри <script> они не разбираются браузером
    $product['description'] = trim(html_entity_decode($raw, ENT_QUOTES | ENT_HTML5, 'UTF-8'));
}
if (!empty($arResult['DETAIL_PICTURE']['SRC'])) {
    $product['image'] = $site . $arResult['DETAIL_PICTURE']['SRC'];
}
if (!empty($arResult['PROPERTIES']['BRAND']['VALUE'])) {
    $b = $arResult['PROPERTIES']['BRAND']['VALUE'];
    $product['brand'] = ['@type' => 'Brand', 'name' => is_array($b) ? reset($b) : $b];
}
if (!empty($arResult['ID']))    { $product['sku']  = (string)$arResult['ID']; }
if ($mpn)                       { $product['mpn']  = $mpn; }
if ($gtin && preg_match('/^\d{13}$/', $gtin)) { $product['gtin13'] = $gtin; }

if ($priceNow !== null) {
    $offer = [
        '@type'           => 'Offer',
        'price'           => $priceNow,
        'priceCurrency'   => 'RUB',
        'availability'    => 'https://schema.org/' . $availability,
        'itemCondition'   => 'https://schema.org/NewCondition',
        'priceValidUntil' => date('Y-m-d', strtotime('+1 year')),
        'url'             => $url,
        'seller'          => ['@type' => 'Organization', 'name' => $org],
    ];
    if ($priceList !== null) {
        $offer['priceSpecification'] = [
            '@type'         => 'UnitPriceSpecification',
            'priceType'     => 'https://schema.org/ListPrice',
            'price'         => $priceList,
            'priceCurrency' => 'RUB',
        ];
    }
    if ($returnPolicy) {
        $rp = [
            '@type'                => 'MerchantReturnPolicy',
            'applicableCountry'    => $returnPolicy['applicableCountry'],
            'returnPolicyCategory' => $returnPolicy['returnPolicyCategory'],
        ];
        if (!empty($returnPolicy['merchantReturnDays'])) { $rp['merchantReturnDays'] = (int)$returnPolicy['merchantReturnDays']; }
        if (!empty($returnPolicy['returnMethod']))       { $rp['returnMethod'] = $returnPolicy['returnMethod']; }
        if (!empty($returnPolicy['returnFees']))         { $rp['returnFees'] = $returnPolicy['returnFees']; }
        $offer['hasMerchantReturnPolicy'] = $rp;
    }
    if ($shipping) {
        $offer['shippingDetails'] = [
            '@type'               => 'OfferShippingDetails',
            'shippingRate'        => ['@type' => 'MonetaryAmount',
                                      'value' => (float)$shipping['rate'], 'currency' => 'RUB'],
            'shippingDestination' => ['@type' => 'DefinedRegion',
                                      'addressCountry' => $shipping['country']],
            'deliveryTime'        => [
                '@type'       => 'ShippingDeliveryTime',
                'handlingTime'=> ['@type' => 'QuantitativeValue',
                                  'minValue' => (int)$shipping['handlingDaysMin'],
                                  'maxValue' => (int)$shipping['handlingDaysMax'],
                                  'unitCode' => 'DAY'],
                'transitTime' => ['@type' => 'QuantitativeValue',
                                  'minValue' => (int)$shipping['transitDaysMin'],
                                  'maxValue' => (int)$shipping['transitDaysMax'],
                                  'unitCode' => 'DAY'],
            ],
        ];
    }
    $product['offers'] = $offer;
}

if ($rating && !empty($rating['reviewCount'])) {
    $product['aggregateRating'] = [
        '@type'       => 'AggregateRating',
        'ratingValue' => (string)$rating['ratingValue'],
        'reviewCount' => (int)$rating['reviewCount'],
        'bestRating'  => '5',
        'worstRating' => '1',
    ];
}
?>
<script type="application/ld+json"><?= json_encode($product, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT) ?></script>
