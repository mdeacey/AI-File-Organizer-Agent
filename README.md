# AI File Organizer Agent

This Python script uses an AI agent (powered by Google Gemini via the Agno framework) to intelligently propose and execute a plan for organizing files within a specified directory on your computer.

## Features

*   **AI-Powered Planning:** Leverages a Gemini language model to analyze the current file structure and suggest a logical organization plan.
*   **User Interaction:** Presents the proposed plan for review, allowing the user to approve, reject, or provide feedback for revisions.
*   **Robust Filesystem Interaction:** Uses the Model Context Protocol (MCP) and the standard `@modelcontextprotocol/server-filesystem` for safe and sandboxed file operations (listing directories, creating directories, moving files/folders).
*   **Configurable Target Directory:** Allows setting a default directory or prompts the user, ensuring operations stay within a defined top-level boundary.
*   **Rate Limit Handling:** Includes basic handling for API rate limits (429 errors) with an automatic pause.
*   **Debug Mode:** Includes a `DEBUG` flag for more verbose output during execution.

## Requirements

*   Python 3.x
*   Node.js and `npx` (comes with npm, usually installed with Node.js). Required to run the MCP filesystem server.
*   Google API Key with Gemini API access. Get one from [Google AI Studio](https://aistudio.google.com/app/apikey).
*   Required Python packages (see `requirements.txt`):
    *   `agno`
    *   `mcp`
    *   `google-genai`
    *   `python-dotenv`

## Setup

1.  **Clone/Download:** Get the `file_organizer_agent.py`, `requirements.txt`, and `.env` files.
2.  **Install Node.js:** If you don't have it, download and install Node.js LTS from [nodejs.org](https://nodejs.org/). This will include `npm` and `npx`.
3.  **Create Python Virtual Environment (Recommended):**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    ```
4.  **Install Python Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
5.  **Configure API Key:**
    *   Create a file named `.env` in the same directory as the script.
    *   Add your Google API Key to it:
        ```env
        GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY_HERE
        ```
    *   Replace `YOUR_GOOGLE_API_KEY_HERE` with your actual key.

## Configuration (in `.env` file)

Adjust these variables in the `.env` file as needed:

*   `GOOGLE_API_KEY`: **Required.** Your API key from Google AI Studio.
*   `DEFAULT_TARGET_DIR`: Optional. Set this to the full path of the directory you usually want to organize (e.g., `/Users/yourname/Downloads`). If this is set and valid (exists and is within `TOP_LEVEL_ALLOWED_PATH`), the script will skip the prompt. If left empty (`""`), the script will always prompt you.
*   `TOP_LEVEL_ALLOWED_PATH`: Optional. Set this to the absolute highest-level directory the script should *ever* be allowed to access (even when prompting). Defaults to the user's home directory (`~`) if not set. For safety, you might restrict this further, e.g., `~/Documents`.
*   `DEBUG`: Optional. Set to `True` to enable detailed debugging output (like the full agent response object). Defaults to `False` if not set.

## Running the Script

1.  Ensure your virtual environment is activated (if using one).
2.  Make sure your `.env` file with the API key is present.
3.  Run the script from your terminal:
    ```bash
    python file_organizer_agent.py
    ```
4.  Follow the prompts:
    *   If `DEFAULT_TARGET_DIR` is not set or invalid, it will ask for the target directory (which must be inside `TOP_LEVEL_ALLOWED_PATH`).
    *   It will ask the agent to list the files (this uses the Gemini API).
    *   It will ask the agent to propose a plan (uses the Gemini API, may take time for large directories).
    *   Review the extracted plan actions.
    *   Type `yes` to execute the plan, `no` to exit, or provide text feedback to ask the agent for a revised plan.

## How it Works

1.  **Setup:** Loads the API key and configuration from the `.env` file, determines the target directory, and initializes the Gemini model via Agno.
2.  **MCP Server:** Launches the `@modelcontextprotocol/server-filesystem` process using `npx`, restricting it to operate only within the determined target directory (`ALLOWED_BASE_PATH_STR`).
3.  **Initial Scan:** Instructs the agent to use the `list_directory` tool (via MCP) to get the initial file structure.
4.  **Planning:** Sends the file structure to the Gemini model and asks for an organization plan, formatted as a sequence of `create_directory` and `move_file` tool calls with relative paths. Instructions guide the agent on desired structure, path usage, and execution order.
5.  **Review:** Extracts the tool calls from the agent's response and displays them clearly for user confirmation.
6.  **Execution (if approved):** Sends the extracted plan back to the agent, instructing it to execute the listed tool calls sequentially via the MCP server.
7.  **Revision (if feedback given):** Sends the user's feedback to the agent, asking it to generate a new plan, potentially re-listing the directory first if needed.

## Error Handling

*   Catches and reports errors during model initialization (e.g., missing API key).
*   Catches and reports errors if `npx` is not found.
*   Catches API rate limit errors (429) during agent calls, prints a message, pauses for ~65 seconds, and allows the user to retry the last action.
*   Catches other model communication errors.

## Notes

*   The quality and logic of the organization plan depend heavily on the capabilities of the Gemini model (`gemini-1.5-flash` currently).
*   Complex directory structures or ambiguous filenames might lead to suboptimal or occasionally flawed plans (like the self-move issue the prompts now try to prevent). Always review the plan carefully before executing.
*   Ensure the user running the script has appropriate read/write permissions for the target directory.
