# -*- coding: utf-8 -*-
"""Что живо на сервере после перезагрузки: службы, порты, очередь заданий, мои накопители."""
import json, os, subprocess, time, urllib.request

o = {}
r = subprocess.run(['powershell', '-Command',
                    "Get-Service obzvon,SenderPanel,seostat* -ErrorAction SilentlyContinue | "
                    "Select-Object -Property Name,Status | ConvertTo-Json -Compress"],
                   capture_output=True, text=True, timeout=120)
o['sluzhby'] = (r.stdout or r.stderr).strip()[:400]

for imya, u in (('обзвон 8012', 'http://127.0.0.1:8012/obzvon/centro/login'),
                ('панель рассыльщика 8091', 'http://127.0.0.1:8091/')):
    try:
        with urllib.request.urlopen(u, timeout=20) as x:
            o[imya] = {'http': x.status, 'байт': len(x.read())}
    except Exception as e:
        o[imya] = str(e)[:110]

# очередь заданий: сколько job-файлов ждёт и когда последний ответ
d = r'C:\sender'
job = [x for x in os.listdir(d) if x.startswith('job-') and x.endswith('.json')]
otv = [x for x in os.listdir(d) if x.startswith('done-') or x.startswith('result-')]
o['ochered_zadaniy'] = {'ждут': len(job), 'ответов рядом': len(otv)}

# мои накопители: растут ли
for f in ('park_dokaz.jsonl', 'park_obshchie_inn.jsonl', 'park_obogashchenie_potok.jsonl'):
    p = os.path.join(d, f)
    o[f] = {'байт': os.path.getsize(p),
            'изменён': time.strftime('%d.%m %H:%M:%S', time.gmtime(os.path.getmtime(p)))} \
        if os.path.exists(p) else 'нет файла'
sn = r'C:\seostat\app\static\centro\dokaz'
o['снимков доказательств'] = len(os.listdir(sn)) if os.path.isdir(sn) else 0
o['сейчас'] = time.strftime('%d.%m %H:%M:%S UTC', time.gmtime())
print(json.dumps(o, ensure_ascii=False, indent=1))
