"""One test (or group) per requirement in the screening brief.

Offline: no network, no LLM calls. The LLM is replaced by a fake client so the
tests prove how the pipeline treats model output. The committed
data/raw_source.html and data/casino.json are checked as real evidence.

Run: python -m pytest -v
"""
import json
import re
import subprocess
from types import SimpleNamespace

import pytest

import build_page
import common
import extractor
import fetcher
import ledger
import llm_wrapper
import review
import run as runner
from common import StepError

ROOT = common.ROOT
RAW = ROOT / "data" / "raw_source.html"
CASINO = ROOT / "data" / "casino.json"
SOURCE = common.DEFAULT_SOURCE


def real_blocks():
    return extractor.extract_blocks(RAW.read_text(encoding="utf-8"))


def good_answer():
    return [
        {"casino_name": "BetMGM Casino", "welcome_bonus": "100% up to 1,000 USD + 25 USD free",
         "wagering_requirement": 15, "minimum_deposit": "10 USD"},
        {"casino_name": "Caesars Palace Casino", "welcome_bonus": "100% up to 1,000 USD",
         "wagering_requirement": 15, "minimum_deposit": "20 USD"},
        {"casino_name": "bet365 Casino", "welcome_bonus": "100% up to 1,000 USD + 1,000 bonus spins",
         "wagering_requirement": 20, "minimum_deposit": "10 USD"},
    ]


class FakeClient:
    """Stands in for google.genai.Client. answers: {model: records | Exception}."""
    def __init__(self, answers):
        self.answers, self.calls = answers, []
        self.models = SimpleNamespace(generate_content=self.generate_content)

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents))
        a = self.answers.get(model, llm_wrapper.genai_errors.ClientError(404, {"error": {"message": "unknown"}}))
        if isinstance(a, Exception):
            raise a
        return SimpleNamespace(text=json.dumps({"casinos": a}))


@pytest.fixture
def fake_llm(monkeypatch, tmp_path):
    """Point the LLM step at temp files and a fake client."""
    blocks = real_blocks()
    unstructured = tmp_path / "unstructured_cache.txt"
    unstructured.write_text(json.dumps(blocks), encoding="utf-8")
    out = tmp_path / "casino.json"
    monkeypatch.setattr(llm_wrapper, "UNSTRUCTURED", unstructured)
    monkeypatch.setattr(llm_wrapper, "CASINO_JSON", out)
    monkeypatch.setattr(llm_wrapper.time, "sleep", lambda s: None)

    def install(answers):
        client = FakeClient(answers)
        monkeypatch.setattr(llm_wrapper, "get_client", lambda: client)
        return client
    return SimpleNamespace(install=install, out=out, blocks=blocks)


# --- Scraper: "Pulls 3 casinos from one public source" ---------------------------------

def test_pulls_exactly_3_casinos_from_one_public_source():
    blocks = real_blocks()
    assert len(blocks) == 3
    assert [b["casino"] for b in blocks] == ["BetMGM Casino Bonus", "Caesars Palace Casino Offer", "bet365 Casino Bonus"]
    assert {b["source_url"] for b in blocks} == {SOURCE}


def test_extractor_fails_loudly_when_layout_changes():
    with pytest.raises(StepError, match="no <article>"):
        extractor.extract_blocks("<html><body><p>nothing here</p></body></html>")
    with pytest.raises(StepError, match="found 1 casino rows"):
        extractor.extract_blocks(
            "<article class='article'><table><tr><th>Casino</th><th>Offer</th></tr>"
            "<tr><td>A</td><td>B</td></tr></table></article>")


# --- Scraper: "Respects robots.txt and does not bypass logins, CAPTCHAs or blocks" -------

def test_respects_robots_txt(monkeypatch):
    monkeypatch.setattr(fetcher.RobotFileParser, "read", lambda self: None)
    monkeypatch.setattr(fetcher.RobotFileParser, "can_fetch", lambda self, ua, url: False)
    called = []
    monkeypatch.setattr(fetcher.requests, "get", lambda *a, **k: called.append(1))
    with pytest.raises(StepError, match="robots.txt"):
        fetcher.fetch(SOURCE)
    assert called == [], "page must not be requested when robots.txt disallows it"


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_stops_when_blocked_instead_of_bypassing(monkeypatch, status):
    monkeypatch.setattr(fetcher, "check_robots", lambda url: None)
    monkeypatch.setattr(fetcher.requests, "get", lambda *a, **k: SimpleNamespace(status_code=status, text=""))
    with pytest.raises(StepError, match="blocked"):
        fetcher.fetch(SOURCE)


def test_stops_on_captcha_page(monkeypatch):
    monkeypatch.setattr(fetcher, "check_robots", lambda url: None)
    page = SimpleNamespace(status_code=200, text="<html>Please solve this CAPTCHA</html>", raise_for_status=lambda: None)
    monkeypatch.setattr(fetcher.requests, "get", lambda *a, **k: page)
    with pytest.raises(StepError, match="CAPTCHA"):
        fetcher.fetch(SOURCE)


def test_sends_identifying_user_agent(monkeypatch):
    monkeypatch.setattr(fetcher, "check_robots", lambda url: None)
    seen = {}

    def get(url, headers, timeout):
        seen.update(headers)
        return SimpleNamespace(status_code=200, text="<article>ok</article>", raise_for_status=lambda: None)
    monkeypatch.setattr(fetcher.requests, "get", get)
    fetcher.fetch(SOURCE)
    assert "Bot" in seen["User-Agent"], "honest bot UA, not a spoofed browser"


# --- Scraper: "Uses a language model ... to turn free-text terms into structured fields" --

def test_llm_receives_the_free_text_and_produces_the_json(fake_llm):
    client = fake_llm.install({llm_wrapper.MODEL: good_answer(), "gemini-3.5-flash": good_answer()})
    llm_wrapper.run()
    sent = client.calls[0][1]
    for b in fake_llm.blocks:
        assert b["text"] in sent, "the scraped free text must be what the model sees"
    data = json.loads(fake_llm.out.read_text(encoding="utf-8"))
    assert data["models"] == [llm_wrapper.MODEL, "gemini-3.5-flash"]
    assert [c["wagering_requirement"] for c in data["casinos"]] == [15, 15, 20]


def test_llm_hallucination_is_rejected(fake_llm):
    bad = good_answer()
    bad[0]["wagering_requirement"] = 35  # not in the source text
    fake_llm.install({llm_wrapper.MODEL: bad, "gemini-3.5-flash": bad})
    with pytest.raises(StepError, match="wagering 35x .* not found in source"):
        llm_wrapper.run()
    assert not fake_llm.out.exists(), "nothing is written when the model invents a number"


def test_models_must_agree(fake_llm):
    other = good_answer()
    # "25" is in BetMGM's text (the $25 free credit), so it passes the source check;
    # only the cross-model comparison can catch it.
    other[0]["minimum_deposit"] = "25 USD"
    fake_llm.install({llm_wrapper.MODEL: good_answer(), "gemini-3.5-flash": other})
    with pytest.raises(StepError, match="disagree on minimum_deposit"):
        llm_wrapper.run()


def test_overloaded_model_falls_back(fake_llm):
    overloaded = llm_wrapper.genai_errors.ServerError(503, {"error": {"message": "high demand"}})
    client = fake_llm.install({llm_wrapper.MODEL: overloaded, "gemini-3.5-flash": good_answer(),
                               "gemini-3.7-flash": good_answer()})
    llm_wrapper.run()
    assert [m for m, _ in client.calls].count(llm_wrapper.MODEL) == llm_wrapper.RETRIES_PER_MODEL
    assert json.loads(fake_llm.out.read_text())["models"] == ["gemini-3.5-flash", "gemini-3.7-flash"]


def test_no_api_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(StepError, match="no API key"):
        llm_wrapper.get_client()


# --- Scraper: "Extracts four fields per casino and writes them to a JSON file" -----------

def test_committed_json_has_3_casinos_with_the_4_fields():
    data = llm_wrapper.validate(CASINO)
    assert len(data["casinos"]) == 3
    for c in data["casinos"]:
        assert re.search(r"\d", c["welcome_bonus"])                        # Welcome bonus
        assert isinstance(c["wagering_requirement"], int)                  # Wagering (multiplier)
        assert re.fullmatch(r"\d[\d,.]* [A-Z]{3}", c["minimum_deposit"])   # Minimum deposit, e.g. "20 EUR"
        assert c["source_url"] == SOURCE                                   # Source URL


def test_validation_rejects_bad_json(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(StepError, match="not valid JSON"):
        llm_wrapper.validate(p)
    p.write_text(json.dumps({"casinos": good_answer()[:2]}), encoding="utf-8")
    with pytest.raises(StepError, match="expected 3"):
        llm_wrapper.validate(p)


# --- "Typing the data in by hand does not meet the requirement" -------------------------

def test_committed_json_matches_the_scraped_page():
    """Every number in casino.json is traceable to the saved source HTML."""
    data = json.loads(CASINO.read_text(encoding="utf-8"))
    for c, block in zip(data["casinos"], real_blocks()):
        llm_wrapper.check_against_source(c, block["text"])
        assert block["casino"].startswith(c["casino_name"].split()[0])


# --- Every step verifies its output (no silent failures) --------------------------------

def test_missing_or_empty_output_raises(tmp_path):
    with pytest.raises(StepError, match="does not exist"):
        common.verify_file(tmp_path / "nope.txt", "t")
    (tmp_path / "empty.txt").write_text("")
    with pytest.raises(StepError, match="0 bytes"):
        common.verify_file(tmp_path / "empty.txt", "t")


# --- Web page: "A table of the 3 casinos, generated from the JSON file ... readable on a phone"

@pytest.fixture
def built_page(monkeypatch, tmp_path):
    monkeypatch.setattr(build_page, "DOCS", tmp_path)
    monkeypatch.setattr(build_page, "INDEX_HTML", tmp_path / "index.html")
    monkeypatch.setattr(build_page, "PUBLIC_JSON", tmp_path / "casino.json")
    build_page.run()
    return (tmp_path / "index.html").read_text(encoding="utf-8")


def test_page_is_a_table_generated_from_the_json(built_page):
    data = json.loads(CASINO.read_text(encoding="utf-8"))
    assert built_page.count("<tr><td") == 3
    for c in data["casinos"]:
        assert c["casino_name"] in built_page
        assert f'>{c["wagering_requirement"]}x<' in built_page
        assert c["minimum_deposit"] in built_page
    assert "<table" in built_page


def test_page_is_readable_on_a_phone(built_page):
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in built_page
    assert "@media (max-width: 640px)" in built_page  # rows become stacked cards


def test_page_escapes_scraped_text(monkeypatch, tmp_path):
    data = json.loads(CASINO.read_text(encoding="utf-8"))
    data["casinos"][0]["casino_name"] = "<script>alert(1)</script>"
    evil = tmp_path / "evil.json"
    evil.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(build_page, "CASINO_JSON", evil)
    monkeypatch.setattr(build_page, "DOCS", tmp_path)
    monkeypatch.setattr(build_page, "INDEX_HTML", tmp_path / "index.html")
    monkeypatch.setattr(build_page, "PUBLIC_JSON", tmp_path / "casino.json")
    build_page.run()
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html


def test_published_page_matches_committed_json():
    page = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert json.loads((ROOT / "docs" / "casino.json").read_text()) == json.loads(CASINO.read_text())
    for c in json.loads(CASINO.read_text())["casinos"]:
        assert c["casino_name"] in page


# --- "Runs with a single command" + ledger/review -----------------------------------------

@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """Run run.main() with stub steps writing into a temp project root."""
    for mod in (runner, ledger, review):
        monkeypatch.setattr(mod, "ROOT", tmp_path)
    page, cj = tmp_path / "index.html", tmp_path / "casino.json"
    monkeypatch.setattr(review, "INDEX_HTML", page)
    monkeypatch.setattr(review, "CASINO_JSON", cj)

    def step(name, fn=None):
        def go():
            if fn:
                fn()
            out = tmp_path / f"{name}.out"
            out.write_text("ok")
            print(f"{name} ran")
            return [out]
        return SimpleNamespace(run=go)

    def build():
        cj.write_text(json.dumps({"casinos": [{"casino_name": "X"}]}))
        page.write_text("<td>X</td>")
    return SimpleNamespace(root=tmp_path, step=step, build=build)


def test_single_command_runs_all_steps_and_ticks_checklist(monkeypatch, sandbox):
    s = sandbox
    monkeypatch.setattr(runner, "PIPELINE", [("fetch", s.step("fetch")), ("extract", s.step("extract")),
                                             ("structure", s.step("structure")), ("build_page", s.step("build_page", s.build))])
    assert runner.main() == 0
    checklist = next(s.root.glob("runs/*/checklist.md")).read_text()
    assert checklist.count("- [x]") == 4 and "- [ ]" not in checklist
    for name in ("fetch", "extract", "structure", "build_page"):
        assert next(s.root.glob(f"runs/*/logs/{name}.log")).stat().st_size > 0


def test_failed_step_is_retried_then_reported(monkeypatch, sandbox):
    s, attempts = sandbox, []

    def boom():
        attempts.append(1)
        raise StepError("[extractor] layout changed")
    monkeypatch.setattr(runner, "PIPELINE", [("fetch", s.step("fetch")), ("extract", SimpleNamespace(run=boom)),
                                             ("structure", s.step("structure")), ("build_page", s.step("build_page", s.build))])
    assert runner.main() == 1
    assert len(attempts) == runner.MAX_PASSES
    checklist = next(s.root.glob("runs/*/checklist.md")).read_text()
    assert "- [x] **fetch**" in checklist and "- [ ] **extract**" in checklist
    assert "layout changed" in checklist


def test_step_that_claims_success_but_writes_nothing_fails(monkeypatch, sandbox):
    s = sandbox

    def liar():
        print("done!")
        empty = s.root / "empty.out"
        empty.write_text("")
        return [empty]
    monkeypatch.setattr(runner, "PIPELINE", [("fetch", SimpleNamespace(run=liar)), ("extract", s.step("extract")),
                                             ("structure", s.step("structure")), ("build_page", s.step("build_page", s.build))])
    assert runner.main() == 1
    assert "0 bytes" in next(s.root.glob("runs/*/checklist.md")).read_text()


# --- Repo hygiene ------------------------------------------------------------------------

def test_api_key_is_not_committed():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert ".env" not in tracked
    key_like = re.compile(r"AQ\.[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}")
    for f in tracked:
        p = ROOT / f
        if p.suffix in {".py", ".md", ".json", ".txt", ".example", ".html"}:
            assert not key_like.search(p.read_text(encoding="utf-8", errors="ignore")), f"key-like string in {f}"
