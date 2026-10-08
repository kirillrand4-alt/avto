import glob, io, os, json
o = {}
for шаг in ('poisk_otbor', 'kc_kontakty', 'kc_audit', 'kc_audit2'):
    лл = sorted(glob.glob(r'C:\sender\server\konveyer_poisk_%s_*.log' % шаг), key=os.path.getmtime)
    if лл:
        o[шаг] = io.open(лл[-1], encoding='utf-8', errors='replace').read()[-700:]
print('===ИТОГ==='); print(json.dumps(o, ensure_ascii=False, indent=1))
