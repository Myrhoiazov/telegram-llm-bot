from app.agent.system_prompt import build_system_prompt


def test_system_prompt_requires_tool_use_for_email_requests():
    prompt = build_system_prompt()
    normalized = prompt.casefold()

    assert "skills/email/SKILL.md" in prompt
    assert "электронн" in prompt
    assert "execute_command" in prompt
    assert "не отвечай" in normalized
    assert "нет доступа к электронной почте" in normalized


def test_system_prompt_preserves_model_decision_making():
    prompt = build_system_prompt()
    normalized = prompt.casefold()

    assert "самостоятельно решай" in normalized
    assert "пользовательский запрос сначала получает модель" in normalized


def test_system_prompt_allows_user_to_request_another_language():
    prompt = build_system_prompt()
    normalized = prompt.casefold()

    assert "если пользователь явно не попросил другой язык" in normalized
