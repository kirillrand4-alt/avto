# -*- coding: utf-8 -*-
"""ПРЕДПОЛЁТНАЯ ПРОВЕРКА выкатки панели: не окажется ли пакет из репозитория
СТАРШЕ того, что уже работает на сервере.

Зачем: 26.07 сверка показала, что копия панели в репозитории отстала — 11 модулей
(ai_letter, company_card, ai_quota, reply_pipeline, mailbrowser…) были только на
сервере, а confirm/sender/store в репо на 10–20 КБ меньше живых. Сборка zip из
репозитория и раскатка стёрли бы волны 1–4 правок и Meyer-генерацию.

Код возврата: 0 — выкатывать безопасно, 1 — есть риск затирания (детали в выводе).
Использование: python preflight_panel.py [путь-к-репо-панели]
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_on_server as R

REPO = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(HERE), 'sender')

PROBE = r'''# -*- coding: utf-8 -*-
import hashlib, json, os
S = r"C:\sender\sender"
out = {}
for dp, dn, fns in os.walk(S):
    dn[:] = [d for d in dn if d not in ("__pycache__", "web", "tests")]
    for fn in fns:
        if fn.endswith(".py"):
            p = os.path.join(dp, fn)
            b = open(p, "rb").read()
            out[os.path.relpath(p, S).replace("\\", "/")] = {
                "n": len(b), "h": hashlib.sha256(b).hexdigest()[:16]}
print(json.dumps(out))
'''


def local():
    d = {}
    for dp, dn, fns in os.walk(REPO):
        dn[:] = [x for x in dn if x not in ('__pycache__', 'node_modules', 'web', 'tests')]
        for fn in fns:
            if fn.endswith('.py'):
                p = os.path.join(dp, fn)
                b = open(p, 'rb').read()
                d[os.path.relpath(p, REPO).replace('\\', '/')] = {
                    'n': len(b), 'h': hashlib.sha256(b).hexdigest()[:16]}
    return d


def main():
    import base64
    R.submit('enrich_contacts', {'op': 'panel_file_put', 'files': [
        {'b64': base64.b64encode(PROBE.encode()).decode(),
         'dest': r'C:\sender\_ops\_preflight.py'}]}, wait=True, poll=8, timeout=300)
    res = R.submit('enrich_contacts',
                   {'op': 'panel_py', 'script': r'C:\sender\_ops\_preflight.py',
                    'timeout': 200}, wait=True, poll=8, timeout=400)
    txt = ((res.get('data') or {}).get('stdout_tail') or '').strip()
    srv = json.loads(txt[txt.index('{'):])
    loc = local()

    # 1) файлы, которых в репо нет вовсе — zip их не затрёт (Expand-Archive кладёт
    #    поверх, не удаляя), но это признак расхождения, о нём надо знать
    missing = sorted(set(srv) - set(loc))
    # 2) НАСТОЯЩАЯ опасность: файл есть в обоих, но репозиторный заметно меньше
    shrink = []
    for k in sorted(set(srv) & set(loc)):
        if loc[k]['h'] != srv[k]['h'] and loc[k]['n'] < srv[k]['n'] - 200:
            shrink.append({'файл': k, 'репо': loc[k]['n'], 'бой': srv[k]['n'],
                           'разница': loc[k]['n'] - srv[k]['n']})
    changed = [k for k in set(srv) & set(loc) if loc[k]['h'] != srv[k]['h']]

    print(json.dumps({
        'файлов_в_бою': len(srv), 'файлов_в_репо': len(loc),
        'отличаются': len(changed),
        'только_в_бою': missing,
        'РИСК_ЗАТИРАНИЯ': shrink,
    }, ensure_ascii=False, indent=1))
    if shrink:
        print('\nВЫКАТКУ НЕ ДЕЛАТЬ: перечисленные файлы в репозитории меньше боевых.\n'
              'Сначала подтянуть бой в репозиторий, потом собирать пакет.')
        return 1
    print('\nБЕЗОПАСНО: ни один файл репозитория не младше боевого.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
