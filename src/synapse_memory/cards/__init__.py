"""Project / Company Card — vault에 저장되는 first-class entity.

이력서 작성 워크플로의 진실원본:
    - Project Card: 내가 한 프로젝트 (역할, 기간, 영향, 기술 스택)
    - Company Card: 지원/관심 회사 (포지션, JD 키워드, 메모)

저장 위치: vault ``20_Reference/Projects/<id>.md``, ``20_Reference/Companies/<id>.md``

저자: Synapse Memory Maintainers
"""

from synapse_memory.cards.company import (
    DEFAULT_COMPANIES_SUBPATH,
    CompanyCard,
    JobPosition,
    list_company_cards,
    load_company_card,
    parse_company_card,
    save_company_card,
    serialize_company_card,
)
from synapse_memory.cards.project import (
    DEFAULT_PROJECTS_SUBPATH,
    ProjectCard,
    ProjectMetric,
    ProjectSource,
    list_project_cards,
    load_project_card,
    parse_project_card,
    save_project_card,
    serialize_project_card,
)

__all__ = [
    "CompanyCard",
    "DEFAULT_COMPANIES_SUBPATH",
    "DEFAULT_PROJECTS_SUBPATH",
    "JobPosition",
    "ProjectCard",
    "ProjectMetric",
    "ProjectSource",
    "list_company_cards",
    "list_project_cards",
    "load_company_card",
    "load_project_card",
    "parse_company_card",
    "parse_project_card",
    "save_company_card",
    "save_project_card",
    "serialize_company_card",
    "serialize_project_card",
]
