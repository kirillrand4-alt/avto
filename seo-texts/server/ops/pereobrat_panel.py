# -*- coding: utf-8 -*-
"""Пересобрать базу панели целиком: свежие 1573 предприятия вместо 375.

Панель работала на снимке от 31.07: 375 предприятий, 17 512 фактов. За это
время вторая сессия вычистила центробежные (17 708 → 12 448 фактов) и собрала
свежую очередь на 1573 предприятия, а третья добавила людей и реквизиты.
Продавец всё это время звонил по данным недельной давности.

Сборщик `app/tools/build_centro_db.py` берёт ТРИ моих CSV: summary, details,
contacts. Значит обновить панель — это обновить их и запустить его.

Форматы взяты ИЗ КОДА СБОРЩИКА, а не из моего старого файла: если подсунуть
ему другие имена колонок, он соберёт пустую базу и не пожалуется —
`csv.DictReader` на отсутствующем ключе молча отдаёт None.

  summary  — одна строка на предприятие (та же ширина, что была)
  details  — разделы КАРТОЧКА / ФАКТ / ЧЕЛОВЕК / НОМЕР / НОВОСТЬ
  contacts — люди с привязанным номером (`BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv`)

Запуск: python pereobrat_panel.py [--apply]
"""
import csv
import io
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict

ДРОП = r'C:\seostat\drop\drop-storage'
ПАПКА = r'C:\sender\server'
ПРИМЕНИТЬ = '--apply' in sys.argv
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', str(т or '')))
    return ц[-10:] if len(ц) >= 10 else ''


def вид(ц):
    return 'нет номера' if not ц else ('мобильный' if ц.startswith('9')
                                       else 'городской')


def читать(имя):
    п = os.path.join(ДРОП, имя)
    if not os.path.exists(п):
        print(f'  НЕТ файла {имя}')
        return []
    csv.field_size_limit(10 ** 7)
    return list(csv.DictReader(
        io.StringIO(open(п, encoding='utf-8-sig', errors='replace').read()),
        delimiter=';'))


def на_дроп(путь, имя):
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    зпр = urllib.request.Request(
        урл.rstrip('/') + '/' + имя, data=open(путь, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(зпр, timeout=600) as о:
        return о.read()[:120]


def main():
    очередь = читать('OCHERED-centrobezhnye.csv')
    предпр = {(r.get('inn') or '').strip(): r for r in очередь
              if (r.get('inn') or '').strip()}
    print(f'предприятий в свежей очереди: {len(предпр)}')

    база = читать('BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv')
    свод = читать('SVODNAYA-centrobezhnye.csv')
    хар = читать('HARAKTERISTIKI-mashin-po-predpriyatiyam.csv')
    print(f'общая база: {len(база)} строк, сводная: {len(свод)}, '
          f'характеристики: {len(хар)}')

    # СОСТОЯНИЕ СЧИТАЕМ САМИ, а не берём из строки человека. Первый прогон
    # показал «состояние не подтверждено у 1406 из 1573» — и это был не факт
    # о данных, а мой дефект: состояние бралось из первой строки ЛЮДЕЙ, а у
    # 1229 предприятий людей нет вовсе, поле выходило пустым. Пустая колонка
    # читается как «не доказано», хотя доказательство есть.
    def _чист_тип(t):
        return any(x.strip().startswith('центробежн') and 'насос' not in x
                   for x in (t or '').split('|'))

    состояние = defaultdict(set)
    ссылка_сост = {}
    for r in свод:
        if _чист_тип(r.get('tip_mashiny')) and r.get('sreda') == 'воздух':
            и = (r.get('inn') or '').strip()
            п = (r.get('pometka') or '').strip()
            if и and п:
                состояние[и].add(п)
                ссылка_сост.setdefault(и, (r.get('ssylka_na_istochnik') or '').strip())
    print(f'предприятий с доказанным состоянием (центробежная+воздух): '
          f'{len(состояние)}')

    прио = {}
    for r in свод:
        и = (r.get('inn') or '').strip()
        if и and и not in прио:
            прио[и] = r
    харт = {}
    for r in хар:
        и = (r.get('inn') or '').strip()
        if и:
            харт.setdefault(и, []).append(r)

    # ---------- SUMMARY: одна строка на предприятие
    # НАБОР КОЛОНОК — РОВНО ТОТ, ЧТО СБОРЩИК УЖЕ ПРИНИМАЛ. Свой сокращённый
    # список стоил падения «no such column: novost»: сборщик читает не только
    # то, что я счёл нужным, а весь заголовок прежнего файла. Хорошо, что
    # упал — молча собрал бы базу без новостей.
    сум_поля = [
        'inn', 'predpriyatie', 'pometka', 'tipy_mashin', 'sreda', 'marki',
        'sostoyaniy', 'vyvod_ekspertizy', 'data_zakluchenia', 'vyruchka_rub',
        'chistaya_pribyl', 'ssch', 'ball_prioriteta', 'okved',
        'oborudovanie_po_okved', 'region', 'adres', 'status_egrul', 'direktor',
        'sayt', 'pochta', 'telefony_iz_bazy', 'telefony_predpriyatiya',
        'lyudej_v_baze', 'tehnicheskih', 'lyudej_iz_faylov',
        'tehnicheskie_lyudi', 'lyudi_iz_faylov', 'proverok_nadzora',
        'v_baze_obzvona', 'segment', 'novost', 'novost_ssylka',
        'chego_ne_hvataet', 'faktov_centrobezhnyh', 'sostoyaniya_po_faktam',
        'ssylki_na_istochniki', 'citaty_dokazatelstv', 'daty_faktov',
        'marki_iz_faktov', 'sreda_po_faktam', 'moy_prioritet',
        'vazhnost_pokupki', 'dostupnost_kontakta', 'prioritet_pochemu',
        'lyudi_moi_vsego', 'lyudi_moi_podrobno', 'istochnik_dopolneniya',
        'lyudi_s_privyazannym_nomerom', 'tehnicheskie_s_nomerom',
        'lyudej_vsego_svedeno', 'lyudej_s_nomerom', 'tehnicheskih_s_nomerom',
        'nomera_bez_vladelca', 'nomerov_bez_vladelca',
        'sostoyanie_potverzhdeno_faktom', 'ssylka_sostoyaniya']
    по_инн_люди = defaultdict(list)
    for r in база:
        и = (r.get('inn') or '').strip()
        if и and (r.get('fio') or '').strip():
            по_инн_люди[и].append(r)

    сум = []
    for и, o in sorted(предпр.items()):
        p = прио.get(и, {})
        люди = по_инн_люди.get(и, [])
        тех = [x for x in люди if x.get('tehLPR') == 'да']
        подр = ' ;; '.join(
            f"{x.get('fio','')} | {x.get('dolzhnost','')} | "
            f"{x.get('vse_nomera','')} | {x.get('rol_kanon','')} | "
            f"{x.get('istochnik','')}" for x in люди[:12])
        сост = ' | '.join(sorted(состояние.get(и, ())))
        з = {k: '' for k in сум_поля}
        з.update({
            'inn': и,
            'predpriyatie': (o.get('predpriyatie') or '')[:90],
            'pometka': сост.split(' | ')[0] if сост else '',
            'tipy_mashin': (o.get('tipy_mashin') or '')[:80],
            'sreda': o.get('sreda_dokazana') or '',
            'marki': (o.get('marki') or '')[:150],
            'sostoyaniy': o.get('sostoyaniy') or '',
            'vyvod_ekspertizy': (o.get('vyvod_ekspertizy') or '')[:60],
            'data_zakluchenia': o.get('data_zakluchenia') or '',
            'vyruchka_rub': p.get('vyruchka_rub') or '',
            'okved': p.get('okved') or '',
            'region': o.get('region') or p.get('region') or '',
            'adres': (p.get('adres') or '')[:90],
            'status_egrul': p.get('status_egrul') or '',
            'direktor': p.get('direktor') or '',
            'sayt': o.get('sayt') or p.get('sayt') or '',
            'pochta': o.get('luchshaya_pochta') or p.get('pochta_predpriyatiya') or '',
            'telefony_iz_bazy': (o.get('telefony_predpriyatiya') or '')[:70],
            'telefony_predpriyatiya': (o.get('telefony_predpriyatiya') or '')[:70],
            'lyudej_v_baze': len(люди),
            'tehnicheskih': len(тех),
            'lyudej_iz_faylov': len(люди),
            'tehnicheskie_lyudi': ' | '.join(
                f"{x.get('fio','')} ({x.get('dolzhnost') or x.get('rol_kanon','')})"
                for x in тех[:8]),
            'lyudi_iz_faylov': ' | '.join(
                f"{x.get('fio','')} ({x.get('dolzhnost') or x.get('rol_kanon','')})"
                for x in люди[:8]),
            'proverok_nadzora': o.get('proverok_nadzora') or '',
            'novost': (o.get('novost') or p.get('novost') or '')[:200],
            'novost_ssylka': o.get('novost_ssylka') or p.get('novost_ssylka') or '',
            'chego_ne_hvataet': (o.get('chego_ne_hvataet') or '')[:80],
            'sostoyaniya_po_faktam': сост,
            'ssylki_na_istochniki': ссылка_сост.get(и, '')
                                    or (p.get('ssylka_na_istochnik') or ''),
            'marki_iz_faktov': (o.get('marki') or '')[:150],
            'sreda_po_faktam': o.get('sreda_dokazana') or '',
            'moy_prioritet': p.get('prioritet') or '',
            'vazhnost_pokupki': p.get('vazhnost_pokupki') or '',
            'dostupnost_kontakta': p.get('dostupnost_kontakta') or '',
            'prioritet_pochemu': (p.get('prioritet_pochemu') or '')[:150],
            'lyudi_moi_vsego': len(люди),
            'lyudi_moi_podrobno': подр[:900],
            'istochnik_dopolneniya': p.get('kto_vnes') or '',
            'lyudej_vsego_svedeno': len(люди),
            'lyudej_s_nomerom': sum(1 for x in люди if (x.get('vse_nomera') or '').strip()),
            'tehnicheskih_s_nomerom': sum(
                1 for x in тех if (x.get('vse_nomera') or '').strip()),
            'sostoyanie_potverzhdeno_faktom': сост,
            'ssylka_sostoyaniya': ссылка_сост.get(и, ''),
        })
        сум.append(з)

    # ---------- DETAILS: разделы, имена колонок из кода сборщика
    дет_поля = ['razdel', 'inn', 'predpriyatie', 'chto', 'kto_ili_marka',
                'dolzhnost_ili_tip', 'rol', 'nomer_10cifr', 'vid_nomera',
                'pochta', 'data', 'chem_dokazano', 'citata', 'ssylka',
                'istochnik', 'tehLPR', 'fio', 'dolzhnost', 'rol_kanon',
                'ssylka_na_istochnik']
    имена = {и: (o.get('predpriyatie') or '')[:90] for и, o in предпр.items()}
    дет = []

    def ряд(**kw):
        d = {k: '' for k in дет_поля}
        d.update(kw)
        дет.append(d)

    for и in sorted(предпр):
        ряд(razdel='КАРТОЧКА', inn=и, predpriyatie=имена[и],
            chto='карточка предприятия', istochnik='очередь центробежных')

    # ФАКТЫ из свежего файла второй сессии, только по нашим ИНН
    фактов = 0
    csv.field_size_limit(10 ** 7)
    п_ф = os.path.join(ДРОП, 'SVOD-tri-sostoyaniya.csv')
    if os.path.exists(п_ф):
        with open(п_ф, encoding='utf-8-sig', errors='replace', newline='') as ф:
            for r in csv.DictReader(ф, delimiter=';'):
                и = (r.get('inn') or '').strip()
                if и not in предпр:
                    continue
                фактов += 1
                ряд(razdel='ФАКТ', inn=и, predpriyatie=имена[и],
                    chto=(r.get('sostoyanie') or '')[:60],
                    kto_ili_marka=(r.get('marki') or '')[:80],
                    dolzhnost_ili_tip=(r.get('tip_mashiny')
                                       or r.get('obekt') or '')[:60],
                    rol=(r.get('sreda') or ''),
                    data=(r.get('data') or ''),
                    chem_dokazano=(r.get('chem_dokazano') or '')[:120],
                    citata=(r.get('tekst') or '')[:300],
                    ssylka=(r.get('ssylka') or ''),
                    istochnik=(r.get('istochnik') or '')[:60])
    print(f'фактов по нашим предприятиям: {фактов}')

    # ЛЮДИ и НОМЕРА из общей базы
    людей = номеров = 0
    for r in база:
        и = (r.get('inn') or '').strip()
        if и not in предпр:
            continue
        фио = (r.get('fio') or '').strip()
        ном = (r.get('mobilnyy_10cifr') or '').strip() or д10(
            (r.get('vse_nomera') or '').split(' | ')[0])
        if фио:
            людей += 1
            ряд(razdel='ЧЕЛОВЕК', inn=и, predpriyatie=имена[и],
                chto='контакт человека', fio=фио,
                kto_ili_marka=фио,
                dolzhnost=(r.get('dolzhnost') or '')[:90],
                dolzhnost_ili_tip=(r.get('dolzhnost') or '')[:90],
                rol=(r.get('rol_kanon') or ''),
                rol_kanon=(r.get('rol_kanon') or ''),
                nomer_10cifr=ном, vid_nomera=вид(ном),
                pochta=(r.get('pochta') or ''),
                data=(r.get('data_fakta') or ''),
                istochnik=(r.get('istochnik') or '')[:60],
                ssylka=(r.get('ssylka_na_istochnik') or ''),
                ssylka_na_istochnik=(r.get('ssylka_na_istochnik') or ''),
                tehLPR=(r.get('tehLPR') or 'нет'))
        elif (r.get('vse_nomera') or '').strip():
            for ц in [д10(x) for x in (r.get('vse_nomera') or '').split(' | ')]:
                if ц:
                    номеров += 1
                    ряд(razdel='НОМЕР', inn=и, predpriyatie=имена[и],
                        chto='ВЛАДЕЛЕЦ НЕИЗВЕСТЕН', nomer_10cifr=ц,
                        vid_nomera=вид(ц),
                        istochnik=(r.get('istochnik') or 'база')[:60])
    print(f'людей: {людей}, номеров без владельца: {номеров}')

    # ---------- запись
    п_сум = os.path.join(ПАПКА, 'SVOD-VSE-OBEDINENNYY.csv')
    п_дет = os.path.join(ПАПКА, 'POLNYY-VSE-vsya-informaciya.csv')
    with open(п_сум, 'w', encoding='utf-8-sig', newline='') as ф:
        w = csv.DictWriter(ф, fieldnames=сум_поля, delimiter=';')
        w.writeheader()
        w.writerows(сум)
        ф.flush()
        os.fsync(ф.fileno())
    with open(п_дет, 'w', encoding='utf-8-sig', newline='') as ф:
        w = csv.DictWriter(ф, fieldnames=дет_поля, delimiter=';')
        w.writeheader()
        w.writerows(дет)
        ф.flush()
        os.fsync(ф.fileno())
    print(f'summary: {len(сум)} строк, details: {len(дет)} строк')

    if not ПРИМЕНИТЬ:
        print('\nсухой прогон: файлы собраны, сборщик НЕ запускался. '
              'Повторить с --apply')
        return

    # бэкап базы перед пересборкой — доливка внутри неё исчезнет, и это
    # ожидаемо: она уже учтена в contacts-файле
    цель = r'C:\seostat\data\centrifugal.db'
    if os.path.exists(цель):
        коп = цель + '.bak-' + str(int(time.time()))
        shutil.copy2(цель, коп)
        print(f'копия старой базы: {os.path.basename(коп)}')

    врем = цель + '.new'
    р = subprocess.run(
        [r'C:\seostat\.venv\Scripts\python.exe', '-m', 'app.tools.build_centro_db',
         '--summary', п_сум, '--details', п_дет,
         '--contacts', os.path.join(ДРОП, 'BAZA-CENTROBEZHNIKI-OBSHCHAYA.csv'),
         '--output', врем],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=r'C:\seostat', timeout=900)
    print('сборщик rc=', р.returncode)
    print((р.stdout or '')[-1500:])
    if р.returncode != 0:
        print('ОШИБКА СБОРЩИКА:', (р.stderr or '')[-1200:])
        return

    # ПРОВЕРКА ДО ПОДМЕНЫ: пустая база собирается так же успешно, как полная
    import sqlite3
    c = sqlite3.connect(врем)
    n_к = c.execute('SELECT COUNT(*) FROM company').fetchone()[0]
    n_л = c.execute('SELECT COUNT(*) FROM person').fetchone()[0]
    n_ф = c.execute('SELECT COUNT(*) FROM fact').fetchone()[0]
    n_т = c.execute("SELECT COUNT(*) FROM contact WHERE kind='phone'").fetchone()[0]
    c.close()
    print(f'СОБРАНО: предприятий {n_к}, людей {n_л}, фактов {n_ф}, телефонов {n_т}')
    if n_к < 100 or n_ф < 1000:
        print('СЛИШКОМ МАЛО — подменять базу не буду, старая остаётся на месте')
        return
    shutil.move(врем, цель)
    print('база подменена')

    for п, имя in ((п_сум, 'SVOD-VSE-OBEDINENNYY.csv'),
                   (п_дет, 'POLNYY-VSE-vsya-informaciya.csv')):
        try:
            на_дроп(п, имя)
            print(f'  на дропе: {имя}')
        except Exception as e:  # noqa: BLE001
            print(f'  {имя} на дроп НЕ легло: {str(e)[:100]}')


if __name__ == '__main__':
    main()
