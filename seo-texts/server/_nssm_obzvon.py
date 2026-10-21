import subprocess, re
print('===ИТОГ===')
for svc, exe in (('obzvon', r'C:\Windows\System32\nssm.exe'), ('p25obzvon', r'C:\nssm.exe')):
    for par in ('Application', 'AppParameters', 'AppDirectory', 'AppEnvironmentExtra'):
        r = subprocess.run([exe, 'get', svc, par], capture_output=True, timeout=60)
        v = (r.stdout or b'').decode('utf-16-le', errors='replace') if b'\x00' in (r.stdout or b'') else (r.stdout or b'').decode('cp866', errors='replace')
        v = re.sub(r'(OBZVON_USERS=)[^\r\n]*', lambda m: m.group(1) + '<логины: ' + ','.join(x.split(':')[0] for x in re.split(r'[,;]', m.group(0).split('=', 1)[1]) if x.strip()) + '>', v)
        v = re.sub(r'((?:PASS|TOKEN|SECRET|KEY)[A-Z_]*=)[^\r\n]*', r'\1<скрыто>', v)
        print(svc, par, ':', v.strip()[:400])
