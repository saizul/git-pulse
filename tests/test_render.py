from git_pulse import svg, text


def test_table_alignment():
    out = text.table(["Name", "N"], [("a", 1), ("bbb", 1000)], "lr")
    lines = out.splitlines()
    assert lines[0].startswith("Name")
    assert lines[3].endswith("1,000")
    assert lines[2].endswith("    1")


def test_truncate_and_fmt():
    assert text.truncate("abcdef", 4) == "abc…"
    assert text.fmt(None) == "-"
    assert text.fmt(True) == "yes"
    assert text.fmt(1234567) == "1,234,567"


def test_bar():
    assert text.bar(0, 10) == ""
    assert len(text.bar(10, 10, 20)) == 20
    assert text.bar(1, 1000, 10) == "▏"


def test_svg_charts_escape_and_handle_empty():
    chart = svg.bar_chart(["<a>", "b"], [1, 3], title="t & u")
    assert "&lt;a&gt;" in chart and "t &amp; u" in chart
    assert chart.count("<rect") == 2
    assert "No data" in svg.bar_chart([], [], title="x")
    assert "No data" in svg.hbar_chart(["a"], [0], title="x")
    assert "No data" in svg.heatmap([[0] * 24 for _ in range(7)], ["Mon"] * 7, title="x")
    assert "No data" in svg.scatter([], title="x")


def test_heatmap_svg_cells():
    grid = [[0] * 24 for _ in range(7)]
    grid[2][14] = 5
    out = svg.heatmap(grid, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], title="h")
    assert out.count('class="cell"') == 7 * 24
    assert "Wed 14:00: 5 commits" in out


def test_nice_max():
    assert svg._nice_max(7) == 10
    assert svg._nice_max(130) == 200
    assert svg._nice_max(0) == 1
