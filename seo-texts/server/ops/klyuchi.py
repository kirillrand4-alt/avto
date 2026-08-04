import os
for k in ('DADATA_TOKEN','DADATA_SECRET','DADATA_KEY','CHECKO_KEY','CHECKO_API_KEY',
          'DOLPHIN_TOKEN','XMLRIVER_USER','XMLRIVER_KEY','PROXY_URL','PROXY_URLV2','PROXY_URLV3'):
    v = os.environ.get(k, '')
    print(f'  {k:18} {"ЕСТЬ" if v else "нет"}')
import urllib.request, os
try:
    d = urllib.request.urlopen(urllib.request.Request(
        os.environ.get('DROP_URL','').rstrip('/')+'/dolphin-proxies.txt',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN','')}), timeout=30).read().decode('utf-8','replace')
    строки = [s for s in d.splitlines() if s.strip()]
    print(f'dolphin-proxies.txt: {len(строки)} прокси, пример: {строки[0][:40] if строки else "—"}')
except Exception as e:
    print('dolphin-proxies.txt:', str(e)[:90])
