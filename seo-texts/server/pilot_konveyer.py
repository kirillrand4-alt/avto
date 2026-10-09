# -*- coding: utf-8 -*-
r"""Пилот плана Meyer (владелец 08.10): конвейер после поиска. Ждёт окончания pilot_poisk.py (строка «готово»
в последнем логе pilot_poisk_*.log), затем шаги плана в наборе pilot (KC_NABOR=pilot, POISK_NABOR=pilot):
разбор -> отбор + обратная сверка -> обход (номера + почты + роли) -> чей номер -> чей сайт -> модель о сайте ->
ОПРОВЕРГАТЕЛИ -> вход агентам (без сайта + опровергнутые) -> агенты (лимит по балансу xmlriver) -> перепроверка.
Статус: C:\sender\server\pilot-konveyer.json (+ дроп). Запуск детачем: _pusk_pilot_konveyer.py.
"""
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import time

DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
НАБОР = os.environ.get('POISK_NABOR', 'pilot')  # для полного прогона — свой набор (meyer7 и т.п.)
СТАТУС = os.path.join(DIR, НАБОР + '-konveyer.json')
# 09.10: + сайты по названию для компаний из каталогов (после отбора) и проверка доп. ОКВЭД по сайту (после обхода)
ВСЕ_ШАГИ = ['poisk_razbor.py', 'pilot_otbor.py', 'pilot_sayty_dobor.py', 'kc_kontakty.py', 'pilot_dop_proverka.py',
            'pilot_pasport.py', 'kc_audit.py', 'kc_audit2.py', 'kc_sayt_proverka.py', 'kc_oproverzhenie.py', 'kc_glubokiy_vhod.py',
            'kc_agent_glubokiy.py', 'kc_agent_glubokiy.py:хвост', 'kc_agent_pereproverka.py']
С_ШАГА = int(os.environ.get('PILOT_S_SHAGA', '0'))
# модель по шагам (сравнение моделей 09.10, решение владельца «согласен»): GPT-6 Luna — классификация (94% совпадения с
# эталоном при $0,0002 за вызов), GPT-6 Sol — проверка сайта (лучшая, 96%) и агенты-исследователи (многошаговые)
# агенты (сравнение Luna/Sol 09.10 на 100 одинаковых компаниях): Sol находит ~в 1,5 раза больше номеров ЛПР и лучше на
# выручке 0,6–2 млрд; ниже ~120 млн ₽ обе модели не находят почти ничего. Решение владельца 09.10 («средний вариант»):
# от KC_AGENT_OT (500 млн) — Sol; хвост от KC_AGENT_OT_HVOST (120 млн) до 500 млн — AGENT_HVOST_MODEL (Luna); ниже — нет
МОДЕЛЬ_ШАГА = {'kc_sayt_proverka.py': 'gpt-6-sol', 'kc_agent_glubokiy.py': 'gpt-6-sol',
               'kc_agent_glubokiy.py:хвост': os.environ.get('AGENT_HVOST_MODEL', 'gpt-6-luna')}
МОДЕЛЬ_ОСН = os.environ.get('PILOT_MODEL', 'gpt-6-luna')
ШАГИ = ВСЕ_ШАГИ[С_ШАГА:]


def статус(o):
    with io.open(СТАТУС, 'w', encoding='utf-8') as f:
        json.dump(o, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    shutil.copyfile(СТАТУС, os.path.join(ДРОП, НАБОР + '-konveyer.json'))


def поиск_готов():
    логи = sorted(glob.glob(os.path.join(DIR, НАБОР + '_poisk_*.log')), key=os.path.getmtime)
    if not логи:
        return True
    return 'готово' in io.open(логи[-1], encoding='utf-8', errors='replace').read()[-600:]


def питон_жив(шаблон):
    """Есть живой python-процесс с командной строкой по шаблону -like. 09.10: «(...).Count» из Python возвращал пусто
    при живом процессе (доводка пробы стартовала раньше конца обхода) — перечисляем PID; фильтр по имени python
    обязателен: командная строка самого powershell тоже содержит шаблон."""
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and "
                        "$_.CommandLine -like '%s' } | ForEach-Object { $_.ProcessId }" % шаблон],
                       capture_output=True, text=True, timeout=120)
    return bool(r.stdout.split())


def разбор_жив():
    """Ранний разбор (_pusk_*_razbor.py) ещё идёт? Два разбора в один файл писать не должны."""
    return питон_жив('*server\\poisk_razbor.py*')


def main():
    o = {'начало': time.strftime('%Y-%m-%d %H:%M'), 'шаги': {}}
    while not поиск_готов():
        o['ждём'] = 'поиск ещё идёт ' + time.strftime('%H:%M')
        статус(o)
        time.sleep(60)
    while разбор_жив():
        o['ждём'] = 'ранний разбор ещё идёт ' + time.strftime('%H:%M')
        статус(o)
        time.sleep(60)
    o.pop('ждём', None)
    env = dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', POISK_NE_ZHDAT='1',
               POISK_CHECKO_MINUT='40', KC_AGENT_OT=os.environ.get('KC_AGENT_OT', '500e6'),
               KC_BEZ_CHECKO='1', KC_ZAKUPKI_OT=os.environ.get('KC_ZAKUPKI_OT', '1e9'),
               KC_POTOKOV_SHAGA=os.environ.get('KC_POTOKOV_SHAGA', '24'), KC_AGENT_POTOKOV=os.environ.get('KC_AGENT_POTOKOV', '30'),
               PASPORT_POTOKOV=os.environ.get('PASPORT_POTOKOV', '24'),
               KC_POTOKOV=os.environ.get('KC_POTOKOV', '24'),
               # 09.10, тест паспорта: молчащая Luna в GP.call тихо уходила на Claude Haiku (3 из 40 вызовов) — дороже и
               # со скрытым довеском шлюза; запасная для дешёвых моделей — GPT-6 Luna (для неё самой — GPT-5.6 Luna)
               PROVIDER_FALLBACK_CHEAP=os.environ.get('PROVIDER_FALLBACK_CHEAP', 'gpt-6-luna'))  # обход: без этого у не-pilot наборов 6 потоков
    for n, шаг in enumerate(ШАГИ):
        ключ = '%d %s' % (n + 1 + С_ШАГА, шаг)
        модель = МОДЕЛЬ_ШАГА.get(шаг, МОДЕЛЬ_ОСН)
        if модель == 'нет':
            continue
        файл, _, режим = шаг.partition(':')
        env_шага = dict(env, PROVIDER_MODEL=модель)
        if режим == 'хвост':
            env_шага['KC_AGENT_OT'] = os.environ.get('KC_AGENT_OT_HVOST', '120e6')  # сделанных Sol агент пропустит сам
        o['шаги'][ключ] = {'старт': time.strftime('%Y-%m-%d %H:%M'), 'модель': модель}
        статус(o)
        лог = os.path.join(DIR, 'konveyer_%s_%s_%s.log' % (НАБОР, файл[:-3] + ('_' + режим if режим else ''),
                                                           time.strftime('%d%m-%H%M')))
        for попытка in range(2):
            with open(лог, 'ab') as f:
                r = subprocess.run([sys.executable, '-u', os.path.join(DIR, файл)], cwd=DIR, env=env_шага,
                                   stdout=f, stderr=subprocess.STDOUT)
            if r.returncode == 0:
                break
        o['шаги'][ключ].update({'конец': time.strftime('%Y-%m-%d %H:%M'), 'код': r.returncode,
                               'хвост': io.open(лог, encoding='utf-8', errors='replace').read()[-500:]})
        статус(o)
        if r.returncode != 0 and шаг in ('poisk_razbor.py', 'pilot_otbor.py', 'pilot_sayty_dobor.py', 'kc_kontakty.py'):
            o['стоп'] = 'шаг %s упал — дальше без него нельзя' % шаг
            статус(o)
            return
    for ф in (НАБОР + x for x in ('-razbor.jsonl', '-spisok.json', '-reestr.json', '-zenka.json', '-kontakty.jsonl',
                                   '-audit.jsonl', '-audit2.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl', '-glubokiy.jsonl',
                                   '-glubokiy2.jsonl', '-serp.jsonl', '-dop.jsonl', '-sayty-dobor.jsonl', '-klass.jsonl',
                                   '-pasport.jsonl')):
        if os.path.exists(os.path.join(DIR, ф)):
            shutil.copyfile(os.path.join(DIR, ф), os.path.join(ДРОП, ф))
    o['конец'] = time.strftime('%Y-%m-%d %H:%M')
    статус(o)


# ---------------------------------------------------------------- волны (09.10, владелец: «да, делай что предложил»)
# PILOT_VOLNY=1: не ждать конца поиска. Пока поиск идёт — волна каждые PILOT_VOLNA_MIN минут по уже найденному: каждый
# шаг доделывает только новое (резюм), отбор пишет снимки списка (PILOT_SNIMKI=1) и обход берёт уже решённые компании;
# сайты по названию, доп. ОКВЭД, паспорт и агенты — фоном; агенты Sol (от KC_AGENT_OT) и Luna (KC_AGENT_OT_HVOST..KC_AGENT_OT)
# параллельно, Luna — в свой файл. Поиск закончился — финальный проход: всё по порядку, ожидание фоновых шагов, слияние
# журналов агентов, перепроверка. Второй экземпляр шага не запускается: метка «--nabor=<набор> --shag=<шаг>» в командной
# строке каждого шага и проверка живых процессов (дети переживают перезапуск оркестратора).
ВОЛНЫ = os.environ.get('PILOT_VOLNY') == '1'
ВОЛНА_МИН = float(os.environ.get('PILOT_VOLNA_MIN', '150'))
ОТБОР_ЖДАТЬ_МИН = float(os.environ.get('PILOT_OTBOR_ZHDAT_MIN', '60'))
ЛУНА_ФАЙЛ = 'glubokiy-hvost.jsonl'


def метка(шаг):
    файл, _, режим = шаг.partition(':')
    return '--nabor=%s --shag=%s' % (НАБОР, файл + ('_hvost' if режим else ''))


def процесс_идёт(шаг):
    """Живой python-процесс этого шага этого набора (метка — последние аргументы командной строки)."""
    return питон_жив('*' + метка(шаг))


class Волны:
    def __init__(self):
        self.o = {'начало': time.strftime('%Y-%m-%d %H:%M'), 'режим': 'волны', 'шаги': {}, 'фон': {}, 'волна': 0}
        self.фон = {}
        self.env = dict(os.environ, KC_NABOR=НАБОР, POISK_NABOR=НАБОР, KC_CEL='meyer', POISK_NE_ZHDAT='1',
                        POISK_CHECKO_MINUT='40', KC_AGENT_OT=os.environ.get('KC_AGENT_OT', '500e6'),
                        KC_BEZ_CHECKO='1', KC_ZAKUPKI_OT=os.environ.get('KC_ZAKUPKI_OT', '1e9'),
                        KC_POTOKOV_SHAGA=os.environ.get('KC_POTOKOV_SHAGA', '24'),
                        KC_AGENT_POTOKOV=os.environ.get('KC_AGENT_POTOKOV', '30'),
                        PASPORT_POTOKOV=os.environ.get('PASPORT_POTOKOV', '24'), KC_POTOKOV=os.environ.get('KC_POTOKOV', '24'),
                        PROVIDER_FALLBACK_CHEAP=os.environ.get('PROVIDER_FALLBACK_CHEAP', 'gpt-6-luna'), PILOT_SNIMKI='1')

    def env_шага(self, шаг):
        e = dict(self.env, PROVIDER_MODEL=МОДЕЛЬ_ШАГА.get(шаг, МОДЕЛЬ_ОСН))
        if шаг.endswith(':хвост'):
            e.update(KC_AGENT_OT=os.environ.get('KC_AGENT_OT_HVOST', '120e6'), KC_AGENT_DO=self.env['KC_AGENT_OT'],
                     KC_AGENT_FAYL=ЛУНА_ФАЙЛ)
        return e

    def статус(self):
        self.o['фон'] = {ш: ('идёт' if п.poll() is None else 'код %s' % п.returncode) for ш, п in self.фон.items()}
        статус(self.o)

    def занят(self, шаг):
        п = self.фон.get(шаг)
        return (п is not None and п.poll() is None) or процесс_идёт(шаг)

    def лог(self, шаг):
        файл, _, режим = шаг.partition(':')
        return os.path.join(DIR, 'konveyer_%s_%s_%s.log' % (НАБОР, файл[:-3] + ('_' + режим if режим else ''),
                                                            time.strftime('%d%m-%H%M')))

    def пуск(self, шаг, фоном=False):
        """-> код возврата (блокирующий) | 'фон' | 'занят'."""
        if self.занят(шаг):
            self.o['шаги'].setdefault(шаг, {})['пропуск'] = 'уже идёт %s' % time.strftime('%H:%M')
            self.статус()
            return 'занят'
        файл = шаг.partition(':')[0]
        cmd = [sys.executable, '-u', os.path.join(DIR, файл)] + метка(шаг).split()
        self.o['шаги'][шаг] = {'старт': time.strftime('%Y-%m-%d %H:%M'), 'модель': МОДЕЛЬ_ШАГА.get(шаг, МОДЕЛЬ_ОСН),
                               'волна': self.o['волна'], 'фоном': фоном}
        self.статус()
        лог = self.лог(шаг)
        if фоном:
            with open(лог, 'ab') as f:
                self.фон[шаг] = subprocess.Popen(cmd, cwd=DIR, env=self.env_шага(шаг), stdout=f, stderr=subprocess.STDOUT)
            self.статус()
            return 'фон'
        with open(лог, 'ab') as f:
            r = subprocess.run(cmd, cwd=DIR, env=self.env_шага(шаг), stdout=f, stderr=subprocess.STDOUT)
        self.o['шаги'][шаг].update({'конец': time.strftime('%Y-%m-%d %H:%M'), 'код': r.returncode,
                                    'хвост': io.open(лог, encoding='utf-8', errors='replace').read()[-500:]})
        self.статус()
        return r.returncode

    def ждать(self, шаги, мин=None):
        t0 = time.time()
        while any(self.занят(ш) for ш in шаги):
            if мин is not None and time.time() - t0 > мин * 60:
                return False
            self.статус()
            time.sleep(60)
        return True

    def слить_луну(self):
        """Журнал агентов Luna -> общий журнал агентов (только когда оба прохода стоят)."""
        п = os.path.join(DIR, НАБОР + '-' + ЛУНА_ФАЙЛ)
        if not os.path.exists(п) or self.занят('kc_agent_glubokiy.py') or self.занят('kc_agent_glubokiy.py:хвост'):
            return
        with io.open(п, encoding='utf-8', errors='replace') as f:
            строки = [s for s in f if s.strip()]
        with io.open(os.path.join(DIR, НАБОР + '-glubokiy.jsonl'), 'a', encoding='utf-8') as f:
            for s in строки:
                f.write(s if s.endswith('\n') else s + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.remove(п)
        self.o['слито_луна'] = self.o.get('слито_луна', 0) + len(строки)

    def отбор_и_снимок(self):
        """Отбор фоном; обход ждёт его конца или первого снимка списка этой волны (не дольше PILOT_OTBOR_ZHDAT_MIN)."""
        сп = os.path.join(DIR, НАБОР + '-spisok.json')
        t0 = time.time()
        if self.пуск('pilot_otbor.py', фоном=True) == 'занят':
            return
        while self.занят('pilot_otbor.py') and time.time() - t0 < ОТБОР_ЖДАТЬ_МИН * 60:
            if os.path.exists(сп) and os.path.getmtime(сп) > t0:
                return
            self.статус()
            time.sleep(30)

    def волна(self):
        self.o['волна'] += 1
        self.слить_луну()
        self.пуск('poisk_razbor.py')
        self.пуск('razbor_brauzer.py')
        self.отбор_и_снимок()
        if not os.path.exists(os.path.join(DIR, НАБОР + '-spisok.json')):
            return
        self.пуск('pilot_sayty_dobor.py', фоном=True)
        self.пуск('kc_kontakty.py')
        for ш in ('pilot_dop_proverka.py', 'pilot_pasport.py'):
            self.пуск(ш, фоном=True)
        for ш in ('kc_audit.py', 'kc_audit2.py', 'kc_sayt_proverka.py', 'kc_oproverzhenie.py', 'kc_glubokiy_vhod.py'):
            self.пуск(ш)
        for ш in ('kc_agent_glubokiy.py', 'kc_agent_glubokiy.py:хвост'):
            self.пуск(ш, фоном=True)

    def финал(self):
        self.o['волна'] = 'финал'
        фоновые = ('pilot_otbor.py', 'pilot_sayty_dobor.py', 'pilot_dop_proverka.py', 'pilot_pasport.py')
        self.ждать(фоновые)
        for ш in ('poisk_razbor.py', 'razbor_brauzer.py', 'pilot_otbor.py', 'pilot_sayty_dobor.py', 'kc_kontakty.py'):
            код = self.пуск(ш)
            if код not in (0, 'занят') and ш in ('poisk_razbor.py', 'pilot_otbor.py', 'kc_kontakty.py'):
                код = self.пуск(ш)  # один повтор, как в последовательном режиме
                if код != 0:
                    self.o['стоп'] = 'шаг %s упал — дальше без него нельзя' % ш
                    self.статус()
                    return False
        for ш in ('pilot_dop_proverka.py', 'pilot_pasport.py'):
            self.пуск(ш, фоном=True)
        for ш in ('kc_audit.py', 'kc_audit2.py', 'kc_sayt_proverka.py', 'kc_oproverzhenie.py', 'kc_glubokiy_vhod.py'):
            if self.пуск(ш) not in (0, 'занят'):
                self.пуск(ш)
        агенты = ('kc_agent_glubokiy.py', 'kc_agent_glubokiy.py:хвост')
        self.ждать(агенты)  # агенты прошлой волны доделывают своё; потом — по свежему входу
        for ш in агенты:
            self.пуск(ш, фоном=True)
        self.ждать(агенты)
        self.слить_луну()
        self.ждать(('pilot_dop_proverka.py', 'pilot_pasport.py'))
        for ш in ('pilot_dop_proverka.py', 'pilot_pasport.py'):  # догнать компании финального обхода (резюм)
            self.пуск(ш)
        self.пуск('kc_agent_pereproverka.py')
        return True

    def main(self):
        while True:
            финал = поиск_готов() and not разбор_жив_чужой()
            if финал:
                break
            t0 = time.time()
            self.волна()
            self.o['следующая_волна'] = time.strftime('%H:%M', time.localtime(t0 + ВОЛНА_МИН * 60))
            self.статус()
            while time.time() - t0 < ВОЛНА_МИН * 60 and not поиск_готов():
                time.sleep(60)
                self.статус()
        if self.финал():
            for ф in (НАБОР + x for x in ('-razbor.jsonl', '-spisok.json', '-reestr.json', '-zenka.json', '-kontakty.jsonl',
                                           '-audit.jsonl', '-audit2.jsonl', '-sayt-proverka.jsonl', '-oprov.jsonl',
                                           '-glubokiy.jsonl', '-glubokiy2.jsonl', '-serp.jsonl', '-dop.jsonl',
                                           '-sayty-dobor.jsonl', '-klass.jsonl', '-pasport.jsonl')):
                if os.path.exists(os.path.join(DIR, ф)):
                    shutil.copyfile(os.path.join(DIR, ф), os.path.join(ДРОП, ф))
            self.o['конец'] = time.strftime('%Y-%m-%d %H:%M')
        self.статус()


def разбор_жив_чужой():
    """Разбор, запущенный не волнами (ранний разбор _pusk_*_razbor.py: в его командной строке нет метки набора)."""
    return питон_жив('*server\\poisk_razbor.py')


if __name__ == '__main__':
    if ВОЛНЫ:
        Волны().main()
    else:
        main()
