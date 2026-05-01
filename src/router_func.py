from typing import TypedDict, List, Optional
from config import Config
from utils import LLMService, GraphState
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
import os

def llm_requires_hpc(state: GraphState) -> bool:
    """
    Use LLM to determine if user requires HPC/cluster execution based on their requirement.
    Args:
        state: Current graph state containing user requirement and LLM service
    Returns:
        bool: True if HPC execution is required, False otherwise
    Used by:
        route_after_input_writer (to choose hpc_runner vs local_runner).
    """
    user_requirement = state["user_requirement"]

    system_prompt = (
        "You are an expert in AbaqusAgent workflow analysis. "
        "Analyze the user requirement to determine if they want to run the simulation on HPC (High Performance Computing) or locally. "
        "Look for keywords like: HPC, cluster, supercomputer, SLURM, PBS, job queue, "
        "parallel computing, distributed computing, or any mention of running on remote systems. "
        "If the user explicitly mentions or implies they want to run on HPC/cluster, return 'hpc_run'. "
        "If they want to run locally or don't specify, return 'local_run'. "
        "Be conservative - if unsure, assume local run unless clearly specified otherwise."
        "Only return 'hpc_run' or 'local_run'. Don't return anything else."
    )

    user_prompt = (
        f"User requirement: {user_requirement}\n\n"
        "return 'hpc_run' or 'local_run'"
    )

    response = state["llm_service"].invoke(user_prompt, system_prompt)
    return "hpc_run" in response.lower()

def route_after_interpreter(state: GraphState):
    missing_items = state.get("missing_items", [])
    missing_required_info = state.get("missing_required_info", False)

    print("Router debug:")
    print(f"missing_required_info = {missing_required_info}")
    print(f"missing_items = {missing_items}")

    if missing_required_info or (missing_items and len(missing_items) > 0):
        print("Router: Missing required input information. Ending workflow.")
        print("Missing items:")
        for item in missing_items:
            print(f"- {item}")
        return END

    print("Router: All required items are present. Routing to architect node.")
    return "architect"

def route_after_architect(state: GraphState):
    """
    Route after architect node based on whether user wants custom mesh.
    For current version, if user wants custom mesh, user should be able to provide a path to the mesh file.
    Logic:
        If state.mesh_type == "custom_mesh" → go to meshing
        If state.mesh_type == "gmsh_mesh" → go to meshing
        Else → go to input_writer
    """
    mesh_type = state.get("mesh_type", "standard_mesh")
    if mesh_type == "custom_mesh":
        print("Router: Custom mesh requested. Routing to meshing node.")
        return "meshing"
    elif mesh_type == "gmsh_mesh":
        print("Router: GMSH mesh requested. Routing to meshing node.")
        return "meshing"
    else:
        print("Router: Standard mesh generation. Routing to input_writer node.")
        return "input_writer"


def route_after_input_writer(state: GraphState):
    """
    Route after input_writer node based on whether user wants to run on HPC.
    Logic:
        If llm_requires_hpc(state) → hpc_runner
        Else → local_runner
    """
    if llm_requires_hpc(state):
        print("LLM determined: HPC run requested. Routing to hpc_runner node.")
        return "hpc_runner"
    else:
        print("LLM determined: Local run requested. Routing to local_runner node.")
        return "local_runner"

def route_after_runner(state):
    if state.get("error_content") or state.get("error_logs"):
        return "reviewer"

    output_dir = state.get("case_dir", "")
    odb_path = os.path.join(output_dir, "AbaqusInput.odb")

    print(f"[route_after_runner] checking ODB at: {odb_path}")

    if os.path.isfile(odb_path):
        state["simulation_success"] = True
        print("[route_after_runner] ODB found -> visualization")
        return "visualization"

    print("[route_after_runner] ODB not found -> END")
    return END


def route_after_reviewer(state):
    loop_count = state.get("loop_count", 0)
    max_loop = state["config"].max_loop
    if loop_count >= max_loop:
        print(f"Maximum loop count ({max_loop}) reached. Ending workflow.")
        # if llm_requires_visualization(state):
        #     return "visualization"
        # else:
        #     return END
        return END
    print(f"Loop {loop_count}: Continuing to fix errors.")

    if (state.get("error_content") or state.get("error_logs")) and loop_count < max_loop:
        print("[route_after_reviewer] errors remain -> input_writer")
        return "input_writer"

    output_dir = state.get("case_dir", "")
    odb_path = os.path.join(output_dir, "AbaqusInput.odb")

    print(f"[route_after_reviewer] checking ODB at: {odb_path}")

    if os.path.isfile(odb_path):
        state["simulation_success"] = True
        print("[route_after_reviewer] ODB found -> visualization")
        return "visualization"

    print("[route_after_reviewer] ODB not found -> END")
    return END
