"""
LangGraph orchestration for the Business Advisor Agent.
Uses raw OpenAI SDK with NVIDIA NIM base_url for inference and tool calling.
"""

import json
import time
from typing import TypedDict, Annotated, Sequence
from openai import OpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from backend.config import get_settings
from backend.agents.tools import get_tools
from backend.agents.advisor import get_system_prompt
from backend.logger import get_logger


class AgentState(TypedDict):
    """State for the advisor agent graph."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    location: str


def create_openai_client():
    """Create OpenAI client configured for NVIDIA NIM."""
    settings = get_settings()
    logger = get_logger()
    logger.api_request("NVIDIA NIM", "Initialize Client", f"base_url=integrate.api.nvidia.com")
    return OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=settings.NVIDIA_API_KEY,
    )


def langchain_to_openai_tools(tools):
    """Convert LangChain tools to OpenAI format."""
    logger = get_logger()
    openai_tools = []
    for tool in tools:
        tool_def = {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.args_schema.schema() if hasattr(tool, "args_schema") and tool.args_schema else {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
        openai_tools.append(tool_def)
        logger.debug(f"Registered tool: {tool.name}")
    return openai_tools


def messages_to_openai_format(messages: list[BaseMessage]) -> list[dict]:
    """Convert LangChain messages to OpenAI format."""
    result = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            result.append({"role": "system", "content": msg.content})
        elif isinstance(msg, ToolMessage):
            result.append({
                "role": "tool", 
                "tool_call_id": msg.tool_call_id, 
                "content": str(msg.content)
            })
        elif isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            # NVIDIA NIM requires non-empty content
            content = msg.content if msg.content else "Searching for information..."
            msg_dict = {"role": "assistant", "content": content}
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"])
                        }
                    } for tc in msg.tool_calls
                ]
            result.append(msg_dict)
    return result


def create_advisor_graph(location: str = "India"):
    """
    Create the LangGraph workflow for the Business Advisor.
    """
    logger = get_logger()
    logger.separator(f"Creating Advisor Graph for location: {location}")
    
    settings = get_settings()
    client = create_openai_client()
    system_prompt = get_system_prompt(location)
    tools = get_tools()
    openai_tools = langchain_to_openai_tools(tools)
    
    logger.system(f"Graph initialized with {len(tools)} tools: {[t.name for t in tools]}")
    logger.system(f"Model: {settings.MODEL_NAME}, Temperature: {settings.MODEL_TEMPERATURE}")
    
    def call_model(state: AgentState) -> dict:
        """Call the LLM with the current state."""
        logger.graph_step("agent", "start", "Preparing LLM call")
        
        messages = state["messages"]
        openai_messages = [{"role": "system", "content": system_prompt}]
        openai_messages.extend(messages_to_openai_format(messages))
        
        # Log the full prompt being sent
        logger.model_thinking("prompt_preparation", f"{len(openai_messages)} messages prepared")
        logger.llm_prompt(openai_messages)
        
        # Log API request
        logger.api_request(
            "NVIDIA NIM", 
            "chat/completions",
            f"model={settings.MODEL_NAME}, messages={len(openai_messages)}, tools={len(openai_tools)}"
        )
        
        start_time = time.time()
        
        completion = client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=openai_messages,
            tools=openai_tools,
            tool_choice="auto",
            temperature=settings.MODEL_TEMPERATURE,
            top_p=settings.MODEL_TOP_P,
            max_tokens=settings.MODEL_MAX_TOKENS,
            frequency_penalty=settings.MODEL_FREQUENCY_PENALTY,
            presence_penalty=settings.MODEL_PRESENCE_PENALTY,
        )
        
        duration_ms = (time.time() - start_time) * 1000
        
        response_message = completion.choices[0].message
        content = response_message.content or ""
        tool_calls = response_message.tool_calls
        
        # Log API response
        logger.api_response("NVIDIA NIM", 200, duration_ms)
        
        # Log raw response details
        logger.model_thinking("response_received", f"content_length={len(content)}, tool_calls={len(tool_calls) if tool_calls else 0}")
        
        if content:
            logger.debug(f"Raw content preview: {content[:200]}...")
        
        # Log usage if available
        if hasattr(completion, 'usage') and completion.usage:
            usage = completion.usage
            logger.debug(f"Token usage - Prompt: {usage.prompt_tokens}, Completion: {usage.completion_tokens}, Total: {usage.total_tokens}")
        
        # Clean any raw tool syntax that leaked into content
        # Some models output <|python_tag|><function>... format instead of proper tool calls
        import re
        clean_content = content
        clean_content = re.sub(r'<\|python_?tag\|>.*', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
        clean_content = re.sub(r'<function.*?(?:</function>|$)', '', clean_content, flags=re.DOTALL | re.IGNORECASE)
        clean_content = re.sub(r'\{"query":\s*"[^"]*"[^}]*\}', '', clean_content)
        clean_content = re.sub(r'<\|[^|]*\|>', '', clean_content)
        clean_content = clean_content.strip()
        
        if content != clean_content:
            logger.debug("Content cleaned (removed leaked tool syntax)")
        
        formatted_tool_calls = []
        if tool_calls:
            logger.model_thinking("tool_decision", f"Model wants to call {len(tool_calls)} tool(s)")
            for tc in tool_calls:
                formatted_call = {
                    "name": tc.function.name,
                    "args": json.loads(tc.function.arguments),
                    "id": tc.id
                }
                formatted_tool_calls.append(formatted_call)
                logger.debug(f"Tool call queued: {tc.function.name} with args {tc.function.arguments}")
        
        # Fallback: Check for manual tool calls in text (common with some models)
        if not formatted_tool_calls:
            import uuid
            # Pattern 1: <TOOLCALL>[...]</TOOLCALL>
            toolcall_match = re.search(r'<TOOLCALL>(.*?)</TOOLCALL>', content, re.DOTALL | re.IGNORECASE)
            # Pattern 2: <tool>...</tool>
            tool_match = re.search(r'<tool>(.*?)</tool>', content, re.DOTALL | re.IGNORECASE)
            
            raw_tools = None
            if toolcall_match:
                raw_tools = toolcall_match.group(1)
                clean_content = clean_content.replace(toolcall_match.group(0), "")
            elif tool_match:
                raw_tools = tool_match.group(1)
                clean_content = clean_content.replace(tool_match.group(0), "")
                
            if raw_tools:
                try:
                    # Clean potential markdown code blocks
                    raw_tools = raw_tools.strip()
                    if raw_tools.startswith("```json"):
                        raw_tools = raw_tools[7:]
                    if raw_tools.startswith("```"):
                        raw_tools = raw_tools[3:]
                    if raw_tools.endswith("```"):
                        raw_tools = raw_tools[:-3]
                    
                    parsed_tools = json.loads(raw_tools)
                    if isinstance(parsed_tools, list):
                        logger.model_thinking("tool_decision", f"Found {len(parsed_tools)} manual tool call(s) in text")
                        for tc in parsed_tools:
                            formatted_call = {
                                "name": tc.get("name"),
                                "args": tc.get("arguments", {}),
                                "id": f"call_{uuid.uuid4().hex[:8]}"
                            }
                            formatted_tool_calls.append(formatted_call)
                            logger.debug(f"Manual tool call queued: {formatted_call['name']}")
                    elif isinstance(parsed_tools, dict):
                         # Handle single tool object
                         formatted_call = {
                                "name": parsed_tools.get("name"),
                                "args": parsed_tools.get("arguments", {}),
                                "id": f"call_{uuid.uuid4().hex[:8]}"
                         }
                         formatted_tool_calls.append(formatted_call)
                         logger.model_thinking("tool_decision", "Found 1 manual tool call in text")

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse manual tool call JSON: {e}")
        
        if not formatted_tool_calls:
            logger.model_thinking("response_finalized", "No tool calls - Final response ready")
        
        # NVIDIA NIM requires non-empty content, use placeholder when making tool calls
        final_content = clean_content if clean_content else ("Searching for information..." if tool_calls else "")
        
        logger.graph_step("agent", "end", f"Output: content={len(final_content)} chars, tools={len(formatted_tool_calls)}")
        
        return {"messages": [AIMessage(content=final_content, tool_calls=formatted_tool_calls)]}

    def execute_tools(state: AgentState) -> dict:
        """Execute the requested tool calls."""
        logger.graph_step("tools", "start", "Executing tool calls")
        
        messages = state["messages"]
        last_message = messages[-1]
        tool_outputs = []
        
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            # Find the tool and run it
            tool_func = next((t for t in tools if t.name == tool_name), None)
            if tool_func:
                logger.tool_call_start(tool_name, tool_args)
                
                start_time = time.time()
                try:
                    result = tool_func.invoke(tool_args)
                    duration_ms = (time.time() - start_time) * 1000
                    logger.tool_call_end(tool_name, str(result), duration_ms)
                    
                    tool_outputs.append(ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call["id"]
                    ))
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    logger.tool_call_error(tool_name, str(e))
                    tool_outputs.append(ToolMessage(
                        content=f"Error executing tool: {str(e)}",
                        tool_call_id=tool_call["id"]
                    ))
            else:
                logger.tool_call_error(tool_name, f"Tool not found")
                tool_outputs.append(ToolMessage(
                    content=f"Error: Tool {tool_name} not found",
                    tool_call_id=tool_call["id"]
                ))
        
        logger.graph_step("tools", "end", f"Executed {len(tool_outputs)} tools")
        return {"messages": tool_outputs}

    def should_continue(state: AgentState) -> str:
        """Determine if we should continue to tools or end."""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            logger.debug(f"Routing decision: -> tools ({len(last_message.tool_calls)} pending calls)")
            return "tools"
        logger.debug("Routing decision: -> END (no more tool calls)")
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", execute_tools)
    workflow.set_entry_point("agent")
    
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END}
    )
    workflow.add_edge("tools", "agent")
    
    logger.system("LangGraph workflow compiled successfully")
    
    return workflow.compile()


async def stream_advisor_response(graph, messages: list, location: str = "India"):
    """
    Stream responses from the advisor graph with tool awareness.
    """
    logger = get_logger()
    logger.debug("Starting async stream response")
    
    state = {"messages": messages, "location": location}
    
    async for event in graph.astream_events(state, version="v2"):
        kind = event["event"]
        
        if kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                logger.debug(f"Stream token: {content[:50]}...")
                yield {"type": "token", "content": content}
        
        elif kind == "on_tool_start":
            logger.tool_call_start(event["name"], event['data'].get('input', {}))
            yield {
                "type": "tool_status",
                "status": "start",
                "tool": event["name"],
                "content": f"🔍 Searching: {str(event['data'].get('input', ''))[:50]}..."
            }
        
        elif kind == "on_tool_end":
            logger.tool_call_end(event["name"], str(event.get('data', {}).get('output', ''))[:100])
            yield {
                "type": "tool_status",
                "status": "end",
                "tool": event["name"],
                "content": "✅ Search complete"
            }
