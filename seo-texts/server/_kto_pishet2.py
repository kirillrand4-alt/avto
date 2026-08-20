# -*- coding: utf-8 -*-
import json
t = open(r'C:\sender\sender\imap_watcher.py', encoding='utf-8', errors='replace').read()
i = t.find('метка = "[автоответ]"')
print(json.dumps({'кусок': t[max(0, i-2200):i+1600]}, ensure_ascii=False, indent=1)[:4200])
