#!/usr/bin/env python3
"""Кто приходит на площадку из поиска: решает модель по реальным запросам.

Словарь на этой задаче не работает - проверено. «Металлург» на vecherka74.ru это
хоккейный клуб, «производственный календарь» на dvobozrenie.ru - рабочие дни, а
«беседка из металла» на satom.ru - дача, а не металлообработка. Регулярка их
не отличает, поэтому запросы судит модель через провайдерский API.

На вход - топ-запросов домена по трафику (что реально приводит людей) плюс те,
где словарь увидел промышленное. На выход - вердикт и доля нашей аудитории.

    python3 classify_semantic.py [сколько доменов]
"""
from __future__ import annotations

import concurrent.futures as cf
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp                                    # noqa: E402

IND = ('компрессор','сжат воздух','сжатого возд','пневмо','сварк','станок','оборудован','азотн',
       'кислородн','осушител','ресивер','промышлен','производств','цех','завод','строитель',
       'монтаж','спецтехник','дизельн','электростанц','насос','котельн','металл','фрезер','токарн')

PROMPT = """Ты подбираешь площадки для гостевых статей поставщика промышленного
оборудования: винтовые и поршневые компрессоры, компрессорные станции, генераторы
азота и кислорода, осушители сжатого воздуха. Покупатель - главный инженер,
энергетик, снабженец завода, прораб, владелец автосервиса, фермер-хозяйственник.

Ниже РЕАЛЬНЫЕ поисковые запросы, по которым люди приходят на площадку из поиска,
с их трафиком. Это факт, а не заявленная тематика.

Ответь СТРОГО:
ВЕРДИКТ: наша | смежная | мимо
ДОЛЯ: <оценка в процентах, какая часть аудитории площадки - наш покупатель>
ПОЧЕМУ: <одна-две строки по конкретным запросам>

Как судить:
* «наша» - заметная часть запросов от людей, решающих производственную или
  строительно-монтажную задачу: оборудование, станки, сварка, сметы, монтаж,
  промышленные материалы.
* «смежная» - таких запросов мало, но аудитория рядом (стройка для частника,
  автомобили, дача с техникой).
* «мимо» - запросы про досуг, знаменитостей, праздники, здоровье, спорт, учёбу.
ВНИМАНИЕ на омонимы: «Металлург» бывает хоккейным клубом, «производственный
календарь» - это рабочие дни, «беседка из металла» - дача, а не металлообработка.

=== ЗАПРОСЫ ПЛОЩАДКИ ===
"""


def snapshot(rec):
    kws = rec.get('keywords') or []
    top = sorted(kws, key=lambda k: -float(k.get('traffic') or 0))[:35]
    ind = [k for k in kws if any(t in (k['kw'] or '').lower() for t in IND)][:35]
    out = [f"домен: {rec['domain']}", '', 'ТОП по трафику:']
    out += [f"  {k['kw']} — {k['traffic']}" for k in top]
    if ind:
        out += ['', 'где словарь увидел промышленное:']
        out += [f"  {k['kw']} — {k['traffic']}" for k in ind]
    return '\n'.join(out)


def one(rec):
    try:
        msg = gp.call(None, [{'role': 'user', 'content': PROMPT + snapshot(rec)}],
                      model='claude-fable-5', attempts=4)
        out = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception as e:                                   # noqa: BLE001
        return {'domain': rec['domain'], 'error': repr(e)[:120]}
    # Модель отвечает с markdown-разметкой: «ВЕРДИКТ: **наша**». Звёздочки снимаем,
    # иначе вердиктом становится «**» - так пропало 31 из 60 ответов.
    out = out.replace('*', '')
    g = lambda k: (re.search(rf'{k}:\s*(.+)', out) or [None, ''])[1].strip()
    v = g('ВЕРДИКТ').split()[0].lower() if g('ВЕРДИКТ') else '?'
    return {'domain': rec['domain'], 'verdict': v, 'share': g('ДОЛЯ'), 'why': g('ПОЧЕМУ')}


def main():
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    scores = {r['dom']: r for r in json.load(open('semantic-scores.json', encoding='utf-8'))}
    recs = {}
    for l in open('ahrefs-keywords-deep.jsonl', encoding='utf-8'):
        d = json.loads(l)
        if d.get('keywords') and (d['domain'] not in recs or
                                  len(d['keywords']) > len(recs[d['domain']]['keywords'])):
            recs[d['domain']] = d
    order = sorted(recs.values(), key=lambda r: -(scores.get(r['domain'], {}).get('share') or 0))
    todo = order[:lim]
    print(f'на разбор моделью: {len(todo)} доменов', flush=True)
    prev = {}
    if os.path.exists('semantic-verdicts.json'):
        for x in json.load(open('semantic-verdicts.json', encoding='utf-8')):
            if x.get('verdict') in ('наша', 'смежная', 'мимо'):
                prev[x['domain']] = x
    todo = [r for r in todo if r['domain'] not in prev]
    print(f'уже разобрано: {len(prev)}, осталось: {len(todo)}', flush=True)
    res = list(prev.values())
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(one, todo):
            res.append(r)
            print(f"  {r['domain']:26} {r.get('verdict','ERR'):9} {str(r.get('share',''))[:6]:>7}  "
                  f"{(r.get('why') or r.get('error') or '')[:60]}", flush=True)
    json.dump(res, open('semantic-verdicts.json', 'w'), ensure_ascii=False, indent=1)
    import collections
    print('\nитог:', dict(collections.Counter(r.get('verdict') for r in res)))


if __name__ == '__main__':
    main()
