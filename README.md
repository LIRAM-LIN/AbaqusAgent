# AbaqusAgent

A multi-agent framework for end-to-end finite element analysis of solid mechanics problems using automated Abaqus simulation generation, execution, and analysis with LLMs.

## Overview

AbaqusAgent automates the full finite element simulation pipeline from a natural language description. It integrates multiple agents to handle requirement interpretation, simulation planning, input file generation, simulation execution, error correction, and result visualization.

## Key Components

- **Interpreter Agent:** Processes user requirements.
- **Architect Agent:** Plans the simulation structure and retrieves similar cases.
- **Input Writer Agent:** Generates Abaqus input files.
- **Runner Agent:** Executes Abaqus simulations.
- **Reviewer Agent:** Diagnoses and fixes simulation errors.
- **Visualization Agent:** Extracts and visualizes results.

## Features

- End-to-end automation of Abaqus workflows
- Multi-agent architecture for modular design
- Automated error detection and correction
- Integration with LLMs for intelligent reasoning
- Retrieval of relevant benchmark cases for improved input generation

## Installation

Install the required Python libraries listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

AbaqusAgent requires a working Abaqus installation. The current version was developed and tested with Abaqus 2023. 

Create a `.env` file using `.env.example` and add your own API keys.

## Usage

Write the simulation problem in `user_requirement.txt`, including geometry, material properties, boundary conditions, loading conditions, and requested outputs.

Run the main script:

```bash
python AbaqusBench_noArg.py
```

The framework will generate Abaqus input files, execute simulations, perform error correction if needed, and produce output and visualization files in the output directory.

## Acknowledgment

This repository uses an agent skeleton adapted from prior work by Ling Yue et al., licensed under the MIT License. The implementation and application for Abaqus-based simulation are independently developed.

## Citation

To be added after paper submission
