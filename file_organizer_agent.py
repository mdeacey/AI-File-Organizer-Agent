import asyncio
import os
# import json # Removed unused import
from pathlib import Path
from textwrap import dedent
from typing import List, Dict, Any

# Agno imports
from agno.agent.agent import Agent
from agno.exceptions import ModelProviderError
# MCP Imports
from agno.tools.mcp import MCPTools
from mcp import StdioServerParameters

# Model import
from agno.models.ollama import Ollama

# Environment variable loading
from dotenv import load_dotenv

# This will be determined based on the logic below
ALLOWED_BASE_PATH_STR = ""

# --- Safety Check Helper ---
def is_path_within_boundary(path_to_check: str, boundary_path: str) -> bool:
    """Checks if path_to_check is within the boundary_path."""
    try:
        abs_boundary = os.path.abspath(boundary_path)
        abs_check = os.path.abspath(path_to_check)
        return os.path.commonpath([abs_boundary, abs_check]) == abs_boundary
    except ValueError: # Handles cases like different drives on Windows
        return False
    except Exception as e:
        print(f"Error during path safety check: {e}")
        return False

# --- Main Async Function ---
async def main():
    load_dotenv() # Load environment variables from .env file

    # --- Load Configuration from Environment ---
    ollama_model_id = os.getenv("OLLAMA_MODEL", "llama3.2") # Default model if not specified
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434") # Default Ollama URL
    debug_mode = os.getenv("DEBUG", "False").lower() in ('true', '1', 't') # Handle boolean conversion

    # Load path config with defaults
    top_level_path_config = os.getenv("TOP_LEVEL_ALLOWED_PATH", "~")
    default_target_dir_config = os.getenv("DEFAULT_TARGET_DIR", "")

    print("--- File Organizer Agent (MCP Version) ---")
    global ALLOWED_BASE_PATH_STR

    # --- Determine Target Directory ---
    target_determined = False
    resolved_top_level = os.path.abspath(os.path.expanduser(top_level_path_config))

    if default_target_dir_config:
        resolved_default = os.path.abspath(os.path.expanduser(default_target_dir_config))
        print(f"Default target directory specified in config: {resolved_default}")
        if not os.path.isdir(resolved_default):
            print(f"Error: Default target directory '{resolved_default}' does not exist or is not a directory.")
        elif not is_path_within_boundary(resolved_default, resolved_top_level):
            print(f"Error: Default target directory '{resolved_default}' is outside the allowed top-level path '{resolved_top_level}'.")
        else:
            ALLOWED_BASE_PATH_STR = resolved_default
            target_determined = True
            print(f"Using default target. Organizing within: {ALLOWED_BASE_PATH_STR}")

    if not target_determined:
        print(f"Note: You will be prompted for a directory, which must be within: {resolved_top_level}")
        while True:
            user_path = input("Enter the full path to the directory you want to organize: ")
            resolved_user_path = os.path.abspath(os.path.expanduser(user_path))
            if not os.path.isdir(resolved_user_path):
                print("Invalid path: Not a directory. Please try again.")
            elif not is_path_within_boundary(resolved_user_path, resolved_top_level):
                print(f"Invalid path: Directory is outside the allowed top-level path '{resolved_top_level}'. Please try again.")
            else:
                ALLOWED_BASE_PATH_STR = resolved_user_path
                target_determined = True
                print(f"Organizing within: {ALLOWED_BASE_PATH_STR}")
                break

    if not ALLOWED_BASE_PATH_STR:
        print("Could not determine a valid target directory to organize. Exiting.")
        return

    # --- Get Optional User Context ---
    print("\n[Optional] Provide any context for organization (e.g., 'These are project files', 'Group photos by year').")
    user_context_input = input("> ").strip()

    # --- Initialize Ollama Model ---
    try:
        ollama_llm = Ollama(id=ollama_model_id, api_key="ollama", base_url=ollama_base_url)
        print(f"Initializing Ollama model: {ollama_model_id} at {ollama_base_url}")
    except ImportError:
        print("\nError: Ollama integration not found in agno library. Please ensure agno supports Ollama.")
        return
    except Exception as e:
        print(f"\nError initializing Ollama model: {e}")
        print(f"Please ensure Ollama is running at {ollama_base_url} and the model '{ollama_model_id}' is available.")
        return

    # --- Configure and Launch MCP Filesystem Server ---
    print("\nConfiguring MCP Filesystem server...")
    server_params = StdioServerParameters(
        command="npx",
        args=[
            "-y",
            "@modelcontextprotocol/server-filesystem",
            ALLOWED_BASE_PATH_STR,
        ],
        cwd=ALLOWED_BASE_PATH_STR,
    )

    # --- Run Agent within MCP Context ---
    try:
        async with MCPTools(server_params=server_params) as mcp_tools:
            print("MCP Tools Initialized.")
            organizer_agent = Agent(
                model=ollama_llm,
                tools=[mcp_tools],
                # Agent instructions defining its role, rules, and tool usage
                instructions=dedent(f"""\
                    You are a filesystem assistant organizing files within '{ALLOWED_BASE_PATH_STR}'.

                    CORE RULES:
                    1. NEVER use absolute paths (like /Users/... or C:/...).
                    2. ALWAYS use RELATIVE paths (like '.', 'subfolder', 'file.txt').
                    3. Keep related files together - move entire folders when appropriate.
                    4. INVALID MOVE: Never move a folder into itself or its own subfolder.
                    5. UNIQUE CALLS: Each tool call in the plan must be unique. Do not list the exact same call multiple times.

                    TOOLS:
                    - list_directory: Lists contents (use with {{ 'path': '.' }} for initial listing)
                    - create_directory: Creates a directory at a relative path
                    - move_file: Moves a file/folder from source to destination
                    - read_file: Reads file content
                    - delete_file: Deletes a file
                    - get_file_info: Gets file/directory metadata
                    - directory_tree: Shows recursive structure
                    - list_allowed_directories: Confirms accessible directories

                    CRITICAL ORDERING FOR PLANS:
                    Creating directories before moving files is MANDATORY. Follow this sequence:
                    1. Create ALL top-level directories first
                    2. Create ALL nested directories next
                    3. Move files and folders ONLY after directories exist

                    FORMAT YOUR PLAN:
                    PLAN:
                    # Phase 1: Create top-level directories
                    call tool 'create_directory' with args {{ 'path': 'Images' }}
                    call tool 'create_directory' with args {{ 'path': 'Documents' }}
                    call tool 'create_directory' with args {{ 'path': 'Projects' }}

                    # Phase 2: Create nested directories
                    call tool 'create_directory' with args {{ 'path': 'Images/Screenshots' }}
                    call tool 'create_directory' with args {{ 'path': 'Documents/Financial' }}

                    # Phase 3: Move files and folders
                    call tool 'move_file' with args {{ 'source': 'image.jpg', 'destination': 'Images/image.jpg' }}
                    call tool 'move_file' with args {{ 'source': 'statement.pdf', 'destination': 'Documents/Financial/statement.pdf' }}
                    call tool 'move_file' with args {{ 'source': 'OldFolder', 'destination': 'Projects/OldFolder' }}

                    ERROR HANDLING:
                    If a tool call fails, report the error and stop.

                    EXECUTION:
                    When executing an approved plan:
                    1. Execute each `call tool` line strictly one after the other, in the exact order provided in the plan text.
                    2. DO NOT proceed to the next step until the previous one succeeds. Dependencies are critical (e.g., a parent directory MUST be successfully created before attempting to create a subdirectory within it or move a file into it).
                    3. Use ONLY RELATIVE paths in the tool arguments during execution."""),
                show_tool_calls=True,
                markdown=True,
            )

            # --- Get Initial File Structure ---
            print("\nAsking agent to list initial file structure...")
            initial_structure_prompt = "CRITICAL: Use the tool 'list_directory' with the EXACT argument {{ 'path': '.' }} NOW. Do not use any other tool or path."
            initial_structure = ""
            try:
                initial_structure_response = await organizer_agent.arun(initial_structure_prompt)

                if debug_mode: # Use the loaded debug_mode variable
                    print("\nDEBUG: Full RunResponse object:")
                    print(vars(initial_structure_response))
                    print("DEBUG: Attributes of RunResponse object:")
                    print(dir(initial_structure_response))

                # Extract initial structure from tool output if available
                tool_output_list = initial_structure_response.tools if hasattr(initial_structure_response, 'tools') else None
                if isinstance(tool_output_list, list) and len(tool_output_list) > 0:
                    first_tool_result = tool_output_list[0]
                    if isinstance(first_tool_result, dict) and first_tool_result.get('tool_name') == 'list_directory' and 'content' in first_tool_result:
                        raw_content = first_tool_result['content']
                        if isinstance(raw_content, list) and len(raw_content) > 0: initial_structure = str(raw_content[0])
                        elif isinstance(raw_content, str): initial_structure = raw_content
                        else: print("Warning: list_directory tool content format unexpected.")
                    else: print("Warning: First tool result structure unexpected.")
                else:
                     print("Warning: No tool results found in response. Using agent's text content.")
                     initial_structure = initial_structure_response.content if hasattr(initial_structure_response, 'content') else str(initial_structure_response)

            except ModelProviderError as e:
                error_str = str(e).lower()
                if "429" in error_str or "resource_exhausted" in error_str:
                     print("\nError: API Rate Limit Hit during initial listing. Please wait a minute and try again.")
                else: print(f"\nError communicating with model provider during initial listing: {e}")
                return

            print("--- Initial Structure (as reported by agent) ---")
            print(initial_structure)
            print("--------------------------------------------------")

            # Exit if initial listing failed or directory is empty
            if not initial_structure.strip():
                 print("\nThe directory appears empty or agent failed to provide structure. Nothing to organize. Exiting.")
                 return

            # --- Planning and Execution Loop ---
            current_plan = ""
            last_response = ""
            while True:
                agent_call_failed = False
                try:
                    # --- Propose Plan ---
                    if not current_plan:
                         # Base prompt requesting organization plan
                         base_prompt = (
                             f"Based on the following file structure within the base directory '{ALLOWED_BASE_PATH_STR}', "
                             "propose a logical organization plan. Present the plan as a sequence of tool calls "
                             "using relative paths.\n\n"
                             f"Initial Structure:\n{initial_structure}"
                         )
                         # Prepend user context if it was provided
                         if user_context_input:
                             prompt = f"User Context for Organization: \"{user_context_input}\"\n\n{base_prompt}"
                         else:
                             prompt = base_prompt

                         print("\nAsking agent to propose an organization plan...")
                         print("(This may take a while for large directory structures...)")
                         last_response_obj = await organizer_agent.arun(prompt)
                         last_response = last_response_obj.content if hasattr(last_response_obj, 'content') else str(last_response_obj)

                         # Only print raw response if debug mode is enabled
                         if debug_mode:
                             print("\n--- Proposed Plan (Raw Agent Response) ---")
                             print(last_response)
                             print("-------------------------------------------")

                         # Extract tool calls from the plan
                         current_plan = ""
                         plan_marker = "PLAN:"
                         tool_call_prefix = "call tool"
                         plan_lines = []
                         if plan_marker in last_response:
                              plan_text = last_response.split(plan_marker, 1)[1].strip()
                              plan_lines = [line.strip() for line in plan_text.split('\n') if line.strip().lower().startswith(tool_call_prefix)]
                         elif tool_call_prefix in last_response.lower():
                              plan_lines = [line.strip() for line in last_response.split('\n') if line.strip().lower().startswith(tool_call_prefix)]
                         if plan_lines:
                              current_plan = "\n".join(plan_lines)
                         else:
                              print("Warning: Could not extract any 'call tool...' lines from the plan.")

                    # --- Display Extracted Plan for User Review ---
                    if current_plan:
                         print("\n--- Extracted Plan Actions --- (Review Carefully!) ---")
                         creates = []
                         moves = []
                         others = []
                         for line in current_plan.split('\n'):
                              if 'create_directory' in line: creates.append(line)
                              elif 'move_file' in line: moves.append(line)
                              else: others.append(line)
                         if creates: print("\n  Directories to Create:"); [print(f"    - {c}") for c in creates]
                         if moves: print("\n  Files/Folders to Move:"); [print(f"    - {m}") for m in moves]
                         if others: print("\n  Other Actions:"); [print(f"    - {o}") for o in others]
                         print("--------------------------------------------------------")
                    else:
                        if last_response and not current_plan:
                             print("\nNo actionable plan steps extracted from the agent's proposal.")

                    # --- Get User Input (Approve/Reject/Revise) ---
                    user_input = input(
                        "\nReview the plan. Type 'yes' to execute, 'no' to exit, "
                        "or provide feedback to revise the plan: "
                    ).lower().strip()

                    # --- Handle User Input ---
                    if user_input == 'yes':
                        if not current_plan:
                            print("No valid plan to execute. Please provide feedback or type 'no'.")
                            continue

                        print("\nExecuting the plan...")
                        execution_prompt = (
                            "Execute the following organization plan step-by-step using the available tools. "
                            "Call the tools exactly as listed.\n\n"
                            f"Plan:\n{current_plan}"
                        )
                        execution_result_obj = await organizer_agent.arun(execution_prompt)
                        execution_result = execution_result_obj.content if hasattr(execution_result_obj, 'content') else str(execution_result_obj)

                        print("\n--- Execution Result ---")
                        print(execution_result)
                        print("-----------------------")
                        print(f"\nOrganization complete (or attempted). Please check the directory: {ALLOWED_BASE_PATH_STR}")
                        break # Exit loop after execution attempt

                    elif user_input == 'no':
                        print("Exiting without organizing.")
                        break # Exit loop
                    else:
                        # Request plan revision based on feedback
                        print("\nAsking agent to revise the plan based on feedback...")
                        revision_prompt = (
                             f"The user wants to revise the organization plan. Their feedback is: '{user_input}'.\n"
                             "Generate a *new* organization plan (as a sequence of tool calls) that addresses this feedback. "
                             "IMPORTANT: If you need to know the current state of the directory, use the 'list_directory' tool *first*."
                        )
                        last_response_obj = await organizer_agent.arun(revision_prompt)
                        last_response = last_response_obj.content if hasattr(last_response_obj, 'content') else str(last_response_obj)
                        current_plan = "" # Reset plan to trigger re-extraction in next loop iteration

                        # Only print raw revised response if debug mode is enabled
                        if debug_mode:
                            print("\n--- Revised Plan Proposal Received (Raw) ---")
                            print(last_response)
                            print("-----------------------------------------------")
                        # Loop continues, will re-extract and display the plan

                # --- Error Handling within the Loop ---
                except ModelProviderError as e:
                    agent_call_failed = True
                    error_str = str(e).lower()
                    if "429" in error_str or "resource_exhausted" in error_str:
                        print("\nError: API Rate Limit Hit (429). Please wait while I pause...")
                        wait_time = 65
                        print(f"Pausing for {wait_time} seconds before allowing retry...")
                        await asyncio.sleep(wait_time)
                        print("Pause complete. You can retry the last action.")
                        # Don't reset current_plan if execution failed, allow user to retry 'yes'
                        if "Executing the plan" not in locals().get('execution_prompt', ""):
                             current_plan = ""
                             last_response = ""
                    else:
                        print(f"\nError communicating with the model provider: {e}")
                        print("Exiting loop due to unexpected model error.")
                        break

                except Exception as e:
                    print(f"\nAn unexpected error occurred within the planning/execution loop: {e}")
                    import traceback
                    traceback.print_exc()
                    print("Attempting to continue...")
                    current_plan = ""
                    last_response = ""
                    agent_call_failed = True

    # --- Error Handling for Setup/MCP ---
    except ImportError as e:
        print(f"\nImport Error: {e}. Please ensure libraries are installed (`pip install -r requirements.txt`)")
    except FileNotFoundError:
         print("\nError: 'npx' command not found. Please ensure Node.js and npm/npx are installed and in your system PATH.")
    except Exception as e:
        print(f"\nAn unexpected error occurred during agent execution setup: {e}")
        import traceback
        traceback.print_exc()

    print("\nAgent finished.")

# --- Script Entry Point ---
if __name__ == "__main__":
    # Check for npx before starting
    try:
        import subprocess
        subprocess.run(["npx", "--version"], check=True, capture_output=True)
        asyncio.run(main())
    except FileNotFoundError:
         print("Error: 'npx' command not found. Please ensure Node.js and npm/npx are installed and in your system PATH.")
    except subprocess.CalledProcessError:
         print("Error: 'npx' command found but returned an error. Please check your Node.js/npm installation.")
    except Exception as e:
         print(f"An error occurred before starting the agent: {e}")
