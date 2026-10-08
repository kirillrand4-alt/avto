import json, os, sys, collections
os.environ['POISK_NABOR'] = 'pilot'
sys.path.insert(0, r'C:\sender\server')
import pilot_otbor as P
import urllib.request
o = {}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for унп in ('100185815', '600125834', '190542056'):
    try:
        o['egr_raw_' + унп] = op.open('https://egr.gov.by/api/v2/egr/getShortInfoByRegNum/%s' % унп, timeout=20).read(400).decode('utf-8', 'replace')
    except Exception as e:
        o['egr_raw_' + унп] = repr(e)[:120]
    o['egr_' + унп] = P.егр_by(унп)
р = P.реестр_пилота()
o['реестр'] = len(р)
o['по_регионам'] = dict(collections.Counter(x['регион'] for x in р.values()))
o['сегменты_топ'] = collections.Counter(x['сегм'] for x in р.values()).most_common(12)
o['от_30млн_по_базе'] = sum(1 for x in р.values() if x['выр_база'] >= 3e7)
print('===ИТОГ==='); print(json.dumps(o, ensure_ascii=False, indent=0))
