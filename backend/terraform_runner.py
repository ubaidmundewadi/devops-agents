import asyncio
import os
import shutil
from typing import Dict, Any, Tuple

PROVIDERS_TF_CONTENT = """terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  # Configuration options are typically set via environment variables:
  # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
}
"""

class TerraformRunner:
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        os.makedirs(self.workspace_dir, exist_ok=True)
        
    def write_providers_tf(self) -> str:
        """Writes the default providers.tf if it doesn't already exist."""
        providers_path = os.path.join(self.workspace_dir, "providers.tf")
        if not os.path.exists(providers_path):
            with open(providers_path, "w") as f:
                f.write(PROVIDERS_TF_CONTENT)
        return providers_path

    def write_main_tf(self, code: str) -> str:
        """Writes/overwrites main.tf with the generated Terraform configuration."""
        main_tf_path = os.path.join(self.workspace_dir, "main.tf")
        with open(main_tf_path, "w") as f:
            f.write(code)
        return main_tf_path

    def read_main_tf(self) -> str:
        """Reads main.tf if it exists."""
        main_tf_path = os.path.join(self.workspace_dir, "main.tf")
        if os.path.exists(main_tf_path):
            with open(main_tf_path, "r") as f:
                return f.read()
        return ""

    async def _run_command(self, args: list[str]) -> Tuple[bool, str, str]:
        """Runs a command asynchronously and returns (success, stdout, stderr)."""
        # Find terraform in PATH
        terraform_path = shutil.which("terraform")
        if not terraform_path:
            return False, "", "Terraform CLI not found in PATH."

        try:
            process = await asyncio.create_subprocess_exec(
                terraform_path,
                *args,
                cwd=self.workspace_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy()
            )
            stdout_bytes, stderr_bytes = await process.communicate()
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            success = process.returncode == 0
            return success, stdout, stderr
        except Exception as e:
            return False, "", f"Execution error: {str(e)}"

    async def init(self) -> Tuple[bool, str, str]:
        """Runs terraform init."""
        self.write_providers_tf()
        return await self._run_command(["init", "-no-color"])

    async def fmt(self) -> Tuple[bool, str, str]:
        """Runs terraform fmt."""
        return await self._run_command(["fmt", "-no-color"])

    async def validate(self) -> Tuple[bool, str, str]:
        """Runs terraform validate."""
        return await self._run_command(["validate", "-no-color"])

    async def plan(self) -> Tuple[bool, str, str]:
        """Runs terraform plan."""
        return await self._run_command(["plan", "-no-color"])

    async def apply(self) -> Tuple[bool, str, str]:
        """Runs terraform apply."""
        return await self._run_command(["apply", "-auto-approve", "-no-color"])
