#one agent daily routine
# needs to know: what actions it can take
# choose and exec action (tool call -> for now the funciton jsut prints to cli)
# reflect on output of function

# choose action -> perform action (produces output to agent) -> reflect

from llama_index.llms.groq import Groq
from llama_index.core.prompts import RichPromptTemplate

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.llms import ChatMessage
from llama_index.core.memory import Memory

from llama_index.core.tools import FunctionTool

from enum import Enum
import time
from datetime import datetime
import asyncio
from tools import move, routine
from prompt_templates import system_prompt_str, init_state_prompt_str, stimuli_prompt_str

class States(Enum):
    ACT = ""
    PERCEIVE = ""
    REFLECT = ""
    CONVERSATION = ""

async def run_manual_agent():  
    # Create tools
    tools = [
        FunctionTool.from_defaults(move),
        FunctionTool.from_defaults(routine)
    ]

    tools_by_name = {t.metadata.name: t for t in tools}
    
    # Setup prompts
    system_prompt_template = RichPromptTemplate(system_prompt_str)
    system_prompt = system_prompt_template.format(
        character="Willem",
        profession="innkeeper",
        background="You are Willem, owner of the Prancing Pony inn. Your background: You are a former traveling merchant who settled down after two decades of welcoming travelers. Your merchant past gave you contacts in distant towns and an ear for road news. Your common room serves as the unofficial town meeting hall, where you mediate disputes and broker deals. You keep a well-maintained armory in your cellar 'just in case.' Speak with gregarious charm while demonstrating your skill at gathering information and resolving conflicts."
    )
    
    init_state_prompt_template = RichPromptTemplate(init_state_prompt_str)
    init_state_prompt = init_state_prompt_template.format(
        time=datetime.now(),
        location="Willem's house",
        mood="neutral",
        actions=["wake up"]
    )

    stimuli_prompt_template = RichPromptTemplate(stimuli_prompt_str)
    stimuli_prompt = stimuli_prompt_template.format(
        events=[""]
    )
    
    # Initialize chat history with system prompt and user query
    # Short term memory
    chat_history = [
        ChatMessage(role="system", content=system_prompt)
    ]
    
    # Manual agent loop
    max_iterations = 5
    iteration = 0
    
    while iteration < max_iterations:
        print(f"\n--- Iteration {iteration + 1} ---")
        
        # STEP 1: Get thinking/reasoning (NO tools available)
        if iteration == 0:
            thinking_prompt = f"{init_state_prompt}\n{stimuli_prompt}\nHere are the tools you potentially have available. DO NOT call anything yet. \n{[tool.metadata.description for tool in tools]}\n What are you thinking about doing next? Describe your thoughts, reasoning, and decision-making process. End with <action>summary of what you want to do</action> tags."
        else:
            thinking_prompt = "What would you like to do next? Think through your options and reasoning. End with <action>summary of what you want to do</action> tags."
        
        chat_history.append(ChatMessage(role="user", content=thinking_prompt))
        
        # Call LLM WITHOUT tools to get pure thinking
        try:
            thinking_resp = await llm.achat(chat_history)
            print("Agent's Thoughts:")
            print(thinking_resp.message.content)
            print()
        except Exception as e:
            print(f"Error getting agent thoughts: {e}")
            break
        
        # Add thinking response to history
        chat_history.append(thinking_resp.message)
        
        # STEP 2: Now ask for the actual action (WITH tools available)
        action_prompt = "Now take the action you decided on."
        chat_history.append(ChatMessage(role="user", content=action_prompt))
        
        # Call LLM with tools to get the action
        try:
            resp = await llm.achat_with_tools(tools, chat_history=chat_history)
        except Exception as e:
            print(f"Error calling LLM for action: {e}")
            break
        
        # Parse tool calls from response
        tool_calls = llm.get_tool_calls_from_response(
            resp, error_on_no_tool_call=False
        )
        
        # We expect exactly one tool call per iteration
        if not tool_calls:
            print("No tool call found. Agent may be finished or confused.")
            if resp.message.content:
                print("Agent said:", resp.message.content)
            chat_history.append(resp.message)
            break
        elif len(tool_calls) > 1:
            print(f"Warning: Agent made {len(tool_calls)} tool calls, but we only expect 1 per iteration")
        
        # Add the LLM's response (with tool calls) to chat history
        chat_history.append(resp.message)
        
        # Execute the first (and ideally only) tool call
        tool_call = tool_calls[0]
        tool_name = tool_call.tool_name
        tool_kwargs = tool_call.tool_kwargs
        
        print(f"\nExecuting Action: {tool_name} with {tool_kwargs}")
        
        try:
            # Get the tool and execute it
            tool = tools_by_name[tool_name]
            tool_output = tool.fn(**tool_kwargs)
            
            # Add tool result to chat history
            chat_history.append(
                ChatMessage(
                    role="tool",
                    content=str(tool_output),
                    additional_kwargs={"tool_call_id": tool_call.tool_id}
                )
            )
            
            print(f"Action Result: {tool_output}")
            
        except Exception as e:
            error_msg = f"Error executing tool {tool_name}: {str(e)}"
            print(f"Action Failed: {error_msg}")
            
            # Add error to chat history
            chat_history.append(
                ChatMessage(
                    role="tool",
                    content=error_msg,
                    additional_kwargs={"tool_call_id": tool_call.tool_id}
                )
            )
        
        iteration += 1
    
    if iteration >= max_iterations:
        print("Max iterations reached. Stopping agent loop.")
    
    print("\nAgent loop completed.")

async def main():
    system_prompt_template = RichPromptTemplate(system_prompt_str)
    system_prompt = system_prompt_template.format(
        character="Willem",
        profession="innkeeper",
        background="You are Willem, owner of the Prancing Pony inn. Your background: You are a former traveling merchant who settled down after two decades of welcoming travelers. Your merchant past gave you contacts in distant towns and an ear for road news. Your common room serves as the unofficial town meeting hall, where you mediate disputes and broker deals. You keep a well-maintained armory in your cellar 'just in case.' Speak with gregarious charm while demonstrating your skill at gathering information and resolving conflicts."
    )
    
    init_state_prompt_template = RichPromptTemplate(init_state_prompt_str)
    init_state_prompt = init_state_prompt_template.format(
        time=datetime.now(),
        location="Willem's house",
        mood="neutral",
        actions=["wake up"]
    )

    stimuli_prompt_template = RichPromptTemplate(stimuli_prompt_str)
    stimuli_prompt = stimuli_prompt_template.format(
        events=[""]

    )
    
    tools = [FunctionTool.from_defaults(
        tool
    ) for tool in [move, routine]]
    
    endpoint = Groq(model="qwen/qwen3-32b", api_key="", tools=tools)
    agent = FunctionAgent(llm=endpoint, tools=tools, system_prompt=system_prompt)
    memory = Memory.from_defaults(session_id="my_session", token_limit=40000)

    #https://docs.llamaindex.ai/en/stable/module_guides/deploying/agents/memory/#short-term-memory
    # 1) Perceive environment -> update current status + list of actions, rank actions (relevance + importance)
    # 2) Take action with highest rank (tool call)
    # 3) Retrieve result, reflect -> update list of actions, current status, & long term memory)

    response = await agent.run(f"{init_state_prompt}\n{stimuli_prompt}\nWhat are you thinking about doing next? Describe your thoughts and reasoning before taking any action.", memory=memory)
    print(str(response))

async def main():
    await run_manual_agent()

if __name__ == '__main__':
    asyncio.run(main())