import pytest

from remnant.v3.scenarios import ScenarioFormatError, ScenarioLoader


VALID = """
scenario:
  id: stale-auth
  name: Stale authorization replay
  description: Controlled local test
steps:
  - name: origin-denied
    via: origin
    path: /protected/report
    expect_status: 403
  - name: proxy-replay
    via: proxy
    path: /protected/report
    expect_status: 200
    expect_cache_state: hit
    expect_body_contains: report-canary
"""


def test_loads_valid_scenario():
    scenario = ScenarioLoader().loads(VALID)
    assert scenario.scenario_id == "stale-auth"
    assert [step.via for step in scenario.steps] == ["origin", "proxy"]


@pytest.mark.parametrize("path", [
    "https://attacker.example/path", "//attacker.example/path",
    "/a/../admin", "/a/./b", "/\\host/path",
])
def test_rejects_absolute_and_traversal_paths(path):
    text = VALID.replace("/protected/report", path, 1)
    with pytest.raises(ScenarioFormatError):
        ScenarioLoader().loads(text)


def test_rejects_unsupported_method():
    with pytest.raises(ScenarioFormatError, match="only GET and HEAD"):
        ScenarioLoader().loads(VALID.replace("path: /protected/report", "method: POST\n    path: /protected/report", 1))


def test_rejects_header_injection():
    text = VALID.replace("path: /protected/report", 'path: /protected/report\n    headers:\n      X-Test: "a\\nb"', 1)
    with pytest.raises(ScenarioFormatError, match="header injection"):
        ScenarioLoader().loads(text)


def test_rejects_unknown_fields():
    with pytest.raises(ScenarioFormatError, match="unsupported fields"):
        ScenarioLoader().loads(VALID.replace("via: origin", "via: origin\n    shell: echo unsafe", 1))


def test_rejects_duplicate_step_names():
    text = VALID.replace("name: proxy-replay", "name: origin-denied")
    with pytest.raises(ScenarioFormatError, match="unique"):
        ScenarioLoader().loads(text)


def test_rejects_more_than_100_steps():
    one = """  - name: step-{n}
    via: origin
    path: /health
"""
    steps = "\n".join(one.format(n=i) for i in range(101))
    text = "scenario:\n  id: many\n  name: Many\nsteps:\n" + steps
    with pytest.raises(ScenarioFormatError, match="100"):
        ScenarioLoader().loads(text)


def test_loads_explicit_control_steps():
    scenario = ScenarioLoader().loads("""
scenario:
  id: control
  name: Control
steps:
  - type: control
    name: revoke-user
    operation: revoke
    via: origin
    principal: alice
  - type: control
    name: purge-cache
    operation: purge
    via: proxy
    path: /private
""")
    assert scenario.steps[0].operation == "revoke"
    assert scenario.steps[1].operation == "purge"
