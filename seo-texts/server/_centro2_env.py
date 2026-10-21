import glob, re
print('===ИТОГ===')
т = open(r'C:\centro2\zapusk.py', encoding='utf-8', errors='replace').read()
print(т[:1500])
for п in glob.glob(r'C:\centro2\*.env') + glob.glob(r'C:\centro2\.env*'):
    for s in open(п, encoding='utf-8', errors='replace'):
        k, _, v = s.partition('=')
        if any(x in k.upper() for x in ('DB', 'ROOT', 'PORT', 'ADMINS')):
            print(п, k.strip(), '=', v.strip())
