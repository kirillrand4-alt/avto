# -*- coding: utf-8 -*-
"""Какая модель лучше судит привязку новости к компании. Замер, а не мнение.

Один и тот же трёхступенчатый заслон (proverka_privyazki) прогоняется на 66 РАЗМЕЧЕННЫХ парах
разными моделями-судьями. Разметка — вердикты аудита (16 мисматчей).

ОГОВОРКА О КРУГОВОМ ЗАМЕРЕ, называю сразу: разметку делал аудит на claude-fable-5. Поэтому у
fable-5 здесь фора — он сверяется отчасти сам с собой. Модели других семейств (gpt, gemini,
deepseek) сравниваются честно, между собой и с разметкой.
"""
import json,sys,time,collections
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,'/home/user/work')
import proverka_privyazki as P

MIS={0,11,12,13,20,22,25,40,44,45,52,54,58,59,62,63}
pairs=json.load(open('rassyl/pairs-audit.json',encoding='utf-8'))
MODELI=['deepseek-v4-pro','gemini-3.6-flash','gpt-5.5','claude-sonnet-5','claude-fable-5']

def прогон(model):
    t0=time.time()
    def one(p):
        try: return P.проверить(p, model=model)
        except Exception as e: return (True,'сбой',str(e)[:40])
    with ThreadPoolExecutor(max_workers=8) as ex: res=list(ex.map(one,pairs))
    otpr=[i for i,r in enumerate(res) if r[0]]
    mis_otpr=[i for i in otpr if i in MIS]
    verno_otpr=[i for i in otpr if i not in MIS]
    zablok=[i for i in MIS if i not in otpr]
    ruch=[i for i,r in enumerate(res) if 'ручн' in r[1]]
    ruch_verno=[i for i in ruch if i not in MIS]
    sboi=sum(1 for r in res if r[1]=='сбой')
    return {'model':model,'sek':round(time.time()-t0),
            'pisem':len(otpr),'oshibochnyh_pisem':len(mis_otpr),
            'vernyh_pisem':len(verno_otpr),'zablok_mismatchey':len(zablok),
            'na_ruchnuyu':len(ruch),'zrya_zaderzhano_vernyh':len(ruch_verno),
            'sboev':sboi,'tochnost':round(len(verno_otpr)/max(1,len(otpr)),3),
            'res':[{'i':i,'keep':r[0],'ur':r[1]} for i,r in enumerate(res)]}

itog=[]
for m in MODELI:
    r=прогон(m); itog.append(r)
    print(f"{m:20} писем {r['pisem']:>3} | ошибочных {r['oshibochnyh_pisem']:>2} | "
          f"поймано {r['zablok_mismatchey']:>2}/16 | зря задержано {r['zrya_zaderzhano_vernyh']:>2} | "
          f"точность {r['tochnost']:.0%} | {r['sek']}с | сбоев {r['sboev']}",flush=True)
json.dump(itog,open('sravnenie-modeley.json','w',encoding='utf-8'),ensure_ascii=False)
