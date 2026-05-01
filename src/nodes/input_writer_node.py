# input_writer_node.py
import os
from utils import save_file, parse_context, AbaqusPydantic, AbaqusfilePydantic
from utils import retrieve_faiss
from services.input_writer import initial_write, rewrite_files  # , build_allrun,
import re
from typing import List
from pydantic import BaseModel, Field

"""
    This node is responsible for writing AbaqusAgent input files and creating the Allrun script.
        It has two modes:
        Initial write (generate files from scratch)
        Rewrite (modify files after review errors)
"""

# System prompts for different modes
INITIAL_WRITE_SYSTEM_PROMPT = (
    "You are an expert in AbaqusAgent simulation and numerical modeling."
    f"Your task is to generate a complete and functional file named: <file_name>{{file_name}}</file_name> within the <folder_name>{{folder_name}}</folder_name> directory. "
    "Ensure all required values are present and match with the files content already generated."
    "Before finalizing the output, ensure:\n"
    "- All necessary fields exist (e.g., if `nu` is defined in `constant/transportProperties`, it must be used correctly in `0/U`).\n"
    "- Cross-check field names between different files to avoid mismatches.\n"
    "- Ensure units and dimensions are correct** for all physical variables.\n"
    f"- Ensure case material settings are consistent with the user's requirements. Available materials are: {{case_material}}.\n"
    "Provide only the code—no explanations, comments, or additional text."
)

REWRITE_SYSTEM_PROMPT = None  # Deprecated: logic moved to service


def compute_priority(subtask):
    if subtask["folder_name"] == "system":
        return 0
    elif subtask["folder_name"] == "constant":
        return 1
    elif subtask["folder_name"] == "0":
        return 2
    else:
        return 3


#
# def parse_allrun(text: str) -> str:
#     match = re.search(r'```(.*?)```', text, re.DOTALL)
#
#     return match.group(1).strip()
#
# def retrieve_commands(command_path) -> str:
#     with open(command_path, 'r') as file:
#         commands = file.readlines()
#
#     return f"[{', '.join([command.strip() for command in commands])}]"

class CommandsPydantic(BaseModel):
    commands: List[str] = Field(description="List of commands")


def input_writer_node(state):
    """
    InputWriter node: Generate the complete AbaqusAgent Abaqusfile.

    Args:
        state: The current state containing all necessary information
    """

    mode = state["input_writer_mode"]

    if mode == "rewrite":
        return _rewrite_mode(state)
    else:
        return _initial_write_mode(state)


def _rewrite_mode(state):
    """Rewrite mode: delegate to service to modify files based on review analysis."""
    """
    When used: after a review cycle (review_analysis exists).
        Delegates to the service rewrite_files(...)
        Passes in existing Abaqusfiles, error logs, review analysis, and directory structure
        Returns the updated file set
    """
    print(f"============================== Rewrite Mode ==============================")
    if not state.get("review_analysis"):
        print("No review analysis available for rewrite mode.")
        return state
    out = rewrite_files(
        llm=state["llm_service"],
        case_dir=state["case_dir"],
        Abaqusfiles=state.get("Abaqusfiles"),
        error_logs=state.get("error_logs", []),
        review_analysis=state.get("review_analysis", ""),
        user_requirement=state.get("user_requirement", ""),
        dir_structure=state.get("dir_structure", {}),
    )
    return out


def _initial_write_mode(state):
    """
    Initial write mode: Generate files from scratch
    Calls initial_write(...) service to create AbaqusAgent files based on subtasks
    Extracts dir_structure and Abaqusfile from the result
    Calls build_allrun(...) to generate the Allrun script
    Returns updated state (dir structure + Abaqusfile)
    """
    print(f"============================== Initial Write Agent ==============================")

    config = state["config"]
    write_out = initial_write(
        llm=state["llm_service"],
        case_dir=state["case_dir"],
        subtasks=state["subtasks"],
        user_requirement=state["user_requirement"],
        tutorial_reference=state["tutorial_reference"],
        # case_material=state['case_stats']['case_material'],
        file_dependency_flag=state["file_dependency_flag"],
    )

    dir_structure = write_out["dir_structure"]
    Abaqusfiles = write_out["Abaqusfiles"]

    # Build Allrun via service
    # mesh_type = state.get("mesh_type")
    # mesh_commands = state.get("mesh_commands") or []
    # allrun_out = build_allrun(
    #     llm=state["llm_service"],
    #     case_dir=state["case_dir"],
    #     config=config,
    #     dir_structure=dir_structure,
    #     case_info=state["case_info"],
    #     allrun_reference=state["allrun_reference"],
    #     mesh_type=mesh_type,
    #     mesh_commands=mesh_commands,
    # )

    return {
        "dir_structure": dir_structure,
        "commands": [],
        "Abaqusfiles": Abaqusfiles,
    }
