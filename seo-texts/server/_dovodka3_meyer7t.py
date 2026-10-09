# -*- coding: utf-8 -*-
r"""Проба meyer7t, третий проход: вернуть сайт из выдачи, где на нём ИНН компании (moskart.ru, tiretsalt.ru), и обойти их.
Был второй проход (владелец 09.10: «почему не всё найдено из контактов? confectum.org/contacts/»):
сайты, найденные агентами, — в список; обход заново по 110 компаниям выборки (контакты из JSON на странице);
чей номер, чей сайт, проверка сайта, опровергатели — по новым сайтам; копии на дроп. Статус — meyer7t-dovodka2.json."""
import io, json, os, shutil, subprocess, sys, time
DIR = r'C:\sender\server'; ДРОП = r'C:\seostat\drop\drop-storage'; НАБОР = 'meyer7t'
ENV = dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', POISK_NE_ZHDAT='1', KC_BEZ_CHECKO='1',
           KC_ZAKUPKI_OT='1e9', KC_POTOKOV='24', KC_POTOKOV_SHAGA='24', PROVIDER_FALLBACK_CHEAP='gpt-6-luna')
МОДЕЛЬ = {'kc_sayt_proverka.py': 'gpt-6-sol'}
o = {'начало': time.strftime('%Y-%m-%d %H:%M'), 'шаги': {}}


def статус():
    п = os.path.join(DIR, НАБОР + '-dovodka3.json')
    with io.open(п, 'w', encoding='utf-8') as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
    shutil.copyfile(п, os.path.join(ДРОП, os.path.basename(п)))


def пуск(шаг):
    o['шаги'][шаг] = {'старт': time.strftime('%H:%M')}
    статус()
    лог = os.path.join(DIR, 'konveyer_%s_%s_%s.log' % (НАБОР, шаг[:-3] + '_3', time.strftime('%d%m-%H%M')))
    with open(лог, 'ab') as f:
        r = subprocess.run([sys.executable, '-u', os.path.join(DIR, шаг), '--nabor=' + НАБОР, '--shag=' + шаг + '_3'], cwd=DIR,
                           env=dict(ENV, PROVIDER_MODEL=МОДЕЛЬ.get(шаг, 'gpt-6-luna')), stdout=f, stderr=subprocess.STDOUT)
    o['шаги'][шаг].update({'конец': time.strftime('%H:%M'), 'код': r.returncode,
                           'хвост': io.open(лог, encoding='utf-8', errors='replace').read()[-400:]})
    статус()


def main():
    import zamok
    сп_п = os.path.join(DIR, НАБОР + '-spisok.json')
    with zamok.замок(сп_п):
        сп = zamok.прочитать(сп_п)
        for i in ('7718528015', '3814011769'):
            к = сп['компании'].get(i)
            if к and к.get('сайт_был'):
                к['сайт'], к['сайт_агента'] = к.pop('сайт_был'), к['сайт']
                к.pop('сайт_откуда', None)
                o.setdefault('возвращено', []).append([i, к['сайт']])
        zamok.записать_атомарно(сп_п, сп)
    for шаг in ('kc_kontakty.py', 'kc_audit.py', 'kc_audit2.py', 'kc_sayt_proverka.py', 'kc_oproverzhenie.py'):
        пуск(шаг)
    for ф in (НАБОР + x for x in ('-spisok.json', '-kontakty.jsonl', '-audit.jsonl', '-audit2.jsonl', '-sayt-proverka.jsonl',
                                   '-oprov.jsonl')):
        shutil.copyfile(os.path.join(DIR, ф), os.path.join(ДРОП, ф))
    o['конец'] = time.strftime('%Y-%m-%d %H:%M')
    статус()


if __name__ == '__main__':
    main()
