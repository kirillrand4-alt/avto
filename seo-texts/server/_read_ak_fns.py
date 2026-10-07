import json, os, zipfile
o = {}
p = r'C:\sender\_ops\ak\ak_fns.py'
o['ak_fns'] = open(p, encoding='utf-8', errors='replace').read()[:6000]
z = zipfile.ZipFile(r'C:\sender\_ops\ak\fns\revexp.zip')
names = z.namelist()
o['zip_files'] = len(names)
o['zip_first'] = names[:3]
o['sample'] = z.read(names[0])[:1200].decode('utf-8', 'replace')
o['fns_dir'] = os.listdir(r'C:\sender\_ops\ak\fns')
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:9000])
