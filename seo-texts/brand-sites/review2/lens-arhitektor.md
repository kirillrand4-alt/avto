# arhitektor

Я вижу сквозную проблему: система писалась как набор скриптов для однократного запуска, а используется как конвейер. Разберу по пунктам.

## 1. Payload из Битрикса - воспроизводимость провалена

**Что сломается:**
- `nash_katalog_20260811.csv` захардкожен везде по имени. Новая выгрузка - надо руками переименовывать или менять пути в коде
- Коды свойств Битрикса (`PROPERTY_143`, `PROPERTY_589`) не документированы. При переезде базы или смене структуры каталога `inventory.py` молча вернёт пустые значения
- Нет маппинга "человеческое имя → технический код". Через полгода никто не вспомнит, что `PROPERTY_589` - это давление
- Формат выгрузки не зафиксирован. CSV меняет порядок колонок - парсер ломается без предупреждения

**Масштаб:** сломается на второй выгрузке, через ~2 недели при обновлении каталога.

**Снаружи:** генерация остановится на гейте "меньше трёх карточек", потому что inventory вернёт пустой список. Либо пропустит с кривыми числами, и QA не заметит - механический QA проверяет только наличие числа в payload, а не корректность самого payload.

**Решение:**
```python
# config/bitrix_mapping.py
BITRIX_SCHEMA_V1 = {
    'power_kw': 'PROPERTY_143',
    'pressure_bar': 'PROPERTY_589', 
    'flow_lmin': 'PROPERTY_XXX',
    'receiver_l': 'PROPERTY_YYY'
}

# inventory.py принимает schema_version
def load_catalog(csv_path, schema=BITRIX_SCHEMA_V1):
    # валидация при загрузке
    required = ['ID', schema['power_kw'], schema['pressure_bar']]
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
```

Выгрузки складывать в `data/catalog/YYYYMMDD_nash_katalog.csv`, последнюю линковать симлинком `data/catalog/latest.csv`.

## 2. Потеря связи источник → текст

**Где рвётся:**
- Payload обогащается в билдерах, которые "затирают обогащение" (из твоих же слов). Это значит промежуточные данные не сохраняются
- Генерация получает JSON с числами, но **не получает ссылку на карточку источника**. Если в тексте "3800 л/мин", невозможно проверить, из какой карточки это взято
- `qa_text.py` проверяет "число есть в payload", но не проверяет "это число про тот товар, про который пишется блок"

**Пример поломки:**
В payload категории "Винтовые 22 кВт" есть пять исполнений ВК-22 с разной производительностью. Модель написала "ВК-22 даёт 3800 л/мин" - формально число из payload, QA пропустил. Но это число только для исполнения 7 бар, а текст не уточняет. Читатель берёт 10-барное, получает 3200 л/мин, пишет претензию.

**Масштаб:** проявится при первой жалобе клиента. На каждые 200 страниц - 2-3 таких места (по аналогии с 223 из 759, не прошедших текущий QA).

**Решение:**
```python
# payload structure
{
    "facts": [
        {
            "value": 3800,
            "unit": "л/мин", 
            "context": "ВК-22 7 бар",
            "source_card_id": "12345",
            "source_url": "https://prokompressor.ru/catalog/item/12345/"
        }
    ]
}

# qa_text.py дополнить
def check_number_context(text, payload):
    for fact in payload['facts']:
        if str(fact['value']) in text:
            # проверить, что рядом упомянут context
            pattern = f"{fact['context']}.*{fact['value']}"
            if not re.search(pattern, text, re.DOTALL):
                yield f"Number {fact['value]} used without context '{fact['context']}'"
```

## 3. Устаревание - автоматика отсутствует

**Что протухнет первым:**
1. Цены (уже протухают за 9 дней, +3.6%)
2. Наличие товара (карточка снята, а страница на неё ссылается)
3. Характеристики при обновлении модельного ряда
4. Дата "обновлено 2026-07-15" - захардкожена, просрочена уже сейчас

**Как это заметить сейчас:** никак. Нет процесса, который бы сравнивал опубликованный текст с актуальным каталогом.

**Снаружи:** читатель видит в тексте "350 733 ₽", в карточке на той же странице "363 250 ₽". Доверие к контенту падает, это бьёт по конверсии сильнее, чем SEO.

**Решение:**
```python
# monitoring/staleness_check.py
def check_page_freshness(page_url, page_payload_snapshot):
    current_catalog = load_catalog('data/catalog/latest.csv')
    
    for fact in page_payload_snapshot['facts']:
        card = current_catalog.get(fact['source_card_id'])
        
        if not card:
            yield Alert('CARD_REMOVED', fact['source_url'])
        
        if card['price'] != fact['value'] and fact['unit'] == '₽':
            drift_pct = abs(card['price'] - fact['value']) / fact['value']
            if drift_pct > 0.05:  # порог 5%
                yield Alert('PRICE_DRIFT', drift_pct, fact['source_url'])

# Запускать раз в сутки, складывать в monitoring/staleness_report_YYYYMMDD.json
```

При публикации страницы сохранять `page_metadata.json`:
```json
{
  "url": "https://berg-kompressor.ru/catalog/vintovye-kompressory/",
  "generated_at": "2026-08-20T14:23:00Z",
  "catalog_snapshot": "20260811",
  "payload_hash": "a3f2b9...",
  "cards_used": ["12345", "12346", "12347"]
}
```

Тогда через 3 месяца можно прогнать весь опубликованный контент и получить список "что переписать в первую очередь".

## 4. Гейты - документ, а не код

**Статус сейчас:**
- "Меньше трёх карточек - не генерировать" - написано в `PLAN.md`, но нет проверки в `gen_tz.py`
- "Число в тексте, которого нет в payload" - есть в `qa_text.py`, но пропускает числа из обогащённого payload, который не сохранён
- "Пересечение скелета 40%" - реализовано, но порог захардкожен
- "Байлайн на брендовом сайте" - как это проверять? Grep по слову "эксперт"?

**Масштаб:** при смене исполнителя или через 6 месяцев половина гейтов перестанет работать, потому что они только в голове у текущего автора.

**Решение:**
```python
# gates/rules.py
class Gate:
    def check(self, context): raise NotImplementedError
    def severity(self): return 'ERROR'  # или 'WARNING'

class MinCardsGate(Gate):
    def __init__(self, min_cards=3):
        self.min_cards = min_cards
    
    def check(self, context):
        if len(context['cards']) < self.min_cards:
            return GateViolation(
                f"Only {len(context['cards'])} cards, need {self.min_cards}",
                action="Skip generation, add to card loading queue"
            )

class SkeletonOverlapGate(Gate):
    def __init__(self, threshold=0.4):
        self.threshold = threshold
    
    def check(self, context):
        for neighbor in context['domain_pages']:
            overlap = compute_skeleton_overlap(context['h2_list'], neighbor['h2_list'])
            if overlap > self.threshold:
                return GateViolation(
                    f"Overlap {overlap:.1%} with {neighbor['url']}",
                    action="Regenerate with different block set"
                )

# gates/config.yaml
production:
  - MinCardsGate: {min_cards: 3}
  - SkeletonOverlapGate: {threshold: 0.4}
  - ExternalLinkGate: {allowed_domains: []}
  - BrandMismatchGate: {}
  - AbsolutePriceGate: {allowed_sections: ['card']}

# gen_pipeline.py
def run_gates(context, config):
    violations = []
    for gate_class, params in config:
        gate = gate_class(**params)
        v = gate.check(context)
        if v and gate.severity() == 'ERROR':
            violations.append(v)
    
    if violations:
        log_violations(violations)
        return None  # остановить pipeline
    return context
```

Тогда `PLAN.md` становится документацией поверх кода, а не единственным источником правил.

## 5. Что построил бы иначе

**Главное:** разделить data pipeline и generation pipeline.

```
data/
  catalog/
    YYYYMMDD_export.csv
    latest.csv -> 20260820_export.csv
  inventory/
    berg-kompressor.ru_YYYYMMDD.json
    enger-air.ru_YYYYMMDD.json
  embeddings/
    spec_match_YYYYMMDD.json
  photos/
    photo_bank_YYYYMMDD.json

generation/
  payloads/
    berg-kompressor.ru_vintovye_YYYYMMDD.json  # входные данные
  outputs/
    berg-kompressor.ru_vintovye_YYYYMMDD_v1.html
    berg-kompressor.ru_vintovye_YYYYMMDD_v2.html  # после правки
  metadata/
    berg-kompressor.ru_vintovye.meta.json  # что из какой версии каталога

published/
  berg-kompressor.ru_vintovye_20260820.published.json
    {
      "url": "...",
      "generated_from": "generation/outputs/..._v2.html",
      "payload_snapshot": "generation/payloads/..._YYYYMMDD.json",
      "catalog_version": "20260811",
      "published_at": "2026-08-20T16:00:00Z"
    }
```

**Ключевые команды:**
```bash
# обновить инвентарь всех доменов из свежего каталога
./rebuild_inventory.sh data/catalog/20260825_export.csv

# сгенерировать одну страницу
./generate_page.sh berg-kompressor.ru vintovye --catalog-version 20260825

# проверить свежесть всех опубликованных страниц
./check_staleness.sh published/ --catalog data/catalog/latest.csv

# пересобрать все страницы одного домена
./rebuild_domain.sh berg-kompressor.ru --from-published

# воспроизвести конкретную версию
./regenerate.sh generation/outputs/berg-kompressor.ru_vintovye_20260820_v2.html
  # автоматически берёт нужную версию каталога из metadata
```

**Что это даёт:**
- При обновлении каталога видно, какие страницы затронуты
- Можно откатить конкретную страницу на старую версию payload без отката всего каталога
- Мониторинг свежести работает автоматически, не нужно помнить "а эту страницу я обновлял?"
- Новый исполнитель запускает `rebuild_domain.sh` и получает рабочий результат, а не "смотри в PLAN.md"

## Главный вывод

Система сейчас в состоянии "работает на текущем исполнителе с текущей выгрузкой". Чтобы она пережила:
- обновление каталога - нужен версионированный data pipeline
- смену исполнителя - нужны гейты в коде, а не в документе  
- рост объёма (209 категорий) - нужен мониторинг устаревания, иначе первые 50 страниц протухнут, пока пишутся последние 50

Приоритет: data pipeline (п.1-3), потом гейты (п.4), потом rebuild automation (п.5). Первое критично уже на второй выгрузке, остальное - на масштабе 100+ страниц.
