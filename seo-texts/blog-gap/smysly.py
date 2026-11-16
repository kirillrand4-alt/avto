"""Смыслы блогов: prokompressor.ru против конкурентов. Вся LLM-работа - через провайдера.

Этапы (каждый резюмируем, jsonl + fsync):
  taxonomy  - справочник тем по выборке заголовков -> taxonomy.json (фиксируется руками)
  extract   - по каждой статье: релевантность + вопросы клиента (тема/тип/глубина/факты)
              + флаг сравнения винтовых блоков -> smysly.jsonl
  canon     - внутри темы сводит одинаковые вопросы всех сайтов в канонические -> canon.jsonl
  gaps      - покрытие: канон.вопрос -> наша глубина / конкуренты -> gaps-candidates.json
  verify    - каждый кандидат в пробелы сверяется с нашим блогом -> verify.jsonl
  vint      - сравнения винтовых блоков у конкурентов (полные тексты) -> vint.jsonl
  report    - итоговый отчёт BLOG-GAP-REPORT.md
python3 smysly.py <этап>
"""
import collections
import concurrent.futures as cf
import json
import os
import random
import re
import sys
import threading

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DIR))
import gen_provider as GP  # noqa: E402

OUR = 'prokompressor.ru'
MODEL = os.environ.get('SM_MODEL', 'claude-sonnet-5-5')
P = lambda n: os.path.join(DIR, n)  # noqa: E731
LOCK = threading.Lock()
DEPTH = {'upomyanuto': 1, 'raskryto': 2, 'raskryto_s_ciframi': 3}


def ask(prompt, max_tokens=8000):
    m = GP.call(None, [{'role': 'user', 'content': prompt}], model=MODEL, thinking_on=False,
                max_tokens=max_tokens)
    txt = m if isinstance(m, str) else ''.join(b.text for b in m.content if b.type == 'text')
    s = re.search(r'[\{\[].*[\}\]]', txt, re.S)
    return json.loads(s.group(0))


def jl(name):
    if not os.path.exists(P(name)):
        return []
    return [json.loads(l) for l in open(P(name), encoding='utf-8') if l.strip()]


def append(name, rec):
    with LOCK, open(P(name), 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        f.flush(); os.fsync(f.fileno())


def pages():
    out = {}
    for r in jl('pages.jsonl'):
        if not r.get('err') and (r.get('n_chars') or 0) >= 800:
            out[r['url']] = r
    return list(out.values())


# ---------- taxonomy
def st_taxonomy():
    ps = pages()
    random.seed(7)
    ours = [p for p in ps if p['domain'] == OUR]
    oth = random.sample([p for p in ps if p['domain'] != OUR], min(350, len(ps) - len(ours)))
    lines = '\n'.join(f"- {p['h1'] or p['title']} || {' / '.join(p['heads'][:8])}" for p in ours + oth)
    prompt = f"""Ниже заголовки статей из блогов компаний, продающих промышленные компрессоры,
осушители, генераторы азота и пневмооборудование (H1 || подзаголовки).
Составь СПРАВОЧНИК ТЕМ для разметки смыслов этих статей: 25-40 тем, взаимоисключающих,
каждая - предметная область, в которой клиент задаёт вопросы (например «Винтовой блок
(airend): устройство, производители, ресурс», «Расчёт производительности и подбор»).
Тему «не по профилю» (насосы, сварка, пескоструй, электроинструмент и т.п.) сделай одной
отдельной темой с id "off". Ответ строго JSON:
{{"topics":[{{"id":"латиница_коротко","name":"название","covers":"что сюда входит, 1 строка"}}]}}

{lines}"""
    tax = ask(prompt, 6000)
    json.dump(tax, open(P('taxonomy.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for t in tax['topics']:
        print(t['id'], '-', t['name'], '|', t['covers'])


# ---------- extract
EXTRACT = """Ты разбираешь статью из блога компании, продающей промышленные компрессоры и
пневмооборудование. Задача - выписать СМЫСЛЫ: вопросы клиента, на которые статья реально
отвечает.

Справочник тем (topic = id):
{tax}

Правила:
- relevant: 1 если статья про сжатый воздух/газы/компрессорную технику и смежное
  оборудование (осушители, фильтры, ресиверы, генераторы азота/кислорода, пневмолинии,
  дизельные передвижные компрессоры); 0 если не по профилю (тогда questions пустой).
- questions: 3-15 вопросов. Формулируй как вопрос клиента, общий и переносимый между
  сайтами («Как выбрать производительность компрессора под пневмоинструмент?»), без
  названия сайта. Не выдумывай: только то, на что в тексте есть ответ.
- type: vybor | sravnenie | raschet | ustroystvo | ekspluataciya | remont | normy | ekonomika | primenenie
- depth: upomyanuto (одна фраза) | raskryto (абзац+, есть объяснение) |
  raskryto_s_ciframi (есть конкретные числа, таблицы, расчёт)
- facts: до 3 ключевых утверждений/цифр ответа, коротко (для сверки), можно пусто.
- vint: 1 если в статье есть СРАВНЕНИЕ винтовых блоков (airend) - производителей
  (GHH, Rotorcomp, Baosi, Hanbell, Tamturbo, Air End и т.п.), типов профиля, ресурса,
  одно- и двухступенчатых, масляных и безмасляных блоков; иначе 0.
Ответ строго JSON:
{{"relevant":0|1,"vint":0|1,"questions":[{{"q":"...","topic":"id","type":"...","depth":"...","facts":["..."]}}]}}

URL: {url}
Заголовок: {h1}
Текст:
{text}"""


TOPIC = re.compile(r'компрессор|сжат\w* воздух|пневм|ресивер|осушит|азот|кислород|винтов|поршнев|'
                   r'конденсат|воздуходув|дожим|бустер|точк\w* рос|компрессорн|запчаст|обслуживан|сепаратор|'
                   r'масл\w* фильтр|remeza|atlas|kaeser|ingersoll|fini|abac|ceccato|dalgakiran|ekomak|'
                   r'comprag|boge|enger|berg', re.I)


def on_topic(p):
    # дешёвый предфильтр без провайдера: наши статьи - все; чужие - если тема видна в заголовках
    if p['domain'] == OUR:
        return True
    return bool(TOPIC.search(' '.join([p.get('title', ''), p.get('h1', '')] + p.get('heads', [])[:15])))


def st_extract():
    tax = json.load(open(P('taxonomy.json'), encoding='utf-8'))['topics']
    taxs = '\n'.join(f"{t['id']}: {t['name']} ({t['covers']})" for t in tax)
    ids = {t['id'] for t in tax}
    done = {r['url'] for r in jl('smysly.jsonl')}
    todo = [p for p in pages() if p['url'] not in done and on_topic(p)]
    todo.sort(key=lambda p: p['domain'] != OUR)  # наши первыми
    print(f'статей к разметке {len(todo)}, уже {len(done)}', flush=True)

    def one(p):
        try:
            r = ask(EXTRACT.format(tax=taxs, url=p['url'], h1=p['h1'] or p['title'],
                                   text=p['text'][:6000]), 3000)
        except Exception as e:
            print('ERR', p['url'], repr(e)[:120], flush=True)
            return
        qs = [q for q in r.get('questions', []) if isinstance(q, dict) and q.get('q')]
        for q in qs:
            if q.get('topic') not in ids:
                q['topic'] = 'other'
        append('smysly.jsonl', {'domain': p['domain'], 'url': p['url'], 'h1': p['h1'] or p['title'],
                                'relevant': int(r.get('relevant', 0)), 'vint': int(r.get('vint', 0)),
                                'questions': qs})

    with cf.ThreadPoolExecutor(int(os.environ.get('SM_THREADS', '6'))) as ex:
        for i, _ in enumerate(ex.map(one, todo), 1):
            if i % 50 == 0:
                print(i, flush=True)


# ---------- canon
CANON = """Ниже вопросы клиентов из статей разных сайтов, одна тема: «{name}».
Формат: N | вопрос. Сведи одинаковые ПО СУТИ вопросы в канонические (один канонический =
один ответ, который можно дать одной статьёй/разделом). Не объединяй разные по сути
(«как выбрать осушитель» и «точка росы для пищевки» - разные). Каждый N - ровно в одном
каноническом. Ответ строго JSON:
{{"canon":[{{"q":"канонический вопрос","n":[номера]}}]}}

{lines}"""


def st_canon():
    tax = {t['id']: t['name'] for t in json.load(open(P('taxonomy.json'), encoding='utf-8'))['topics']}
    tax['other'] = 'Прочее'
    items = collections.defaultdict(list)
    for r in jl('smysly.jsonl'):
        if not r['relevant']:
            continue
        for q in r['questions']:
            items[q['topic']].append({'q': q['q'], 'domain': r['domain'], 'url': r['url'],
                                      'depth': DEPTH.get(q.get('depth'), 1), 'type': q.get('type'),
                                      'facts': q.get('facts', [])})
    done = {r['topic'] for r in jl('canon.jsonl')}
    CH = 350

    def topic(tid):
        its = items[tid]
        if tid == 'off' or tid in done:
            return
        groups = []
        for s in range(0, len(its), CH):
            part = its[s:s + CH]
            lines = '\n'.join(f'{i} | {x["q"]}' for i, x in enumerate(part))
            res = ask(CANON.format(name=tax.get(tid, tid), lines=lines), 16000)
            for c in res['canon']:
                mem = [part[i] for i in c['n'] if isinstance(i, int) and 0 <= i < len(part)]
                if mem:
                    groups.append({'q': c['q'], 'members': mem})
        if len(its) > CH:  # второй проход: свести канонические разных кусков
            lines = '\n'.join(f'{i} | {g["q"]}' for i, g in enumerate(groups))
            res = ask(CANON.format(name=tax.get(tid, tid), lines=lines), 16000)
            merged = []
            for c in res['canon']:
                mem = [m for i in c['n'] if isinstance(i, int) and 0 <= i < len(groups)
                       for m in groups[i]['members']]
                if mem:
                    merged.append({'q': c['q'], 'members': mem})
            groups = merged
        append('canon.jsonl', {'topic': tid, 'name': tax.get(tid, tid), 'canon': groups})
        print(tid, len(its), '->', len(groups), flush=True)

    with cf.ThreadPoolExecutor(4) as ex:
        list(ex.map(topic, list(items)))


# ---------- gaps
def st_gaps():
    cands, stats = [], collections.Counter()
    for t in jl('canon.jsonl'):
        for c in t['canon']:
            our = max([m['depth'] for m in c['members'] if m['domain'] == OUR] or [0])
            comp = collections.defaultdict(lambda: {'depth': 0, 'url': ''})
            for m in c['members']:
                if m['domain'] != OUR and m['depth'] > comp[m['domain']]['depth']:
                    comp[m['domain']] = {'depth': m['depth'], 'url': m['url'], 'facts': m['facts']}
            if not comp:
                stats['tolko_u_nas'] += 1
                continue
            cdepth = max(v['depth'] for v in comp.values())
            if our >= 2 and our >= cdepth - 0:
                stats['zakryto'] += 1
                continue
            score = len(comp) * 2 + sum(v['depth'] for v in comp.values()) / max(1, len(comp)) - our * 2
            cands.append({'topic': t['topic'], 'topic_name': t['name'], 'q': c['q'], 'our_depth': our,
                          'n_comp': len(comp), 'comp_max_depth': cdepth, 'score': round(score, 2),
                          'comp': sorted(([d, v['depth'], v['url'], v.get('facts', [])] for d, v in comp.items()),
                                         key=lambda x: -x[1])})
            stats['kandidat'] += 1
    cands.sort(key=lambda x: -x['score'])
    json.dump(cands, open(P('gaps-candidates.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(dict(stats))


# ---------- verify
VERIFY = """Проверь, закрывает ли блог prokompressor.ru вопросы клиента. Ниже ВСЕ смыслы
нашего блога (URL | вопрос | глубина 1-3), затем вопросы-кандидаты. Для каждого кандидата
реши: net (в блоге нет ответа), chastichno (есть упоминание/поверхностно), zakryt (есть
полноценный ответ - укажи url). Учитывай синонимы и то, что вопрос мог быть сформулирован
иначе. Ответ строго JSON: {{"v":[[N,"net|chastichno|zakryt","url или пусто"]]}}

СМЫСЛЫ НАШЕГО БЛОГА:
{ours}

КАНДИДАТЫ:
{cands}"""


def st_verify():
    ours = '\n'.join(f"{r['url'].replace('https://prokompressor.ru', '')} | {q['q']} | {DEPTH.get(q.get('depth'), 1)}"
                     for r in jl('smysly.jsonl') if r['domain'] == OUR and r['relevant'] for q in r['questions'])
    cands = json.load(open(P('gaps-candidates.json'), encoding='utf-8'))
    done = {r['q'] for r in jl('verify.jsonl')}
    todo = [c for c in cands if c['q'] not in done]
    B = 40

    def batch(part):
        lines = '\n'.join(f"{i} | {c['q']}" for i, c in enumerate(part))
        res = ask(VERIFY.format(ours=ours, cands=lines), 6000)
        for row in res['v']:
            i = int(row[0])
            if 0 <= i < len(part):
                append('verify.jsonl', {'q': part[i]['q'], 'v': row[1], 'url': row[2] if len(row) > 2 else ''})

    with cf.ThreadPoolExecutor(4) as ex:
        list(ex.map(batch, [todo[s:s + B] for s in range(0, len(todo), B)]))
    print('проверено', len(jl('verify.jsonl')))


# ---------- vint
VINT = """Статья с сайта конкурента затрагивает сравнение винтовых блоков (airend) компрессоров.
Выпиши ВСЁ, что в ней говорится при сравнении: какие производители/типы блоков сравниваются,
по каким критериям, какие утверждения и цифры (ресурс, КПД, удельная мощность, обороты,
профиль роторов, подшипники, страна, цена, ремонтопригодность), какой вывод/кого продвигают.
Только из текста, без домыслов. Ответ строго JSON:
{{"sravnivayut":["..."],"kriterii":["..."],"utverzhdeniya":[{{"o_chem":"...","tezis":"...","cifry":"..."}}],
"vyvod":"...","kogo_prodvigayut":"..."}}

URL: {url}
Текст:
{text}"""


def st_vint():
    sm = {r['url']: r for r in jl('smysly.jsonl')}
    pg = {p['url']: p for p in pages()}
    kw = re.compile(r'винтов\w+ блок|airend|эйрэнд|GHH|Rotorcomp|Baosi|Hanbell|роторн\w+ пар', re.I)
    urls = [u for u, r in sm.items() if r['domain'] != OUR and (r['vint'] or kw.search(pg.get(u, {}).get('text', '')[:20000]) and r['relevant'])]
    done = {r['url'] for r in jl('vint.jsonl')}
    todo = [u for u in urls if u not in done and u in pg]
    print('статей о винтовых блоках', len(urls), 'к разбору', len(todo), flush=True)

    def one(u):
        try:
            r = ask(VINT.format(url=u, text=pg[u]['text'][:20000]), 4000)
        except Exception as e:
            print('ERR', u, repr(e)[:100], flush=True)
            return
        append('vint.jsonl', {'domain': pg[u]['domain'], 'url': u, 'h1': pg[u]['h1'], **r})

    with cf.ThreadPoolExecutor(6) as ex:
        list(ex.map(one, todo))


if __name__ == '__main__':
    {'taxonomy': st_taxonomy, 'extract': st_extract, 'canon': st_canon, 'gaps': st_gaps,
     'verify': st_verify, 'vint': st_vint}[sys.argv[1]]()
