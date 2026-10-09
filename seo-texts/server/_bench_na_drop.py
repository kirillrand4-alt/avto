import json, shutil
for ф in ('pilot-bench-nabor.json', 'pilot-bench-otvety.jsonl'):
    shutil.copyfile(r'C:\sender\server\\' + ф, r'C:\seostat\drop\drop-storage\\' + ф)
print('===ИТОГ==='); print('ok')
