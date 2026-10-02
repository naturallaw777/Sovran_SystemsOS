"""Guards for the home-IP warnings.

Server + Desktop publishes the home IP address (the domain points at it), so every
place that offers Server + Desktop must say so, and the README section they point
at must exist.

These read the shipped source files like the nix-file checks in test_security.py:
nothing is run and nothing touches the network.
"""

import os
import re
import unittest

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_PHRASE = "home ip address"


def _read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _github_slug(heading):
    slug = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return slug.replace(" ", "-")


class HomeIpWarnings(unittest.TestCase):

    def test_installer_role_card(self):
        src = _read("iso", "installer.py")
        card = re.search(r'\("Server \+ Desktop",\s*"((?:[^"\\]|\\.)*)"', src, re.S)
        self.assertIsNotNone(card, "Server + Desktop role card not found")
        self.assertIn(_PHRASE, card.group(1).lower())

    def test_hub_domain_setup_text(self):
        # domain-prereqs.js is the single source for onboarding, feature setup
        # and domain reconfiguration; the notice must follow every variant.
        js = _read("app", "sovran_systemsos_web", "static", "js", "domain-prereqs.js")
        body = js[js.index("function renderDomainNeedsHtml"):]
        body = body[:body.index("\n}\n")]
        self.assertIn(_PHRASE, body.lower())
        self.assertGreater(body.lower().index(_PHRASE), body.rindex("} else {"),
                           "the notice must come after the last variant, not inside one")

    def test_hub_upgrade_dialog(self):
        html = _read("app", "sovran_systemsos_web", "templates", "index.html")
        dialog = html[html.index('id="upgrade-modal"'):html.index("Security Reset overlay")]
        self.assertIn(_PHRASE, " ".join(dialog.lower().split()))

    def test_readme_and_security_policy(self):
        self.assertIn(_PHRASE, _read("README.md").lower())
        self.assertIn(_PHRASE, " ".join(_read("SECURITY.md").lower().split()))

    def test_links_to_the_readme_section_resolve(self):
        readme = _read("README.md")
        slugs = {_github_slug(m.group(2))
                 for m in re.finditer(r"^(#{1,6})\s+(.+?)\s*$", readme, re.M)}
        links = re.findall(r"\]\(#(server--desktop[^)]*)\)", readme)
        links += re.findall(r"README\.md#(server--desktop[^)\s]*)", _read("SECURITY.md"))
        self.assertTrue(links, "expected links to the home-IP section")
        for anchor in links:
            self.assertIn(anchor, slugs)


if __name__ == "__main__":
    unittest.main()
