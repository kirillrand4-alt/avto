# -*- coding: utf-8 -*-
"""Опознание через НАШ корпус событий + округ карточки роботов."""
import json, re, sqlite3, ssl, urllib.request

CTX = ssl.create_default_context(); CTX.check_hostname=False; CTX.verify_mode=ssl.CERT_NONE
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
     'Accept-Language': 'ru', 'Referer': 'https://investprojects.info/project-base'}
НП = urllib.request.build_opener(urllib.request.ProxyHandler({}))
o = {}

def кратко(ид):
    try:
        r = НП.open(urllib.request.Request(
            'https://investprojects.info/project-base/%s' % ид, headers=H), timeout=45)
        ч = re.sub(r'<script.*?</script>|<style.*?</style>', ' ',
                   r.read(700000).decode('utf-8','replace'), flags=re.S)
        ч = re.sub(r'\s+',' ', re.sub(r'<[^>]+>',' ',ч))
        m = re.search(r'Краткое описание (.{0,250}?) Сроки проекта', ч)
        отр = re.search(r'Отрасль (.{0,40}?) Подотрасль (.{0,45}?) ', ч)
        сроки = re.search(r'Сроки проекта (.{0,70}?) Стадия', ч)
        return {'краткое': (m.group(1) if m else '')[:200],
                'отрасль': отр.group(1).strip() if отр else '',
                'подотрасль': отр.group(2).strip() if отр else '',
                'сроки': сроки.group(1).strip() if сроки else ''}
    except Exception as e:
        return repr(e)[:70]

o['карточка_271244'] = кратко('271244')

c = sqlite3.connect(r'file:C:\sender\enrich.db?mode=ro', uri=True, timeout=30)
def искать(имя, слова):
    усл = ' or '.join("lower(s.what) like '%%%s%%'" % w for w in слова)
    р = c.execute(
        "select s.inn, coalesce(cmp.name,''), substr(s.what,1,110), s.source, "
        "substr(s.updated_at,1,10), coalesce(cmp.region,'') "
        "from signals s left join companies cmp on cmp.inn=s.inn where %s limit 8" % усл
    ).fetchall()
    o[имя] = [{'инн': x[0], 'компания': x[1][:45], 'что': x[2], 'источник': x[3],
               'узнали': x[4], 'регион': x[5][:25]} for x in р]

искать('наши_молочноконсервные', ['молочноконсерв', 'молочно-консерв', 'сгущ', 'сухого молока'])
искать('наши_роботы', ['промышленных роботов', 'робототехн', 'производство роботов'])
c.close()
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1)[:5000])
