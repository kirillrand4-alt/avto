# -*- coding: utf-8 -*-
r"""Загрузить в «Партию 935» ВСЕ мейеровские паспорта.

Владелец 27.08: «закинь все паспарта мейер в 935». Отличие от штатного
`dogruz_935`: тот берёт только паспорта с непустой «продукцией», а здесь идут
все непустые паспорта текущего формата у направления meyer — включая те, где
продукции нет, но есть оборудование, газы или мощности. Заслоны остаются
штатные: стоп-листы по ИНН и домену, конкуренты по флагу и по собственному
паспорту, приговор «чужой сайт», адрес, закреплённый за другим ИНН, и наши
собственные домены рассылки.

ВТОРАЯ МЕТКА «Чужой домен». Замер перед заливкой: из 5 614 адресов 3 603 на
бесплатной почте, 1 250 на домене собственного сайта компании, а 758 — на
ЧУЖОМ корпоративном домене. Часть из них законна (ящик у местного провайдера,
ЭДО-адрес вида ИНН_КПП@eo.tensor.ru), часть — явный брак: хлебозавод «Нива» с
адресом info@lada.ru, шоколадный «Спектр-Инвест» с rop@iktmail.ru. Разделять
их вслепую нельзя, а держать вне партии — значит не выполнить просьбу. Поэтому
грузим всех, а рисковым ставим вторую метку: в панели они видны отдельным
фильтром, и оператор решает сам.

    python dogruz_meyer.py            прикидка, ничего не пишет
    python dogruz_meyer.py --primenit собрать CSV, импортировать, проставить метки
"""
import csv
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (_DIR, os.path.dirname(_DIR), r'C:\sender'):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)
import dogruz_935 as D  # noqa: E402

ENRICH = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
SENDER = os.environ.get('SENDER_DB', r'C:\sender\sender.db')
МЕТКА_РИСКА = 'Чужой домен'
ЖУРНАЛ = r'C:\sender\_tmp\dogruz-meyer.jsonl'
БЕСПЛАТНЫЕ = {'mail.ru', 'yandex.ru', 'ya.ru', 'gmail.com', 'bk.ru', 'list.ru',
              'inbox.ru', 'rambler.ru', 'internet.ru', 'yahoo.com', 'icloud.com',
              'outlook.com', 'hotmail.com', 'vk.com', 'mail.com', 'gmail.ru'}


def _koren(u):
    u = re.sub(r'^https?://', '', (u or '').lower()).split('/')[0].split(':')[0]
    if u.startswith('www.'):
        u = u[4:]
    ч = u.split('.')
    if len(ч) > 2 and ч[-2] in ('com', 'co', 'org', 'net'):
        return '.'.join(ч[-3:])
    return '.'.join(ч[-2:]) if len(ч) > 1 else u


def _inny_meyer():
    c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    инны = {str(r[0]) for r in c.execute(
        'select f.inn from site_facts f join companies k on k.inn=f.inn '
        "where k.division like '%meyer%' and coalesce(f.facts_json,'')<>'' "
        'and coalesce(f.format,0)>=2')}
    c.close()
    return инны


def _riskovye(инны):
    """ИНН из партии, чей адрес сидит на ЧУЖОМ корпоративном домене.

    Считаем по тому, что РЕАЛЬНО лежит в панели, а не по строкам CSV: часть
    компаний была в панели раньше, им догруз только дописывает метку, и в CSV
    они не попадают вовсе — а адрес у них ровно такой же спорный.

    ЭДО-адрес Тензора (ИНН_КПП@eo.tensor.ru) риском НЕ считаем: он содержит ИНН
    самой компании, то есть принадлежит ей заведомо. Письмо туда бесполезно, но
    это вопрос отдачи, а не ошибочного адресата.
    """
    c = sqlite3.connect('file:%s?mode=ro' % ENRICH.replace('\\', '/'), uri=True)
    сайты = {str(r[0]): (r[1] or r[2] or '') for r in c.execute(
        "select inn, coalesce(site,''), coalesce(cand_site,'') from companies")}
    c.close()
    риск = {}
    s = sqlite3.connect('file:%s?mode=ro' % SENDER.replace('\\', '/'), uri=True)
    for r in s.execute("select coalesce(inn,'') inn, lower(coalesce(email,'')) em "
                       'from recipients where inn is not null'):
        инн = ''.join(ch for ch in str(r[0]) if ch.isdigit())
        if инн not in инны or '@' not in (r[1] or ''):
            continue
        дом = r[1].split('@')[-1]
        if дом in БЕСПЛАТНЫЕ or инн in r[1]:
            continue
        сайт = _koren(сайты.get(инн, ''))
        if сайт and дом == сайт:
            continue
        риск[инн] = r[1]
    s.close()
    return риск


def _pometit(инны, метка):
    """Дописать метку получателям с этими ИНН. Мелкими транзакциями."""
    if not инны:
        return 0
    s = sqlite3.connect(SENDER, timeout=90)
    s.execute('PRAGMA busy_timeout=60000')
    ts = time.strftime('%Y-%m-%dT%H:%M:%S')
    ряды = []
    q = ','.join('?' * len(инны))
    for r in s.execute("select id, coalesce(extra_json,'') ex from recipients "
                       'where inn in (%s)' % q, tuple(инны)):
        ряды.append((r[0], r[1]))
    сделано = 0
    for i in range(0, len(ряды), 50):
        кусок = ряды[i:i + 50]
        for _ in range(30):
            try:
                s.execute('BEGIN IMMEDIATE')
                for rid, ex in кусок:
                    try:
                        d = json.loads(ex) if (ex or '').strip() else {}
                        if not isinstance(d, dict):
                            d = {}
                    except Exception:  # noqa: BLE001
                        d = {}
                    гр = [g for g in (d.get('gruppy') or []) if str(g).strip()]
                    if метка in гр:
                        continue
                    d['gruppy'] = гр + [метка]
                    s.execute('update recipients set extra_json=?, updated_at=? '
                              'where id=?',
                              (json.dumps(d, ensure_ascii=False), ts, rid))
                    сделано += 1
                s.commit()
                break
            except sqlite3.OperationalError:
                try:
                    s.rollback()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(2)
    s.close()
    return сделано


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    инны = _inny_meyer()
    d = {'мейеровских_паспортов': len(инны)}
    if '--primenit' not in sys.argv:
        свод, теги, строки = D.собрать(инны, D.ГРУППА, vse_pochty=True)
        d['свод'] = свод
        d['тегов'] = len(теги)
        d['риск_среди_уже_в_панели'] = len(_riskovye(инны))
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0

    d['шаг1_сбор'] = D.применить(инны, [D.ГРУППА], D.ГРУППА, vse_pochty=True)
    csv_path = d['шаг1_сбор'].get('csv') or D.CSV_PATH
    if os.path.exists(csv_path):
        p = subprocess.run([sys.executable, '-m', 'sender', '--config',
                            r'C:\sender\sender.yaml', 'import', csv_path],
                           cwd=r'C:\sender', capture_output=True, text=True,
                           timeout=3600)
        d['шаг2_импорт'] = {'rc': p.returncode,
                            'вывод': ((p.stdout or '') + (p.stderr or ''))
                            .strip()[-400:]}
        # ВТОРОЙ ПРОХОД ОБЯЗАТЕЛЕН: импорт заводит получателя, но группу ему не
        # ставит. Без него компания в панели есть, а ни под один фильтр не
        # попадает — так уже было при заливке 17.08.
        d['шаг3_метки'] = D.применить(инны, [D.ГРУППА], D.ГРУППА, vse_pochty=True)

    риск = _riskovye(инны)
    d['риск_чужой_домен'] = len(риск)
    d['помечено_риском'] = _pometit(list(риск), МЕТКА_РИСКА)
    with open(ЖУРНАЛ, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
                            'итог': d, 'риск': риск}, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps(d, ensure_ascii=False, indent=1)[:3000])
    return 0


if __name__ == '__main__':
    sys.exit(main())
