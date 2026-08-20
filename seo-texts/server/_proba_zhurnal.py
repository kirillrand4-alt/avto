# -*- coding: utf-8 -*-
import json, os
п = r'C:\sender\proba_50_potokov.jsonl'
if not os.path.exists(п):
    print(json.dumps({'журнала нет': п}, ensure_ascii=False)); raise SystemExit
стр = [s.strip() for s in open(п, encoding='utf-8', errors='replace') if s.strip()]
итоги = [json.loads(s)['ИТОГ'] for s in стр if s.startswith('{"ИТОГ"')]
print(json.dumps({'строк': len(стр), 'итогов': len(итоги),
                  'последние': итоги[-2:]}, ensure_ascii=False, indent=1)[:2200])
