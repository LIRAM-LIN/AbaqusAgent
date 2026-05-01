import os
import subprocess
import sys
import argparse
import shlex
#from dotenv import load_dotenv
from dotenv import load_dotenv
from pathlib import Path
#load the API code here
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path, override=True)

def parse_args():
    """
    # Purpose: Defines and parses the CLI arguments for the benchmark runner.
    #
    # Arguments:
    #
    # --abaqus_path(required) → expected abaqus installation root(WM_PROJECT_DIR)
    # --output(required) → output directory for results
    # --prompt_path(required) → user requirement text file
    # --custom_mesh_path(optional) → custom mesh file for the case
    #
    # Returns: argparse.Namespace
    """
    parser = argparse.ArgumentParser(description="Benchmark Workflow Interface")
    parser.add_argument(
        '--output',
        type=str,
        required=None,
        help="Base output directory for benchmark results"
    )
    parser.add_argument(
        '--prompt_path',
        type=str,
        required=None,
        help="User requirement file path for the benchmark"
    )
    parser.add_argument(
        '--custom_mesh_path',
        type=str,
        default=None,
        help="Path to custom mesh file (e.g., .msh, .stl, .obj). If not provided, no custom mesh will be used."
    )
    return parser.parse_args()


def run_command(command_str):
    """
    Execute a command string using the current terminal's input/output,
    with the working directory set to the directory of the current file.

    Parameters:
        command_str (str): The command to execute, e.g. "python main.py --output_dir xxxx"
                           or "bash xxxxx.sh".
    """
    # Split the command string into a list of arguments
    args = shlex.split(command_str)
    # Set the working directory to the directory of the current file
    cwd = os.path.dirname(os.path.abspath(__file__))

    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
            stdin=sys.stdin
        )
        print(f"Finished command: Return Code {result.returncode}")
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        sys.exit(e.returncode)


def main():
    """Purpose: End‑to‑end orchestrator for the benchmark workflow."""
    """
    Step‑by‑step:
    Parse CLI args (parse_args()).
    Validate environment: checks OPENAI_API_KEY exists.
    Create output directory if needed.
    Prepare preprocessing script list:
    If tutorial/FAISS artifacts don’t exist, it schedules scripts to generate them.
    Build and append main workflow command:
    python src/main.py --prompt_path ... --output_dir ...
    Adds --custom_mesh_path if provided.
    Run all scripts in order using run_command(...).
    """
    args = parse_args()
    args.output='./output'
    args.prompt_path = './user_requirement.txt'
    args.custom_mesh_path = None

    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not anthropic_api_key:
        print("Error: ANTHROPIC_API_KEY is not set in the environment.")
        sys.exit(1)

    # Optional
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_api_key:
        os.environ["OPENAI_API_KEY"] = openai_api_key

    # ensure child processes get the cleaned version
    os.environ["OPENAI_API_KEY"] = openai_api_key

    # Create the output folder
    os.makedirs(args.output, exist_ok=True)

    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"script_dir: {script_dir}")

    SCRIPTS = []
    """
       Preprocessing commands (only if needed): 
       Tutorial parsing
       FAISS index building for tutorial details
       The main workflow command:
    """

    # Preprocess the AbaqusAgent tutorials
    """
        AbaqusAgent relies on FAISS databases for retrieval (RAG).
        These must be generated before the workflow runs.
        So faiss_tutorials_structure checks if they already exist and only regenerates them when necessary.
    """

    main_cmd = f'"{sys.executable}" src/main.py --prompt_path="{args.prompt_path}" --output_dir="{args.output}"'
    if args.custom_mesh_path:
        main_cmd += f' --custom_mesh_path="{args.custom_mesh_path}"'

    print(f"Main workflow command: {main_cmd}")
    # Main workflow
    SCRIPTS.extend([
        main_cmd
    ])

    print("Starting workflow...")
    for script in SCRIPTS:
        run_command(script)
    print("Workflow completed successfully.")


if __name__ == "__main__":
    main()
