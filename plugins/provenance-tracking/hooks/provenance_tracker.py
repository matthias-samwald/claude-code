#!/usr/bin/env python3
"""
Provenance Tracker for Claude Code

Tracks the complete provenance of Claude Code sessions including:
- User input
- Tool calls and results
- Chain of thought (inferred from tool sequences)
- Session metadata
- Subagent relationships
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


class ProvenanceTracker:
    """Tracks and logs provenance data for Claude Code sessions."""

    def __init__(self, hook_data: Dict[str, Any]):
        self.hook_data = hook_data
        self.session_id = hook_data.get("session_id", "unknown")
        self.hook_event = hook_data.get("hook_event_name", "unknown")
        self.timestamp = datetime.utcnow().isoformat() + "Z"

        # Set up provenance directory
        home = Path.home()
        self.provenance_dir = home / ".claude" / "provenance" / self.session_id
        self.provenance_dir.mkdir(parents=True, exist_ok=True)

        # Provenance log file
        self.log_file = self.provenance_dir / "provenance.jsonl"

    def track_event(self):
        """Track the current hook event."""
        event_data = {
            "timestamp": self.timestamp,
            "event_type": self.hook_event,
            "session_id": self.session_id,
        }

        if self.hook_event == "SessionStart":
            event_data.update(self._track_session_start())
        elif self.hook_event == "SessionEnd":
            event_data.update(self._track_session_end())
        elif self.hook_event == "UserPromptSubmit":
            event_data.update(self._track_user_prompt())
        elif self.hook_event == "PostToolUse":
            event_data.update(self._track_tool_use())
        elif self.hook_event in ["Stop", "SubagentStop"]:
            event_data.update(self._track_stop())

        # Write to JSONL log
        self._write_log(event_data)

        # Update session metadata
        self._update_session_metadata(event_data)

    def _track_session_start(self) -> Dict[str, Any]:
        """Track session initialization."""
        return {
            "action": "session_started",
            "cwd": os.getcwd(),
            "environment": {
                "CLAUDE_PLUGIN_ROOT": os.environ.get("CLAUDE_PLUGIN_ROOT"),
                "CLAUDE_PROJECT_DIR": os.environ.get("CLAUDE_PROJECT_DIR"),
            }
        }

    def _track_session_end(self) -> Dict[str, Any]:
        """Track session termination."""
        return {
            "action": "session_ended"
        }

    def _track_user_prompt(self) -> Dict[str, Any]:
        """Track user input."""
        return {
            "action": "user_input",
            "prompt": self.hook_data.get("user_prompt", ""),
            "conversation_turn": self.hook_data.get("conversation_turn"),
        }

    def _track_tool_use(self) -> Dict[str, Any]:
        """Track tool execution with full provenance."""
        tool_data = {
            "action": "tool_execution",
            "tool_name": self.hook_data.get("tool_name"),
            "tool_use_id": self.hook_data.get("tool_use_id"),
            "parent_tool_use_id": self.hook_data.get("parent_tool_use_id"),
            "is_subagent": self.hook_data.get("parent_tool_use_id") is not None,
        }

        # Include tool input
        tool_input = self.hook_data.get("tool_input", {})
        tool_data["tool_input"] = self._sanitize_tool_input(tool_input)

        # Include tool result
        tool_result = self.hook_data.get("tool_result")
        if tool_result:
            tool_data["tool_result"] = self._sanitize_tool_result(tool_result)

        # Track file operations for lineage
        tool_data["file_operations"] = self._extract_file_operations(
            tool_data["tool_name"],
            tool_input,
            tool_result
        )

        return tool_data

    def _track_stop(self) -> Dict[str, Any]:
        """Track agent/subagent completion."""
        transcript_path = self.hook_data.get("transcript_path")

        stop_data = {
            "action": "agent_stopped",
            "is_subagent": self.hook_event == "SubagentStop",
            "transcript_path": transcript_path,
        }

        # For subagents, track parent relationship
        if self.hook_event == "SubagentStop":
            stop_data["parent_tool_use_id"] = self.hook_data.get("parent_tool_use_id")

        # Extract thinking blocks from transcript if available
        if transcript_path:
            thinking_blocks = self._extract_thinking_from_transcript(transcript_path)
            if thinking_blocks:
                stop_data["thinking_blocks"] = thinking_blocks
                # Also save to a separate file for easy access
                self._save_thinking_blocks(thinking_blocks)

        return stop_data

    def _extract_thinking_from_transcript(self, transcript_path: str) -> list:
        """Extract thinking blocks from transcript file."""
        thinking_blocks = []

        try:
            transcript_file = Path(transcript_path)
            if not transcript_file.exists():
                return thinking_blocks

            with open(transcript_file, "r") as f:
                transcript_data = json.load(f)

            # Transcript may contain messages with thinking blocks
            # Look for content blocks with type "thinking"
            messages = transcript_data if isinstance(transcript_data, list) else transcript_data.get("messages", [])

            for msg_idx, message in enumerate(messages):
                if message.get("role") == "assistant":
                    content = message.get("content", [])

                    # Content can be a list of blocks or a string
                    if isinstance(content, list):
                        for block_idx, block in enumerate(content):
                            if isinstance(block, dict) and block.get("type") == "thinking":
                                thinking_blocks.append({
                                    "message_index": msg_idx,
                                    "block_index": block_idx,
                                    "thinking": block.get("thinking", ""),
                                    "timestamp": message.get("timestamp"),
                                })

        except Exception as e:
            # Log error but don't fail
            sys.stderr.write(f"Error extracting thinking from transcript: {e}\n")

        return thinking_blocks

    def _save_thinking_blocks(self, thinking_blocks: list):
        """Save thinking blocks to a separate file for easy access."""
        try:
            thinking_file = self.provenance_dir / "thinking_blocks.jsonl"

            with open(thinking_file, "a") as f:
                for block in thinking_blocks:
                    block["extracted_at"] = self.timestamp
                    f.write(json.dumps(block) + "\n")

        except Exception as e:
            sys.stderr.write(f"Error saving thinking blocks: {e}\n")

    def _extract_file_operations(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_result: Any
    ) -> Dict[str, Any]:
        """Extract file lineage information from tool operations."""
        operations = {
            "reads": [],
            "writes": [],
            "edits": [],
        }

        if tool_name == "Read":
            file_path = tool_input.get("file_path")
            if file_path:
                operations["reads"].append({
                    "path": file_path,
                    "offset": tool_input.get("offset"),
                    "limit": tool_input.get("limit"),
                })

        elif tool_name == "Write":
            file_path = tool_input.get("file_path")
            if file_path:
                operations["writes"].append({
                    "path": file_path,
                    "new_file": not os.path.exists(file_path),
                })

        elif tool_name == "Edit":
            file_path = tool_input.get("file_path")
            if file_path:
                operations["edits"].append({
                    "path": file_path,
                    "old_string_length": len(tool_input.get("old_string", "")),
                    "new_string_length": len(tool_input.get("new_string", "")),
                    "replace_all": tool_input.get("replace_all", False),
                })

        elif tool_name == "Bash":
            # Try to infer file operations from bash commands
            command = tool_input.get("command", "")
            if any(cmd in command for cmd in ["cat", "less", "head", "tail", "grep"]):
                operations["reads"].append({"inferred_from_bash": command[:100]})
            if any(cmd in command for cmd in ["touch", "echo >", ">"]):
                operations["writes"].append({"inferred_from_bash": command[:100]})

        return operations

    def _sanitize_tool_input(self, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize tool input, truncating large content."""
        sanitized = tool_input.copy()

        # Truncate large content fields
        if "content" in sanitized and isinstance(sanitized["content"], str):
            content = sanitized["content"]
            if len(content) > 1000:
                sanitized["content"] = content[:500] + f"\n... [truncated {len(content) - 1000} chars] ...\n" + content[-500:]

        return sanitized

    def _sanitize_tool_result(self, tool_result: Any) -> Any:
        """Sanitize tool result, truncating large outputs."""
        if isinstance(tool_result, str) and len(tool_result) > 2000:
            return tool_result[:1000] + f"\n... [truncated {len(tool_result) - 2000} chars] ...\n" + tool_result[-1000:]
        return tool_result

    def _write_log(self, event_data: Dict[str, Any]):
        """Write event to JSONL log file."""
        with open(self.log_file, "a") as f:
            f.write(json.dumps(event_data) + "\n")

    def _update_session_metadata(self, event_data: Dict[str, Any]):
        """Maintain session metadata summary."""
        metadata_file = self.provenance_dir / "metadata.json"

        # Load existing metadata
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
        else:
            metadata = {
                "session_id": self.session_id,
                "started_at": None,
                "ended_at": None,
                "total_events": 0,
                "tool_usage_count": {},
                "files_read": set(),
                "files_written": set(),
                "files_edited": set(),
            }

        # Update metadata
        metadata["total_events"] += 1

        if event_data["event_type"] == "SessionStart":
            metadata["started_at"] = event_data["timestamp"]
        elif event_data["event_type"] == "SessionEnd":
            metadata["ended_at"] = event_data["timestamp"]
        elif event_data["event_type"] == "PostToolUse":
            tool_name = event_data.get("tool_name")
            if tool_name:
                metadata["tool_usage_count"][tool_name] = metadata["tool_usage_count"].get(tool_name, 0) + 1

            # Track file operations
            file_ops = event_data.get("file_operations", {})
            for read_op in file_ops.get("reads", []):
                if "path" in read_op:
                    metadata["files_read"].add(read_op["path"])
            for write_op in file_ops.get("writes", []):
                if "path" in write_op:
                    metadata["files_written"].add(write_op["path"])
            for edit_op in file_ops.get("edits", []):
                if "path" in edit_op:
                    metadata["files_edited"].add(edit_op["path"])

        # Convert sets to lists for JSON serialization
        metadata["files_read"] = list(metadata["files_read"])
        metadata["files_written"] = list(metadata["files_written"])
        metadata["files_edited"] = list(metadata["files_edited"])

        # Write updated metadata
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)


def main():
    """Main entry point for the provenance tracker hook."""
    try:
        # Read hook data from stdin
        hook_data = json.load(sys.stdin)

        # Create tracker and track event
        tracker = ProvenanceTracker(hook_data)
        tracker.track_event()

        # Exit successfully
        sys.exit(0)

    except Exception as e:
        # Log error but don't fail - we don't want to interrupt Claude
        error_msg = f"Provenance tracking error: {str(e)}\n"
        sys.stderr.write(error_msg)
        sys.exit(0)  # Exit 0 to not interrupt Claude


if __name__ == "__main__":
    main()
