# -*- coding: utf-8 -*-
# 12.10 04:00: догон паспортов meyer7 — сайты сменились после шага паспортов 19:28 (сайты агентов 21:44, возвраты хвоста):
# паспорт старого сайта Excel прячет (пасп_чужой). pilot_pasport сам видит смену сайта (старые факты — в pasport-staroe,
# пересбор) и пустые. Пишет site_facts (enrich.db) и <набор>-pasport.jsonl — с файлом обхода не пересекается.
import json, os, subprocess, sys, time
DIR = r'C:\sender\server'
os.environ.update({'POISK_NABOR': 'meyer7', 'KC_NABOR': 'meyer7', 'PILOT_VOLNY': '1', 'PILOT_MODEL': 'gpt-6-luna',
                   'PROVIDER_FALLBACK_CHEAP': 'gpt-5.6-luna', 'PYTHONIOENCODING': 'utf-8'})
sys.path.insert(0, DIR); sys.path.insert(0, r'C:\sender'); os.chdir(DIR)
import pilot_konveyer as PK  # noqa: E402
w = PK.Волны()
ш = 'pilot_pasport.py'
лог = os.path.join(DIR, 'konveyer_meyer7_pasport_dogon_%s.log' % time.strftime('%d%m-%H%M'))
with open(лог, 'wb') as в:
    p = subprocess.Popen([PK.питон(ш), '-u', os.path.join(DIR, ш), '--metka=pasport_dogon_meyer7'], cwd=DIR, env=w.env_шага(ш),
                         stdout=в, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=0x08 | 0x200, close_fds=False)
time.sleep(60)
print('===ИТОГ===')
print(json.dumps({'pid': p.pid, 'питон': PK.питон(ш), 'лог': os.path.basename(лог),
                  'хвост': open(лог, encoding='utf-8', errors='replace').read()[-700:]}, ensure_ascii=False, indent=1))
