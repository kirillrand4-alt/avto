# -*- coding: utf-8 -*-
"""Проверка кубика ПЕРЕД отправкой владельцу: области видимости и баланс скобок.

Зачем: 14.08 кубик уехал владельцу с ошибкой компиляции — переменная объявлена
внутри блока `if (godnaya(glavnaya))`, а использована ниже, за его пределами.
ZennoPoster сказал только «произошла ошибка компиляции проекта», без номера
строки, и цену ошибки заплатил владелец: скачал, вставил, запустил, получил
красный крест.

Компилятора C# здесь нет, но именно этот класс ошибок ловится разбором скобок:
для каждого использования имени проверяем, есть ли ВИДИМОЕ объявление — в том
же блоке или в любом объемлющем, и раньше по тексту.

    python zenno/proverka_oblasti.py zenno/obhod_stranic.cs
"""
import re
import sys

ТИП = (r'(?:var|string\[\]|string|bool|int|uint|long|double|decimal|object'
       r'|List<[^>]+>|HashSet<[^>]+>|Dictionary<[^>]+>|Func<[^>]+>|Action(?:<[^>]+>)?'
       r'|Exception|Uri|StringBuilder)')
# слова языка и типы, которые не надо считать переменными
НЕ_ИМЯ = {'if', 'for', 'foreach', 'while', 'return', 'new', 'true', 'false', 'null',
          'else', 'break', 'continue', 'try', 'catch', 'finally', 'delegate', 'in',
          'var', 'string', 'int', 'bool', 'object', 'this', 'base', 'throw', 'using'}


def _маска(s):
    """Строки и комментарии — пробелами: в них лежат и «{», и имена переменных."""
    s = re.sub(r'"(?:\\.|[^"\\\n])*"', lambda m: '"' + 'x' * (len(m.group(0)) - 2) + '"', s)
    s = re.sub(r'@"(?:[^"]|"")*"', lambda m: ' ' * len(m.group(0)), s)
    s = re.sub(r'//[^\n]*', lambda m: ' ' * len(m.group(0)), s)
    return re.sub(r'/\*.*?\*/', lambda m: ' ' * len(m.group(0)), s, flags=re.S)


def проверить(put):
    исходник = open(put, encoding='utf-8').read()
    t = _маска(исходник)
    стек, блоки = [], []
    for i, ch in enumerate(t):
        if ch == '{':
            стек.append(i)
        elif ch == '}':
            if not стек:
                return ['лишняя закрывающая скобка, строка %d'
                        % (исходник[:i].count('\n') + 1)]
            блоки.append((стек.pop(), i))
    if стек:
        return ['незакрытая скобка, строка %d' % (исходник[:стек[0]].count('\n') + 1)]
    блоки.append((-1, len(t)))            # корень файла

    def тело_после(поз):
        """Область действия заголовка for/foreach/catch, начиная с позиции ключевого
        слова. Тело бывает и БЕЗ фигурных скобок — «foreach (string s in ...) f(s);»,
        и тогда переменная живёт до точки с запятой, а не до следующего блока в файле
        (на этом проверка сперва выдала семь ложных тревог)."""
        о = t.find('(', поз)
        if о < 0:
            return (-1, len(t))
        гл = 0
        закр = -1
        for i in range(о, len(t)):
            if t[i] == '(':
                гл += 1
            elif t[i] == ')':
                гл -= 1
                if гл == 0:
                    закр = i
                    break
        if закр < 0:
            return (-1, len(t))
        j = закр + 1
        while j < len(t) and t[j].isspace():
            j += 1
        if j < len(t) and t[j] == '{':
            for st, en in блоки:
                if st == j:
                    return (st, en)
            return (-1, len(t))
        # тело — один оператор: до ближайшей «;» на нулевой глубине скобок
        гл2 = 0
        for i in range(j, len(t)):
            if t[i] in '([{':
                гл2 += 1
            elif t[i] in ')]}':
                гл2 -= 1
            elif t[i] == ';' and гл2 <= 0:
                return (поз, i + 1)
        return (поз, len(t))

    def узкий(поз):
        л = None
        for st, en in блоки:
            if st < поз < en and (л is None or (en - st) < (л[1] - л[0])):
                л = (st, en)
        return л or (-1, len(t))

    объявления = {}    # имя -> [(позиция, блок)]
    свои = []          # куски текста самих объявлений: там имя стоит до тела

    def запомнить(имя, поз, блок, кусок=None):
        if имя in НЕ_ИМЯ:
            return
        объявления.setdefault(имя, []).append((поз, блок))
        if кусок:
            свои.append(кусок)

    # 1) обычные объявления: «var x =», «string x;», «int i = 0»
    for m in re.finditer(ТИП + r'\s+([A-Za-z_]\w*)\s*(?==|;|,)', t):
        запомнить(m.group(1), m.start(), узкий(m.start()), (m.start(), m.end()))
    # 2) заголовок for: переменная видна в теле цикла
    for m in re.finditer(r'\bfor\s*\(\s*' + ТИП + r'\s+([A-Za-z_]\w*)', t):
        запомнить(m.group(1), m.start(), тело_после(m.start()), (m.start(), m.end()))
    # 3) foreach
    for m in re.finditer(r'\bforeach\s*\(\s*(?:' + ТИП + r'|[A-Za-z_][\w.<>\[\]]*)'
                         r'\s+([A-Za-z_]\w*)\s+in\b', t):
        запомнить(m.group(1), m.start(), тело_после(m.start()), (m.start(), m.end()))
    # 4) catch (Exception e)
    for m in re.finditer(r'\bcatch\s*\(\s*[A-Za-z_][\w.]*\s+([A-Za-z_]\w*)\s*\)', t):
        запомнить(m.group(1), m.start(), тело_после(m.start()), (m.start(), m.end()))
    # 5) параметры delegate(...) — видны в теле делегата
    for m in re.finditer(r'\bdelegate\s*\(([^)]*)\)', t):
        тело = тело_после(m.start())
        for кусок in m.group(1).split(','):
            ч = кусок.strip().split()
            if len(ч) >= 2:
                запомнить(ч[-1], m.start(), тело, (m.start(), m.end()))

    беды = []
    заявлено = set()
    for m in re.finditer(r'\b([A-Za-z_]\w*)\b', t):
        имя = m.group(1)
        if имя in НЕ_ИМЯ or имя in заявлено or имя not in объявления:
            continue
        # обращение к члену (что-то.Имя) переменной не является
        нач = t.rfind('.', max(0, m.start() - 2), m.start())
        if нач == m.start() - 1:
            continue
        # само объявление (имя в скобках заголовка) использованием не считаем
        if any(a <= m.start() < b for a, b in свои):
            continue
        видно = any(поз <= m.start() and бл[0] < m.start() < бл[1]
                    for поз, бл in объявления[имя])
        if not видно:
            беды.append('«%s» использована в строке %d, но ни одно её объявление '
                        'сюда не достаёт' % (имя, исходник[:m.start()].count('\n') + 1))
            заявлено.add(имя)
    return беды


if __name__ == '__main__':
    файл = sys.argv[1] if len(sys.argv) > 1 else 'zenno/obhod_stranic.cs'
    б = проверить(файл)
    print('\n'.join(б) if б else 'область видимости и скобки — без нареканий')
    sys.exit(1 if б else 0)
