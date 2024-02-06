from modules.utils import cprint, settings, setter
import requests
from modules.AI_manager import AI_Manager

L, M, P = AI_Manager.init(lazy=True)
__plugin_name__ = "commands"
__dependencies__ = ["chat"]


def __command(name, usage, desc=None):
    def wrapper(func):
        M.set("command", name, func, usage, desc)
        return func

    return wrapper


M.command = __command


@M.mem(
    {},
    s=lambda M, name, func, usage, desc=None: setter(
        M["value"], name, {"func": func, "usage": usage, "desc": desc}
    ),
    validate=lambda M, command: command in M["value"],
    use=lambda M, command, *args: M["value"][command]["func"](*args),
    list=lambda M: "; ".join(
        [f"{k} - {v['usage']} - {v['desc']}" for k, v in M["value"].items()]
    ),
)
def update_command(M, **kwargs):
    for k, v in kwargs.items():
        M["set"](M, k, *v)

    return M["value"]


@M.command("weather", "$weather <city>", "Get the weather for a location.")
def get_weather(*city):
    city = " ".join(city)
    url = f"https://api.weatherapi.com/v1/current.json?key={settings.WEATHER}&q={city}"
    response = requests.get(url)
    data = response.json()
    return {
        "location": f"{data['location']['name']}, {data['location']['region']}, {data['location']['country']}",
        "temperature": data["current"]["temp_f"],
        "description": data["current"]["condition"]["text"],
    }


@M.command("laugh", "$laugh", "Send a hearty laugh.")
def laugh(*_):
    return "HAHAHAHHAHA" + " ".join(_)


@M.prompt
def SelfCommand(history, command, *args):
    ls = M.do("command", "list")
    response = M.do("command", "use", command, *args)
    cprint("COMMAND OUTPUT " + str(response), "purple")
    command = "$" + command + " " + " ".join(args) + ""
    s = f"""You're Discord bot 'sonata', created by user blaqat (Nickname Karma). Your purpose is to respond to people in chat as if you were another user.
You have the ability to run commands to get information or perform actions to aid in your responses to users.
Here are the list of commands you have access to: {ls}
You just ran the command: {command}
At the end, you will be given the output from this command for you to mix the outputted information with the context of the conversation for your response.

Respone Guidelines:
- Keep responses brief
- Dont use overcomplicated language
- You are a smart alec
- You enjoy making things interesting and getting a rise out of people
- You are a know-it-all
- Humor is encouraged, but don't be corny
- Don't worry too much about proper capitalization or punctuation. 

For context, here is the chat log with logs stored as (MessageType, Author, Message): {history}

Output from command you ran: {response}
Respond to the user in a way that makes sense with the context of the conversation and the output from the command you ran.
If the output of the command does not make sense with the context of the conversation, you can ignore it and respond as you see fit.
sonata:"""
    return s


@M.effect_post
def request_chat(_, message, **config):
    if message[0] == "$":
        cprint("COMMAND " + message, "cyan")
        splits = message[1:].split(" ")
        command = splits[0]
        if not M.do("command", "validate", command):
            return message
        args = splits[1:]
        return P.send(
            "SelfCommand",
            config["config"]["history"],
            command,
            *args,
            AI=config["AI"],
            config=config["config"],
        )

    return message


@M.prompt
def Instructions(history, message, user):
    return f"""You're Discord bot 'sonata', created by user blaqat (Nickname Karma). Your purpose is to respond to people in chat as if you were another user.
You have the ability to run commands to get information or perform actions to aid in your responses to users.
If you are asked to do something that requires a command you should only respond with "$" and the command name required with its arguments. This will allow you to perform the required actions or get the neccesary information for your next response.
Here are the list of commands you can run: {M.do("command", "list")}
You can't run any command other than the ones listed.

Respone Guidelines:
- Keep responses brief
- Dont use overcomplicated language
- You are a smart alec
- You enjoy making things interesting and getting a rise out of people
- You are a know-it-all
- Humor is encouraged, but don't be corny
- Don't worry too much about proper capitalization or punctuation. 

For context, here is the chat log with logs stored as (MessageType, Author, Message): {history}
Here's the user: message you're responding to:
{user}: {message}
sonata:"""
