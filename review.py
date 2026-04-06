"""
Treasure or Trash — TUI for reviewing scanned projects.

Reads the projects.json from the scanner, lets you mark each project
as keep (default), archive (zip + remove original), or delete.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Label,
    Static,
)

VERDICT_ICONS = {"treasure": "💎", "trash": "🗑️", "unsure": "🤷"}
ACTION_STYLES = {
    "keep": ("keep", "green"),
    "archive": ("archive", "yellow"),
    "delete": ("DELETE", "red"),
}


class ConfirmScreen(ModalScreen[bool]):
    """Modal confirmation before applying destructive actions."""

    BINDINGS = [
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, summary: str) -> None:
        super().__init__()
        self.summary = summary

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Are you sure?", id="confirm-title"),
            Static(self.summary, id="confirm-body"),
            Label("Press [b]y[/b] to confirm, [b]n[/b] or [b]Esc[/b] to cancel", id="confirm-hint"),
            id="confirm-dialog",
        )

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class ProjectDetail(Static):
    """Shows details of the currently selected project."""

    def update_project(self, project: dict | None) -> None:
        if project is None:
            self.update("")
            return
        verdict = VERDICT_ICONS.get(project.get("verdict", "unsure"), "🤷")
        action_label, _ = ACTION_STYLES[project.get("action", "keep")]
        lines = [
            f"[bold]{project['name']}[/bold]  {verdict}  [{ACTION_STYLES[project.get('action', 'keep')][1]}]{action_label}[/]",
            "",
            f"[dim]Type:[/dim] {project['type']}  |  [dim]Complexity:[/dim] {project['complexity']}  |  [dim]Files:[/dim] {project['source_file_count']}",
            f"[dim]Path:[/dim] {project['path']}",
            "",
            project.get("one_liner", "No description available."),
        ]
        self.update("\n".join(lines))


class ReviewApp(App):
    """TUI for reviewing treasure-or-trash scan results."""

    CSS = """
    #main {
        height: 1fr;
    }
    #table-container {
        width: 3fr;
        height: 1fr;
    }
    #detail-panel {
        width: 2fr;
        height: 1fr;
        padding: 1 2;
        border-left: solid $accent;
    }
    #confirm-dialog {
        width: 60;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: solid $error;
        background: $surface;
        align: center middle;
    }
    ConfirmScreen {
        align: center middle;
    }
    #confirm-title {
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    #confirm-body {
        margin-bottom: 1;
        max-height: 20;
    }
    #confirm-hint {
        color: $text-muted;
    }
    #stats-bar {
        height: 1;
        dock: bottom;
        padding: 0 1;
        background: $boost;
    }
    DataTable {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("k", "mark_keep", "Keep", priority=True),
        Binding("a", "mark_archive", "Archive", priority=True),
        Binding("d", "mark_delete", "Delete", priority=True),
        Binding("enter", "apply", "Apply actions", priority=True),
        Binding("f", "filter", "Cycle filter", priority=True),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, projects: list[dict], archive_dir: Path) -> None:
        super().__init__()
        self.projects = projects
        self.archive_dir = archive_dir
        self.current_filter = "all"  # all, keep, archive, delete
        self.title = "Treasure or Trash"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="table-container"):
                yield DataTable(id="project-table")
            yield ProjectDetail(id="detail-panel")
        yield Static("", id="stats-bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Action", "Verdict", "Name", "Type", "Cplx", "Files", "Summary")
        self._populate_table()
        self._update_stats()
        # Initial detail panel update
        self.set_timer(0.1, self._update_detail)

    def _populate_table(self) -> None:
        table = self.query_one("#project-table", DataTable)
        table.clear()
        for project in self.projects:
            action = project.get("action", "keep")
            if self.current_filter != "all" and action != self.current_filter:
                continue
            label, colour = ACTION_STYLES[action]
            verdict = VERDICT_ICONS.get(project.get("verdict", "unsure"), "🤷")
            one_liner = project.get("one_liner", "")
            if len(one_liner) > 60:
                one_liner = one_liner[:57] + "..."
            table.add_row(
                f"[{colour}]{label}[/]",
                verdict,
                project["name"],
                project["type"],
                project["complexity"],
                str(project["source_file_count"]),
                one_liner,
                key=project["path"],
            )

    def _get_selected_project(self) -> dict | None:
        table = self.query_one("#project-table", DataTable)
        if table.row_count == 0:
            return None
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        path = row_key.value
        return next((p for p in self.projects if p["path"] == path), None)

    def _update_detail(self) -> None:
        project = self._get_selected_project()
        detail = self.query_one("#detail-panel", ProjectDetail)
        detail.update_project(project)

    def _update_stats(self) -> None:
        counts = {"keep": 0, "archive": 0, "delete": 0}
        for p in self.projects:
            counts[p.get("action", "keep")] += 1
        bar = self.query_one("#stats-bar", Static)
        total = len(self.projects)
        bar.update(
            f" {total} projects  |  "
            f"[green]keep: {counts['keep']}[/]  "
            f"[yellow]archive: {counts['archive']}[/]  "
            f"[red]delete: {counts['delete']}[/]  "
            f"[dim]filter: {self.current_filter}[/]"
        )

    def _mark_selected(self, action: str) -> None:
        project = self._get_selected_project()
        if project is None:
            return
        project["action"] = action
        table = self.query_one("#project-table", DataTable)
        cursor_row = table.cursor_coordinate.row
        self._populate_table()
        self._update_stats()
        # Move cursor to next row (or stay at end)
        if table.row_count > 0:
            new_row = min(cursor_row, table.row_count - 1)
            table.move_cursor(row=new_row)
        self._update_detail()

    @on(DataTable.RowHighlighted)
    def on_row_highlighted(self) -> None:
        self._update_detail()

    @on(DataTable.CellHighlighted)
    def on_cell_highlighted(self) -> None:
        self._update_detail()

    def action_mark_keep(self) -> None:
        self._mark_selected("keep")

    def action_mark_archive(self) -> None:
        self._mark_selected("archive")

    def action_mark_delete(self) -> None:
        self._mark_selected("delete")

    def action_filter(self) -> None:
        filters = ["all", "keep", "archive", "delete"]
        idx = filters.index(self.current_filter)
        self.current_filter = filters[(idx + 1) % len(filters)]
        self._populate_table()
        self._update_stats()
        self._update_detail()

    def action_apply(self) -> None:
        to_archive = [p for p in self.projects if p.get("action") == "archive"]
        to_delete = [p for p in self.projects if p.get("action") == "delete"]

        if not to_archive and not to_delete:
            self.notify("Nothing to do — all projects marked as keep.", severity="information")
            return

        lines = []
        if to_archive:
            lines.append(f"[yellow]Archive {len(to_archive)} project(s):[/]")
            for p in to_archive:
                lines.append(f"  → {p['name']}")
        if to_delete:
            lines.append(f"[red]DELETE {len(to_delete)} project(s):[/]")
            for p in to_delete:
                lines.append(f"  ✕ {p['name']}")
        lines.append(f"\nArchive destination: {self.archive_dir}")

        summary = "\n".join(lines)

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                self._execute_actions(to_archive, to_delete)

        self.push_screen(ConfirmScreen(summary), on_confirm)

    def _execute_actions(self, to_archive: list[dict], to_delete: list[dict]) -> None:
        errors = []
        archived = 0
        deleted = 0

        if to_archive:
            self.archive_dir.mkdir(parents=True, exist_ok=True)

        for project in to_archive:
            project_path = Path(project["path"])
            if not project_path.exists():
                errors.append(f"Not found: {project['name']}")
                continue
            try:
                archive_path = self.archive_dir / project["name"]
                # shutil.make_archive wants the base name without extension
                shutil.make_archive(str(archive_path), "zip", project_path.parent, project_path.name)
                shutil.rmtree(project_path)
                archived += 1
            except Exception as e:
                errors.append(f"Archive failed for {project['name']}: {e}")

        for project in to_delete:
            project_path = Path(project["path"])
            if not project_path.exists():
                errors.append(f"Not found: {project['name']}")
                continue
            try:
                shutil.rmtree(project_path)
                deleted += 1
            except Exception as e:
                errors.append(f"Delete failed for {project['name']}: {e}")

        # Remove actioned projects from the list
        actioned_paths = {p["path"] for p in to_archive + to_delete}
        self.projects = [p for p in self.projects if p["path"] not in actioned_paths or p["path"] in {
            e.split(": ")[1] if ": " in e else "" for e in errors
        }]

        self._populate_table()
        self._update_stats()

        msg = f"Done: {archived} archived, {deleted} deleted."
        if errors:
            msg += f" {len(errors)} error(s) — check notifications."
            for err in errors:
                self.notify(err, severity="error", timeout=10)

        self.notify(msg, severity="information", timeout=5)


def main():
    parser = argparse.ArgumentParser(
        description="Treasure or Trash — review and act on scanned projects."
    )
    parser.add_argument(
        "json_file",
        help="Path to projects.json from the scanner",
    )
    parser.add_argument(
        "--archive-dir",
        default="~/project-archives",
        help="Directory to store archived project zips (default: ~/project-archives)",
    )

    args = parser.parse_args()

    json_path = Path(args.json_file).resolve()
    if not json_path.exists():
        print(f"Error: {json_path} not found", file=sys.stderr)
        sys.exit(1)

    projects = json.loads(json_path.read_text())
    archive_dir = Path(args.archive_dir).expanduser().resolve()

    # Set default action based on verdict
    for p in projects:
        if "action" not in p:
            if p.get("verdict") == "trash":
                p["action"] = "delete"
            elif p.get("verdict") == "treasure":
                p["action"] = "keep"
            else:
                p["action"] = "keep"

    app = ReviewApp(projects, archive_dir)
    app.run()


if __name__ == "__main__":
    main()
