# -*- coding: utf-8 -*-
r"""Ночной прогон контактов ЦА O2/N2 (09.11, владелец: «ночью не забудь выполнить задачу по полному поиску контактов
под азот и кислород»). Шаги 3–4 плана PLAN_CA_O2_N2.md на готовом конвейере pilot_konveyer (набор «ca»):
  1. ca_spisok.py — список (реестр ФНС + ca_cel, исключения, сайт из баз / поиск xmlriver) -> ca-spisok.json;
  2. pilot_konveyer.py с шага kc_kontakty (PILOT_S_SHAGA=3): обход сайтов (номера, почты, роли), доразметка, проверка
     доп. ОКВЭД, паспорт сайта, чей номер, чей сайт (Sol), опровергатели, агенты для компаний без подтверждённого сайта
     (Sol от 500 млн, Luna 120–500 млн), перепроверка; закупки ЕИС с порога 30 млн (план: «до порога категории»).
Модели — решение владельца 09.10 (Luna — классификация, Sol — проверка сайта и агенты), всё через провайдера.
Только сбор контактов: никаких рассылок (холд CLAUDE.md). Низкий приоритет, замок от второго экземпляра.
Статус: ca-konveyer.json (+ дроп), лог обёртки — ca\ca_konveyer_*.log. Запуск: python ca_konveyer.py (сам в фон).
"""
import io, json, os, subprocess, sys, time

DIR = r'C:\sender\server'
ПАПКА = os.path.join(DIR, 'ca')

if '--vnutri' not in sys.argv:
    os.makedirs(ПАПКА, exist_ok=True)
    лог = os.path.join(ПАПКА, 'ca_konveyer_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.abspath(__file__), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200 | 0x4000, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT,
                         close_fds=False)
    time.sleep(20)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-600:])
    sys.exit(0)

ЗАМОК = os.path.join(ПАПКА, 'ca_konveyer.lock')
try:
    _fd = os.open(ЗАМОК, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(_fd, str(os.getpid()).encode())
    os.close(_fd)
except FileExistsError:
    _pid = open(ЗАМОК).read().strip()
    if _pid and _pid in subprocess.run(['tasklist', '/FI', 'PID eq %s' % _pid], capture_output=True, text=True).stdout:
        print('уже запущен, pid', _pid)
        sys.exit(0)
    open(ЗАМОК, 'w').write(str(os.getpid()))

ENV = dict(os.environ, POISK_NABOR='ca', KC_NABOR='ca', KC_CEL='kc', PILOT_S_SHAGA='3',
           KC_ZAKUPKI_OT='30e6', KC_POTOKOV=os.environ.get('KC_POTOKOV', '24'), KC_LIMIT_MIN='25',
           KC_EC='1', KC_EC_XML_OT='5e8', KC_EC_BEZ_MODELI='1', KC_AGENT_XML_MIN='60',
           PILOT_MODEL='gpt-6-luna', PROVIDER_FALLBACK_CHEAP='gpt-5.6-luna')


def отметка(**k):
    k['обновлено'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(os.path.join(ПАПКА, 'ca-konveyer-obertka.json'), 'w', encoding='utf-8') as f:
        json.dump(k, f, ensure_ascii=False)
    print(json.dumps(k, ensure_ascii=False)[:400], flush=True)


def загрузка():
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        '(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average'],
                       capture_output=True, text=True, timeout=120)
    try:
        return float((r.stdout or '0').strip().replace(',', '.') or 0)
    except ValueError:
        return 0.0


def main():
    сп = os.path.join(DIR, 'ca-spisok.json')
    флаг = os.path.join(ПАПКА, 'ca-spisok-zanovo.flag')  # вторая волна: пересобрать список (лазер с сигналом, добор)
    if not os.path.exists(сп) or os.environ.get('CA_SPISOK_ZANOVO') == '1' or os.path.exists(флаг):
        if os.path.exists(флаг):
            os.remove(флаг)
        отметка(этап='список')
        with open(os.path.join(ПАПКА, 'ca_spisok_%s.log' % time.strftime('%d%m-%H%M')), 'ab') as f:
            r = subprocess.run([sys.executable, '-u', os.path.join(DIR, 'ca_spisok.py')], cwd=DIR, env=ENV,
                               stdout=f, stderr=subprocess.STDOUT)
        if r.returncode != 0 or not os.path.exists(сп):
            отметка(этап='ошибка', ошибка='ca_spisok.py код %s' % r.returncode)
            return
    компаний = len(json.load(io.open(сп, encoding='utf-8'))['компании'])
    # нагрузка сервера <= 90 % (CLAUDE.md tender): не стартуем обход, пока процессор занят чужими задачами
    for _ in range(60):
        з = загрузка()
        if з < 80:
            break
        отметка(этап='жду нагрузку', загрузка=з, компаний=компаний)
        time.sleep(120)
    отметка(этап='конвейер', компаний=компаний)
    with open(os.path.join(DIR, 'ca_konveyer_pilot_%s.log' % time.strftime('%d%m-%H%M')), 'ab') as f:
        r = subprocess.run([sys.executable, '-u', os.path.join(DIR, 'pilot_konveyer.py')], cwd=DIR, env=ENV,
                           stdout=f, stderr=subprocess.STDOUT)
    отметка(этап='готово', код=r.returncode, компаний=компаний)


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:  # noqa: BLE001
        отметка(этап='ошибка', ошибка=repr(e)[:500])
        raise
    finally:
        try:
            os.remove(ЗАМОК)
        except OSError:
            pass
