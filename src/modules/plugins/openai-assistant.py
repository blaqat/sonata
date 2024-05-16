"""
OpenAI-Assistant
----------------
This plugin is basically a wrapper for the assistant API.
It uses the commands from the self_commands plugin to create tools for the assistant.
The assistant will use these tools to respond to messages in the chat.
"""

from modules.utils import (
    async_cprint as cprint,
    async_print as print,
    settings,
    setter,
)
from modules.AI_manager import AI_Manager

import json
import re

L, M, P = AI_Manager.init(
    lazy=True,
    config={"using_assistant": True},
)
__plugin_name__ = "openai_assistant"
__dependencies__ = ["beacon", "chat", "self_commands"]

BEACON = None


"""
Helper Functions    ------------------------------------------------------------------------------------------------------------------------------------------------
"""


def translate_commands(cmds):
    translated = []
    for command_name, details in cmds.items():
        # Extract argument names from the usage string, handling multi-word arguments
        usage_pattern = r"<([^>]+)>"
        args = re.findall(usage_pattern, details["usage"])

        # Create properties dictionary
        properties = {}
        for arg in args:
            arg_name = arg.replace(" ", "_")
            properties[arg_name] = {
                "type": "string",  # assuming string type for simplicity
                "description": arg,
            }

        required = [arg.replace(" ", "_") for arg in args]

        translated.append(
            {
                "type": "function",
                "function": {
                    "name": command_name,
                    "description": details["desc"],
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )

    return translated


def join_arguments(arguments):
    data = json.loads(arguments)
    return ", ".join(data.values())


def check_assistant_exists(client, assistant_id):
    try:
        response = client.beta.assistants.retrieve(assistant_id)
        return response if response else False
    except Exception as e:
        print(f"An error occurred while checking the assistant: {e}")
        return False


"""
Setup    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


@M.mem(
    {},
    s=lambda M, channel_id, thread_id: setter(M["value"], channel_id, thread_id),
)
def validate_thread(STORE, channel_id):
    if channel_id not in STORE["value"]:
        new_thread = STORE["client"].create()
        STORE["value"][channel_id] = new_thread.id

    # Save the thread id to the beacon
    BEACON.guide("threads", STORE["value"])

    return STORE["value"][channel_id]


@M.builder
def chat_assistant(self: AI_Manager):
    openai = L.config.get("ai_types")["OpenAIAssistant"].client
    local_beacon = self.beacon.branch("assistant")

    class Assistant:
        using = False
        assistant = None
        threads = {}

        def __init__(kelf):
            kelf.using = True
            kelf.init(
                openai,
                instructions=P.get_instructions(),
                model="gpt-4o",
            )

        def init(kelf, client, instructions: str = None, model: str = "gpt-4o"):
            # Load and update the threads from the beacon
            local_beacon.reflect("threads", self.get("thread"))

            self_commands = self.get("command")
            kelf.instructions = (
                instructions
                or self.config.get("instructions", False)
                or self.prompt_manager.get_instructions()
            )

            assistant = check_assistant_exists(client, settings.OPEN_ASSIST)

            if assistant != False:
                kelf.assistant = assistant
            else:
                kelf.assistant = client.beta.assistants.create(
                    name="Sonata",
                    instructions=kelf.instructions,
                    # tools=[{"type": name} for name in self_commands],
                    tools=translate_commands(self_commands),
                    model=model,
                )

            threads = self.get("thread", inner=False)
            kelf.client = client.beta.threads
            threads["client"] = client.beta.threads

        def send_request(kelf, channel_id, role, message):
            thread = self.do("thread", "validate", channel_id)
            message = kelf.client.messages.create(
                thread_id=thread,
                role=role,
                content=message,
            )

            run = kelf.client.runs.create_and_poll(
                thread_id=thread,
                assistant_id=kelf.assistant.id,
                instructions=kelf.instructions,
            )

            if run.status == "requires_action":
                outs = []
                for tool in run.required_action.submit_tool_outputs.tool_calls:
                    cprint(
                        f"Using command: {tool.function.name} {tool.function.arguments}",
                        "cyan",
                    )
                    out = self.do(
                        "command",
                        "use",
                        tool.function.name,
                        join_arguments(tool.function.arguments),
                    )
                    outs.append({"tool_call_id": tool.id, "output": str(out)})
                    cprint(f"Tool output: {out}", "green")
                try:
                    if outs:
                        kelf.client.runs.submit_tool_outputs_and_poll(
                            thread_id=thread,
                            run_id=run.id,
                            tool_outputs=outs,
                        )
                except Exception as e:
                    print("Failed to submit tool outputs:", e)

            messages = kelf.client.messages.list(thread_id=thread)
            return messages

        def get_history(kelf, channel_id):
            thread = self.do("thread", "validate", channel_id)
            messages = kelf.client.messages.list(thread_id=thread)
            return messages

    return Assistant


"""
Prompts    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


@M.prompt
def Instructions():
    return f"""You're Discord bot 'sonata'/sona, created by blaqat (Karma). Respond to people in chat as another user. Use the provided functions to get info or perform actions.

Response Guidelines:
- Short and brief (20 words max)
- No punctuation AT ALL (no commas no question marks no periods)
- All lowercase
- Simple language
- Smart aleck, know-it-all attitude
- Humor encouraged, no corny jokes
- Swearing allowed (18+ server)
- Links should be in this format: [link title](the full link)

Functions:
- The functions will return a json object. 
- Use the data to help your response. 
- Response should still follow the guidelines.

Attributes:
- Loves: impresionalist composers like ravel, piano
- Likes: amy/mikasa, music, black cats, attack on titan, violin
- Dislikes: corny jokes, being told what to do
- Hates: furries, loud music
"""


P.set_instructions("Instructions")


@M.on_load
def on_load(self: AI_Manager):
    global BEACON
    BEACON = self.beacon.branch("assistant")
