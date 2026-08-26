# Визуальные схемы ManBot

Этот файл показывает процесс работы ManBot визуально: от самой простой схемы до более сложной архитектуры с параллельным выполнением.

Mermaid-диаграммы можно смотреть прямо в GitHub, VS Code с Mermaid Preview или любом Markdown-просмотрщике с поддержкой Mermaid.

## 1. Самая простая схема

Это минимальное понимание проекта:

```mermaid
flowchart LR
    U[Пользователь] --> T[Telegram Adapter]
    T --> C[Core Orchestrator]
    C --> P[Planner Agent]
    P --> E[Executor Agent]
    E --> C
    C --> T
    T --> U
```

Смысл:

```text
Пользователь пишет сообщение.
Telegram Adapter принимает его.
Core Orchestrator управляет задачей.
Planner строит план.
Executor выполняет план.
Ответ возвращается пользователю.
```

## 2. Схема с внутренними сервисами

Это уже ближе к реальному устройству проекта:

```mermaid
flowchart TD
    U[Пользователь в Telegram]
    TA[Telegram Adapter]
    C[Core Orchestrator]
    P[Planner Agent]
    TM[Task Memory SQLite]
    E[Executor Agent]
    MR[Model Router]
    L[Lemonade Adapter]
    TH[Tool Host]
    RAG[RAG Service]
    CRON[Cron Manager]
    FP[File Processor]
    LOG[Logger Service]
    K[Critic Agent]
    OUT[Ответ пользователю]

    U --> TA
    TA -->|task.create| C
    C -->|plan.create| P
    P -->|DAG plan| C
    C -->|task.create| TM
    C -->|plan.execute| E

    E --> MR
    MR --> L
    E --> TH
    E --> RAG
    E --> CRON
    E --> K

    TA -->|file.ingest| C
    C --> FP
    FP --> C

    C --> LOG
    E --> LOG
    TH --> LOG
    RAG --> LOG
    CRON --> LOG

    E -->|result| C
    C -->|telegram.send| TA
    TA --> OUT
```

Ключевая идея:

```text
Core Orchestrator не делает всю работу сам.
Он управляет процессами и отправляет сообщения нужным сервисам.
```

## 3. Сообщения внутри системы

Все процессы общаются через Envelope:

```mermaid
sequenceDiagram
    participant User as Пользователь
    participant Telegram as Telegram Adapter
    participant Core as Core Orchestrator
    participant Planner as Planner Agent
    participant Memory as Task Memory
    participant Executor as Executor Agent
    participant Model as Model Router

    User->>Telegram: Текст сообщения
    Telegram->>Core: task.create
    Core->>Planner: plan.create
    Planner-->>Core: response: DAG plan
    Core->>Memory: task.create
    Memory-->>Core: response: task saved
    Core->>Executor: plan.execute
    Executor->>Model: node.execute
    Model-->>Executor: response: generated text
    Executor-->>Core: response: final result
    Core->>Telegram: telegram.send
    Telegram-->>User: Ответ
```

Каждое внутреннее сообщение имеет форму:

```ts
{
  id: string,
  from: string,
  to: string,
  type: string,
  payload: unknown,
  timestamp: number,
  version: "1.0"
}
```

## 4. Как Planner превращает цель в DAG

Пользовательская цель:

```text
Найди информацию, сравни варианты и дай вывод.
```

Planner может превратить ее в такой граф:

```mermaid
flowchart TD
    G[Цель пользователя]
    A[Узел 1: поиск информации]
    B[Узел 2: поиск альтернатив]
    C[Узел 3: анализ плюсов]
    D[Узел 4: анализ минусов]
    E[Узел 5: итоговый вывод]

    G --> A
    G --> B
    A --> C
    B --> C
    A --> D
    B --> D
    C --> E
    D --> E
```

DAG означает:

```text
Directed Acyclic Graph
Направленный граф без циклов.
```

То есть шаги идут вперед и не зацикливаются.

## 5. Параллельное выполнение

Некоторые задачи не зависят друг от друга. Executor может выполнять их параллельно.

Пример:

```mermaid
flowchart TD
    START[Начало задачи]

    R1[Research A]
    R2[Research B]
    R3[Research C]

    S1[Суммаризация A]
    S2[Суммаризация B]
    S3[Суммаризация C]

    M[Объединение результатов]
    F[Финальный ответ]

    START --> R1
    START --> R2
    START --> R3

    R1 --> S1
    R2 --> S2
    R3 --> S3

    S1 --> M
    S2 --> M
    S3 --> M

    M --> F
```

Что здесь происходит:

```text
Research A, Research B и Research C можно запустить одновременно.
После них каждая ветка суммаризируется.
Потом результаты объединяются.
Финальный ответ строится только после объединения.
```

В Executor это работает через:

```text
getDependencyMap()
getReadyNodes()
completedIds
nodeOutputs
```

Executor постоянно спрашивает:

```text
Какие узлы уже можно запускать?
Все ли зависимости выполнены?
Какие результаты надо передать дальше?
```

## 6. От простого к сложному: три уровня проекта

### Уровень 1: простой бот

```mermaid
flowchart LR
    U[User] --> B[Bot]
    B --> LLM[LLM]
    LLM --> B
    B --> U
```

Плюсы:

- быстро сделать;
- мало кода;
- легко понять.

Минусы:

- нет памяти задач;
- нет нормального планирования;
- сложно добавлять инструменты;
- сложно отлаживать;
- все смешано в одном месте.

### Уровень 2: бот с сервисами

```mermaid
flowchart TD
    U[User] --> A[Adapter]
    A --> C[Controller]
    C --> M[Model Service]
    C --> MEM[Memory Service]
    C --> TOOLS[Tools Service]
    M --> C
    MEM --> C
    TOOLS --> C
    C --> A
    A --> U
```

Плюсы:

- код разделен по ролям;
- проще тестировать;
- можно добавлять память и инструменты.

Минусы:

- Controller все еще сам решает порядок работы;
- нет полноценного DAG;
- сложные задачи выполнять труднее.

### Уровень 3: ManBot-style платформа

```mermaid
flowchart TD
    U[User] --> A[Adapter]
    A --> O[Orchestrator]
    O --> P[Planner]
    P --> O
    O --> M[Task Memory]
    O --> E[Executor]

    E --> N1[Node 1]
    E --> N2[Node 2]
    E --> N3[Node 3]

    N1 --> S1[Service / Tool]
    N2 --> S2[Service / RAG]
    N3 --> S3[Service / LLM]

    S1 --> E
    S2 --> E
    S3 --> E

    E --> K[Critic]
    K --> E

    E --> O
    O --> A
    A --> U
```

Плюсы:

- сложные задачи разбиваются на план;
- можно выполнять независимые шаги параллельно;
- сервисы изолированы;
- проще расширять систему;
- можно добавлять новые агенты, инструменты и память.

Минусы:

- архитектура сложнее;
- нужно понимать протокол сообщений;
- сложнее отладка без логов и диаграмм.

## 7. Разные результаты выполнения

Одна и та же система может давать разные пути выполнения в зависимости от задачи.

### Простая задача

Пример:

```text
Скажи кратко, что такое RAG.
```

Процесс:

```mermaid
flowchart LR
    U[User] --> TA[Telegram Adapter]
    TA --> C[Core]
    C --> P[Planner]
    P --> C
    C --> E[Executor]
    E --> MR[Model Router]
    MR --> E
    E --> C
    C --> TA
    TA --> U
```

Здесь почти не нужны инструменты. Достаточно LLM-ответа.

### Средняя задача

Пример:

```text
Найди информацию на сайте и перескажи.
```

Процесс:

```mermaid
flowchart TD
    U[User] --> TA[Telegram Adapter]
    TA --> C[Core]
    C --> P[Planner]
    P --> C
    C --> E[Executor]
    E --> TH[Tool Host: http_get]
    TH --> E
    E --> MR[Model Router: summarize]
    MR --> E
    E --> C
    C --> TA
    TA --> U
```

Здесь уже нужен инструмент `http_get`, потом модель суммаризирует результат.

### Сложная задача

Пример:

```text
Исследуй тему, сравни источники, сделай вывод и сохрани важное в память.
```

Процесс:

```mermaid
flowchart TD
    U[User] --> TA[Telegram Adapter]
    TA --> C[Core]
    C --> P[Planner]
    P --> C
    C --> TM[Task Memory]
    C --> E[Executor]

    E --> R1[Search source 1]
    E --> R2[Search source 2]
    E --> R3[Search source 3]

    R1 --> TH[Tool Host]
    R2 --> TH
    R3 --> TH

    TH --> A1[Analyze source 1]
    TH --> A2[Analyze source 2]
    TH --> A3[Analyze source 3]

    A1 --> MERGE[Merge findings]
    A2 --> MERGE
    A3 --> MERGE

    MERGE --> RAG[RAG Service: save memory]
    MERGE --> K[Critic Agent]
    K --> FINAL[Final Answer]

    FINAL --> C
    C --> TA
    TA --> U
```

Здесь видны:

- параллельный поиск;
- анализ нескольких источников;
- объединение результатов;
- запись в память;
- проверка через Critic;
- финальный ответ.

## 8. Карта зависимостей процессов

```mermaid
flowchart TD
    O[Core Orchestrator]

    O --> TA[Telegram Adapter]
    O --> P[Planner Agent]
    O --> E[Executor Agent]
    O --> TM[Task Memory]
    O --> LOG[Logger]
    O --> MR[Model Router / Generator]
    O --> RAG[RAG Service]
    O --> TH[Tool Host]
    O --> CRON[Cron Manager]
    O --> FP[File Processor]
    O --> DASH[Dashboard]

    P --> L[Lemonade Adapter]
    E --> MR
    E --> TH
    E --> RAG
    E --> CRON
    MR --> L
    RAG --> L
    FP --> L
```

Core запускает и связывает процессы. Многие процессы зависят от Lemonade Adapter, потому что им нужна LLM, embeddings или vision-модель.

## 9. Главная визуальная формула

```mermaid
flowchart LR
    A[Adapter] --> O[Orchestrator]
    O --> P[Planner]
    P --> G[DAG Plan]
    G --> E[Executor]
    E --> S[Services]
    S --> M[Memory]
    E --> K[Critic]
    K --> R[Result]
    R --> A
```

Запомни так:

```text
Adapter принимает внешний сигнал.
Orchestrator управляет системой.
Planner строит план.
Executor выполняет план.
Services делают конкретные действия.
Memory сохраняет состояние.
Critic проверяет качество.
Adapter возвращает ответ.
```

## 10. Как использовать эти схемы для своих проектов

Когда строишь свой проект, сначала нарисуй такую карту:

```text
1. Кто пользователь?
2. Где он пишет?
3. Кто принимает сообщение?
4. Кто управляет задачей?
5. Кто планирует?
6. Кто выполняет?
7. Какие сервисы нужны?
8. Где хранится память?
9. Как возвращается ответ?
```

Если ты можешь нарисовать этот путь, тебе намного проще писать код.

