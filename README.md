# AbaqusAgent

A multi-agent framework for end-to-end finite element analysis (FEA) of solid mechanics problems, enabling automated Abaqus simulation generation, execution, and analysis from natural language descriptions.

---

## Overview

AbaqusAgent automates the complete finite element simulation pipeline starting from a user-defined problem in natural language. The framework integrates multiple specialized agents to perform requirement interpretation, simulation planning, input file generation, execution, iterative error correction, and result visualization.

---

## Architecture

The framework is composed of the following agents:

- **Interpreter Agent:** Parses user requirements and ensures completeness of simulation inputs.
- **Architect Agent:** Designs the simulation workflow and retrieves relevant benchmark cases.
- **Input Writer Agent:** Generates Abaqus `.inp` files based on structured requirements.
- **Runner Agent:** Executes Abaqus simulations and manages job outputs.
- **Reviewer Agent:** Diagnoses errors and iteratively refines the input file.
- **Visualization Agent:** Extracts results from `.odb` files and generates visual outputs.

---

## Features

- End-to-end automation of Abaqus-based FEA workflows  
- Modular multi-agent architecture  
- Automated error detection and correction loop  
- Integration with large language models for reasoning and planning  
- Retrieval-augmented generation using benchmark simulation cases  

---

## Installation

Install the required Python libraries listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

## Requirements:
- Installed Abaqus. Education license of Abaqus is free. 
- Python environment with required libraries

--------------------------------------------------

## Setup Guidelines

1. Save the project on your local computer.

2. Set the required API keys as local environment variables:
   - `ANTHROPIC_API_KEY`
   - `OPENAI_API_KEY`

   These are required for proper execution, as the framework uses both APIs.  
   On Windows, add them under **User Variables** in **Environment Variables**.

   If the user doesn't have both the API keys, some local adjustments are needed to replace the ANTHROPIC_API_KEY to OPENAI_API_KEY or vice versa.

4. Open the project in PyCharm or your preferred IDE, and select **"Trust Project"** when prompted in PyCharm. This ensures that the correct project configuration is used and that the intended `main.py` is executed. Also, make sure all required libraries are installed in the project’s Python environment.

5. Before running a new simulation, check the output folder for any `.lck` file:
   - If an `.odb` file is still open, close it to automatically remove the `.lck` file.
   - If the `.lck` file persists, delete it manually before running a new case.

   The `.lck` file prevents new Abaqus jobs from starting.
   

--------------------------------------------------

## Usage

1. Define the simulation problem in user_requirement.txt, including:
   - Geometry
   - Material properties
   - Boundary conditions
   - Loading conditions
   - Requested outputs

2. Run the main script:

```bash
python AbaqusBench_noArg.py
```

3. The framework will:
   - Generate Abaqus input files
   - Execute simulations
   - Perform iterative error correction
   - Generate Abaqus output files
   - Visualize the simulation results in a separate Abaqus Viewer window.

--------------------------------------------------

## Acknowledgment

This repository builds on an agent skeleton adapted from prior work licensed under the MIT License. The implementation and its application to Abaqus-based simulations have been independently developed.

--------------------------------------------------

## Citation

To be added after paper submission
--------------------------------------------------
