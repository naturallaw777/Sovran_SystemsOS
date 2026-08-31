"""Regression tests for the Bitcoin Core Tor IBD gossip Hub option.

These tests intentionally avoid importing the FastAPI application so they can run
in the repository's lightweight test environment without NixOS service access.
"""

import ast
import os
import unittest


_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))


def _read(*parts: str) -> str:
    with open(os.path.join(_REPO_ROOT, *parts), encoding="utf-8") as source:
        return source.read()


def _literal_assignment(source: str, name: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f"Assignment {name} was not found")


class TestBitcoinTorGossipNixWiring(unittest.TestCase):
    def test_integration_layer_maps_tor_gossip_option(self):
        """The integration layer must bridge sovran_systemsOS.features.bitcoin-tor-gossip
        to sovran-bitcoin.bitcoindTorGossip."""
        integration = _read("modules", "sovran-bitcoin-integration.nix")
        self.assertIn("bitcoindTorGossip", integration)
        self.assertIn("bitcoin-tor-gossip", integration)

    def test_hub_option_and_evaluated_state_are_declared(self):
        roles = _read("modules", "core", "roles.nix")
        hub = _read("modules", "core", "sovran-hub.nix")
        self.assertIn("bitcoin-tor-gossip = lib.mkEnableOption", roles)
        self.assertIn("bitcoin-tor-gossip = cfg.features.bitcoin-tor-gossip;", hub)


class TestBitcoinTorGossipHubWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_source = _read("app", "sovran_systemsos_web", "server.py")
        cls.registry = _literal_assignment(cls.server_source, "FEATURE_REGISTRY")

    def test_feature_is_modal_only_and_explains_risk(self):
        feature = next(item for item in self.registry if item["id"] == "bitcoin-tor-gossip")
        self.assertTrue(feature["modal_only"])
        self.assertIn("bitcoin-service", feature["requires"])
        self.assertTrue(any("clearnet" in detail for detail in feature["details"]))
        self.assertTrue(any("bandwidth" in detail for detail in feature["details"]))

    def test_backend_rejects_gossip_without_bitcoin_service(self):
        self.assertIn(
            "Enable the Bitcoin service before advertising its Tor IBD service.",
            self.server_source,
        )

    def test_core_modal_renders_and_controls_the_option(self):
        frontend = _read(
            "app", "sovran_systemsos_web", "static", "js", "service-detail.js"
        )
        self.assertIn("Tor IBD Service Advertising", frontend)
        self.assertIn("svc-detail-related-feature-btn", frontend)
        self.assertIn("handleFeatureToggle(relatedFeat", frontend)


if __name__ == "__main__":
    unittest.main()
