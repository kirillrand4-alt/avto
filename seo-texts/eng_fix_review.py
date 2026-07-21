# -*- coding: utf-8 -*-
"""Ревью КОРРЕКТНОСТИ фиксов инженера через провайдера (sonnet-5).
По каждому фикс-коммиту: правильно ли и ПОЛНО ли закрыт баг, нет ли поверхностного/
регрессивного фикса. Диффы берём из репо (коммиты уже fetched). Запуск: python3 eng_fix_review.py
"""
import os, sys, json, re, time, subprocess, pathlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G

ROOT = '/home/user/avto'
SCR = pathlib.Path('/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad')
COMMITS = [
    ('4589553', 'П1 ЮРИДИКА ФЗ-38: нормализация email, вечная отписка, честный one-click, has_reply перед SMTP, атрибуция'),
    ('8bcf449', 'П2 ДОСТАВЛЯЕМОСТЬ: STARTTLS 587, CRLF-санация, fail-safe паузы/гейтов, bounce по получателю, day_key зоны'),
    ('51ae558', 'П3 MEDIUM: XSS-экранирование, лимит Content-Length, RCPT-страховка, extra_json, suppressed-заслон, пиксель-URL'),
]
PROMPT = """Ты — придирчивый ревьюер безопасности/корректности самописного B2B cold-email рассыльщика (РФ, ФЗ-38:
отписка соблюдается НАВСЕГДА). Ниже — ДИФФ фикс-коммита «%s». Это ИСПРАВЛЕНИЯ ранее найденных багов.

Проверь КАЖДОЕ изменение: (1) реально ли оно закрывает заявленный дефект (не симптом/не косметика);
(2) ПОЛНО ли (нет пропущенного пути обхода, гонки, второй точки, где баг остаётся);
(3) не вносит ли РЕГРЕССИЮ (сломанное поведение/новый баг).

Верни СТРОГО JSON: {"verdicts":[{"area":"<файл:тема>","status":"ok|incomplete|wrong|regression",
"why":"<одно предложение по коду>","residual":"<что ещё остаётся/нужно, или пусто>"}],
"overall":"<1-2 предложения: можно ли считать приоритет закрытым>"}
Будь конкретным по коду. Не хвали — ищи дыры. Дифф:
```
%s
```"""


def review(commit, desc):
    diff = subprocess.run(['git', '-C', ROOT, 'show', commit, '--', '*.py', ':!*/tests/*'],
                          capture_output=True, text=True).stdout[:60000]
    prompt = PROMPT % (desc, diff)
    for _ in range(4):
        try:
            msg = G._raw_stream([{'role': 'user', 'content': prompt}], 'claude-sonnet-5', 4000, thinking=False)
            txt = ''.join(b.text for b in msg.content if b.type == 'text')
            m = re.search(r'\{.*\}', txt, re.S)
            if m:
                return json.loads(m.group(0))
        except Exception:
            time.sleep(3)
    return {'error': 'no-output'}


def main():
    rep = {}
    for c, desc in COMMITS:
        print(f'ревью {c} ({desc[:30]}) ...', flush=True)
        rep[c] = {'desc': desc, 'review': review(c, desc)}
        v = rep[c]['review'].get('verdicts', []) if isinstance(rep[c]['review'], dict) else []
        bad = [x for x in v if x.get('status') in ('incomplete', 'wrong', 'regression')]
        print(f"  -> {len(v)} вердиктов, проблемных: {len(bad)}", flush=True)
    (SCR / 'eng_fix_review.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print('\n=== СВОД ===', flush=True)
    for c, d in rep.items():
        r = d['review']
        print(f"\n{c} — {d['desc'][:50]}", flush=True)
        print('  overall:', r.get('overall', r.get('error', '?')), flush=True)
        for v in (r.get('verdicts') or []):
            if v.get('status') != 'ok':
                print(f"  [{v.get('status','?').upper()}] {v.get('area','')}: {v.get('why','')}"
                      + (f" | остаток: {v.get('residual')}" if v.get('residual') else ''), flush=True)


if __name__ == '__main__':
    main()
