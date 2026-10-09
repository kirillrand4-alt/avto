import json, subprocess, sys
o = {}
for м in ('pilot_poisk', 'poisk_razbor', 'poisk_otbor', 'pilot_otbor', 'pilot_sayty_dobor', 'kc_kontakty', 'kc_pochty',
          'pilot_dop_proverka', 'pilot_pasport', 'kc_audit', 'kc_audit2', 'kc_sayt_proverka', 'kc_oproverzhenie',
          'kc_agent_glubokiy', 'kc_agent_pereproverka', 'pilot_konveyer'):
    r = subprocess.run([sys.executable, '-c', 'import os; os.environ["KC_NABOR"]="meyer7t"; os.environ["POISK_NABOR"]="meyer7t"; import %s; print("ok")' % м],
                       cwd=r'C:\sender\server', capture_output=True, text=True, timeout=300)
    o[м] = (r.stdout.strip()[-20:] or r.stderr.strip()[-200:])
print('===ИТОГ==='); print(json.dumps(o, ensure_ascii=False, indent=0))
