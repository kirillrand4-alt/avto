# Линза: Инженерия данных и актуальность

_Сгенерировано claude-fable-5 через провайдерский эндпоинт. Это идеи модели, а не проверенные факты._

---

## Модель данных для актуальной базы инженеров

### Ядро схемы: три основные сущности

**person** (физлицо как стабильная единица):
- person_id (UUID, первичный ключ)
- full_name_canonical (нормализованная форма: Иванов Иван Иванович)
- birth_year (год рождения, если известен — для разрешения омонимов)
- gender (М/Ж, опционально, для разрешения омонимов)
- phone_canonical (единый формат +79XXXXXXXXX)
- email_primary
- social_vk, social_ok, social_telegram (username или ID)
- created_at, updated_at

**organization** (юрлицо):
- org_id (UUID)
- inn (10 или 12 цифр, уникальный индекс)
- ogrn
- full_name_legal (полное наименование из ЕГРЮЛ)
- short_name (краткое)
- parent_org_id (для филиалов, ссылка на головную org_id)
- industry_okved (основной ОКВЭД)
- region_code (код ФИАС региона)
- is_active (действующая/ликвидирована)
- created_at, updated_at

**employment** (назначение человека на роль в организации):
- employment_id (UUID)
- person_id (FK)
- org_id (FK)
- title (должность текстом: «главный энергетик», «начальник ОГМ»)
- title_normalized (стандартизированная роль из справочника)
- date_start (дата начала работы, часто NULL)
- date_confirmed (когда последний раз подтвердили актуальность)
- date_end (дата увольнения, если известна, иначе NULL)
- is_current (булев флаг: работает ли СЕЙЧАС)
- confidence_score (0.0-1.0: насколько уверены)
- source_type (откуда: crm_call, egrul_head, parser_zakupki, manual, inference)
- source_url (прямая ссылка на источник)
- source_date (когда источник был получен)
- notes (текстовое поле для комментариев оператора)

### Провенанс и доверие

**data_provenance** (история изменений любого поля любой сущности):
- provenance_id (UUID)
- entity_type (person/organization/employment)
- entity_id
- field_name (например, "email_primary")
- old_value, new_value
- source_type, source_url, source_date
- changed_by (system/user_id)
- changed_at

Скоринг доверия (confidence_score) строится по правилам:
- ЕГРЮЛ (генеральный директор) = 0.95
- Закупки 44-ФЗ/223-ФЗ (контактное лицо) = 0.85
- CRM (подтверждённый звонок < 90 дней) = 0.90
- CRM (подтверждённый звонок 90-180 дней) = 0.75
- Сайт компании (раздел «Контакты») = 0.70
- Соцсети (указано в профиле) = 0.60
- Inference (вывод по косвенным признакам) = 0.40

При конфликте (два источника дают разные org_id для одного person_id в пересекающиеся даты) выигрывает запись с более свежей source_date и выше confidence_score.

### Entity resolution: разрешение омонимов и дублей

**Проблема**: Иванов И.И. из Газпромнефть и Иванов Игорь Иванович из Газпром нефть — один человек или два?

**Решение**: Многоступенчатый матчинг.

1. **Точный матч** (автослияние):
   - ИНН физлица (если есть) — абсолютная идентичность
   - Телефон + полное ФИО совпадают
   - Email + полное ФИО совпадают

2. **Вероятный дубль** (требует ручного подтверждения):
   - Фамилия + инициалы + org_id совпадают
   - Фамилия + имя совпадают, org_id в одной группе компаний (через parent_org_id)
   - Расстояние Левенштейна по ФИО < 3, телефон или email совпадают

3. **Смена фамилии**: специальная таблица **person_name_history**:
   - person_id, old_name, new_name, change_date, source_type

4. **Транслитерация**: таблица **person_aliases**:
   - person_id, alias_name (Ivanov Ivan, Іванов Іван), source

При загрузке новой записи система выдаёт список кандидатов на слияние с вероятностью, оператор принимает решение. Слияния логируются в отдельную таблицу **merge_log** с возможностью отката.

### Матчинг организаций

**ИНН — единственный надёжный ключ**. При загрузке названия «ООО "Газпром добыча Ямбург"» система:
1. Ищет ИНН через API nalog.ru или внутреннюю копию ЕГРЮЛ
2. Если нашла — обогащает запись (ОГРН, адрес, статус)
3. Если не нашла — создаёт запись со статусом "requires_inn_lookup"

**Филиалы и группы**: parent_org_id указывает на головную организацию. При матчинге «работает ли человек в Газпроме» учитываются все org_id с parent_org_id = Газпром или сам Газпром.

**Проблема переименований**: та же компания с тем же ИНН меняет название. Решение: таблица **org_name_history**, храним все прошлые наименования с датами.

### Механика протухания и переобхода

**Поле date_confirmed** — дата последней верификации факта «человек работает здесь». Приоритет переобхода:

1. **Красная зона** (переобойти немедленно):
   - is_current = TRUE, но date_confirmed старше 12 месяцев
   - confidence_score > 0.8, но source_date старше 18 месяцев

2. **Жёлтая зона** (переобойти в течение квартала):
   - is_current = TRUE, date_confirmed 6-12 месяцев
   - confidence_score 0.6-0.8, source_date 12-18 месяцев

3. **Зелёная зона** (рутинный переобход раз в год):
   - date_confirmed < 6 месяцев

**Детект смены места работы** (триггеры на переобход):
- В ЕГРЮЛ появился новый гендиректор в org_id, где наш person был директором — вероятно уволился
- Человек исчез из «Контактов» на сайте компании (мониторинг через парсер)
- В соцсетях (VK) обновилось поле «Место работы»
- В закупках 44-ФЗ тот же ИНН организации, но другое контактное лицо на той же должности

Эти события создают запись в таблице **staleness_signals**:
- signal_id, person_id, org_id, signal_type, detected_at, processed (булев)

Система выстраивает очередь переобхода по убыванию приоритета (вес = confidence_score × days_since_confirmed × count_staleness_signals).

### Дедупликация при загрузке

**Сценарий**: загружаем выгрузку из Битрикс-CRM, там 1500 контактов, половина уже есть в базе.

**Алгоритм**:
1. Парсим CSV, извлекаем ФИО, телефон, email, должность, название компании
2. Для каждой строки ищем org_id по названию компании (fuzzywuzzy > 90%) или по ИНН, если есть
3. Для каждой строки ищем person_id:
   - Точный матч по телефону или email → person_id найден
   - Нет матча → создаём новый person_id
4. Проверяем employment: есть ли связка (person_id, org_id, title_normalized) с is_current = TRUE?
   - Есть → обновляем date_confirmed = сегодня, повышаем confidence_score
   - Нет → создаём новую запись employment

**Результат**: ноль дублей, обогащение существующих записей, логирование всех изменений в data_provenance.

### Конкретная схема SQL (PostgreSQL)

```sql
CREATE TABLE person (
    person_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name_canonical VARCHAR(255) NOT NULL,
    birth_year SMALLINT,
    gender CHAR(1) CHECK (gender IN ('М', 'Ж')),
    phone_canonical VARCHAR(15),
    email_primary VARCHAR(255),
    social_vk VARCHAR(100),
    social_ok VARCHAR(100),
    social_telegram VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_person_name ON person USING gin(to_tsvector('russian', full_name_canonical));
CREATE UNIQUE INDEX idx_person_phone ON person(phone_canonical) WHERE phone_canonical IS NOT NULL;

CREATE TABLE organization (
    org_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inn VARCHAR(12) UNIQUE NOT NULL,
    ogrn VARCHAR(15),
    full_name_legal VARCHAR(500) NOT NULL,
    short_name VARCHAR(255),
    parent_org_id UUID REFERENCES organization(org_id),
    industry_okved VARCHAR(10),
    region_code VARCHAR(10),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_org_inn ON organization(inn);
CREATE INDEX idx_org_parent ON organization(parent_org_id) WHERE parent_org_id IS NOT NULL;

CREATE TABLE employment (
    employment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organization(org_id) ON DELETE CASCADE,
    title VARCHAR(255),
    title_normalized VARCHAR(100),
    date_start DATE,
    date_confirmed DATE NOT NULL,
    date_end DATE,
    is_current BOOLEAN DEFAULT TRUE,
    confidence_score NUMERIC(3,2) CHECK (confidence_score BETWEEN 0 AND 1),
    source_type VARCHAR(50),
    source_url TEXT,
    source_date DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_employment_person ON employment(person_id);
CREATE INDEX idx_employment_org ON employment(org_id);
CREATE INDEX idx_employment_current ON employment(is_current) WHERE is_current = TRUE;
CREATE INDEX idx_employment_stale ON employment(date_confirmed) WHERE is_current = TRUE;

CREATE TABLE data_provenance (
    provenance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('person', 'organization', 'employment')),
    entity_id UUID NOT NULL,
    field_name VARCHAR(50) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    source_type VARCHAR(50),
    source_url TEXT,
    source_date DATE,
    changed_by VARCHAR(100),
    changed_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_provenance_entity ON data_provenance(entity_type, entity_id);

CREATE TABLE staleness_signals (
    signal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID REFERENCES person(person_id),
    org_id UUID REFERENCES organization(org_id),
    signal_type VARCHAR(50),
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE
);
CREATE INDEX idx_signals_unprocessed ON staleness_signals(processed) WHERE processed = FALSE;
```

### Трудоёмкость реализации

- **Схема БД и базовый CRUD**: 2-3 дня
- **Entity resolution (матчинг и дедупликация)**: 5-7 дней
- **Интеграция с ЕГРЮЛ (ИНН→реквизиты)**: 2 дня (НЕ ПРОВЕРЕНО: есть ли готовая библиотека для nalog.ru API)
- **Механика протухания и приоритизации переобхода**: 3-4 дня
- **Детект смены места работы (триггеры и сигналы)**: 4-5 дней
- **Интерфейс для ручного подтверждения слияний**: 3-5 дней

Итого: 19-26 дней разработки одним человеком при наличии инструментов (PostgreSQL, Python, базовый веб-фреймворк).

## 3 самые сильные идеи этой линзы

**1. Разделение person, organization, employment с временными метками**

Это решает главную боль: «работает сейчас» — не свойство человека, а утверждение с датой истечения. Схема позволяет хранить историю смен мест работы, отслеживать протухание информации и корректно обрабатывать одного человека в нескольких компаниях (совместительство, смена работы). Без этого разделения база превращается в свалку противоречивых записей за 3-6 месяцев.

**2. Провенанс каждого поля с confidence_score**

Когда у вас email из CRM (подтверждён звонком 2 месяца назад, 0.9) и email с сайта компании (парсили 2 недели назад, 0.7) — система знает, какому верить. При конфликте выигрывает более свежий и надёжный источник. Это критично, когда данные собираются из 5-10 разнородных источников с разной степенью актуальности. Плюс полная аудируемость: можно показать, откуда взялся каждый факт (требование 152-ФЗ при возможной проверке).

**3. Автоматизированный детект протухания и приоритизация переобхода**

Без этого база мертвеет за полгода. Механизм staleness_signals + приоритетная очередь позволяет системе самой понимать, кого проверить первым: не всех подряд, а тех, где вероятность изменений максимальна (новый гендир в ЕГРЮЛ, исчез с сайта компании). При команде в одного человека это разница между «обзваниваем всех раз в год» и «обзваниваем только тех, кто вероятно сменил работу, раз в квартал».

## Чего эта линза не видит

**Первоначальное наполнение**. Схема прекрасно работает, когда данные уже есть, но как собрать первые 50 000 записей инженеров — вне зоны этой линзы. Нужна линза «источники данных» (ЕГРЮЛ, закупки, парсеры, покупные базы).

**Юридическая чистота обработки ПДн**. Схема не отвечает на вопрос, нужно ли согласие на обработку от каждого физлица, как его хранить, как обрабатывать запросы на удаление по ст. 14 ФЗ-152. Это требует отдельного блока (поле consent_date, таблица erasure_requests).

**UX для оператора**. Есть схема таблиц, но нет интерфейса: как оператор подтверждает слияние дублей, как просматривает очередь переобхода, как вручную корректирует записи. Нужна линза «пользовательский интерфейс».

**Масштабирование за пределы 100k записей**. При 500k+ person и 1M+ employment потребуются партиционирование (по date_confirmed), настройка индексов под конкретные запросы, возможно переход на более тяжёлую СУБД. Текущая схема рассчитана на «один человек + AI, база до 100k инженеров».

**Машинное обучение для inference**. Линза описывает, где хранить confidence_score, но не объясняет, как его считать автоматически (ML-модель на основе исторических подтверждений), как детектить смену работы по косвенным признакам (изменение тональности в соцсетях, новые связи). Это требует линзы «data science».
