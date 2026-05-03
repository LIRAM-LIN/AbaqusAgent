#localEnv.VariableUsed
import os
import re
import argparse
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

from langchain_community.vectorstores import FAISS
from langchain_openai.embeddings import OpenAIEmbeddings
from langchain_core.documents import Document

"""
This script builds a FAISS vector index from the raw detailed tutorial contents 
so Foam‑Agent can retrieve similar cases during RAG.
It reads:
    database/raw/AbaqusAgent_tutorials_details.txt
and writes a FAISS index to:
    database/faiss/AbaqusAgent_tutorials_details
"""

# Function to extract specific fields from text
def extract_field(field_name: str, text: str) -> str:
    """Extracts the specified field from the given text."""
    match = re.search(fr"{field_name}:\s*(.*)", text)
    return match.group(1).strip() if match else "Unknown"

def tokenize(text: str) -> str:
    # Replace underscores with spaces
    text = text.replace('_', ' ')
    # Insert a space between a lowercase letter and an uppercase letter (global match)
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    return text.lower()

def main():
   # Step 1: Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Process AbaqusAgent case data and store embeddings in FAISS."
    )
    parser.add_argument(
        "--database_path",
        type=str,
        default=r"database\script\database",  # Default database path; change this if your database is stored elsewhere.
        help="Path to the database directory (default: '../../')",
    )
        
    args = parser.parse_args()
    database_path = args.database_path
    print(f"Database path: {database_path}")
        
    # Step 2: Read the input file
    database_allrun_path = os.path.join(database_path + "/AbaqusAgent_tutorials_details.txt")
    if not os.path.exists(database_allrun_path):
        raise FileNotFoundError(f"File not found: {database_allrun_path}")

    with open(database_allrun_path, "r", encoding="utf-8") as file:
        file_content = file.read()

    # Step 3: Extract `<case_begin> ... </case_end>` segments using regex
    pattern = re.compile(r"<case_begin>(.*?)</case_end>", re.DOTALL)
    matches = pattern.findall(file_content)

    if not matches:
        raise ValueError("No cases found in the input file. Please check the file content.")

    documents = []

    for match in matches:
        full_content = match.strip()  # Store the complete case

        index_match = re.search(r"<index>(.*?)</index>", match, re.DOTALL)
        if not index_match:
            raise ValueError("Missing <index> block in a case.")
        index_content = index_match.group(1).strip()  # Extract `<index>` content
        index = index_match.group(0) # include the tags for indexing
        
        # Extract metadata fields
        """For each case block it extracts:
            <index> metadata (name/domain)
            <file_content> (full Abaqus case data)
        """
        content_match = re.search(r"<file_content>(.*?)</file_content>", match, re.DOTALL)
        file_content_block = content_match.group(1).strip() if content_match else ""
        # Extract input_file inside file_content
        input_match = re.search(r"<input_file>(.*?)</input_file>", file_content_block, re.DOTALL | re.IGNORECASE)
        input_block = input_match.group(1).strip() if input_match else ""

        case_name = extract_field("case name", index_content)
        case_domain = extract_field("case domain", index_content)
        # Create a Document instance
        documents.append(Document(
            page_content=tokenize(index + '\n' + file_content_block+ '\n' + input_block),
            metadata={
                "full_content": full_content,  # Store full `<case_begin> ... </case_end>`
                "case_name": case_name,
                "case_domain": case_domain
            }
        ))

    # Step 4: Compute embeddings and store them in FAISS

    BASE_DIR = Path(__file__).resolve().parent.parent
    load_dotenv(BASE_DIR / ".env") # Default database path; change this if your database is stored elsewhere.

    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "").strip()
    if not os.environ["OPENAI_API_KEY"]:
        raise RuntimeError("OPENAI_API_KEY missing (after loading .env)")
    embedding_model = OpenAIEmbeddings(model="text-embedding-3-small")
    vectordb = FAISS.from_documents(documents, embedding_model)

    # Step 5: Save FAISS index locally
    persist_directory = os.path.join(database_path, "faiss/Abaqusagent_tutorials_details")
    vectordb.save_local(persist_directory)

    print(f"{len(documents)} cases indexed successfully with metadata! Saved at: {persist_directory}")

if __name__ == "__main__":
    main()
    