# src/services/interpreter.py
import json
import re

INTERPRETER_SYSTEM_PROMPT = """
You are an expert Abaqus FEA prompt interpreter.

Your task is to:
1. Rewrite the user's raw request into a clear, professional Abaqus-style engineering prompt.
2. Check whether these 5 required items are present:
   - geometry
   - material properties
   - boundary conditions
   - loading conditions
   - requested output

Rules:
1. Preserve the user's original technical intent.
2. Rewrite the request using proper Abaqus and finite element analysis terminology.
3. Improve clarity, grammar, and structure.
4. Do not invent numerical values or technical details that the user did not provide.
5. If the user provides additional useful simulation information beyond the 5 required items, preserve that information in the rewritten prompt.
6. Do not remove useful details such as analysis type, dimensionality, element type, step type, meshing preference, symmetry, contact definition, solver hints, units, special constraints, or postprocessing requests.
7. If a required item is not clearly provided, mark it as missing.
8. If the prompt is too vague or lacks sufficient detail, include all missing required items.
9. Return only valid JSON. Do not add markdown fences, comments, or extra explanation.

Return output strictly in this JSON format:
{
  "rewritten_prompt": "string",
  "missing_items": [
    "list of missing items from: geometry, material properties, boundary conditions, loading conditions, requested output"
  ]
}

If no required items are missing, return:
{
  "rewritten_prompt": "string",
  "missing_items": []
}
"""


def _extract_response_text(response):
    if isinstance(response, str):
        return response.strip()
    if hasattr(response, "content"):
        return response.content.strip()
    return str(response).strip()


def _clean_json_text(text: str) -> str:
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    return text.strip()


def interpret_and_check_missing_items(raw_prompt, llm_service):
    raw_prompt = (raw_prompt or "").strip()

    if not raw_prompt:
        return {
            "rewritten_prompt": "",
            "missing_items": [
                "geometry",
                "material properties",
                "boundary conditions",
                "loading conditions",
                "requested output"
            ]
        }

    user_message = f"""
Raw user prompt:
{raw_prompt}

Rewrite it into proper Abaqus FEA wording and identify which required items are missing.
"""

    response = llm_service.invoke(user_message, INTERPRETER_SYSTEM_PROMPT)

    content = _extract_response_text(response)
    content = _clean_json_text(content)

    try:
        result = json.loads(content)
    except Exception as e:
        raise ValueError(
            f"Interpreter returned invalid JSON.\nRaw response was:\n{content}"
        ) from e

    rewritten_prompt = result.get("rewritten_prompt", "").strip()
    missing_items = result.get("missing_items", [])

    if not isinstance(missing_items, list):
        raise ValueError(f"'missing_items' must be a list, got: {type(missing_items)}")

    valid_items = {
        "geometry",
        "material properties",
        "boundary conditions",
        "loading conditions",
        "requested output",
    }

    cleaned_missing_items = []
    for item in missing_items:
        if isinstance(item, str):
            item_clean = item.strip().lower()
            if item_clean in valid_items and item_clean not in cleaned_missing_items:
                cleaned_missing_items.append(item_clean)

    if not rewritten_prompt:
        rewritten_prompt = raw_prompt

    return {
        "rewritten_prompt": rewritten_prompt,
        "missing_items": cleaned_missing_items
    }