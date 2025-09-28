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

from dotenv import load_dotenv
import os
from enum import Enum
import time
from datetime import datetime
import asyncio
from tools import move, routine
from prompt_templates import system_prompt_str, init_state_prompt_str, stimuli_prompt_str
from characters import characters
import re

load_dotenv()
key = os.getenv('GROQ_API_KEY')

class AgentLoopController:
    """Handles the main agent interaction loop, separated for future inter-agent communication"""

    def __init__(self, character_key):
        self.character = characters[character_key]

        # Create tools
        self.tools = [
            FunctionTool.from_defaults(move),
            FunctionTool.from_defaults(routine)
        ]
        self.tools_by_name = {t.metadata.name: t for t in self.tools}

        # Setup prompts
        system_prompt_template = RichPromptTemplate(system_prompt_str)
        self.system_prompt = system_prompt_template.format(
            character=self.character['name'],
            profession=self.character['profession'],
            background=self.character['ai_prompt']
        )

        self.init_state_prompt = self._build_init_state_prompt(RichPromptTemplate(init_state_prompt_str))
        self.stimuli_prompt = self._build_stimuli_prompt(RichPromptTemplate(stimuli_prompt_str))

        # Initialize chat history with system prompt
        self.chat_history = [
            ChatMessage(role='system', content=self.system_prompt)
        ]

        # Create endpoint
        self.endpoint = Groq(model="qwen/qwen3-32b", api_key=key, tools=self.tools)

    """
    Things we need for convo
    1. agent, during routine, calls action (converse) to talk to another agent
    2. converse returns their location, if their location is the same as where the agent currently is, converse will return a string
    saying "you dont need to move, how would you like to greet them?". Otherwise "you have moved to (their location), how would you like to greet them?"
    3. 
    """
        
    async def run_single_iteration(self, iteration):
        """Execute a single iteration of the agent loop"""
        print(f"\n--- Iteration {iteration + 1} ---")

        thinking_resp = await self.prompt_agent(iteration)

        if not thinking_resp:
            raise ValueError('ERROR: agent response invalid')
            
        self.chat_history.append(thinking_resp.message)
        
        # Extract desired action
        desired_action = re.search(r"ACTION_IM_GOING_TO_TAKE: (.+)", thinking_resp.message.content)
        

        await asyncio.sleep(1)
        
        # STEP 2: Execute the action (WITH tools available)
        success = await self._execute_agent_action(desired_action)
        return success

    async def conversation_loop():
        pass
    
    def _build_init_state_prompt(self, init_state_prompt_template):
        """Generate the current initialization state prompt"""
        return init_state_prompt_template.format(
            location=self.character.get('start_location', 'Unknown location'),
            mood=self.character.get('mood', 'neutral'),
            actions=self.character.get('actions', [])
        )

    def _build_stimuli_prompt(self, stimuli_prompt_template, events = None):
        """Generate the current stimuli prompt"""
        if events == None:
            events = ['']
        return stimuli_prompt_template.format(
            time=datetime.now(),
            events=events
        )
    
    def _build_thinking_prompt(self, iteration):
        """Build the appropriate thinking prompt based on iteration"""
        thinking_prompt = f'{self.stimuli_prompt}\nWhat action would you like to take next? Think through your options and reasoning. Again, do NOT call any tools yet. End with a concise action summary in the format "ACTION_IM_GOING_TO_TAKE: summary"'
        if iteration == 0:
            return f'{self.init_state_prompt}\nHere are the tools you potentially have available. DO NOT call anything yet. \n{[tool.metadata.description for tool in self.tools]}' + thinking_prompt
        else:
            return thinking_prompt

    async def routine_loop(self, iterations, events=None):
        """Main routine loop - separated for future inter-agent communication"""
        iteration = 0

        while iteration < iterations:
            success = await self.run_single_iteration(iteration)

            if not success:
                break

            iteration += 1

        if iteration >= iterations:
            print("Max iterations reached. Stopping agent loop.")
    
    async def _get_agent_thoughts(self):
        """Get agent's thinking without tools"""
        
        try:
            while True:
                thinking_resp = await self.endpoint.achat(self.chat_history)
                print("Agent's Thoughts:")
                print(thinking_resp.message.content)
                print()
                if '<tool_call>' in thinking_resp.message.content:
                    # Agent mistakenly made a tool call. Reprompt
                    self.chat_history.pop([-1])
                    self.chat_history.append()
                return thinking_resp
        except Exception as e:
            print(f"Error getting agent thoughts: {e}")
            return None
    
    async def _execute_agent_action(self, desired_action):
        """Execute the agent's chosen action with tools"""
        # Ask for the actual action
        action_prompt = f"Now take the action you decided on, i.e. call the tool corresponding to {desired_action.group(0) if desired_action else 'your planned action'}"
        self.chat_history.append(ChatMessage(role="user", content=action_prompt))
        
        # Call LLM with tools
        try:
            resp = await self.endpoint.achat_with_tools(self.tools, chat_history=self.chat_history)
        except Exception as e:
            print(f"Error calling LLM for action: {e}")
            return False
        
        # Process tool calls
        return self._process_tool_calls(resp)
    
    def _process_tool_calls(self, resp):
        """Process and execute tool calls from LLM response"""
        tool_calls = self.endpoint.get_tool_calls_from_response(
            resp, error_on_no_tool_call=False
        )
        
        if not tool_calls:
            print("No tool call found. Agent may be finished or confused.")
            if resp.message.content:
                print("Agent said:", resp.message.content)
            self.chat_history.append(resp.message)
            return False
        elif len(tool_calls) > 1:
            print(f"Warning: Agent made {len(tool_calls)} tool calls, but we only expect 1 per iteration")
        
        # Add the LLM's response to chat history
        self.chat_history.append(resp.message)

        # Execute the tool call
        return self._execute_tool_call(tool_calls[0])
    
    def _execute_tool_call(self, tool_call):
        """Execute a single tool call and handle results"""
        tool_name = tool_call.tool_name
        tool_kwargs = tool_call.tool_kwargs
        
        print(f"\nExecuting Action: {tool_name} with {tool_kwargs}")
        
        try:
            # Get the tool and execute it
            tool = self.tools_by_name[tool_name]
            tool_output = tool.fn(**tool_kwargs)
            
            # Add tool result to chat history
            self.chat_history.append(
                ChatMessage(
                    role="tool",
                    content=str(tool_output),
                    additional_kwargs={"tool_call_id": tool_call.tool_id}
                )
            )
            
            print(f"Action Result: {tool_output}")
            return True
            
        except Exception as e:
            error_msg = f"Error executing tool {tool_name}: {str(e)}"
            print(f"Action Failed: {error_msg}")
            
            # Add error to chat history
            self.chat_history.append(
                ChatMessage(
                    role="tool",
                    content=error_msg,
                    additional_kwargs={"tool_call_id": tool_call.tool_id}
                )
            )
            return False
    
    async def prompt_agent(self, iteration):
        thinking_prompt = self._build_thinking_prompt(iteration)
        original_history_length = len(self.chat_history)
        self.chat_history.append(ChatMessage(role="user", content=thinking_prompt))

        try:
            while True:
                thinking_resp = await self.endpoint.achat(self.chat_history)
                print("Agent's Thoughts:")
                print(thinking_resp.message.content)
                print()

                if '<tool_call>' not in thinking_resp.message.content:
                    # Success - clean up excess reprompts if any
                    if len(self.chat_history) > original_history_length + 1:
                        self.chat_history = self.chat_history[:original_history_length + 1]
                    return thinking_resp

                # Failed - add response and reprompt
                print('ERROR: Agent made tool call during thinking. Retrying...')
                self.chat_history.append(thinking_resp.message)
                self.chat_history.append(ChatMessage(role="user", content="Retry. DO NOT call any tools."))

        except Exception as e:
            print(f"Error getting agent thoughts: {e}")
            return None


def print_chat_history(chat_history):
    """Print everything in chat_history"""
    print(f"\n{'='*80}")
    print("COMPLETE CHAT HISTORY DEBUG")
    print(f"{'='*80}")
    
    for i, message in enumerate(chat_history):
        print(f"\nMessage {i+1} - Role: {message.role}")
        print(f"Content: {message.content}")
        print("-" * 80)

async def run_manual_agent(character_key: str, iterations: int):
    # Create the loop controller with character - all initialization is now handled in constructor
    loop_controller = AgentLoopController(character_key)

    # Run the routine loop
    await loop_controller.routine_loop(iterations)

    print("\nAgent loop completed.")
    print_chat_history(loop_controller.chat_history)

async def main():
    await run_manual_agent("willem_innkeeper", 5)  # Added missing parameters

if __name__ == '__main__':
    asyncio.run(main())
