# src/nodes/interpreter_node.py

from services.interpreter import interpret_and_check_missing_items


def interpreter_node(state):
    raw_prompt = state.get("user_requirement", "")
    raw_prompt = raw_prompt.strip() if raw_prompt else ""

    if not raw_prompt:
        missing_items = [
            "geometry",
            "material properties",
            "boundary conditions",
            "loading conditions",
            "requested output"
        ]

        feedback = (
            "Simulation failed due to insufficient user prompt.\n"
            "Please update the missing items:\n- " +
            "\n- ".join(missing_items)
        )

        print("\n" + "=" * 80)
        print("INTERPRETER NODE")
        print("=" * 80)
        print("Empty user requirement detected.")
        print(feedback)
        print("=" * 80 + "\n")

        print("Interpreter return debug:")
        print(f"missing_items = {missing_items}")
        print("missing_required_info = True")

        return {
            **state,
            "original_user_requirement": "",
            "interpreted_prompt": "",
            "user_requirement": "",
            "missing_items": missing_items,
            "missing_required_info": True,
            "interpreter_feedback": feedback,
        }

    llm_service = state.get("llm_service", None)
    if llm_service is None:
        raise ValueError("llm_service is missing from state.")

    print("\n" + "=" * 80)
    print("INTERPRETER NODE")
    print("=" * 80)
    print("Original user requirement:\n")
    print(raw_prompt)
    print("\nGenerating interpreted prompt and checking required items...\n")

    try:
        result = interpret_and_check_missing_items(raw_prompt, llm_service)
        interpreted_prompt = result.get("rewritten_prompt", raw_prompt).strip()
        missing_items = result.get("missing_items", [])

        if not isinstance(missing_items, list):
            missing_items = []

        missing_items = [str(item).strip().lower() for item in missing_items if str(item).strip()]
        missing_required_info = len(missing_items) > 0

        if missing_required_info:
            feedback = (
                "Simulation failed due to insufficient user prompt.\n"
                "Please update the missing items:\n- " +
                "\n- ".join(missing_items)
            )
        else:
            feedback = "All required items are present. Proceeding to the next step."

        print("Interpreted prompt:\n")
        print(interpreted_prompt)

        print("\nMissing items:")
        if missing_items:
            for item in missing_items:
                print(f"- {item}")
        else:
            print("None")

        print("=" * 80 + "\n")

        print("Interpreter return debug:")
        print(f"missing_items = {missing_items}")
        print(f"missing_required_info = {missing_required_info}")

        return {
            **state,
            "original_user_requirement": raw_prompt,
            "interpreted_prompt": interpreted_prompt,
            "user_requirement": interpreted_prompt,
            "missing_items": missing_items,
            "missing_required_info": missing_required_info,
            "interpreter_feedback": feedback,
        }

    except Exception as e:
        error_msg = str(e)

        lower_error = error_msg.lower()
        missing_items = []

        if "geometry" in lower_error:
            missing_items.append("geometry")
        if "material properties" in lower_error:
            missing_items.append("material properties")
        if "boundary conditions" in lower_error:
            missing_items.append("boundary conditions")
        if "loading conditions" in lower_error:
            missing_items.append("loading conditions")
        if "requested output" in lower_error:
            missing_items.append("requested output")

        if not missing_items:
            missing_items = [
                "geometry",
                "material properties",
                "boundary conditions",
                "loading conditions",
                "requested output"
            ]

        feedback = (
            "Simulation failed due to insufficient user prompt.\n"
            "Please update the missing items:\n- " +
            "\n- ".join(missing_items)
        )

        print("\n[Interpreter Node] Error:")
        print(error_msg)
        print("\n" + feedback)

        print("Interpreter return debug:")
        print(f"missing_items = {missing_items}")
        print("missing_required_info = True")

        return {
            **state,
            "original_user_requirement": raw_prompt,
            "interpreted_prompt": raw_prompt,
            "user_requirement": raw_prompt,
            "missing_items": missing_items,
            "missing_required_info": True,
            "interpreter_feedback": feedback,
        }