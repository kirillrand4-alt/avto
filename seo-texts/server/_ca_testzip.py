# -*- coding: utf-8 -*-
# Проверка целостности скачанного rsmp (CRC всех файлов архива) — в фоне, итог в ca\ca-testzip.json
import glob, json, os, subprocess, sys, time, zipfile
P = r'C:\sender\server\ca'
if '--vnutri' not in sys.argv:
    subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], creationflags=0x08 | 0x200 | 0x4000,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    print('===ИТОГ=== запущено')
    sys.exit(0)
o = {'старт': time.strftime('%H:%M:%S')}
for f in glob.glob(r'C:\sender\_ops\ak\fns\data-*-structure-*.zip') + [r'C:\sender\_ops\ak\fns\revexp.zip']:
    плохие, всего = [], 0
    try:
        with zipfile.ZipFile(f) as z:
            for i in z.infolist():
                всего += 1
                try:
                    with z.open(i) as fh:
                        while fh.read(1 << 22):
                            pass
                except Exception as e:  # noqa: BLE001
                    плохие.append([i.filename, i.header_offset, repr(e)[:80]])
    except Exception as e:  # noqa: BLE001
        плохие.append(['архив', 0, repr(e)[:120]])
    o[os.path.basename(f)] = {'файлов': всего, 'битых': len(плохие), 'первые': плохие[:5], 'мб': os.path.getsize(f) >> 20}
o['конец'] = time.strftime('%H:%M:%S')
json.dump(o, open(os.path.join(P, 'ca-testzip.json'), 'w', encoding='utf-8'), ensure_ascii=False)
