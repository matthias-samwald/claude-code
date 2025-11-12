# Provenance Tracking Plugin

Comprehensive provenance tracking for Claude Code sessions, capturing the complete audit trail of user interactions, tool executions, and file operations.

## What is Provenance Tracking?

Provenance tracking creates a detailed record of:

- **User Input**: Every prompt and question submitted
- **Actions Taken**: All tool calls (Read, Write, Edit, Bash, etc.) with inputs and results
- **Thinking Blocks**: Claude's internal reasoning process (extracted from transcripts)
- **Chain of Thought**: The sequence of operations showing how Claude approached problems
- **File Lineage**: Which files were read, written, or edited, and when
- **Subagent Activity**: Tracking of specialized agents and their relationships
- **Session Metadata**: Timestamps, durations, and summary statistics

This is useful for:
- Understanding Claude's decision-making process
- Debugging complex workflows
- Auditing changes made during a session
- Analyzing tool usage patterns
- Creating reproducible workflows
- Compliance and security audits

## Installation

The plugin is already part of the Claude Code repository in `plugins/provenance-tracking/`.

To enable it in your project:

```bash
# Create a symbolic link in your project
ln -s /path/to/claude-code/plugins/provenance-tracking ~/.claude/plugins/provenance-tracking

# Or copy it to your local plugins directory
cp -r plugins/provenance-tracking ~/.claude/plugins/
```

The plugin will automatically start tracking all sessions once installed.

## How It Works

The plugin uses Claude Code's **hook system** to intercept events:

### Hooks Implemented

1. **SessionStart**: Captures session initialization and environment
2. **SessionEnd**: Marks session completion
3. **UserPromptSubmit**: Tracks every user input
4. **PostToolUse**: Records all tool executions with full context
5. **Stop/SubagentStop**: Tracks agent completion and subagent relationships

### Thinking Block Extraction

When a session or subagent completes, the **Stop/SubagentStop hooks** receive a `transcript_path` pointing to a conversation transcript file. The provenance tracker automatically:

1. **Reads the transcript** - Parses the JSON transcript provided by Claude Code
2. **Extracts thinking blocks** - Searches for content blocks with `type: "thinking"`
3. **Saves separately** - Stores thinking blocks in `thinking_blocks.jsonl` for easy access
4. **Links to events** - Associates thinking with message indices and timestamps

**Note**: Thinking blocks are only available when transcript files are provided by Claude Code. The availability depends on the Claude Code version and session configuration.

### Data Storage

Provenance data is stored in `~/.claude/provenance/<session_id>/`:

```
~/.claude/provenance/
└── <session_id>/
    ├── provenance.jsonl      # Complete event log (JSONL format)
    ├── metadata.json         # Session summary and statistics
    └── thinking_blocks.jsonl # Claude's thinking blocks (when available)
```

### Event Format

Each event in `provenance.jsonl` contains:

```json
{
  "timestamp": "2025-11-12T10:30:45.123Z",
  "event_type": "PostToolUse",
  "session_id": "abc123...",
  "action": "tool_execution",
  "tool_name": "Edit",
  "tool_use_id": "unique-id",
  "parent_tool_use_id": null,
  "is_subagent": false,
  "tool_input": {
    "file_path": "/path/to/file.py",
    "old_string": "...",
    "new_string": "..."
  },
  "tool_result": "...",
  "file_operations": {
    "reads": [],
    "writes": [],
    "edits": [{"path": "/path/to/file.py"}]
  }
}
```

## Usage

### Automatic Tracking

Once installed, provenance tracking happens automatically for all sessions. No action needed!

### Querying Provenance Data

Use the `query_provenance.py` utility to explore tracked data:

#### List All Sessions

```bash
python3 plugins/provenance-tracking/query_provenance.py --list
```

Output:
```
Found 5 tracked sessions:

Session ID                               Started                   Events     Tools Used
----------------------------------------------------------------------------------------------------
abc123def456...                         2025-11-12 10:30:45 UTC   47         8
xyz789uvw012...                         2025-11-11 14:22:13 UTC   123        12
```

#### View Session Summary

```bash
python3 plugins/provenance-tracking/query_provenance.py <session_id>
```

Output:
```
================================================================================
SESSION SUMMARY: abc123def456
================================================================================

Started:      2025-11-12 10:30:45 UTC
Ended:        2025-11-12 11:15:22 UTC
Total Events: 47

Tool Usage:
  Read                    15 calls
  Edit                     8 calls
  Bash                     6 calls
  Write                    3 calls
  Grep                     2 calls

Files Affected:
  Read:    12 files
  Written: 3 files
  Edited:  8 files
```

#### Show All Tool Executions

```bash
python3 plugins/provenance-tracking/query_provenance.py <session_id> --events tool_execution
```

#### Show File Lineage

```bash
python3 plugins/provenance-tracking/query_provenance.py <session_id> --files
```

Output:
```
FILE LINEAGE (8 files):

📄 /home/user/project/src/main.py
   First access: 2025-11-12 10:31:00 UTC
   Last access:  2025-11-12 11:12:33 UTC
   Operations:   3 reads, 0 writes, 2 edits

📄 /home/user/project/README.md
   First access: 2025-11-12 10:35:15 UTC
   Last access:  2025-11-12 10:35:15 UTC
   Operations:   0 reads, 1 writes, 0 edits
```

#### Show Tool Execution Chain

```bash
python3 plugins/provenance-tracking/query_provenance.py <session_id> --chain
```

This shows the sequence of tool calls, useful for understanding Claude's approach.

#### Show Thinking Blocks

```bash
python3 plugins/provenance-tracking/query_provenance.py <session_id> --thinking
```

Output:
```
THINKING BLOCKS (3 total):

1. [2025-11-12 10:32:15 UTC]
   Message: 0, Block: 0
   Thinking:
   I need to first understand the current authentication system
   by searching for existing auth-related files. Let me use Grep
   to find authentication references in the codebase...

2. [2025-11-12 10:45:22 UTC]
   Message: 2, Block: 1
   Thinking:
   Based on the files I've read, I can see the auth system uses
   JWT tokens. I should modify the token validation logic to add
   the requested expiration checking feature...
```

This displays Claude's internal reasoning extracted from session transcripts, providing direct insight into decision-making process.

#### Export Full Provenance as JSON

```bash
python3 plugins/provenance-tracking/query_provenance.py <session_id> --export > provenance.json
```

This exports complete provenance data including all events, metadata, file lineage, and thinking blocks.

## Understanding Chain of Thought

The plugin captures Claude's reasoning process through **two complementary mechanisms**:

### 1. Direct Thinking Blocks

When available, thinking blocks are extracted from session transcripts (provided by Stop hooks). These contain Claude's actual internal reasoning text, giving you direct insight into:
- Problem analysis approach
- Decision-making rationale
- Planning and strategy
- Debugging thought process

View with: `--thinking`

### 2. Inferred Chain of Thought

Even without explicit thinking blocks, you can infer reasoning from behavioral patterns:

1. **Tool Sequence**: The order of tool calls shows how Claude explored the problem
2. **File Operations**: Which files were read before being edited shows information gathering
3. **Subagent Usage**: When Claude delegates to specialized agents
4. **Timestamps**: Time between operations can indicate reasoning complexity

Example inference:
```
1. Grep for "authentication" → Understanding current implementation
2. Read src/auth.py → Deep dive into specific file
3. Read tests/test_auth.py → Understanding test coverage
4. Edit src/auth.py → Making changes
5. Bash: pytest tests/test_auth.py → Validating changes
```

This sequence shows Claude's thought process: explore → understand → modify → validate.

## Advanced Usage

### Programmatic Access

You can import and use the `ProvenanceQuery` class in your own scripts:

```python
from query_provenance import ProvenanceQuery

# Query a session
query = ProvenanceQuery("session_id_here")

# Get all tool executions
tools = query.get_events("tool_execution")

# Analyze file lineage
lineage = query.get_file_lineage()

# Get user interactions
inputs = query.get_user_interactions()

# Get thinking blocks
thinking = query.get_thinking_blocks()
```

### Filtering and Analysis

The JSONL format makes it easy to use standard tools:

```bash
# Count tool usage by type
jq -r 'select(.action=="tool_execution") | .tool_name' provenance.jsonl | sort | uniq -c

# Find all file writes
jq 'select(.action=="tool_execution" and .tool_name=="Write")' provenance.jsonl

# Extract user prompts
jq -r 'select(.action=="user_input") | .prompt' provenance.jsonl

# View all thinking blocks
jq -r '.thinking' thinking_blocks.jsonl

# Search thinking blocks for specific terms
jq -r 'select(.thinking | contains("authentication")) | .thinking' thinking_blocks.jsonl
```

### Integration with CI/CD

You can use provenance data in CI/CD pipelines:

```bash
# Verify no sensitive files were accessed
python3 query_provenance.py $SESSION_ID --files | grep -q "secrets.json" && exit 1

# Export provenance for audit logs
python3 query_provenance.py $SESSION_ID --export > audit_logs/$SESSION_ID.json
```

## Privacy and Performance

### What Gets Tracked

- Tool names and parameters
- File paths (but not full file contents)
- Command strings (first 100 chars for bash)
- Timestamps and metadata

### What's Truncated

To keep storage reasonable:
- Large file contents: First and last 500 chars
- Tool outputs: First and last 1000 chars
- Bash commands: First 100 chars in file lineage

### Disabling Tracking

To temporarily disable for a specific session, you can:

1. Remove the plugin symlink
2. Set permissions to "deny" in `hooks.json`
3. Delete the hook handlers

## Troubleshooting

### No Data Being Tracked

Check:
1. Plugin is installed in `~/.claude/plugins/` or project `.claude/plugins/`
2. Hook script has execute permissions: `chmod +x hooks/provenance_tracker.py`
3. Python 3 is available in PATH

### Query Script Errors

Ensure:
1. Session ID is correct (use `--list` to see available sessions)
2. Provenance directory exists: `~/.claude/provenance/`
3. You have read permissions on the provenance files

### Hook Errors Don't Stop Claude

The provenance tracker is designed to fail gracefully - errors are logged but don't interrupt Claude's operation.

## File Structure

```
provenance-tracking/
├── .claude-plugin/
│   └── plugin.json           # Plugin metadata
├── hooks/
│   ├── hooks.json            # Hook configuration
│   └── provenance_tracker.py # Main tracking logic
├── query_provenance.py       # Query utility
└── README.md                 # This file
```

## Contributing

Ideas for enhancements:

- Web UI for browsing provenance data
- Graph visualization of tool chains
- Integration with git to track code changes
- Export to other formats (CSV, SQLite, etc.)
- Real-time streaming of provenance to external systems
- Machine learning on provenance patterns

## License

Part of the Claude Code repository. See main repository LICENSE.

## See Also

- [Claude Code Documentation](https://docs.claude.com/claude-code)
- [Hook System Guide](https://docs.claude.com/claude-code/hooks)
- [Plugin Development Guide](https://docs.claude.com/claude-code/plugins)
