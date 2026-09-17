# -*- coding: utf-8 -*-
"""Реальные строки из реестров РФРП. Вывод компактный: раннер режет stdout сверху."""
import io
import json
import re
import ssl
import urllib.error
import urllib.request
import zipfile

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {}


def взять(url, лимит=1200000, tmo=40):
    try:
        r = НП.open(urllib.request.Request(url, headers=H), timeout=tmo)
        return r.getcode(), r.read(лимит)
    except urllib.error.HTTPError as e:
        return e.code, b''
    except Exception:
        return -1, b''


def текст(сырое):
    т = сырое.decode('utf-8', 'replace')
    if 'charset=windows-1251' in т[:900].lower():
        т = сырое.decode('cp1251', 'replace')
    return т


def плоско(html):
    ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ч))


# 1. Рязань — карточки проектов.
код, сырое = взять('https://frp62.ru/project')
ч = плоско(текст(сырое))
куски = re.findall(r'((?:ООО|АО|ПАО|ЗАО)\s*[«"][^»"]{3,55}[»"][^|]{0,90})', ч)
o['рязань'] = [re.sub(r'\s+', ' ', k).strip()[:110] for k in куски[:5]]

# 2. Вологда — таблица реестра с ИНН.
код, сырое = взять('https://smb35.ru/reestr')
html = текст(сырое)
табл = []
for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S | re.I)[:8]:
    яч = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', c)).strip()
          for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S | re.I)]
    яч = [c[:45] for c in яч if c]
    if len(яч) >= 3:
        табл.append(яч[:6])
o['вологда'] = табл[:5]

# 3. Якутия — файл XLSX, разбор с правильным чтением общих строк.
код, сырое = взять('https://fondsakha.ru/files/64/-/293/------1--2026-.xlsx', 6000000)
зап = {'код': код, 'байт': len(сырое)}
try:
    z = zipfile.ZipFile(io.BytesIO(сырое))
    общие = []
    if 'xl/sharedStrings.xml' in z.namelist():
        сс = z.read('xl/sharedStrings.xml').decode('utf-8', 'replace')
        for si in re.findall(r'<si>(.*?)</si>', сс, re.S):
            общие.append(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', si)).strip())
    лист = sorted(n for n in z.namelist() if n.startswith('xl/worksheets/sheet'))[0]
    xml = z.read(лист).decode('utf-8', 'replace')
    строки = []
    for row in re.findall(r'<row[^>]*>(.*?)</row>', xml, re.S)[:9]:
        яч = []
        for c in re.findall(r'<c\b([^>]*)>(.*?)</c>', row, re.S):
            атр, тело = c
            тип = (re.search(r't="(\w+)"', атр) or [None, ''])[1] if 't="' in атр else ''
            v = re.search(r'<v>(.*?)</v>', тело, re.S)
            знач = v.group(1) if v else ''
            if not знач and '<is>' in тело:
                знач = re.sub(r'<[^>]+>', '', тело)
            if тип == 's' and знач.isdigit() and int(знач) < len(общие):
                знач = общие[int(знач)]
            знач = знач.strip()
            if знач:
                яч.append(знач[:42])
        if яч:
            строки.append(яч[:6])
    зап['всего_строк'] = len(re.findall(r'<row', xml))
    зап['строки'] = строки[:6]
except Exception as e:
    зап['ошибка'] = repr(e)[:90]
o['якутия_файл'] = зап

print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5500])
