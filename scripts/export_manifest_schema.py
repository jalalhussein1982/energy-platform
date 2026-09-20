"""Print the manifest JSON Schema exported from the Pydantic model (ADR-017).

`make schema` redirects this into schemas/manifest.v1.json; a test asserts the committed file is
current, so the schema can never drift from the model unnoticed.
"""

from __future__ import annotations

import json
import sys

from energy_platform.contracts.manifest import Manifest


def render() -> str:
    return json.dumps(Manifest.model_json_schema(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    sys.stdout.write(render())
