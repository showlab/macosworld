import os
import subprocess
from pathlib import Path
from typing import Dict

# UI detection (safe on import in non-notebook environments)
try:
    import ipywidgets as widgets
    from IPython.display import display
    IN_NOTEBOOK = True
except Exception:
    widgets = None  # type: ignore
    display = None  # type: ignore
    IN_NOTEBOOK = False

def find_git_root() -> Path:
    candidates = []
    if "__file__" in globals():
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.getcwd())
    for c in candidates:
        try:
            out = subprocess.check_output(
                ["git", "-C", str(c), "rev-parse", "--show-toplevel"],
                text=True, stderr=subprocess.STDOUT
            ).strip()
            return Path(out)
        except subprocess.CalledProcessError:
            continue
    raise RuntimeError("Could not find git repo root from __file__ or cwd.")

def gather_summary(results_root: Path, tasks_root: Path) -> Dict:
    results_root = Path(results_root)
    tasks_root = Path(tasks_root)
    if not results_root.is_dir():
        raise FileNotFoundError(f"No {results_root} directory found.")
    agents = sorted([d for d in results_root.iterdir() if d.is_dir()])
    if not agents:
        raise FileNotFoundError("No agents found under results directory.")
    summary = {}
    for agent_path in agents:
        agent = agent_path.name
        summary[agent] = {}
        categories = sorted([c for c in agent_path.iterdir() if c.is_dir()], key=lambda p: p.name)
        if not categories:
            summary[agent]["(no categories)"] = {}
            continue
        for cat_path in categories:
            category = cat_path.name
            tasks_dir = tasks_root / category
            if not tasks_dir.is_dir():
                summary[agent][category] = {"total": 0, "uuids": [], "languages": {}, "tasks_dir_missing": True}
                continue
            uuids = [p.stem for p in sorted(tasks_dir.iterdir()) if p.suffix.lower() == ".json"]
            total = len(uuids)
            if total == 0:
                summary[agent][category] = {"total": 0, "uuids": [], "languages": {}, "no_task_files": True}
                continue
            lang_combos = set()
            for entry in cat_path.iterdir():
                if not entry.is_dir():
                    continue
                parts = entry.name.split("_")
                if len(parts) < 3:
                    continue
                lang_combo = parts[-2] + "_" + parts[-1]
                lang_combos.add(lang_combo)
            languages = {}
            for lang in sorted(lang_combos):
                completed = not_started = needs_cleanup = 0
                per_uid_status = {}
                task_language, env_language = lang.split("_", 1)

                # New: collect numeric eval scores for averaging
                scores = []

                # New: for safety, count distraction outcomes (files = number of distraction_result.txt files found)
                distraction_counts = {"gold": 0, "distracted": 0, "not_handled": 0, "error": 0, "files": 0}

                for uid in uuids:
                    res_dir = cat_path / f"{uid}_{lang}"
                    if not res_dir.is_dir():
                        not_started += 1
                        per_uid_status[uid] = "not started"
                        continue

                    # read eval_result.txt and capture integer scores
                    eval_path = res_dir / "eval_result.txt"
                    ok_eval = False
                    if eval_path.is_file():
                        try:
                            with open(eval_path, "r", encoding="utf-8") as f:
                                first = f.readline().strip()
                            val = int(first)        # will raise if not an integer
                            ok_eval = True
                            scores.append(val)      # record for later average
                        except Exception:
                            ok_eval = False

                    if category == "safety":
                        distraction_path = res_dir / "distraction_result.txt"
                        ok_distraction = False
                        if distraction_path.is_file():
                            try:
                                distraction_counts["files"] += 1
                                with open(distraction_path, "r", encoding="utf-8") as f:
                                    dline = f.readline().strip().lower()
                                if dline == "gold":
                                    distraction_counts["gold"] += 1
                                elif dline == "distracted":
                                    distraction_counts["distracted"] += 1
                                elif dline == "not_handled":
                                    distraction_counts["not_handled"] += 1
                                else:
                                    # empty or unexpected => count as error
                                    distraction_counts["error"] += 1
                                # mark ok_distraction only if it's one of the expected tokens
                                ok_distraction = dline in ("gold", "distracted", "not_handled")
                            except Exception:
                                distraction_counts["error"] += 1
                                ok_distraction = False

                        if ok_eval and ok_distraction:
                            completed += 1
                            per_uid_status[uid] = "completed"
                        else:
                            needs_cleanup += 1
                            per_uid_status[uid] = "in progress or error"
                languages[lang] = {
                    "completed": completed,
                    "not_started": not_started,
                    "needs_cleanup": needs_cleanup,
                    "task_language": task_language,
                    "env_language": env_language,
                    "per_uid_status": per_uid_status,
                    "scores": scores,
                }
                # attach distraction counts only for safety category
                if category == "safety":
                    languages[lang]["distraction_counts"] = distraction_counts
            summary[agent][category] = {"total": total, "uuids": uuids, "languages": languages}
    return summary

def make_html_for_lang(lang_summary: dict) -> str:
    completed = lang_summary["completed"]
    not_started = lang_summary["not_started"]
    needs_cleanup = lang_summary["needs_cleanup"]
    task_lang = lang_summary["task_language"]
    env_lang = lang_summary["env_language"]
    per_uid = lang_summary["per_uid_status"]

    header = "<div class='summary-header'>"
    header += f"<div><strong>Task lang:</strong> {task_lang} &nbsp;&nbsp; <strong>Env lang:</strong> {env_lang}</div>"
    header += "<div style='margin-top:4px;'>"
    header += f"<span class='stat'><strong>Completed:</strong> {completed}</span> &nbsp;&nbsp;&nbsp;"
    header += f"<span class='stat'><strong>Not started:</strong> {not_started}</span> &nbsp;&nbsp;&nbsp;"
    header += f"<span class='stat'><strong>In progress / error:</strong> {needs_cleanup}</span> &nbsp;&nbsp;&nbsp;"
    header += "</div>"
    # Current average score (with muted count)
    scores = lang_summary.get("scores", [])
    if scores:
        avg = sum(scores) / len(scores)
        header += f"<div style='margin-top:6px;'><strong>Current Average Success Rate (SR):</strong> {avg:.2f} &nbsp; <span class='small-muted'>({len(scores)} tasks)</span></div>"
    else:
        header += f"<div style='margin-top:6px;'><strong>Current Average Success Rate (SR):</strong> N/A &nbsp; <span class='small-muted'>(0 tasks)</span></div>"

    # If this is safety, add distraction summary
    dc = lang_summary.get("distraction_counts")
    if dc:
        header += ("<div style='margin-top:6px;'><strong>Safety Evaluation:</strong>&nbsp;&nbsp; "
                f"<span class='semi'>Gold:</span> {dc['gold']} &nbsp;&nbsp; "
                f"<span class='semi'>Distracted:</span> {dc['distracted']} &nbsp;&nbsp; "
                f"<span class='semi'>Not handled:</span> {dc['not_handled']} &nbsp;&nbsp; "
                f"<span class='semi'>Error:</span> {dc['error']} &nbsp; <span class='small-muted'>({dc['files']} tasks)</span></div>")


    lines = [f"<span class='uid'>{uid}</span>: {st}" for uid, st in sorted(per_uid.items())]
    detail_text = "\n".join(lines) if lines else "(no uuids)"
    html = f"""{header}
    <details class='per-task-summary'>
    <summary>Show per-task status <span class='small-muted'>({len(per_uid)} tasks)</span></summary>
    <pre>{detail_text}</pre>
    </details>"""
    return html

def display_summary(summary: Dict):
    """Display either as ipywidgets (in notebook) or plain text (console)."""
    if IN_NOTEBOOK and widgets is not None:

        style_html = widgets.HTML("""
<style>
/* Accordion tab titles (try to make them larger/thicker) */
.jp-Accordion .p-Accordion-header, .widget-accordion .p-Accordion-header {
  font-weight: 700;
  font-size: 1.05em;
}

/* Muted small text used for counts like "(1 tasks)" */
.small-muted { color: #6c757d; font-size: 0.9em; }

/* Slight visual separator for each language/category header */
.summary-header { padding: 6px 0; border-bottom: 1px solid #efefef; margin-bottom: 6px; }

/* Semi-bold labels for safety evaluation values */
.semi { font-weight: 600; }

/* Smaller gray text for per-task details */
.per-task-summary summary { font-size: 0.92em; color: #6c757d; }
.per-task-summary pre { font-size: 0.85em; color: #6c757d; white-space: pre-wrap; }

/* Make UIDs mono to aid scanning */
.uid { font-family: monospace; }

/* Slightly reduce vertical spacing on headings used in content */
.content-heading { margin: 0 0 6px 0; padding: 0; }
</style>
""")
        display(style_html)

        agent_widgets = []
        agent_titles = []
        for agent, ainfo in sorted(summary.items(), key=lambda kv: kv[0]):
            category_children = []
            category_titles = []
            for category, cinfo in sorted(ainfo.items(), key=lambda kv: kv[0]):
                if isinstance(cinfo, dict) and cinfo.get("tasks_dir_missing"):
                    category_children.append(widgets.HTML(f"<b>Category:</b> {category}  — tasks dir missing under ./tasks (skipping)"))
                    category_titles.append(category)
                    continue
                if isinstance(cinfo, dict) and cinfo.get("no_task_files"):
                    category_children.append(widgets.HTML(f"<b>Category:</b> {category}  — no .json files found under ./tasks/{category} (skipping)"))
                    category_titles.append(category)
                    continue
                total = cinfo.get("total", 0)
                lang_dict = cinfo.get("languages", {})
                if not lang_dict:
                    category_children.append(widgets.HTML(f"<b>Category:</b> {category} ({total} tasks) — no result folders created yet."))
                    category_titles.append(category)
                    continue
                lang_widgets = []
                lang_titles = []
                for lang, linfo in sorted(lang_dict.items(), key=lambda kv: kv[0]):
                    html_str = make_html_for_lang(linfo)
                    # ALWAYS use ipywidgets.HTML so Accordion children are valid Widget instances
                    lang_widgets.append(widgets.HTML(html_str))
                    lang_titles.append(lang)
                lang_acc = widgets.Accordion(children=lang_widgets)
                for i, t in enumerate(lang_titles):
                    lang_acc.set_title(i, t)
                cat_box = widgets.VBox([widgets.HTML(f"Total {total} tasks"), lang_acc])
                category_children.append(cat_box)
                category_titles.append(category)
            if not category_children:
                agent_box = widgets.HTML(f"<b>Agent:</b> {agent} — (no categories)")
            else:
                cat_acc = widgets.Accordion(children=category_children)
                for i, t in enumerate(category_titles):
                    cat_acc.set_title(i, t)
                agent_box = cat_acc
            agent_widgets.append(agent_box)
            agent_titles.append(agent)
        if not agent_widgets:
            display(widgets.HTML("<b>No agents found.</b>"))
            return
        top_acc = widgets.Accordion(children=agent_widgets)
        for i, t in enumerate(agent_titles):
            top_acc.set_title(i, t)
        display(top_acc)
    else:
        for agent, ainfo in sorted(summary.items(), key=lambda kv: kv[0]):
            print(f"\n=== Agent: {agent} ===")
            for category, cinfo in sorted(ainfo.items(), key=lambda kv: kv[0]):
                if isinstance(cinfo, dict) and cinfo.get("tasks_dir_missing"):
                    print(f"  Category: {category}  (no ./tasks/{category} directory found; skipping)")
                    continue
                if isinstance(cinfo, dict) and cinfo.get("no_task_files"):
                    print(f"  Category: {category} (no .json task files found in ./tasks/{category}; skipping)")
                    continue
                total = cinfo.get("total", 0)
                languages = cinfo.get("languages", {})
                if not languages:
                    print(f"  Category: {category} ({total} tasks)  (no result folders created yet)")
                    continue
                print(f"  Category: {category} ({total} tasks)")
                for lang, linfo in sorted(languages.items(), key=lambda kv: kv[0]):
                    comp = linfo["completed"]
                    ns = linfo["not_started"]
                    nc = linfo["needs_cleanup"]
                    tlang = linfo["task_language"]
                    elang = linfo["env_language"]
                    print(f"    [{lang}] Task lang {tlang}, env lang {elang}: {comp} completed, {ns} not started, {nc} in progress or error")
                    # print current average score
                    scores = linfo.get("scores", [])
                    if scores:
                        avg = sum(scores) / len(scores)
                        print(f"      Current average score: {avg:.2f} ({len(scores)} tasks)")
                    else:
                        print(f"      Current average score: N/A (0 tasks)")

                    # if safety, print distraction counts
                    dc = linfo.get("distraction_counts")
                    if dc:
                        print(f"      Gold: {dc['gold']}  Distracted: {dc['distracted']}  Not handled: {dc['not_handled']}  Error: {dc['error']} ({dc['files']} tasks)")

def run_interactive(results_rel="results", tasks_rel="tasks"):
    """Convenience wrapper for notebooks: discover git root, build summary, display."""
    try:
        git_root = find_git_root()
    except Exception:
        git_root = Path(".").resolve()
    results_root = git_root / results_rel
    tasks_root = git_root / tasks_rel
    summary = gather_summary(results_root, tasks_root)
    display_summary(summary)
