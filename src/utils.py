# utils.py
import re
import subprocess
import os
from typing import Optional, Any, Type, TypedDict, List
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model
from langchain_community.vectorstores import FAISS
from langchain_openai.embeddings import OpenAIEmbeddings
from langchain_aws import ChatBedrock, ChatBedrockConverse
from langchain_anthropic import ChatAnthropic
from pathlib import Path
#import tracking_aws
import requests
import time
import random
from botocore.exceptions import ClientError
import shutil
from config import Config
from langchain_ollama import ChatOllama
from anthropic import Anthropic
from langchain_core.messages import SystemMessage, HumanMessage
# Global dictionary to store loaded FAISS databases
"""
The module loads multiple FAISS indices from database/faiss into a global cache:
    AbaqusAgent_tutorials_details
These are stored in FAISS_DB_CACHE and used by retrieve_faiss(...) to return similar docs for a given query.
"""
FAISS_DB_CACHE = {}
DATABASE_DIR = f"{Path(__file__).resolve().parent.parent}/database/script/database/faiss"

FAISS_DB_CACHE = {
    "AbaqusAgent_tutorials_details": FAISS.load_local(f"{DATABASE_DIR}/AbaqusAgent_tutorials_details",
                                                      OpenAIEmbeddings(model="text-embedding-3-small"),
                                                      allow_dangerous_deserialization=True)
}

"""
    The file defines Pydantic schemas used when writing Abaqus files:
        AbaqusfilePydantic
        AbaqusPydantic
        ResponseWithThinkPydantic
    These are used to structure LLM outputs and enforce field types.
"""


class AbaqusfilePydantic(BaseModel):
    file_name: str = Field(description="Name of the Abaqus input file")
    folder_name: str = Field(description="Folder where the Abaqusfile should be stored")
    content: str = Field(description="Content of the Abaqus file, written in AbaqusAgent dictionary format")


class AbaqusPydantic(BaseModel):
    list_Abaqusfile: List[AbaqusfilePydantic] = Field(
        default_factory=list,
        description="List of AbaqusAgent configuration files"
    )

class ResponseWithThinkPydantic(BaseModel):
    think: str = Field(description="Thought process of the LLM")
    response: str = Field(description="Response of the LLM")


class LLMService:
    def __init__(self, config: object):
        self.model_version = getattr(config, "model_version", "gpt-4o")
        self.temperature = getattr(config, "temperature", 0)
        self.model_provider = getattr(config, "model_provider", "openai")
        print("LLM Provider Loaded:", self.model_provider) #modify here
        print("Model Version:", self.model_version) #modify here

        # Initialize statistics
        self.total_calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.failed_calls = 0
        self.retry_count = 0

        # Initialize the LLM
        if self.model_provider.lower() == "bedrock":
            bedrock_runtime = tracking_aws.new_default_client()
            self.llm = ChatBedrockConverse(
                client=bedrock_runtime,
                model_id=self.model_version,
                temperature=self.temperature,
                max_tokens=8192
            )
        elif self.model_provider.lower() == "anthropic":
            if not os.getenv("ANTHROPIC_API_KEY", "").strip():
                raise EnvironmentError("ANTHROPIC_API_KEY is not set in the environment.")

            # Create direct Anthropic client (for accurate token usage)
            self._anthropic_client = Anthropic(
                api_key=os.environ["ANTHROPIC_API_KEY"]
            )

            self.llm = ChatAnthropic(
                model=self.model_version,
                temperature=self.temperature,
                max_tokens=8192
            )
        elif self.model_provider.lower() == "openai":
            self.llm = init_chat_model(
                self.model_version,
                model_provider=self.model_provider,
                temperature=self.temperature
            )
        elif self.model_provider.lower() == "ollama":
            try:
                response = requests.get("http://localhost:11434/api/version", timeout=2)
                # If request successful, service is running
            except requests.exceptions.RequestException:
                print("Ollama is not running, starting it...")
                subprocess.Popen(["ollama", "serve"],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
                # Wait for service to start
                time.sleep(5)  # Give it 3 seconds to initialize

            self.llm = ChatOllama(
                model=self.model_version,
                temperature=self.temperature,
                num_predict=-1,
                num_ctx=131072,
                base_url="http://localhost:11434"
            )
        else:
            raise ValueError(f"{self.model_provider} is not a supported model_provider")

    from typing import Optional, Type, Any
    from pydantic import BaseModel
    from langchain_core.messages import SystemMessage, HumanMessage

    def invoke(self,
               user_prompt: str,
               system_prompt: Optional[str] = None,
               pydantic_obj: Optional[Type[BaseModel]] = None,
               max_retries: int = 10) -> Any:
        """
        Invoke the LLM with the given prompts and return the response.
        Tracks token usage. For Anthropic, uses native token counting.
        """
        self.total_calls += 1

        # Build messages (LangChain format)
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=user_prompt))

        # ---- Prompt token counting ----
        # Avoid LangChain GPT-2 fallback. Use Anthropic native counting if available.
        prompt_tokens = 0
        if self.model_provider.lower() == "anthropic" and hasattr(self, "_anthropic_client"):
            try:
                # Anthropic expects "messages" as role/content.
                # System prompt is passed separately as "system".
                system_text = system_prompt or ""
                anthropic_messages = [{"role": "user", "content": user_prompt}]
                token_info = self._anthropic_client.messages.count_tokens(
                    model=self.model_version,
                    system=system_text,
                    messages=anthropic_messages
                )
                prompt_tokens = int(getattr(token_info, "input_tokens", 0))
            except Exception:
                prompt_tokens = 0  # fall back to 0 if counting fails
        else:
            prompt_tokens = 0  # skip counting for non-anthropic to avoid GPT-2 fallback warnings

        retry_count = 0
        while True:
            try:
                # Force output token limit at invoke time (more reliable for tool/structured calls)
                invoke_cfg = {"max_tokens": getattr(self, "max_tokens", 8192)}

                if pydantic_obj:
                    structured_llm = self.llm.with_structured_output(pydantic_obj)
                    response = structured_llm.invoke(messages, config=invoke_cfg)
                else:
                    if self.model_version.startswith("deepseek"):
                        structured_llm = self.llm.with_structured_output(ResponseWithThinkPydantic)
                        response = structured_llm.invoke(messages, config=invoke_cfg)
                        response = response.response
                    else:
                        response = self.llm.invoke(messages, config=invoke_cfg)
                        response = response.content

                # ---- Completion token counting ----
                completion_tokens = 0
                if self.model_provider.lower() == "anthropic" and hasattr(self, "_anthropic_client"):
                    try:
                        # Count tokens of assistant output using Anthropic counter.
                        # This is an approximation of output tokens (good for stats).
                        token_info_out = self._anthropic_client.messages.count_tokens(
                            model=self.model_version,
                            messages=[{"role": "assistant", "content": str(response)}]
                        )
                        completion_tokens = int(getattr(token_info_out, "input_tokens", 0))
                    except Exception:
                        completion_tokens = 0

                total_tokens = prompt_tokens + completion_tokens

                # Update statistics
                self.total_prompt_tokens += prompt_tokens
                self.total_completion_tokens += completion_tokens
                self.total_tokens += total_tokens

                return response

            except ClientError as e:
                if e.response['Error']['Code'] in ['Throttling', 'TooManyRequestsException']:
                    retry_count += 1
                    self.retry_count += 1

                    if retry_count > max_retries:
                        self.failed_calls += 1
                        raise Exception(f"Maximum retries ({max_retries}) exceeded: {str(e)}")

                    base_delay = 1.0
                    max_delay = 60.0
                    delay = min(max_delay, base_delay * (2 ** (retry_count - 1)))
                    jitter = random.uniform(0, 0.1 * delay)
                    sleep_time = delay + jitter

                    print(
                        f"ThrottlingException occurred: {str(e)}. Retrying in {sleep_time:.2f} seconds "
                        f"(attempt {retry_count}/{max_retries})"
                    )
                    time.sleep(sleep_time)
                else:
                    self.failed_calls += 1
                    raise e

            except Exception as e:
                self.failed_calls += 1
                raise e

    def get_statistics(self) -> dict:
        """
        Get the current statistics of the LLM service.

        Returns:
            Dictionary containing various statistics
        """
        return {
            "total_calls": self.total_calls,
            "failed_calls": self.failed_calls,
            "retry_count": self.retry_count,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "average_prompt_tokens": self.total_prompt_tokens / self.total_calls if self.total_calls > 0 else 0,
            "average_completion_tokens": self.total_completion_tokens / self.total_calls if self.total_calls > 0 else 0,
            "average_tokens": self.total_tokens / self.total_calls if self.total_calls > 0 else 0
        }

    def print_statistics(self) -> None:
        """
        Print the current statistics of the LLM service.
        """
        stats = self.get_statistics()
        print("\n<LLM Service Statistics>")
        print(f"Total calls: {stats['total_calls']}")
        print(f"Failed calls: {stats['failed_calls']}")
        print(f"Total retries: {stats['retry_count']}")
        print(f"Total prompt tokens: {stats['total_prompt_tokens']}")
        print(f"Total completion tokens: {stats['total_completion_tokens']}")
        print(f"Total tokens: {stats['total_tokens']}")
        print(f"Average prompt tokens per call: {stats['average_prompt_tokens']:.2f}")
        print(f"Average completion tokens per call: {stats['average_completion_tokens']:.2f}")
        print(f"Average tokens per call: {stats['average_tokens']:.2f}\n")
        print("</LLM Service Statistics>")


class GraphState(TypedDict):
    user_requirement: str
    config: Config
    case_dir: str
    tutorial: str
    case_name: str
    subtasks: List[dict]
    current_subtask_index: int
    error_command: Optional[str]
    error_content: Optional[str]
    loop_count: int
    file_dependency_flag: bool
    # Additional state fields that will be added during execution
    llm_service: Optional['LLMService']
    case_stats: Optional[dict]
    tutorial_reference: Optional[str]
    case_path_reference: Optional[str]
    dir_structure_reference: Optional[str]
    case_info: Optional[str]
    allrun_reference: Optional[str]
    dir_structure: Optional[dict]
    commands: Optional[List[str]]
    Abaqusfiles: Optional[dict]
    error_logs: Optional[List[str]]
    history_text: Optional[List[str]]
    case_domain: Optional[str]
    case_category: Optional[str]
    case_material: Optional[str]
    # Mesh-related state fields
    mesh_info: Optional[dict]
    mesh_commands: Optional[List[str]]
    custom_mesh_used: Optional[bool]
    mesh_type: Optional[str]
    custom_mesh_path: Optional[str]
    # Review and rewrite related fields
    review_analysis: Optional[str]
    input_writer_mode: Optional[str]
    # HPC-related fields
    job_id: Optional[str]
    cluster_info: Optional[dict]
    slurm_script_path: Optional[str]


def tokenize(text: str) -> str:
    """
    tokenize(text: str) -> str is a simple normalization helper used before FAISS retrieval. It:
        Replaces underscores with spaces
        Inserts spaces between lower→upper camel-case boundaries
        Lowercases the final string
    So "MyCase_Name" becomes "my case name".
    """
    # Replace underscores with spaces
    text = text.replace('_', ' ')
    # Insert a space between a lowercase letter and an uppercase letter (global match)
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    return text.lower()


#####################################################################################
#####################################################################################
"""
    Basic helpers for file and directory operations:
        save_file(path, content)
        read_file(path)
        list_case_files(case_dir)
        remove_files(directory, prefix)
        remove_file(path)
        remove_numeric_folders(case_dir)
    These support node/service logic for writing AbaqusAgent inputs, cleaning cases, etc.
"""


def save_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', errors='replace') as f:
        f.write(content)
    print(f"Saved file at {path}")


def read_file(path: str) -> str:
    if os.path.exists(path):
        with open(path, 'r') as f:
            return f.read()
    return ""


def list_case_files(case_dir: str) -> str:
    files = [f for f in os.listdir(case_dir) if os.path.isfile(os.path.join(case_dir, f))]
    return ", ".join(files)


def remove_files(directory: str, prefix: str) -> None:
    for file in os.listdir(directory):
        if file.startswith(prefix):
            os.remove(os.path.join(directory, file))
    print(f"Removed files with prefix '{prefix}' in {directory}")


def remove_file(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)
        print(f"Removed file {path}")


def remove_numeric_folders(case_dir: str) -> None:
    """
    Remove all folders in case_dir that represent numeric values, including those with decimal points,
    except for the "0" folder.

    Args:
        case_dir (str): The directory path to process
    """
    for item in os.listdir(case_dir):
        item_path = os.path.join(case_dir, item)
        if os.path.isdir(item_path) and item != "0":
            try:
                # Try to convert to float to check if it's a numeric value
                float(item)
                # If conversion succeeds, it's a numeric folder
                try:
                    shutil.rmtree(item_path)
                    print(f"Removed numeric folder: {item_path}")
                except Exception as e:
                    print(f"Error removing folder {item_path}: {str(e)}")
            except ValueError:
                # Not a numeric value, so we keep this folder
                pass


"""Core helpers for running AbaqusAgent and parsing logs:
    run_command(script_path, out_file, err_file, working_dir, config)
        → Executes Allrun by sourcing AbaqusAgent env (WM_PROJECT_DIR/etc/bashrc)
    check_Abaqus_errors(directory)
        → Scans log* files for ERROR: blocks
    extract_commands_from_allrun_out(out_file)
        → Extracts “Running <command>” lines from Allrun output
"""


def run_command(script_path: str, out_file: str, err_file: str, working_dir: str, config: Config) -> None:
    print(f"Executing script {script_path} in {working_dir}")
    os.chmod(script_path, 0o777)
    #AbaqusAgent_dir = os.getenv("WM_PROJECT_DIR")
    command = f"abaqus job=AbaqusInput input={os.getcwd()+script_path} int"
    timeout_seconds = config.max_time_limit

    with open(out_file, 'w') as out, open(err_file, 'w') as err:
        process = subprocess.Popen(
            command,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            shell=True
        )

        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            out.write(stdout)
            err.write(stderr)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            timeout_message = (
                "Abaqus execution took too long. "
                "This case, if set up right, does not require such large execution times.\n"
            )
            out.write(timeout_message + stdout)
            err.write(timeout_message + stderr)
            print(f"Execution timed out: {script_path}")

    print(f"Executed script {script_path}")


def check_Abaqus_errors(directory: str) -> list:
    error_logs = []
    # DOTALL mode allows '.' to match newline characters
    pattern = re.compile(r"ERROR:(.*)", re.DOTALL)

    for file in os.listdir(directory):
        if file.startswith("log"):
            filepath = os.path.join(directory, file)
            with open(filepath, 'r') as f:
                content = f.read()

            match = pattern.search(content)
            if match:
                error_content = match.group(0).strip()
                error_logs.append({"file": file, "error_content": error_content})
            elif "error" in content.lower():
                print(f"Warning: file {file} contains 'error' but does not match expected format.")
        elif file.endswith(".dat"):
            dat_path = os.path.join(directory, file)
            error_blocks = extract_error_blocks_from_dat(dat_path)
            if error_blocks:
                error_file_path = write_error_file(dat_path, error_blocks)
                for block in error_blocks:
                    error_logs.append({
                        "file": file,
                        "error_content": block,
                        "error_file": error_file_path,
                    })
    return error_logs

def extract_error_blocks_from_dat(dat_path: str) -> list:
    error_blocks = []
    if not os.path.exists(dat_path):
        return error_blocks

    with open(dat_path, "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()

    current_block = []
    capturing = False
    for line in lines:
        if "***ERROR" in line:
            capturing = True

        if capturing:
            if line.strip() == "" or (line.lstrip().startswith("***") and "***ERROR" not in line):
                if current_block:
                    error_blocks.append("".join(current_block).rstrip())
                break
            current_block.append(line)

    if current_block and not error_blocks:
        error_blocks.append("".join(current_block).rstrip())

    return error_blocks


def write_error_file(dat_path: str, error_blocks: list) -> str:
    error_path = str(Path(dat_path).with_suffix(".error"))
    with open(error_path, "w", encoding="utf-8") as handle:
        for index, block in enumerate(error_blocks, start=1):
            handle.write(block)
            if index != len(error_blocks):
                handle.write("\n\n")
    return error_path


def extract_commands_from_allrun_out(out_file: str) -> list:
    commands = []
    if not os.path.exists(out_file):
        return commands
    with open(out_file, 'r') as f:
        for line in f:
            if line.startswith("Running "):
                parts = line.split(" ")
                if len(parts) > 1:
                    commands.append(parts[1].strip())
    return commands

"""
    Helpers to parse LLM outputs and AbaqusAgent context:
        parse_case_name(...)
        split_subtasks(...)
        parse_context(...)
        parse_file_name(...), parse_folder_name(...)
        parse_directory_structure(...)
    These functions help standardize and interpret LLM-generated text.
"""

"""
    Function	Used?	Where
        parse_case_name	❌ No	Defined only in src/utils.py
        split_subtasks	❌ No	Defined only in src/utils.py
        parse_context	✅ Yes	src/services/files.py
        parse_file_name	❌ No	Defined only in src/utils.py
        parse_folder_name	❌ No	Defined only in src/utils.py
        parse_directory_structure	✅ Yes	src/services/architect.py
"""


def parse_context(text: str) -> str:
    match = re.search(r'AbaqusFile\s*\{.*?(?=```|$)', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(0).strip()

    print("Warning: Could not parse context; returning original text.")
    return text


def parse_directory_structure(data: str) -> dict:
    """
    Parses the directory structure string and returns a dictionary where:
      - Keys: directory names
      - Values: count of files in that directory.
    """
    directory_file_counts = {}

    # Find all <dir>...</dir> blocks in the input string.
    dir_blocks = re.findall(r'<dir>(.*?)</dir>', data, re.DOTALL)

    for block in dir_blocks:
        # Extract the directory name (everything after "directory name:" until the first period)
        dir_name_match = re.search(r'directory name:\s*(.*?)\.', block)
        # Extract the list of file names within square brackets
        files_match = re.search(r'File names in this directory:\s*\[(.*?)\]', block)

        if dir_name_match and files_match:
            dir_name = dir_name_match.group(1).strip()
            files_str = files_match.group(1)
            # Split the file names by comma, removing any surrounding whitespace
            file_list = [filename.strip() for filename in files_str.split(',')]
            directory_file_counts[dir_name] = len(file_list)

    return directory_file_counts



def find_similar_file(description: str, tutorial: str) -> str:
    start_pos = tutorial.find(description)
    if start_pos == -1:
        return "None"
    end_marker = "input_file_end."
    end_pos = tutorial.find(end_marker, start_pos)
    if end_pos == -1:
        return "None"
    return tutorial[start_pos:end_pos + len(end_marker)]


def read_commands(file_path: str) -> str:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Commands file not found: {file_path}")
    with open(file_path, 'r') as f:
        # join non-empty lines with a comma
        return ", ".join(line.strip() for line in f if line.strip())


def find_input_file(case_dir: str, command: str) -> str:
    for root, _, files in os.walk(case_dir):
        for file in files:
            if command in file:
                return os.path.join(root, file)
    return ""


def _extract_field_from_text(text: str, field_name: str) -> str:
    pattern = rf"{field_name}\s*:\s*(.+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return "unknown"

def retrieve_faiss(database_name: str, query: str, topk: int = 1) -> dict:
    """
    performs RAG-style retrieval from a preloaded FAISS vector index. It:
        Normalizes the query (via tokenize).
        Runs similarity search against the requested FAISS index
        Formats results into a structured list depending on the database type.
    It is the core helper used by nodes to fetch AbaqusAgent references (tutorials, scripts, command help) for LLM
    grounding.retrieve_faiss is the central retrieval hook for Abaqus-Agent’s RAG pipeline: it normalizes a query,
    searches FAISS, and returns structured metadata to guide LLM responses.
    USED:
        architect.py
    """

    if database_name not in FAISS_DB_CACHE:
        raise ValueError(f"Database '{database_name}' is not loaded.")

    # Tokenize the query
    query = tokenize(query)

    vectordb = FAISS_DB_CACHE[database_name]
    docs = vectordb.similarity_search(query, k=topk)
    if not docs:
        raise ValueError(f"No documents found for query: {query}")

    formatted_results = []
    for doc in docs:
        metadata = doc.metadata or {}

        if database_name == "AbaqusAgent_tutorials_details":
            full_content = metadata.get("full_content", doc.page_content)

            case_name = metadata.get("case_name", "unknown")
            case_domain = metadata.get("case_domain", "unknown")
            case_category = metadata.get("case_category", "unknown")
            case_material = metadata.get("case_material", "unknown")

            if case_name == "unknown":
                case_name = _extract_field_from_text(full_content, "case name")

            if case_domain == "unknown":
                case_domain = _extract_field_from_text(full_content, "case domain")

            if case_category == "unknown":
                case_category = _extract_field_from_text(full_content, "case category")

            if case_material == "unknown":
                case_material = _extract_field_from_text(full_content, "case material")

            formatted_results.append({
                "index": doc.page_content,
                "full_content": full_content,
                "case_name": case_name,
                "case_domain": case_domain,
                "case_category": case_category,
                "case_material": case_material,
                "dir_structure": metadata.get("dir_structure", "unknown"),
                "tutorials": metadata.get("tutorials", "N/A")
            })
        else:
            raise ValueError(f"Unknown database name: {database_name}")

    return formatted_results



