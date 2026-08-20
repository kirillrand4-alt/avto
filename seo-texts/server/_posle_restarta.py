# -*- coding: utf-8 -*-
r"""Проверка после рестарта: жива ли панель и видит ли она ответы."""
import json, sqlite3, subprocess, urllib.request, os

итог = {}
try:
    out = subprocess.run(['powershell', '-NoProfile', '-Command',
        "(Get-Service SenderPanel).Status"], capture_output=True, text=True, timeout=60)
    итог['служба'] = (out.stdout or '').strip()
except Exception as e:
    итог['служба'] = str(e)[:80]

# какой лид у Росткрана
c = sqlite3.connect('file:C:/sender/sender.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
лид = c.execute(
    "select l.id, l.email, l.inn, l.status from leads l where l.inn='3906283152' "
    "order by l.id desc limit 1").fetchone()
итог['лид'] = dict(лид) if лид else 'нет'
c.close()

# сама лента через HTTP панели
if лид:
    for порт in (8082, 8080, 8000):
        try:
            r = urllib.request.urlopen(
                'http://127.0.0.1:%d/leads/%d/dialog' % (порт, лид['id']), timeout=15)
            d = json.loads(r.read().decode('utf-8', 'replace'))
            итог['порт'] = порт
            т = d.get('thread') or []
            итог['лента'] = {
                'строк': len(т),
                'входящих': sum(1 for x in т if x.get('direction') == 'in'),
                'с_отметкой': sum(1 for x in т if x.get('adres_iz_pisma')),
                'последние': [{'когда': (x.get('ts') or '')[:16],
                               'куда': x.get('direction'), 'что': x.get('kind'),
                               'пометка': x.get('pometka', '')} for x in т[-4:]]}
            break
        except Exception as e:
            итог.setdefault('порты_не_ответили', []).append('%d: %s' % (порт, str(e)[:60]))
# что отдаёт статика
try:
    a = r'C:\sender\web\dist\assets'
    итог['бандл'] = [f for f in os.listdir(a) if f.endswith('.js')]
except Exception as e:
    итог['бандл'] = str(e)[:60]
print(json.dumps(итог, ensure_ascii=False, indent=1))
