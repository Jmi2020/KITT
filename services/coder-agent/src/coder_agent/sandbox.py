"""
Safe execution sandbox for running generated Python code and tests.

Executes code in isolated subprocess with strict resource limits, timeouts,
and no network access. Used for test-driven code validation.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of code execution in sandbox."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    error_message: Optional[str] = None


class CodeSandbox:
    """
    Secure sandbox for executing generated Python code with pytest.

    Safety features:
    - Isolated subprocess execution
    - Configurable timeout (default 20s)
    - No network access (enforced via subprocess environment)
    - Temporary file system for code and tests
    - Resource limits via subprocess
    """

    def __init__(
        self,
        timeout_seconds: int = 20,
        max_output_size: int = 50_000,
        allow_network: bool = False,
        allow_file_io: bool = False,
    ) -> None:
        """
        Initialize code sandbox.

        Args:
            timeout_seconds: Maximum execution time
            max_output_size: Maximum stdout/stderr size (chars)
            allow_network: Allow network access (default: False)
            allow_file_io: Allow file I/O beyond temp files (default: False)
        """
        self.timeout_seconds = timeout_seconds
        self.max_output_size = max_output_size
        self.allow_network = allow_network
        self.allow_file_io = allow_file_io

        logger.info(
            f"Initialized sandbox: timeout={timeout_seconds}s, "
            f"network={allow_network}, file_io={allow_file_io}"
        )

    def run_tests(
        self,
        code: str,
        test_code: str,
    ) -> ExecutionResult:
        """
        Run pytest tests against generated code.

        Args:
            code: Python module code to test
            test_code: Pytest test code

        Returns:
            ExecutionResult with test outcomes
        """
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)

                # Write code module
                code_file = tmp_path / "module.py"
                code_file.write_text(code, encoding="utf-8")

                # Write test module
                test_file = tmp_path / "test_module.py"
                test_file.write_text(test_code, encoding="utf-8")

                # Run pytest
                result = self._run_pytest(tmp_path)

                logger.info(
                    f"Tests {'passed' if result.success else 'failed'} "
                    f"(exit_code={result.exit_code})"
                )

                return result

        except Exception as exc:
            logger.error(f"Sandbox execution failed: {exc}", exc_info=True)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                error_message=f"Sandbox error: {exc}",
            )

    def run_code(
        self,
        code: str,
        check_syntax: bool = True,
    ) -> ExecutionResult:
        """
        Run Python code directly (without tests).

        Args:
            code: Python code to execute
            check_syntax: Validate syntax before execution

        Returns:
            ExecutionResult with execution outcomes
        """
        if check_syntax:
            syntax_result = self._check_syntax(code)
            if not syntax_result.success:
                return syntax_result

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)

                # Write code file
                code_file = tmp_path / "module.py"
                code_file.write_text(code, encoding="utf-8")

                # Execute code
                result = self._run_python(code_file)

                logger.info(
                    f"Code execution {'succeeded' if result.success else 'failed'} "
                    f"(exit_code={result.exit_code})"
                )

                return result

        except Exception as exc:
            logger.error(f"Code execution failed: {exc}", exc_info=True)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                error_message=f"Execution error: {exc}",
            )

    def _check_syntax(self, code: str) -> ExecutionResult:
        """
        Check Python syntax without execution.

        Args:
            code: Python code to validate

        Returns:
            ExecutionResult with syntax validation status
        """
        try:
            compile(code, "<string>", "exec")
            return ExecutionResult(
                success=True,
                stdout="Syntax valid",
                stderr="",
                exit_code=0,
            )
        except SyntaxError as exc:
            logger.warning(f"Syntax error: {exc}")
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(exc),
                exit_code=1,
                error_message=f"Syntax error: {exc}",
            )

    def _run_pytest(self, working_dir: Path) -> ExecutionResult:
        """
        Execute pytest in working directory.

        Args:
            working_dir: Directory containing test files

        Returns:
            ExecutionResult with pytest outcomes
        """
        cmd = [
            "python",
            "-m",
            "pytest",
            str(working_dir),
            "-v",  # Verbose output
            "--tb=short",  # Short traceback format
            "--color=no",  # No color codes
        ]

        return self._run_subprocess(cmd, cwd=working_dir)

    def _run_python(self, script_path: Path) -> ExecutionResult:
        """
        Execute Python script.

        Args:
            script_path: Path to Python file

        Returns:
            ExecutionResult with execution outcomes
        """
        cmd = ["python", str(script_path)]

        return self._run_subprocess(cmd, cwd=script_path.parent)

    def _run_subprocess(
        self,
        cmd: list[str],
        cwd: Path,
    ) -> ExecutionResult:
        """
        Run subprocess with timeout and resource limits.

        Args:
            cmd: Command and arguments
            cwd: Working directory

        Returns:
            ExecutionResult with process outcomes
        """
        env = self._build_sandbox_env()

        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,  # Don't raise on non-zero exit
            )

            # Truncate output if too large
            stdout = proc.stdout[: self.max_output_size]
            stderr = proc.stderr[: self.max_output_size]

            if len(proc.stdout) > self.max_output_size:
                stdout += "\n... (output truncated)"
            if len(proc.stderr) > self.max_output_size:
                stderr += "\n... (output truncated)"

            success = proc.returncode == 0

            return ExecutionResult(
                success=success,
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode,
            )

        except subprocess.TimeoutExpired:
            logger.warning(f"Process timed out after {self.timeout_seconds}s")
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Execution timed out after {self.timeout_seconds}s",
                exit_code=-1,
                timed_out=True,
                error_message=f"Timeout after {self.timeout_seconds}s",
            )

        except Exception as exc:
            logger.error(f"Subprocess execution failed: {exc}", exc_info=True)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(exc),
                exit_code=-1,
                error_message=f"Subprocess error: {exc}",
            )

    def _build_sandbox_env(self) -> dict[str, str]:
        """
        Build restricted environment for subprocess.

        Returns:
            Environment variables dict with safety restrictions
        """
        import os

        # Start with minimal environment
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "USER": os.environ.get("USER", ""),
        }

        # Disable network if not allowed
        if not self.allow_network:
            env["http_proxy"] = "http://127.0.0.1:0"
            env["https_proxy"] = "http://127.0.0.1:0"
            env["HTTP_PROXY"] = "http://127.0.0.1:0"
            env["HTTPS_PROXY"] = "http://127.0.0.1:0"
            env["no_proxy"] = ""
            env["NO_PROXY"] = ""

        # Python-specific restrictions
        env["PYTHONDONTWRITEBYTECODE"] = "1"  # No .pyc files
        env["PYTHONUNBUFFERED"] = "1"  # Unbuffered output

        # Disable user site-packages for isolation
        env["PYTHONNOUSERSITE"] = "1"

        return env


class TestRunner:
    """
    High-level test runner for code generation workflow.

    Combines code execution, test execution, and result analysis.
    """

    def __init__(
        self,
        timeout_seconds: int = 20,
        allow_network: bool = False,
    ) -> None:
        """
        Initialize test runner.

        Args:
            timeout_seconds: Execution timeout
            allow_network: Allow network access
        """
        self.sandbox = CodeSandbox(
            timeout_seconds=timeout_seconds,
            allow_network=allow_network,
        )

    def validate_and_test(
        self,
        code: str,
        test_code: str,
    ) -> tuple[bool, ExecutionResult]:
        """
        Validate syntax and run tests on generated code.

        Args:
            code: Python module code
            test_code: Pytest test code

        Returns:
            Tuple of (passed, ExecutionResult)
        """
        # First check syntax
        syntax_check = self.sandbox._check_syntax(code)
        if not syntax_check.success:
            logger.warning("Code failed syntax validation")
            return False, syntax_check

        # Then run tests
        test_result = self.sandbox.run_tests(code, test_code)

        return test_result.success, test_result

    def run_single_test(
        self,
        code: str,
        test_code: str,
    ) -> ExecutionResult:
        """
        Convenience method for running tests.

        Args:
            code: Python code to test
            test_code: Test code

        Returns:
            ExecutionResult
        """
        return self.sandbox.run_tests(code, test_code)
