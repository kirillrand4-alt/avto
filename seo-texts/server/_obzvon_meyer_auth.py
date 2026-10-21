import subprocess, glob, os, re
print('===ИТОГ===')
r = subprocess.run(['powershell', '-NoProfile', '-Command',
  "Get-CimInstance Win32_Service | Where-Object { $_.Name -like '*obzvon*' -or $_.Name -like '*centro*' -or $_.PathName -like '*8014*' } | Select-Object Name,State,PathName | Format-List | Out-String -Width 300"],
  capture_output=True, text=True, timeout=120)
print(r.stdout[-2500:])
# конфиги обратного прокси
for п in glob.glob(r'C:\**\Caddyfile*', recursive=False) + glob.glob(r'C:\caddy\*') + glob.glob(r'C:\nginx*\conf\*.conf') + glob.glob(r'C:\seostat\deploy\*') :
    try:
        т = open(п, encoding='utf-8', errors='replace').read()
    except Exception:
        continue
    if 'obzvon' in т:
        for м in re.finditer(r'.{0,200}obzvon-meyer.{0,400}', т, re.S):
            print(п, '::', re.sub(r'(basicauth|basic_auth)[^\n]*\n(\s*\S+\s+)\S+', r'\1 … \2<скрыто>', м.group(0))[:600])
# все .env с OBZVON_
for п in glob.glob(r'C:\seostat*\**\.env*', recursive=True)[:50]:
    try:
        for s in open(п, encoding='utf-8', errors='replace'):
            if s.startswith('OBZVON_') or s.startswith('ROOT_PATH') or 'MEYER' in s.split('=')[0]:
                k, _, v = s.partition('=')
                if k.strip() == 'OBZVON_USERS':
                    логины = [x.split(':')[0].strip() for x in re.split(r'[,;]', v.strip()) if x.strip()]
                    print(п, 'OBZVON_USERS логины:', логины)
                elif k.strip() == 'OBZVON_ADMINS':
                    print(п, 'OBZVON_ADMINS:', v.strip())
                else:
                    print(п, k.strip(), '=', v.strip()[:80])
    except Exception:
        pass
