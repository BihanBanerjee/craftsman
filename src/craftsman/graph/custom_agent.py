"""Custom LangGraph agent with full Phase 2 features.

This builds a custom StateGraph instead of using create_react_agent,
enabling proper integration of:
- Permission system with interrupt()
- Doom loop detection as conditional edge
- Context compaction in the loop
- Multi-agent subgraph invocation
"""

from typing import Annotated, Literal, Any
import json

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from craftsman.tools.core import TOOLS
from craftsman.agents.config import get_agent_config
from craftsman.permission.rules import evaluate_permission, PermissionAction, get_agent_rules
from craftsman.graph.safety import check_doom_loop, format_doom_loop_warning, DOOM_LOOP_THRESHOLD
from craftsman.graph.compaction import (
    should_compact,
    prune_tool_outputs,
    RECENT_MESSAGES_TO_KEEP,
    SUMMARY_PROMPT,
)
from craftsman.graph.builder import get_model


class AgentState(TypedDict):
    """State for the custom agent graph."""
    messages: Annotated[list[BaseMessage], add_messages]
    recent_tool_calls: list[dict]
    needs_compaction: bool
    agent_name: str



def build_custom_agent(
    agent_name: str = "coder",
    model_name: str | None = None,
    checkpointer = None,
    approval_policy: str = "ask",
    hook_system = None,
    cwd: str | None = None,
):
    """Build a custom agent graph with all Phase 2 features.

    Features:
    - Permission checks with interrupt() for human-in-the-loop
    - Doom loop detection as conditional routing
    - Context compaction when approaching token limits
    - Subagent delegation tools (for coder agent)
    """
    agent_config = get_agent_config(agent_name)
    model = get_model(model_name)

    # Build the final system prompt once at agent-build time.
    # Captured in the call_model closure so it's injected on every turn.
    final_system_prompt = agent_config.with_dynamic_context(cwd)

    # Build tool list - add extra tools for coder agent
    tools = list(agent_config.tools)
    if agent_name == "coder":
        # Add subagent delegation tools
        from craftsman.agents.subagents import create_subagent_tools
        subagent_tools = create_subagent_tools(model, cwd=cwd)
        tools.extend(subagent_tools)
        
        # Add switch_agent tool
        from craftsman.tools.switch_agent import switch_agent
        tools.append(switch_agent)
        
        # Add memory, web tools, and todo (lazy import for faster startup)
        from craftsman.tools.memory import memory
        from craftsman.tools.web_search import web_search
        from craftsman.tools.web_fetch import web_fetch
        from craftsman.tools.todo import todo
        tools.extend([memory, web_search, web_fetch, todo])
    
    model_with_tools = model.bind_tools(tools)
    
    # --- NODES ---
    
    def call_model(state: AgentState) -> dict:
        """Call the LLM with the current messages."""
        messages = state["messages"]

        # Prepend system prompt if not already present.
        # final_system_prompt is captured from the outer build scope so it's
        # computed once at agent-build time (not re-evaluated per turn).
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=final_system_prompt)] + list(messages)

        # BEFORE_AGENT hook
        if hook_system:
            user_msg = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
            import asyncio
            try:
                asyncio.create_task(hook_system.trigger_before_agent(user_msg))
            except RuntimeError:
                # No event loop running, skip hook
                pass
        
        response = model_with_tools.invoke(messages)
        
        # AFTER_AGENT hook
        if hook_system and hasattr(response, 'content'):
            user_msg = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
            import asyncio
            try:
                asyncio.create_task(hook_system.trigger_after_agent(user_msg, response.content))
            except RuntimeError:
                # No event loop running, skip hook
                pass
        
        return {"messages": [response]}
    
    def check_permissions(state: AgentState) -> dict:
        """Check permissions for pending tool calls, using interrupt() for ASK."""
        messages = state["messages"]
        last_message = messages[-1]
        
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return {}
        
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            args = tool_call.get("args", {})
            pattern = args.get("file_path", args.get("path", args.get("command", "*")))
            
            # BEFORE_TOOL hook
            if hook_system:
                import asyncio
                try:
                    asyncio.create_task(hook_system.trigger_before_tool(tool_name, args))
                except RuntimeError:
                    pass
            
            # Get agent-specific permission rules
            agent_rules = get_agent_rules(agent_name)
            action = evaluate_permission(tool_name, pattern, rules=agent_rules)
            
            if action == PermissionAction.DENY:
                return {
                    "messages": [
                        ToolMessage(
                            content=f"Permission denied: Tool '{tool_name}' is not allowed for pattern '{pattern}'",
                            tool_call_id=tool_call["id"],
                        )
                    ]
                }
            
            elif action == PermissionAction.ASK:
                # Apply approval policy
                from craftsman.permission.rules import apply_policy, ApprovalPolicy
                policy = ApprovalPolicy(approval_policy)
                modified_action = apply_policy(action, policy)
                
                if modified_action == PermissionAction.ALLOW:
                    # Policy auto-approves
                    continue
                elif modified_action == PermissionAction.DENY:
                    return {
                        "messages": [
                            ToolMessage(
                                content=f"Permission denied by policy: Tool '{tool_name}'",
                                tool_call_id=tool_call["id"],
                            )
                        ]
                    }
                
                # Import memory function
                from craftsman.permission.rules import remember_approval
                
                response = interrupt({
                    "type": "permission_request",
                    "tool": tool_name,
                    "pattern": pattern,
                    "args": args,
                    "message": f"Tool '{tool_name}' requires approval. Allow? (args: {args})",
                    "remember_option": True,  # Offer "remember this decision"
                })
                
                # If user chose to remember, save the decision
                if response.get("remember", False):
                    decision = PermissionAction.ALLOW if response.get("approved") else PermissionAction.DENY
                    remember_approval(tool_name, pattern, decision)
                
                if not response.get("approved", False):
                    return {
                        "messages": [
                            ToolMessage(
                                content=f"Permission rejected by user for tool '{tool_name}'",
                                tool_call_id=tool_call["id"],
                            )
                        ]
                    }
        
        return {}
    
    def execute_tools(state: AgentState) -> dict:
        """Execute tool calls and track for doom loop detection."""
        messages = state["messages"]
        last_message = messages[-1]
        
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return {}
        
        # Track tool calls for doom loop detection
        new_tool_calls = []
        for tool_call in last_message.tool_calls:
            new_tool_calls.append({
                "tool": tool_call["name"],
                "args": tool_call.get("args", {}),
            })
        
        # Use ToolNode to execute
        tool_node = ToolNode(tools)
        result = tool_node.invoke(state)
        
        # AFTER_TOOL hook
        if hook_system:
            import asyncio
            for tool_call in last_message.tool_calls:
                tool_name = tool_call["name"]
                args = tool_call.get("args", {})
                # Get result from executed tools
                tool_result = ""
                if "messages" in result:
                    for msg in result["messages"]:
                        if hasattr(msg, "tool_call_id") and msg.tool_call_id == tool_call["id"]:
                            tool_result = msg.content if hasattr(msg, "content") else str(msg)
                            break
                try:
                    asyncio.create_task(hook_system.trigger_after_tool(tool_name, args, tool_result))
                except RuntimeError:
                    pass
        
        # Update recent tool calls
        recent = state.get("recent_tool_calls", [])
        recent = (recent + new_tool_calls)[-(DOOM_LOOP_THRESHOLD + 1):]
        
        return {
            **result,
            "recent_tool_calls": recent,
        }
    
    def handle_doom_loop(state: AgentState) -> dict:
        """Handle doom loop by asking user to continue."""
        recent_calls = state.get("recent_tool_calls", [])
        if recent_calls:
            last_call = recent_calls[-1]
            warning = format_doom_loop_warning(last_call["tool"], last_call["args"])
            
            response = interrupt({
                "type": "doom_loop_warning",
                "message": warning,
                "question": "The agent seems stuck. Continue anyway?",
            })
            
            if not response.get("continue", False):
                return {
                    "messages": [
                        AIMessage(content="Stopping due to detected doom loop. Please provide different instructions.")
                    ]
                }
        
        return {"recent_tool_calls": []}
    
    def check_compaction(state: AgentState) -> dict:
        """Check if context compaction is needed and perform it."""
        messages = state["messages"]
        
        # Check if compaction is needed (with model-specific limits)
        if not should_compact(messages, model_name=model_name):
            return {"needs_compaction": False}
        
        # Perform compaction by summarizing old messages
        if len(messages) <= RECENT_MESSAGES_TO_KEEP:
            return {"needs_compaction": False}
        
        # First, prune old tool outputs to save space
        pruned_messages = prune_tool_outputs(messages)
        
        # Split messages
        old_messages = pruned_messages[:-RECENT_MESSAGES_TO_KEEP]
        recent_messages = pruned_messages[-RECENT_MESSAGES_TO_KEEP:]
        
        # Generate summary using the model (actual LLM call)
        summary_request = [
            SystemMessage(content=SUMMARY_PROMPT),
            *old_messages,
            HumanMessage(content="Please summarize the above conversation.")
        ]
        
        # Use the base model (without tools) for summarization
        base_model = get_model(model_name)
        summary_response = base_model.invoke(summary_request)
        summary = summary_response.content
        
        summary_message = SystemMessage(
            content=f"[CONVERSATION SUMMARY]\n{summary}\n[END SUMMARY]\n\n"
                    f"The above summarizes our earlier conversation. Recent messages follow:"
        )
        
        # Return new compacted messages
        return {
            "messages": [summary_message] + recent_messages,
            "needs_compaction": False,
        }
    
    # --- ROUTING ---
    
    def should_continue(state: AgentState) -> Literal["check_permissions", "check_compaction"]:
        """Route based on whether there are tool calls."""
        messages = state["messages"]
        last_message = messages[-1]
        
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "check_permissions"
        return "check_compaction"
    
    def after_permission_check(state: AgentState) -> Literal["execute_tools", "call_model"]:
        """Route after permission check."""
        messages = state["messages"]
        last_message = messages[-1]
        
        if isinstance(last_message, ToolMessage) and "denied" in last_message.content.lower():
            return "call_model"
        
        return "execute_tools"
    
    def after_tool_execution(state: AgentState) -> Literal["call_model", "doom_loop"]:
        """Check for doom loop after tool execution."""
        recent_calls = state.get("recent_tool_calls", [])
        
        if check_doom_loop(recent_calls):
            return "doom_loop"
        
        return "call_model"
    
    def after_compaction(state: AgentState) -> Literal["end"]:
        """Always end after compaction check (no more tool calls)."""
        return "end"
    
    # --- BUILD GRAPH ---
    
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("call_model", call_model)
    graph.add_node("check_permissions", check_permissions)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("doom_loop", handle_doom_loop)
    graph.add_node("check_compaction", check_compaction)
    
    # Set entry point
    graph.set_entry_point("call_model")
    
    # Add edges
    graph.add_conditional_edges(
        "call_model",
        should_continue,
        {
            "check_permissions": "check_permissions",
            "check_compaction": "check_compaction",
        }
    )
    
    graph.add_conditional_edges(
        "check_permissions",
        after_permission_check,
        {
            "execute_tools": "execute_tools",
            "call_model": "call_model",
        }
    )
    
    graph.add_conditional_edges(
        "execute_tools",
        after_tool_execution,
        {
            "call_model": "call_model",
            "doom_loop": "doom_loop",
        }
    )
    
    graph.add_edge("doom_loop", "call_model")
    
    graph.add_conditional_edges(
        "check_compaction",
        after_compaction,
        {"end": END}
    )
    
    # Compile with checkpointer
    return graph.compile(checkpointer=checkpointer)
