import glob, io, json, os, shutil
DIR = r'C:\sender\server'
o = {}
отч = os.path.join(DIR, 'meyer-proverka.jsonl')
стр = [json.loads(s) for s in io.open(отч, encoding='utf-8', errors='replace') if s.strip()]
o['строк'] = len(стр)
посл = {}
for з in стр:
    посл[з['id']] = з
o['id'] = len(посл)
o['с_вердиктом'] = sum(1 for з in посл.values() if 'вердикт' in з)
o['по_кэшу'] = sum(1 for з in посл.values() if 'проверено_по' in з)
логи = sorted(glob.glob(os.path.join(DIR, 'meyer_proverka_*.log')), key=os.path.getmtime)
if логи:
    o['лог'] = os.path.basename(логи[-1])
    o['хвост'] = io.open(логи[-1], encoding='utf-8', errors='replace').read()[-400:]
shutil.copyfile(отч, r'C:\seostat\drop\drop-storage\meyer-proverka.jsonl')
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1))
