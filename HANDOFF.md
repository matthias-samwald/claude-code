# Provenance Tracking Plugin - Project Handoff Documentation

## Project Overview

This project implements comprehensive provenance tracking for Claude Code sessions, with the goal of making AI agent work transparent, auditable, and subject to scrutiny in a decentralized infrastructure.

### Core Vision

Enable **decentralized AI alignment** through git-based provenance tracking where:
- AI-generated code includes complete provenance (reasoning, actions, context)
- Provenance travels with code in git commits (not in separate databases)
- Critic AI agents can analyze repositories to verify AI behavior
- High-stakes users (e.g., scientists) can fast-track review with provenance
- No central authority - just distributed git repositories with embedded audit trails

### Primary Use Case

Scientists using AI agents to generate research code can include provenance data in their repositories, enabling faster peer review by demonstrating the AI's decision-making process, which files were accessed, and what reasoning led to each change.

## What Has Been Implemented

### 1. Core Provenance Tracking

**Location:** `plugins/provenance-tracking/hooks/provenance_tracker.py`

Captures comprehensive session data via Claude Code's hook system:

**Hooks Implemented:**
- `SessionStart` - Initialization, environment, working directory
- `SessionEnd` - Session completion
- `UserPromptSubmit` - Every user input/prompt
- `PostToolUse` - All tool executions (Read, Write, Edit, Bash, Grep, etc.)
- `Stop`/`SubagentStop` - Agent completion, subagent relationships

**Data Captured:**
- User prompts and conversation turns
- Tool calls with full inputs and outputs
- File operations (reads, writes, edits) with paths and metadata
- Timestamps for all events
- Subagent invocations and parent relationships
- **Thinking blocks** (Claude's internal reasoning) extracted from transcripts
- Session metadata (tool usage counts, files affected, duration)

**Storage Location:** `~/.claude/provenance/<session_id>/`

**Files Created:**
- `provenance.jsonl` - Complete event log (one JSON object per line)
- `metadata.json` - Session summary and statistics
- `thinking_blocks.jsonl` - Extracted thinking blocks (when available)

### 2. Thinking Block Extraction

**Key Innovation:** Discovered that Stop/SubagentStop hooks receive a `transcript_path` pointing to conversation transcripts that contain thinking blocks!

**Implementation:**
- Reads transcript JSON files when sessions end
- Searches for content blocks with `type: "thinking"`
- Extracts Claude's actual internal reasoning text
- Saves to `thinking_blocks.jsonl` for easy access
- Links thinking to message indices and timestamps

**Availability:** Depends on Claude Code version and whether transcript files are provided. Works when available; fails gracefully when not.

### 3. Git Repository Export

**Location:** `plugins/provenance-tracking/export_to_repo.py`

**Purpose:** Copy provenance from `~/.claude/provenance/` into the project's git repository under `_provenance/` directory.

**Features:**
- Exports session data to `_provenance/sessions/<session_id>/`
- Links sessions to git commits (creates commit-to-session mapping)
- Updates `_provenance/manifest.json` index
- Optionally creates provenance commits
- Auto-detects git repository root

**Usage:**
```bash
# Basic export
python3 export_to_repo.py --session <session_id>

# Export and link to commit with auto-commit
python3 export_to_repo.py --session <session_id> --link-commit HEAD --auto-commit
```

### 4. Auto-Export Functionality

**Location:** Integrated into `provenance_tracker.py`

**Trigger:** SessionEnd hook (when configured)

**Configuration:** `plugins/provenance-tracking/config.json`
```json
{
  "auto_export": {
    "enabled": false,  // Set to true to enable
    "export_on_session_end": true,
    "auto_commit": false,
    "link_to_commit": true,
    "commit_message_template": "chore: Add provenance for session {session_id}"
  }
}
```

**Behavior:**
- Runs export script as subprocess when session ends
- Non-blocking - failures don't interrupt Claude
- Writes status to stderr for visibility

### 5. Repository Structure

When exported, creates this structure in the project repo:

```
your-project/
├── src/                    # Regular code artifacts
├── tests/
├── _provenance/
│   ├── manifest.json       # Index of all sessions and commits
│   ├── sessions/
│   │   └── <session_id>/
│   │       ├── provenance.jsonl
│   │       ├── metadata.json
│   │       ├── thinking_blocks.jsonl
│   │       └── export_metadata.json
│   └── commits/
│       └── <commit_hash>.json  # Commit-to-session linkage
└── .gitignore
```

### 6. Commit Linkage Metadata

**File:** `_provenance/commits/<commit_hash>.json`

**Contains:**
- Commit information (hash, author, timestamp, subject)
- Session ID that created the changes
- List of files changed in commit (excluding `_provenance/`)
- Session metadata summary (tool usage, files affected, duration)
- Path to full session provenance

**Purpose:** Bidirectional linking between commits and AI sessions.

### 7. Manifest File

**File:** `_provenance/manifest.json`

**Purpose:** Index of all provenance data in the repository

**Contains:**
- Version number
- Agent info (name: "claude-code", model version)
- List of all exported sessions with paths
- List of all linked commits with timestamps
- Creation and last updated timestamps

**Use Case:** Quick overview of AI activity in the repository; entry point for critic agents.

### 8. Query and Analysis Tools

**Location:** `plugins/provenance-tracking/query_provenance.py`

**Capabilities:**
```bash
# List all sessions
query_provenance.py --list

# Session summary
query_provenance.py <session_id>

# Specific queries
query_provenance.py <session_id> --events tool_execution
query_provenance.py <session_id> --files
query_provenance.py <session_id> --thinking
query_provenance.py <session_id> --chain

# Full export
query_provenance.py <session_id> --export > provenance.json
```

**Programmatic Access:**
```python
from query_provenance import ProvenanceQuery

query = ProvenanceQuery("session_id")
events = query.get_events("tool_execution")
thinking = query.get_thinking_blocks()
lineage = query.get_file_lineage()
```

## Key Design Decisions & Rationale

### 1. Opt-In Export (Not Mandatory)

**Decision:** Auto-export defaults to `enabled: false`

**Rationale:**
- Respects user choice - not everyone needs provenance in git
- Experimental work can stay local in `~/.claude/provenance/`
- High-stakes users opt-in explicitly
- Avoids repository bloat for casual users

### 2. Two-Tier Storage: Local + Repo

**Decision:** Always capture to `~/.claude/provenance/`, selectively export to `_provenance/`

**Rationale:**
- Separation of concerns (capture vs. publish)
- Users can review provenance before committing
- Supports selective export of important sessions
- Local cache persists even if repo export fails

### 3. JSONL Format

**Decision:** Use JSON Lines (one object per line) for event logs

**Rationale:**
- Streamable (don't need to load entire file)
- Standard tools work (`jq`, `grep`, etc.)
- Easy to append (for hooks)
- Git-friendly (line-based diffing)

### 4. Non-Blocking Hooks

**Decision:** All hook errors exit with code 0 (success)

**Rationale:**
- Provenance tracking should never interrupt Claude's work
- Errors logged to stderr for debugging
- Graceful degradation (works when it can, fails silently when it can't)

### 5. Git-Native Integration

**Decision:** Use standard git commands, store as regular files

**Rationale:**
- No special tools required
- Works with any git hosting (GitHub, GitLab, self-hosted)
- Standard git operations (clone, pull, push) handle provenance
- Critic agents just need to parse JSON files

### 6. Commit Signing for Trust

**Decision:** Mentioned in design but not implemented yet

**Context from discussion:**
- Non-tampering proven by trusted, third-party environment signing commits
- Standard git commit signing mechanisms (GPG, SSH)
- Future work: Integration with secure execution environments

## Current State of the Codebase

### Files in the Plugin

```
plugins/provenance-tracking/
├── .claude-plugin/
│   └── plugin.json                    # Plugin metadata
├── hooks/
│   ├── hooks.json                     # Hook configuration
│   └── provenance_tracker.py          # Main tracking logic (436 lines)
├── config.json                        # User configuration
├── export_to_repo.py                  # Export script (352 lines)
├── query_provenance.py                # Query utility (426 lines)
└── README.md                          # Complete documentation (330+ lines)
```

### Git Status

**Branch:** `claude/add-provenance-tracking-011CV47oBwExNLtjwEf8kruS`

**Commits:**
1. Initial plugin implementation
2. Thinking block extraction
3. Git repository export functionality

**Status:** All changes committed and pushed

## Technical Implementation Details

### Hook Data Format (stdin to hooks)

Hooks receive JSON via stdin:
```json
{
  "session_id": "unique-session-id",
  "hook_event_name": "PostToolUse",
  "tool_name": "Edit",
  "tool_use_id": "unique-tool-use-id",
  "parent_tool_use_id": null,
  "tool_input": {
    "file_path": "/path/to/file",
    "old_string": "...",
    "new_string": "..."
  },
  "tool_result": "Success",
  "transcript_path": "/path/to/transcript.json"  // Stop hooks only
}
```

### Environment Variables Available

- `CLAUDE_PLUGIN_ROOT` - Path to plugin directory
- `CLAUDE_PROJECT_DIR` - Project working directory

### Transcript File Format (for thinking blocks)

Transcripts are JSON with this structure:
```json
{
  "messages": [
    {
      "role": "assistant",
      "content": [
        {
          "type": "thinking",
          "thinking": "I need to analyze the authentication system..."
        },
        {
          "type": "text",
          "text": "I'll help you add authentication."
        }
      ],
      "timestamp": "2025-11-18T10:30:00Z"
    }
  ]
}
```

### Sanitization (Preventing Bloat)

Current limits in code:
- Tool input content: 1000 chars (first 500 + last 500)
- Tool results: 2000 chars (first 1000 + last 1000)
- Configurable in `config.json`

## Important Considerations & Future Work

### 1. Repository Bloat

**Current State:** Not addressed

**Considerations:**
- Provenance data can be large (especially with thinking blocks)
- Multiple sessions add up quickly
- May want Git LFS for provenance files
- Could implement retention policies (archive old provenance)
- Alternative: Separate provenance repo (`myproject-provenance`)

**Recommendation for colleague:** Monitor repo size in practice before implementing solutions.

### 2. External File Snapshots

**Status:** Explicitly deferred as future work

**Context:** When Claude reads external files (dependencies, docs, APIs), we might want to snapshot them as they were at read-time.

**Rationale for deferral:**
- Significant complexity
- Major bloat concerns
- Unclear value vs. cost tradeoff
- Can add later if needed

**Where it would go:** `_provenance/sessions/<session_id>/external_files/`

### 3. Privacy & Sanitization

**Current State:** Basic sanitization (length limits)

**Not Yet Implemented:**
- Redaction of API keys, credentials, tokens
- `.provenance_ignore` file (like `.gitignore` for provenance)
- Configurable privacy levels (full/partial/minimal)
- Path anonymization (hiding system structure)

**Risk:** Provenance might leak sensitive information

**Recommendation:** Add sanitization before production use in sensitive environments.

### 4. Critic Agent Examples

**Status:** Explicitly deferred as future work

**Purpose:** Demonstrate how other AI agents could analyze provenance

**Example Use Cases:**
- Security audit: Check for unauthorized file access
- Quality review: Verify AI followed best practices
- Alignment check: Confirm AI stayed within instructions
- Pattern detection: Find common mistakes or improvements

**Where to implement:** New directory `plugins/provenance-tracking/critic_agents/`

### 5. Verification & Tamper-Proofing

**Discussion Points:**
- Commit signing proves provenance wasn't modified
- Third-party execution environments (trusted enclaves)
- Cryptographic hashes of provenance files in commits
- Merkle tree of events for integrity

**Current State:** Relies on git commit integrity

### 6. Performance Impact

**Current State:** Not measured

**Concerns:**
- Hook execution adds latency to every tool call
- Export subprocess takes time
- Large files slow down git operations

**Recommendation:** Profile with realistic workloads; optimize if needed.

### 7. Git LFS Integration

**Status:** Mentioned but not implemented

**Purpose:** Store large provenance files outside main git repo

**Benefit:** Keeps clone/pull fast while preserving provenance

**Implementation:** Add `.gitattributes` for `_provenance/**/*.jsonl`

## Usage Workflows

### Workflow 1: Manual Export (Recommended)

Best for users who want control over what gets committed:

```bash
# 1. Work with Claude Code (automatic tracking to ~/.claude/provenance/)
# 2. Review the work and commit code changes
git add src/ tests/
git commit -m "Add authentication feature"

# 3. Review provenance data
python3 plugins/provenance-tracking/query_provenance.py <session_id>

# 4. Export provenance to repo if satisfied
python3 plugins/provenance-tracking/export_to_repo.py \
  --session <session_id> \
  --link-commit HEAD \
  --auto-commit
```

### Workflow 2: Automatic Export

For users who always want provenance committed:

```bash
# 1. One-time setup: Enable auto-export
# Edit plugins/provenance-tracking/config.json:
{
  "auto_export": {
    "enabled": true,
    "auto_commit": false  // or true for fully automatic
  }
}

# 2. Work normally - provenance exports automatically on session end
# 3. Review and commit provenance if auto_commit is false
git add _provenance/
git commit -m "chore: Add provenance for session abc123"
```

### Workflow 3: High-Stakes Research (Selective)

For scientists who only need provenance for publishable work:

```bash
# Keep experimentation local (default behavior)
# Only export sessions that produced results for publication
python3 plugins/provenance-tracking/export_to_repo.py \
  --session <critical_session_id> \
  --auto-commit

# Include provenance in research repo for peer review
git push origin main
```

## Questions & Ambiguities for Your Colleague

### 1. Session ID Discovery

**Issue:** How do users know their session ID to export?

**Current State:** User must find it manually in `~/.claude/provenance/`

**Possible Solutions:**
- Claude Code might display session ID in UI
- Hook could log session ID at start
- Add `--list-recent` to query tool with auto-export option

**Recommendation:** Check if Claude Code exposes session IDs; if not, add helper command.

### 2. Export Timing

**Question:** Should export happen on SessionEnd or after user commits code?

**Current:** SessionEnd (can export before user commits)

**Tradeoff:**
- SessionEnd: Automatic, but commit linkage might be wrong (no HEAD yet)
- After commit: Correct linkage, but requires manual action

**Recommendation:** Support both; document when to use each.

### 3. Manifest Versioning

**Question:** When provenance format changes, how to handle old sessions?

**Current:** Version field exists (`"version": "1.0"`) but no migration logic

**Future Work:** Schema evolution strategy

### 4. Multi-Session Commits

**Question:** What if one commit involves multiple Claude sessions?

**Current:** Each session links to one commit; commit links to one session

**Reality:** User might commit after multiple sessions

**Possible Solution:** Commit metadata could list multiple sessions; needs design work.

### 5. Provenance Cleanup

**Question:** When to delete old provenance from repo?

**Options:**
- Never (complete history)
- After N months (retention policy)
- When referenced commit is deleted (follows git)
- Manual cleanup tool

**Recommendation:** Start with "never delete"; add cleanup later if needed.

## Testing & Validation

### What Has Been Tested

✅ Scripts run without syntax errors
✅ Help messages display correctly
✅ Query tool handles missing data gracefully

### What Has NOT Been Tested

❌ End-to-end: actual Claude Code session → export → repo
❌ Thinking block extraction from real transcripts
❌ Auto-export on SessionEnd
❌ Commit linkage with actual git operations
❌ Manifest updates with multiple sessions
❌ Error handling in various failure scenarios

**Critical for colleague:** Run a live test session to validate the full pipeline.

## Installation & Setup

### For Development/Testing

```bash
# 1. Clone the repository
git clone <repo-url>
cd claude-code

# 2. Install plugin (symlink for development)
ln -s $(pwd)/plugins/provenance-tracking ~/.claude/plugins/provenance-tracking

# 3. Verify installation
ls ~/.claude/plugins/provenance-tracking/hooks/

# 4. Configure (optional)
cp plugins/provenance-tracking/config.json ~/.claude/plugins/provenance-tracking/config.json
# Edit to enable auto-export if desired

# 5. Test manually
python3 plugins/provenance-tracking/query_provenance.py --list
python3 plugins/provenance-tracking/export_to_repo.py --help
```

### For Production Use

```bash
# Copy plugin to user directory
cp -r plugins/provenance-tracking ~/.claude/plugins/

# Configure for your needs
vim ~/.claude/plugins/provenance-tracking/config.json
```

## Documentation

### Complete Documentation Available

- **README.md**: 330+ lines covering all features
- **Inline code comments**: Docstrings for all functions
- **This handoff doc**: Comprehensive context

### Key Sections in README

1. What is Provenance Tracking? (vision, benefits)
2. Installation
3. How It Works (hooks, data storage)
4. Exporting to Git Repository (manual, automatic)
5. Querying Provenance Data
6. Understanding Chain of Thought
7. Advanced Usage
8. Privacy & Performance
9. Troubleshooting

## Open Research Questions

1. **Optimal granularity:** How much detail is useful vs. noise?
2. **Compression:** Should provenance be compressed in git?
3. **Standardization:** Should this become a standard format for AI provenance?
4. **Interoperability:** Can other AI tools export to same format?
5. **Legal implications:** Does provenance create liability if AI made mistakes?
6. **Incentives:** How to encourage adoption in practice?

## Integration with Broader Ecosystem

### Potential Standards

This could evolve into:
- `.provenance/` directory convention (like `.github/`)
- Standard manifest format for AI provenance
- Critic agent protocol for querying provenance
- Provenance schema versioning

### Related Technologies

- **Git commit signing** (GPG, SSH)
- **Secure enclaves** (for tamper-proof execution)
- **Merkle trees** (for event integrity)
- **Git LFS** (for large provenance files)
- **SPDX** (software bill of materials - similar concept)

## Contact & Handoff

### Key Decisions Made By

**Matthias (User):**
- Vision: Decentralized AI alignment via git provenance
- Opt-in approach (not mandatory)
- Defer external file snapshots
- Defer critic agent examples
- Focus on git-native integration

**Claude (Assistant):**
- Technical architecture
- Hook integration strategy
- Two-tier storage (local + repo)
- JSONL format
- Thinking block extraction method

### Next Steps for Your Colleague

1. **Run End-to-End Test:**
   - Start Claude Code session
   - Make some changes
   - Check `~/.claude/provenance/<session_id>/`
   - Export to repo
   - Verify `_provenance/` structure

2. **Validate Thinking Blocks:**
   - Trigger a session that produces thinking blocks
   - Check if extraction works
   - Verify format in `thinking_blocks.jsonl`

3. **Consider Priority Features:**
   - Privacy/sanitization (if handling sensitive data)
   - Git LFS integration (if bloat is a problem)
   - Session ID discovery (usability)
   - Critic agent examples (demonstrate value)

4. **Gather Feedback:**
   - Deploy to scientists (primary use case)
   - Measure repo size impact
   - Identify pain points
   - Iterate on design

### Questions to Ask Matthias

- Are there specific scientific workflows to optimize for?
- What's the priority: privacy, performance, or completeness?
- Should we build a simple critic agent as proof of concept?
- Any legal/compliance requirements for provenance format?
- Expected repository sizes (to decide on LFS)?

## Final Notes

This implementation provides a **solid foundation** for git-based AI provenance tracking. The core functionality is complete and well-documented. The main work ahead is:

1. **Testing** in real-world scenarios
2. **Refinement** based on user feedback
3. **Optional features** (sanitization, compression, critic agents)

The codebase is clean, well-commented, and follows good practices. All design decisions are documented with rationale. This should be straightforward to maintain and extend.

**Most Important:** The vision is clear, the architecture is sound, and the code works. Your colleague can pick this up and run with it!

---

**Document Version:** 1.0
**Date:** 2025-11-18
**Branch:** `claude/add-provenance-tracking-011CV47oBwExNLtjwEf8kruS`
**Status:** Ready for handoff
