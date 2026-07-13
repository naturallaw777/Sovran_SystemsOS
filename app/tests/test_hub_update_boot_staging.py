import unittest
from pathlib import Path


HUB_NIX = Path(__file__).resolve().parents[2] / "modules" / "core" / "sovran-hub.nix"


def _section(source: str, start: str, end: str) -> str:
    start_idx = source.index(start)
    end_idx = source.index(end, start_idx)
    return source[start_idx:end_idx]


class HubUpdateBootStagingTests(unittest.TestCase):
    def setUp(self):
        self.source = HUB_NIX.read_text()
        self.update_section = _section(
            self.source,
            'update-script = pkgs.writeShellScript "sovran-hub-update.sh" \'\'',
            "# ── Rebuild wrapper script",
        )
        self.rebuild_section = _section(
            self.source,
            'rebuild-script = pkgs.writeShellScript "sovran-hub-rebuild.sh" \'\'',
            "# ── Brave launcher wrapper",
        )

    def test_full_update_uses_boot_not_switch(self):
        self.assertIn("nixos-rebuild boot --flake /etc/nixos", self.update_section)
        self.assertNotIn("nixos-rebuild switch --flake /etc/nixos", self.update_section)

    def test_full_update_marks_reboot_required(self):
        self.assertIn('echo "REBOOT_REQUIRED" > "$STATUS"', self.update_section)

    def test_rebuild_path_keeps_switch_semantics(self):
        self.assertIn("nixos-rebuild switch --flake /etc/nixos", self.rebuild_section)


if __name__ == "__main__":
    unittest.main()
