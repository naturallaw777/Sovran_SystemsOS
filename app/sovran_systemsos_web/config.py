"""Load the Nix-generated config and build-time versions for Sovran_SystemsOS_Hub."""

import json
import os


def load_config() -> dict:
    """Read config from the path injected by the Nix derivation."""
    path = os.environ.get(
        "SOVRAN_HUB_CONFIG",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.json",
        ),
    )
    try:
        with open(path, "r") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"refresh_interval": 5, "command_method": "systemctl", "services": []}


def load_versions() -> dict:
    """Read the Nix-generated or fallback build-time package versions."""
    path = os.environ.get("SOVRAN_HUB_VERSIONS")
    if not path:
        # Candidate 1: parent folder (same as config.json, typical for Nix layout)
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidate1 = os.path.join(parent_dir, "versions.json")
        if os.path.exists(candidate1):
            path = candidate1
        else:
            # Candidate 2: local package folder (dev folder structure)
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "versions.json")

    try:
        with open(path, "r") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
