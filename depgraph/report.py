"""Portable HTML evidence report. Repository and model strings are escaped."""

import html

from .store import verify_events


def render_report(run):
    def esc(value):
        return html.escape(str(value), quote=True)

    rows = "".join(
        f"<tr><td>{esc(c['name'])}</td><td>{esc(c['from'])} → {esc(c['to'])}</td>"
        f"<td>{esc(c['outcome'])}</td><td>{esc(c.get('security', {}).get('status', '—'))}</td></tr>"
        for c in run["candidates"]
    )
    patches = "".join(f"<h3>{esc(c['path'])}</h3><pre>{esc(c['diff'])}</pre>" for c in run["changes"])
    events = "".join(
        f"<li><b>{esc(e['stage'])}</b> · {esc(e['message'])}<small>{esc(e['hash'])}</small></li>"
        for e in run["events"]
    )
    validations = [("Baseline", run.get("baseline"))]
    for candidate in run["candidates"]:
        validations.append((candidate["name"], candidate.get("validation")))
        validations.extend(
            (candidate["name"] + " repair", a.get("validation")) for a in candidate["attempts"]
        )
    commands = ""
    for label, validation in validations:
        if validation:
            commands += f"<h3>{esc(label)} · {'passed' if validation['passed'] else 'failed'}</h3>"
            for command in validation["commands"]:
                commands += (
                    f"<pre>{esc(' '.join(command['command']))}\nexit={esc(command['return_code'])}\n"
                    f"{esc(command['stdout'])}\n{esc(command['stderr'])}</pre>"
                )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>DepGraph · {esc(run["id"])}</title><style>
body{{background:#0b0e13;color:#dce6ee;font:14px/1.7 system-ui;max-width:1050px;margin:50px auto;padding:20px}}
h1,h2{{color:#7ee0bb}}p,small{{color:#8b9dac}}small{{display:block;overflow-wrap:anywhere}}
table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;border-bottom:1px solid #293645;padding:12px}}
pre{{background:#131b24;border:1px solid #293645;padding:20px;white-space:pre-wrap;overflow-wrap:anywhere}}
li{{padding:10px}}@media print{{body{{background:white;color:black}}pre{{background:#eee;color:black}}}}
</style><h1>DepGraph / execution report</h1><p>{esc(run["repo"])}<br>Run {esc(run["id"])} · {esc(run["status"])}
<br>{"OFFLINE FIXTURE · local modules and deterministic repair, real tests" if run["demo"] else "REAL REPOSITORY ANALYSIS"}
<br>Event chain verified: {verify_events(run["events"])}</p><h2>Upgrade decisions</h2>
<table><tr><th>Package</th><th>Version path</th><th>Outcome</th><th>Security</th></tr>{rows}</table>
<h2>Proposed patch</h2>{patches or "<p>No validated changes.</p>"}<h2>Execution journal</h2><ol>{events}</ol>
<h2>Command evidence</h2>{commands}<p>Hash chains detect edits relative to the stored chain; they are not cryptographic signatures.
Virtual environments isolate dependencies, not hostile code. Test success is evidence, not a proof of compatibility.</p></html>"""
