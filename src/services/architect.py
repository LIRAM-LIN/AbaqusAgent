import os
import re
from typing import Dict, List, Tuple
from dataclasses import dataclass
from pydantic import BaseModel, Field
from utils import retrieve_faiss, parse_directory_structure
from difflib import SequenceMatcher # for priority searching

class CaseSummaryModel(BaseModel):
    case_name: str = Field(description="name of the case")
    case_domain: str = Field(description="domain of the case")
    case_category: str = Field(description="category of the case")
    case_material: str = Field(description="material of the case")


class SubtaskModel(BaseModel):
    file_name: str
    folder_name: str


class AbaqusAgentPlanModel(BaseModel):
    subtasks: List[SubtaskModel]


def parse_requirement_to_case_info(user_requirement: str, case_stats: Dict, llm) -> Dict:
    """
    Purpose: Convert a free‑text user requirement into a structured AbaqusAgent case description.
        Builds a system prompt that restricts valid domain/category/material to values in case_stats.
        Calls the LLM with a Pydantic schema (CaseSummaryModel).
        Returns a normalized dict with keys:
        case_name (spaces → underscores)
        case_domain
        case_category
        case_material
    """

    parse_system_prompt = (
        "You are an Abaqus case naming and classification assistant. "
        "Read the user requirement carefully, do not summarize it for case name, "
        "and convert it into a structured case description. "
        "The case name must follow Abaqus benchmark naming style. "
        "The case name should reflect: "
        "(1) the main analysis type or physical phenomenon, "
        "(2) the structure or geometry type, and "
        "(3) the loading or condition if important. "
        "Use standard solid mechanics and finite element analysis wording. "
        "Use the following examples only as guidance for naming style. "
        "Do not copy them directly unless they truly match the user requirement: "
        "'Buckling of a column under axial compression', "
        "'Vibration of a cantilever beam', "
        "'Beam under uniaxial tension', "
        "'Uniaxial stretching of a sheet with a circular hole'. "
        "Do not include dimensions, material properties, or numeric values in the case name. "
        "The key elements should include case name, case domain, case category, and case material."
        f"Note: case domain must be one of {case_stats.get('case_domain', [])}."
        f"Note: case category must be one of {case_stats.get('case_category', [])}."
        f"Note: case material must be one of {case_stats.get('case_material', [])}."
    )
    parse_user_prompt = f"User requirement: {user_requirement}."
    res = llm.invoke(parse_user_prompt, parse_system_prompt, pydantic_obj=CaseSummaryModel)
    # pydantic_obj=CaseSummaryModel to enforce a structured response.
    return {
        "case_name": res.case_name.replace(" ", "_"),
        "case_domain": res.case_domain,
        "case_category": res.case_category,
        "case_material": res.case_material,
    }


def resolve_case_dir(config, case_name: str) -> str:
    """
    Purpose: Decide where the case should be written.
    Logic:
        If config.case_dir is set, use that directly.
        Else, use config.run_directory and append case name.
        If config.run_times > 1, suffix the case directory with the run count.
    """
    if getattr(config, "case_dir", ""):
        case_dir = config.case_dir
    else:
        if getattr(config, "run_times", 1) > 1:
            case_dir = os.path.join(str(config.run_directory), f"{case_name}_{config.run_times}")
        else:
            case_dir = os.path.join(str(config.run_directory), case_name)
    return case_dir

def _normalize_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = text.replace("_", " ")
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def _token_overlap_score(text1: str, text2: str) -> float:
    t1 = set(_normalize_text(text1).split())
    t2 = set(_normalize_text(text2).split())

    if not t1 or not t2:
        return 0.0

    overlap = len(t1.intersection(t2))
    total = len(t1.union(t2))
    return overlap / total


def _sequence_score(text1: str, text2: str) -> float:
    return SequenceMatcher(None, _normalize_text(text1), _normalize_text(text2)).ratio()


def _field_match_score(query_value: str, candidate_value: str, max_partial_score: float = 0.95) -> float:
    """
    1.0 if exact after normalization.
    Otherwise partial similarity up to max_partial_score.
    """
    q = _normalize_text(query_value)
    c = _normalize_text(candidate_value)

    if not q or not c:
        return 0.0

    if q == c:
        return 1.0

    token_score = _token_overlap_score(q, c)
    seq_score = _sequence_score(q, c)

    partial_score = 0.6 * token_score + 0.4 * seq_score
    return min(max_partial_score, partial_score)


def _hybrid_priority_score(item: Dict, case_name: str, case_category: str, case_material: str) -> float:
    """
    Hybrid stage inside the already domain-matched set:
    Category = 30%
    Case Name = 60%
    Case material = 10%
    """
    category_score = _field_match_score(
        case_category,
        item.get("case_category", ""),
        max_partial_score=0.70
    )

    name_score = _field_match_score(
        case_name,
        item.get("case_name", ""),
        max_partial_score=0.80
    )

    material_score = _field_match_score(
        case_material,
        item.get("case_material", ""),
        max_partial_score=0.70
    )
    final_score = (
        0.30 * category_score +
        0.60 * name_score +
        0.10 * material_score
    )
    print(
        f"{item.get('case_name')}\n"
        f"   category={item.get('case_category')} | category_score={category_score:.4f}\n"
        f"   material={item.get('case_material')} | material_score={material_score:.4f}\n"
        f"   name_score={name_score:.4f}\n"
        f"   final_score={final_score:.4f}\n"
    )
    return final_score


def _safe_faiss_score(item: Dict) -> float:
    """
    Tie breaker only.
    Assumes smaller score is better if score exists.
    If score is absent, send it to the end.
    """
    try:
        return float(item.get("score", 1e9))
    except Exception:
        return 1e9


def _rerank_candidates(candidates: List[Dict], case_name: str, case_category: str, case_material: str) -> List[Dict]:
    scored_candidates = []

    for item in candidates:
        hybrid_score = _hybrid_priority_score(
            item=item,
            case_name=case_name,
            case_category=case_category,
            case_material=case_material
        )
        faiss_score = _safe_faiss_score(item)

        item_copy = dict(item)
        item_copy["hybrid_score"] = hybrid_score
        item_copy["faiss_score"] = faiss_score

        scored_candidates.append(item_copy)

    return sorted(
        scored_candidates,
        key=lambda x: (-x["hybrid_score"], x["faiss_score"])
    )

def retrieve_references(case_name: str, case_material: str, case_domain: str, case_category: str, config, llm) -> Tuple[str, bool]:
    """
    Hybrid retrieval logic:
    1. Retrieve multiple candidates from FAISS using config.searchdocs
    2. Hard filter by exact case_domain
    3. Print only case names after hard domain filtering
    4. Rerank inside that filtered set using:
       - category 30%
       - case name 60%
       - case material 10%
    5. Return the best tutorial reference
    """

    case_info = (
        f"case name: {case_name}\n"
        f"case domain: {case_domain}\n"
        f"case category: {case_category}\n"
        f"case material: {case_material}"
    )

    topk = int(config.searchdocs)

    faiss_results = retrieve_faiss(
        "AbaqusAgent_tutorials_details",
        case_info,
        topk=topk
    )

    if not faiss_results:
        print("No FAISS candidates found.")
        return "", False

    print("\nSample FAISS result:")
    print(faiss_results[0])

    # Hard domain filtering
    domain_matched = [
        item for item in faiss_results
        if _normalize_text(item.get("case_domain", "")) == _normalize_text(case_domain)
    ]

    print("\nCase names after hard domain filtering:")
    print("======================================")
    if domain_matched:
        for i, item in enumerate(domain_matched, start=1):
            print(f"{i}. {item.get('case_name')}")
    else:
        print("No exact domain matched cases found.")
        print("Falling back to all FAISS candidates.")

    candidates = domain_matched if domain_matched else faiss_results

    ranked_candidates = _rerank_candidates(
        candidates=candidates,
        case_name=case_name,
        case_category=case_category,
        case_material=case_material
    )

    print("\nCase scores after domain filtering:")
    print("===================================")
    if ranked_candidates:
        for i, item in enumerate(ranked_candidates, start=1):
            print(
                f"{i}. {item.get('case_name')} | "
                f"Hybrid score: {item.get('hybrid_score', 0):.4f} | "
                f"Approximate similarity: {item.get('hybrid_score', 0) * 100:.2f}% | "
                f"FAISS score: {item.get('faiss_score', 0):.4f}"
            )
    else:
        print("No ranked candidates found.")
        return "", False

    selected = ranked_candidates[0]

    print("\nFinal selected similar case:")
    print("===========================")
    print(selected.get("case_name"))
    print(f"Hybrid score: {selected.get('hybrid_score', 0):.4f}")
    print(f"Approximate similarity: {selected.get('hybrid_score', 0) * 100:.2f}%")

    faiss_detailed = selected.get("full_content", "")

    if not faiss_detailed:
        return "", False

    faiss_detailed = re.sub(r"\n{3,}", "\n\n", faiss_detailed)

    file_dependency_flag = True
    if faiss_detailed.count('\n') >= config.file_dependency_threshold:
        file_dependency_flag = False

    return faiss_detailed, file_dependency_flag
