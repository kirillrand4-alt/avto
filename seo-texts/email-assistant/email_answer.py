# -*- coding: utf-8 -*-
"""Движок черновиков ответов: классификация -> ретрив из answer-kb -> генерация -> QA-гейт.
Использование: python3 email_answer.py <файл_письма.txt> [--json]"""
import json, os, re, sys

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
import gen_provider as gp
from scrub import scrub

KB = json.load(open(os.path.join(DIR, 'answer-kb.json')))
MODEL_IDX = (json.load(open(os.path.join(DIR, 'model-index.json')))
             if os.path.exists(os.path.join(DIR, 'model-index.json')) else {})
PLAYBOOK = open(os.path.join(DIR, 'PLAYBOOK.md'), encoding='utf-8').read()
GOLD = (json.load(open(os.path.join(DIR, 'golden-pairs.json')))
        if os.path.exists(os.path.join(DIR, 'golden-pairs.json')) else [])

RU2LAT = str.maketrans('абвгдезиклмнопрстуфхэюя', 'abvgdeziklmnoprstufheua')
BRAND_ALIAS = {'абак': 'abac', 'чекато': 'ceccato', 'чеккато': 'ceccato', 'кезер': 'kaeser',
               'кайзер': 'kaeser', 'атлас копко': 'atlas copco', 'кросс эйр': 'cross air'}
CYRTOK = str.maketrans('АВЕКМНОРСТУХаверкмнорстух', 'ABEKMHOPCTYXabepkmhopctyx')

def _norm_tok(t):
    return re.sub(r'[\s\-–—_/.,()]', '', t.translate(CYRTOK).upper())

def _model_tokens(s):
    out = set()
    words = re.findall(r'[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9\-./,]{0,24}', s)
    for t in words:
        if re.search(r'\d', t) and re.search(r'[A-Za-zА-Яа-я]', t):
            n = _norm_tok(t)
            if 4 <= len(n) <= 22:
                out.add(n)
    for a, b in zip(words, words[1:]):      # «Formula I 45-10», «РВ 500.11.02»
        if re.search(r'[A-Za-zА-Яа-я]', a) and re.search(r'\d', b) and not re.search(r'\d', a):
            n = _norm_tok(a + b)
            if 5 <= len(n) <= 24:
                out.add(n)
    return out

def retrieve(letter):
    """Куски базы под письмо: бренды (латиница/кириллица/алиасы) + модели по индексу
    + отрасль + цены сегмента."""
    low = letter.lower()
    low_lat = low.translate(RU2LAT)             # кириллические названия брендов
    for cyr, lat in BRAND_ALIAS.items():
        if cyr in low:
            low = low + ' ' + lat
    ctx = dict(company=KB['company'], brands={}, projects=[], prices={}, model_hits=[])
    for b, v in KB['brands'].items():
        if len(b) > 2 and (b in low or b in low_lat):
            ctx['brands'][b] = v
    # артикул без бренда: модельный индекс -> бренд
    for t in _model_tokens(letter):
        b = MODEL_IDX.get(t)
        if b:
            ctx['model_hits'].append({'token': t, 'brand': b})
            if b in KB['brands']:
                ctx['brands'][b] = KB['brands'][b]
    for s, pr in KB['projects_by_sphere'].items():
        if any(w in low for w in s.lower().split()[:2] if len(w) > 4):
            ctx['projects'] += pr[:3]
    for cat, v in KB['prices']['by_cat'].items():
        tail = cat.split(' / ')[-1].lower()
        if len(tail) > 5 and tail[:6] in low:
            ctx['prices'][cat] = v
    return ctx

def qa_gate(draft, ctx):
    issues = []
    kb_text = json.dumps(ctx, ensure_ascii=False)
    for num in re.findall(r'\b\d{4,}\b', re.sub(r'<[^>]+>', '', draft)):
        if num not in kb_text:
            issues.append(f'цифра {num} не из базы')
    if '—' in draft: issues.append('длинное тире')
    for w in ('гарантирую', 'обещаю', 'скидк'):
        if w in draft.lower(): issues.append(f'стоп-слово: {w}')
    if len(draft) > 2600: issues.append(f'длина {len(draft)} > 1 экрана')
    return issues

def answer(letter_text, client=None):
    client = client or gp.make_client()
    letter = scrub(letter_text)
    msg = gp.call(client, [{'role': 'user', 'content':
        'Классифицируй письмо клиента по типам 1-7 плейбука и ответь ЧЕРНОВИКОМ письма.\n\n'
        '=== ПЛЕЙБУК ===\n' + PLAYBOOK +
        '\n\n=== БАЗА (только отсюда цифры) ===\n' + json.dumps(retrieve(letter), ensure_ascii=False) +
        ('\n\n=== ПРИМЕРЫ ЗОЛОТЫХ ОТВЕТОВ ===\n' + json.dumps(GOLD[:6], ensure_ascii=False) if GOLD else '') +
        '\n\n=== ПИСЬМО КЛИЕНТА ===\n' + letter[:4000] +
        '\n\nВерни ТОЛЬКО JSON: {"type": 1-7, "type_name": "...", "escalate": true/false, '
        '"draft": "текст письма-ответа (пустой если escalate/спам)", "questions": ["уточняющие"], '
        '"used_facts": ["какие факты базы использованы"]}'}],
        model='claude-fable-5', effort='medium')
    d = gp.parse_json(msg)
    d['qa_issues'] = qa_gate(d.get('draft', ''), retrieve(letter)) if d.get('draft') else []
    return d

if __name__ == '__main__':
    txt = open(sys.argv[1], encoding='utf-8').read()
    res = answer(txt)
    print(json.dumps(res, ensure_ascii=False, indent=1))
