# -*- coding: utf-8 -*-
"""Задача 4: сравнить fable/sonnet/haiku/opus на извлечении ролей из реальных текстов сайтов.
Тот же extract_roles-промпт через 4 модели → метрики согласия с fable (текущая прод-модель).
Запуск: python3 model_compare.py <texts.json>  (нужен PROVIDER_API_KEY). Резюмируемо (кэш).
"""
import os, sys, json, re, time, pathlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G

SCR = pathlib.Path('/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad')
CACHE = SCR / 'modelcmp_cache'
CACHE.mkdir(parents=True, exist_ok=True)
MODELS = ['claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-5', 'claude-haiku-4-5']
# цена $/1M (офиц.): in, out — для оценки; router.cheap дешевле, но пропорции те же
PRICE = {'claude-fable-5': (10, 50), 'claude-opus-4-8': (5, 25),
         'claude-sonnet-5': (3, 15), 'claude-haiku-4-5': (1, 5)}
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


def build_prompt(text, company):
    return (
        'Из текста сайта компании извлеки контакты С РОЛЯМИ и ПОДТВЕРДИ, что сайт '
        f'принадлежит именно этой компании. Компания: «{company.get("name","")}»'
        + (f', ИНН {company.get("inn")}' if company.get('inn') else '')
        + (f', город {company.get("city")}' if company.get('city') else '') + '. '
        'Также определи по тексту главной, ЧЕМ занимается компания, и НЕ является ли она '
        'сама производителем/продавцом компрессоров, насосов, компрессорного оборудования '
        '(тогда это КОНКУРЕНТ, а не покупатель — таким не пишем). '
        'Верни СТРОГО JSON без markdown: '
        '{"owner_match":true/false,"owner_reason":"почему сайт этой/не этой компании",'
        '"activity":"1 короткая фраза чем занимается компания (для персонализации письма)",'
        '"is_compressor_maker":true/false,'
        '"emails":[{"email":"","role":"директор|снабжение/закупки|гл.инженер|'
        'продажи|бухгалтерия|приёмная|общий","person":"ФИО или пусто"}],'
        '"phones":[""],"best_for_outreach":"email ЛПР для холодного письма '
        '(приоритет закупки>гл.инженер>директор>продажи>общий)"}. '
        'owner_match=false если сайт — агрегатор/каталог/тёзка/другая фирма. '
        'Бери только email этой компании (её домен), не сторонние. Текст:\n' + text[:24000])


def run_model(client, prompt, model):
    # thinking=False — как в проде (extract_via_provider): fable без явного thinking-конфига,
    # чистый JSON без пустого text-после-thinking. max_tokens 2000 хватает на JSON ролей.
    t0 = time.time()
    txt = ''
    for att in range(4):
        try:
            msg = G._raw_stream([{'role': 'user', 'content': prompt}], model, 2000, thinking=False)
            txt = ''.join(b.text for b in msg.content if b.type == 'text')
            if txt.strip():
                break
        except Exception:
            time.sleep(2 + att * 2)
    dt = time.time() - t0
    m = re.search(r'\{.*\}', txt, re.S)
    data = json.loads(m.group(0)) if m else {}
    return data, dt


def norm_emails(data):
    return set((e.get('email') or '').strip().lower() for e in (data.get('emails') or []) if e.get('email'))


def roles_map(data):
    return {(e.get('email') or '').strip().lower(): (e.get('role') or '').strip().lower()
            for e in (data.get('emails') or []) if e.get('email')}


def jaccard(a, b):
    if not a and not b:
        return 1.0
    u = a | b
    return len(a & b) / len(u) if u else 1.0


def main():
    texts_path = sys.argv[1] if len(sys.argv) > 1 else str(SCR / 'texts.json')
    d = json.load(open(texts_path))
    res = d.get('data', {}).get('results', [])
    samples = [r for r in res if r.get('crawled_text') and EMAIL_RE.search(r.get('crawled_text', ''))]
    print(f'текстов с email: {len(samples)}', flush=True)
    client = G.make_client()
    per_model = {m: [] for m in MODELS}
    outputs = {}  # inn -> {model -> data}
    for si, s in enumerate(samples):
        inn = str(s.get('inn') or si)
        prompt = build_prompt(s['crawled_text'], s)
        outputs[inn] = {'name': s.get('name'), 'models': {}}
        for model in MODELS:
            cf = CACHE / f'{inn}_{model}.json'
            if cf.exists():
                try:
                    rec = json.loads(cf.read_text())
                except Exception:
                    rec = None
            else:
                rec = None
            if rec is None:
                try:
                    data, dt = run_model(client, prompt, model)
                    # оценка токенов вход/выход по символам/3
                    rec = {'data': data, 'sec': round(dt, 1),
                           'in_chars': len(prompt), 'out_chars': len(json.dumps(data, ensure_ascii=False))}
                except Exception as e:
                    rec = {'error': str(e)[:120], 'sec': 0, 'in_chars': len(prompt), 'out_chars': 0}
                cf.write_text(json.dumps(rec, ensure_ascii=False))
            per_model[model].append(rec)
            outputs[inn]['models'][model] = rec
        print(f'[{si+1}/{len(samples)}] {s.get("name","")[:40]} — прогнан через 4 модели', flush=True)

    # метрики: сравнение каждой модели с fable (прод-эталон)
    ref = 'claude-fable-5'
    report = {'n_samples': len(samples), 'per_model': {}}
    for model in MODELS:
        emails_j, role_agree, comp_agree, owner_agree, best_agree = [], [], [], [], []
        secs, cost = [], 0.0
        n_email_found = 0
        for inn, rec in outputs.items():
            r_ref = rec['models'][ref].get('data', {})
            r_m = rec['models'][model].get('data', {})
            if rec['models'][model].get('error'):
                continue
            em_ref, em_m = norm_emails(r_ref), norm_emails(r_m)
            if em_m:
                n_email_found += 1
            emails_j.append(jaccard(em_ref, em_m))
            rm_ref, rm_m = roles_map(r_ref), roles_map(r_m)
            shared = set(rm_ref) & set(rm_m)
            if shared:
                role_agree.append(sum(1 for e in shared if rm_ref[e] == rm_m[e]) / len(shared))
            comp_agree.append(1.0 if r_ref.get('is_compressor_maker') == r_m.get('is_compressor_maker') else 0.0)
            owner_agree.append(1.0 if r_ref.get('owner_match') == r_m.get('owner_match') else 0.0)
            best_agree.append(1.0 if (r_ref.get('best_for_outreach') or '').lower()
                              == (r_m.get('best_for_outreach') or '').lower() else 0.0)
            secs.append(rec['models'][model].get('sec', 0))
            pin, pout = PRICE[model]
            cost += rec['models'][model].get('in_chars', 0) / 3 / 1e6 * pin
            cost += rec['models'][model].get('out_chars', 0) / 3 / 1e6 * pout

        def avg(x):
            return round(sum(x) / len(x), 3) if x else None
        report['per_model'][model] = {
            'email_jaccard_vs_fable': avg(emails_j),
            'role_agree_vs_fable': avg(role_agree),
            'competitor_flag_agree': avg(comp_agree),
            'owner_match_agree': avg(owner_agree),
            'best_lpr_agree': avg(best_agree),
            'found_emails_in': f'{n_email_found}/{len(samples)}',
            'avg_sec': avg(secs),
            'est_cost_usd_official': round(cost, 4),
        }
    out_f = SCR / 'model_compare_report.json'
    out_f.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print('\n=== ИТОГ (согласие с fable-5) ===', flush=True)
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
    # также сохраним полные выводы для ручного спот-чека
    (SCR / 'model_compare_outputs.json').write_text(json.dumps(outputs, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
