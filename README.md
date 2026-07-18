# Infra Agent 🚀

An interactive, stateful, and automated AWS Cloud Infrastructure Provisioning Agent. Powered by the **Google Antigravity SDK**, **FastAPI**, and **Terraform**, this application guides developers through a secure, validation-backed, and Human-in-the-Loop (HITL) deployment pipeline.

---

## Features

- **6-Step Managed Pipeline:** Step-by-step progress tracking through Requirements Gathering, HCL Code Generation, Syntax Formatting & Validation, HIL Code Review, Terraform Execution Planning, and AWS Deployment.
- **Human-in-the-Loop (HITL) Approvals:** Script approval (Step 4) and Plan approval (Step 5) gates prevent unexpected infrastructure changes.
- **Auto-Correction Engine:** If formatting or syntax validation fails, the agent parses the error logs, self-corrects the HCL script, and validates it again automatically.
- **AWS Credentials Status Banner:** Live UI badge checks for active AWS keys in the environment on connection.
- **Session Persistence:** Stateful conversations are saved and restored automatically using unique session IDs stored in your browser's local storage.

---

## Prerequisites

Before running the project locally, ensure you have the following installed:

1. **Python 3.10+** (Virtual environment recommended)
2. **Terraform CLI** (Must be installed and present in your system's `PATH`)
3. **AWS CLI** (Installed and configured)
4. **Google Gemini API Key** (From [Google AI Studio](https://aistudio.google.com/app/api-keys))

---

## Installation & Setup

Follow these steps to run the application on your local machine:

### 1. Clone the Repository
```bash
git clone https://github.com/ubaidmundewadi/devops-agents.git
cd devops-agents
```

### 2. Set Up a Python Virtual Environment
```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment (Mac/Linux)
source .venv/bin/activate

# Activate virtual environment (Windows)
# .venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
You must export your Gemini API key and AWS credentials in the terminal session running the backend:

```bash
# Set your Gemini API Key (Required)
export GEMINI_API_KEY="your_gemini_api_key_here"

# Set your AWS Credentials (Required for deployment)
export AWS_ACCESS_KEY_ID="your_aws_access_key_id"
export AWS_SECRET_ACCESS_KEY="your_aws_secret_access_key"
export AWS_DEFAULT_REGION="us-east-1"
```

---

## Running the Application

Start the FastAPI application using the Uvicorn web server:

```bash
uvicorn backend.main:app --reload
```

Once running, open your web browser and navigate to:
👉 **[http://localhost:8000/](http://localhost:8000/)**

---

## Project Structure

```text
├── backend/
│   ├── infra_agent.py        # Core agent logic, system instructions, and tool definitions
│   ├── main.py               # FastAPI server, static files serving, and WebSocket handlers
│   ├── sessions_store/       # Directory where persistent session trajectories are saved (ignored by git)
│   └── terraform_runner.py   # Wrapper executing local terraform cli commands
├── frontend/
│   ├── app.js                # Core UI events, WebSocket client, and text streaming
│   ├── index.html            # Dashboard layout and timeline visualizer
│   └── style.css             # Vanilla CSS design tokens and layouts
├── terraform/                # Target directory where the agent saves HCL configurations (git-tracked)
├── README.md                 # This documentation file
└── requirements.txt          # Python dependencies
```

---

## Pushing Updates to Git
Since this is a public repository, ensure you do not commit any state files or credential tokens. The project has a pre-configured `.gitignore`. 

To push your updates:
```bash
git add .
git commit -m "Your update description"
git push origin main
```
