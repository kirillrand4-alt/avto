# -*- coding: utf-8 -*-
"""Регенерация с инлайн-верификацией и бюджет-капом.
Очередь: flagged-facets -> flagged-brands (shallow-first) -> clean-brands (shallow-first).
- Флагнутым страницам инжектируется КОНКРЕТНЫЙ дефект (defect-map-resolved.json) как «ОБЯЗАТЕЛЬНО ИСПРАВЬ».
- Мех-QA (qa_text) отрабатывает бесплатно на каждой (доводка до 2 раундов).
- keep-best: если новая версия механически ХУЖЕ старой — откатываем из gen-orig/ (не регрессируем).
- КАЖДАЯ 6-я готовая страница -> инженер-верификация (Fable) в живой лог regen-monitor.log.
- Бюджет: копим output/input токены, оцениваем $ по прайсу Fable (консерв.), стоп у cap.
Устойчив к обрыву: regen-state.json (done-слаги), при рестарте продолжает.
"""
import json, os, re, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import gen_provider as gp
import qa_text

DIR = os.path.dirname(os.path.abspath(__file__))
QUEUE = json.load(open(os.path.join(DIR, os.environ.get('REGEN_QUEUE', 'regen-queue.json'))))
DEFECTS = json.load(open(os.path.join(DIR, 'defect-map-resolved.json')))
STATE_F = os.path.join(DIR, 'regen-state.json')
MON_F = os.path.join(DIR, 'regen-monitor.log')
MODEL = 'claude-fable-5'

# бюджет: прайс Fable-5 (консервативная верхняя оценка; router.cheap обычно дешевле)
USD_IN = 10.0 / 1_000_000       # $/токен вход (без кеша)
USD_CACHE = 1.0 / 1_000_000     # $/токен чтение кеша (~10% от входа)
USD_OUT = 50.0 / 1_000_000      # $/токен выход
BUDGET_USD = float(os.environ.get('REGEN_BUDGET', '185'))   # оставляем запас от 200

ENG_HEAD = """Ты - главный инженер по компрессорному оборудованию и пневмосистемам (20 лет практики).
Проверь ТЕХНИЧЕСКУЮ ТОЧНОСТЬ связующей прозы (фактуру из прайса не трогай).
Ошибки-маркеры: обратная зависимость давление/производительность; переставленная/усечённая цепочка
подготовки (канон: компрессор->концевой охладитель->циклон->ресивер->префильтр->осушитель->магистральный
фильтр); адсорбция как «химия» (она физическая); ресивер занижен/завышен либо выдуман в литрах (норма
10-20% минутной производительности); подмена производительности объёмом ресивера; «осушитель до -40» без
уточнения что адсорбционный; путаница объёмный/массовый расход.
Верни РОВНО одну строку: <critical|important|minor|clean> | <очень кратко или ->
critical=грубая физ/тех ошибка, important=заметная неточность, minor=косметика, clean=ошибок нет."""

_lock = threading.Lock()
_state = {'done': {}, 'spent_usd': 0.0, 'in_tok': 0, 'cache_tok': 0, 'out_tok': 0,
          'kept_old': [], 'regressions': [], 'eng_verdicts': []}
if os.path.exists(STATE_F):
    try: _state.update(json.load(open(STATE_F)))
    except Exception: pass


def save_state():
    with _lock:
        json.dump(_state, open(STATE_F, 'w'), ensure_ascii=False, indent=1)


def mon(line):
    with _lock:
        open(MON_F, 'a', encoding='utf-8').write(line.rstrip() + '\n')
    print(line.rstrip(), flush=True)


def text_of(d):
    t = re.sub(r'<[^>]+>', ' ', d.get('text_html', '')).replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def mech_badness(d, payload):
    """Дешёвая мех-оценка «плохости» для keep-best (те же детекторы, без сети)."""
    html = d.get('text_html', ''); text = text_of(d); low = text.lower()
    n = len(qa_text.refinement_check(low)) + len(qa_text.naturalness(html, text, low))
    n += sum(1 for b in qa_text.BANNED if b in low)
    if qa_text.keyword_density_issue(html, text): n += 1
    if not (2300 <= len(text) <= 5200): n += 1
    return n


def cost_add(summary):
    inp = summary.get('input_tokens', 0); cr = summary.get('cache_read_tokens', 0)
    out = summary.get('output_tokens', 0); cw = summary.get('cache_write_tokens', 0)
    # input_tokens у SDK уже без кеш-чтения; кеш-запись тарифим как вход
    usd = (inp + cw) * USD_IN + cr * USD_CACHE + out * USD_OUT
    with _lock:
        _state['in_tok'] += inp + cw; _state['cache_tok'] += cr; _state['out_tok'] += out
        _state['spent_usd'] += usd
    return usd


def eng_verify(slug, client):
    d = json.load(open(os.path.join(DIR, f'gen/result-{slug}.json')))
    p = json.load(open(os.path.join(DIR, f'gen/payload-{slug}.json')))
    prompt = ENG_HEAD + f"\n\n[{p.get('category')}] {p.get('h1')}\n" + text_of(d)
    try:
        # verify - необязательный мониторинг: 2 попытки, чтобы не блокировать цикл на 11 мин ретраев
        msg = gp.call(client, [{'role': 'user', 'content': prompt}], model=MODEL, attempts=2)
        with _lock:
            _state['out_tok'] += msg.usage.output_tokens
            _state['spent_usd'] += msg.usage.output_tokens * USD_OUT + \
                (msg.usage.input_tokens) * USD_IN
        out = ''.join(b.text for b in msg.content if b.type == 'text').strip()
        m = re.search(r'(critical|important|minor|clean)\s*\|\s*(.*)', out, re.I)
        return (m.group(1).lower(), m.group(2).strip()[:120]) if m else ('parse', out[:80])
    except Exception as e:
        return ('err', repr(e)[:80])


def defect_directive(slug, flagged):
    if not flagged or slug not in DEFECTS:
        return ''
    sev, defect = DEFECTS[slug]
    return (f"\n=== ОБЯЗАТЕЛЬНО ИСПРАВИТЬ (инженерная проверка нашла в прежней версии) ===\n"
            f"Прежний текст содержал ошибку: «{defect}». В новой версии этой ошибки быть НЕ должно. "
            f"Проверь соответствующий фрагмент особенно тщательно и напиши его технически корректно.")


def process(item):
    slug = item['slug']; flagged = item['flagged']
    old_path = os.path.join(DIR, f'gen/result-{slug}.json')
    orig_path = os.path.join(DIR, f'gen-orig/result-{slug}.json')
    payload = json.load(open(os.path.join(DIR, f'gen/payload-{slug}.json')))
    old = json.load(open(orig_path)) if os.path.exists(orig_path) else json.load(open(old_path))
    old_bad = mech_badness(old, payload)
    price_known = not (payload.get('price_known') is False)
    try:
        summ = gp.run_one(slug, price_known=price_known, extra=defect_directive(slug, flagged),
                          model=MODEL, max_rounds=int(os.environ.get('REGEN_MAXROUNDS', '3')))
    except Exception as e:
        # генерация не удалась — оставляем старую версию как есть
        return {'slug': slug, 'status': 'GEN-FAIL', 'err': repr(e)[:120], 'flagged': flagged}
    usd = cost_add(summ)
    new = json.load(open(old_path))
    new_bad = mech_badness(new, payload)
    kept = 'new'
    # keep-best: не регрессируем механически. Флагнутой странице даём приоритет новой (семант. фикс),
    # если она не СТРОГО хуже старой; чистой странице — только при не-ухудшении.
    if new_bad > old_bad:
        json.dump(old, open(old_path, 'w'), ensure_ascii=False, indent=1)
        kept = 'old'
        with _lock: _state['kept_old'].append(slug)
    return {'slug': slug, 'status': 'OK', 'flagged': flagged, 'kept': kept,
            'old_bad': old_bad, 'new_bad': new_bad, 'rounds': len(summ.get('rounds', [])),
            'clean': summ.get('clean'), 'usd': round(usd, 3), 'words': summ.get('words')}


def main():
    workers = int(os.environ.get('REGEN_WORKERS', '4'))
    todo = [it for it in QUEUE if it['slug'] not in _state['done']]
    mon(f"=== REGEN START {time.strftime('%H:%M')} | очередь {len(todo)}/{len(QUEUE)} | "
        f"бюджет ${BUDGET_USD} | потрачено ${_state['spent_usd']:.2f} | workers {workers} ===")
    client = gp.make_client()
    done_ct = [len(_state['done'])]
    stop = [False]

    def wrapped(it):
        if stop[0]:
            return None
        return process(it)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {}
        it = iter(todo)
        # начальная заправка пула
        for _ in range(workers):
            try: nxt = next(it)
            except StopIteration: break
            futs[ex.submit(wrapped, nxt)] = nxt
        while futs:
            for fut in as_completed(list(futs)):
                item = futs.pop(fut)
                r = fut.result()
                if r is None:
                    continue
                slug = r['slug']
                with _lock:
                    _state['done'][slug] = r['status']
                    done_ct[0] += 1
                    n = done_ct[0]; spent = _state['spent_usd']
                if r['status'] == 'OK':
                    tag = 'FLAG' if r['flagged'] else 'clean'
                    kb = ' ⟲KEEP-OLD' if r['kept'] == 'old' else ''
                    mon(f"[{n}] {tag} {slug} | bad {r['old_bad']}→{r['new_bad']} r{r['rounds']}"
                        f"{' clean' if r['clean'] else ' DIRTY'}{kb} | ${r['usd']} | Σ${spent:.2f}")
                else:
                    mon(f"[{n}] {r['status']} {slug} | {r.get('err','')}")
                # каждая 6-я готовая -> инженер-верификация
                if n % 6 == 0 and r['status'] == 'OK':
                    sev, note = eng_verify(slug, client)
                    with _lock:
                        _state['eng_verdicts'].append({'n': n, 'slug': slug, 'sev': sev, 'note': note,
                                                       'was_flagged': r['flagged']})
                    flag_mark = '⚠REGRESS' if (sev in ('critical', 'important') and not r['flagged']) else ''
                    mon(f"    └─ ИНЖЕНЕР[{n}] {slug}: {sev} | {note} {flag_mark}")
                    if sev in ('critical', 'important') and not r['flagged']:
                        with _lock: _state['regressions'].append({'slug': slug, 'sev': sev, 'note': note})
                save_state()
                # бюджет-кап: стоп заправки новых задач
                if spent >= BUDGET_USD:
                    if not stop[0]:
                        mon(f"=== БЮДЖЕТ ${BUDGET_USD} ДОСТИГНУТ (${spent:.2f}) — заправка остановлена ===")
                    stop[0] = True
                # заправляем следующей задачей
                if not stop[0]:
                    try:
                        nxt = next(it)
                        futs[ex.submit(wrapped, nxt)] = nxt
                    except StopIteration:
                        pass
                break   # пересобрать as_completed с обновлённым futs
    with _lock:
        s = _state
    mon(f"=== REGEN STOP {time.strftime('%H:%M')} | готово {len(s['done'])}/{len(QUEUE)} | "
        f"потрачено ${s['spent_usd']:.2f} (in {s['in_tok']} cache {s['cache_tok']} out {s['out_tok']}) | "
        f"keep-old {len(s['kept_old'])} | регрессий {len(s['regressions'])} ===")
    save_state()


if __name__ == '__main__':
    main()
