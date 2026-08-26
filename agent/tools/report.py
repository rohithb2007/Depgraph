"""
DepGraph HTML Report Generator.

Generates self-contained static HTML reports from DepGraph run logs.
"""

import json
import html
import os
from typing import Dict, Any, Optional


def esc(val: Any) -> str:
    """Safely convert any value to string and HTML-escape it."""
    if val is None:
        return ""
    return html.escape(str(val))


def generate_report(run_log: Dict[str, Any], output_path: Optional[str] = None) -> str:
    """
    Generate a self-contained static HTML report from a run log dict.

    Args:
        run_log: Dictionary containing execution details of DepGraph.
        output_path: Optional file path to write the HTML report to.

    Returns:
        The generated HTML content as a string.
    """
    if not isinstance(run_log, dict):
        run_log = {}

    repo = esc(run_log.get("repo", "N/A"))
    started_at = run_log.get("started_at")
    finished_at = run_log.get("finished_at")
    
    time_info = ""
    if started_at is not None:
        time_info += f"Started: {esc(started_at)}"
    if finished_at is not None:
        if time_info:
            time_info += " | "
        time_info += f"Finished: {esc(finished_at)}"

    deps = run_log.get("deps", [])
    if not isinstance(deps, list):
        deps = []

    # Overall Summary calculation
    total_deps = len(deps)
    clean_upgraded = sum(1 for d in deps if isinstance(d, dict) and d.get("outcome") == "upgraded_clean")
    fixed_upgraded = sum(1 for d in deps if isinstance(d, dict) and d.get("outcome") == "upgraded_and_fixed")
    failed_rolled = sum(1 for d in deps if isinstance(d, dict) and "failed" in str(d.get("outcome", "")))
    
    if total_deps == 0:
        overall_status = "No dependencies analyzed"
    elif failed_rolled == 0:
        overall_status = "SUCCESS"
    elif clean_upgraded + fixed_upgraded > 0:
        overall_status = "PARTIAL SUCCESS"
    else:
        overall_status = "FAILURE"

    # Dependency Graph section
    graph_html = ""
    dep_graph = run_log.get("dependency_graph")
    if isinstance(dep_graph, dict):
        summary = dep_graph.get("summary", {})
        summary_items = []
        if isinstance(summary, dict):
            for k, v in summary.items():
                summary_items.append(f"<li><strong>{esc(k)}:</strong> {esc(v)}</li>")
        summary_str = "<ul>" + "".join(summary_items) + "</ul>" if summary_items else "<p>No summary details.</p>"

        # Graph dependencies list
        g_deps = dep_graph.get("dependencies", [])
        g_deps_rows = []
        if isinstance(g_deps, list):
            for gd in g_deps:
                if isinstance(gd, dict):
                    name = esc(gd.get("name", ""))
                    used = esc(gd.get("used", False))
                    g_deps_rows.append(f"<tr><td>{name}</td><td>{used}</td></tr>")
        g_deps_table = (
            "<table><thead><tr><th>Dependency</th><th>Used</th></tr></thead><tbody>"
            + "".join(g_deps_rows)
            + "</tbody></table>"
            if g_deps_rows
            else ""
        )

        # Graph files list
        g_files = dep_graph.get("files", [])
        g_files_html = []
        if isinstance(g_files, list):
            for gf in g_files:
                if isinstance(gf, dict):
                    fname = esc(gf.get("file", ""))
                    imports = gf.get("imports", [])
                    imp_list = []
                    if isinstance(imports, list):
                        for imp in imports:
                            if isinstance(imp, dict):
                                mod = esc(imp.get("module", ""))
                                d_name = esc(imp.get("dependency", ""))
                                imp_list.append(f"module: {mod} (dep: {d_name})")
                    imp_str = ", ".join(imp_list) if imp_list else "None"
                    g_files_html.append(f"<li><strong>File:</strong> {fname} — <strong>Imports:</strong> {imp_str}</li>")
        g_files_str = "<ul>" + "".join(g_files_html) + "</ul>" if g_files_html else ""

        graph_html = f"""
        <section class="section">
            <h2>Dependency Graph Analysis</h2>
            {summary_str}
            {g_deps_table}
            {g_files_str}
        </section>
        """
    else:
        graph_html = """
        <section class="section">
            <h2>Dependency Graph Analysis</h2>
            <p>No dependency graph analysis available.</p>
        </section>
        """

    # Dependency Table & Detail Rows
    dep_rows = []
    for dep in deps:
        if not isinstance(dep, dict):
            continue

        name = esc(dep.get("name", "N/A"))
        from_ver = esc(dep.get("from", "N/A"))
        to_ver = esc(dep.get("to", "N/A"))
        outcome = esc(dep.get("outcome", "N/A"))

        # Risk info
        risk_info = dep.get("risk")
        if isinstance(risk_info, dict):
            r_score = esc(risk_info.get("score", "N/A"))
            r_level = esc(risk_info.get("level", "N/A"))
            reasons = risk_info.get("reasons", [])
            if isinstance(reasons, list):
                r_reasons = ", ".join(esc(r) for r in reasons)
            else:
                r_reasons = esc(reasons)
            risk_str = f"Score: {r_score} | Level: {r_level}<br><small>Reasons: {r_reasons}</small>"
        else:
            risk_str = "N/A"

        # Security info
        sec_info = dep.get("security")
        if isinstance(sec_info, dict):
            curr_sec = sec_info.get("current", {})
            cand_sec = sec_info.get("candidate", {})

            curr_status = esc(curr_sec.get("status", "N/A")) if isinstance(curr_sec, dict) else "N/A"
            cand_status = esc(cand_sec.get("status", "N/A")) if isinstance(cand_sec, dict) else "N/A"

            curr_vulns = curr_sec.get("vulnerabilities", []) if isinstance(curr_sec, dict) else []
            cand_vulns = cand_sec.get("vulnerabilities", []) if isinstance(cand_sec, dict) else []

            vuln_list = []
            if isinstance(curr_vulns, list) and curr_vulns:
                vuln_list.extend([esc(v) for v in curr_vulns])
            if isinstance(cand_vulns, list) and cand_vulns:
                vuln_list.extend([esc(v) for v in cand_vulns])

            vuln_str = f"<br><small>Vulns: {', '.join(vuln_list)}</small>" if vuln_list else ""
            sec_str = f"Current: {curr_status} → Candidate: {cand_status}{vuln_str}"
        else:
            sec_str = "N/A"

        # Attempts & Gemini Repair
        attempts = dep.get("attempts", [])
        attempt_blocks = []
        if isinstance(attempts, list):
            for att in attempts:
                if not isinstance(att, dict):
                    continue
                att_num = esc(att.get("attempt", "N/A"))
                diag = esc(att.get("diagnosis", "N/A"))
                conf = esc(att.get("confidence", "N/A"))
                src = esc(att.get("diagnosis_source", "N/A"))
                model = esc(att.get("model", "N/A"))
                p_find = esc(att.get("patch_find", ""))
                p_replace = esc(att.get("patch_replace", ""))
                p_applied = esc(att.get("patch_applied", False))
                res = esc(att.get("result", "N/A"))

                patch_str = ""
                if p_find or p_replace:
                    patch_str = f"<pre>Find: {p_find}\nReplace: {p_replace}</pre>"

                attempt_blocks.append(
                    f"<div class='attempt'>"
                    f"<strong>Attempt {att_num}:</strong> {res}<br>"
                    f"<small>Diagnosis ({src}/{model}, confidence: {conf}): {diag}</small><br>"
                    f"<small>Applied: {p_applied}</small>"
                    f"{patch_str}"
                    f"</div>"
                )

        attempts_str = "".join(attempt_blocks) if attempt_blocks else "None"

        # Install error if present
        install_err = dep.get("install_error")
        err_str = ""
        if isinstance(install_err, dict):
            err_rc = esc(install_err.get("return_code", ""))
            err_stdout = esc(install_err.get("stdout", ""))
            err_stderr = esc(install_err.get("stderr", ""))
            err_str = f"<div class='error'><strong>Install Error (RC {err_rc}):</strong><pre>{err_stderr or err_stdout}</pre></div>"

        dep_rows.append(
            f"<tr>"
            f"<td><strong>{name}</strong></td>"
            f"<td>{from_ver}</td>"
            f"<td>{to_ver}</td>"
            f"<td><span class='badge outcome-{outcome}'>{outcome}</span></td>"
            f"<td>{risk_str}</td>"
            f"<td>{sec_str}</td>"
            f"<td>{attempts_str}{err_str}</td>"
            f"</tr>"
        )

    deps_table_body = "".join(dep_rows) if dep_rows else "<tr><td colspan='7'>No dependencies evaluated.</td></tr>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DepGraph Execution Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f8f9fa; }}
        h1, h2, h3 {{ color: #2c3e50; }}
        .header {{ background: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .summary-cards {{ display: flex; gap: 15px; margin-top: 15px; flex-wrap: wrap; }}
        .card {{ background: #edf2f7; padding: 15px; border-radius: 6px; flex: 1; min-width: 150px; text-align: center; }}
        .card-value {{ font-size: 1.5em; font-weight: bold; color: #2b6cb0; }}
        .section {{ background: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        th, td {{ border: 1px solid #e2e8f0; padding: 12px; text-align: left; vertical-align: top; }}
        th {{ background-color: #f7fafc; font-weight: 600; }}
        .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600; text-transform: uppercase; }}
        .outcome-upgraded_clean {{ background-color: #c6f6d5; color: #22543d; }}
        .outcome-upgraded_and_fixed {{ background-color: #feebc8; color: #744210; }}
        .outcome-failed_rolled_back {{ background-color: #fed7d7; color: #742a2a; }}
        .attempt {{ background: #f7fafc; border-left: 3px solid #4299e1; padding: 8px; margin-top: 8px; border-radius: 2px; }}
        .error {{ background: #fff5f5; border-left: 3px solid #e53e3e; padding: 8px; margin-top: 8px; color: #c53030; }}
        pre {{ background: #2d3748; color: #edf2f7; padding: 8px; border-radius: 4px; overflow-x: auto; font-size: 0.85em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>DepGraph Run Report</h1>
        <p><strong>Repository:</strong> {repo}</p>
        <p>{time_info}</p>
        <div class="summary-cards">
            <div class="card"><div class="card-label">Overall Status</div><div class="card-value">{overall_status}</div></div>
            <div class="card"><div class="card-label">Total Dependencies</div><div class="card-value">{total_deps}</div></div>
            <div class="card"><div class="card-label">Upgraded Clean</div><div class="card-value">{clean_upgraded}</div></div>
            <div class="card"><div class="card-label">Upgraded & Fixed</div><div class="card-value">{fixed_upgraded}</div></div>
            <div class="card"><div class="card-label">Failed & Rolled Back</div><div class="card-value">{failed_rolled}</div></div>
        </div>
    </div>

    {graph_html}

    <section class="section">
        <h2>Dependency Upgrade Details</h2>
        <table>
            <thead>
                <tr>
                    <th>Package</th>
                    <th>From</th>
                    <th>To</th>
                    <th>Outcome</th>
                    <th>Risk Assessment</th>
                    <th>Security Status</th>
                    <th>Attempts / Errors</th>
                </tr>
            </thead>
            <tbody>
                {deps_table_body}
            </tbody>
        </table>
    </section>
</body>
</html>"""

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

    return html_content


def generate_report_from_file(log_path: str, output_path: Optional[str] = None) -> str:
    """
    Read a DepGraph run log JSON file and generate an HTML report.

    Args:
        log_path: Path to the depgraph_run_log.json file.
        output_path: Optional file path to write the HTML report to.

    Returns:
        The generated HTML content as a string.
    """
    with open(log_path, "r", encoding="utf-8") as f:
        run_log = json.load(f)
    return generate_report(run_log, output_path)
