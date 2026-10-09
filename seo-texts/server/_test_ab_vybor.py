import json, os, subprocess, sys
п = r'C:\sender\server\pilot-ab-vybor.json'
if os.path.exists(п): os.remove(п)
р = subprocess.run([sys.executable, '-c', 'import pilot_agenty_ab as P; в = P.выборка(); в2=[к.get("выручка") or 0 for к in в]; print(len(в), "без сайта", sum(1 for к in в if not к.get("сайт")), "откл", sum(1 for к in в if к.get("отклонены")), "выручка млн макс/мед/мин", round(max(в2)/1e6), round(sorted(в2)[50]/1e6), round(min(в2)/1e6)); print([к["имя"][:25] for к in в[::12]])'],
                   cwd=r'C:\sender\server', capture_output=True, text=True, timeout=600)
print('===ИТОГ==='); print(р.stdout[-1500:], р.stderr[-800:])
