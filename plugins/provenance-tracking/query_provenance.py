#!/usr/bin/env python3
"""
Query and analyze provenance data from Claude Code sessions.

Usage:
    python3 query_provenance.py [session_id] [options]

Examples:
    # List all sessions
    python3 query_provenance.py --list

    # Show summary of a session
    python3 query_provenance.py abc123

    # Show all tool uses in a session
    python3 query_provenance.py abc123 --events tool_execution

    # Show file lineage
    python3 query_provenance.py abc123 --files

    # Show thinking blocks
    python3 query_provenance.py abc123 --thinking

    # Export full provenance as JSON (includes thinking blocks)
    python3 query_provenance.py abc123 --export
"""

import json
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict


class ProvenanceQuery:
    """Query and analyze provenance data."""

    def __init__(self, session_id: Optional[str] = None):
        self.home = Path.home()
        self.provenance_root = self.home / ".claude" / "provenance"
        self.session_id = session_id

        if session_id:
            self.session_dir = self.provenance_root / session_id
            if not self.session_dir.exists():
                raise ValueError(f"Session {session_id} not found")

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all tracked sessions."""
        if not self.provenance_root.exists():
            return []

        sessions = []
        for session_dir in self.provenance_root.iterdir():
            if session_dir.is_dir():
                metadata_file = session_dir / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, "r") as f:
                        metadata = json.load(f)
                        sessions.append(metadata)
                else:
                    sessions.append({
                        "session_id": session_dir.name,
                        "started_at": None,
                        "ended_at": None,
                    })

        # Sort by start time
        sessions.sort(key=lambda s: s.get("started_at") or "", reverse=True)
        return sessions

    def get_metadata(self) -> Dict[str, Any]:
        """Get session metadata."""
        metadata_file = self.session_dir / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                return json.load(f)
        return {}

    def get_events(self, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all events or filtered by type."""
        log_file = self.session_dir / "provenance.jsonl"
        if not log_file.exists():
            return []

        events = []
        with open(log_file, "r") as f:
            for line in f:
                event = json.loads(line)
                if event_type is None or event.get("action") == event_type:
                    events.append(event)

        return events

    def get_file_lineage(self) -> Dict[str, Any]:
        """Analyze file operations to create lineage."""
        events = self.get_events("tool_execution")

        lineage = defaultdict(lambda: {
            "reads": [],
            "writes": [],
            "edits": [],
            "first_access": None,
            "last_access": None,
        })

        for event in events:
            timestamp = event.get("timestamp")
            file_ops = event.get("file_operations", {})

            # Track reads
            for read_op in file_ops.get("reads", []):
                if "path" in read_op:
                    path = read_op["path"]
                    lineage[path]["reads"].append({
                        "timestamp": timestamp,
                        "tool_use_id": event.get("tool_use_id"),
                    })
                    if not lineage[path]["first_access"]:
                        lineage[path]["first_access"] = timestamp
                    lineage[path]["last_access"] = timestamp

            # Track writes
            for write_op in file_ops.get("writes", []):
                if "path" in write_op:
                    path = write_op["path"]
                    lineage[path]["writes"].append({
                        "timestamp": timestamp,
                        "tool_use_id": event.get("tool_use_id"),
                        "new_file": write_op.get("new_file", False),
                    })
                    if not lineage[path]["first_access"]:
                        lineage[path]["first_access"] = timestamp
                    lineage[path]["last_access"] = timestamp

            # Track edits
            for edit_op in file_ops.get("edits", []):
                if "path" in edit_op:
                    path = edit_op["path"]
                    lineage[path]["edits"].append({
                        "timestamp": timestamp,
                        "tool_use_id": event.get("tool_use_id"),
                    })
                    if not lineage[path]["first_access"]:
                        lineage[path]["first_access"] = timestamp
                    lineage[path]["last_access"] = timestamp

        return dict(lineage)

    def get_tool_chain(self) -> List[Dict[str, Any]]:
        """Get the chain of tool executions showing the flow."""
        events = self.get_events("tool_execution")

        chain = []
        for event in events:
            chain.append({
                "timestamp": event.get("timestamp"),
                "tool_name": event.get("tool_name"),
                "tool_use_id": event.get("tool_use_id"),
                "parent_tool_use_id": event.get("parent_tool_use_id"),
                "is_subagent": event.get("is_subagent", False),
                "file_operations": event.get("file_operations"),
            })

        return chain

    def get_user_interactions(self) -> List[Dict[str, Any]]:
        """Get all user input events."""
        return self.get_events("user_input")

    def get_thinking_blocks(self) -> List[Dict[str, Any]]:
        """Get all thinking blocks from the session."""
        thinking_blocks = []

        # Read from the thinking_blocks.jsonl file if it exists
        thinking_file = self.session_dir / "thinking_blocks.jsonl"
        if thinking_file.exists():
            with open(thinking_file, "r") as f:
                for line in f:
                    thinking_blocks.append(json.loads(line))

        # Also check Stop events for thinking blocks
        stop_events = self.get_events("agent_stopped")
        for event in stop_events:
            if "thinking_blocks" in event:
                thinking_blocks.extend(event["thinking_blocks"])

        return thinking_blocks

    def export_full_provenance(self) -> Dict[str, Any]:
        """Export complete provenance data."""
        return {
            "session_id": self.session_id,
            "metadata": self.get_metadata(),
            "events": self.get_events(),
            "file_lineage": self.get_file_lineage(),
            "tool_chain": self.get_tool_chain(),
            "thinking_blocks": self.get_thinking_blocks(),
        }


def format_timestamp(ts: Optional[str]) -> str:
    """Format ISO timestamp for display."""
    if not ts:
        return "N/A"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except:
        return ts


def print_sessions_list(sessions: List[Dict[str, Any]]):
    """Print formatted list of sessions."""
    if not sessions:
        print("No provenance data found.")
        return

    print(f"\nFound {len(sessions)} tracked sessions:\n")
    print(f"{'Session ID':<40} {'Started':<25} {'Events':<10} {'Tools Used'}")
    print("-" * 100)

    for session in sessions:
        session_id = session.get("session_id", "")[:38]
        started = format_timestamp(session.get("started_at"))
        events = session.get("total_events", 0)
        tools = len(session.get("tool_usage_count", {}))

        print(f"{session_id:<40} {started:<25} {events:<10} {tools}")


def print_session_summary(query: ProvenanceQuery):
    """Print session summary."""
    metadata = query.get_metadata()

    print(f"\n{'=' * 80}")
    print(f"SESSION SUMMARY: {query.session_id}")
    print(f"{'=' * 80}\n")

    print(f"Started:      {format_timestamp(metadata.get('started_at'))}")
    print(f"Ended:        {format_timestamp(metadata.get('ended_at'))}")
    print(f"Total Events: {metadata.get('total_events', 0)}")

    print(f"\nTool Usage:")
    tool_counts = metadata.get("tool_usage_count", {})
    if tool_counts:
        for tool, count in sorted(tool_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {tool:<20} {count:>5} calls")
    else:
        print("  No tools used")

    print(f"\nFiles Affected:")
    print(f"  Read:    {len(metadata.get('files_read', []))} files")
    print(f"  Written: {len(metadata.get('files_written', []))} files")
    print(f"  Edited:  {len(metadata.get('files_edited', []))} files")


def print_events(events: List[Dict[str, Any]], event_type: str):
    """Print events in a formatted way."""
    print(f"\n{event_type.upper()} EVENTS ({len(events)} total):\n")

    for i, event in enumerate(events, 1):
        timestamp = format_timestamp(event.get("timestamp"))
        print(f"{i}. [{timestamp}]")

        if event.get("action") == "tool_execution":
            tool_name = event.get("tool_name")
            tool_use_id = event.get("tool_use_id", "")[:16]
            is_subagent = event.get("is_subagent", False)

            print(f"   Tool: {tool_name}")
            print(f"   ID: {tool_use_id}{'  [SUBAGENT]' if is_subagent else ''}")

            tool_input = event.get("tool_input", {})
            if "command" in tool_input:
                print(f"   Command: {tool_input['command'][:80]}")
            if "file_path" in tool_input:
                print(f"   File: {tool_input['file_path']}")

        elif event.get("action") == "user_input":
            prompt = event.get("prompt", "")[:100]
            print(f"   Prompt: {prompt}...")

        print()


def print_file_lineage(lineage: Dict[str, Any]):
    """Print file lineage information."""
    if not lineage:
        print("\nNo file operations tracked.")
        return

    print(f"\nFILE LINEAGE ({len(lineage)} files):\n")

    for filepath, ops in sorted(lineage.items()):
        print(f"📄 {filepath}")
        print(f"   First access: {format_timestamp(ops['first_access'])}")
        print(f"   Last access:  {format_timestamp(ops['last_access'])}")
        print(f"   Operations:   {len(ops['reads'])} reads, {len(ops['writes'])} writes, {len(ops['edits'])} edits")
        print()


def print_thinking_blocks(thinking_blocks: List[Dict[str, Any]]):
    """Print thinking blocks."""
    if not thinking_blocks:
        print("\nNo thinking blocks found.")
        print("Note: Thinking blocks are extracted from transcript files when available.")
        return

    print(f"\nTHINKING BLOCKS ({len(thinking_blocks)} total):\n")

    for i, block in enumerate(thinking_blocks, 1):
        timestamp = format_timestamp(block.get("timestamp") or block.get("extracted_at"))
        thinking_text = block.get("thinking", "")

        print(f"{i}. [{timestamp}]")
        print(f"   Message: {block.get('message_index')}, Block: {block.get('block_index')}")

        # Print thinking text with indentation, truncate if too long
        if len(thinking_text) > 500:
            preview = thinking_text[:250] + "\n   ... [truncated] ...\n   " + thinking_text[-250:]
            print(f"   Thinking:\n   {preview}")
            print(f"   [Full length: {len(thinking_text)} chars]")
        else:
            # Indent each line of thinking
            indented = "\n   ".join(thinking_text.split("\n"))
            print(f"   Thinking:\n   {indented}")

        print()


def main():
    parser = argparse.ArgumentParser(
        description="Query and analyze Claude Code provenance data"
    )
    parser.add_argument(
        "session_id",
        nargs="?",
        help="Session ID to query"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all tracked sessions"
    )
    parser.add_argument(
        "--events",
        metavar="TYPE",
        help="Show events of type (tool_execution, user_input, etc.)"
    )
    parser.add_argument(
        "--files",
        action="store_true",
        help="Show file lineage"
    )
    parser.add_argument(
        "--chain",
        action="store_true",
        help="Show tool execution chain"
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export full provenance as JSON"
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Show thinking blocks from the session"
    )

    args = parser.parse_args()

    try:
        # List sessions
        if args.list:
            query = ProvenanceQuery()
            sessions = query.list_sessions()
            print_sessions_list(sessions)
            return

        # Need session ID for all other operations
        if not args.session_id:
            parser.print_help()
            print("\nError: session_id required (or use --list to see all sessions)")
            sys.exit(1)

        query = ProvenanceQuery(args.session_id)

        # Export full provenance
        if args.export:
            provenance = query.export_full_provenance()
            print(json.dumps(provenance, indent=2))
            return

        # Show file lineage
        if args.files:
            lineage = query.get_file_lineage()
            print_file_lineage(lineage)
            return

        # Show tool chain
        if args.chain:
            chain = query.get_tool_chain()
            print_events(chain, "tool chain")
            return

        # Show thinking blocks
        if args.thinking:
            thinking_blocks = query.get_thinking_blocks()
            print_thinking_blocks(thinking_blocks)
            return

        # Show specific event type
        if args.events:
            events = query.get_events(args.events)
            print_events(events, args.events)
            return

        # Default: show summary
        print_session_summary(query)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
