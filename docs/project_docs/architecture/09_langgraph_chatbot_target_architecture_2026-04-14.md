# Архитектура: LangGraph intake-оркестратор

Дата актуализации: 2026-04-29

## Базовые правила

- Intake не выбирает компанию эвристически.
- Компания определяется только через `service_object + дата -> company_object_service_period`.
- FIAS-поиск идет до уровня дома.
- Квартира хранится в контексте и используется для локального выбора квартирного `service_object`, но не блокирует прием заявки, если дом уже обслуживается.
- `request_intake` не создается.

## Целевой graph pipeline

1. `ingress_normalize`
2. `security_guard`
3. `txtprb_accumulator`
4. `address_extract`
5. `address_validate`
6. `service_period_resolve`
7. `classification_extract`
8. `service_resolve`
9. `question_generate`
10. `confirmation_gate`
11. `intake_json_build`
12. `request_create`

## Адресный контур внутри intake

### Шаг `address_extract`

- выделяет из текста: населенный пункт, улицу, дом, квартиру;
- нормализует строку адреса;
- не принимает неполный адрес как валидный.

### Шаг `address_validate`

- основной поиск: полный адрес;
- fallback: `street_fias_guid + house_number`;
- если `street_fias_guid` не найден, дом не подтверждается;
- если дом подтвержден, идет поиск локального `service_object`.

### Квартира

- не участвует в FIAS lookup;
- после нахождения дома бот пытается найти локальный объект помещения;
- если найден — в заявку идет квартирный объект;
- если не найден — в заявку идет домовой объект.

## Создание заявки

`request_create` создает:

- `request_mgmt.work_order`
- `request_mgmt.work_order_status_history`
- SLA-записи текущего контура
- `request_mgmt.work_order_event_log`

Diagnostic intake payload хранится в event log, а не в отдельном intake-документе.

## Что считать устаревшим

- house-level идентичность внутри `service_object` через `fias_house_object_id`;
- любые схемы с `request_intake`;
- любые описания выбора компании “по эвристике”.
