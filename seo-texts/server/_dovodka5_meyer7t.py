# -*- coding: utf-8 -*-
r"""Проба meyer7t, пятый проход (владелец 09.10: «делай так, чтобы почт, телефонов, ролей, ФИО у нас было не меньше,
чем в скриптах на сервере»; «не берёт ли наш почты из невидимой части страниц»): обход заново по 110 компаниям выборки
версией v3 — свой обход + серверный обогатитель (enrich_one) на том же сайте внутри обхода + отсев почт, невидимых людям;
закупки ЕИС — из прежних записей; затем чей номер, чей сайт, проверка сайта, опровергатели, копии на дроп. Прежние
журналы — копией «.bak-v2-<время>». Статус — meyer7t-dovodka5.json."""
import io, json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'; ДРОП = r'C:\seostat\drop\drop-storage'; НАБОР = 'meyer7t'; ВЕРСИЯ = 'v3-0910'
ENV = dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', POISK_NE_ZHDAT='1', KC_BEZ_CHECKO='1',
           KC_ZAKUPKI_OT='1e9', KC_POTOKOV='12', KC_POTOKOV_SHAGA='24', PROVIDER_FALLBACK_CHEAP='gpt-6-luna',
           KC_VERSIYA=ВЕРСИЯ)
МОДЕЛЬ = {'kc_sayt_proverka.py': 'gpt-6-sol'}
ЖУРНАЛЫ = ('-spisok.json', '-kontakty.jsonl', '-audit.jsonl', '-audit2.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl')
o = {'начало': time.strftime('%Y-%m-%d %H:%M'), 'версия': ВЕРСИЯ, 'шаги': {}}


def статус():
    п = os.path.join(DIR, НАБОР + '-dovodka5.json')
    with io.open(п, 'w', encoding='utf-8') as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
    shutil.copyfile(п, os.path.join(ДРОП, os.path.basename(п)))


def пуск(шаг):
    o['шаги'][шаг] = {'старт': time.strftime('%H:%M')}
    статус()
    лог = os.path.join(DIR, 'konveyer_%s_%s_%s.log' % (НАБОР, шаг[:-3] + '_5', time.strftime('%d%m-%H%M')))
    with open(лог, 'ab') as f:
        r = subprocess.run([sys.executable, '-u', os.path.join(DIR, шаг), '--nabor=' + НАБОР, '--shag=' + шаг + '_5'], cwd=DIR,
                           env=dict(ENV, PROVIDER_MODEL=МОДЕЛЬ.get(шаг, 'gpt-6-luna')), stdout=f, stderr=subprocess.STDOUT)
    o['шаги'][шаг].update({'конец': time.strftime('%H:%M'), 'код': r.returncode,
                           'хвост': io.open(лог, encoding='utf-8', errors='replace').read()[-400:]})
    статус()


def main():
    метка = time.strftime('%d%m-%H%M')
    for х in ЖУРНАЛЫ:
        п = os.path.join(DIR, НАБОР + х)
        if os.path.exists(п):
            shutil.copyfile(п, п + '.bak-v2-' + метка)
    o['бэкап'] = '.bak-v2-' + метка
    for шаг in ('kc_kontakty.py', 'kc_audit.py', 'kc_audit2.py', 'kc_sayt_proverka.py', 'kc_oproverzhenie.py'):
        пуск(шаг)
    for ф in (НАБОР + x for x in ЖУРНАЛЫ):
        shutil.copyfile(os.path.join(DIR, ф), os.path.join(ДРОП, ф))
    o['конец'] = time.strftime('%Y-%m-%d %H:%M')
    статус()


if __name__ == '__main__':
    main()
