# Задача для Claude: оформить коммиты

Нужно сделать серию аккуратных git-коммитов по уже внесенным изменениям. Не склеивай всё в один коммит.

Правила:
- сообщения коммитов только на русском;
- перед каждым коммитом проверь `git diff --cached` и `git status`;
- не включай в коммит лишние артефакты из `tmp/clean_14_04_2026`, если они не относятся к конкретному шагу;
- если видишь чужие несвязанные изменения, не трогай их;
- сначала коммить код и миграции, потом документацию, потом уборку проекта.

Рекомендуемая разбивка:

1. Коммит 1
Сообщение:
`Добавить house-level FIAS ID для объектов обслуживания и привязку компании по периоду`

Что должно войти:
- `portal/models.py`
- `portal/migrations/0022_add_service_object_house_fias_and_indexes.py`
- `kladr/fias_service.py`
- `work_orders/migrations/0016_seed_company_object_service_periods.py`

2. Коммит 2
Сообщение:
`Разделить chat intake на модули и перевести создание заявок на company_object_service_period`

Что должно войти:
- `work_orders/intake_service.py`
- `work_orders/chat_intake/__init__.py`
- `work_orders/chat_intake/company_resolver.py`
- `work_orders/chat_intake/payload_builder.py`
- `message_handler_service.py`
- `message_handler_intake_helpers.py`

3. Коммит 3
Сообщение:
`Обновить архитектурное описание intake и целевую схему LangGraph`

Что должно войти:
- `docs/project_docs/architecture/09_langgraph_chatbot_target_architecture_2026-04-14.md`
- связанные обновления архитектурной документации, если они есть

4. Коммит 4
Сообщение:
`Перенести архивы и разрозненную документацию в единые каталоги`

Что должно войти:
- перемещения в `tmp/clean_14_04_2026`
- перенос документации в `docs/project_docs`

После коммитов:
- покажи список созданных коммитов через `git log --oneline -n 4`;
- отдельно перечисли, какие файлы остались незакоммиченными и почему.
