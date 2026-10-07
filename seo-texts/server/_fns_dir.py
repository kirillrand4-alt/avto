# -*- coding: utf-8 -*-
import os, json, time
d = r'C:\sender\_ops\ak\fns'
o = {'файлы': [(f, round(os.path.getsize(os.path.join(d, f)) / 1e6, 1)) for f in sorted(os.listdir(d))],
     'время_сервера': time.strftime('%Y-%m-%d %H:%M')}
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False))
