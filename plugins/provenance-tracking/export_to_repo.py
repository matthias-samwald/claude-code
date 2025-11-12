#!/usr/bin/env python3
"""
Export provenance data to a git repository.

This script copies provenance data from ~/.claude/provenance/<session_id>/
to the project repository's _provenance/ directory, making it part of the
git history alongside the artifacts created by Claude Code.

Usage:
    # Export a specific session
    python3 export_to_repo.py --session <session_id> --repo /path/to/repo

    # Export and link to current git commit
    python3 export_to_repo.py --session <session_id> --repo /path/to/repo --link-commit HEAD

    # Export and auto-commit the provenance data
    python3 export_to_repo.py --session <session_id> --repo /path/to/repo --auto-commit

    # Export from current directory (auto-detect repo)
    python3 export_to_repo.py --session <session_id>
"""

import json
import sys
import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class ProvenanceExporter:
    """Export provenance data to git repository."""

    def __init__(self, repo_path: Path, session_id: str):
        self.repo_path = Path(repo_path).resolve()
        self.session_id = session_id

        # Provenance directories
        self.home = Path.home()
        self.source_dir = self.home / ".claude" / "provenance" / session_id
        self.target_dir = self.repo_path / "_provenance" / "sessions" / session_id
        self.commits_dir = self.repo_path / "_provenance" / "commits"
        self.manifest_file = self.repo_path / "_provenance" / "manifest.json"

        # Verify source exists
        if not self.source_dir.exists():
            raise ValueError(f"Session {session_id} not found in ~/.claude/provenance/")

        # Verify we're in a git repo
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"{repo_path} is not a git repository")

    def export_session(self) -> Dict[str, Any]:
        """Export session provenance data to repository."""
        print(f"Exporting session {self.session_id} to {self.repo_path}")

        # Create _provenance directory structure
        self.target_dir.mkdir(parents=True, exist_ok=True)
        self.commits_dir.mkdir(parents=True, exist_ok=True)

        # Copy provenance files
        files_copied = []
        for file_name in ["provenance.jsonl", "metadata.json", "thinking_blocks.jsonl"]:
            source_file = self.source_dir / file_name
            if source_file.exists():
                target_file = self.target_dir / file_name
                shutil.copy2(source_file, target_file)
                files_copied.append(file_name)
                print(f"  Copied: {file_name}")

        if not files_copied:
            raise ValueError(f"No provenance files found for session {self.session_id}")

        # Create session export metadata
        export_metadata = {
            "session_id": self.session_id,
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "files_exported": files_copied,
            "source_path": str(self.source_dir),
            "target_path": str(self.target_dir),
        }

        # Write export metadata
        export_metadata_file = self.target_dir / "export_metadata.json"
        with open(export_metadata_file, "w") as f:
            json.dump(export_metadata, f, indent=2)
        print(f"  Created: export_metadata.json")

        return export_metadata

    def link_to_commit(self, commit_ref: str = "HEAD") -> Dict[str, Any]:
        """Link session to a git commit."""
        print(f"\nLinking session to commit {commit_ref}...")

        # Get commit hash
        result = subprocess.run(
            ["git", "rev-parse", commit_ref],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        commit_hash = result.stdout.strip()

        # Get commit info
        result = subprocess.run(
            ["git", "show", "-s", "--format=%H%n%an%n%ae%n%at%n%s", commit_hash],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        lines = result.stdout.strip().split("\n")
        commit_info = {
            "hash": lines[0],
            "author_name": lines[1],
            "author_email": lines[2],
            "timestamp": datetime.fromtimestamp(int(lines[3])).isoformat() + "Z",
            "subject": lines[4] if len(lines) > 4 else "",
        }

        # Get files changed in commit
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        files_changed = [f for f in result.stdout.strip().split("\n") if f and not f.startswith("_provenance/")]

        # Load session metadata
        session_metadata_file = self.target_dir / "metadata.json"
        with open(session_metadata_file, "r") as f:
            session_metadata = json.load(f)

        # Create commit linkage
        commit_linkage = {
            "commit": commit_info,
            "session_id": self.session_id,
            "linked_at": datetime.utcnow().isoformat() + "Z",
            "files_changed_in_commit": files_changed,
            "session_metadata": {
                "started_at": session_metadata.get("started_at"),
                "ended_at": session_metadata.get("ended_at"),
                "total_events": session_metadata.get("total_events"),
                "tool_usage_count": session_metadata.get("tool_usage_count"),
                "files_read": session_metadata.get("files_read"),
                "files_written": session_metadata.get("files_written"),
                "files_edited": session_metadata.get("files_edited"),
            },
            "provenance_path": f"_provenance/sessions/{self.session_id}/",
        }

        # Save commit linkage
        commit_file = self.commits_dir / f"{commit_hash}.json"
        with open(commit_file, "w") as f:
            json.dump(commit_linkage, f, indent=2)
        print(f"  Created: _provenance/commits/{commit_hash}.json")

        return commit_linkage

    def update_manifest(self, commit_linkage: Optional[Dict[str, Any]] = None):
        """Update or create the provenance manifest."""
        print("\nUpdating manifest...")

        # Load existing manifest or create new
        if self.manifest_file.exists():
            with open(self.manifest_file, "r") as f:
                manifest = json.load(f)
        else:
            manifest = {
                "version": "1.0",
                "created_at": datetime.utcnow().isoformat() + "Z",
                "agent": {
                    "name": "claude-code",
                    "model": "claude-sonnet-4-5-20250929",
                },
                "sessions": [],
                "commits": [],
            }

        # Update last_updated
        manifest["last_updated"] = datetime.utcnow().isoformat() + "Z"

        # Add session if not already in manifest
        if self.session_id not in [s.get("session_id") for s in manifest["sessions"]]:
            session_entry = {
                "session_id": self.session_id,
                "exported_at": datetime.utcnow().isoformat() + "Z",
                "path": f"_provenance/sessions/{self.session_id}/",
            }
            manifest["sessions"].append(session_entry)

        # Add commit if provided
        if commit_linkage:
            commit_hash = commit_linkage["commit"]["hash"]
            if commit_hash not in [c.get("commit_hash") for c in manifest["commits"]]:
                commit_entry = {
                    "commit_hash": commit_hash,
                    "session_id": self.session_id,
                    "timestamp": commit_linkage["commit"]["timestamp"],
                    "path": f"_provenance/commits/{commit_hash}.json",
                }
                manifest["commits"].append(commit_entry)

        # Sort by timestamp
        manifest["sessions"].sort(key=lambda s: s.get("exported_at", ""), reverse=True)
        manifest["commits"].sort(key=lambda c: c.get("timestamp", ""), reverse=True)

        # Save manifest
        with open(self.manifest_file, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"  Updated: _provenance/manifest.json")

    def create_provenance_commit(self, message: Optional[str] = None):
        """Create a git commit for the provenance data."""
        print("\nCreating provenance commit...")

        # Add provenance files
        subprocess.run(
            ["git", "add", "_provenance/"],
            cwd=self.repo_path,
            check=True
        )

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=self.repo_path,
        )

        if result.returncode == 0:
            print("  No changes to commit (provenance already up to date)")
            return

        # Create commit
        if not message:
            message = f"chore: Add provenance for session {self.session_id[:8]}"

        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.repo_path,
            check=True
        )
        print(f"  Committed: {message}")

    def export_and_commit(
        self,
        link_to_commit: Optional[str] = None,
        auto_commit: bool = False,
        commit_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Complete export workflow."""
        # Export session data
        export_metadata = self.export_session()

        # Link to commit if requested
        commit_linkage = None
        if link_to_commit:
            commit_linkage = self.link_to_commit(link_to_commit)

        # Update manifest
        self.update_manifest(commit_linkage)

        # Auto-commit if requested
        if auto_commit:
            self.create_provenance_commit(commit_message)

        print("\n✅ Export complete!")
        return {
            "session_id": self.session_id,
            "export_metadata": export_metadata,
            "commit_linkage": commit_linkage,
            "manifest_updated": True,
        }


def find_git_root(start_path: Path) -> Optional[Path]:
    """Find the root of the git repository."""
    current = start_path.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Export Claude Code provenance data to git repository"
    )
    parser.add_argument(
        "--session",
        required=True,
        help="Session ID to export"
    )
    parser.add_argument(
        "--repo",
        help="Path to git repository (default: current directory)"
    )
    parser.add_argument(
        "--link-commit",
        metavar="REF",
        help="Link session to a git commit (e.g., HEAD, abc123)"
    )
    parser.add_argument(
        "--auto-commit",
        action="store_true",
        help="Automatically create a git commit for the provenance data"
    )
    parser.add_argument(
        "--commit-message",
        help="Custom commit message for auto-commit"
    )

    args = parser.parse_args()

    try:
        # Determine repository path
        if args.repo:
            repo_path = Path(args.repo)
        else:
            repo_path = find_git_root(Path.cwd())
            if not repo_path:
                print("Error: Not in a git repository. Use --repo to specify path.", file=sys.stderr)
                sys.exit(1)

        # Create exporter and run
        exporter = ProvenanceExporter(repo_path, args.session)
        result = exporter.export_and_commit(
            link_to_commit=args.link_commit,
            auto_commit=args.auto_commit,
            commit_message=args.commit_message,
        )

        # Print summary
        print(f"\nSession: {result['session_id']}")
        print(f"Exported to: {repo_path}/_provenance/sessions/{args.session}/")
        if result['commit_linkage']:
            print(f"Linked to commit: {result['commit_linkage']['commit']['hash'][:8]}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
