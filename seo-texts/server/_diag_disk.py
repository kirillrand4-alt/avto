import shutil, os, glob
print('===ИТОГ===')
for д in ('C:\\',):
    u = shutil.disk_usage(д); print(д, 'свободно ГБ', round(u.free/1e9,1), 'всего', round(u.total/1e9,1))
п = r'C:\seostat\drop\pagecache'
фф = glob.glob(os.path.join(п, '*.json.gz')); р = sum(os.path.getsize(f) for f in фф)
print('pagecache файлов', len(фф), 'МБ', round(р/1e6), 'ср КБ', round(р/max(1,len(фф))/1e3,1))
сер = sum(os.path.getsize(f) for f in glob.glob(r'C:\sender\server\pilot-*'))
print('pilot-* МБ', round(сер/1e6))
print('enrich.db МБ', round(os.path.getsize(r'C:\sender\enrich.db')/1e6))
