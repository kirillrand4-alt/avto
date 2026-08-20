# -*- coding: utf-8 -*-
import json
t = open(r'C:\sender\sender\avtootvet.py', encoding='utf-8', errors='replace').read()
i = t.find('def разобрать_автоответ')
print(json.dumps({'байт': len(t), 'кусок': t[i:i+2600]}, ensure_ascii=False, indent=1)[:4000])
