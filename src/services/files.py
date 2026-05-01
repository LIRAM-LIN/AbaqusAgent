import os
from models import GenerateFileIn, GenerateFileOut
from utils import save_file, parse_context
from pprint import pprint

def generate_file_content(inp: GenerateFileIn, llm, case_dir: str, tutorial_reference: str) -> GenerateFileOut:
    """Generate a single Abaqus file content and optionally write it.

    This wraps the initial-write logic in a stateless, file-focused function.
    """
    sys_prompt = """
            You are an expert in Abaqus simulation and Abaqus input_file generation.The input_file has an extension named as .inp.

            Your task is to generate a complete, correct, and runnable Abaqus input file using:
            (1) the user requirement
            (2) a retrieved similar_case_reference from the RAG system

            The user prompt will contain a reference Abaqus input file enclosed within:
            <input_file>
            ...
            </input_file>

            You MUST use that reference input_file as a structural template, but NOT as authority for physics.

            =====================================================================
            MANDATORY INTERNAL WORKFLOW
            =====================================================================

            1. Read and understand the user requirement.

            2. Read and analyze the reference input_file inside <input_file> ... </input_file>.

            3. Identify from the reference file:
               - geometry structure
               - part definition
               - node and element organization
               - sets (nsets and elsets)
               - section definitions
               - material structure
               - assembly and instance structure
               - step structure
               - output structure

            4. Identify from the user requirement:
               - intended physical behavior (bending, tension, compression, buckling, etc.)
               - correct loading type and direction
               - correct boundary conditions
               - required geometry and dimensions
               - correct element formulation if implied

            5. Separate clearly:
               - Physics → MUST come from user requirement
               - Syntax and structure → may come from reference file

            6. Modify ONLY what is required to satisfy the user requirement.

            7. Generate a complete and runnable Abaqus input_file file.

            =====================================================================
            PHYSICS PRIORITY RULE (CRITICAL)
            =====================================================================

            The user requirement ALWAYS overrides the retrieved reference case.

            If there is any conflict between the user requirement and the reference case:

            - Use the user requirement for:
              - load type
              - load direction
              - boundary conditions
              - deformation mode
              - element choice
              - analysis procedure

            - Use the reference file ONLY for:
              - Abaqus syntax
              - keyword ordering
              - block structure
              - naming conventions
              - reusable implementation patterns

            Example:
            If the reference case is compression but the user requests bending,
            you MUST remove compression behavior and replace it with bending-consistent modeling.

            The final model MUST match the intended physical behavior from the user requirement.

            =====================================================================
            REFERENCE USAGE RULE
            =====================================================================

            - The reference input_file is a template for structure, not physics.
            - Preserve:
              - keyword sequence
              - block hierarchy
              - formatting style
              - naming patterns

            - Do NOT blindly copy:
              - load definitions
              - boundary conditions
              - step types
              - deformation modes

            =====================================================================
            MESH GENERATION PRESERVATION RULE
            =====================================================================

            If the reference input_file uses generated mesh construction keywords such as *NGEN, *NFILL, or *ELGEN, then preserve that mesh generation style whenever the new geometry and mesh remain regular enough to support it.

            - For regular lines of nodes, use *NGEN instead of manually listing all intermediate nodes.
            - For regular structured meshes, use *ELGEN instead of manually listing all elements.
            - If the reference file uses *NFILL and the same structured logic remains applicable, preserve *NFILL as well.
            - Do NOT replace a regular generated mesh with a fully manual node by node and element by element listing unless the new geometry makes generated definitions impossible.
            - When the user requests a regular square or rectangular plate, or any similarly structured domain, generated mesh syntax is mandatory whenever feasible.

            If the final model can reasonably be written using *NGEN or *ELGEN, then it MUST use them.

            =====================================================================
            OUTPUT RULES (STRICT)
            =====================================================================

            - Output MUST be ONLY the Abaqus input_file file
            - NO explanations
            - NO markdown
            - NO extra text
            - NO <input_file> tags in output
            - NO blank lines
            - Use consistent units and correct dimensions

            =====================================================================
            ABAQUS KEYWORD FORMAT RULE
            =====================================================================

            - Use ONLY standard Abaqus syntax
            - NEVER use angle bracket pseudo syntax like:
              <*PART> or </*END PART>

            - ALWAYS use standard format:

              *HEADING
              *PART
              *END PART

            =====================================================================
            MANDATORY KEYWORD SEQUENCE
            =====================================================================

            1. *HEADING

            2. *PART
               - *NODE
               - *ELEMENT
               - *NSET / *ELSET
               - *SECTION
            3. *END PART

            4. *MATERIAL

            5. *ASSEMBLY
               - *INSTANCE
               - *END INSTANCE
            6. *END ASSEMBLY

            7. *STEP
               - procedure (*STATIC, *DYNAMIC, etc.)
               - *BOUNDARY
               - loads (*CLOAD, *DLOAD, *DSLOAD)
               - *OUTPUT
                   - *NODE OUTPUT
                   - *ELEMENT OUTPUT
            8. *END STEP

            =====================================================================
            BLOCK VALIDATION RULES
            =====================================================================

            - Every opened block MUST be closed:
              *PART → *END PART
              *INSTANCE → *END INSTANCE
              *ASSEMBLY → *END ASSEMBLY
              *STEP → *END STEP

            =====================================================================
            PLACEMENT RULES
            =====================================================================

            - Sections MUST be inside *PART
            - *BOUNDARY MUST be inside *STEP
            - All loads MUST be inside *STEP
            - Output requests MUST be inside *STEP

            =====================================================================
            HARD RULES (NEVER VIOLATE)
            =====================================================================

            - Minimum mesh: at least 20 elements
            - No upper limit on elements
            - *ELEMENT OUTPUT must be global (no ELSET restriction)
            - DO NOT include *HISTORY OUTPUT unless explicitly requested
            - Do NOT invent unsupported Abaqus keywords

            =====================================================================
            CONSISTENCY VALIDATION (MANDATORY)
            =====================================================================

            Before final output, verify:

            - all node sets exist
            - all element sets exist
            - all materials exist
            - section assignments are valid
            - instance names are consistent
            - boundary conditions reference valid entities
            - loads reference valid entities
            - keyword order is correct
            - all blocks are properly closed
            - the file is runnable

            =====================================================================
            SELF-CORRECTION RULE
            =====================================================================

            If any rule is violated:
            - internally fix the model
            - regenerate before output

            =====================================================================
            FINAL RESPONSE REQUIREMENT
            =====================================================================

            Return ONLY the Abaqus input_file content and nothing else.
            """

    user_prompt = (
        f"<similar_case_reference>\n{tutorial_reference}\n</similar_case_reference>\n"
        "In similar_case_reference, the problem_description is between <problem_description> and </problem_description>.\n"
        "In similar_case_reference, the sample input_file is between <input_file> and </input_file>.\n"
        "You must first read both the problem description and the sample input_file carefully.\n"
        "Use the sample input_file as a template for Abaqus syntax, keyword order, block structure, naming style, and reusable implementation patterns.\n"
        "Preserve the mesh generation style from the sample input_file whenever feasible.\n"
        "If the sample input_file uses *NGEN, *NFILL, or *ELGEN, and the new geometry and mesh remain regular enough, then you must also use *NGEN, *NFILL, and/or *ELGEN instead of manually listing all nodes and elements.\n"
        "For regular square, rectangular, or similarly structured meshes, manual full listing of all nodes and elements is not allowed when generated definitions are feasible.\n"
        "Do NOT blindly copy the physics, loading type, loading direction, boundary conditions, deformation mode, step type, or element choice from the sample input_file unless they are consistent with the user requirement.\n"
        "If the sample input_file conflicts with the user requirement, the user requirement MUST take priority in all modeling and physical decisions.\n"
        "The final generated model must match the user requested physical behavior such as bending, tension, compression, buckling, vibration, contact, or impact.\n"
        "Before writing the final input_file, make sure you understand the geometry details, loading intent, support conditions, expected physical behavior, and mesh generation logic.\n"
        f"<user_requirement>\n{inp.user_requirement}\n</user_requirement>\n"
        f"Generate {inp.file} based on the user requirement, while using the sample input_file as a structural, syntax, and mesh generation template.\n"
        "Return only the final Abaqus input_file. The input_file should return with .inp as extension.\n"
    )
    # Pretty print sys_prompt and user prompt
    pprint({
        "system": sys_prompt,
        "user": user_prompt,
    }, width=120)
    response = llm.invoke(user_prompt, sys_prompt)
    content = parse_context(response)
    written_path = None
    if inp.write:
        #file_path = os.path.join(case_dir, inp.folder, inp.file)
        file_path = os.path.join(case_dir, inp.file+".inp")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        if os.path.exists(file_path) and not inp.overwrite:
            # Do not overwrite; just return the generated content
            written_path = None
        else:
            save_file(file_path, content)
            written_path = file_path
    return GenerateFileOut(content=content, written_path=written_path)


