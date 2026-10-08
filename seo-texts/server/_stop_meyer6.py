import json, subprocess
cmd = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and ($_.CommandLine -like '*\\meyer6_konveyer.py*' -or $_.CommandLine -like '*\\kc_sayt_proverka.py*' -or $_.CommandLine -like '*\\kc_agent_glubokiy.py*') } | "
       "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }")
r = subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, text=True, timeout=120)
import io, os
п = r'C:\sender\server\meyer6-sayt-proverka.jsonl'
стр = [s for s in io.open(п, encoding='utf-8', errors='replace')] if os.path.exists(п) else []
хор = []
плох = 0
for s in стр:
    try:
        x = json.loads(s)
    except ValueError:
        continue
    # записи без вердикта модели (шаг1 пустой — баланс кончился) — удалить, чтобы их перепроверили
    if not (x.get('шаг1') or {}).get('вердикт') and x.get('итог') == 'неясно':
        плох += 1
        continue
    хор.append(s)
with io.open(п, 'w', encoding='utf-8') as f:
    f.writelines(хор); f.flush(); os.fsync(f.fileno())
print('===ИТОГ==='); print(json.dumps({'стоп': r.stdout.split(), 'проверка_удалено_пустых': плох, 'осталось': len(хор)}))
