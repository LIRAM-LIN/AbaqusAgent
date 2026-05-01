import os
from typing import Dict, List
from utils import save_file, parse_context, AbaqusPydantic, AbaqusfilePydantic
from utils import retrieve_faiss
from services.files import generate_file_content
import re


def compute_priority(subtask):
    if subtask["folder_name"] == "system":
        return 0
    elif subtask["folder_name"] == "constant":
        return 1
    elif subtask["folder_name"] == "0":
        return 2
    else:
        return 3


def initial_write(llm, case_dir: str, subtasks: List[Dict], user_requirement: str, tutorial_reference: str, file_dependency_flag: bool) -> Dict:
    subtasks = sorted(subtasks, key=compute_priority)
    written_files = []
    dir_structure = {}

    file_name="AbaqusInput"
    folder_name=case_dir
    inp = type("GenIn", (), {"file": file_name, "write": True, "overwrite": True, "user_requirement":user_requirement})
    out = generate_file_content(inp, llm, case_dir, tutorial_reference)
    written_files.append(AbaqusfilePydantic(file_name=file_name, folder_name=folder_name, content=out.content))

    Abaqusfiles = AbaqusPydantic(list_Abaqusfile=written_files)
    return {"dir_structure": dir_structure, "Abaqusfiles": Abaqusfiles}


def rewrite_files(llm, case_dir: str, Abaqusfiles, error_logs, review_analysis, user_requirement: str, dir_structure: Dict) -> Dict:
    """Rewrite Abaqus files based on reviewer analysis using LLM and return updated structures.

    Returns a dict with keys: dir_structure, files, error_logs (cleared on success).
    """
    from utils import AbaqusPydantic, AbaqusfilePydantic  # local import to avoid cycles
    import re
    import os

    rewrite_system_prompt = (
        "You are an expert in Abaqus simulation and numerical modeling. "
        "Your task is to modify and rewrite the necessary Abaqus input files to fix the reported error. "
        "Please do not propose solutions that require modifying any parameters declared in the user requirement, try other approaches instead."
        "The user will provide the error content, error command, reviewer's suggestions, and all relevant files. "
        "Only return files that require rewriting, modification, or addition; do not include files that remain unchanged. "
        "Return the complete, corrected file contents in the following JSON format: "
        "list of files: [{file_name: 'file_name', folder_name: 'folder_name', content: 'content'}]. "
        "Follow this exact mandatory section order in the .inp file:\n"
        "1) *HEADING\n"
        "2) *PART ... (nodes, elements, nsets/elsets, sections)\n"
        "   - All section assignments MUST be inside the *PART block\n"
        "   - If there is a *PART, there MUST be a matching *END PART\n"
        "3) *MATERIAL ... (all materials)\n"
        "4) *ASSEMBLY ... (instances, assembly-level sets/surfaces)\n"
        "   - If there is an *INSTANCE, there MUST be a matching *END INSTANCE\n"
        "   - If there is an *ASSEMBLY, there MUST be a matching *END ASSEMBLY\n"
        "5) *STEP ...\n"
        "   - *BOUNDARY must be inside the *STEP\n"
        "   - All loads (*CLOAD, *DLOAD, *DSLOAD) must be inside the *STEP\n"
        "   - Output requests (*OUTPUT, *NODE OUTPUT, *ELEMENT OUTPUT) must be inside the *STEP\n"
        "   - If there is a *STEP, there MUST be a matching *END STEP\n"
        "HARD RULES (must never be violated):\n"
        "   - The finite element mesh MUST contain at least 10 elements. "
        "     There is no upper limit on the number of elements.\n"
        "   - When requesting *ELEMENT OUTPUT, do NOT request output for any specific element set; "
        "     element output must be global/default only.\n"
        "   - Do NOT request *HISTORY OUTPUT under any circumstances.\n"
        "Before finalizing, validate that all referenced set names, material names, and section names exist "
        "and are used consistently."
    )

    rewrite_user_prompt = (
        f"<Abaqus files>{str(Abaqusfiles)}</Abaqus files>\n"
        f"<error_logs>{error_logs}</error_logs>\n"
        f"<reviewer_analysis>{review_analysis}</reviewer_analysis>\n\n"
        f"<user_requirement>{user_requirement}</user_requirement>\n\n"
        "Please update the relevant Abaqus files to resolve the reported errors, ensuring that all modifications strictly adhere to the specified formats. Ensure all modifications adhere to user requirement."
    )

    response = llm.invoke(rewrite_user_prompt, rewrite_system_prompt, pydantic_obj=AbaqusPydantic)

    # Prepare updated structures
    updated_dir = dict(dir_structure) if dir_structure else {}
    Abaqusfiles_list = list(Abaqusfiles.list_Abaqusfile) if Abaqusfiles and hasattr(Abaqusfiles, "list_Abaqusfile") else []

    for Abaqusfile in response.list_Abaqusfile:
        # file_path = os.path.join(case_dir, Abaqusfile.folder_name, Abaqusfile.file_name)
        file_path = os.path.join(case_dir, Abaqusfile.file_name+'.inp')
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        save_file(file_path, Abaqusfile.content)

        if Abaqusfile.folder_name not in updated_dir:
            updated_dir[Abaqusfile.folder_name] = []
        if Abaqusfile.file_name not in updated_dir[Abaqusfile.folder_name]:
            updated_dir[Abaqusfile.folder_name].append(Abaqusfile.file_name)

        Abaqusfiles_list = [
            f for f in Abaqusfiles_list
            if not (f.folder_name == Abaqusfile.folder_name and f.file_name == Abaqusfile.file_name)
        ]
        Abaqusfiles_list.append(Abaqusfile)

    updated_Abaqusfiles = AbaqusPydantic(list_Abaqusfile=Abaqusfiles_list)
    return {
        "dir_structure": updated_dir,
        "Abaqusfiles": updated_Abaqusfiles,
        "error_logs": [],
    }

