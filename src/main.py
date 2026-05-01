from dataclasses import dataclass, field
from typing import List, Optional, TypedDict, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
import argparse
from pathlib import Path
from utils import LLMService, GraphState
import time
from config import Config
from nodes.interpreter_node import interpreter_node
from nodes.architect_node import architect_node
# from nodes.meshing_node import meshing_node
from nodes.input_writer_node import input_writer_node
from nodes.local_runner_node import local_runner_node
from nodes.reviewer_node import reviewer_node
from nodes.visualization_node import visualization_node
# from nodes.hpc_runner_node import hpc_runner_node
from router_func import (
    route_after_interpreter,
    route_after_runner,
    route_after_reviewer
)
import json

def create_abaqus_agent_graph() -> StateGraph:
    """Create the abaqus agent workflow graph."""

    # Create the graph
    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("interpreter", interpreter_node)
    workflow.add_node("architect", architect_node)
    #workflow.add_node("meshing", meshing_node)
    workflow.add_node("input_writer", input_writer_node)
    workflow.add_node("local_runner", local_runner_node)
    #workflow.add_node("hpc_runner", hpc_runner_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("visualization", visualization_node)

    # Add edges
    workflow.add_edge(START, "interpreter")
    workflow.add_conditional_edges("interpreter", route_after_interpreter)
    workflow.add_edge("architect", "input_writer")
    workflow.add_edge("input_writer", "local_runner")
    workflow.add_conditional_edges("local_runner", route_after_runner)
    workflow.add_conditional_edges("reviewer", route_after_reviewer)
    workflow.add_edge("visualization", END)

    return workflow

"""
Purpose: builds the shared state object for the workflow.

It creates a GraphState object with: 
    user requirement string
    config
    LLM service instance
    mesh fields
    error tracking fields
    loop counters
    reference info, etc.
This state is what every node reads and writes.
"""


def initialize_state(user_requirement: str, config: Config, custom_mesh_path: Optional[str] = None) -> GraphState:

    case_stats = json.load(open(f"{config.database_path}/raw/abaqus_case_stats.json", "r"))


    state = GraphState(
        user_requirement=user_requirement,
        config=config,
        case_dir="./output",
        tutorial="",
        case_name="",
        subtasks=[],
        current_subtask_index=0,
        error_command=None,
        error_content=None,
        loop_count=0,
        file_dependency_flag=True,
        llm_service=LLMService(config),
        # case_stats
        # is a dictionary loaded from a JSON file that contains valid AbaqusAgent metadata values
        # (domains, categories, materials).
        # It is used to constrain LLM outputs when parsing the user requirement
        # into a structured case description.
        ###################################
        case_stats=case_stats,
        ###################################
        tutorial_reference=None,
        case_path_reference=None,
        dir_structure_reference=None,
        case_info=None,
        allrun_reference=None,
        dir_structure=None,
        commands=None,
        foamfiles=None,
        error_logs=None,
        history_text=None,
        case_domain=None,
        case_category=None,
        case_material=None,
        mesh_info=None,
        mesh_commands=None,
        custom_mesh_used=None,
        mesh_type=None,
        custom_mesh_path=custom_mesh_path,
        review_analysis=None,
        input_writer_mode="initial",
        job_id=None,
        cluster_info=None,
        slurm_script_path=None,
        # interpreter-related fields
        original_user_requirement = None,
        interpreted_prompt = None,
        missing_items = [],
        missing_required_info = False,
        interpreter_feedback = None,


    )
    if custom_mesh_path:
        print(f"Custom mesh path: {custom_mesh_path}")
    else:
        print("No custom mesh path provided.")
    return state


def main(user_requirement: str, config: Config, custom_mesh_path: Optional[str] = None):
    """Main function to run the Abaqus workflow."""

    # Create and compile the graph
    workflow = create_abaqus_agent_graph()
    app = workflow.compile()

    # Initialize the state
    initial_state = initialize_state(user_requirement, config, custom_mesh_path)

    print("Starting Abaqus-Agent...")

    # Invoke the graph
    try:
        start_time = time.time()

        result = app.invoke(initial_state, config={"recursion_limit": 100})

        if result.get("missing_required_info", False):
            end_time = time.time()
            total_seconds = end_time - start_time
            total_minutes = total_seconds / 60

            print("\n" + "=" * 80)
            print(result.get("interpreter_feedback", "Simulation failed due to insufficient user prompt."))
            print("=" * 80)
            print(f"Total workflow time before stop: {total_seconds:.2f} seconds")
            print(f"Total workflow time before stop: {total_minutes:.2f} minutes")
            return

        end_time = time.time()
        total_seconds = end_time - start_time
        total_minutes = total_seconds / 60

        print("Workflow completed successfully!")
        print(f"Total workflow time: {total_seconds:.2f} seconds")
        print(f"Total workflow time: {total_minutes:.2f} minutes")

        if result.get("llm_service"):
            result["llm_service"].print_statistics()

    except Exception as e:
        end_time = time.time()
        total_seconds = end_time - start_time
        total_minutes = total_seconds / 60

        print(f"Workflow failed with error: {e}")
        print(f"Total workflow time before failure: {total_seconds:.2f} seconds")
        print(f"Total workflow time before failure: {total_minutes:.2f} minutes")
        raise

if __name__ == "__main__":
    # python main.py
    parser = argparse.ArgumentParser(
        description="Run the Abaqus workflow")
    parser.add_argument(
        "--prompt_path",
        type=str,
        default=f"{Path(__file__).parent.parent}/user_requirement.txt",
        help="User requirement file path for the workflow.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="",
        help="Output directory for the workflow.",
    )
    parser.add_argument(
        "--custom_mesh_path",
        type=str,
        default=None,
        help="Path to custom mesh file (e.g., .msh, .stl, .obj). If not provided, no custom mesh will be used.",
    )

    args = parser.parse_args()
    print(f"args: {args}")

    # Initialize configuration.
    config = Config()  # This is defined in src/config.py
    if args.output_dir != "":
        config.case_dir = args.output_dir

    with open(args.prompt_path, "r", encoding="utf-8", errors="replace") as f:
        user_requirement = f.read()


    main(user_requirement, config, args.custom_mesh_path)
