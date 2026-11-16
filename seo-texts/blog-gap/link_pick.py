"""Перелинковка блог -> категории. Вся LLM-работа через провайдера, резюмируемо (jsonl+fsync).

  python3 link_pick.py pick     -> link-pick.jsonl   (кандидаты по каждой статье)
  python3 link_pick.py review   -> link-review.jsonl (ревьюер-провайдер по каждой статье)
  python3 link_pick.py build    -> PERELINKOVKA-TABLICA.csv/.md (QA + балансировка)
"""
import collections
import concurrent.futures as cf
import csv
import json
import os
import re
import sys
import threading

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
import gen_provider as GP  # noqa: E402

MODEL = os.environ.get('LP_MODEL', 'claude-opus-5-5')
LOCK = threading.Lock()
MAX_PER_ARTICLE, MAX_PER_CAT, EXACT_SHARE = 5, 10, 0.3
P = lambda n: os.path.join(DIR, n)  # noqa: E731


def jl(name):
    return [json.loads(l) for l in open(P(name), encoding='utf-8')] if os.path.exists(P(name)) else []


def append(name, rec):
    with LOCK, open(P(name), 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        f.flush(); os.fsync(f.fileno())


def ask(prompt, max_tokens=6000):
    m = GP.call(None, [{'role': 'user', 'content': prompt}], model=MODEL, thinking_on=False, max_tokens=max_tokens)
    txt = m if isinstance(m, str) else ''.join(b.text for b in m.content if b.type == 'text')
    return json.loads(re.search(r'\{.*\}', txt, re.S).group(0))


def categories():
    acc = {x['page'].rstrip('/') + '/': x for x in json.load(open(os.path.join(os.path.dirname(DIR), 'guest-posts', 'acceptors-v15.json'), encoding='utf-8'))}
    out = {}
    for r in jl('categories.jsonl'):
        if r.get('status') != 200 or r.get('noindex') or not r.get('h1'):
            continue
        if r.get('final_url') and r['final_url'] != r['url']:
            continue
        if r.get('canonical') and r['canonical'] != r['url']:
            continue
        if r['url'] == '/catalog/':
            continue
        r['prio'] = 1 if r['url'] in acc else 0
        out[r['url']] = r
    return out


def cat_lines(cats):
    return '\n'.join(f"{u} | {c['h1']} | товаров {c.get('n_products', 0)}{' | ПРИОРИТЕТ' if c['prio'] else ''}"
                     for u, c in sorted(cats.items()))


PICK = """Ты делаешь внутреннюю перелинковку: статья блога prokompressor.ru -> разделы каталога.
Цель: читателю статьи в нужном месте предложить перейти в раздел, где он купит/подберёт
то, о чём читает; и передать разделу релевантный вес.

Правила:
- 2-5 ссылок на статью (меньше, если честно подходит меньше; 0 если статья не про наш каталог).
- Только разделы из списка ниже (URL точно как в списке). Предпочитай самый точный раздел
  (не «все компрессоры», если речь о винтовых безмасляных). ПРИОРИТЕТ - бонус при равной уместности.
- На один раздел - одна ссылка. Не ставить в заголовки (tag h2/h3) и в абзац 0.
  Не ставить в абзацы, где уже есть ссылка, и на разделы, на которые статья уже ссылается.
- anchor - ТОЧНАЯ подстрока текста абзаца (символ в символ), 2-6 слов, естественная
  фраза, по смыслу = содержимое раздела. Типы: exact (= название раздела/главный запрос),
  partial (запрос + уточнение/форма слова), descriptive (описательная фраза).
  Разнообразь типы; exact - не больше 1-2 на статью.
- Если подходящей фразы в тексте нет, но ссылка очень уместна - можно предложить
  ОДНУ на статью вставку: new_sentence - короткое предложение в конец абзаца, содержащее
  anchor. Стиль: без длинных тире, без списков, без названия юрлица, без выдуманных фактов и цифр.
- why - одна фраза: зачем читателю этот переход здесь.
Ответ строго JSON:
{{"links":[{{"para":N,"anchor":"...","url":"/catalog/.../","type":"exact|partial|descriptive","new_sentence":"" ,"why":"..."}}]}}

РАЗДЕЛЫ КАТАЛОГА (url | H1 | товаров):
{cats}

СТАТЬЯ: {url}
H1: {h1}
Уже ссылается на: {existing}
Абзацы (N | tag | текст; [L] - в абзаце уже есть ссылка):
{paras}"""


def para_lines(a):
    linked = {l['n'] for l in a.get('links', [])}
    return '\n'.join(f"{p['n']} | {p['tag']}{' [L]' if p['n'] in linked else ''} | {p['text'][:700]}" for p in a['paras'])


def st_pick():
    cats = categories()
    cl = cat_lines(cats)
    print('разделов в списке', len(cats), flush=True)
    done = {r['url'] for r in jl('link-pick.jsonl')}
    arts = [a for a in jl('blog.jsonl') if a.get('status') == 200 and a['url'] not in done]

    def one(a):
        try:
            r = ask(PICK.format(cats=cl, url=a['url'], h1=a['h1'],
                                existing=', '.join(sorted({l['href'] for l in a.get('links', [])})) or 'нет',
                                paras=para_lines(a)))
        except Exception as e:
            print('ERR', a['url'], repr(e)[:120], flush=True)
            return
        append('link-pick.jsonl', {'url': a['url'], 'links': r.get('links', [])})
        print(a['url'], len(r.get('links', [])), flush=True)

    with cf.ThreadPoolExecutor(int(os.environ.get('LP_THREADS', '5'))) as ex:
        list(ex.map(one, arts))


REVIEW = """Ты ревьюер внутренней перелинковки (SEO + редактор). Статья блога и предложенные
ссылки на разделы каталога. Оцени КАЖДУЮ ссылку:
 ok - уместно, раздел точно соответствует смыслу анкора и абзаца, звучит естественно;
 fix - идея верная, но лучше другой раздел из списка / другой анкор из того же абзаца
       (дай исправленные url/anchor; anchor - точная подстрока абзаца);
 drop - неуместно, натянуто, раздел не про то, рекламно звучит.
Если new_sentence не пустое - проверь стиль (естественно, без длинных тире, без выдуманных
фактов) и исправь при необходимости.
Ответ строго JSON: {{"v":[{{"i":индекс,"verdict":"ok|fix|drop","url":"...","anchor":"...","new_sentence":"...","note":"..."}}]}}

РАЗДЕЛЫ КАТАЛОГА:
{cats}

СТАТЬЯ: {url} - {h1}
Абзацы:
{paras}

ПРЕДЛОЖЕННЫЕ ССЫЛКИ:
{links}"""


def st_review():
    cats = categories()
    cl = cat_lines(cats)
    arts = {a['url']: a for a in jl('blog.jsonl')}
    done = {r['url'] for r in jl('link-review.jsonl')}
    todo = [r for r in jl('link-pick.jsonl') if r['url'] not in done and r['links']]

    def one(r):
        a = arts[r['url']]
        links = '\n'.join(f"{i}: абзац {l.get('para')} | анкор «{l.get('anchor')}» -> {l.get('url')} | {l.get('type')}"
                          f"{' | вставка: ' + l['new_sentence'] if l.get('new_sentence') else ''} | {l.get('why', '')}"
                          for i, l in enumerate(r['links']))
        try:
            v = ask(REVIEW.format(cats=cl, url=a['url'], h1=a['h1'], paras=para_lines(a), links=links))
        except Exception as e:
            print('ERR', r['url'], repr(e)[:120], flush=True)
            return
        append('link-review.jsonl', {'url': r['url'], 'v': v.get('v', [])})

    with cf.ThreadPoolExecutor(int(os.environ.get('LP_THREADS', '5'))) as ex:
        list(ex.map(one, todo))
    print('отревьюено', len(jl('link-review.jsonl')))


def st_build():
    cats = categories()
    arts = {a['url']: a for a in jl('blog.jsonl')}
    rev = {r['url']: {int(x['i']): x for x in r['v'] if 'i' in x} for r in jl('link-review.jsonl')}
    rows, rejected = [], collections.Counter()
    for r in jl('link-pick.jsonl'):
        a = arts[r['url']]
        paras = {p['n']: p for p in a['paras']}
        linked_p = {l['n'] for l in a.get('links', [])}
        linked_u = {l['href'] for l in a.get('links', [])}
        used, ins = set(), 0
        for i, l in enumerate(r['links']):
            v = rev.get(r['url'], {}).get(i, {'verdict': 'ok'})
            if v['verdict'] == 'drop':
                rejected['ревьюер: drop'] += 1
                continue
            if v['verdict'] == 'fix':
                l = {**l, 'url': v.get('url') or l['url'], 'anchor': v.get('anchor') or l['anchor'],
                     'new_sentence': v.get('new_sentence', l.get('new_sentence', ''))}
            url = (l.get('url') or '').strip()
            n = l.get('para')
            p = paras.get(n if isinstance(n, int) else -1)
            ns = (l.get('new_sentence') or '').strip()
            why = None
            if url not in cats:
                why = 'раздела нет в каталоге/не 200/не канон'
            elif p is None or p['tag'] in ('h2', 'h3') or n == 0:
                why = 'абзац недопустим'
            elif n in linked_p:
                why = 'в абзаце уже есть ссылка'
            elif url in linked_u or url in used:
                why = 'повтор раздела'
            elif ns and ins >= 1:
                why = 'больше одной вставки'
            elif ns and l['anchor'] not in ns:
                why = 'анкора нет во вставке'
            elif not ns and l['anchor'] not in p['text']:
                why = 'анкор не подстрока абзаца'
            elif ns and re.search('[—–]', ns):
                why = 'длинное тире во вставке'
            if why:
                rejected[why] += 1
                continue
            used.add(url)
            ins += bool(ns)
            src = ns if ns else p['text']
            k = src.find(l['anchor'])
            sent_start = max(src.rfind('. ', 0, k) + 2, 0) if src.rfind('. ', 0, k) >= 0 else 0
            sent_end = src.find('. ', k + len(l['anchor']))
            sent = src[sent_start: sent_end + 1 if sent_end >= 0 else len(src)]
            rows.append({'statya': 'https://prokompressor.ru' + r['url'], 'statya_h1': a['h1'], 'abzac': n,
                         'ankor': l['anchor'], 'link': 'https://prokompressor.ru' + url, 'razdel': cats[url]['h1'],
                         'tip_ankora': l.get('type', ''), 'vstavka': ns, 'predlozhenie': sent,
                         'prioritet': 'да' if cats[url]['prio'] else '', 'zachem': l.get('why', ''),
                         'revyu': v['verdict']})
    # балансировка: лимит на статью и на раздел, доля exact
    by_art = collections.defaultdict(list)
    for x in rows:
        by_art[x['statya']].append(x)
    rows = [x for xs in by_art.values() for x in xs[:MAX_PER_ARTICLE]]
    rejected['лимит на статью'] += sum(max(0, len(xs) - MAX_PER_ARTICLE) for xs in by_art.values())
    by_cat = collections.defaultdict(list)
    for x in rows:
        by_cat[x['link']].append(x)
    final = []
    for u, xs in by_cat.items():
        xs.sort(key=lambda x: (x['tip_ankora'] == 'exact', x['vstavka'] != ''))
        keep, ex_n, seen_anchor = [], 0, set()
        for x in xs:
            a = x['ankor'].lower()
            if a in seen_anchor:
                rejected['повтор анкора на раздел'] += 1
                continue
            if x['tip_ankora'] == 'exact' and ex_n + 1 > max(1, EXACT_SHARE * len(xs)):
                rejected['доля точных анкоров'] += 1
                continue
            if len(keep) >= MAX_PER_CAT:
                rejected['лимит на раздел'] += 1
                continue
            seen_anchor.add(a)
            ex_n += x['tip_ankora'] == 'exact'
            keep.append(x)
        final += keep
    final.sort(key=lambda x: (x['statya'], x['abzac']))
    cols = ['statya', 'statya_h1', 'abzac', 'ankor', 'link', 'razdel', 'tip_ankora', 'predlozhenie',
            'vstavka', 'prioritet', 'zachem', 'revyu']
    head = ['Статья', 'H1 статьи', 'Абзац №', 'Анкор', 'Ссылка', 'Раздел', 'Тип анкора', 'Предложение',
            'Вставка (новое предложение)', 'Приоритетный раздел', 'Зачем', 'Ревью']
    with open(P('PERELINKOVKA-TABLICA.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(head)
        for x in final:
            w.writerow([x[c] for c in cols])
    st = {'ссылок': len(final), 'статей со ссылками': len({x['statya'] for x in final}),
          'разделов получили': len({x['link'] for x in final}),
          'приоритетных разделов': len({x['link'] for x in final if x['prioritet']}),
          'вставок': sum(1 for x in final if x['vstavka']),
          'типы': dict(collections.Counter(x['tip_ankora'] for x in final)), 'отсеяно': dict(rejected)}
    json.dump({'stats': st, 'rows': final}, open(P('perelinkovka.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(st, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    {'pick': st_pick, 'review': st_review, 'build': st_build}[sys.argv[1]]()
