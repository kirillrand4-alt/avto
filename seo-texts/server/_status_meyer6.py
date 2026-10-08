import io, json, os, glob, time
п = r'C:\sender\server\meyer6-konveyer.json'
o = json.load(io.open(п, encoding='utf-8')) if os.path.exists(п) else {}
print('===ИТОГ===')
print(time.strftime('%H:%M'))
for k, v in o.get('шаги', {}).items():
    print(k, v.get('старт'), v.get('конец'), v.get('код'), (v.get('хвост') or '')[-200:].replace('\n', ' | '))
for л in sorted(glob.glob(r'C:\sender\server\konveyer_meyer6_*.log'), key=os.path.getmtime)[-1:]:
    print('ЛОГ', os.path.basename(л), io.open(л, encoding='utf-8', errors='replace').read()[-300:].replace('\n', ' | '))
