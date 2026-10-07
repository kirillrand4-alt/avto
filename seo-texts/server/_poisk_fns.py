import glob, json, os
o = []
for маска in (r'C:\seostat\**\*revexp*', r'C:\seostat\**\*rsmp*', r'C:\seostat\**\*msp*', r'C:\sender\**\*revexp*',
              r'C:\sender\**\*rsmp*', r'C:\sender\**\*msp*', r'C:\seostat\**\*opendata*', r'C:\sender\**\*opendata*',
              r'C:\seostat\**\*fns*', r'C:\sender\**\*fns*', r'C:\seostat\**\*dohod*', r'C:\sender\**\*dohod*'):
    for п in glob.glob(маска, recursive=True)[:30]:
        try:
            o.append([п, round(os.path.getsize(п) / 1e6, 1) if os.path.isfile(п) else 'папка'])
        except OSError:
            pass
print('===ИТОГ===')
print(json.dumps(sorted(set(map(tuple, o)))[:80], ensure_ascii=False, indent=0))
