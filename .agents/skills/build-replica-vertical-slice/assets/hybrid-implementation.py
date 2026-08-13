from __future__ import annotations

import json
import sys
from typing import Any


def replicate(request: dict[str, Any]) -> Any:
    """Implement the frozen public contract using request input and assets."""
    raise NotImplementedError("replace with the claim-specific implementation")


def main() -> int:
    request = json.load(sys.stdin)
    result = replicate(request)
    json.dump(result, sys.stdout, ensure_ascii=False, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
