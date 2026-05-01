# reviewer_node.py
from pydantic import BaseModel, Field
from typing import List
from services.review import review_error_logs

REVIEWER_SYSTEM_PROMPT = (
    "You are an expert in Abaqus finite element modeling and Abaqus input (.inp) file debugging. "
    "Your task is to review the provided Abaqus error logs and diagnose the underlying issues. "
    "You will be provided with a similar case reference, which is a list of similar cases ordered by similarity. "
    "Use these references to understand the intended analysis and typical keyword patterns. "
    "When an error indicates that a specific Abaqus keyword, option, set name, surface name, element type, material name, or step procedure is undefined, "
    "your response must propose a fix that defines that exact missing item exactly as it appears in the error message (case-sensitive where applicable). "
    "Do not rename, reinterpret, or 'correct' the identifier; treat it literally and make the smallest change needed to define it. "
    "When the error indicates an unavailable procedure (e.g., a keyword not supported in Abaqus/Explicit such as *BUCKLE), "
    "propose an equivalent supported workflow using the same user intent (for example, eigenvalue buckling in Abaqus/Standard, "
    "or an Explicit dynamic alternative such as an imperfection + quasi-static compression), without changing the user-stated requirements unless unavoidable. "
    "Propose ideas to resolve the errors, but do not modify any files directly and do not output a complete rewritten .inp. "
    "Do not propose solutions that require changing geometry, loads, boundary conditions, material constants, units, or analysis targets stated in the user requirement; "
    "instead, prioritize fixes such as correcting keyword order, adding required data lines, defining missing *NSET/*ELSET/*SURFACE, "
    "fixing section assignments, adding amplitude/step controls, correcting node/element numbering, resolving duplicate IDs, "
    "fixing contact/rigid body definitions, and ensuring assembly/instance scoping is correct. "
    "The user will supply all relevant Abaqus files and the error logs; in the logs you will find the error content and the corresponding command or job context. "
    "Do not ask the user any questions. "
    "Your output must be a clear list of: (1) likely root cause(s), (2) the minimal keyword-level fix(es), and (3) a brief verification checklist "
    "to confirm the fix (e.g., 'check set exists at the correct scope', 'confirm step type supports the requested output')."
)
def reviewer_node(state):
    """
    Reviewer node: Reviews the error logs and provides analysis and suggestions
    for fixing the errors. This node only focuses on analysis, not file modification.
    """
    print(f"============================== Reviewer Analysis ==============================")
    if len(state["error_logs"]) == 0:
        print("No error to review.")
        return state
    
    # Stateless review via service
    history_text = state.get("history_text") or []
    review_content, updated_history = review_error_logs(
        tutorial_reference=state.get('tutorial_reference', ''),
        Abaqusfiles=state.get('Abaqusfiles'),
        error_logs=state.get('error_logs'),
        user_requirement=state.get('user_requirement', ''),
        llm=state["llm_service"],
        history_text=history_text,
    )

    print(review_content)
    print("loop_count + 1")

    return {
        "history_text": updated_history,
        "review_analysis": review_content,
        "loop_count": state.get("loop_count", 0) + 1,
        "input_writer_mode": "rewrite",
    }
