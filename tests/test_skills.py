from __future__ import annotations

from pathlib import Path

SKILLS = {
    "moon-work-chunk": Path("skills/moon-work-chunk/SKILL.md"),
    "moon-wrap-up": Path("skills/moon-wrap-up/SKILL.md"),
    "moon-update-brief": Path("skills/moon-update-brief/SKILL.md"),
}


def test_moon_skills_exist_with_expected_frontmatter() -> None:
    for name, path in SKILLS.items():
        text = path.read_text(encoding="utf-8")
        assert f"name: {name}" in text
        assert "description:" in text


def test_skills_use_implemented_agent_result_schema() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in SKILLS.values())

    assert "requested_state" not in combined
    assert '"disposition"' in combined
    assert '"summary"' in combined


def test_docs_show_explicit_skill_loading() -> None:
    text = Path("docs/skills.md").read_text(encoding="utf-8")

    assert "--skill /opt/moon/skills/moon-work-chunk" in text
    assert "/skill:moon-work-chunk" in text
