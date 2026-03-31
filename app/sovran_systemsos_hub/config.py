"""Load the Nix-generated config for Sovran_SystemsOS_Hub."""

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