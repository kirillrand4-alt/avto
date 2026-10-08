import glob, io, os
л = sorted(glob.glob(r'C:\sender\server\kc_sayt_proverka_*.log'), key=os.path.getmtime)
print('===ИТОГ==='); print(io.open(л[-1], encoding='utf-8', errors='replace').read()[-800:] if л else 'нет лога')
