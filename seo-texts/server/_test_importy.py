import json, subprocess, sys
o = {}
for м in ('poisk_otbor', 'poisk_razbor', 'kc_kontakty', 'kc_audit', 'kc_audit2', 'kc_sayty'):
    r = subprocess.run([sys.executable, '-c', 'import os; os.environ["KC_NABOR"]="poisk"; import %s; print("ok")' % м],
                       cwd=r'C:\sender\server', capture_output=True, text=True, timeout=300)
    o[м] = (r.stdout.strip()[-20:] or r.stderr.strip()[-200:])
print('===ИТОГ==='); print(json.dumps(o, ensure_ascii=False, indent=0))
