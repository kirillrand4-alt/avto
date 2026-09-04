<?php
/**
 * Микроразметка «вопрос-ответ» + Product для карточки товара prokompressor.ru.
 * Даёт сниппет вида: «1 ответ · Лучший ответ: ✅ Цены: от 194 035 ₽ ✅ В наличии ✅ Доставка...»
 * и (при РЕАЛЬНЫХ отзывах) звёзды рейтинга.
 *
 * Куда класть: /bitrix/templates/<тема>/components/bitrix/catalog.element/<шаблон>/
 *   и подключить в конце template.php:      include __DIR__ . '/qa-snippet.php';
 * Правильнее - в своей копии шаблона, чтобы обновление темы не затёрло файл.
 *
 * Почему в шаблоне, а не в тексте описания: цена и наличие живые. Статическая строка
 * «от 194 035 ₽», вшитая в описание, через месяц разойдётся с ценой на странице -
 * это и плохой UX, и повод для Google снять расширенный сниппет.
 */

if (!defined('B_PROLOG_INCLUDED') || B_PROLOG_INCLUDED !== true) die();

/** @var array $arResult - результат компонента bitrix:catalog.element */

$site   = 'https://prokompressor.ru';
$org    = 'ООО «Руспром»';
$name   = (string)($arResult['NAME'] ?? '');
$url    = $site . ($arResult['DETAIL_PAGE_URL'] ?? '');

// --- цена: берём первую живую цену из тех мест, где её кладут разные шаблоны -----------
$price = null;
foreach ([
    $arResult['MIN_PRICE']['DISCOUNT_VALUE'] ?? null,
    $arResult['MIN_PRICE']['VALUE'] ?? null,
    $arResult['ITEM_PRICES'][0]['RATIO_PRICE'] ?? null,
    $arResult['ITEM_PRICES'][0]['PRICE'] ?? null,
] as $candidate) {
    if ($candidate > 0) { $price = (float)$candidate; break; }
}
// торговые предложения: минимальная цена по офферам
if ($price === null && !empty($arResult['OFFERS'])) {
    foreach ($arResult['OFFERS'] as $offer) {
        $p = $offer['MIN_PRICE']['DISCOUNT_VALUE'] ?? ($offer['ITEM_PRICES'][0]['RATIO_PRICE'] ?? null);
        if ($p > 0 && ($price === null || $p < $price)) { $price = (float)$p; }
    }
}

// --- наличие ---------------------------------------------------------------------------
$available = (($arResult['CATALOG_AVAILABLE'] ?? 'N') === 'Y')
          || (($arResult['CATALOG_QUANTITY'] ?? 0) > 0);

// --- РЕАЛЬНЫЙ рейтинг: подставьте свой источник отзывов ---------------------------------
// Ничего не выдумывайте: рейтинг без отзывов, которые видны на этой же странице, -
// прямое нарушение правил Google (ручные санкции «Spammy structured markup»)
// и статьи о недостоверной рекламе. Оставьте null, пока отзывов по товару нет.
$ratingValue = null;   // напр. (float)$arResult['PROPERTIES']['RATING']['VALUE']
$reviewCount = null;   // напр. (int)$arResult['PROPERTIES']['REVIEWS_CNT']['VALUE']

// ---------------------------------------------------------------------------------------
$fmt = static fn(float $v): string => number_format($v, 0, ',', ' ');

$marks = [];
if ($price !== null)  { $marks[] = 'Цены: от ' . $fmt($price) . ' ₽'; }
if ($available)       { $marks[] = 'В наличии'; }
$marks[] = 'Доставка по Москве и России';

$question = 'Почему стоит купить ' . $name . ' в ' . $org . '?';
$line     = implode(' ', array_map(static fn($m) => '✅ ' . $m, $marks)) . '.';
$tail     = 'Подбираем оборудование под фактический расход воздуха и давление на участке, '
          . 'отгружаем со склада и под заказ, помогаем с запуском и сервисом.';
$answer   = $line . ' ' . $tail;
$anchor   = 'qa-answer-1';

$author = ['@type' => 'Person', 'name' => 'Игорь Волков', 'url' => $site . '/company/staff/igor-volkov/'];

$qaPage = [
    '@context'   => 'https://schema.org',
    '@type'      => 'QAPage',
    'url'        => $url,
    'mainEntity' => [
        '@type'          => 'Question',
        'name'           => $question,
        'text'           => $question,
        'answerCount'    => 1,
        'author'         => $author,
        'acceptedAnswer' => [
            '@type'       => 'Answer',
            'text'        => $answer,
            'url'         => $url . '#' . $anchor,
            'upvoteCount' => 1,
            'author'      => $author,
        ],
    ],
];

$product = [
    '@context' => 'https://schema.org',
    '@type'    => 'Product',
    'name'     => $name,
    'url'      => $url,
];
if (!empty($arResult['DETAIL_PICTURE']['SRC'])) {
    $product['image'] = $site . $arResult['DETAIL_PICTURE']['SRC'];
}
if (!empty($arResult['PROPERTIES']['BRAND']['VALUE'])) {
    $product['brand'] = ['@type' => 'Brand', 'name' => $arResult['PROPERTIES']['BRAND']['VALUE']];
}
if ($price !== null) {
    $product['offers'] = [
        '@type'         => 'Offer',
        'price'         => (string)round($price, 2),
        'priceCurrency' => 'RUB',
        'availability'  => $available ? 'https://schema.org/InStock' : 'https://schema.org/PreOrder',
        'url'           => $url,
        'seller'        => ['@type' => 'Organization', 'name' => $org],
    ];
}
// Звёзды в выдаче даёт именно этот блок - и только с настоящими отзывами.
if ($ratingValue !== null && $reviewCount) {
    $product['aggregateRating'] = [
        '@type'       => 'AggregateRating',
        'ratingValue' => (string)$ratingValue,
        'reviewCount' => (int)$reviewCount,
        'bestRating'  => '5',
        'worstRating' => '1',
    ];
}

$enc = static fn(array $d): string => json_encode($d, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
$h   = static fn(string $s): string => htmlspecialcharsbx($s);
?>

<!-- видимый блок: без него разметка считается скрытым контентом -->
<div class="page-qa" id="qa">
    <h2><?= $h($question) ?></h2>
    <div id="<?= $anchor ?>">
        <p><?= $h($line) ?></p>
        <p><?= $h($tail) ?></p>
    </div>
</div>

<script type="application/ld+json"><?= $enc($qaPage) ?></script>
<script type="application/ld+json"><?= $enc($product) ?></script>
