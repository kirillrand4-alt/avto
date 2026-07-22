# -*- coding: utf-8 -*-
"""Сравнение моделей на ПОЛНОЙ задаче extract_roles (email+роли+owner_match+конкурент+ЛПР+
активность) на УЖЕ КРАУЛЕННЫХ текстах. Эталон — fable (что сейчас в бою). Цель: если дешёвая
модель тянет так же → переключить массовый прогон = экономия ×N на КАЖДОМ сайте.
Плюс проверка БАТЧ-5 (5 текстов за 1 вызов) — падает ли качество.
Вход: roletext_recovered.json (записи с crawled_text). Запуск: python3 model_extract_test.py [N]
"""
import os, sys, json, re, time, pathlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G

SCR = pathlib.Path('/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad')
CACHE = SCR / 'mextract_cache'
CACHE.mkdir(parents=True, exist_ok=True)
# цена $/1М (вход, выход)
PRICE = {'claude-fable-5': (10, 50), 'claude-opus-4-8': (5, 25),
         'claude-sonnet-5': (3, 15), 'claude-haiku-4-5': (1, 5)}
MODELS = ['claude-fable-5', 'claude-haiku-4-5', 'claude-sonnet-5', 'claude-opus-4-8']

PROMPT = (
    'Из текста сайта компании извлеки контакты С РОЛЯМИ и ПОДТВЕРДИ, что сайт принадлежит '
    'именно этой компании. Компания: «{name}»{inn}{city}. '
    'Также определи по тексту, ЧЕМ занимается компания, и НЕ является ли она сама '
    'производителем/продавцом компрессоров, насосов, компрессорного оборудования '
    '(тогда это КОНКУРЕНТ). Верни СТРОГО JSON без markdown: '
    '{{"owner_match":true/false,"activity":"1 фраза",'
    '"is_compressor_maker":true/false,'
    '"emails":[{{"email":"","role":"директор|снабжение/закупки|гл.инженер|продажи|'
    'бухгалтерия|приёмная|общий","person":""}}],'
    '"best_for_outreach":"email ЛПР (закупки>гл.инженер>директор>продажи>общий)"}}. Текст:\n{text}')


def call_model(prompt, model, max_tokens=1500):
    for _ in range(3):
        try:
            msg = G._raw_stream([{'role': 'user', 'content': prompt}], model, max_tokens, thinking=False)
            out = ''.join(b.text for b in msg.content if b.type == 'text')
            m = re.search(r'\{.*\}', out, re.S)
            if m:
                return json.loads(m.group(0)), len(prompt), len(out)
        except Exception:
            time.sleep(2)
    return None, len(prompt), 0


def one_prompt(rec):
    c = {'name': rec.get('name', ''), 'inn': rec.get('inn', '')}
    return PROMPT.format(name=c['name'],
                         inn=f", ИНН {c['inn']}" if c['inn'] else '',
                         city='', text=(rec.get('crawled_text') or '')[:24000])


def norm_role(r):
    r = (r or '').lower()
    for k, v in (('закуп', 'зк'), ('снабж', 'зк'), ('прода', 'пр'), ('сбыт', 'пр'),
                 ('директ', 'дир'), ('инженер', 'инж'), ('бухгалт', 'бх'),
                 ('приём', 'об'), ('приемн', 'об'), ('общ', 'об')):
        if k in r:
            return v
    return r[:4]


def emails_of(d):
    return {(e.get('email') or '').lower().strip() for e in (d.get('emails') or []) if e.get('email')}


def roles_map(d):
    return {(e.get('email') or '').lower().strip(): norm_role(e.get('role')) for e in (d.get('emails') or [])}


def compare(ref, cand):
    """Согласие кандидата с эталоном по ключевым полям. Возвращает dict метрик."""
    re_, ce = emails_of(ref), emails_of(cand)
    inter = re_ & ce
    email_recall = len(inter) / max(1, len(re_))          # нашла ли те же email
    rr, cr = roles_map(ref), roles_map(cand)
    role_match = sum(1 for e in inter if rr.get(e) == cr.get(e)) / max(1, len(inter))
    owner = int(bool(ref.get('owner_match')) == bool(cand.get('owner_match')))
    comp = int(bool(ref.get('is_compressor_maker')) == bool(cand.get('is_compressor_maker')))
    lpr = int((ref.get('best_for_outreach') or '').lower() == (cand.get('best_for_outreach') or '').lower())
    return {'email_recall': email_recall, 'role_match': role_match,
            'owner_match': owner, 'competitor_match': comp, 'lpr_match': lpr}


def main():
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    recs = [r for r in json.load(open(SCR / 'roletext_recovered.json')) if r.get('crawled_text')][:N]
    print(f'текстов: {len(recs)}', flush=True)
    # 1) прогон каждой модели по 1 тексту/вызов
    per_cost = {m: 0.0 for m in MODELS}
    outs = {}   # inn -> {model -> parsed}
    for i, rec in enumerate(recs):
        inn = str(rec.get('inn') or i)
        outs[inn] = {}
        pr = one_prompt(rec)
        for model in MODELS:
            cf = CACHE / f'{inn}_{model}.json'
            if cf.exists():
                d = json.loads(cf.read_text())
            else:
                parsed, cin, cout = call_model(pr, model)
                d = {'parsed': parsed, 'in': cin, 'out': cout}
                cf.write_text(json.dumps(d, ensure_ascii=False))
            outs[inn][model] = d
            pin, pout = PRICE[model]
            per_cost[model] += d['in'] / 3 / 1e6 * pin + d['out'] / 3 / 1e6 * pout
        print(f'[{i+1}/{len(recs)}] {rec.get("name","")[:32]}', flush=True)
    # 2) метрики каждой модели vs fable
    ref_m = 'claude-fable-5'
    report = {'texts': len(recs), 'per_model': {}}
    for model in MODELS:
        agg = {'email_recall': [], 'role_match': [], 'owner_match': [], 'competitor_match': [], 'lpr_match': []}
        for inn in outs:
            ref = outs[inn][ref_m]['parsed']
            cand = outs[inn][model]['parsed']
            if not ref or not cand:
                continue
            c = compare(ref, cand)
            for k in agg:
                agg[k].append(c[k])
        report['per_model'][model] = {k: round(100 * sum(v) / max(1, len(v)), 1) for k, v in agg.items()}
        report['per_model'][model]['est_cost_usd_per_text'] = round(per_cost[model] / max(1, len(recs)), 5)
    # 3) рекомендация: дешёвая модель, если ключевые метрики близки к fable (эталон=100)
    rec_model = ref_m
    for model in ('claude-haiku-4-5', 'claude-sonnet-5', 'claude-opus-4-8'):
        pm = report['per_model'][model]
        # порог: email_recall≥90, role_match≥85, owner/competitor≥90
        if (pm['email_recall'] >= 90 and pm['role_match'] >= 85
                and pm['owner_match'] >= 90 and pm['competitor_match'] >= 90):
            rec_model = model
            break
    report['recommendation'] = rec_model
    fc = report['per_model'][ref_m]['est_cost_usd_per_text']
    rc = report['per_model'][rec_model]['est_cost_usd_per_text']
    report['economy'] = f'{fc/max(rc,1e-9):.1f}x дешевле' if rec_model != ref_m else 'нет (fable)'
    (SCR / 'model_extract_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print('\n=== ИТОГ (extract_roles, эталон fable=100%) ===', flush=True)
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
    print(f'\nРЕКОМЕНДАЦИЯ: {rec_model} ({report["economy"]})', flush=True)


if __name__ == '__main__':
    main()
