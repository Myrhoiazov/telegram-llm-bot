from pathlib import Path


def test_email_skill_is_adapted_to_local_imap_infrastructure():
    skill = Path("skills/email/SKILL.md").read_text(encoding="utf-8")

    assert "execute_command" in skill
    assert "skills/email/scripts/count_unread.py" in skill
    assert "skills/email/scripts/list_unread_headers.py" in skill
    assert "skills/email/scripts/triage_unread.py" in skill
    assert "EMAIL_IMAP_HOST" in skill
    assert "EMAIL_APP_PASSWORD" in skill
    assert "gog" not in skill
    assert "gog gmail" not in skill


def test_email_skill_explains_available_and_unavailable_actions():
    skill = Path("skills/email/SKILL.md").read_text(encoding="utf-8").casefold()

    assert "непрочитан" in skill
    assert "заголов" in skill
    assert "черновик" in skill
    assert "недоступ" in skill
