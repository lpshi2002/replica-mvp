from __future__ import annotations

import json
import sys
import tracemalloc


MAX_ENVELOPE_BYTES = 8_000_000
MAX_OUTPUT_BYTES = 1_000_000
MAX_EXECUTION_STEPS = 200_000
MAX_TRACED_MEMORY_BYTES = 64_000_000
SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


def _fail() -> None:
    sys.stderr.write("generated Python execution failed\n")
    raise SystemExit(1)


def main() -> None:
    envelope_bytes = sys.stdin.buffer.read(MAX_ENVELOPE_BYTES + 1)
    if len(envelope_bytes) > MAX_ENVELOPE_BYTES:
        _fail()
    try:
        envelope = json.loads(envelope_bytes)
        source = envelope["source"]
        runtime_input = envelope["runtime_input"]
        if (
            set(envelope) != {"source", "runtime_input"}
            or not isinstance(source, str)
            or not isinstance(runtime_input, dict)
        ):
            _fail()

        namespace = {"__builtins__": SAFE_BUILTINS}
        compiled = compile(source, "<replica-python>", "exec")
        exec(compiled, namespace, namespace)
        replicate = namespace.get("replicate")
        if not callable(replicate):
            _fail()

        steps = 0
        tracemalloc.start()

        def guard(frame, event, argument):
            nonlocal steps
            if (
                event == "line"
                and frame.f_code.co_filename == "<replica-python>"
            ):
                steps += 1
                if steps > MAX_EXECUTION_STEPS:
                    raise RuntimeError("step limit")
                if tracemalloc.get_traced_memory()[1] > (
                    MAX_TRACED_MEMORY_BYTES
                ):
                    raise MemoryError("memory limit")
            return guard

        sys.settrace(guard)
        try:
            output = replicate(runtime_input)
        finally:
            sys.settrace(None)
        output_bytes = json.dumps(
            output,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        if len(output_bytes) > MAX_OUTPUT_BYTES:
            _fail()
    except BaseException:
        _fail()
    sys.stdout.buffer.write(output_bytes)


if __name__ == "__main__":
    main()
