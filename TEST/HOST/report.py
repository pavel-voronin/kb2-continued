"""Self-contained HTML and JUnit reports; no browser or game launch."""

from html import escape
import xml.etree.ElementTree as ET


def write_report(report, folder, root):
    suite = ET.Element(
        "testsuite",
        name="KB2 modules",
        tests=str(len(report["tests"]) + 1),
        failures=str(
            sum(t["status"] != "pass" for t in report["tests"])
            + int(not report["complete"])
        ),
    )
    for test in report["tests"]:
        node = ET.SubElement(
            suite,
            "testcase",
            classname=test["module"],
            name=test["name"],
            time=str(test["seconds"]),
        )
        if test["status"] != "pass":
            ET.SubElement(node, "failure", message=test["error"]).text = test["error"]
    gate = ET.SubElement(
        suite, "testcase", classname="coverage", name="all-reachable-code-and-assembly"
    )
    if not report["complete"]:
        ET.SubElement(
            gate, "failure", message="Uncovered code or stale reachability proof"
        )
    ET.ElementTree(suite).write(
        folder / "JUNIT.xml", encoding="utf-8", xml_declaration=True
    )
    out = [
        '<!doctype html><html lang="ru"><meta charset="utf-8"><title>KB2 unit coverage</title>',
        "<style>body{font:16px system-ui;max-width:1200px;margin:2em auto;padding:0 1em}td,th{padding:.3em .8em;text-align:left}table{border-collapse:collapse}tr:nth-child(even){background:#eee}pre{white-space:pre-wrap}details{margin:1em 0}.missing{color:#a00}code{font:13px monospace}</style>",
        "<h1>Модульные тесты KB2</h1>",
        f"<p>Успешно: {sum(t['status'] == 'pass' for t in report['tests'])} / {len(report['tests'])}. "
        f"Точки Pascal: {report['covered']} / {report['total']}.</p>",
        f"<p>Достижимые точки: {report['reachable_covered']} / {report['reachable_total']}. "
        f"Обоснованно недостижимые: {len(report['unreachable'])}. "
        f"Строгая проверка: {'пройдена' if report['complete'] else 'не пройдена'}.</p>",
        "<p>Считаются выполненные операторы, входы в процедуры, исходы условий и циклов. "
        "Инструкции ASM и исходы переходов считаются отдельно. "
        "Синтетическая ветвь case-unmatched означает отсутствие подходящей ветви case; "
        "она может быть недостижима при допустимом входе. Неисполненные пути с обоснованиями "
        "учитываются отдельно и остаются в исходном знаменателе.</p>",
        "<table><tr><th>Модуль<th>Pascal выполнено<th>Недостижимо<th>Пробелы<th>ASM инструкции<th>ASM переходы",
    ]
    for item in report["coverage"]:
        if item["module"] not in report["selected"]:
            continue
        name = item["module"]
        out.append(
            f'<tr><td><a href="#{name}">{name}</a><td>{item["covered"]}/{item["total"]}'
            f"<td>{len(item['unreachable'])}<td>{len(item['unexplained_missing'])}"
            f"<td>{item['assembly_covered']}/{item['assembly_instructions']}"
            f"<td>{item['assembly_edges_covered']}/{item['assembly_edges']}"
        )
    out.append("</table>")
    for item in report["coverage"]:
        if item["module"] not in report["selected"]:
            continue
        name = item["module"]
        out.append(
            f'<details id="{name}"><summary>{name}: непокрытые точки ({len(item["missing"])})</summary>'
        )
        lines = (root / "SRC" / f"{name}.PAS").read_bytes().decode("cp866").splitlines()
        out.append("<pre>")
        for point in item["missing"]:
            line = point["line"]
            text = lines[line - 1] if line <= len(lines) else point["source"]
            out.append(
                escape(f"{line:4} {point['routine']} [{point['kind']}] {text}") + "\n"
            )
        out.append("</pre></details>")
    out.append("<h2>Обоснования недостижимости</h2>")
    for point in report["unreachable"]:
        out.append(
            "<p>"
            + escape(
                f"{point['file']}:{point['line']} [{point['kind']}] {point['reason']}"
            )
            + "</p>"
        )
    for error in report["audit_errors"]:
        out.append('<p class="missing">' + escape(error) + "</p>")
    for test in report["tests"]:
        if test["status"] != "pass":
            out.append(
                '<p class="missing">'
                + escape(test["module"] + " " + test["name"] + ": " + test["error"])
                + "</p>"
            )
    out.append("</html>")
    (folder / "COVERAGE.html").write_text("\n".join(out), encoding="utf-8")
