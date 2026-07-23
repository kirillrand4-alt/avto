#!/usr/bin/env python3
"""Потоковая регенерация 49 КЦ-писем: 4 воркера, чанки по 3, готовое письмо сразу
в очередь kc-queue-###.json на дропе (демон на сервере шлёт по одному).
Кэши regen-rw-*.json прошлого прогона переиспользуются (они по новым правилам).
После всех чанков кладёт kc-queue-STOP.json."""
import glob, json, os, re, sys, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SP)
sys.path.insert(0, '/home/user/avto/seo-texts')
from regen_kc import RULES, facts_block, gate, ask, rw_prompt, vf_prompt, V, KC  # noqa: E402

DROP_URL = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop').rstrip('/')
DROP_TOKEN = os.environ.get('DROP_TOKEN', '')
CHUNK, WORKERS = 3, 4
STATE = os.path.join(SP, 'stream-state.json')
LOCK = threading.Lock()

def drop_put(name, blob):
    if isinstance(blob, str):
        blob = blob.encode('utf-8')
    req = urllib.request.Request(f'{DROP_URL}/' + urllib.parse.quote(name), data=blob,
                                 method='PUT', headers={'X-Drop-Token': DROP_TOKEN})
    urllib.request.urlopen(req, timeout=90).read()

def log(msg):
    with LOCK:
        print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)

# кэш rewrite прошлого прогона (тот же RULES-канон)
cached = {}
for f in sorted(glob.glob(os.path.join(SP, 'regen-rw-*.json'))):
    try:
        for L in json.load(open(f)).get('letters', []):
            cached[int(L['idx'])] = {'subject': L['subject'], 'body': L['body']}
    except Exception:
        pass

state = {'uploaded': []}
if os.path.exists(STATE):
    state = json.load(open(STATE))

def mark_uploaded(idx, payload=None):
    with LOCK:
        state['uploaded'].append(idx)
        json.dump(state, open(STATE, 'w'))
        if payload:
            with open(os.path.join(SP, 'stream-letters.jsonl'), 'a', encoding='utf-8') as f:
                f.write(json.dumps(payload, ensure_ascii=False) + '\n')

def fix_prompt(letters, problems):
    parts = []
    for i in letters:
        parts.append(f"=== ПИСЬМО #{i}\nТЕМА: {letters[i]['subject']}\n{letters[i]['body']}\n"
                     f"НАРУШЕНИЯ: {'; '.join(str(x) for x in problems[i][:6])}")
    return (f"Доработай письма: устрани ПЕРЕЧИСЛЕННЫЕ нарушения, ничего не ломая.\n\n{RULES}\n\n"
            f"{facts_block()}\n\nФОРМАТ - СТРОГО JSON: "
            f'{{"letters":[{{"idx":N,"subject":"...","body":"..."}}]}}\n\n' + "\n\n".join(parts))

def process(chunk):
    chunk = [i for i in chunk if i not in state['uploaded']]
    if not chunk:
        return {}
    letters = {i: dict(cached[i]) for i in chunk if i in cached}
    need = [i for i in chunk if i not in letters]
    try:
        if need:
            log(f'rw {need}')
            for L in ask(rw_prompt(need), f'rw{need}')['letters']:
                letters[int(L['idx'])] = {'subject': L['subject'], 'body': L['body']}
        for rnd in range(3):
            bad = {}
            for i in chunk:
                if i not in letters:
                    bad[i] = ['нет текста']
                    continue
                fails = gate(i, letters[i]['subject'], letters[i]['body'])
                if fails:
                    bad[i] = fails
            good = [i for i in chunk if i not in bad]
            if good and rnd < 2:
                vf = ask(vf_prompt([(i, letters[i]['subject'], letters[i]['body']) for i in good]),
                         f'vf{good}')
                for v in vf['verdicts']:
                    if not v.get('ok'):
                        bad[int(v['idx'])] = v.get('problems', ['verify'])[:6]
            if not bad:
                break
            log(f'fix r{rnd} {sorted(bad)}')
            fixable = {i: letters[i] for i in bad if i in letters}
            if not fixable:
                break
            for L in ask(fix_prompt(fixable, bad), f'fx{sorted(bad)}')['letters']:
                letters[int(L['idx'])] = {'subject': L['subject'], 'body': L['body']}
        residual = {}
        for i in chunk:
            if i not in letters:
                residual[i] = ['нет текста']
                continue
            fails = gate(i, letters[i]['subject'], letters[i]['body'])
            if fails:
                residual[i] = fails
                continue
            payload = {'idx': i, 'role': V[i]['role'], 'angle': V[i]['angle'],
                       'tone': V[i]['tone'], 'subject': letters[i]['subject'],
                       'body': letters[i]['body']}
            drop_put(f'kc-queue-{i:03d}.json', json.dumps(payload, ensure_ascii=False, indent=1))
            mark_uploaded(i, payload)
            log(f'-> очередь #{i} «{letters[i]["subject"][:40]}»')
        return residual
    except Exception as e:  # noqa: BLE001
        log(f'ОШИБКА чанка {chunk}: {type(e).__name__} {e}')
        return {i: [f'crash: {e}'] for i in chunk}

def main():
    todo = [i for i in KC if i not in state['uploaded']]
    log(f'к генерации {len(todo)} писем, кэш rewrite покрывает {sum(1 for i in todo if i in cached)}')
    chunks = [todo[i:i+CHUNK] for i in range(0, len(todo), CHUNK)]
    residual = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for r in pool.map(process, chunks):
            residual.update(r)
    # финальный слепок для коммита
    final = []
    for i in KC:
        if i in state['uploaded'] or i in residual:
            src = cached.get(i, {})
            final.append({'idx': i, 'status': 'queued' if i in state['uploaded'] else 'RESIDUAL',
                          'residual': residual.get(i)})
    json.dump({'uploaded': sorted(state['uploaded']), 'residual': residual},
              open(os.path.join(SP, 'stream-report.json'), 'w'), ensure_ascii=False, indent=1)
    drop_put('kc-queue-STOP.json', '{}')
    log(f'DONE: в очередь {len(state["uploaded"])}/{len(KC)}, остаток {sorted(residual)}')

if __name__ == '__main__':
    main()
