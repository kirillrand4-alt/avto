#!/usr/bin/env python3
"""Фаза 1: агент оценивает фит площадки ко ВСЕМ нашим сайтам сразу.

Зачем не «пусть агент сам выберет сайт»: выберут все одно и то же. У prokompressor.ru
33 страницы из 58 и самая денежная позиция (72 152 ₽/мес) - любой агент, глядя только
на свою площадку, возьмёт максимум, и сателлиты не получат ничего. Хотя ссылка нужнее
как раз им: у страниц ac-kompressor.ru UR 0 и ноль внешних ссылок.

Поэтому агент не решает, а СУДИТ: даёт оценку 0-10 по каждому нашему сайту с лучшей
страницей и обоснованием. Распределение по квотам владельца делает код (`assign_jobs.py`),
максимизируя суммарный фит.

Урок первого прогона: агент видел только 8 самых денежных страниц, и для площадок
с бытовой аудиторией (дача, гараж) в выборке не было подходящего товара - весь топ
prokompressor.ru промышленный. Здесь список полный.

    python3 fit_score.py [донор ...]
"""
from __future__ import annotations

import concurrent.futures as cf
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen_provider as gp                                    # noqa: E402
from plan_jobs import GENRE, donor_block, load               # noqa: E402

OUT = os.environ.get('FIT_OUT', 'fit-scores.jsonl')
SITES = ['prokompressor.ru', 'enger-air.ru', 'berg-compressor.com',
         'dali-kompressor.ru', 'abac-kompressor.ru', 'ac-kompressor.ru']

PROMPT = """Ты подбираешь площадку под гостевую статью для поставщика промышленного
компрессорного оборудования (ООО «Руспром»): винтовые и поршневые компрессоры,
компрессорные станции, генераторы азота и кислорода, осушители, ресиверы.

Тебе дана ОДНА площадка-донор и ШЕСТЬ наших сайтов. Оцени, насколько органично статья
со ссылкой на каждый сайт легла бы на эту площадку. Статью писать не нужно.

=== ПЛОЩАДКА-ДОНОР ===
{donor_block}

=== НАШИ САЙТЫ И ИХ СТРАНИЦЫ ===
{sites_block}

=== КАК ОЦЕНИВАТЬ ===
9-10 - аудитория площадки прямо решает задачу, которую закрывает эта страница.
6-8  - аудитория смежная, честный мост есть (пример: студенческий журнал и азот
       в учебных лабораториях; туристический портал и кислородные станции в
       высокогорных отелях).
3-5  - мост существует, но требует натяжки; читатель площадки удивится теме.
0-2  - пересечения нет вообще, любой мост будет выдуманным.

Оценивай ЧЕСТНО. Низкая оценка - нормальный ответ, натянутый мост хуже отказа.
Одинаковые оценки всем сайтам бесполезны: нас интересует, какой из них ЛУЧШЕ
других ложится на эту конкретную аудиторию.

=== ФОРМАТ ОТВЕТА (строго, plain text, без markdown, ровно шесть строк) ===
prokompressor.ru | <0-10> | <URL лучшей страницы этого сайта> | <одна строка: почему>
enger-air.ru | <0-10> | <URL> | <почему>
berg-compressor.com | <0-10> | <URL> | <почему>
dali-kompressor.ru | <0-10> | <URL> | <почему>
abac-kompressor.ru | <0-10> | <URL> | <почему>
ac-kompressor.ru | <0-10> | <URL> | <почему>
"""


def sites_block(v15, pq):
    out = []
    for site in SITES:
        rows = [r for r in v15 if r['site'] == site]
        rows.sort(key=lambda r: -(float(r['money'] or 0)))
        out.append(f'--- {site} ---')
        for r in rows:
            q = pq.get((site, r['page']), {})
            themes = '; '.join(t['theme'] for t in (q.get('themes') or [])[:2] if t['theme'])
            money = int(float(r['money'] or 0))
            mark = f" | РУЧНОЙ ПРИОРИТЕТ ВЛАДЕЛЬЦА: {r['manual']}" if r.get('manual') else ''
            out.append(f"  {r['page']} | {money} ₽/мес | позиция {r['pos_google']}{mark}"
                       + (f" | темы: {themes}" if themes else ''))
    return '\n'.join(out)


def parse(raw):
    res = {}
    for line in raw.replace('*', '').split('\n'):
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 3 or parts[0] not in SITES:
            continue
        m = re.search(r'\d+', parts[1])
        if not m:
            continue
        res[parts[0]] = {'score': int(m.group()), 'page': parts[2],
                         'why': parts[3] if len(parts) > 3 else ''}
    return res


def one(args):
    dom, prompt = args
    try:
        msg = gp.call(None, [{'role': 'user', 'content': prompt}],
                      model='claude-fable-5', attempts=4)
        raw = ''.join(b.text for b in msg.content if b.type == 'text').strip()
    except Exception as e:                                   # noqa: BLE001
        return {'donor': dom, 'error': repr(e)[:150]}
    return {'donor': dom, 'fit': parse(raw), 'raw': raw}


def main():
    cards, v15, pq, sem, th = load()
    from plan_jobs import ASSIGN
    doms = sys.argv[1:] or list(ASSIGN)
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding='utf-8'):
            if line.strip():
                r = json.loads(line)
                if r.get('fit'):
                    done.add(r['donor'])
    todo = [d for d in doms if d not in done]
    print(f'доноров: {len(doms)} | готово: {len(done)} | к оценке: {len(todo)}', flush=True)
    sb = sites_block(v15, pq)
    tasks = [(d, PROMPT.format(donor_block=donor_block(d, cards, sem, th), sites_block=sb))
             for d in todo]
    f = open(OUT, 'a', encoding='utf-8')
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for rec in ex.map(one, tasks):
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush(); os.fsync(f.fileno())
            fit = rec.get('fit') or {}
            best = max(fit.items(), key=lambda kv: kv[1]['score']) if fit else None
            print('  %-28s %s | лучший: %s' % (
                rec['donor'],
                ' '.join('%s:%d' % (s.split('-')[0][:5], fit[s]['score']) for s in SITES if s in fit),
                f'{best[0]} {best[1]["score"]}/10' if best else rec.get('error', '')), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
