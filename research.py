"""Run one research task on the deep-researcher Managed Agent.

The agent and its environment are defined as files in agents/deep-researcher/
and created once with `ant apply`, which records their IDs in claude-lock.json.
This script only does the per-run part: it starts a session, hands the agent
the question as an outcome (so a grader checks the report against a rubric),
streams what the agent does, and downloads the finished report.

Usage:
    python research.py "Wie funktionieren Claude Managed Agents?"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parent
LOCK_FILE = REPO_ROOT / "claude-lock.json"
AGENT_FILE = "agents/deep-researcher/agent.md"
ENVIRONMENT_FILE = "agents/deep-researcher/environment.yaml"

# Starter rubric (from the Console's deep-research quickstart). The grader scores
# each line on its own, so keep criteria concrete. Tune it to your needs.
RUBRIC = """\
- The report is a single Markdown file at /mnt/session/outputs/report.md.
- The report directly answers the question that was asked, organized by the sub-questions it was decomposed into.
- Every non-obvious claim has an inline citation, and the cited sources are authoritative for that claim (primary sources, official documentation, or peer-reviewed work where available).
- Disagreements between sources are surfaced rather than smoothed over, with a reasoned judgement on which source is more credible.
- The report ends with a confidence-and-gaps section that names where coverage was thin, where sources conflicted, and what remains uncertain.
- No placeholder text, TODOs, or empty sections remain.
"""


class ConfigError(RuntimeError):
    """Raised when the agent or environment ID cannot be found."""


def _find_lock_id(resources: dict, rel_path: str) -> str | None:
    """Return the ID that claude-lock.json records for a resource file.

    `ant apply` keys resources by the path it printed (e.g. "./agents/...").
    Match on the normalized path so either spelling works.
    """
    wanted = Path(rel_path).as_posix()
    for key, entry in resources.items():
        if Path(key).as_posix().removeprefix("./") == wanted and isinstance(entry, dict):
            return entry.get("id")
    return None


def load_ids(lock_file: Path = LOCK_FILE, env: dict | None = None) -> tuple[str, str]:
    """Return (agent_id, environment_id).

    AGENT_ID / ENVIRONMENT_ID environment variables win; otherwise the IDs come
    from claude-lock.json written by `ant apply`.
    """
    env = os.environ if env is None else env
    agent_id = env.get("AGENT_ID")
    environment_id = env.get("ENVIRONMENT_ID")

    if not (agent_id and environment_id) and lock_file.exists():
        resources = json.loads(lock_file.read_text()).get("resources", {})
        agent_id = agent_id or _find_lock_id(resources, AGENT_FILE)
        environment_id = environment_id or _find_lock_id(resources, ENVIRONMENT_FILE)

    if not agent_id or not environment_id:
        raise ConfigError(
            "Agent oder Environment nicht gefunden. Bitte zuerst im Repo-Ordner ausführen:\n"
            f"  ant apply {AGENT_FILE} {ENVIRONMENT_FILE}\n"
            "(oder AGENT_ID und ENVIRONMENT_ID als Umgebungsvariablen setzen)."
        )
    return agent_id, environment_id


def build_outcome(question: str, max_iterations: int = 3) -> dict:
    """The kickoff event: the question as an outcome graded against RUBRIC."""
    return {
        "type": "user.define_outcome",
        "description": (
            "Research the following question and write the report to "
            f"/mnt/session/outputs/report.md:\n\n{question}"
        ),
        "rubric": {"type": "text", "content": RUBRIC},
        "max_iterations": max_iterations,
    }


def approve(event) -> bool:
    """Decide on a tool call the server paused for review.

    Asks on the terminal when someone is watching; denies when unattended.
    """
    if not sys.stdin.isatty():
        return False
    print(f"\n[Freigabe nötig] {event.name}: {json.dumps(event.input, ensure_ascii=False)[:500]}")
    return input("Erlauben? [j/N] ").strip().lower() in {"j", "ja", "y", "yes"}


def run_session(client: anthropic.Anthropic, session_id: str, kickoff: dict) -> None:
    """Stream the session until the agent is done, answering paused tool calls."""
    # Stream first, then send, so no early events are missed.
    with client.beta.sessions.events.stream(session_id=session_id) as stream:
        client.beta.sessions.events.send(session_id=session_id, events=[kickoff])
        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        print(block.text, end="", flush=True)
            elif event.type in ("agent.tool_use", "agent.mcp_tool_use"):
                print(f"\n[Tool] {event.name}", flush=True)
                if getattr(event, "evaluated_permission", None) == "ask":
                    client.beta.sessions.events.send(
                        session_id=session_id,
                        events=[{
                            "type": "user.tool_confirmation",
                            "tool_use_id": event.id,
                            "result": "allow" if approve(event) else "deny",
                        }],
                    )
            elif event.type == "span.outcome_evaluation_end":
                print(f"\n[Bewertung {event.iteration + 1}] {event.result}: {event.explanation}", flush=True)
            elif event.type == "session.error":
                print(f"\n[Fehler] {event.error}", file=sys.stderr, flush=True)
            elif event.type == "session.status_idle":
                # requires_action means the session waits on us: keep streaming.
                if event.stop_reason.type != "requires_action":
                    return
            elif event.type == "session.status_terminated":
                return


def download_outputs(client: anthropic.Anthropic, session_id: str, out_dir: Path) -> list[Path]:
    """Save the files the agent wrote to /mnt/session/outputs/."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for attempt in range(3):  # files show up a few seconds after the session idles
        files = client.beta.files.list(scope_id=session_id, betas=["managed-agents-2026-04-01"])
        for f in files.data:
            target = out_dir / Path(f.filename).name
            client.beta.files.download(f.id).write_to_file(target)
            saved.append(target)
        if saved:
            break
        time.sleep(2 * (attempt + 1))
    return saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recherche-Auftrag an den Deep-researcher-Agenten.")
    parser.add_argument("question", help="Die Frage, die der Agent recherchieren soll.")
    parser.add_argument("--max-iterations", type=int, default=3,
                        help="Wie oft der Agent nach der Bewertung nachbessern darf (1-20, Standard 3).")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "outputs",
                        help="Ordner für den fertigen Bericht (Standard: ./outputs).")
    parser.add_argument("--workspace", default=os.environ.get("ANTHROPIC_WORKSPACE", "default"),
                        help="Workspace-ID für den Link zur Console (Standard: default).")
    args = parser.parse_args(argv)

    try:
        agent_id, environment_id = load_ids()
    except ConfigError as err:
        print(err, file=sys.stderr)
        return 2

    client = anthropic.Anthropic()
    session = client.beta.sessions.create(
        agent=agent_id,
        environment_id=environment_id,
        title=args.question[:80],
    )
    print(f"Session: {session.id}")
    print(f"Live ansehen: https://platform.claude.com/workspaces/{args.workspace}/sessions/{session.id}\n")

    run_session(client, session.id, build_outcome(args.question, args.max_iterations))

    saved = download_outputs(client, session.id, args.out / session.id)
    if saved:
        print("\nGespeichert:")
        for path in saved:
            print(f"  {path}")
    else:
        print("\nDer Agent hat keine Datei abgelegt. Details in der Console (Link oben).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
