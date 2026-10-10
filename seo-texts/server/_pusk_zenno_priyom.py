# -*- coding: utf-8 -*-
# 10.10, полный прогон Meyer: Зенка кладёт HTML в zenno\gotovo, а в кэш страниц (pagecache) его переносит только
# zenno_most --priyom — демона приёма на сервере не было, 89 сайтов волны 1 пролежали в gotovo. Цикл приёма каждые
# 5 минут (только приём: очередь Зенке он НЕ пополняет), отдельным процессом с меткой; гасится по метке.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
ЛОГ = os.path.join(DIR, 'zenno_priyom_%s.log' % time.strftime('%d%m-%H%M'))
КОД = ("import sys, os, time, json; sys.path.insert(0, r'C:\\sender\\server'); sys.path.insert(0, r'C:\\sender'); "
       "os.chdir(r'C:\\sender\\server'); import zenno_most as ZM\n"
       "while True:\n"
       "    try:\n"
       "        r = ZM.priyom()\n"
       "        print(time.strftime('%H:%M'), json.dumps(r, ensure_ascii=False)[:300], flush=True)\n"
       "    except Exception as e:\n"
       "        print(time.strftime('%H:%M'), 'сбой', repr(e)[:200], flush=True)\n"
       "    time.sleep(300)\n")
python = r'C:\Program Files\Python312\python.exe'
if not os.path.exists(python): python = sys.executable
выход = open(ЛОГ, 'wb')
p = subprocess.Popen([python, '-u', '-c', КОД, '--metka=zenno_priyom_meyer7'], cwd=DIR, creationflags=0x08 | 0x200,
                     stdin=subprocess.DEVNULL, stdout=выход, stderr=subprocess.STDOUT, close_fds=False)
выход.close()
time.sleep(15)
print('===ИТОГ===')
print(json.dumps({'pid': p.pid, 'лог': os.path.basename(ЛОГ),
                  'хвост': open(ЛОГ, encoding='utf-8', errors='replace').read()[-300:]}, ensure_ascii=False, indent=1))
