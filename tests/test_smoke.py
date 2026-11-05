"""The deployment smoke gate must reject both false refusals and false answers."""

import sys

import pytest

from scripts import smoke


@pytest.mark.parametrize(
    ("covered", "absent", "expected"),
    [(True, False, 0), (False, False, 1), (True, True, 1)],
)
def test_smoke_requires_grounded_covered_answer_and_absent_refusal(
    monkeypatch, covered, absent, expected
):
    calls = iter([
        (200, "<html></html>"),
        (200, smoke.json.dumps({
            "answered_from_context": covered,
            "retrieved": [{"source": "rules", "section": "1", "page": 1}],
            "citations": ([{"source": "rules", "section": "1", "page": 1}]
                          if covered else []),
        })),
        (200, smoke.json.dumps({"answered_from_context": absent})),
    ])
    monkeypatch.setattr(smoke, "call", lambda *args, **kwargs: next(calls))
    monkeypatch.setattr(sys, "argv", ["smoke.py", "--api", "http://example"])
    assert smoke.main() == expected
