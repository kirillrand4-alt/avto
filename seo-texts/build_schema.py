# -*- coding: utf-8 -*-
"""Post-process: строит JSON-LD (FAQPage + BreadcrumbList + Product) из готового текста и payload,
отдаёт КАЖДУЮ страницу в ДВУХ вариантах для вставки на сайт:
  publish/plain/<name>.html   - только текст (как сейчас)
  publish/schema/<name>.html  - текст + <script type=application/ld+json> (микроразметка)
Микроразметку строим ТОЛЬКО из реальных данных страницы (вопросы FAQ, крошки, бренд/цена/кол-во)."""
import json, os, re, glob, html as _html

DIR = os.path.dirname(os.path.abspath(__file__))
PLAIN = os.path.join(DIR, 'publish', 'plain')
SCHEMA = os.path.join(DIR, 'publish', 'schema')
for d in (PLAIN, SCHEMA):
    os.makedirs(d, exist_ok=True)

SITE = 'https://prokompressor.ru'
RU_SEG = {'catalog': 'Каталог', 'vozdushnye-kompressory': 'Воздушные компрессоры',
          'osushiteli': 'Осушители', 'resivery': 'Ресиверы', 'podgotovka-vozdukha': 'Подготовка воздуха',
          'generatsiya-gazov': 'Генерация газов', 'zapasnye-chasti-i-raskhodniki': 'Запчасти и расходники'}


def strip_tags(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s)).strip()


def faq_pairs(html):
    """Извлечь пары вопрос/ответ из аккордеона Aspro (вопросы и ответы по порядку, затем zip)."""
    qs = re.findall(r'accordion-head[^>]*>.*?<span>([^<]+)</span>\s*</div>', html, re.S)
    ans = re.findall(r'accordion-body">\s*(.*?)\s*</div>', html, re.S)
    pairs = []
    for q, a in zip(qs, ans):
        q, a = strip_tags(q), strip_tags(a)
        if q and a and len(q) > 5:
            pairs.append((q, a))
    return pairs


def breadcrumbs(url, h1):
    segs = [s for s in url.strip('/').split('/') if s]
    items = [{'@type': 'ListItem', 'position': 1, 'name': 'Главная', 'item': SITE + '/'}]
    path = ''
    pos = 2
    for s in segs:
        path += '/' + s
        name = RU_SEG.get(s)
        last = (path.rstrip('/') == url.rstrip('/'))
        if last:
            name = h1
        if not name:
            continue
        items.append({'@type': 'ListItem', 'position': pos, 'name': name, 'item': SITE + path + '/'})
        pos += 1
    return {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': items}


def faqpage(pairs):
    return {'@context': 'https://schema.org', '@type': 'FAQPage',
            'mainEntity': [{'@type': 'Question', 'name': q,
                            'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in pairs]}


try:
    _PRODUCTS = json.load(open(os.path.join(DIR, 'products-index.json'), encoding='utf-8'))
except FileNotFoundError:
    _PRODUCTS = {}


def collection_page(payload, slug):
    """CollectionPage со списком РЕАЛЬНЫХ товаров (ItemList из Product) - корректная разметка
    страницы-листинга (не один Product на категорию)."""
    prods = _PRODUCTS.get(slug) or []
    brand = None
    if payload.get('page_brand'):
        brand = {'@type': 'Brand', 'name': payload['page_brand'].replace('_', ' ').title()}
    elements = []
    for i, pr in enumerate(prods, 1):
        # цены НЕ кладём: снимок из краула быстро разойдётся с живой ценой -> нарушение schema.
        # Живые цены/наличие - в разметке карточек товаров, не на странице-листинге.
        item = {'@type': 'Product', 'name': pr['name'], 'url': SITE + pr['url'],
                'category': 'Компрессорное оборудование'}
        if brand:
            item['brand'] = brand
        elements.append({'@type': 'ListItem', 'position': i, 'item': item})
    if not elements:
        return None
    return {'@context': 'https://schema.org', '@type': 'CollectionPage',
            'name': payload.get('h1'), 'url': SITE + payload.get('url', ''),
            'mainEntity': {'@type': 'ItemList',
                           'numberOfItems': int(payload.get('count') or len(elements)),
                           'itemListElement': elements}}


def name_of(slug):
    return slug


def build_one(result_path):
    slug = os.path.basename(result_path)[len('result-'):-len('.json')]
    pp = os.path.join(DIR, 'gen', f'payload-{slug}.json')
    if not os.path.exists(pp):
        return None
    d = json.load(open(result_path)); payload = json.load(open(pp))
    text = d.get('text_html', '')
    if not text:
        return None
    # plain
    open(os.path.join(PLAIN, slug + '.html'), 'w', encoding='utf-8').write(text)
    # schema
    blocks = [breadcrumbs(payload.get('url', ''), payload.get('h1'))]
    fp = faq_pairs(text)
    if fp:
        blocks.append(faqpage(fp))
    cp = collection_page(payload, slug)
    if cp:
        blocks.append(cp)
    scripts = '\n'.join(
        '<script type="application/ld+json">\n' + json.dumps(b, ensure_ascii=False, indent=1) + '\n</script>'
        for b in blocks)
    open(os.path.join(SCHEMA, slug + '.html'), 'w', encoding='utf-8').write(text + '\n\n' + scripts + '\n')
    return slug, len(fp)


def main():
    import sys
    if len(sys.argv) > 1:
        results = [os.path.join(DIR, 'gen', f'result-{s.strip()}.json') for s in open(sys.argv[1]) if s.strip()]
    else:
        results = glob.glob(os.path.join(DIR, 'gen', 'result-*.json'))
    n = 0; faqs = 0
    for r in results:
        if not os.path.exists(r):
            continue
        out = build_one(r)
        if out:
            n += 1; faqs += (1 if out[1] else 0)
    print(f'собрано в 2 вариантах: {n} страниц (plain + schema) | с FAQ-разметкой: {faqs}')
    print(f'  без разметки:  publish/plain/*.html')
    print(f'  с разметкой:   publish/schema/*.html')


if __name__ == '__main__':
    main()
