"""Regression test for Starlette 1.1.0+ TemplateResponse keyword-argument style.

Prior to this fix, the three HTML routes called:
    templates.TemplateResponse("name.html", {"request": request, ...})
which passes the context dict as the second positional argument.  With the
updated Starlette/FastAPI versions shipped in NixOS unstable (Starlette 1.1.0,
FastAPI 0.136.3) that positional argument is the template name, causing Jinja2
to receive a dict as a cache key and raise:
    TypeError: unhashable type: 'dict'

The fix updates every call to use keyword arguments:
    templates.TemplateResponse(request=request, name="name.html", context={...})
"""

import ast
import unittest
from pathlib import Path


SERVER_PY = Path(__file__).resolve().parents[1] / "sovran_systemsos_web" / "server.py"


def _template_response_calls(source: str):
    """Return a list of ast.Call nodes that are TemplateResponse calls."""
    tree = ast.parse(source)
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "TemplateResponse":
            calls.append(node)
    return calls


class TemplateResponseSignatureTests(unittest.TestCase):
    def setUp(self):
        self.source = SERVER_PY.read_text()
        self.calls = _template_response_calls(self.source)

    def test_at_least_one_template_response_call_found(self):
        self.assertGreater(len(self.calls), 0, "No TemplateResponse calls found in server.py")

    def test_no_old_style_positional_dict_context(self):
        """No TemplateResponse call should pass a dict literal as its second positional arg.

        The old style was:
            templates.TemplateResponse("name.html", {"request": request, ...})
        where args[0] is a string and args[1] is a Dict node.  That pattern
        triggers the Starlette 1.1.0 bug.
        """
        for call in self.calls:
            positional = call.args
            if len(positional) >= 2 and isinstance(positional[1], ast.Dict):
                self.fail(
                    f"Found old-style TemplateResponse call at line {call.lineno}: "
                    "second positional argument is a dict literal.  "
                    "Use keyword arguments (request=, name=, context=) instead."
                )

    def test_request_not_duplicated_in_context(self):
        """The 'request' key must not appear inside the context= dict when
        request= is already passed as a dedicated keyword argument."""
        for call in self.calls:
            kw_dict = {kw.arg: kw.value for kw in call.keywords if isinstance(kw, ast.keyword)}

            if "request" not in kw_dict:
                continue  # no request= kwarg, nothing to check

            context_node = kw_dict.get("context")
            if not isinstance(context_node, ast.Dict):
                continue

            for key_node in context_node.keys:
                if isinstance(key_node, ast.Constant) and key_node.value == "request":
                    self.fail(
                        f"TemplateResponse at line {call.lineno} passes 'request' both as "
                        "request= keyword argument and inside the context dict."
                    )

    def test_all_calls_use_keyword_arguments(self):
        """Every TemplateResponse call should use keyword arguments for request, name,
        and context rather than relying on positional ordering."""
        for call in self.calls:
            kw_args = {kw.arg for kw in call.keywords if isinstance(kw, ast.keyword)}
            self.assertIn(
                "request",
                kw_args,
                f"TemplateResponse at line {call.lineno} is missing keyword argument 'request='.",
            )
            self.assertIn(
                "name",
                kw_args,
                f"TemplateResponse at line {call.lineno} is missing keyword argument 'name='.",
            )


if __name__ == "__main__":
    unittest.main()
