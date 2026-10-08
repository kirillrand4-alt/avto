import glob, io, os
л = sorted(glob.glob(r'C:\sender\server\konveyer_poisk_kc_agent_glubokiy_*.log'), key=os.path.getmtime)
print('===ИТОГ==='); print(io.open(л[-1], encoding='utf-8', errors='replace').read()[-400:] if л else 'нет')
import time; print(time.strftime('%H:%M'))
