import shutil, sys
for имя in sys.argv[1:] or ('meyer-proverka-ost.jsonl',):
    shutil.copyfile(r'C:\sender\server\%s' % имя, r'C:\seostat\drop\drop-storage\%s' % имя)
print('===ИТОГ===\nok')
