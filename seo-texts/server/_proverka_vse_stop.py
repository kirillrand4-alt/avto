import io, json, os, subprocess
DIR = r'C:\sender\server'
p = subprocess.run(['powershell', '-NoProfile', '-Command',
                    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*meyer_proverka_vse.py*' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"],
                   capture_output=True, text=True, timeout=120)
o = {'остановлены_pid': (p.stdout or '').split(), 'ошибки': (p.stderr or '')[-300:]}
p2 = subprocess.run(['powershell', '-NoProfile', '-Command',
                     "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*meyer_proverka_vse.py*' } | Measure-Object).Count"],
                    capture_output=True, text=True, timeout=90)
o['осталось_процессов'] = (p2.stdout or '').strip()
отч = os.path.join(DIR, 'meyer-proverka-vse.jsonl')
стр = [json.loads(s) for s in io.open(отч, encoding='utf-8', errors='replace') if s.strip()]
o['записано_номеров'] = len(стр)
o['сверено_моделью'] = sum(1 for з in стр if з.get('итог') == 'сверен')
o['страниц'] = len({з['url'] for з in стр})
лог = os.path.join(DIR, 'meyer_proverka_vse_0610-1054.log')
o['лог_хвост'] = io.open(лог, encoding='utf-8', errors='replace').read()[-300:] if os.path.exists(лог) else ''
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
