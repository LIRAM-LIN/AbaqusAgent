import os
import time
import subprocess
from pathlib import Path
from typing import Dict, Any


def safe_remove(path: str):
    try:
        if os.path.isfile(path):
            os.remove(path)
            print(f"[visualization_node] removed old file: {path}")
    except Exception as e:
        print(f"[visualization_node] warning: could not remove {path}: {e}")


def visualization_node(state: Dict[str, Any]) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("[visualization_node] ENTERED")
    print("=" * 80)
    print(f"[visualization_node] state keys = {list(state.keys())}")
    print(f"[visualization_node] state case_dir = {state.get('case_dir')}")
    print(f"[visualization_node] state error_content = {state.get('error_content')}")
    print(f"[visualization_node] state error_logs = {state.get('error_logs')}")

    output_dir = state.get("case_dir", "").strip()
    if not output_dir:
        state["visualization_success"] = False
        state["visualization_error"] = "case_dir not found in state."
        print("[visualization_node] ERROR: case_dir missing")
        return state

    output_dir = os.path.abspath(output_dir)
    print(f"[visualization_node] absolute output_dir = {output_dir}")

    odb_path = os.path.join(output_dir, "AbaqusInput.odb")
    print(f"[visualization_node] checking ODB at: {odb_path}")

    if not os.path.isfile(odb_path):
        state["visualization_success"] = False
        state["visualization_error"] = f"ODB file not found: {odb_path}"
        print("[visualization_node] ERROR: ODB not found")
        return state

    post_dir = os.path.join(output_dir, "postprocess")
    os.makedirs(post_dir, exist_ok=True)
    print(f"[visualization_node] postprocess dir = {post_dir}")

    script_path = Path(__file__).resolve().parents[1] / "services" / "visualization.py"
    print(f"[visualization_node] visualization script path = {script_path}")

    if not script_path.is_file():
        state["visualization_success"] = False
        state["visualization_error"] = f"Visualization script not found: {script_path}"
        print("[visualization_node] ERROR: visualization.py not found")
        return state

    start_file = os.path.join(post_dir, "visualization_started.txt")
    done_file = os.path.join(post_dir, "visualization_done.txt")
    error_file = os.path.join(post_dir, "visualization_error.txt")
    log_file = os.path.join(post_dir, "visualization_log.txt")
    disp_csv = os.path.join(post_dir, "displacement_nodal_data.csv")
    png_mag = os.path.join(post_dir, "displacement_magnitude.png")
    png_u1 = os.path.join(post_dir, "displacement_U1.png")
    png_u2 = os.path.join(post_dir, "displacement_U2.png")
    png_u3 = os.path.join(post_dir, "displacement_U3.png")

    # remove old artifacts first
    print("[visualization_node] cleaning old artifacts...")

    for f in [start_file, done_file, error_file, log_file, disp_csv, png_mag, png_u1, png_u2, png_u3]:
        safe_remove(f)

    env = os.environ.copy()
    env["ABAQUS_ODB_PATH"] = odb_path
    env["ABAQUS_POST_DIR"] = post_dir

    abaqus_cmd = r"C:\SIMULIA\Commands\abaqus.bat"

    cmd = [
        abaqus_cmd,
        "viewer",
        f"script={script_path}"
    ]

    print(f"[visualization_node] launch command = {cmd}")

    try:
        proc = subprocess.Popen(cmd, env=env)
        print(f"[visualization_node] Abaqus Viewer launched successfully, pid = {proc.pid}")
    except Exception as e:
        state["visualization_success"] = False
        state["visualization_error"] = f"Failed to launch Abaqus Viewer: {str(e)}"
        print(f"[visualization_node] ERROR launching Abaqus Viewer: {e}")
        return state

    print(f"[visualization_node] waiting for marker files...")
    print(f"[visualization_node] start_file = {start_file}")
    print(f"[visualization_node] done_file  = {done_file}")
    print(f"[visualization_node] error_file = {error_file}")
    print(f"[visualization_node] log_file   = {log_file}")
    print(f"[visualization_node] disp_csv   = {disp_csv}")

    timeout_seconds = 180
    waited = 0

    while waited < timeout_seconds:
        if os.path.isfile(done_file):
            print(f"[visualization_node] DONE file found after {waited} s")
            break
        if os.path.isfile(error_file):
            print(f"[visualization_node] ERROR file found after {waited} s")
            break
        if waited % 10 == 0:
            print(f"[visualization_node] still waiting... {waited}/{timeout_seconds} s")
        time.sleep(1)
        waited += 1

    artifacts = []
    for f in [start_file, disp_csv, png_mag, png_u1, png_u2, png_u3, done_file, error_file, log_file]:
        if os.path.isfile(f):
            artifacts.append(f)

    print(f"[visualization_node] artifacts found = {artifacts}")

    state["odb_path"] = odb_path
    state["postprocess_dir"] = post_dir
    state["visualization_pid"] = proc.pid
    state["visualization_artifacts"] = artifacts

    if os.path.isfile(done_file):
        state["visualization_success"] = True
        state["visualization_error"] = ""
        print("[visualization_node] SUCCESS: visualization completed")
    elif os.path.isfile(error_file):
        state["visualization_success"] = False
        try:
            with open(error_file, "r", encoding="utf-8", errors="replace") as f:
                state["visualization_error"] = f.read()
        except Exception as e:
            state["visualization_error"] = f"Visualization failed and error file could not be read: {e}"
        print("[visualization_node] FAILURE: visualization_error.txt found")
        print(state["visualization_error"])
    else:
        state["visualization_success"] = False
        state["visualization_error"] = (
            f"Abaqus Viewer launched, but no done/error file was found within {timeout_seconds} seconds."
        )
        print("[visualization_node] FAILURE: timeout reached with no done/error file")

    print("[visualization_node] returning state")
    print("=" * 80 + "\n")
    return state