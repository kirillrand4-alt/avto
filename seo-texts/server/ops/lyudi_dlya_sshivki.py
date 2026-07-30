# -*- coding: utf-8 -*-
"""Все мои люди с провенансом — второй сессии для сшивки.

Она просит отдать людей с ИНН, состояние по машине приклеит сама по своим
фактам. Её формат требует двух вещей, и обе разумны: у каждой пометки должна
быть ССЫЛКА НА ИСТОЧНИК, иначе это мнение, и число в отчёте читается
перечитыванием файла, а не счётчиком прогона.

Заодно проверяю себя её же правилом: сколько моих людей записано БЕЗ ссылки
на источник. Такие строки в общий файл идут с честной пометкой, а не
маскируются под доказанные.

Запуск: python lyudi_dlya_sshivki.py
"""
import csv
import os
import re
import sys

sys.path.insert(0, r'C:\sender\server')
import enrich_db as EDB  # noqa: E402

ИМЯ = 'LYUDI-1-SESSIYA-dlya-sshivki.csv'
ПАПКА = r'C:\sender\server'
_ДОБ = re.compile(r'\s*(?:доб|вн|внутр|ext)\.?\s*[:№]?\s*[\d\-]+\s*$', re.I)
_МОБ = re.compile(r'(?:\+?7|8)\D{0,3}9\d\d')
_800 = re.compile(r'8\D{0,3}800')


def д10(т):
    ц = re.sub(r'\D', '', _ДОБ.sub('', т or ''))
    return ц[-10:] if len(ц) >= 10 else ''


def на_дроп(путь, имя):
    import urllib.request
    урл = os.environ.get('DROP_URL', 'https://parsercompressor.online/drop')
    зпр = urllib.request.Request(
        урл.rstrip('/') + '/' + имя, data=open(путь, 'rb').read(), method='PUT',
        headers={'X-Drop-Token': os.environ.get('DROP_TOKEN', '')})
    with urllib.request.urlopen(зпр, timeout=180) as о:
        return о.read()[:200]


def main():
    db = EDB.EnrichDB()
    q = db.cx.execute
    тр = set(EDB.EnrichDB.TECH_ROLES)

    ряды = q(
        "SELECT p.inn, COALESCE(c.name,''), p.person, COALESCE(p.post,''), "
        "COALESCE(p.role,''), COALESCE(p.phone,''), COALESCE(p.email,''), "
        "COALESCE(p.source,''), COALESCE(p.source_url,''), "
        "COALESCE(p.observed_at,'') "
        'FROM people p LEFT JOIN companies c ON c.inn = p.inn '
        'ORDER BY p.inn').fetchall()

    без_ссылки = sum(1 for r in ряды if not r[8].strip())
    без_инн = sum(1 for r in ряды if not (r[0] or '').strip())
    print(f'людей всего: {len(ряды)}')
    print(f'  БЕЗ ссылки на источник: {без_ссылки} '
          f'({round(100 * без_ссылки / max(1, len(ряды)))}%)')
    print(f'  без ИНН: {без_инн}')

    # какие источники не дают ссылки — это чинить, а не прятать
    нет_ссылки_по_ист = {}
    for r in ряды:
        if not r[8].strip():
            нет_ссылки_по_ист[r[7] or '(пусто)'] = \
                нет_ссылки_по_ист.get(r[7] or '(пусто)', 0) + 1
    print('  источники без ссылки (топ-6):')
    for и, n in sorted(нет_ссылки_по_ист.items(), key=lambda x: -x[1])[:6]:
        print(f'    {n:>5}  {и}')

    путь = os.path.join(ПАПКА, ИМЯ)
    с_личным = 0
    with open(путь, 'w', encoding='utf-8-sig', newline='') as ф:
        в = csv.writer(ф, delimiter=';')
        в.writerow(['inn', 'kompaniya', 'fio', 'dolzhnost', 'rol',
                    'telefon', 'nomer_10cifr', 'lichnyy', 'pochta',
                    'istochnik', 'ssylka_na_istochnik', 'est_ssylka',
                    'tehLPR', 'kogda_vzyato'])
        for инн, комп, фио, пост, роль, тел, поч, ист, урл, когда in ряды:
            ц = д10(тел)
            личн = bool(ц) and bool(_МОБ.search(тел)) and not _800.search(тел)
            if личн:
                с_личным += 1
            в.writerow([инн, комп[:70], фио, пост[:100], роль, тел, ц,
                        'да' if личн else 'нет', поч, ист, урл,
                        'да' if урл.strip() else 'НЕТ',
                        'да' if роль in тр else 'нет', когда])
        ф.flush()
        os.fsync(ф.fileno())

    # ЧИСЛА ПЕРЕЧИТЫВАНИЕМ ФАЙЛА, а не счётчиком прогона — её правило
    строк = сум_личн = сум_тех = сум_без = 0
    предпр = set()
    with open(путь, encoding='utf-8-sig', newline='') as ф:
        for r in csv.DictReader(ф, delimiter=';'):
            строк += 1
            предпр.add(r['inn'])
            if r['lichnyy'] == 'да':
                сум_личн += 1
            if r['tehLPR'] == 'да':
                сум_тех += 1
            if r['est_ssylka'] == 'НЕТ':
                сум_без += 1
    print()
    print('=== ЧИСЛА ПЕРЕЧИТЫВАНИЕМ ФАЙЛА (не счётчиком прогона) ===')
    print(f'  строк {строк}, предприятий {len(предпр)}')
    print(f'  техЛПР {сум_тех}, с личным номером {сум_личн}')
    print(f'  без ссылки на источник {сум_без}')
    if сум_личн != с_личным:
        print(f'  !! счётчик прогона говорил {с_личным} — расхождение, '
              'верить файлу')
    try:
        на_дроп(путь, ИМЯ)
        print(f'  на дропе: {ИМЯ}')
    except Exception as e:  # noqa: BLE001
        print(f'  на дроп НЕ легло: {str(e)[:120]}')
    print(f'строк {строк}, личных {сум_личн}, без ссылки {сум_без}')


if __name__ == '__main__':
    main()
