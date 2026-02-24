# code_executor.py
"""
Safely validates and executes LLM-generated Python code within the CATIA context.

Features:
  - AST-based code validation (blocks dangerous imports/calls)
  - Sandboxed execution namespace
  - Detailed error reporting with line numbers
  - Execution logging and history
  - Auto-retry support
"""

import ast
import sys
import traceback
import logging
import time
from datetime import datetime
from typing import Tuple, Optional, Dict, Any, List

from catia_bridge import CATIABridge

logger = logging.getLogger("CodeExecutor")


# ═══════════════════════════════════════════════════════════════════
# Security Configuration
# ═══════════════════════════════════════════════════════════════════

# Modules that generated code must NOT import
BLOCKED_MODULES = frozenset({
    # System / OS access
    "os", "sys", "subprocess", "shutil", "pathlib",
    "platform", "signal", "resource",
    # Network
    "socket", "http", "urllib", "urllib2", "requests",
    "ftplib", "smtplib", "telnetlib", "xmlrpc",
    # Dangerous serialization
    "pickle", "shelve", "marshal",
    # Low-level
    "ctypes", "cffi", "mmap",
    # Code execution
    "code", "codeop", "compileall", "importlib",
    # File-system
    "glob", "fnmatch", "tempfile",
    # Introspection that could be abused
    "inspect", "dis",
})

# Built-in functions that must NOT be called
BLOCKED_BUILTINS = frozenset({
    "exec",
    "eval",
    "compile",
    "__import__",
    "globals",
    "locals",
    "breakpoint",
    "exit",
    "quit",
    "input",          # Blocks interactive input during execution
    "open",           # File I/O — use bridge.save_part() instead
    "delattr",
    "setattr",        # Could tamper with bridge objects
})

# Maximum code length (characters) we will execute
MAX_CODE_LENGTH = 100_000

# Maximum execution time (seconds) — note: we can't truly enforce this
# without threading, but we log a warning
MAX_EXECUTION_TIME = 120


# ═══════════════════════════════════════════════════════════════════
# Code Validator
# ═══════════════════════════════════════════════════════════════════

class CodeValidator:
    """
    Validates Python code using AST analysis before execution.
    Blocks dangerous patterns while allowing CATIA automation code.
    """

    def validate(self, code: str) -> Tuple[bool, str]:
        """
        Validate code for syntax correctness and safety.

        Args:
            code: Python source code string.

        Returns:
            (is_valid, message) — message is "OK" on success,
            or a description of the problem on failure.
        """
        # ── Length check ──
        if len(code) > MAX_CODE_LENGTH:
            return False, (
                f"Code too long: {len(code)} chars "
                f"(max {MAX_CODE_LENGTH})"
            )

        if not code.strip():
            return False, "Empty code"

        # ── Syntax check ──
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, (
                f"Syntax error at line {e.lineno}, col {e.offset}: {e.msg}"
            )

        # ── Walk the AST for dangerous patterns ──
        for node in ast.walk(tree):
            result = self._check_node(node)
            if result is not None:
                return False, result

        return True, "OK"

    def _check_node(self, node: ast.AST) -> Optional[str]:
        """
        Check a single AST node for dangerous patterns.
        Returns an error message string if blocked, None if OK.
        """
        # ── Check: import statements ──
        if isinstance(node, ast.Import):
            for alias in node.names:
                base_module = alias.name.split(".")[0]
                if base_module in BLOCKED_MODULES:
                    return (
                        f"Blocked import: '{alias.name}' "
                        f"(module '{base_module}' is not allowed)"
                    )

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base_module = node.module.split(".")[0]
                if base_module in BLOCKED_MODULES:
                    return (
                        f"Blocked import: 'from {node.module} import ...' "
                        f"(module '{base_module}' is not allowed)"
                    )

        # ── Check: dangerous function calls ──
        elif isinstance(node, ast.Call):
            func_name = self._get_call_name(node)
            if func_name and func_name in BLOCKED_BUILTINS:
                return f"Blocked function call: '{func_name}()'"

        # ── Check: attribute access to __dunder__ methods ──
        elif isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("__") and attr.endswith("__"):
                # Allow __name__, __class__ (sometimes needed)
                allowed_dunders = {"__name__", "__class__", "__doc__"}
                if attr not in allowed_dunders:
                    return f"Blocked dunder access: '.{attr}'"

        return None

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Extract the function name from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None


# ═══════════════════════════════════════════════════════════════════
# Execution Log Entry
# ═══════════════════════════════════════════════════════════════════

class ExecutionRecord:
    """Record of a single code execution attempt."""

    def __init__(
        self,
        code: str,
        success: bool,
        message: str,
        error_traceback: Optional[str] = None,
        duration: float = 0.0,
    ):
        self.timestamp = datetime.now()
        self.code = code
        self.success = success
        self.message = message
        self.error_traceback = error_traceback
        self.duration = duration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "message": self.message,
            "duration_seconds": round(self.duration, 2),
            "code_length": len(self.code),
            "code_lines": self.code.count("\n") + 1,
            "error": self.error_traceback,
        }

    def __repr__(self) -> str:
        status = "✅" if self.success else "❌"
        return (
            f"ExecutionRecord({status} {self.timestamp:%H:%M:%S} "
            f"{self.duration:.1f}s)"
        )


# ═══════════════════════════════════════════════════════════════════
# Code Executor
# ═══════════════════════════════════════════════════════════════════

class CodeExecutor:
    """
    Executes validated Python code in a sandboxed CATIA context.

    Usage:
        bridge = CATIABridge()
        bridge.connect()
        bridge.create_new_part("Test")

        executor = CodeExecutor(bridge)
        success, msg, err = executor.execute(some_generated_code)
    """

    def __init__(self, bridge: CATIABridge):
        """
        Args:
            bridge: An initialized and connected CATIABridge instance.
        """
        self.bridge = bridge
        self.validator = CodeValidator()
        self.execution_history: List[ExecutionRecord] = []
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0

    # ──────────────────────────────────────────────
    # Main Execution Method
    # ──────────────────────────────────────────────

    def execute(
        self,
        code: str,
        skip_validation: bool = False,
        description: str = "",
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Validate and execute Python code in the CATIA context.

        Args:
            code: Python source code to execute.
            skip_validation: If True, skip AST safety checks (NOT recommended).
            description: Optional description for logging.

        Returns:
            Tuple of:
                - success (bool): Whether execution completed without error.
                - message (str): Human-readable result message.
                - error_traceback (Optional[str]): Full traceback if failed, None if OK.
        """
        self.total_executions += 1

        # ── Step 1: Validate ──
        if not skip_validation:
            is_valid, validation_msg = self.validator.validate(code)
            if not is_valid:
                msg = f"Code validation failed: {validation_msg}"
                logger.error(f"❌ {msg}")
                record = ExecutionRecord(code, False, msg)
                self.execution_history.append(record)
                self.failed_executions += 1
                return False, msg, None

        # ── Step 2: Build execution namespace ──
        try:
            namespace = self._build_namespace()
        except Exception as e:
            msg = f"Failed to build execution context: {e}"
            logger.error(f"❌ {msg}")
            record = ExecutionRecord(code, False, msg, traceback.format_exc())
            self.execution_history.append(record)
            self.failed_executions += 1
            return False, msg, traceback.format_exc()

        # ── Step 3: Execute ──
        desc = description or f"Execution #{self.total_executions}"
        logger.info(f"▶️  {desc}")
        logger.info(f"   Code: {len(code)} chars, {code.count(chr(10))+1} lines")

        start_time = time.time()

        try:
            # Execute the code in our controlled namespace
            exec(code, namespace)

            duration = time.time() - start_time

            msg = (
                f"Code executed successfully in {duration:.1f}s "
                f"({code.count(chr(10))+1} lines)"
            )
            logger.info(f"✅ {msg}")

            record = ExecutionRecord(code, True, msg, duration=duration)
            self.execution_history.append(record)
            self.successful_executions += 1

            return True, msg, None

        except Exception as e:
            duration = time.time() - start_time
            error_tb = traceback.format_exc()

            # Try to extract the most useful error info
            error_summary = self._format_error(e, error_tb, code)

            msg = f"Execution error: {error_summary}"
            logger.error(f"❌ {msg}")
            logger.debug(f"Full traceback:\n{error_tb}")

            record = ExecutionRecord(
                code, False, msg, error_tb, duration
            )
            self.execution_history.append(record)
            self.failed_executions += 1

            return False, msg, error_tb

    # ──────────────────────────────────────────────
    # Namespace Builder
    # ──────────────────────────────────────────────

    def _build_namespace(self) -> Dict[str, Any]:
        """
        Build the execution namespace (sandbox) that the generated
        code runs inside. This is the "world" the code can see.
        """
        # Get CATIA objects from the bridge
        ctx = self.bridge.get_execution_context()

        namespace: Dict[str, Any] = {}

        # ── CATIA Objects ──
        namespace["catia"] = ctx.get("catia")
        namespace["part_document"] = ctx.get("part_document")
        namespace["part"] = ctx.get("part")
        namespace["hybrid_shape_factory"] = ctx.get("hybrid_shape_factory")
        namespace["shape_factory"] = ctx.get("shape_factory")
        namespace["origin_planes"] = ctx.get("origin_planes")

        # Convenient aliases
        namespace["sf"] = ctx.get("shape_factory")
        namespace["hsf"] = ctx.get("hybrid_shape_factory")

        # Bodies
        part = ctx.get("part")
        if part:
            try:
                namespace["bodies"] = part.Bodies
                namespace["main_body"] = part.Bodies.Item(1)
            except Exception:
                namespace["bodies"] = None
                namespace["main_body"] = None
        else:
            namespace["bodies"] = None
            namespace["main_body"] = None

        # ── Helper Functions ──
        namespace["create_sketch"] = ctx.get("create_sketch")
        namespace["update"] = ctx.get("update")
        namespace["create_reference"] = ctx.get("create_reference")

        # ── Safe Python Built-ins ──
        import math

        safe_builtins = {
            # Types
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "frozenset": frozenset,
            "bytes": bytes,
            "bytearray": bytearray,
            "type": type,
            # Numeric
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "pow": pow,
            "divmod": divmod,
            # Iterables
            "range": range,
            "len": len,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sorted": sorted,
            "reversed": reversed,
            "any": any,
            "all": all,
            # String / repr
            "repr": repr,
            "format": format,
            "chr": chr,
            "ord": ord,
            # Printing (useful for debugging)
            "print": print,
            # Boolean
            "True": True,
            "False": False,
            "None": None,
            # Type checking
            "isinstance": isinstance,
            "issubclass": issubclass,
            "hasattr": hasattr,
            "getattr": getattr,
            # Math module
            "math": math,
        }
        namespace.update(safe_builtins)

        # Allow `import math` in generated code (safe)
        namespace["__builtins__"] = {
            k: v for k, v in __builtins__.__dict__.items()
            if k not in BLOCKED_BUILTINS
        } if isinstance(__builtins__, type(sys)) else {
            k: v for k, v in __builtins__.items()
            if k not in BLOCKED_BUILTINS
        }

        return namespace

    # ──────────────────────────────────────────────
    # Error Formatting
    # ──────────────────────────────────────────────

    def _format_error(
        self,
        exception: Exception,
        full_traceback: str,
        code: str,
    ) -> str:
        """
        Create a concise, useful error message.
        Tries to identify the failing line in the generated code.
        """
        error_type = type(exception).__name__
        error_msg = str(exception)

        # Try to find the line number in the generated code
        # Look for "File \"<string>\", line X" pattern in traceback
        import re

        line_match = re.search(
            r'File ["\']<string>["\'], line (\d+)', full_traceback
        )

        if line_match:
            line_num = int(line_match.group(1))
            code_lines = code.split("\n")

            if 1 <= line_num <= len(code_lines):
                failing_line = code_lines[line_num - 1].strip()
                return (
                    f"{error_type}: {error_msg} "
                    f"(line {line_num}: `{failing_line}`)"
                )

        return f"{error_type}: {error_msg}"

    # ──────────────────────────────────────────────
    # History & Diagnostics
    # ──────────────────────────────────────────────

    def get_last_error(self) -> Optional[ExecutionRecord]:
        """Get the most recent failed execution record."""
        for record in reversed(self.execution_history):
            if not record.success:
                return record
        return None

    def get_last_success(self) -> Optional[ExecutionRecord]:
        """Get the most recent successful execution record."""
        for record in reversed(self.execution_history):
            if record.success:
                return record
        return None

    def get_history(
        self, limit: int = 10, failures_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get execution history.

        Args:
            limit: Max number of records to return.
            failures_only: If True, only return failed executions.
        """
        records = self.execution_history
        if failures_only:
            records = [r for r in records if not r.success]

        return [r.to_dict() for r in records[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        return {
            "total_executions": self.total_executions,
            "successful": self.successful_executions,
            "failed": self.failed_executions,
            "success_rate": (
                f"{self.successful_executions / self.total_executions * 100:.1f}%"
                if self.total_executions > 0
                else "N/A"
            ),
            "history_size": len(self.execution_history),
        }

    def clear_history(self) -> None:
        """Clear execution history (does not reset counters)."""
        self.execution_history.clear()
        logger.info("Execution history cleared")


# ═══════════════════════════════════════════════════════════════════
# Standalone Test
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    Quick validation test — runs WITHOUT CATIA.
    Tests the validator on sample code.
    """
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    print("=" * 60)
    print("  Code Executor — Validator Test")
    print("=" * 60)

    validator = CodeValidator()

    test_cases = [
        # (description, code, should_pass)
        (
            "Valid CATIA code",
            """
sketch = create_sketch("xy")
factory2D = sketch.OpenEdition()
circle = factory2D.CreateClosedCircle(0.0, 0.0, 25.0)
sketch.CloseEdition()
pad = sf.AddNewPad(sketch, 50.0)
pad.Name = "TestCylinder"
update()
""",
            True,
        ),
        (
            "Blocked import (os)",
            "import os\nos.system('dir')",
            False,
        ),
        (
            "Blocked import (subprocess)",
            "import subprocess\nsubprocess.run(['cmd'])",
            False,
        ),
        (
            "Blocked function (eval)",
            "result = eval('1+1')",
            False,
        ),
        (
            "Blocked function (exec)",
            "exec('print(1)')",
            False,
        ),
        (
            "Blocked function (open)",
            "f = open('test.txt', 'w')",
            False,
        ),
        (
            "Safe math import",
            "import math\nx = math.pi * 25.0\nprint(x)",
            True,
        ),
        (
            "Syntax error",
            "def broken(\n    pass",
            False,
        ),
        (
            "Loop with CATIA calls",
            """
positions = [(10, 10), (20, 20), (30, 30)]
for i, (x, y) in enumerate(positions):
    sk = create_sketch("xy")
    f = sk.OpenEdition()
    f.CreateClosedCircle(float(x), float(y), 5.0)
    sk.CloseEdition()
    p = sf.AddNewPocket(sk, 10.0)
    p.Name = "Hole_" + str(i)
update()
""",
            True,
        ),
        (
            "Blocked: network access",
            "from urllib.request import urlopen\nurlopen('http://evil.com')",
            False,
        ),
    ]

    passed = 0
    failed = 0

    for desc, code, should_pass in test_cases:
        is_valid, msg = validator.validate(code.strip())
        test_passed = is_valid == should_pass

        status = "✅ PASS" if test_passed else "❌ FAIL"
        expected = "should pass" if should_pass else "should block"

        print(f"\n{status} | {desc} ({expected})")
        if not test_passed:
            print(f"       Result: valid={is_valid}, msg={msg}")
            failed += 1
        else:
            passed += 1
            if not is_valid:
                print(f"       Blocked: {msg}")

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)}")
    print(f"{'=' * 60}")