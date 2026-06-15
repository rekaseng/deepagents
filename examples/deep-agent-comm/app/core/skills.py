"""Skill loader — reads the SAME markdown files as the TS side (src/skills/*.md).
Frontmatter: name, description, triggers (comma list), intent, subagent."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..config import SKILLS_DIR

_FM_RE = re.compile(r"^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$")


@dataclass
class Skill:
    name: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    prompt: str = ""
    intent: str | None = None
    subagent: bool = False


def _parse_skill_file(raw: str, fallback_name: str) -> Skill | None:
    m = _FM_RE.match(raw)
    if not m:
        return None
    fm, body = m.group(1), m.group(2)
    meta: dict[str, str] = {}
    for line in fm.split("\n"):
        idx = line.find(":")
        if idx == -1:
            continue
        key = line[:idx].strip()
        val = line[idx + 1:].strip()
        if key:
            meta[key] = val
    return Skill(
        name=meta.get("name") or fallback_name,
        description=meta.get("description", ""),
        triggers=[t.strip().lower() for t in meta.get("triggers", "").split(",") if t.strip()],
        prompt=body.strip(),
        intent=meta.get("intent") or None,
        subagent=meta.get("subagent") == "true",
    )


def load_skills(skills_dir: Path = SKILLS_DIR) -> list[Skill]:
    skills: list[Skill] = []
    if not skills_dir.is_dir():
        return skills
    for f in sorted(skills_dir.glob("*.md")):
        skill = _parse_skill_file(f.read_text(encoding="utf-8"), f.stem)
        if skill:
            skills.append(skill)
    return skills


def match_skills(goal: str, skills: list[Skill]) -> list[Skill]:
    g = goal.lower()
    return [s for s in skills if any(t in g for t in s.triggers)]
