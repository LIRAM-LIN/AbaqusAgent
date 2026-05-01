# architect_node.py
import os
import re
from utils import save_file, retrieve_faiss, parse_directory_structure
from utils import save_file, parse_directory_structure
from services.architect import (
    parse_requirement_to_case_info,
    resolve_case_dir,
    retrieve_references,
)
from pydantic import BaseModel, Field
from typing import List
import shutil

# from router_func import llm_requires_custom_mesh

"""
CaseSummaryPydantic: defined at the top of src/nodes/architect_node.py
AbaqusAgentPlanPydantic: defined in the same file
They are only defined in src/nodes/architect_node.py and not used anywhere else in the codebase.
"""

class CaseSummaryPydantic(BaseModel):
    case_name: str = Field(description="name of the case")
    case_domain: str = Field(description="domain of the case, case domain must be one of [staticstressdisplacementanalysis_bending, staticstressdisplacementanalysis_tension, staticstressdisplacementanalysis_compression, staticstressdisplacementanalysis_torsion, bucklinganalysis, vibrationanalysis, and dynamic_analysis_not_vibration_analysis].")
    case_category: str = Field(description="category of the case")
    case_material: str = Field(description="material of the case")


class SubtaskPydantic(BaseModel):
    file_name: str = Field(description="Name of the AbaqusAgent input file")
    folder_name: str = Field(description="Name of the folder where the Abaqus file should be stored")


class AbaqusAgentPlanPydantic(BaseModel):
    subtasks: List[SubtaskPydantic] = Field(description="List of subtasks, each with its corresponding file and folder names")


"""
    architect_node is the first major node in the AbaqusAgent workflow. Its job is to:
        Interpret the user requirement into a structured AbaqusAgent case description
        Create a new case directory
        Retrieve similar case references from FAISS
        Split the work into subtasks (files to generate)
        Decide mesh type (custom / gmsh / standard)
"""


def architect_node(state):
    """
    Architect node: Parse the user requirement to a standard case description,
    finds a similar reference case from the FAISS databases, and splits the work into subtasks.
    Updates state with:
      - case_dir, tutorial, case_name, subtasks.
    """
    config = state["config"]
    user_requirement = state["user_requirement"]

    # Step 1: Translate user requirement (service)
    info = parse_requirement_to_case_info(user_requirement, state["case_stats"], state["llm_service"])
    case_name = info["case_name"]
    case_domain = info["case_domain"]
    case_category = info["case_category"]
    case_material = info["case_material"]

    print(f"Parsed case name: {case_name}")
    print(f"Parsed case domain: {case_domain}")
    print(f"Parsed case category: {case_category}")
    print(f"Parsed case material: {case_material}")

    # # Step 2: Determine case directory (service)
    case_dir = resolve_case_dir(config, case_name)
    faiss_detailed, file_dependency_flag = retrieve_references(
         case_name, case_material, case_domain, case_category, config, state["llm_service"]
     )

    case_path = os.path.join(case_dir, "similar_case.txt")

    tutorial_reference = faiss_detailed
    case_path_reference = case_path

    save_file(case_path, f"{faiss_detailed}\n\n\n")

    # Return updated state
    case_info = f"case name: {case_name}\ncase domain: {case_domain}\ncase category: {case_category}\ncase solver: {case_material}"
    return {
        "case_name": case_name,
        "case_domain": case_domain,
        "case_category": case_category,
        "case_material": case_material,
        "case_dir": case_dir,
        "tutorial_reference": tutorial_reference,
        "case_path_reference": case_path_reference,
        "case_info": case_info,
        "file_dependency_flag": file_dependency_flag
    }
