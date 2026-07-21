# -*- coding: utf-8 -*-
"""Тест: как fable vs дешёвые модели справляются с РОЛЬЮ для «каши» (email без
детерминированной роли — то, что экстрактор отдаёт LLM). Эталон — fable.
Решение: если дешёвая модель в пределах ±5% согласия с fable → рекомендуем её.
Вход: enrich-вывод с crawled_text. Запуск: python3 role_model_test.py <texts.json> [N]
"""
import os, sys, json, re, time, pathlib
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contact_extract as CE
import gen_provider as G

SCR = pathlib.Path('/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad')
CACHE = SCR / 'rolecmp_cache'
CACHE.mkdir(parents=True, exist_ok=True)
MODELS = ['claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-5', 'claude-haiku-4-5']
PRICE = {'claude-fable-5': (10, 50), 'claude-opus-4-8': (5, 25),
         'claude-sonnet-5': (3, 15), 'claude-haiku-4-5': (1, 5)}


def resolve(kasha, text, company, model):
    prompt = (f'Компания «{company.get("name","")}». Для КАЖДОГО email определи роль владельца '
              f'по тексту сайта: снабжение/закупки | продажи | директор | гл.инженер | бухгалтерия | '
              f'кадры | общий/приёмная. Email: {", ".join(kasha)}. Верни СТРОГО JSON '
              f'{{"roles":{{"email":"роль"}}}}. Текст:\n' + (text or "")[:12000])
    t0 = time.time()
    for _ in range(3):
        try:
            msg = G._raw_stream([{'role': 'user', 'content': prompt}], model, 1200, thinking=False)
            out = ''.join(b.text for b in msg.content if b.type == 'text')
            m = re.search(r'\{.*\}', out, re.S)
            if m:
                return json.loads(m.group(0)).get('roles', {}), len(prompt), len(out), time.time() - t0
        except Exception:
            time.sleep(2)
    return {}, len(prompt), 0, time.time() - t0


def norm_role(r):
    r = (r or '').lower()
    for key in ('закуп', 'снабж', 'прода', 'сбыт', 'директор', 'инженер', 'бухгалт', 'кадр', 'приём', 'приемн', 'общий'):
        if key in r:
            return {'закуп': 'закуп', 'снабж': 'закуп', 'прода': 'прод', 'сбыт': 'прод',
                    'директор': 'дир', 'инженер': 'инж', 'бухгалт': 'бух', 'кадр': 'кадр',
                    'приём': 'общ', 'приемн': 'общ', 'общий': 'общ'}[key]
    return r[:6]


def main():
    texts_path = sys.argv[1]
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    d = json.load(open(texts_path))
    res = d.get('data', {}).get('results') if 'data' in d else d.get('results', d)
    # собрать образцы каши: (company, text, [kasha emails])
    samples = []
    for r in (res or []):
        text = r.get('crawled_text') or ''
        if not text:
            continue
        ex = CE.extract(text)  # extract на тексте (html=text здесь; mailto уже нет, но текст+обфускация ловятся)
        kasha = ex.get('kasha') or []
        if kasha:
            samples.append({'company': {'inn': r.get('inn'), 'name': r.get('name')},
                            'text': text, 'kasha': kasha[:6]})
        if sum(len(s['kasha']) for s in samples) >= target:
            break
    n_kasha = sum(len(s['kasha']) for s in samples)
    print(f'образцов-сайтов: {len(samples)} | email-каши: {n_kasha}', flush=True)

    outputs = {}  # inn -> {model -> roles}
    per_cost = {m: 0.0 for m in MODELS}
    per_sec = {m: [] for m in MODELS}
    for si, s in enumerate(samples):
        inn = str(s['company'].get('inn') or si)
        outputs[inn] = {'kasha': s['kasha'], 'models': {}}
        for model in MODELS:
            cf = CACHE / f'{inn}_{model}.json'
            if cf.exists():
                rec = json.loads(cf.read_text())
            else:
                roles, cin, cout, sec = resolve(s['kasha'], s['text'], s['company'], model)
                rec = {'roles': roles, 'in': cin, 'out': cout, 'sec': round(sec, 1)}
                cf.write_text(json.dumps(rec, ensure_ascii=False))
            outputs[inn]['models'][model] = rec
            pin, pout = PRICE[model]
            per_cost[model] += rec['in'] / 3 / 1e6 * pin + rec['out'] / 3 / 1e6 * pout
            per_sec[model].append(rec['sec'])
        print(f'[{si+1}/{len(samples)}] {s["company"].get("name","")[:34]} — {len(s["kasha"])} каши × 4 модели', flush=True)

    ref = 'claude-fable-5'
    report = {'sites': len(samples), 'kasha_emails': n_kasha, 'per_model': {}}
    for model in MODELS:
        agree, total, resolved = 0, 0, 0
        for inn, rec in outputs.items():
            rr = rec['models'][ref]['roles']
            rm = rec['models'][model]['roles']
            for em in rec['kasha']:
                rv = rm.get(em) or rm.get(em.lower())
                if rv:
                    resolved += 1
                fv = rr.get(em) or rr.get(em.lower())
                if fv and rv:
                    total += 1
                    if norm_role(fv) == norm_role(rv):
                        agree += 1
        report['per_model'][model] = {
            'role_agree_vs_fable_pct': round(100 * agree / total, 1) if total else None,
            'resolved_pct': round(100 * resolved / max(1, n_kasha), 1),
            'avg_sec': round(sum(per_sec[model]) / max(1, len(per_sec[model])), 1),
            'est_cost_usd': round(per_cost[model], 4),
        }
    # решение: дешёвая в пределах 5% от fable (100%) → рекомендуем
    rec_model = ref
    for model in ('claude-haiku-4-5', 'claude-sonnet-5', 'claude-opus-4-8'):
        a = report['per_model'][model]['role_agree_vs_fable_pct']
        if a is not None and a >= 95.0:
            rec_model = model
            break
    report['recommendation'] = rec_model
    (SCR / 'role_model_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print('\n=== ИТОГ (роль каши, эталон fable) ===', flush=True)
    print(json.dumps(report, ensure_ascii=False, indent=1), flush=True)
    print(f'\nРЕКОМЕНДАЦИЯ: {rec_model}', flush=True)


if __name__ == '__main__':
    main()
