import glob, os, re, collections
л = sorted(glob.glob(r'C:\sender\server\konveyer_ca_kc_agent_glubokiy_хвост_1111-*.log'), key=os.path.getmtime)[-1]
т = open(л, encoding='utf-8', errors='replace').read()
строки = [s for s in т.splitlines() if s.strip() and not s.startswith('готово')]
с = collections.Counter(re.sub(r'\d+', 'N', s)[:90] for s in строки)
print('===ИТОГ=== строк', len(т.splitlines()), 'не-«готово»', len(строки))
for k, v in с.most_common(12): print(v, k)
