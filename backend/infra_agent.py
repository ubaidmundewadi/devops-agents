import asyncio
import os
import shutil
import json
import logging
from typing import Callable, Awaitable, List
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig, types
from google.antigravity.hooks import policy
from backend.terraform_runner import TerraformRunner

logger = logging.getLogger("infra_agent")

class InfraAgentSession:
    def __init__(self, send_to_client: Callable[[dict], Awaitable[None]], workspace_dir: str, conversation_id: str = "default_session"):
        self.send_to_client = send_to_client
        self.workspace_dir = workspace_dir
        self.conversation_id = conversation_id
        self.runner = TerraformRunner(workspace_dir)
        self.input_queue = asyncio.Queue()
        self.agent_task = None
        self.active_agent = None

    async def update_status(self, step: int, description: str):
        """Helper to send the current status step to the frontend."""
        await self.send_to_client({
            "type": "status",
            "step": step,
            "description": description
        })

    async def send_credentials_status(self):
        """Checks AWS credentials (static or IRSA) and sends the status to the client."""
        has_static = "AWS_ACCESS_KEY_ID" in os.environ and "AWS_SECRET_ACCESS_KEY" in os.environ
        has_irsa = "AWS_ROLE_ARN" in os.environ and "AWS_WEB_IDENTITY_TOKEN_FILE" in os.environ
        has_credentials = has_static or has_irsa
        await self.send_to_client({
            "type": "credentials_status",
            "available": has_credentials
        })

    def get_tools(self) -> List[Callable]:
        """Defines and returns the list of custom tools closure-bound to this session."""
        
        async def ask_user_for_info(prompt: str) -> str:
            """Asks the user for missing configuration variables or parameters.
            
            Args:
                prompt: A clear question detailing what information is needed (e.g. "What AWS region would you like to use?").
            """
            await self.update_status(1, f"Awaiting user input: {prompt}")
            await self.send_to_client({
                "type": "info_request",
                "prompt": prompt
            })
            
            # Wait for user input from the queue
            user_response = await self.input_queue.get()
            text = user_response.get("text", "")
            await self.update_status(1, "Received user input.")
            return text

        async def save_terraform_code(code: str) -> str:
            """Saves the generated Terraform configuration to main.tf.
            
            Args:
                code: The complete, valid Terraform HCL configuration string.
            """
            await self.update_status(2, "Saving Terraform script to file...")
            path = self.runner.write_main_tf(code)
            await self.update_status(2, f"Saved script to {os.path.basename(path)}.")
            return f"Successfully saved configuration code to local file system."

        async def request_script_approval(code: str) -> str:
            """Presents the Terraform code to the user and blocks until approved or rejected.
            
            Args:
                code: The configuration code to review.
            """
            await self.update_status(4, "Awaiting script approval from user...")
            await self.send_to_client({
                "type": "script_approval",
                "code": code
            })
            
            response = await self.input_queue.get()
            approved = response.get("approved", False)
            feedback = response.get("feedback", "")
            
            if approved:
                await self.update_status(4, "Script approved by user.")
                return "APPROVED"
            else:
                await self.update_status(4, "Script rejected by user. Feedback received.")
                return f"REJECTED. Feedback: {feedback}. Please rewrite the terraform file to address the feedback."

        async def run_terraform_fmt_validate() -> str:
            """Runs terraform init, fmt, and validate on the workspace, returning the outcome.
            
            If validate fails, it returns the error logs so they can be parsed and corrected.
            """
            await self.update_status(3, "Initializing Terraform provider...")
            success, stdout, stderr = await self.runner.init()
            if not success:
                await self.update_status(3, "Terraform init failed.")
                return f"terraform init failed:\n{stderr}\n{stdout}"
                
            await self.update_status(3, "Formatting Terraform files (terraform fmt)...")
            await self.runner.fmt()
            
            await self.update_status(3, "Validating Terraform configuration (terraform validate)...")
            success, stdout, stderr = await self.runner.validate()
            if success:
                await self.update_status(3, "Terraform validation succeeded.")
                return "VALIDATION_SUCCESS"
            else:
                await self.update_status(3, "Terraform validation failed.")
                return f"VALIDATION_FAILED:\n{stderr}\n{stdout}\nSuggest corrections for these validation errors and save the corrected file."

        async def run_terraform_plan() -> str:
            """Generates a Terraform execution plan and returns the plan output.
            
            Requires active AWS credentials. If it fails, details are returned.
            """
            await self.update_status(5, "Generating Terraform plan...")
            success, stdout, stderr = await self.runner.plan()
            if success:
                await self.update_status(5, "Plan generated successfully.")
                return stdout
            else:
                await self.update_status(5, "Failed to run terraform plan.")
                return f"PLAN_FAILED:\n{stderr}\n{stdout}\nMake sure AWS credentials are set and valid."

        async def request_plan_approval(plan_output: str) -> str:
            """Presents the plan output to the user and blocks until approved or rejected.
            
            Args:
                plan_output: The text output from terraform plan.
            """
            await self.update_status(5, "Awaiting plan approval from user...")
            await self.send_to_client({
                "type": "plan_approval",
                "plan": plan_output
            })
            
            response = await self.input_queue.get()
            approved = response.get("approved", False)
            feedback = response.get("feedback", "")
            
            if approved:
                await self.update_status(5, "Plan approved by user.")
                return "APPROVED"
            else:
                await self.update_status(5, "Plan rejected. Feedback received.")
                return f"REJECTED. Feedback: {feedback}. Please modify the configuration based on feedback."

        async def run_terraform_apply() -> str:
            """Deploys the infrastructure by running terraform apply.
            
            Requires active AWS credentials. Output log is returned.
            """
            await self.update_status(6, "Applying Terraform plan. Deploying to AWS...")
            success, stdout, stderr = await self.runner.apply()
            if success:
                await self.update_status(6, "Infrastructure successfully deployed!")
                return f"APPLY_SUCCESS:\n{stdout}"
            else:
                await self.update_status(6, "Deployment failed.")
                return f"APPLY_FAILED:\n{stderr}\n{stdout}"

        return [
            ask_user_for_info,
            save_terraform_code,
            request_script_approval,
            run_terraform_fmt_validate,
            run_terraform_plan,
            request_plan_approval,
            run_terraform_apply
        ]

    async def start(self, initial_prompt: str):
        """Starts the agent chat execution in a background task."""
        self.agent_task = asyncio.create_task(self._run_agent(initial_prompt))

    async def _run_agent(self, initial_prompt: str):
        try:
            # Check AWS Credentials (static or IRSA) and notify the UI of current availability
            has_static = "AWS_ACCESS_KEY_ID" in os.environ and "AWS_SECRET_ACCESS_KEY" in os.environ
            has_irsa = "AWS_ROLE_ARN" in os.environ and "AWS_WEB_IDENTITY_TOKEN_FILE" in os.environ
            has_credentials = has_static or has_irsa
            await self.send_to_client({
                "type": "credentials_status",
                "available": has_credentials
            })

            # Define System Instructions for the agent
            sys_instructions = (
                "You are an AWS Cloud Infrastructure Provisioning Agent. Your job is to guide the user in provisioning AWS resources via Terraform in exactly 6 steps:\n"
                "1. Gather requirements. Greet the user, understand what resource they want, and determine what required parameters are needed for that resource (based on latest AWS provider version 5.x). Use `ask_user_for_info` to collect any missing details. You MUST ask for the AWS region if not specified, and always include the `provider \"aws\" { region = \"...\" }` block in your generated code. Additionally, for EC2 instances, you MUST restrict the instance type choice to ONLY these 4 allowed options: 't3.micro', 't3.small', 'c7i-flex.large', and 'm7i-flex.large'. If the user requests any other type, explain the restriction and ask them to select one of the allowed types.\n"
                "2. Generate Terraform script. Write the configuration code and call `save_terraform_code` to save it locally. Crucially, when generating EC2 instance resources, you MUST NOT use hardcoded default AMI IDs. If the user explicitly provides a specific AMI ID (e.g. starting with 'ami-'), use that ID directly in the resource block. Otherwise, always define a dynamic `aws_ami` data source (searching for the latest Amazon Linux 2023 AMI, owners=['amazon'], filter name='name' with values=['al2023-ami-*-x86_64']) and reference its ID in the instance resource. Also, double-check that the instance type is strictly one of the 4 allowed options ('t3.micro', 't3.small', 'c7i-flex.large', 'm7i-flex.large') and NEVER generate scripts using other types.\n"
                "3. Format & Validate. Call `run_terraform_fmt_validate`. If validation fails, correct the code, save it locally, and re-validate until it passes.\n"
                "4. Request script approval. Once the script is valid, call `request_script_approval` to present the code to the user. If they reject/modify, correct it, save, re-validate, and request approval again.\n"
                "5. Plan and Review. Call `run_terraform_plan` to generate a plan. Present the output to the user by calling `request_plan_approval`. If rejected, ask for feedback, apply changes (loop back to step 2), and generate a new plan.\n"
                "6. Deploy. Once the plan is approved, call `run_terraform_apply` to provision the resources. Report success to the user.\n\n"
                "Strictly follow this exact order. Always report status progress using chat texts as you transition. Speak directly, professionally, and concisely.\n"
                "Do NOT use Markdown headers (like `#`, `##`, `###`) in your chat responses. Keep your responses clean and easy to read using simple paragraphs, bold text, or bullet points instead."
            )

            # Create session store directory
            sessions_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions_store")
            os.makedirs(sessions_dir, exist_ok=True)

            # Check if we should resume a previous conversation
            # Antigravity SDK requires the trajectory file to exist in order to pass conversation_id
            resume_id = None
            if self.conversation_id:
                session_file_json = os.path.join(sessions_dir, f"{self.conversation_id}.json")
                session_file_raw = os.path.join(sessions_dir, self.conversation_id)
                if os.path.exists(session_file_json) or os.path.exists(session_file_raw):
                    resume_id = self.conversation_id

            # Dynamically connect to the remote AWS MCP server via SSE if URL is configured
            mcp_servers = []
            aws_mcp_url = os.environ.get("AWS_MCP_SSE_URL")
            if aws_mcp_url:
                headers = {}
                aws_mcp_token = os.environ.get("AWS_MCP_SSE_TOKEN")
                if aws_mcp_token:
                    headers["Authorization"] = f"Bearer {aws_mcp_token}"
                
                mcp_servers.append(
                    types.McpSseServer(
                        url=aws_mcp_url,
                        headers=headers if headers else None
                    )
                )

            # Create agent configuration
            config = LocalAgentConfig(
                system_instructions=sys_instructions,
                capabilities=CapabilitiesConfig(enable_subagents=True),
                tools=self.get_tools(),
                mcp_servers=mcp_servers if mcp_servers else None,
                policies=[policy.allow_all()],
                save_dir=sessions_dir,
                conversation_id=resume_id
            )

            async with Agent(config) as agent:
                self.active_agent = agent
                
                # Fetch the active conversation ID (which could be newly generated by the SDK)
                self.conversation_id = agent.conversation_id
                
                # Notify the client of the active session/conversation ID so it can save it for resuming
                await self.send_to_client({
                    "type": "session_id",
                    "session_id": self.conversation_id
                })
                
                prompt = initial_prompt
                while True:
                    await self.update_status(1, "Starting requirements analysis...")
                    
                    response = await agent.chat(prompt)
                    
                    # Stream the text output to client
                    async for token in response:
                        await self.send_to_client({
                            "type": "text",
                            "content": token
                        })
                    
                    await self.send_to_client({
                        "type": "complete",
                        "content": "Deployment pipeline iteration complete. Ready for further instructions (e.g. create more resources, modify existing ones, or delete/destroy resources).\n\nDo you have any further instructions?"
                    })
                    
                    # Wait for next user message from the queue
                    user_msg = await self.input_queue.get()
                    prompt = user_msg.get("text", "")
                    if not prompt:
                        break
                
        except asyncio.CancelledError:
            logger.info("Agent run cancelled.")
        except Exception as e:
            logger.exception("Agent run encountered an error")
            await self.send_to_client({
                "type": "error",
                "message": f"Agent error: {str(e)}"
            })

    async def handle_client_message(self, message: dict):
        """Receives input from client (WebSocket) and pushes it to input_queue for tool blocks."""
        mtype = message.get("type")
        if mtype == "chat":
            # If the user is chatting, we feed it to the active agent conversation
            # Wait, if the agent is blocked in a tool queue, the message goes to the queue instead.
            if self.input_queue.empty():
                # If nothing is waiting, we can feed it as a new turn (if possible)
                # But since the agent is running in a one-turn chat script loop that handles HITL,
                # we primarily feed inputs into the input_queue.
                await self.input_queue.put({"text": message.get("content")})
            else:
                await self.input_queue.put({"text": message.get("content")})
        elif mtype in ("info_response", "script_approval_response", "plan_approval_response"):
            await self.input_queue.put(message)
