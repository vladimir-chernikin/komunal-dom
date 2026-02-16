# АДАПТАЦИЯ: Голосовой нейро-консультант → MainAgent-2 УК "Аспект"

**Дата:** 2026-02-12
**Проект:** komunal-dom.ru
**Источники:**
- Борисов Д.А. (голосовой нейро-консультант)
- VM_MA.md (материалы лекций)
- MAINAGENT_PROMPT_V2_PROPOSAL.md (предложение MainAgent-2)

---

## 1. АРХИТЕКТУРА НЕЙРО-КОНСУЛЬТАНТА

### Схема работы

```
┌─────────────────────────────────────────────────────────┐
│              Голосовой нейро-консультант                │
└─────────────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
    ┌───▼────┐    ┌───▼────┐    ┌───▼────┐
    │  Телефон │    │  Клиент │    │ Тестер  │
    │  звонок  │    │   Web   │    │         │
    └───┬────┘    └───┬────┘    └───┬────┘
        │               │               │
        └───────────────┴───────────────┘
                      │
                ┌─────▼─────┐
                │  Телефония │
                └─────┬─────┘
                      │
            ┌─────────▼─────────┐
            │   WebSocket сервер │
            │    (asyncio)     │
            └─────────┬─────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
    ┌───▼────┐  ┌───▼────┐  ┌───▼────┐
    │  Vosk  │  │  RAG   │  │  GPT   │
    │  STT   │  │  FAISS │  │  LLM   │
    └───┬────┘  └───┬────┘  └───┬────┘
        │            │            │
        └────────────┴────────────┘
                      │
                ┌─────▼─────┐
                │  Yandex    │
                │  SpeechKit │
                │    TTS     │
                └─────┬─────┘
                      │
            ┌─────────▼─────────┐
            │  Память (SQLite) │
            │  CRM (Bitrix24)  │
            │  Google Sheets    │
            └───────────────────┘
```

---

## 2. ТЕХНИЧЕСКИЙ СТЕК

### Язык и среда
```python
Python 3
WebSocket сервер (websockets, asyncio)
Асинхронный I/O (aiofiles, httpx)
```

### Голосовые технологии
```python
STT (Speech-to-Text): Vosk (локальная модель)
TTS (Text-to-Speech): Yandex SpeechKit (streaming via WebSocket)
```

### AI и обработка знаний
```python
Векторный поиск: FAISS + OpenAI Embeddings (RAG)
LLM: OpenAI GPT (API)
```

### База знаний
```python
Форматы: .txt, .docx, .pdf (python-docx, PyPDF2)
Индексация: FAISS, хранение эмбеддингов в .bin/.npy
```

### Память и диалоги
```python
Хранение истории: SQLAlchemy (PostgreSQL/MySQL/SQLite)
```

### Интеграции
```python
CRM: Bitrix24 (webhook API)
Google Sheets (gspread, oauth2client) — live-промпты
```

---

## 3. КЛЮЧЕВЫЕ ПРИНЦИПЫ

### 3.1. RAG (Retrieval Augmented Generation)

**Принцип:** Поиск релевантных фрагментов в базе знаний

**Реализация:**
```python
# 1. Индексация базы знаний
documents = load_documents(".txt", ".docx", ".pdf")
embeddings = openai_embedding_model.encode(documents)
faiss_index = faiss.IndexFlatL2(embeddings.shape[1])
faiss_index.add(embeddings)

# 2. Поиск релевантных фрагментов
query_embedding = openai_embedding_model.encode(query)
distances, indices = faiss_index.search(query_embedding, k=5)
retrieved_docs = [documents[i] for i in indices[0]]

# 3. Формирование промпта с RAG
prompt = f"""
На основе следующих документов:
{chr(10).join(retrieved_docs)}

Ответь на вопрос: {query}
"""
```

**Применение к УК "Аспект":**
- База знаний: правила проживания, тарифы, нормы ЖКХ
- Поиск: по истории заявок, регламентам
- Ответ: с учетом найденной информации

### 3.2. Память и Summary

**Принцип:** Сохранение истории, summary и follow-up задач

**Реализация:**
```python
# Память диалога
dialog_memory = {
    "session_id": "abc123",
    "messages": [
        {"role": "user", "content": "У меня течет кран"},
        {"role": "assistant", "content": "Где именно находится кран?"}
    ],
    "summary": "Клиент сообщает о протечке крана. Уточнено: кухня.",
    "follow_up_tasks": ["Создать заявку на ремонт крана"]
}
```

**Применение к УК "Аспект":**
- txtPrb = накопленное описание проблемы
- История диалога = контекст
- Follow-up = создание заявки в CRM

### 3.3. Live-промпты через Google Sheets

**Принцип:** Динамическое изменение промптов "на лету"

**Реализация:**
```python
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Подключение к Google Sheets
scope = ['https://scenarios.googleapis.com/auth/spreadsheets']
creds = ServiceAccountCredentials.from_json_keyfile_name('key.json', scope)
client = gspread.authorize(creds)
sheet = client.open("Промпты").sheet1

# Чтение промпта
def get_prompt(prompt_name):
    row = sheet.find(prompt_name)
    return row.value
```

**Применение к УК "Аспект":**
- Таблица "Промпты MainAgent"
- Листы: Router, CriticalHandler, ServiceClassifier, GeneralInquiry
- Изменение в Google Sheets → мгновенное обновление AI

### 3.4. WebSocket (Streaming)

**Принцип:** Двусторонняя потоковая передача

**Реализация:**
```python
import asyncio
import websockets

async def handler(websocket, path):
    async for message in websocket:
        # STT: аудио → текст
        text = vosk_stt.process_audio(message)

        # RAG + LLM: текст → ответ
        response = llm_generate(text)

        # TTS: текст → аудио
        audio = yandex_tts.synthesize(response)

        # Отправка клиенту
        await websocket.send(audio)
```

**Применение к УК "Аспект":**
- Telegram бот (long polling)
- Web-чат (WebSocket)
- Голосовой интерфейс (будущее)

---

## 4. АДАПТАЦИЯ К UK "АСПЕКТ"

### 4.1. Замена технологий

| Борисов Д.А. | УК "Аспект" | Причина |
|--------------|-------------|---------|
| **Vosk STT** | Telegram/Web текст | Текущий интерфейс - текстовый |
| **OpenAI GPT** | YandexGPT | Контракт с Яндексом |
| **OpenAI Embeddings** | Yandex Embeddings | Контракт с Яндексом |
| **Bitrix24 CRM** | Собственная CRM | PostgreSQL база |
| **Google Sheets** | PostgreSQL (PromptTemplate) | Уже реализовано |
| **WebSocket** | Django HTTP | Web-архитектура |

### 4.2. Сохранение принципов

| Принцип | Адаптация для УК "Аспект" |
|---------|---------------------------|
| **RAG** | VectorSearchService (уже есть) |
| **Память** | ProblemAccumulationService (уже есть) |
| **Summary** | txtPrb (накопление описания) |
| **Follow-up** | Создание заявки в CRM |
| **Live-промпты** | PromptTemplate в БД (уже есть) |

### 4.3. Новые компоненты

**1. RAG-расширение для MainAgent-2**

```python
# main_agent/rag_service.py

class RAGService:
    """
    RAG (Retrieval Augmented Generation) для MainAgent-2
    """

    def __init__(self):
        self.faiss_index = self._load_faiss_index()
        self.documents = self._load_documents()

    def retrieve(self, query: str, top_k: int = 5) -> list[str]:
        """
        Поиск релевантных фрагментов в базе знаний

        Args:
            query: Запрос пользователя
            top_k: Количество фрагментов

        Returns:
            Список релевантных документов
        """
        query_embedding = yandex_embedding(query)
        distances, indices = self.faiss_index.search(query_embedding, k=top_k)
        return [self.documents[i] for i in indices[0]]

    def augment_prompt(self, prompt: str, query: str) -> str:
        """
        Аугментация промпта релевантными фрагментами

        Args:
            prompt: Базовый промпт
            query: Запрос пользователя

        Returns:
            Аугментированный промпт
        """
        relevant_docs = self.retrieve(query)
        context = "\n\n".join(relevant_docs)

        return f"""
{prompt}

## КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ
{context}
"""
```

**База знаний УК "Аспект":**
- Правила проживания (собаки, ремонт, шум)
- Тарифы и квитанции
- Нормативные документы (ЖКХ РФ)
- FAQ (частые вопросы)

**2. Память диалогов**

```python
# main_agent/dialog_memory.py

class DialogMemoryManager:
    """
    Управление памятью диалогов
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages = []

    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now()
        })

    def get_summary(self) -> str:
        """
        Генерация summary диалога

        Returns:
            Краткое содержание диалога
        """
        prompt = f"""
Сформируй краткое содержание диалога (1-2 предложения):

{chr(10).join([f'{m["role"]}: {m["content"]}' for m in self.messages])}
"""
        return yandexgpt_call(prompt, temperature=0.15)

    def get_context_window(self, last_n: int = 10) -> list[dict]:
        """
        Получение последних N сообщений

        Args:
            last_n: Количество сообщений

        Returns:
            Список последних сообщений
        """
        return self.messages[-last_n:]
```

**3. Follow-up задачи**

```python
# main_agent/follow_up.py

class FollowUpManager:
    """
    Управление follow-up задачами
    """

    def __init__(self):
        self.tasks = []

    def add_task(self, task: dict):
        """
        Добавление follow-up задачи

        Args:
            task: {
                "action": "create_ticket",
                "priority": "normal",
                "description": "Ремонт крана"
            }
        """
        self.tasks.append({
            "task": task,
            "status": "pending",
            "created_at": datetime.now()
        })

    def execute_tasks(self):
        """
        Выполнение_pending задач
        """
        for task in self.tasks:
            if task["status"] == "pending":
                self._execute(task)
                task["status"] = "completed"

    def _execute(self, task: dict):
        """
        Выполнение задачи

        Args:
            task: Задача
        """
        action = task["task"]["action"]

        if action == "create_ticket":
            self._create_ticket(task["task"])
        elif action == "escalate":
            self._escalate(task["task"])
        elif action == "send_to_operator":
            self._send_to_operator(task["task"])
```

---

## 5. АРХИТЕКТУРА MAINAGENT-2 С RAG

### Обновленная схема

```
┌─────────────────────────────────────────────────────────┐
│                   MainAgent-2                          │
│              (Главный диспетчер)                       │
│                                                         │
│  Функции:                                              │
│  - Маршрутизация запросов                              │
│  - Определение критических ситуаций                    │
│  - Оркестрация суб-агентов                             │
│  - Накопление контекста (txtPrb)                       │
│  - RAG (поиск в базе знаний) ← НОВОЕ                  │
│  - Память диалогов ← НОВОЕ                              │
│  - Follow-up задачи ← НОВОЕ                               │
└─────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
    ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
    │  Critical  │  │  Service  │  │  General  │
    │  Handler   │  │Classifier │  │  Inquiry  │
    │   Agent    │  │   Agent   │  │   Agent   │
    └───────────┘  └─────┬─────┘  └───────────┘
                          │
                ┌─────────┴─────────┐
                │  Shared Services  │
                │  - TagSearch      │
                │  - VectorSearch   │
                │  - FilterDetect   │
                │  - ProblemAccum   │
                │  - RAGService ← НОВОЕ                     │
                │  - DialogMemory ← НОВОЕ                    │
                │  - FollowUpManager ← НОВОЕ                 │
                └───────────────────┘
```

---

## 6. ПРОМПТ С RAG-АУГМЕНТАЦИЕЙ

### Пример аугментированного промпта

```markdown
# MainAgent-2: AI-Диспетчер УК "Аспект"

## РОЛЬ
Ты - умный AI-диспетчер управляющей компании "Аспект". Твоя задача - понимать проблемы жильцов, определять нужную услугу и создавать заявки.

## КРИТИЧЕСКИЕ ПРАВИЛА
1. **Один вопрос за раз** - запрещены двойные вопросы через "или", "и"
2. **Открытые вопросы** - только "Что/Как/Где/Когда/Почему", запрещены "да/нет"
3. **Не повторяйся** - не спрашивай то, что уже известно из диалога
4. **Краткость** - максимум 10 слов в вопросе
5. **Без эмодзи** - используй только текст

## ПРИОРИТЕТ БЕЗОПАСНОСТИ
ПРОВЕРЬ ПЕРВУЮ: Если есть угроза жизни/здоровью - немедленная эскалация!

---

## СПИСОК УСЛУГ УК "АСПЕКТ"
[Список услуг с хэштегами как в основном промпте]

---

## КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ (RAG)

### Релевантные документы:
{retrieved_documents}

### История диалога:
{dialog_history}

### Накопленное описание (txtPrb):
{txtPrb}

### Установленные фильтры:
- **Категория:** {category}
- **Локализация:** {location}
- **Тип:** {incident_type}

---

## АЛГОРИТМ РАБОТЫ
[Алгоритм как в основном промпте]

## ВЫХОДНОЙ ФОРМАТ
[Формат как в основном промпте]
```

---

## 7. ПЛАН ВНЕДРЕНИЯ RAG

### Этап 1. Подготовка базы знаний (1 неделя)
- [ ] Собрать документы (правила, тарифы, FAQ)
- [ ] Конвертировать в .txt/.pdf
- [ ] Создать эмбеддинги (Yandex Embeddings API)
- [ ] Построить FAISS индекс

### Этап 2. RAGService (1 неделя)
- [ ] Создать main_agent/rag_service.py
- [ ] Реализовать retrieve()
- [ ] Реализовать augment_prompt()
- [ ] Написать тесты

### Этап 3. Память диалогов (1 неделя)
- [ ] Создать main_agent/dialog_memory.py
- [ ] Хранение в PostgreSQL (таблица dialog_messages)
- [ ] Реализовать get_summary()
- [ ] Реализовать get_context_window()

### Этап 4. Follow-up (1 неделя)
- [ ] Создать main_agent/follow_up.py
- [ ] Интеграция с CRM (создание заявок)
- [ ] Автоматическое выполнение задач

### Этап 5. Интеграция (2 недели)
- [ ] Обновить промпты MainAgent-2
- [ ] Добавить RAG в критические ситуации
- [ ] Тестирование на реальных диалогах
- [ ] Мониторинг качества

---

## 8. ПРЕИМУЩЕСТВА RAG-ПОДХОДА

### 8.1. Для бизнеса

**1. Актуальность ответов**
- Ответы с учетом актуальных правил и тарифов
- Нет устаревшей информации

**2. Снижение нагрузки**
- Частые вопросы отвечаются автоматически
- Операторы занимаются сложными случаями

**3. Контроль качества**
- Логирование всех решений
- Анализ базы знаний для улучшения

### 8.2. Для разработки

**4. Быстрое обновление**
- Добавил документ в базу знаний → сразу работает
- Нет необходимости менять код

**5. Тестируемость**
- RAG тестируется отдельно
- Проверка качества поиска

**6. Масштабируемость**
- База знаний растет без ограничений
- FAISS работает быстро даже на миллионах документов

---

## 9. СРАВНЕНИЕ: С RAG vs БЕЗ RAG

| Характеристика | Без RAG | С RAG |
|---|---|---|
| **Источник знаний** | Только промпт | Промпт + база знаний |
| **Актуальность** | Пересборка при изменениях | Мгновенное обновление |
| **Детальность** | Общая информация | Точные цитаты из документов |
| **Объяснимость** | "LLM так сказал" | "Согласно документу X, параграф Y" |
| **Поддержка** | Программист | Менеджер (добавил документ) |

---

## 10. ЗАКЛЮЧЕНИЕ

### Ключевые выводы

**1. Принципы Борисова Д.А. применимы к УК "Аспект":**
- RAG (поиск знаний)
- Память диалогов (summary)
- Follow-up (задачи)
- Live-промпты (динамические изменения)

**2. Адаптация технологий:**
- YandexGPT вместо OpenAI (контракт)
- Yandex Embeddings вместо OpenAI
- PostgreSQL вместо Google Sheets
- VectorSearchService вместо FAISS (уже есть)

**3. Новые компоненты для MainAgent-2:**
- RAGService (аугментация промпта)
- DialogMemoryManager (память диалогов)
- FollowUpManager (автоматическое выполнение задач)

**4. Результат:**
- Более умные ответы (с учетом базы знаний)
- Контекстуальная память (история диалогов)
- Автоматизация (follow-up задачи)
- Гибкость (live-обновления)

---

**КОНЕЦ ДОКУМЕНТА**
