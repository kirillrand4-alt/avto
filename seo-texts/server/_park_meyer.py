# -*- coding: utf-8 -*-
"""Есть ли в базе «Парк компрессорного оборудования» (park_panel.db) компании под Meyer по ТЗ:
сегменты по ОКВЭД (основной и все), пересечение с нашими 4 файлами и базой Meyer, запреты панели,
контакты (телефон/почта, должность, личный/мобильный). Список новых целевых — CSV на дроп."""
import csv, io, json, os, re, shutil, sqlite3, glob

ДРОП = r'C:\seostat\drop\drop-storage'
вход = json.load(io.open(os.path.join(ДРОП, 'park-sverka-vhod.json'), encoding='utf-8'))
наши, зап, база = вход['наши_файлы'], вход['запреты'], set(вход['база_meyer'])
СЕГМЕНТЫ = [('2 семеноводы', ('01.64', '01.11', '01.13.52', '01.25.2')), ('3 пищевые', ('10.',)),
            ('4 элеваторы', ('52.10.3', '01.63', '10.61')), ('5 орехи', ('10.39.2', '01.25.3')),
            ('6 ягоды', ('01.25.1', '10.39.2', '10.32')),
            ('7 предложено (осн.)', ('46.21', '01.12', '01.61', '46.31', '46.37'))]
ЛПР = re.compile(r'генеральн|директор|руковод|главн\w* инженер|гл\.\s*инж|техническ\w* дир|технолог|'
                 r'производств|качеств|лаборатор|закуп|снабж|агроном|семеновод|элеватор', re.I)
НЕ_ЛПР = re.compile(r'региональн|финансов|по продаж|маркет|персонал|бухгалт|кадр|секретар|приёмн|приемн', re.I)


def коды(*s):
    out = []
    for x in s:
        for к in re.findall(r'\d{2}(?:\.\d{1,2}){0,3}', x or ''):
            if к not in out:
                out.append(к)
    return out


def попадает(вс, пр):
    return any((п.endswith('.') and к.startswith(п)) or к == п or к.startswith(п + '.') for к in вс for п in пр)


o = {'базы': {}}
for п in sorted(glob.glob(os.path.join(ДРОП, 'park*.db'))):
    c = sqlite3.connect('file:%s?mode=ro' % п, uri=True, timeout=30)
    тт = [r[0] for r in c.execute("select name from sqlite_master where type='table'")]
    o['базы'][os.path.basename(п)] = {т: c.execute('select count(*) from "%s"' % т).fetchone()[0] for т in тт if т in ('predpriyatie', 'kontakt')}
    c.close()

п = os.path.join(ДРОП, 'park_panel.db')
c = sqlite3.connect('file:%s?mode=ro' % п, uri=True, timeout=30)
кол = [r[1] for r in c.execute('pragma table_info(predpriyatie)')]
o['колонки_predpriyatie'] = кол
пр = [dict(zip(кол, r)) for r in c.execute('select * from predpriyatie')]
ккол = [r[1] for r in c.execute('pragma table_info(kontakt)')]
o['колонки_kontakt'] = ккол
конт = {}
for r in c.execute('select * from kontakt'):
    д = dict(zip(ккол, r))
    конт.setdefault(str(д.get('inn')), []).append(д)
c.close()

итог = {'всего': len(пр), 'целевых_по_осн': 0, 'целевых_только_доп': 0, 'по_сегментам': {}}
строки = []
for р in пр:
    инн = str(р.get('inn') or '')
    осн = коды(р.get('okved') or '')[:1]
    все = коды(р.get('okved') or '', р.get('okved_vse') or '', р.get('okved_kody') or '')
    сегм_осн = [с for с, п in СЕГМЕНТЫ if осн and попадает(осн, п)]
    сегм_доп = [с for с, п in СЕГМЕНТЫ if not с.startswith('7') and попадает(все, п) and с not in сегм_осн]
    if not (сегм_осн or сегм_доп):
        continue
    if сегм_осн:
        итог['целевых_по_осн'] += 1
    else:
        итог['целевых_только_доп'] += 1
    for с in сегм_осн + сегм_доп:
        итог['по_сегментам'][с] = итог['по_сегментам'].get(с, 0) + 1
    кк = конт.get(инн, [])
    тел = [к for к in кк if (к.get('vid') or '').lower().startswith('тел') or re.search(r'\d{10}', re.sub(r'\D', '', str(к.get('znachenie') or '')))]
    лпр = [к for к in тел if ЛПР.search(str(к.get('dolzhnost') or '') + ' ' + str(к.get('rol') or '')) and not НЕ_ЛПР.search(str(к.get('dolzhnost') or ''))]
    моб = [к for к in тел if str(к.get('mobilnyy') or '') in ('1', 'True', 'true', 'да')]
    где = 'в наших файлах (%s)' % наши[инн] if инн in наши else ('в базе Meyer, но без подтверждённых номеров' if инн in база else 'новая для Meyer')
    строки.append({'ИНН': инн, 'Название': р.get('nazvanie'), 'Регион': р.get('region'), 'Основной ОКВЭД': осн[0] if осн else '',
                   'Сегмент по осн. ОКВЭД': ' | '.join(сегм_осн), 'Сегмент только по доп.': ' | '.join(сегм_доп),
                   'Выручка': р.get('vyruchka'), 'Статус ЕГРЮЛ': р.get('status_egrul'), 'Где у нас': где,
                   'Запрет панели': зап.get(инн, ''), 'Телефонов': len(тел), 'С должностью ЛПР': len(лпр), 'Мобильных': len(моб),
                   'Лучший ЛПР': ('%s — %s — %s' % (лпр[0].get('person') or '', лпр[0].get('dolzhnost') or '', лпр[0].get('znachenie') or '')) if лпр else '',
                   'Человек (из карточки)': р.get('chelovek'), 'Должность (из карточки)': р.get('dolzhnost'), 'Телефон (из карточки)': р.get('telefon')})

ц = строки
итог['целевых_всего'] = len(ц)
итог['уже_в_наших_файлах'] = sum(1 for s in ц if s['Где у нас'].startswith('в наших'))
итог['в_базе_Meyer_без_номеров'] = sum(1 for s in ц if s['Где у нас'].startswith('в базе'))
итог['новых_для_Meyer'] = sum(1 for s in ц if s['Где у нас'] == 'новая для Meyer')
нов = [s for s in ц if not s['Где у нас'].startswith('в наших')]
итог['из_не_вошедших: со сделкой/запретом'] = sum(1 for s in нов if s['Запрет панели'])
чист = [s for s in нов if not s['Запрет панели'] and 'ликвид' not in str(s['Статус ЕГРЮЛ'] or '').lower()]
итог['чистых_кандидатов'] = len(чист)
итог['  из них по основному ОКВЭД'] = sum(1 for s in чист if s['Сегмент по осн. ОКВЭД'])
итог['  с телефоном'] = sum(1 for s in чист if s['Телефонов'])
итог['  с телефоном ЛПР'] = sum(1 for s in чист if s['С должностью ЛПР'])
итог['  с мобильным'] = sum(1 for s in чист if s['Мобильных'])
o['итог'] = итог
o['пример'] = [{k: str(v)[:70] for k, v in s.items() if k in ('Название', 'Основной ОКВЭД', 'Сегмент по осн. ОКВЭД', 'Где у нас', 'Лучший ЛПР')} for s in sorted(чист, key=lambda s: -s['С должностью ЛПР'])[:8]]
файл = r'C:\sender\server\park-meyer-kandidaty.csv'
with io.open(файл, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(ц[0].keys()) if ц else ['ИНН'], delimiter=';')
    w.writeheader()
    for s in sorted(ц, key=lambda s: (s['Где у нас'].startswith('в наших'), bool(s['Запрет панели']), not s['Сегмент по осн. ОКВЭД'], -s['С должностью ЛПР'])):
        w.writerow(s)
    f.flush(); os.fsync(f.fileno())
shutil.copyfile(файл, os.path.join(ДРОП, 'park-meyer-kandidaty.csv'))
print('===ИТОГ===')
print(json.dumps(o, ensure_ascii=False, indent=1, default=str)[:6000])
