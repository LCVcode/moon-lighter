from __future__ import annotations

from pathlib import Path

SKILLS = {
    "moon-work-chunk": Path("skills/moon-work-chunk/SKILL.md"),
    "moon-plan-roadmap": Path("skills/moon-plan-roadmap/SKILL.md"),
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


def test_work_chunk_skill_does_not_treat_placeholder_brief_as_blocker() -> None:
    text = SKILLS["moon-work-chunk"].read_text(encoding="utf-8")

    assert "placeholder-only `.moon/brief.md`" in text
    assert "not a blocker" in text
    assert "repository context" in text


def test_work_chunk_skill_prioritizes_completion_over_scope_drift() -> None:
    text = SKILLS["moon-work-chunk"].read_text(encoding="utf-8")

    assert "Prioritize completing brief-defined goals" in text
    assert "do not treat autonomy as permission to invent large speculative features" in text
    assert "completes or stabilizes existing roadmap/brief scope before adding new scope" in text


def test_work_chunk_skill_uses_versioned_roadmap_planning() -> None:
    text = SKILLS["moon-work-chunk"].read_text(encoding="utf-8")

    assert "Read `.moon/roadmap.md` if present" in text
    assert "identify the next planned version/update" in text
    assert "switch to project-planning mode using `moon-plan-roadmap`" in text


def test_roadmap_skill_writes_versioned_path() -> None:
    text = SKILLS["moon-plan-roadmap"].read_text(encoding="utf-8")

    assert "`.moon/roadmap.md`" in text
    assert "current project state, the desired state, and the delta" in text
    assert "Use the `semantic-versioning` skill" in text
    assert "### Next: <version> - <name>" in text


def test_docs_show_explicit_skill_loading() -> None:
    text = Path("docs/skills.md").read_text(encoding="utf-8")

    assert "--skill /opt/moon/skills/moon-work-chunk" in text
    assert "--skill /opt/moon/skills/moon-plan-roadmap" in text
    assert "/skill:moon-work-chunk" in text
