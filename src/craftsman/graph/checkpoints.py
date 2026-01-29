"""Session checkpoint management.

Provides functions to list and restore checkpoints from LangGraph's
SqliteSaver checkpointer. Enables "save point" functionality.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass


@dataclass
class CheckpointInfo:
    """Information about a checkpoint."""
    checkpoint_id: str
    thread_id: str
    timestamp: str
    step: int

def list_checkpoints(
    db_path: Path,
    thread_id: str,
    limit: int = 20,
) -> list[CheckpointInfo]:
    """List checkpoints for a given session (thread_id).
    
    Args:
        db_path: Path to the SQLite database
        thread_id: The session/thread ID to list checkpoints for
        limit: Maximum number of checkpoints to return
    
    Returns:
        List of CheckpointInfo, most recent first
    """
    if not db_path.exists():
        return []
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # LangGraph's SqliteSaver stores checkpoints in 'checkpoints' table
        # with thread_id and thread_ts (timestamp) columns

        cursor.execute("""
            SELECT thread_ts, thread_id
            FROM checkpoints
            WHERE thread_id = ?
            ORDER BY thread_ts DESC
            LIMIT ?
        """, (thread_id, limit)
        )

        checkpoints = []
        for idx, (thread_ts, tid) in enumerate(cursor.fetchall()):
            checkpoints.append(CheckpointInfo(
                checkpoint_id=thread_ts,
                thread_id=tid,
                timestamp=_formmat_timestamp(thread_ts),
                step=idx
            ))
        
        conn.close()
        return checkpoints
    except Exception as e:
        return []


def get_latest_checkpoint(db_path: Path, thread_id: str) -> str | None:
    """Get the latest checkpoint ID for a session.

    Returns:
        The checkpoint_id (thread_ts) or None if no checkpoints exist
    """
    checkpoints = list_checkpoints(db_path, thread_id, limit=1)
    return checkpoints[0].checkpoint_id if checkpoints else None


def get_session_count(db_path: Path) -> dict[str, int]:
    """Get count of checkpoints per session.

    Returns:
        Dict mapping thread_id to checkpoint count
    """

    if not db_path.exists():
        return {}
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT thread_id, COUNT(*) as count
            FROM checkpoints
            GROUP BY thread_id
            ORDER BY MAX(thread_ts) DESC
        """)

        result = {tid: count for tid, count in cursor.fetchall()}
        conn.close()
        return result
    except Exception:
        return {}
    

def _formmat_timestamp(thread_ts: str) -> str:
    """Format a LangGraph thread_ts into human-readable format."""
    try:
        # LangGraph uses UUIDs or timestamps as thread_ts
        # If it's a UUID, just return a shortened version
        if len(thread_ts) > 20:
            return thread_ts[:8] + "..."
        return thread_ts
    except Exception:
        return thread_ts
    

def format_checkpoint_table(checkpoints: list[CheckpointInfo]) -> str:
    """Format checkpoints as a text table for display."""
    if not checkpoints:
        return "No checkpoints found for this session."
    
    lines = ["📍 Session Checkpoints:", ""]
    lines.append(f"{'#':<4} {'Checkpoint ID':<40} {'Thread ID':<15}")
    lines.append("-" * 60)
    
    for i, cp in enumerate(checkpoints):
        short_id = cp.checkpoint_id[:36] if len(cp.checkpoint_id) > 36 else cp.checkpoint_id
        lines.append(f"{i:<4} {short_id:<40} {cp.thread_id:<15}")
    
    lines.append("")
    lines.append("Use /restore <#> or /restore <checkpoint_id> to restore to a checkpoint.")
    
    return "\n".join(lines)


def export_session(
    db_path: Path,
    thread_id: str,
    output_path: Path | None = None,
    agent: str = "coder",
) -> tuple[bool, str]:
    """Export a session's conversation history to markdown.

    Args:
        db_path: Path to the SQLite database
        thread_id: The session/thread ID to export
        output_path: Path to write the markdown file (default: session-<id>.md)
        agent: Agent mode used
    
    Returns:
        Tuple of (success, message or file path)    
    """

    if not db_path.exists():
        return False, "No session database found."
    
    if output_path is None:
        output_path = Path.cwd() / f"session-{thread_id}.md"
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get checkpoint blobs with messages
        cursor.execute(
            """
            SELECT checkpoint, thread_ts
            FROM checkpoints
            WHERE thread_id = ?
            ORDER BY thread_ts ASC
            """, (thread_id))
        
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return False, f"No conversation found for session '{thread_id}'."
        
        # Build markdown content
        lines = [
            f"# Agent CLI Session: {thread_id}",
            "",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"**Agent:** {agent}",
            "",
            "---",
            "",
        ]

        # Parse checkpoint blobs to extract messages
        

        message_count = 0

        for checkpoint_blob, _ in rows:
            try:
                # Checkpoints are stored as JSON or pickle
                # Try to decode as JSON first

                if isinstance(checkpoint_blob, bytes):
                    try:
                        checkpoint = json.loads(checkpoint_blob.decode('utf-8'))
                    except:
                        # Skip binary pickled checkpoints
                        continue
                else:
                    checkpoint = json.loads(checkpoint_blob) if isinstance(checkpoint_blob, str) else checkpoint_blob

                
                # Extract messages from checkpoint state
                if isinstance(checkpoint, dict):
                    channel_values = checkpoint.get('channel_values', {})
                    messages = channel_values.get('messages', [])

                    for msg in messages:
                        if isinstance(msg, dict):
                            role = msg.get('type', 'unknown')
                            content = msg.get('content', '')

                            if role == 'human':
                                lines.append("## 👤 User")
                                lines.append("")
                                lines.append(content)
                                lines.append("")
                                lines.append("---")
                                lines.append("")
                                message_count += 1
                            
                            elif role == 'ai':
                                lines.append("## 🤖 Assistant")
                                lines.append("")
                                lines.append(content if content else "(tool call)")
                                lines.append("")
                                lines.append("---")
                                lines.append("")
                                message_count += 1         
            except Exception:
                continue
        

        if message_count == 0:
            # Fallback message
            lines.append("*No messages could be extracted from checkpoints.*")
            lines.append("")
            lines.append(f"Session had {len(rows)} checkpoints.")
        

        # Write to file
        output_path.write_text("\n".join(lines))

        return True, str(output_path)
    
    except Exception as e:
        return False, f"Export failed: {e}"




    
