# -*- coding: utf-8 -*-
"""Прогон пула вариаций письма-1 через ревьюеров (6 линз cold-email в одном вызове)
и отбор 100 лучших: 0 CRITICAL + ранжирование по баллу. Через провайдера, параллельно."""
import os, sys, json, re
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider

D = os.path.dirname(os.path.abspath(__file__))
pool = json.load(open(os.path.join(D,'variations-pool.json'), encoding='utf-8'))
CACHE = os.path.join(D,'review-cache'); os.makedirs(CACHE, exist_ok=True)

RUBRIC = ("Оцени письмо ПЕРВОГО касания холодной B2B-рассылки по 6 линзам сразу и дай итог. "
 "Линзы: 1) доставляемость (тема есть, без спам-триггеров/КАПС, длина в экран); "
 "2) юрист ФЗ-38/152 (нет недостоверности/незаконной оферты; атрибуцию/отписку движок "
 "добавит — их отсутствие не минус); 3) факт-чек (5580+ и число проектов не выдуманы, "
 "внутренне согласованы); 4) корректор (нет опечаток/грамматики/оборванных фраз, НЕТ "
 "незаполненных {{плейсхолдеров}}, НЕТ длинных тире —); 5) адвокат ЛПР (релевантно, не "
 "раздражает, есть ценность/крючок, хочется ответить); 6) продажник (ровно один лёгкий "
 "вопрос/CTA, не в лоб). CRITICAL = что-то из: нет темы, опечатка/битая фраза, длинное "
 "тире, незаполненный плейсхолдер, выдуманная цифра, вводит в заблуждение, срыв CTA.")

def find_json(raw):
    m = re.search(r'\{.*\}', raw, re.S)
    return m.group(0) if m else None

def review_one(v):
    cf = os.path.join(CACHE, f"v{v['id']:03d}.json")
    if os.path.exists(cf):
        return json.load(open(cf))
    prompt = (f"{RUBRIC}\n\n=== ТЕМА ===\n{v.get('subject','')}\n\n=== ТЕЛО ===\n{v.get('body','')}\n\n"
        "Верни СТРОГО JSON без markdown: "
        '{"critical":[<список CRITICAL-проблем, пусто если нет>],'
        '"warn":[<мелкие замечания>],"score":<0-100 общая удачность>,'
        '"one_line":"<чем письмо хорошо/плохо>"}.')
    res = {'id': v['id'], 'critical':['review-failed'], 'score':0}
    for a in range(4):
        try:
            msg = gen_provider._raw_stream([{'role':'user','content':prompt}],'claude-fable-5',900,thinking=False)
            t = ''.join(b.text for b in msg.content if getattr(b,'type','')=='text')
            d = json.loads(find_json(t))
            res = {'id':v['id'],'critical':d.get('critical',[]) or [],
                   'warn':d.get('warn',[]) or [],'score':int(d.get('score',0)),
                   'one_line':d.get('one_line','')}
            break
        except Exception as e:
            if a==3: res['one_line']=f'err:{str(e)[:60]}'
    json.dump(res, open(cf,'w'), ensure_ascii=False)
    return res

if __name__ == '__main__':
    valid = [v for v in pool if v.get('body') and v.get('subject')]
    sys.stderr.write(f'вариаций в пуле: {len(pool)}, к ревью: {len(valid)}\n'); sys.stderr.flush()
    with ThreadPoolExecutor(max_workers=8) as ex:
        reviews = list(ex.map(review_one, valid))
    rmap = {r['id']: r for r in reviews}
    # чистые (0 CRITICAL) → сортировка по score; добираем разнообразие по бакетам
    clean = [v for v in valid if not rmap[v['id']]['critical']]
    clean.sort(key=lambda v: rmap[v['id']]['score'], reverse=True)
    # отбор 100 с балансом по бакетам (не более 5 из одного бакета сначала)
    picked, per_bucket = [], {}
    for v in clean:
        b = v.get('bucket')
        if per_bucket.get(b,0) < 5:
            picked.append(v); per_bucket[b] = per_bucket.get(b,0)+1
        if len(picked) >= 100: break
    if len(picked) < 100:  # добор без ограничения по бакету
        for v in clean:
            if v not in picked:
                picked.append(v)
            if len(picked) >= 100: break
    for v in picked:
        v['review'] = rmap[v['id']]
    json.dump(picked, open(os.path.join(D,'variations-100.json'),'w'), ensure_ascii=False, indent=1)
    sys.stderr.write(f'чистых (0 CRITICAL): {len(clean)} | отобрано: {len(picked)}\n')
    if picked:
        sc = [rmap[v['id']]['score'] for v in picked]
        sys.stderr.write(f'баллы отобранных: min {min(sc)} / max {max(sc)} / медиана {sorted(sc)[len(sc)//2]}\n')
