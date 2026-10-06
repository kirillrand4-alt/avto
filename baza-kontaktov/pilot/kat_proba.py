import sys, os, time, re
sys.path.insert(0, os.path.dirname(__file__))
import analiz as A
print('===ИТОГ===')
for sid in ('82300', '82301', '82302'):
    t = time.time(); st, _, d = A.get('https://catalog.expocentr.ru/catalog.php?wyst_id=171&info_id=0&stand_id=' + sid, timeout=30)
    print(sid, st, len(d or ''), round(time.time() - t, 1), 'с', d[:80] if st is None else '')
t = time.time(); st, _, d = A.get('https://productcenter.ru/producers', timeout=30); print('pc', st, round(time.time() - t, 1))
