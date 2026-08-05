# -*- coding: utf-8 -*-
import json, re, statistics, itertools, glob

prices = json.load(open('diz-min-prices.json'))
pages = {r['slug']: r for r in json.load(open('diz-brands-pages.json'))}
proj_urls = set(r['url'].replace('https://prokompressor.ru','') for r in json.load(open('projects-index.json')) if not r.get('error'))

BANNED = ['кстати','к слову','между прочим','около ','примерно','ориентировочно','берите','отталкивайтесь',
'фильтр слева','незаменим','в этом разделе','по договорённости',
'важно отметить','стоит отметить','широкий спектр','идеальное решение','представляет собой','в современном мире',
'высочайш','инновационн','гарантия 5 лет']  # «гарантия 5 лет» без «до» запрещена
LINK_OK = re.compile(r'^(/catalog/vozdushnye-kompressory/po-tipu/vintovye/(dizelnye/enger/|elektricheskie_1/(enger/)?)|/services/uslugi/[a-z-]+_?/|/projects/[a-z0-9%.-]+/[^"]+|/company/reviews/|/company/staff/igor-volkov/|#)')

def fmt_price(p): return f"{int(p):,}".replace(',', ' ')

results = {}
for f in sorted(glob.glob('gen/result-*.json')):
    d = json.load(open(f))
    slug = d['slug']
    html = d['text_html']
    text = re.sub(r'<[^>]+>',' ', html).replace('&nbsp;',' ')
    text = re.sub(r'\s+',' ', text).strip()
    low = text.lower()
    issues = []
    # объём
    if not (2300 <= len(text) <= 4700): issues.append(f'объём {len(text)}')
    # запрещённые
    hits = [b for b in BANNED if b in low]
    if hits: issues.append('стоп-слова: '+','.join(hits))
    # витринные конструкции: «в разделе/каталоге … представлены/собраны»
    inv = re.findall(r'в (?:раздел[а-я]*|каталог[а-я]*|ассортимент[а-я]*|линейк[а-я]+)[^.!?]{0,50}?(?:представлен|собран)[а-я]*|(?:представлен|собран)[а-я]*\s+(?:на|в)\s+(?:странице|разделе|каталоге)', low)
    if inv: issues.append('витринная конструкция: '+' | '.join(i[:60] for i in inv))
    # SEO-жаргон (границы слова, чтобы не ловить «категория»/«стратегия»)
    jarg = re.findall(r'\b(?:тег|тега|теге|тегу|тегом|тегах|теги|фасет[а-я]*|листинг[а-я]*|выдач[а-я]*)\b', low)
    if jarg: issues.append('SEO-жаргон: '+', '.join(sorted(set(jarg))))
    # тире — запрещено полностью (маркер ИИ-текста)
    dash = text.count('—')
    if dash: issues.append(f'длинное тире « — » запрещено полностью ({dash} вхождений)')
    # вводный H2
    m = re.search(r'<h2>([^<]+)</h2>', html)
    h2первый = (m.group(1) if m else '').lower()
    if not ('винтов' in h2первый and 'дизель' in h2первый): issues.append(f'вводный H2 без полной типизации: "{m.group(1) if m else "нет"}"')
    # script/style
    fake = re.findall(r'<[^a-z/!][^>]{0,15}>', html)
    if fake: issues.append('псевдотеги/плейсхолдеры в HTML: ' + ', '.join(sorted(set(fake))[:5]))
    if '<script' in html or '<style' in html: issues.append('script/style в тексте')
    # аккордеон
    n_tog = html.count('data-toggle="collapse"')
    ids = re.findall(r'id="(accordion-[a-z0-9а-я-]+)"', html)
    n_col = html.count('panel-collapse collapse')
    if not (n_tog == len(ids) == n_col and len(set(ids)) == len(ids) and n_tog >= 3):
        issues.append(f'аккордеон: toggle={n_tog} ids={len(ids)}/{len(set(ids))} collapse={n_col}')
    # ссылки
    for href in re.findall(r'href="([^"]+)"', html):
        if not LINK_OK.match(href): issues.append(f'ссылка вне белого списка: {href}')
        elif href.startswith('/projects/') and href not in proj_urls and href.replace('%20',' ') not in proj_urls:
            issues.append(f'проект не найден: {href}')
    # h1
    if d['h1'] != pages[slug]['h1']: issues.append(f'h1 изменён: {d["h1"]}')
    # description
    dl = len(d['description'])
    if not (110 <= dl <= 175): issues.append(f'description {dl} зн.')
    # цена в title
    p = prices.get(slug, {}).get('min_diesel_price')
    tt = d['title']
    m2 = re.search(r'от ([\d\s]+) ?₽', tt)
    if m2:
        tprice = int(m2.group(1).replace(' ',''))
        if p is None: issues.append(f'цена в title {tprice}, но цен на сайте нет')
        elif abs(tprice - p) > 1: issues.append(f'цена в title {tprice} ≠ мин.дизельной {int(p)}')
    results[slug] = {'issues': issues, 'len': len(text), 'dash': dash, 'title': tt,
                     'faq': re.findall(r'<span>([^<]{10,120}\?)</span>', html), 'text': low}

# межстраничная похожесть (шинглы 5 слов, без разметки)
def shingles(t, n=5):
    w = re.findall(r'[а-яёa-z0-9]+', t)
    return set(tuple(w[i:i+n]) for i in range(len(w)-n+1))
sh = {s: shingles(r['text']) for s, r in results.items()}
sim_flags = []
for a, b in itertools.combinations(results, 2):
    inter = len(sh[a] & sh[b]); uni = len(sh[a] | sh[b])
    j = inter/uni if uni else 0
    if j > 0.12: sim_flags.append((a, b, round(j,3)))

# FAQ разнообразие
from collections import Counter
faqc = Counter(q for r in results.values() for q in r['faq'])

print('=== ПРОБЛЕМЫ ПО ТЕКСТАМ ===')
ok = 0
for s, r in results.items():
    if r['issues']:
        print(f'\n{s}:'); [print('   -', i) for i in r['issues']]
    else: ok += 1
print(f'\nчистых текстов: {ok}/{len(results)}')
print('\n=== ПОХОЖЕСТЬ (>0.12 жаккар) ===')
for a,b,j in sorted(sim_flags, key=lambda x:-x[2]): print(f'   {a} ~ {b}: {j}')
print('\n=== ТОП FAQ-вопросов (повторы) ===')
for q, c in faqc.most_common(8):
    if c >= 5: print(f'   {c}×  {q[:80]}')
print('\nвсего уникальных вопросов:', len(faqc))
