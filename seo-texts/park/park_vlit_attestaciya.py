# -*- coding: utf-8 -*-
"""Аттестация РТН 2-й сессии -> факты (Б.7/Б.8 = сила 1) + контакты со ссылкой.
Плюс КАНОНИЗАЦИЯ РОЛИ: чиню свой дефект «машинист» -> «нач.цеха» (нашла 3-я сессия)."""
import sqlite3, csv, re, os, time, json, importlib.util
D = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('pb', os.path.join(D, 'park_build.py'))
pb = importlib.util.module_from_spec(spec); spec.loader.exec_module(pb)
p = sqlite3.connect(os.path.join(D, 'park.db')); cur = p.cursor()

# ---------- КАНОН РОЛИ: по подразделению и профессии, а не по слову «начальник» ------
ROL = [
    (r'(?i)машинист\s+компрессор|аппаратчик\s+воздухораздел|оператор\s+компрессорн|'
     r'аппаратчик\s+кислородн|моторист\s+.*азотн', 'рабочий-эксплуатант', 1),
    (r'(?i)главн\w+\s+(инженер|механик|энергетик)|техническ\w+\s+директор|'
     r'директор\s+по\s+техн', 'главный инженер/механик/энергетик', 1),
    (r'(?i)начальник\s+(компрессорн|энергоцех|энергетическ)|начальник\s+участка\s*/.*компрессор',
     'начальник компрессорного/энергоцеха', 1),
    (r'(?i)начальник\s+(цеха|производств)|главн\w+\s+технолог|начальник\s+(асу|кипиа|кип)',
     'начальник цеха/производства', 2),
    (r'(?i)инженер|механик|энергетик|мастер|техник|слесар', 'инженер/механик', 2),
    (r'(?i)снабжен|закупк|мто|тендер|коммерческ', 'снабжение/закупки', 3),
    (r'(?i)директор|руководител|генеральн|президент', 'руководство', 4),
]
def rol_i_krug(dolzh):
    d = (dolzh or '').strip()
    for sh, rol, krug in ROL:
        if re.search(sh, d):
            return rol, krug
    return ('не определена', 5) if d else ('должность не названа', 5)

# ---------- вливание ------------------------------------------------------------
vsego = fakt_n = kont_n = 0
_B78 = re.compile(r'\bБ\.[78]\.')
for r in csv.DictReader(open(os.path.join(D, 'PARK-ATTESTACIYA-OBLAST-2S.csv'),
                             encoding='utf-8-sig'), delimiter=';'):
    vsego += 1
    inn = (r.get('inn') or '').strip()
    url = (r.get('ssylka') or '').strip()
    if not re.fullmatch(r'\d{10}|\d{12}', inn) or not url.startswith('http'):
        continue
    raz = pb.razbor_url(url)
    domen, ist, pi = raz if raz else ('', 'Ростехнадзор', 1)
    chel = (r.get('chelovek') or '').strip()
    dolzh = (r.get('dolzhnost') or '').strip()
    obl = (r.get('oblast') or '').strip()
    cit = (r.get('citata') or '').strip()
    # ФАКТ О МАШИНЕ: только там, где область прямо про оборудование под давлением/газ
    if _B78.search(obl):
        tip = 'компрессорное оборудование (по области аттестации)'
        dedup = '|'.join([inn, tip, '', obl, '', ''])
        cur.execute('insert or ignore into fakt(inn,nazvanie,tip,sostoyanie,marka,model,'
                    'napisanie,zavodskoy_nomer,sreda,summa,data_fakta,srok_do,sila,chem_rang,'
                    'chto_naydeno,pochemu,uverennost,kto,karantin,dedup,ts) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, '', tip, 'эксплуатирует', '', obl, '', '', '', '', '', '', 1,
                     'надзорная запись: аттестация по области ' + obl,
                     cit[:400], 'область Б.7/Б.8 = газ и оборудование под избыточным давлением; '
                     'аттестуют только там, где такое оборудование есть', 'vysokaya',
                     'PARK-ATTESTACIYA-OBLAST-2S.csv (2-я)', '', dedup,
                     time.strftime('%Y-%m-%d %H:%M:%S')))
        fid = cur.execute('select id from fakt where dedup=?', (dedup,)).fetchone()[0]
        cur.execute('insert or ignore into fakt_ssylka(fakt_id,url,domen,istochnik,etap,'
                    'pervoistochnik,data_nablyudeniya,fayl) values (?,?,?,?,?,?,?,?)',
                    (fid, url, domen, 'Ростехнадзор: график проверки знаний', '', 1, '', ''))
        fakt_n += 1
    # КОНТАКТ: человек с должностью и ссылкой на документ — наблюдение
    if chel:
        cur.execute('insert or ignore into contact_source(inn,vid,znachenie,person,dolzhnost,'
                    'istochnik,source_url,domen,pervoistochnik,data_nablyudeniya,quote,kto) '
                    'values (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (inn, 'chelovek', chel.lower(), chel, dolzh,
                     'Ростехнадзор: график проверки знаний', url, domen, 1, '', cit[:300],
                     'PARK-ATTESTACIYA-OBLAST-2S.csv (2-я)'))
        kont_n += 1
cur.execute('insert into zhurnal_vlivaniya values (?,?,?,?,?,?)',
            (time.strftime('%Y-%m-%d %H:%M:%S'), 'PARK-ATTESTACIYA-OBLAST-2S.csv',
             vsego, fakt_n + kont_n, 0,
             json.dumps({'фактов Б.7/Б.8': fakt_n, 'наблюдений человека': kont_n},
                        ensure_ascii=False)))
p.commit()
print('аттестация: строк %s -> фактов %s, наблюдений человека %s' % (vsego, fakt_n, kont_n))

# ---------- канонизация роли по ВСЕЙ базе ---------------------------------------
cur.execute("select id, dolzhnost from kontakt")
n = 0
for kid, dolzh in cur.fetchall():
    rol, krug = rol_i_krug(dolzh)
    cur.execute('update kontakt set rol=?, rang=? where id=?', (rol, krug, kid)); n += 1
p.commit()
print('роль проставлена контактам:', n)
print('--- распределение роли ---')
for r in cur.execute('select rol,rang,count(*) from kontakt group by 1,2 order by 2,3 desc'):
    print('  круг %s  %-40s %s' % (r[1], r[0][:40], r[2]))
print()
print('=== ИТОГО В БАЗЕ ===')
for q, t in (("select count(*) from fakt", 'фактов'),
             ("select count(distinct inn) from fakt", 'ИНН с фактом'),
             ("select count(distinct inn) from fakt where sila=1", 'ИНН с доказательством силы 1'),
             ("select count(*) from fakt_ssylka", 'ссылок'),
             ("select count(*) from contact_source", 'наблюдений контакта'),
             ("select count(distinct inn) from contact_source where vid='chelovek'", 'ИНН с ЧЕЛОВЕКОМ')):
    print('  %-36s %s' % (t, cur.execute(q).fetchone()[0]))
p.close()
