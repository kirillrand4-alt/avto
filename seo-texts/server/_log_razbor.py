import glob, io, os
л = sorted(glob.glob(r'C:\sender\server\konveyer_poisk_poisk_razbor_*.log'), key=os.path.getmtime)[-1]
print('===ИТОГ==='); print(io.open(л, encoding='utf-8', errors='replace').read()[-1500:])
