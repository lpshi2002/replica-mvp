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


def _darwin_memory_limit() -> None:
    """Bound new mappings after dyld has established the macOS runtime mappings."""
    import ctypes
    import os
    import resource

    # Apple's vm_map_set_size_limit rejects a limit below the current map size.
    # proc_taskinfo: six uint64_t values followed by twelve int32_t values.
    info = ctypes.create_string_buffer(96)
    proc = ctypes.CDLL("/usr/lib/libproc.dylib")
    proc.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    proc.proc_pidinfo.restype = ctypes.c_int
    if proc.proc_pidinfo(os.getpid(), 4, 0, info, ctypes.sizeof(info)) != ctypes.sizeof(info):
        raise RuntimeError("cannot establish macOS memory limit")
    baseline = int.from_bytes(info.raw[:8], sys.byteorder)
    ceiling = baseline + 128 * 1024 * 1024
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    ceiling = min(ceiling, soft, hard)
    resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))


def main() -> None:
    if sys.platform == "darwin":
        try:
            _darwin_memory_limit()
        except (OSError, ValueError, RuntimeError):
            _fail()
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
