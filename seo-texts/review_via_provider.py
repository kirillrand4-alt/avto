# -*- coding: utf-8 -*-
"""Ревью кода сендера через провайдера (router.cheap, fable-5) — не жжём токены сессии.

Читает каждый модуль, шлёт провайдеру с ревью-промптом, собирает баги (JSON),
кэширует по модулю (резюмируемо), пишет отчёт. Второй проход — верификация топ-багов
другой моделью. Запуск: python3 review_via_provider.py  (нужен PROVIDER_API_KEY в env).
"""
import os, sys, json, re, time, pathlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider as G

ROOT = pathlib.Path('/home/user/avto')
CACHE = pathlib.Path('/tmp/claude-0/-home-user-avto/bcce55cd-293a-515c-9700-ae71a77daa5a/scratchpad/review_cache')
CACHE.mkdir(parents=True, exist_ok=True)
OUT_JSON = ROOT / 'seo-texts' / 'sender' / 'REVIEW-FINDINGS.json'
OUT_MD = ROOT / 'seo-texts' / 'sender' / 'REVIEW-FINDINGS.md'

MODULES = [
    'seo-texts/sender/sender.py',
    'seo-texts/sender/store.py',
    'seo-texts/sender/warmup.py',
    'seo-texts/sender/gates.py',
    'seo-texts/sender/suppression.py',
    'seo-texts/sender/unsub.py',
    'seo-texts/sender/unsub_server.py',
    'seo-texts/sender/cadence.py',
    'seo-texts/sender/importer.py',
    'seo-texts/sender/orchestrator.py',
    'seo-texts/sender/postoffice.py',
    'seo-texts/sender/personalize.py',
    'seo-texts/sender/validation.py',
    'seo-texts/sender/tracking.py',
    'seo-texts/sender/config.py',
    'seo-texts/sender/autoresponder.py',
    'seo-texts/sender/reply_classify.py',
    'seo-texts/sender/imap_watcher.py',
    'seo-texts/sender/auth.py',
    'seo-texts/sender/dns.py',
]

REVIEW_PROMPT = """Ты ревьюишь Python-модуль самописного B2B COLD-EMAIL рассыльщика (РФ, под ФЗ-38 «О рекламе»:
получатель должен иметь возможность отписаться, и отписки должны соблюдаться НАВСЕГДА). Система под ХОЛДОМ
(боевой отправки ещё нет), поэтому ищем корректность, которая выстрелит в момент запуска.

Найди ТОЛЬКО реальные конкретные дефекты (не стиль). Приоритет:
- потеря/порча данных, неверные переходы состояний
- ЮРИДИКА: отписка/подавление не соблюдается, либо подавленный адрес всё ещё можно отправить
- доставляемость: обход/просчёт warmup-рампы или rate/cadence-гейтов, отправка быстрее задуманного
- дедуп (один получатель дважды), гонки, конкурентность
- ошибки SMTP/IMAP, утечки ресурсов (незакрытые соединения/файлы)
- инъекция в шаблон/персонализацию, инъекция заголовков письма
- молчаливое проглатывание исключений, прячущее сбои
- off-by-one, неверное сравнение, ошибки timezone/дат в расписании

Верни СТРОГО JSON без markdown-обёртки:
{"findings":[{"line":<int>,"severity":"critical|high|medium|low","category":"<кратко>",
"summary":"<одно предложение>","failure_scenario":"<конкретные вход/состояние -> неверный итог>"}]}
Если модуль чистый — {"findings":[]}. НЕ выдумывай баги ради количества. Строки — по номерам в коде ниже.

Модуль: %s
```python
%s
```"""


def numbered(path, start=1, end=None):
    lines = (ROOT / path).read_text(encoding='utf-8', errors='replace').splitlines()
    end = end or len(lines)
    return '\n'.join(f'{i+1}\t{lines[i]}' for i in range(start - 1, min(end, len(lines)))), len(lines)


def extract_json(txt):
    txt = re.sub(r'^```(?:json)?\s*|\s*```$', '', txt.strip())
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r'\{.*\}', txt, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def review_module(client, path, model='claude-fable-5'):
    cache_f = CACHE / (path.replace('/', '_') + '.json')
    if cache_f.exists():
        try:
            return json.loads(cache_f.read_text())
        except Exception:
            pass
    code, nlines = numbered(path)
    chunks = []
    if nlines > 750:
        # крупный модуль — бьём на куски по ~700 строк с перекрытием
        step = 700
        for s in range(1, nlines + 1, step):
            c, _ = numbered(path, s, s + step + 40)
            chunks.append(c)
    else:
        chunks = [code]
    all_f = []
    for ci, ch in enumerate(chunks):
        prompt = REVIEW_PROMPT % (path + (f' (часть {ci+1}/{len(chunks)})' if len(chunks) > 1 else ''), ch)
        try:
            # thinking=False (как в проде) — иначе fable шлёт пустой text после thinking-блока
            txt = ''
            for att in range(5):
                try:
                    msg = G._raw_stream([{'role': 'user', 'content': prompt}], model, 4000, thinking=False)
                    txt = ''.join(b.text for b in msg.content if b.type == 'text')
                    if txt.strip():
                        break
                except Exception:
                    time.sleep(3 + att * 3)
            data = extract_json(txt)
            if data and isinstance(data.get('findings'), list):
                for f in data['findings']:
                    f['file'] = path
                all_f.extend(data.get('findings', []))
        except Exception as e:
            all_f.append({'file': path, 'line': 0, 'severity': 'meta',
                          'category': 'review-error', 'summary': f'провайдер не отревьюил кусок {ci+1}: {str(e)[:80]}',
                          'failure_scenario': ''})
        time.sleep(1)
    cache_f.write_text(json.dumps(all_f, ensure_ascii=False))
    return all_f


def main():
    client = G.make_client()
    model = sys.argv[1] if len(sys.argv) > 1 else 'claude-fable-5'
    everything = []
    for i, path in enumerate(MODULES):
        print(f'[{i+1}/{len(MODULES)}] ревью {path} ...', flush=True)
        fs = review_module(client, path, model)
        real = [f for f in fs if f.get('severity') != 'meta']
        print(f'    -> {len(real)} находок', flush=True)
        everything.extend(fs)
    OUT_JSON.write_text(json.dumps(everything, ensure_ascii=False, indent=1))
    # markdown-сводка по severity
    order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3, 'meta': 9}
    real = [f for f in everything if f.get('severity') != 'meta']
    real.sort(key=lambda f: order.get(f.get('severity'), 5))
    lines = [f'# Ревью кода сендера (провайдер {model})', '',
             f'Всего находок: {len(real)} (модулей: {len(MODULES)})', '']
    for sev in ('critical', 'high', 'medium', 'low'):
        grp = [f for f in real if f.get('severity') == sev]
        if not grp:
            continue
        lines.append(f'## {sev.upper()} ({len(grp)})')
        for f in grp:
            lines.append(f"- **{f.get('file')}:{f.get('line')}** [{f.get('category')}] {f.get('summary')}")
            if f.get('failure_scenario'):
                lines.append(f"  - сценарий: {f.get('failure_scenario')}")
        lines.append('')
    errs = [f for f in everything if f.get('severity') == 'meta']
    if errs:
        lines.append(f'## Ошибки ревью ({len(errs)})')
        for f in errs:
            lines.append(f"- {f.get('file')}: {f.get('summary')}")
    OUT_MD.write_text('\n'.join(lines))
    print(f'ГОТОВО: {len(real)} находок -> {OUT_MD}', flush=True)


if __name__ == '__main__':
    main()
