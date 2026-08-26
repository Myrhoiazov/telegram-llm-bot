# Implementation Prompt: Telegram AI Bot с future-ready архитектурными границами

## Цель

Разработай простой Telegram AI Bot на Python 3.12+, который получает текстовые сообщения из Telegram, отправляет каждое сообщение в локальную LLM через Ollama и возвращает ответ пользователю.

Перед реализацией прочитай связанные документы:

- `README.md` - карта документации и порядок чтения;
- `docs/specifications/Spec.md` - техническая спецификация и source of truth;
- `AGENTS.md` - будущие Agent/Harness границы, без реализации сейчас;
- `CLAUDE.md` - будущий cloud/deployment path, без реализации сейчас.

Текущий поток должен быть минимальным и stateless:

```text
User Message -> Telegram Adapter -> Application/Core -> Responder Interface -> Inference Provider -> Ollama -> Bot Reply
```

Важно: сейчас не нужно строить полноценный Agent Harness, MCP, RAG, tool execution, memory или agent loop. Нужно реализовать первую простую рабочую версию, но сразу провести правильные архитектурные границы, чтобы позже можно было добавить эти подсистемы без переписывания ядра.

## Главный принцип

Telegram, application/core и inference должны быть разделены.

Telegram-слой не должен знать детали Ollama API.  
Core/application не должен импортировать Telegram-specific или Ollama-specific модули.  
Inference provider должен быть заменяемым.

Текущий компонент, который отвечает пользователю, можно назвать `Responder`, `AssistantResponder` или `LLMResponder`. Не называй его полноценным autonomous agent, потому что agent loop, tools, permissions и sandbox пока отсутствуют.

## Что нужно реализовать сейчас

Используй Python 3.12+.

Telegram Bot API использовать напрямую через HTTP:

- не использовать `aiogram`;
- не использовать `telebot`;
- не использовать `python-telegram-bot`;
- использовать `getUpdates` для long polling;
- использовать `sendMessage` для ответа.

Бот должен:

1. Получать updates из Telegram.
2. Извлекать `update_id`, `chat_id` и текст сообщения.
3. Игнорировать неподдерживаемые update/message types без падения.
4. Хранить offset только в памяти процесса.
5. Не обрабатывать один update повторно во время работы процесса.
6. Передавать текст сообщения в application/core.
7. Application/core должен вызвать responder/inference через минимальный контракт.
8. Отправлять ответ модели обратно в тот же Telegram chat.

## Stateless behavior

Бот должен работать без памяти:

```text
User Message -> LLM -> Bot Reply
```

Каждое сообщение является отдельным независимым запросом.

Не хранить и не передавать в модель:

- историю диалога;
- sessions;
- conversation memory;
- предыдущие user/assistant messages;
- данные пользователей в базе.

## Минимальный inference contract

Сделай простой интерфейс, например:

```python
class TextGenerator(Protocol):
    def generate(self, prompt: str) -> str:
        ...
```

или эквивалентный минимальный контракт:

```python
generate(prompt: str) -> str
```

Основной provider сейчас: Ollama HTTP API.

Модели:

- `qwen3:1.7b`;
- `tinyllama`.

Ollama должен рассматриваться как отдельный process/container, к которому бот обращается по HTTP. Архитектура должна позволять позже добавить vLLM provider без изменения Telegram adapter и application/core.

## Рекомендуемая структура проекта

Сделай структуру простой и понятной для человека, который изучает Python:

```text
app/
  main.py
  config.py
  telegram/
    __init__.py
    client.py
    updates.py
  application/
    __init__.py
    bot_service.py
    responder.py
  inference/
    __init__.py
    base.py
    ollama.py
tests/
  test_config.py
  test_telegram_updates.py
  test_inference_contract.py
Dockerfile
docker-compose.yml
.env.example
.gitignore
README.md
Agent.md
Cloud.md
```

Можно немного адаптировать имена, но сохрани смысл:

- `config.py` - чтение и валидация env-настроек;
- `telegram/client.py` - низкоуровневые HTTP-вызовы `getUpdates` и `sendMessage`;
- `telegram/updates.py` - парсинг Telegram updates в простую внутреннюю структуру;
- `application/bot_service.py` - основной use case: принять входящее сообщение, получить ответ, вернуть результат;
- `application/responder.py` - простой responder contract, который пока вызывает LLM;
- `inference/base.py` - общий inference contract;
- `inference/ollama.py` - Ollama provider;
- `main.py` - сборка зависимостей и запуск polling loop.

## Dependency rules

Соблюдай правила зависимостей:

```text
main -> telegram adapter + application + inference provider
telegram adapter -> application contract / DTO
application/core -> responder/inference interface
inference/ollama -> Ollama HTTP API
```

Запрещено:

- `application/core` импортирует `telegram.client`;
- `application/core` импортирует `inference.ollama`;
- Telegram adapter формирует Ollama request;
- Ollama provider знает про Telegram `chat_id` или `update_id`.

## Future extension points

Не реализуй эти подсистемы сейчас, но заложи место для их появления в архитектуре и документации:

```text
app/
  agent/        # future: Agent Runtime / Harness
  tools/        # future: Tool Registry and tool contracts
  mcp/          # future: MCP adapter/client layer
  rag/          # future: Knowledge/Retrieval service
  memory/       # future: state and long-term memory
  sandbox/      # future: isolated execution
  telemetry/    # future: traces, audit logs, metrics
```

Не создавай пустые сложные подсистемы ради архитектуры. Можно упомянуть эти директории в README/Spec как future modules. В коде текущей реализации достаточно маленьких interfaces там, где они реально уменьшают связность.

Разделяй роли:

- RAG = knowledge/retrieval, поиск релевантных знаний и контекста;
- MCP = standardized tool/context integration layer;
- Harness = control/orchestration/security вокруг LLM и tool calls;
- Tools = actions, например чтение файла, запуск команды, вызов API;
- Sandbox = execution isolation для опасных или внешних действий;
- Memory/State = сохранение опыта, состояния задач и истории выполнения;
- Telemetry/Trace = наблюдаемость, логи, токены, tool calls, ошибки.

## Request flow

Реализуй основной поток так:

```text
1. main.py загружает config.
2. main.py создает Telegram client.
3. main.py создает Ollama provider как TextGenerator.
4. main.py создает BotService/Responder.
5. Polling loop вызывает Telegram getUpdates(offset, timeout).
6. Telegram adapter парсит updates в внутренние message objects.
7. Для каждого text message application/core вызывает generate(prompt).
8. BotService возвращает reply text.
9. Telegram adapter отправляет reply через sendMessage.
10. Offset обновляется после обработки update.
```

## Configuration

Все настройки и секреты должны приходить из environment variables.

Добавь `.env.example`:

```text
TELEGRAM_BOT_TOKEN=replace_me
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen3:1.7b
POLL_TIMEOUT_SECONDS=30
REQUEST_TIMEOUT_SECONDS=60
LOG_LEVEL=INFO
```

Не коммить реальные токены.  
Не логировать секреты.  
Добавь `.gitignore` для `.env`, Python cache, virtualenv и временных файлов.

## Docker Compose

Сейчас нужны только два сервиса:

```text
telegram-bot
ollama
```

Не добавлять PostgreSQL, Redis, Qdrant, MCP server, agent-service или отдельный RAG container, пока они не нужны.

Требования:

- `telegram-bot` запускается non-root;
- no privileged mode;
- не монтировать `/var/run/docker.sock`;
- не монтировать `~/.ssh`;
- не монтировать host root или весь filesystem;
- secrets только через env;
- bot обращается к Ollama по `http://ollama:11434`;
- Ollama запускается отдельным process/container.

## Error handling

Обработай:

- Telegram API error;
- Telegram network timeout;
- malformed Telegram response;
- update без `message.text`;
- Ollama API error;
- Ollama timeout;
- invalid JSON от Ollama;
- пустой ответ модели;
- недоступная модель.

При inference error бот должен отправить короткое понятное сообщение пользователю, например:

```text
Сейчас не получилось получить ответ от локальной модели. Попробуйте еще раз чуть позже.
```

Логи должны помогать отладке, но не раскрывать токены и секреты.

## Tests

Добавь минимальные тесты:

- parsing Telegram updates;
- config loading/validation;
- inference contract через fake provider;
- BotService вызывает responder/inference и возвращает ожидаемый reply.

Не нужно поднимать реальный Telegram или Ollama в unit tests.

## Non-Goals

Не реализовывать сейчас:

- database;
- Redis;
- RAG implementation;
- vector database;
- MCP server/client implementation;
- tool execution;
- agent loop;
- autonomous agent runtime;
- memory;
- multi-agent;
- web UI;
- Kubernetes;
- separate agent service;
- PostgreSQL/Qdrant containers;
- Docker socket access;
- privileged execution.

## Future evolution / architectural path

Документируй целевую эволюцию без реализации сейчас:

```text
Current bot
  -> separate Agent Service behind the same application boundary
  -> Agent Runtime / Harness with controlled loop
  -> Tool Registry and tool contracts
  -> Permission/Policy Engine
  -> Sandbox executor for isolated actions
  -> MCP adapter/client layer for standardized tools and context
  -> RAG/Knowledge service for retrieval
  -> Memory/State for longer-running tasks
  -> Telemetry/Trace for observability, tokens, decisions, tool calls
  -> multi-agent only when there is a concrete need
```

Telegram в будущем должен иметь возможность обращаться к отдельному Agent Service через тот же application boundary, не переписывая Telegram adapter.

## Acceptance Criteria

- Bot receives Telegram text messages through direct `getUpdates`.
- Bot sends replies through direct `sendMessage`.
- No Telegram frameworks are used.
- Each message is processed statelessly.
- No conversation history, memory, DB or sessions are used.
- Application/core does not depend on Telegram or Ollama-specific modules.
- Telegram adapter does not know Ollama request/response format.
- Ollama provider implements a minimal `generate(prompt) -> str` contract.
- vLLM can be added later as another provider without rewriting Telegram handling.
- Docker Compose contains only `telegram-bot` and `ollama`.
- Bot container runs as non-root.
- No privileged mode, Docker socket mount, `~/.ssh` mount or broad host mount.
- Config is loaded from env variables.
- `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`, `README.md` are present.
- Errors and timeouts are handled and logged without leaking secrets.
- Minimal tests cover config, Telegram update parsing and inference/application contract.
- Future Harness/MCP/RAG path is documented but not implemented.

## Definition of Done

- The project runs locally with Docker Compose after `.env` is populated.
- End-to-end flow works: `User Message -> Ollama -> Telegram Reply`.
- Code is small, readable and suitable for learning Python.
- Architecture has clear boundaries for future Agent Harness, MCP, RAG, tools, permissions, sandbox, memory and telemetry.
- No unnecessary enterprise-style scaffolding is added.
