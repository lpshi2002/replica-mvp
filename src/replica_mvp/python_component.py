from __future__ import annotations

import ast
import ctypes
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn


PYTHON_COMPONENT_LANGUAGE = "replica-python/v1"
PYTHON_ENTRYPOINT = "replicate"
MAX_PYTHON_SOURCE_BYTES = 100_000
MAX_PYTHON_INPUT_BYTES = 1_000_000
MAX_PYTHON_OUTPUT_BYTES = 1_000_000
PYTHON_TIMEOUT_SECONDS = 5
MAX_PYTHON_PROCESS_MEMORY_BYTES = 128 * 1024 * 1024

SAFE_BUILTINS = {
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "float",
    "int",
    "isinstance",
    "len",
    "list",
    "max",
    "min",
    "range",
    "reversed",
    "round",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
    "zip",
}
SAFE_METHODS = {
    "append",
    "clear",
    "copy",
    "count",
    "endswith",
    "extend",
    "get",
    "index",
    "insert",
    "items",
    "join",
    "keys",
    "lower",
    "pop",
    "remove",
    "replace",
    "reverse",
    "setdefault",
    "sort",
    "split",
    "startswith",
    "strip",
    "update",
    "upper",
    "values",
}
ALLOWED_STATEMENTS = (
    ast.FunctionDef,
    ast.Return,
    ast.Assign,
    ast.AugAssign,
    ast.Expr,
    ast.If,
    ast.For,
    ast.Break,
    ast.Continue,
    ast.Pass,
)
ALLOWED_EXPRESSIONS = (
    ast.Name,
    ast.Constant,
    ast.Dict,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Subscript,
    ast.Slice,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.Call,
    ast.Attribute,
    ast.IfExp,
    ast.ListComp,
    ast.DictComp,
    ast.SetComp,
    ast.GeneratorExp,
)
ALLOWED_BINARY_OPERATORS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
)
ALLOWED_UNARY_OPERATORS = (ast.Not, ast.UAdd, ast.USub)
ALLOWED_BOOLEAN_OPERATORS = (ast.And, ast.Or)
ALLOWED_COMPARISON_OPERATORS = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)


def _reject_nonstandard_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard JSON constant: {value}")


def _standard_json_bytes(value: Any, label: str) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError):
        raise ValueError(f"{label} must contain standard JSON") from None


def _valid_identifier(value: str) -> bool:
    return value.isidentifier() and not value.startswith("_")


def _validate_arguments(node: ast.arguments) -> None:
    if (
        node.posonlyargs
        or node.vararg is not None
        or node.kwonlyargs
        or node.kw_defaults
        or node.kwarg is not None
        or node.defaults
        or not all(_valid_identifier(argument.arg) for argument in node.args)
        or any(argument.annotation is not None for argument in node.args)
    ):
        raise ValueError("generated Python uses unsupported function arguments")


def validate_python_component_source(source: Any) -> str:
    if not isinstance(source, str) or not source.strip():
        raise ValueError("generated Python source must not be empty")
    if len(source.encode()) > MAX_PYTHON_SOURCE_BYTES:
        raise ValueError("generated Python source exceeded its size limit")
    try:
        tree = ast.parse(source, filename="<replica-python>", mode="exec")
    except SyntaxError:
        raise ValueError("generated Python source is invalid") from None

    if not tree.body or not all(
        isinstance(statement, ast.FunctionDef) for statement in tree.body
    ):
        raise ValueError("generated Python may contain only function definitions")
    function_names = {
        statement.name for statement in tree.body
        if isinstance(statement, ast.FunctionDef)
    }
    if (
        PYTHON_ENTRYPOINT not in function_names
        or len(function_names) != len(tree.body)
        or not all(_valid_identifier(name) for name in function_names)
    ):
        raise ValueError("generated Python must define one replicate entrypoint")

    replicate = next(
        statement for statement in tree.body
        if isinstance(statement, ast.FunctionDef)
        and statement.name == PYTHON_ENTRYPOINT
    )
    if [argument.arg for argument in replicate.args.args] != ["runtime_input"]:
        raise ValueError(
            "generated Python replicate entrypoint must accept runtime_input"
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            continue
        if isinstance(node, ALLOWED_STATEMENTS):
            if isinstance(node, ast.FunctionDef):
                _validate_arguments(node.args)
                if (
                    node.decorator_list
                    or node.returns is not None
                    or node.type_comment is not None
                ):
                    raise ValueError(
                        "generated Python function metadata is unsupported"
                    )
            continue
        if isinstance(node, ALLOWED_EXPRESSIONS):
            if isinstance(node, ast.Name) and not _valid_identifier(node.id):
                raise ValueError("generated Python uses a forbidden name")
            if isinstance(node, ast.Constant):
                value = node.value
                if (
                    not isinstance(value, (str, int, float, bool, type(None)))
                    or isinstance(value, float)
                    and not math.isfinite(value)
                ):
                    raise ValueError(
                        "generated Python uses an unsupported constant"
                    )
            if isinstance(node, ast.Attribute) and (
                node.attr not in SAFE_METHODS
            ):
                raise ValueError("generated Python uses a forbidden attribute")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if (
                        node.func.id not in SAFE_BUILTINS
                        and node.func.id not in function_names
                    ):
                        raise ValueError(
                            "generated Python calls a forbidden function"
                        )
                elif not (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in SAFE_METHODS
                ):
                    raise ValueError(
                        "generated Python calls a forbidden function"
                    )
                if any(keyword.arg is None for keyword in node.keywords):
                    raise ValueError(
                        "generated Python argument expansion is forbidden"
                    )
            if isinstance(node, ast.Dict) and any(
                key is None for key in node.keys
            ):
                raise ValueError("generated Python dictionary expansion is forbidden")
            continue
        if isinstance(node, ast.BinOp):
            continue
        if isinstance(node, ast.operator):
            if not isinstance(node, ALLOWED_BINARY_OPERATORS):
                raise ValueError(
                    "generated Python uses a forbidden binary operator"
                )
            continue
        if isinstance(node, ast.unaryop):
            if not isinstance(node, ALLOWED_UNARY_OPERATORS):
                raise ValueError(
                    "generated Python uses a forbidden unary operator"
                )
            continue
        if isinstance(node, ast.boolop):
            if not isinstance(node, ALLOWED_BOOLEAN_OPERATORS):
                raise ValueError(
                    "generated Python uses a forbidden boolean operator"
                )
            continue
        if isinstance(node, ast.cmpop):
            if not isinstance(node, ALLOWED_COMPARISON_OPERATORS):
                raise ValueError(
                    "generated Python uses a forbidden comparison operator"
                )
            continue
        if isinstance(
            node,
            (
                ast.arguments,
                ast.arg,
                ast.keyword,
                ast.comprehension,
                ast.expr_context,
            ),
        ):
            continue
        raise ValueError(
            f"generated Python uses forbidden syntax: {type(node).__name__}"
        )

    return source


def python_language_contract() -> dict[str, Any]:
    return {
        "language": PYTHON_COMPONENT_LANGUAGE,
        "entrypoint": f"{PYTHON_ENTRYPOINT}(runtime_input)",
        "source_field": "source",
        "allowed_builtins": sorted(SAFE_BUILTINS),
        "allowed_methods": sorted(SAFE_METHODS),
        "limits": {
            "max_source_bytes": MAX_PYTHON_SOURCE_BYTES,
            "max_input_bytes": MAX_PYTHON_INPUT_BYTES,
            "max_output_bytes": MAX_PYTHON_OUTPUT_BYTES,
            "timeout_seconds": PYTHON_TIMEOUT_SECONDS,
            "max_process_memory_bytes": MAX_PYTHON_PROCESS_MEMORY_BYTES,
        },
        "forbidden": [
            "imports",
            "file access",
            "network access",
            "process creation",
            "eval or exec",
            "classes",
            "decorators",
            "global state",
        ],
    }


def _unix_memory_limit() -> None:
    import resource

    resource.setrlimit(
        resource.RLIMIT_AS,
        (
            MAX_PYTHON_PROCESS_MEMORY_BYTES,
            MAX_PYTHON_PROCESS_MEMORY_BYTES,
        ),
    )


def _assign_windows_memory_job(process: subprocess.Popen[bytes]) -> int:
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
    ]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
    information = ExtendedLimitInformation()
    information.BasicLimitInformation.LimitFlags = 0x100 | 0x2000
    information.ProcessMemoryLimit = MAX_PYTHON_PROCESS_MEMORY_BYTES
    if not kernel32.SetInformationJobObject(
        job,
        9,
        ctypes.byref(information),
        ctypes.sizeof(information),
    ):
        kernel32.CloseHandle(job)
        raise OSError(
            ctypes.get_last_error(),
            "SetInformationJobObject failed",
        )
    if not kernel32.AssignProcessToJobObject(job, process._handle):
        kernel32.CloseHandle(job)
        raise OSError(
            ctypes.get_last_error(),
            "AssignProcessToJobObject failed",
        )
    return int(job)


def _close_windows_job(job: int) -> None:
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(job)


def _run_restricted_python(
    runner: Path,
    input_bytes: bytes,
) -> tuple[int, bytes]:
    preexec_fn = _unix_memory_limit if os.name != "nt" else None
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-S",
            str(runner),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=preexec_fn,
    )
    job = None
    try:
        if os.name == "nt":
            try:
                job = _assign_windows_memory_job(process)
            except OSError:
                process.kill()
                process.wait()
                raise RuntimeError(
                    "generated Python hard sandbox is unavailable"
                ) from None
        try:
            stdout, _ = process.communicate(
                input=input_bytes,
                timeout=PYTHON_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RuntimeError(
                "generated Python exceeded its time limit"
            ) from None
        return process.returncode, stdout
    finally:
        if job is not None:
            _close_windows_job(job)


def execute_python_component(source: str, runtime_input: Any) -> Any:
    validate_python_component_source(source)
    input_bytes = _standard_json_bytes(
        {
            "source": source,
            "runtime_input": runtime_input,
        },
        "generated Python input",
    )
    if len(_standard_json_bytes(runtime_input, "Replica input")) > (
        MAX_PYTHON_INPUT_BYTES
    ):
        raise ValueError("generated Python input exceeded its size limit")

    runner = Path(__file__).with_name("_python_component_runner.py")
    returncode, stdout = _run_restricted_python(runner, input_bytes)
    if returncode != 0:
        raise RuntimeError("generated Python execution failed")
    if len(stdout) > MAX_PYTHON_OUTPUT_BYTES:
        raise RuntimeError("generated Python exceeded its output limit")
    try:
        return json.loads(
            stdout,
            parse_constant=_reject_nonstandard_constant,
        )
    except (UnicodeDecodeError, ValueError):
        raise RuntimeError("generated Python returned invalid JSON") from None
