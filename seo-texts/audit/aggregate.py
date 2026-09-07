# -*- coding: utf-8 -*-
"""Этап 3: сводка по карточкам ревью + механике в одну таблицу и очереди работ."""
import json, os, glob, csv, collections

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    chk = {json.loads(l)['url']: json.loads(l)
           for l in open(os.path.join(HERE, 'checks.jsonl'), encoding='utf-8')}
    keys = json.load(open(os.path.join(HERE, 'keys-by-url.json')))
    rows, findings = [], []
    for f in sorted(glob.glob(os.path.join(HERE, 'reviews', '*.json'))):
        d = json.load(open(f))
        u = d['url']
        c = chk.get(u, {})
        k = keys.get(u, {})
        b = d.get('blocks', {})
        st = lambda n: (b.get(n) or {}).get('status', '')
        fs = d.get('findings', [])
        rows.append({
            'url': u.replace('https://prokompressor.ru', ''),
            'вердикт': d.get('verdict', ''),
            'приоритет': c.get('priority', ''),
            'показы': c.get('shows', 0),
            'клики': c.get('clicks', 0),
            'недобор_кликов': c.get('ctr_gap_clicks', 0),
            'статья': st('1_nalichie'), 'соответствие': st('2_sootvetstvie'),
            'выбор': st('3_vybor'), 'метатеги': st('4_metategi'),
            'достоверность': st('5_dostovernost'), 'ссылки': st('6_ssylki'),
            'каннибализация': st('7_kannibalizaciya'),
            'критично': sum(1 for x in fs if x.get('severity') == 'КРИТИЧНО'),
            'внимание': sum(1 for x in fs if x.get('severity') == 'ВНИМАНИЕ'),
            'проверить': sum(1 for x in fs if x.get('severity') == 'ПРОВЕРИТЬ'),
            'почему': d.get('verdict_why', '')[:200],
        })
        for x in fs:
            findings.append({'url': rows[-1]['url'], 'блок': x.get('block', ''),
                             'тяжесть': x.get('severity', ''),
                             'цитата': (x.get('citation') or '').replace('\n', ' ')[:300],
                             'почему': (x.get('why') or '').replace('\n', ' ')[:400],
                             'что_делать': (x.get('fix') or '').replace('\n', ' ')[:300]})
    rows.sort(key=lambda r: (r['приоритет'] if r['приоритет'] != '' else 9, -r['показы']))

    def dump(name, data):
        if not data:
            return
        w = csv.DictWriter(open(os.path.join(HERE, name), 'w', encoding='utf-8-sig', newline=''),
                           fieldnames=list(data[0]), delimiter=';')
        w.writeheader(); w.writerows(data)
        print(name, len(data), 'строк')

    dump('results.csv', rows)
    dump('findings.csv', findings)

    V = collections.Counter(r['вердикт'] for r in rows)
    print('\nстраниц с ревью:', len(rows))
    print('вердикты:', dict(V))
    print('находки: критично', sum(r['критично'] for r in rows),
          '| внимание', sum(r['внимание'] for r in rows),
          '| проверить', sum(r['проверить'] for r in rows))
    print('\nстатусы по блокам:')
    for col in ('статья', 'соответствие', 'выбор', 'метатеги', 'достоверность', 'ссылки', 'каннибализация'):
        c = collections.Counter(r[col] for r in rows)
        print(f"  {col:<16} ОК {c.get('ОК',0):>3} | ВНИМАНИЕ {c.get('ВНИМАНИЕ',0):>3} | КРИТИЧНО {c.get('КРИТИЧНО',0):>3}")
    print('\nтоп-15 по показам среди ПЕРЕГЕНЕРАЦИЯ:')
    for r in [x for x in rows if x['вердикт'] == 'ПЕРЕГЕНЕРАЦИЯ'][:15]:
        print(f"  {r['показы']:>6} пок  крит {r['критично']:>2}  {r['url']}")


if __name__ == '__main__':
    main()
