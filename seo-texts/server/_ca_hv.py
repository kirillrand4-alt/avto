import glob, os
л = sorted(glob.glob(r'C:\sender\server\konveyer_ca_kc_agent_glubokiy_хвост_1111-*.log'), key=os.path.getmtime)
print('===ИТОГ===', [os.path.basename(x) for x in л[-1:]])
if л: print(open(л[-1], encoding='utf-8', errors='replace').read()[-300:].replace('\n', ' | '))
