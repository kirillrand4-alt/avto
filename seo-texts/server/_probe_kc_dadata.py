# -*- coding: utf-8 -*-
import io, json, os
п = r'C:\sender\server\kc-okved-fns.jsonl'
o = [json.loads(s) for s in io.open(п, encoding='utf-8', errors='replace') if '"dadata"' in s][-12:]
print('===ИТОГ===')
print(json.dumps([{k: x.get(k) for k in ('inn', 'итог', 'ошибка', 'оквэд', 'название')} for x in o], ensure_ascii=False, indent=0))
