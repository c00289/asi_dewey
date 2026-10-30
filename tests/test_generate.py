from __future__ import annotations

import json
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from asi_dewey import Brain
from asi_dewey.automation.cli import main
from asi_dewey.brain import ENV_CONFIG, ENV_OUT
from asi_dewey.errors import CommandError, NotFound
from asi_dewey.generate import DiagramFactory, DocumentFactory, Param, Spec
from asi_dewey.generate.figures import build_diagram

DIAGRAMS = {"schema_map", "lifecycle_overview", "phase_flow", "task_flow"}
DOCUMENTS = {"safety_plan", "status_report", "handbook"}


def fuller(brain: Brain) -> Brain:
    """More rows on top of ``seeded``: a blocked phase, a second task, a ticket, a QMS document."""
    brain.execute("create", entity="safety_plan_row", data={
        "order": 2, "lifecycle_phase": "3. Functional Safety Concept (FSC)", "deliverable": "FSC",
        "author": "Systems", "status": "Blocked", "reviewer_pat": 1, "gate_reviewer": "Gate 3",
    })
    brain.execute("create", entity="task", data={"order": 2, "task_class": "deliverable", "name": "Write FSC",
                                               "start": "2026-10-25"})
    brain.execute("create", entity="jira_ticket", data={"order": 1, "name": "WL-1", "status": "open", "url": "https://x.y/WL-1"})
    brain.execute("create", entity="qms_document", data={"order": 1, "name": "QP-06", "url": "https://x.y/qp06"})
    brain.execute("create", entity="person", data={"order": 1, "person_class": "role", "nickname": "FuSa", "text": "x"})
    return brain


# -- catalog and specs ----------------------------------------------------
def test_catalogs_are_listed_without_a_name(brain):
    diagrams = brain.execute("diagram").data["catalog"]
    documents = brain.execute("document").data["catalog"]
    assert {s["key"] for s in diagrams} == DIAGRAMS and {s["key"] for s in documents} == DOCUMENTS
    for spec in (*diagrams, *documents):
        assert spec["title"] and spec["description"] and isinstance(spec["params"], list)
    phase = next(s for s in diagrams if s["key"] == "phase_flow")
    assert phase["params"][0] == {
        "name": "phase", "help": phase["params"][0]["help"], "required": True, "default": None,
        "lookup": "lifecycle_phase",
    }
    assert {"diagram", "document"} <= set(brain.status()["commands"])
    assert DiagramFactory.keys() == [s["key"] for s in diagrams]
    assert DocumentFactory.keys() == [s["key"] for s in documents]


def test_spec_validates_params():
    spec = Spec("x", "X", params=(Param("a", required=True), Param("b", default="2")))
    assert spec.check_params({"a": "1"}) == {"a": "1", "b": "2"}
    assert spec.check_params({"a": 1, "b": " "}) == {"a": "1", "b": "2"}
    with pytest.raises(CommandError, match="missing required param 'a'"):
        spec.check_params({})
    with pytest.raises(CommandError, match="unknown param"):
        spec.check_params({"a": "1", "zz": "3"})
    with pytest.raises(NotFound, match="known: schema_map"):
        DiagramFactory.create("nope")
    with pytest.raises(ValueError):
        Spec("bad key", "X")
    with pytest.raises(ValueError):
        DiagramFactory.register(Spec("schema_map", "dup"))(lambda brain, params: None)


# -- diagrams -----------------------------------------------------------------
def test_schema_map_on_empty_brain(brain, tmp_path):
    result = brain.execute("diagram", name="schema_map", out=str(tmp_path / "gen"))
    assert result.ok, result.errors
    data = result.data
    assert set(data["paths"]) == {"png", "svg", "dot", "mmd"}
    assert all(Path(p).is_file() for p in data["paths"].values())
    assert data["primary"] == data["paths"]["png"] and data["name"] == "schema_map"
    assert data["nodes"] == len(brain.registry) and data["edges"] == 0 and data["issues"] == []
    assert json.loads(result.to_json())["data"]["size"] == data["size"]


def test_lifecycle_overview_and_task_flow_on_seeded(seeded, tmp_path):
    fuller(seeded)
    for name in ("lifecycle_overview", "task_flow"):
        result = seeded.execute("diagram", name=name, out=str(tmp_path))
        assert result.ok, result.errors
        assert result.data["issues"] == [] and result.warnings == []
        assert (tmp_path / f"{name}.png").is_file() and (tmp_path / f"{name}.mmd").is_file()
    overview = seeded.execute("diagram", name="lifecycle_overview", out=str(tmp_path)).data
    assert overview["nodes"] == len(seeded.lookups["lifecycle_phase"]) and overview["edges"] == overview["nodes"] - 1
    dot = (tmp_path / "lifecycle_overview.dot").read_text(encoding="utf-8")
    assert "1 deliverables, 0 done" in dot
    only = seeded.execute("diagram", name="task_flow", out=str(tmp_path), param={"class": "deliverable"}).data
    assert only["nodes"] == 1
    assert not seeded.execute("diagram", name="task_flow", param=["class=mystery"]).ok


def test_phase_flow_params(seeded, tmp_path):
    missing = seeded.execute("diagram", name="phase_flow", out=str(tmp_path))
    assert not missing.ok and "phase" in missing.errors[0]
    by_number = seeded.execute("diagram", name="phase_flow", out=str(tmp_path), param=["phase=1"])
    assert by_number.ok, by_number.errors
    first = Path(by_number.data["paths"]["mmd"]).read_text(encoding="utf-8")
    by_label = seeded.execute("diagram", name="phase_flow", out=str(tmp_path),
                              param={"phase": "1. Concept Development"})
    assert by_label.ok and Path(by_label.data["paths"]["mmd"]).read_text(encoding="utf-8") == first
    assert by_number.data["nodes"] == 5  # start, author, verification, reviewer, end
    assert "FuSa Engineer" in first and "Level U3" in first
    unknown = seeded.execute("diagram", name="phase_flow", param={"phase": "42"})
    assert not unknown.ok and "known:" in unknown.errors[0]


def test_unknown_names_and_formats_fail_cleanly(brain, tmp_path):
    result = brain.execute("diagram", name="nope")
    assert not result.ok and "schema_map" in result.errors[0] and "lifecycle_overview" in result.errors[0]
    result = brain.execute("document", name="nope")
    assert not result.ok and "safety_plan" in result.errors[0]
    assert not brain.execute("diagram", name="schema_map", param=["x=1"]).ok
    assert not brain.execute("diagram", name="schema_map", formats="png,bmp", out=str(tmp_path)).ok
    only = brain.execute("diagram", name="schema_map", formats="svg", out=str(tmp_path))
    assert only.ok and list(only.data["paths"]) == ["svg"] and only.data["primary"].endswith(".svg")


def test_layout_warning_is_captured_as_issues(tmp_path):
    from asi_escher import Diagram, LayoutWarning

    d = Diagram("Crowded", "flowchart")
    d.start()
    d.end()
    for i in range(3):
        d.action(f"a{i}", f"step {i}")
        d.edge("start", f"a{i}", "a long label that will not fit between two nodes " * 2)
        d.edge(f"a{i}", "end", "another very long label that competes for the same space " * 2)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        built = build_diagram(d, tmp_path, "crowded", formats=("mmd",))
    assert not any(issubclass(w.category, LayoutWarning) for w in caught)
    assert built["issues"] and all({"kind", "message", "edge", "node"} <= set(i) for i in built["issues"])
    json.dumps(built)  # plain data only


# -- documents ----------------------------------------------------------------
def test_safety_plan_document(seeded, tmp_path):
    fuller(seeded)
    out = tmp_path / "gen"
    result = seeded.execute("document", name="safety_plan", out=str(out), actor="agent")
    assert result.ok, result.errors
    data = result.data
    assert set(data["paths"]) == {"md", "pdf", "docx"} and all(Path(p).is_file() for p in data["paths"].values())
    assert data["primary"] == data["paths"]["pdf"] and data["pages"] >= 2 and data["issues"] == []
    assert result.warnings == []
    md = Path(data["paths"]["md"]).read_text(encoding="utf-8")
    assert "![Figure 1: Safety lifecycle overview](figures/lifecycle_overview.png)" in md
    assert (out / "figures" / "lifecycle_overview.png").is_file() and (out / "figures" / "phase_flow_1.png").is_file()
    assert [f["name"] for f in data["diagrams"]] == ["lifecycle_overview", "phase_flow_1", "phase_flow_3"]
    assert all(f["issues"] == [] and Path(f["png"]).is_file() for f in data["diagrams"])
    assert data["diagrams"][1]["nodes"] == 5 and isinstance(data["diagrams"][0]["size"], list)
    assert "| Author | agent |" in md and "Wheel Loader" in md and "not the controlled" in md.lower()
    assert "[QP-06](https://x.y/qp06)" in md and "Gate 3" in md
    assert data["stats"]["figures"] == 3 and data["stats"]["tables"] >= 5


def test_status_report_and_handbook(seeded, tmp_path):
    fuller(seeded)
    report = seeded.execute("document", name="status_report", out=str(tmp_path))
    assert report.ok, report.errors
    md = Path(report.data["paths"]["md"]).read_text(encoding="utf-8")
    assert "[WL-1](https://x.y/WL-1)" in md and "| Fact | 2 |" in md
    assert [f["name"] for f in report.data["diagrams"]] == ["task_flow", "lifecycle_overview"]
    book = seeded.execute("document", name="handbook", out=str(tmp_path))
    assert book.ok, book.errors
    md = Path(book.data["paths"]["md"]).read_text(encoding="utf-8")
    assert "## A Schema map" in md and "![Figure 1: Entities and their row counts](figures/schema_map.png)" in md
    assert "### 2.1 role" in md and "[JIRA](https://x.y/z)" in md


def test_handbook_and_status_report_on_empty_database(brain, tmp_path):
    for name in ("handbook", "status_report", "safety_plan"):
        result = brain.execute("document", name=name, out=str(tmp_path))
        assert result.ok, (name, result.errors)
        assert Path(result.data["paths"]["pdf"]).stat().st_size > 1000
    md = (tmp_path / "handbook.md").read_text(encoding="utf-8")
    assert "No facts recorded." in md and "No links recorded." in md


def test_locked_pdf_falls_back_to_timestamped_stem(seeded, tmp_path, monkeypatch):
    import asi_gutenberg.pipeline as pipeline

    real = pipeline.render_pdf
    calls: list[str] = []

    def locked_once(doc, path, **kw):
        calls.append(path)
        if len(calls) == 1:
            raise PermissionError("locked")
        return real(doc, path, **kw)

    monkeypatch.setattr(pipeline, "render_pdf", locked_once)
    result = seeded.execute("document", name="handbook", out=str(tmp_path))
    assert result.ok, result.errors
    pdf = Path(result.data["paths"]["pdf"])
    assert pdf.is_file() and pdf.stem.startswith("handbook_") and pdf.stem[len("handbook_"):].replace("-", "").isdigit()
    assert any("locked" in w for w in result.warnings) and len(calls) == 2


def test_audit_and_events_after_a_build(seeded, tmp_path):
    seen: list[str] = []
    seeded.events.subscribe("generated", lambda topic, event: seen.append(event["name"]))
    seeded.execute("diagram", name="schema_map", out=str(tmp_path), actor="bot")
    tail = seeded.storage.audit_tail(1)[0]
    assert tail["action"] == "generate" and tail["actor"] == "bot" and tail["entity"] == "schema_map"
    assert tail["payload"]["kind"] == "diagram" and tail["payload"]["paths"]["png"].endswith("schema_map.png")
    assert seeded.events.last(1)[0]["topic"] == "generated" and seen == ["schema_map"]
    seeded.execute("document", name="handbook", out=str(tmp_path))
    assert seeded.storage.audit_tail(1)[0]["payload"] == {
        "kind": "document", "paths": seeded.events.last(1)[0]["paths"],
    }


def test_wire_format_and_script(seeded, tmp_path):
    result = seeded.execute_dict({
        "verb": "diagram",
        "args": {"name": "phase_flow", "param": {"phase": "1"}, "out": str(tmp_path), "formats": "mmd"},
        "actor": "claude",
    })
    assert result.ok, result.errors
    script = tmp_path / "steps.jsonl"
    script.write_text(
        json.dumps({"verb": "document", "args": {"name": "handbook", "out": str(tmp_path)}, "actor": "claude"}) + "\n"
        + json.dumps({"verb": "diagram", "args": {"name": "task_flow", "out": str(tmp_path)}}) + "\n",
        encoding="utf-8",
    )
    run = seeded.execute("run", path=str(script))
    assert run.ok and run.data["steps"] == 2
    assert seeded.storage.audit_tail(2)[-1]["actor"] == "claude"


# -- output folder ------------------------------------------------------------
def test_out_dir_precedence(tmp_path, monkeypatch):
    with Brain(tmp_path / "test.db") as b:
        assert b.out_dir == str(tmp_path / "out") and b.status()["out_dir"] == b.out_dir
    with Brain(":memory:") as b:
        assert b.out_dir == "out"
    config = tmp_path / "dewey.toml"
    config.write_text('db = "cfg.db"\nout = "generated"\n', encoding="utf-8")
    monkeypatch.setenv(ENV_CONFIG, str(config))
    with Brain(tmp_path / "test.db") as b:
        assert Path(b.out_dir) == (tmp_path / "generated").resolve()
    monkeypatch.setenv(ENV_OUT, str(tmp_path / "env_out"))
    with Brain(tmp_path / "test.db") as b:
        assert b.out_dir == str(tmp_path / "env_out")
    with Brain(tmp_path / "test.db", out_dir=tmp_path / "arg_out") as b:
        assert b.out_dir == str(tmp_path / "arg_out")
        built = b.execute("diagram", name="schema_map", formats="mmd")
        assert built.ok and Path(built.data["paths"]["mmd"]).parent == tmp_path / "arg_out"
        explicit = b.execute("diagram", name="schema_map", formats="mmd", out=str(tmp_path / "explicit"))
        assert Path(explicit.data["paths"]["mmd"]).parent == tmp_path / "explicit"


# -- CLI and start-up cost ----------------------------------------------------
def test_cli_diagram_and_document(tmp_path, capsys):
    db = str(tmp_path / "cli.db")
    code = main(["--db", db, "diagram", "schema_map", "--out", str(tmp_path / "gen")])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["ok"] and payload["verb"] == "diagram"
    assert Path(payload["data"]["paths"]["png"]).is_file()
    code = main(["--db", db, "--compact", "diagram"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and {s["key"] for s in payload["data"]["catalog"]} == DIAGRAMS
    code = main(["--db", db, "diagram", "phase_flow", "--out", str(tmp_path), "--param", "phase=2",
                 "--formats", "svg,mmd"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and set(payload["data"]["paths"]) == {"svg", "mmd"}
    code = main(["--db", db, "diagram", "phase_flow"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 and "phase" in payload["errors"][0]
    code = main(["--db", db, "document", "handbook", "--out", str(tmp_path / "gen")])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["data"]["primary"].endswith("handbook.pdf")


def test_importing_asi_dewey_does_not_import_the_generators():
    code = (
        "import sys, asi_dewey, asi_dewey.commands, asi_dewey.generate\n"
        "from asi_dewey import Brain\n"
        "Brain(':memory:').execute('diagram')\n"
        "heavy = [m for m in ('matplotlib', 'reportlab', 'docx', 'asi_escher', 'asi_gutenberg') if m in sys.modules]\n"
        "print(heavy)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]", out.stdout
