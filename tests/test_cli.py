import json
import re

from git_pulse import __version__
from git_pulse.cli import main

from .conftest import Repo


def run(capsys, *args):
    code = main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_version(capsys):
    try:
        main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == 2
    assert "usage" in capsys.readouterr().out


def test_every_command_table_and_json(repo, capsys):
    for cmd in (
        "summary",
        "timeline",
        "contributors",
        "bus-factor",
        "churn",
        "hotspots",
        "newcomers",
        "merges",
        "heatmap",
    ):
        code, out, err = run(capsys, cmd, "-C", str(repo.path))
        assert code == 0, err
        assert out.strip()
        code, out, err = run(capsys, cmd, "-C", str(repo.path), "--format", "json")
        assert code == 0, err
        json.loads(out)


def test_contributors_table(repo, capsys):
    _, out, _ = run(capsys, "contributors", "-C", str(repo.path))
    assert "Alice Anders" in out and "alice@old-laptop.local" not in out


def test_summary_json(repo, capsys):
    _, out, _ = run(capsys, "summary", "-C", str(repo.path), "-f", "json")
    data = json.loads(out)
    assert data["commits"] == 16
    assert data["first_commit"].startswith("2024-01-01T09:00:00")


def test_top_and_exclude(repo, capsys):
    _, out, _ = run(capsys, "churn", "-C", str(repo.path), "-f", "json", "--top", "2", "--exclude", "src/core.py")
    rows = json.loads(out)
    assert len(rows) == 2 and all(r["path"] != "src/core.py" for r in rows)
    _, out, _ = run(capsys, "churn", "-C", str(repo.path), "-f", "json", "--top", "0", "--include-generated")
    assert "package-lock.json" in {r["path"] for r in json.loads(out)}


def test_bus_factor_min_gate(repo, capsys):
    code, _, _ = run(capsys, "bus-factor", "-C", str(repo.path), "--min", "2")
    assert code == 0
    code, _, err = run(capsys, "bus-factor", "-C", str(repo.path), "--min", "3")
    assert code == 1 and "below" in err


def test_threshold_validation(repo, capsys):
    try:
        main(["bus-factor", "-C", str(repo.path), "--threshold", "1.5"])
    except SystemExit as exc:
        assert exc.code == 2


def test_report_html_is_self_contained(repo, tmp_path, capsys):
    out_file = tmp_path / "report.html"
    code, _, err = run(capsys, "report", "-C", str(repo.path), "-o", str(out_file))
    assert code == 0 and "wrote" in err
    html = out_file.read_text()
    assert html.startswith("<!DOCTYPE html>")
    assert html.count("<svg") >= 5
    assert "<script" not in html
    assert not re.search(r"""(src|href)=["']https?://""", html)
    assert "Alice Anders" in html and "src/core.py" in html
    assert "Bus factor: 2" in html


def test_report_default_filename(repo, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code, _, _ = run(capsys, "report", "-C", str(repo.path))
    assert code == 0
    assert (tmp_path / "git-pulse-report.html").exists()


def test_report_escapes_html(tmp_path, capsys):
    r = Repo(tmp_path / "xss")
    r.commit("<script>alert(1)</script>", {"a.txt": "x\n"}, author=("Eve & Co", "eve@example.com"))
    out_file = tmp_path / "r.html"
    assert main(["report", "-C", str(r.path), "-o", str(out_file)]) == 0
    html = out_file.read_text()
    assert "<script>" not in html and "Eve & Co" not in html
    assert "Eve &amp; Co" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_report_json_and_table(repo, capsys):
    code, out, _ = run(capsys, "report", "-C", str(repo.path), "-f", "json")
    assert code == 0
    data = json.loads(out)
    assert set(data) >= {"meta", "summary", "hotspots", "heatmap", "merges"}
    assert data["meta"]["tool"] == "git-pulse"
    _, out, _ = run(capsys, "report", "-C", str(repo.path), "-f", "table")
    assert "Bus factor" in out and "Hotspots" in out


def test_output_file(repo, tmp_path, capsys):
    target = tmp_path / "s.json"
    assert main(["summary", "-C", str(repo.path), "-f", "json", "-o", str(target)]) == 0
    assert json.loads(target.read_text())["authors"] == 4


def test_errors_are_reported(tmp_path, capsys):
    code, _, err = run(capsys, "summary", "-C", str(tmp_path / "nope"))
    assert code == 2 and "error" in err
    (tmp_path / "plain").mkdir()
    code, _, err = run(capsys, "summary", "-C", str(tmp_path / "plain"))
    assert code == 2


def test_empty_repo_report(tmp_path, capsys):
    r = Repo(tmp_path / "empty")
    out_file = tmp_path / "e.html"
    assert main(["report", "-C", str(r.path), "-o", str(out_file)]) == 0
    assert "No data" in out_file.read_text()
    code, _, _ = run(capsys, "heatmap", "-C", str(r.path))
    assert code == 0


def test_since_filter(repo, capsys):
    _, out, _ = run(capsys, "summary", "-C", str(repo.path), "-f", "json", "--since", "2024-03-01")
    assert json.loads(out)["commits"] == 4


def test_all_refs(repo, capsys):
    repo.git("checkout", "-q", "-b", "side")
    repo.commit("side work", {"side.txt": "x\n"}, date="2024-06-01T10:00:00+00:00")
    repo.git("checkout", "-q", "main")
    _, out, _ = run(capsys, "summary", "-C", str(repo.path), "-f", "json")
    assert json.loads(out)["commits"] == 16
    _, out, _ = run(capsys, "summary", "-C", str(repo.path), "-f", "json", "--all")
    assert json.loads(out)["commits"] == 17


def test_report_svgs_are_well_formed_xml(repo, tmp_path):
    import xml.etree.ElementTree as ET

    out_file = tmp_path / "report.html"
    assert main(["report", "-C", str(repo.path), "-o", str(out_file)]) == 0
    svgs = re.findall(r"<svg.*?</svg>", out_file.read_text(), flags=re.S)
    assert len(svgs) >= 5
    for chart in svgs:
        ET.fromstring(chart)
