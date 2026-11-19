import ast
import json

from charts import bar_spec, pie_spec


def test_pie_spec():
    assert pie_spec("A", 0, 0, 0) is None
    s = pie_spec("A", 2, 1, 3)
    assert [v["次數"] for v in s["data"]["values"]] == [2, 1, 3]
    json.dumps(s)


def test_bar_spec_has_all_players():
    s = bar_spec(["A", "B"], [30, -30])
    assert len(s["data"]["values"]) == 2
    json.dumps(s)


def test_app_has_no_bare_expressions_streamlit_would_display():
    tree = ast.parse(open("app.py", encoding="utf-8").read())
    bad = [n.lineno for n in ast.walk(tree)
           if isinstance(n, ast.Expr) and not isinstance(n.value, ast.Call)
           and not (isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    assert bad == []
