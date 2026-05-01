# config.py
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    max_loop: int = 15


    batchsize: int = 10
    searchdocs: int = 15
    run_times: int = 1  # current run number (for directory naming)
    database_path: str = Path(__file__).resolve().parent.parent / "database"
    run_directory: str = Path(__file__).resolve().parent.parent / "runs"
    case_dir: str = ""
    max_time_limit: int = 3600  # Max time limit after which the openfoam run will be terminated, in seconds
    file_dependency_threshold: int = 3000  # threshold length on the similar case; see `nodes/architect_node.py` for details
    #model_provider: str = "openai"  # [openai, ollama, bedrock] #modify here
    # # #model_version should be in ["gpt-4o", "deepseek-r1:32b-qwen-distill-fp16", "qwen2.5:32b-instruct"]
    #model_version: str = "gpt-5.2" #modify here
    # # # # model_version: str = "gpt-4o"
    #temperature: float = 0.0

    # #modify here
    model_provider: str =  "anthropic" # [openai, ollama, bedrock] #modify here
    # # # # # model_version should be in ["gpt-4o", "deepseek-r1:32b-qwen-distill-fp16", "qwen2.5:32b-instruct"]
    model_version: str = "claude-opus-4-6" #modify here
    # # # # # model_version: str = "gpt-4o"
    temperature: float = 0.0

