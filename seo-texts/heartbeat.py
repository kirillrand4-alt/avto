# -*- coding: utf-8 -*-
"""Пульс: спит ~55 мин, собирает статус всего ночного пула, на выходе будит сессию."""
import time, os, sys, json, glob
D='/home/user/avto/seo-texts'; os.chdir(D); sys.path.insert(0,D)
from gen_provider import env
E=env(); os.environ['DROP_URL']=E['DROP_URL']; os.environ['DROP_TOKEN']=E['DROP_TOKEN']
for line in open('/tmp/rs.env',encoding='utf-8'):
    if line.startswith('JOB_SECRET='): os.environ['JOB_SECRET']=line.split('=',1)[1].strip()
time.sleep(3300)  # 55 минут
st={'gen_buckets': len(glob.glob(D+'/variations-cache/b*.json')),
    'picked_100': os.path.exists(D+'/variations-100.json'),
    'news_scan_built': os.path.exists(D+'/server/news_scan.py')}
sys.path.insert(0,D+'/server')
try:
    import run_on_server as R
    try: st['campaign']=json.loads(R._req('GET','campaign-progress.json')).get('stats')
    except Exception as e: st['campaign']='нет прогресса: '+str(e)[:40]
except Exception as e: st['campaign_err']=str(e)[:50]
print('HEARTBEAT', json.dumps(st,ensure_ascii=False), flush=True)
