# -*- coding: utf-8 -*-
"""Ревью пула вариаций и отбор 100 лучших. На письмо — один компактный вызов-судья
(линзы: доставляемость/юр/факт/корректор/ЛПР/CTA) → verdict+балл+проблемы.
Резюмируемо (кэш на письмо). CRITICAL отбрасываем, топ-100 по баллу → variations-100.json."""
import os, sys, json, re
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider

D = os.path.dirname(os.path.abspath(__file__))
RC = os.path.join(D, 'review-cache'); os.makedirs(RC, exist_ok=True)
POOL = json.load(open(os.path.join(D, 'variations-pool.json'), encoding='utf-8'))

JUDGE = """Ты — конвейер ревью холодного письма первого касания (первое касание B2B).
Прогони письмо через линзы и верни ОБЩИЙ вердикт:
- Доставляемость: есть тема; нет спам-триггеров/КАПС/«!»; 1 экран.
- Юр ФЗ-38/152: нет недостоверных утверждений/незаконной оферты (атрибуцию/отписку движок ставит — не требуй).
- Факт: цифры только 5580+ и число проектов в регионе; никаких выдуманных фактов о клиенте.
- Корректор: НЕТ опечаток, НЕТ длинных тире (—), НЕТ незаполненных {{плейсхолдеров}}, читаемо.
- ЛПР: релевантно адресату, есть ценность/крючок, не раздражает.
- CTA: РОВНО один лёгкий вопрос/шаг.
CRITICAL если: нет темы / опечатка / длинное тире / плейсхолдер / выдуманный факт / спам-вид / нет внятного CTA.
Верни СТРОГО JSON без markdown: {"verdict":"PASS|WARN|CRITICAL","score":0-100,"problems":[".."]}.
score — общая пригодность к отправке (100 — идеально)."""

def review(v):
    cf = os.path.join(RC, f"{v['id']}.json")
    if os.path.exists(cf):
        try: return json.load(open(cf))
        except Exception: pass
    prompt = (f"{JUDGE}\n\n=== ТЕМА ===\n{v.get('subject')}\n\n=== ТЕЛО ===\n{v.get('body')}\n\n"
              f"(адресат: {v.get('role')}; оборудование: {v.get('equipment')}; отрасль: {v.get('industry')})")
    res = {'id': v['id'], 'verdict': 'WARN', 'score': 0, 'problems': ['no-parse']}
    for a in range(4):
        try:
            msg = gen_provider._raw_stream([{'role':'user','content':prompt}],'claude-fable-5',900,thinking=False)
            t = ''.join(b.text for b in msg.content if getattr(b,'type','')=='text')
            m = re.search(r'\{.*\}', t, re.S)
            d = json.loads(m.group(0))
            res = {'id': v['id'], 'verdict': str(d.get('verdict','WARN')).upper(),
                   'score': int(d.get('score',0) or 0), 'problems': d.get('problems',[])}
            break
        except Exception:
            continue
    json.dump(res, open(cf,'w'), ensure_ascii=False)
    return res

if __name__ == '__main__':
    sys.stderr.write(f'писем в пуле: {len(POOL)}\n'); sys.stderr.flush()
    with ThreadPoolExecutor(max_workers=8) as ex:
        reviews = list(ex.map(review, POOL))
    by_id = {r['id']: r for r in reviews}
    clean = [v for v in POOL if by_id.get(v['id'],{}).get('verdict') != 'CRITICAL']
    clean.sort(key=lambda v: by_id[v['id']]['score'], reverse=True)
    top = clean[:100]
    for v in top:
        v['review'] = by_id[v['id']]
    json.dump(top, open(os.path.join(D,'variations-100.json'),'w'), ensure_ascii=False, indent=1)
    crit = sum(1 for r in reviews if r['verdict']=='CRITICAL')
    passed = sum(1 for r in reviews if r['verdict']=='PASS')
    avg = round(sum(by_id[v['id']]['score'] for v in top)/max(1,len(top)),1)
    sys.stderr.write(f'ГОТОВО: PASS {passed}, CRITICAL {crit}, отобрано {len(top)}, средний балл топ-100: {avg}\n')
