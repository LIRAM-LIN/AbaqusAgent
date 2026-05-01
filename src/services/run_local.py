import os
from typing import List
from models import RunIn, RunOut
from utils import remove_files, remove_file, remove_numeric_folders, run_command, check_Abaqus_errors

"""
This module provides the local execution services for Abaqus cases:
    run the Allrun script
    collect error logs
    return a run status
"""

def run_allrun_and_collect_errors(case_dir: str, config) -> List[str]:
    """Execute Allrun in case_dir and return parsed error logs (list)."""
    allrun_file_path = os.path.join(case_dir, "AbaqusInput.inp")
    out_file = os.path.join(case_dir, "AbaqusInput.out")
    err_file = os.path.join(case_dir, "AbaqusInput.err")
    abaqus_error_file=os.path.join(case_dir, "AbaqusInput.error")

    # Cleanup
    remove_files(case_dir, prefix="log")
    remove_file(err_file)
    remove_file(out_file)
    remove_file(abaqus_error_file)
    remove_numeric_folders(case_dir)

    # Run
    run_command(allrun_file_path, out_file, err_file, case_dir, config)

    # Inspect
    error_logs = check_Abaqus_errors(case_dir)
    return error_logs


def run_simulation_local(inp: RunIn, config, case_dir: str) -> RunOut:
    errors = run_allrun_and_collect_errors(case_dir, config)
    status = "completed" if len(errors) == 0 else "failed"
    return RunOut(job_id=None, status=status)


