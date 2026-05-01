from typing import List, Optional, Tuple
from models import ReviewIn, ReviewOut


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


def review_error_logs(
    tutorial_reference: str,
    Abaqusfiles,
    error_logs,
    user_requirement: str,
    llm,
    history_text: Optional[List[str]] = None,
) -> Tuple[str, List[str]]:
    """Stateless reviewer: returns (review_analysis, updated_history)."""

    """
    If there’s history:
        It includes prior attempts and asks for new guidance.
    If there’s no history:
        It prompts the LLM with:
            similar case reference
            current Abaqusfiles
            current error logs
            user requirement
    Then it:
        Calls the LLM (llm.invoke)
        Builds a structured history block for this attempt
        Returns (review_content, updated_history)
    """


    if history_text:
        reviewer_user_prompt = (
            f"<similar_case_reference>{tutorial_reference}</similar_case_reference>\n"
            f"<abaqusfiles>{str(Abaqusfiles)}</abaqusfiles>\n"
            f"<current_error_logs>{error_logs}</current_error_logs>\n"
            f"<history>\n{chr(10).join(history_text)}\n</history>\n\n"
            f"<user_requirement>{user_requirement}</user_requirement>\n\n"
            f"I have modified the files according to your previous suggestions. If the error persists, please provide further guidance. Make sure your suggestions adhere to user requirements and do not contradict it. Also, please consider the previous attempts and try a different approach."
        )
    else:
        reviewer_user_prompt = (
            f"<similar_case_reference>{tutorial_reference}</similar_case_reference>\n"
            f"<abaqusfiles>{str(Abaqusfiles)}</abaqusfiles>\n"
            f"<error_logs>{error_logs}</error_logs>\n"
            f"<user_requirement>{user_requirement}</user_requirement>\n"
            "Please review the error logs and provide guidance on how to resolve the reported errors. Make sure your suggestions adhere to user requirements and do not contradict it."
        )

    review_response = llm.invoke(reviewer_user_prompt, REVIEWER_SYSTEM_PROMPT)
    """The LLM only suggests fixes in the reviewer step, 
    but the actual file modifications happen in rewrite_files(...),"""
    review_content = review_response

    updated_history = list(history_text) if history_text else []
    current_attempt = [
        f"<Attempt {len(updated_history)//4 + 1}>\n",
        f"<Error_Logs>\n{error_logs}\n</Error_Logs>",
        f"<Review_Analysis>\n{review_content}\n</Review_Analysis>",
        f"</Attempt>\n",
    ]
    updated_history.extend(current_attempt)
    return review_content, updated_history


def review_and_suggest_fix(inp: ReviewIn, llm, tutorial_reference: str, Abaqusfiles, user_requirement: str) -> ReviewOut:
    """A thin wrapper used by the MCP adapter:
            Calls review_error_logs(...)
            Returns a ReviewOut object (suggestions only)
    """
    review_content, _ = review_error_logs(
        tutorial_reference=tutorial_reference,
        Abaqusfiles=Abaqusfiles,
        error_logs=inp.logs,
        user_requirement=user_requirement,
        llm=llm,
        history_text=None,
    )
    return ReviewOut(suggestions=review_content)


