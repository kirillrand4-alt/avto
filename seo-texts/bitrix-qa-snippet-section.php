<?php
/**
 * То же, что bitrix-qa-snippet.php, но для СТРАНИЦЫ РАЗДЕЛА каталога (759 SEO-страниц):
 * цена «от» и число позиций считаются по живому списку товаров раздела, а не вшиты в текст.
 *
 * Куда класть: /bitrix/templates/<тема>/components/bitrix/catalog.section/<шаблон>/
 *   и подключить в конце template.php:   include __DIR__ . '/qa-snippet-section.php';
 *
 * Заголовок вопроса берётся из H1 раздела, поэтому один файл обслуживает все разделы.
 */

if (!defined('B_PROLOG_INCLUDED') || B_PROLOG_INCLUDED !== true) die();

/** @var array $arResult - результат компонента bitrix:catalog.section */
global $APPLICATION;

$site = 'https://prokompressor.ru';
$org  = 'ООО «Руспром»';
$h1   = (string)($APPLICATION->GetTitle(false) ?: ($arResult['NAME'] ?? ''));
$url  = $site . $APPLICATION->GetCurPage(false);

$min = null; $count = 0; $inStock = 0;
foreach (($arResult['ITEMS'] ?? []) as $item) {
    $count++;
    $p = $item['MIN_PRICE']['DISCOUNT_VALUE']
        ?? ($item['ITEM_PRICES'][0]['RATIO_PRICE'] ?? ($item['PRICES']['BASE']['VALUE'] ?? null));
    if ($p > 0 && ($min === null || $p < $min)) { $min = (float)$p; }
    if (($item['CATALOG_AVAILABLE'] ?? 'N') === 'Y' || ($item['CATALOG_QUANTITY'] ?? 0) > 0) { $inStock++; }
}
// при постраничной навигации общее число позиций лежит в NAV_RESULT
if (!empty($arResult['NAV_RESULT']) && method_exists($arResult['NAV_RESULT'], 'SelectedRowsCount')) {
    $count = (int)$arResult['NAV_RESULT']->SelectedRowsCount();
}

$fmt = static fn(float $v): string => number_format($v, 0, ',', ' ');

$marks = [];
if ($min !== null) { $marks[] = 'Цены: от ' . $fmt($min) . ' ₽'; }
// «В наличии» - только про реальный остаток; иначе честнее «В продаже»
if ($inStock)      { $marks[] = 'В наличии: ' . $inStock . ' ' . qa_plural($inStock, 'позиция', 'позиции', 'позиций'); }
elseif ($count)    { $marks[] = 'В продаже: ' . $count . ' ' . qa_plural($count, 'позиция', 'позиции', 'позиций'); }
$marks[] = 'Доставка по Москве и России';

if (!function_exists('qa_plural')) {
    function qa_plural(int $n, string $one, string $few, string $many): string {
        $n = abs($n);
        if ($n % 10 === 1 && $n % 100 !== 11) return $one;
        if ($n % 10 >= 2 && $n % 10 <= 4 && ($n % 100 < 12 || $n % 100 > 14)) return $few;
        return $many;
    }
}

$question = 'Почему стоит купить ' . mb_strtolower(mb_substr($h1, 0, 1)) . mb_substr($h1, 1) . ' в ' . $org . '?';
$line     = implode(' ', array_map(static fn($m) => '✅ ' . $m, $marks)) . '.';
$tail     = 'Подбираем оборудование под фактический расход воздуха и давление на участке, '
          . 'отгружаем со склада и под заказ, помогаем с запуском и сервисом.';
$anchor   = 'qa-answer-1';
$author   = ['@type' => 'Person', 'name' => 'Игорь Волков', 'url' => $site . '/company/staff/igor-volkov/'];

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
            'text'        => $line . ' ' . $tail,
            'url'         => $url . '#' . $anchor,
            'upvoteCount' => 1,
            'author'      => $author,
        ],
    ],
];

$h = static fn(string $s): string => htmlspecialcharsbx($s);
?>

<div class="page-qa" id="qa">
    <h2><?= $h($question) ?></h2>
    <div id="<?= $anchor ?>">
        <p><?= $h($line) ?></p>
        <p><?= $h($tail) ?></p>
    </div>
</div>

<script type="application/ld+json"><?= json_encode($qaPage, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT) ?></script>
