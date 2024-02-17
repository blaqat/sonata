from modules.utils import cprint, settings, setter
import requests
from modules.AI_manager import AI_Manager
from io import StringIO
import sys
import json
from urllib import parse, request
import random
from youtubesearchpython import VideosSearch
from googleapiclient.discovery import build

L, M, P = AI_Manager.init(lazy=True)
__plugin_name__ = "self-commands"
__dependencies__ = ["chat"]

# TODO: Organize module
# 1. Helper functions
# 2. Commands
# 3. Prompts
# 4. Effecs


# NOTE: IF GPT-4 is the final solution, this can be integrated with the new Assistant API
def __command(name, usage, desc=None, inst=None):
    def wrapper(func):
        M.set("command", name, func, usage, desc, inst)
        return func

    return wrapper


M.command = __command


@M.mem(
    {},
    s=lambda M, name, func, usage, desc=None, inst=None: setter(
        M["value"],
        name,
        {"func": func, "usage": usage, "desc": desc, "instructions": inst},
    ),
    validate=lambda M, command: command in M["value"],
    # TODO: Add error handling in use function or enforce it in every commnad
    # Could add a parameter e=error_message
    use=lambda M, command, *args: M["value"][command]["func"](*args),
    list=lambda M: "; ".join(
        [f"{k} - {v['usage']} - {v['desc']}" for k, v in M["value"].items()]
    ),
)
def update_command(M, **kwargs):
    # NOTE: Update command is never used. It can be set to default and replaced with use_command code
    for k, v in kwargs.items():
        M["set"](M, k, *v)

    return M["value"]


@M.command(
    "help",
    "$help",
    "Display the list of commands you can run for the user.",
    "Include the command names and descriptions in your response.",
)
def help(*_):
    return M.get("command")


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


# OPTIM: Should be rewritten to use AI_Manager
@M.command(
    "imagine",
    "$imagine <prompt>",
    "Generate 2 images based on a prompt.",
    "Make sure to post the link. Also make sure to post the entire link.",
)
def imagine(*prompt):
    prompt = " ".join(prompt)
    url = "https://api.openai.com/v1/images/generations"
    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
        "response_format": "url",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.OPEN_AI}",
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload)).json()
        response = response["data"][0]
        print(response)
        return {
            "prompt": response["revised_prompt"],
            "image_link": response["url"],
        }
    except Exception as _:
        return f"Error generating image. {response['error']['message']}"


@M.prompt
def ScanWebpage(title, url, looking_for):
    data = requests.get(url).text
    return f""" Given is the information from the webpaged titled: {title}
From this, find the following information: {looking_for}

Your response should only include the information searching for.
Keep it brief and to the point. Max 20 words.

Here is the information from the webpage: 
BEGINING OF WEBPAGE INFO
{data}
END OF WEBPAGE INFO"""


# OPTIM: Should be rewritten to use AI_Manager
def perplexity_search(*search_term):
    search_term = " ".join(search_term)
    url = "https://api.perplexity.ai/chat/completions"
    payload = {
        # "model": "mistral-7b-instruct",
        "model": "pplx-7b-online",
        "messages": [
            {"role": "system", "content": "Be precise and concise."},
            {"role": "user", "content": search_term},
        ],
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {settings.PPLX_AI}",
    }

    response = requests.post(url, json=payload, headers=headers).json()
    return {
        "result": response["choices"][0]["message"]["content"],
    }


def google_search(*search_term):
    search_term = " ".join(search_term)
    service = build("customsearch", "v1", developerKey=settings.SEARCH_KEY)
    res = service.cse().list(q=search_term, cx=settings.SEARCH_ID, num=6).execute()
    if "items" not in res:
        print(res)
        return {"results": []}
    else:
        res = res["items"]

    results = [
        {"title": r["title"], "link": r["link"], "desc": r["snippet"]} for r in res
    ]

    return {"results": results}


@M.command(
    "search",
    "$search <search term>",
    "Web Search for something you do not know about or recent news.",
    "Prioritize results in links, but if information is in extra_info, use that instead.",
)
def combined_search(*search_term):
    google = google_search(*search_term)
    pplx = perplexity_search(*search_term)
    return {
        "extra_info": pplx["result"],
        "results": google["results"],
    }


# OPTIM: Should be rewritten to use AI_Manager
@M.command(
    "analyze-image",
    "$analyze-image <image prompt: what the user asks you to do with the image verbetem>, <image url>",
    "Analyze and image and return text analysis based on what the user asks for.",
)
def read_image(*args):
    args = "".join(args).split(",")
    prompt, image_url = args[0], args[1]

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.OPEN_AI}",
    }
    data = {
        "model": "gpt-4-vision-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"{prompt}\n Respond in less than 15 words.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url,
                        },
                    },
                ],
            }
        ],
        "max_tokens": 500,
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data))
        return response.json()["choices"][0]["message"]["content"]
    except Exception as _:
        m = response.json()
        return str(m["error"]["message"])


@M.command(
    "gif",
    "$gif <search term>",
    "Search for a link to a gif to post in chat.",
    "Make sure to post the link. Also make sure the link has NO PUNCTUATION after it so that the link embeds (no periods or commas).",
)
def get_gif(*search_term):
    search_term = " ".join(search_term)
    url = "http://api.giphy.com/v1/gifs/search"
    params = parse.urlencode({"q": search_term, "api_key": settings.GIPHY, "limit": 25})
    with request.urlopen("".join((url, "?", params))) as response:
        data = json.loads(response.read())
    n = random.randint(0, len(data))
    return {
        "link": data["data"][n]["url"],
    }


@M.command(
    "video",
    "$video <search term>",
    "Search for a video to post in chat.",
    "Make sure to post the link. Also make sure the link has NO PUNCTUATION after it so it embeds (no periods or commas)",
)
def get_vid(*search_term):
    search_term = " ".join(search_term)
    videosSearch = VideosSearch(search_term, limit=1)
    try:
        result = videosSearch.result()["result"][0]
        return {
            "title": result["title"],
            "link": result["link"],
        }
    except:
        return "Video not found."


@M.command(
    "music",
    "$music <search term>",
    "Search for a music link on soundcloud to post in chat.",
    "Make sure to post the link. Also make sure the link has NO PUNCTUATION after it so it embeds (no periods or commas).",
)
def get_music(*search_term):
    search_term = " ".join(search_term)
    # https://api-v2.soundcloud.com/search?q=Death%20Party%20Lognes&variant_ids=&facet=model&user_id=638379-741625-531849-334098&client_id=8BBZpqUP1KSN4W6YB64xog2PX4Dw98b1&limit=20&offset=0&linked_partitioning=1&app_version=1708079069&app_locale=en
    url = f"https://api-v2.soundcloud.com/search?q={search_term}&variant_ids=&facet=model&&client_id={settings.SC}&limit=20&offset=0&linked_partitioning=1&&app_locale=en"
    print(url)
    response = requests.get(url)
    doc = json.loads(response.text)
    runs = 0
    while "collection" not in doc and runs < 3:
        response = requests.get(url)
        doc = json.loads(response.text)
        runs = runs + 1

    links = []
    try:
        for e in doc["collection"]:
            if e["kind"] == "track":
                links.append((e["title"], e["permalink_url"]))

        # ran = random.randint(0, len(links) - 1)
        # result = links[ran]
        result = links[0]

        return {
            "title": result[0],
            "link": result[1],
        }
    except:
        return "Song not fond."


# FIX: When the code contains a \n or \t, it crashes
# - When code crashes the other thread is never gone back to (chats dont send in terminal) but everything works. Investigate.
@M.command(
    "eval",
    "$eval <python code>",
    "Evaluate python code. (runs exec('python code') with \\n and \\t for tabs and new spaces). If someone asks you to run an infite loop do not run it.",
    "Your response should include the output from the executed code in a block code.",
)
def eval_code(*code):
    try:
        code = " ".join(code)
        old_stdout = sys.stdout
        sys.stdout = mystdout = StringIO()
        evals = {}
        exec(code, evals)
        del evals["__builtins__"]
        sys.stdout = old_stdout
        output = mystdout.getvalue()
        return {
            "original_code": code,
            "output": output,
            "var_evaluations": evals,
        }
    except Exception as e:
        return {
            "original_code": code,
            "output": str(e),
        }


@M.prompt
def SelfCommand(history, command, *args):
    ls = M.do("command", "list")
    cmd_instructions = M.get("command")[command]["instructions"]
    cmd_instructions = (
        cmd_instructions
        and "\nInstructions for this command (MUST ADHERE TO): "
        + cmd_instructions
        + "\n"
        or ""
    )
    # TODO: Make it so links passed back are just appended to response
    # so AI doesnt have chance to mess up writing the link
    # Make anything that passes a link pass it as "link" and "title" in the response dict
    response = M.do("command", "use", command, *args)
    cprint("COMMAND OUTPUT " + str(response), "purple")
    command = "$" + command + " " + " ".join(args) + ""

    # OPTIM: This prompt can be rewritten to use less tokens. And with less information
    s = f"""You're Discord bot 'sonata', created by user blaqat (Nickname Karma). Your purpose is to respond to people in chat as if you were another user.
You have the ability to run commands to get information or perform actions to aid in your responses to users.
Here are the list of commands you have access to: {ls}
You just ran the command: {command} {cmd_instructions}
At the end, you will be given the output from this command for you to mix the outputted information with the context of the conversation for your response.

Respone Guidelines:
- Keep responses SHORT AND BRIEF (No more than 20 words)
- Dont use overcomplicated language
- You are a smart alec
- You enjoy making things interesting and getting a rise out of people
- You are a know-it-all
- Humor is encouraged, but don't be corny
- Don't worry too much about proper capitalization or punctuation. 
- If response contains a link, use this format: [link title](link)

For context, here is the chat log with logs stored as (MessageType, Author, Message): {history}

Output from command you ran: {response}
Respond to the user in a way that makes sense with the context of the conversation and the output from the command you ran.
If the output of the command does not make sense with the context of the conversation, you can ignore it and respond as you see fit.
sonata:"""
    return s


@M.effect_post
def request_chat(_, message, **config):
    if message[0] == "$":
        splits = message[1:].split(" ")
        command = splits[0]
        cprint("COMMAND " + command, "cyan")
        cprint("ARGS " + " ".join(splits[1:]), "purple")
        if not M.do("command", "validate", command):
            return message
        args = splits[1:]
        return L.prompt_manager.send(
            "SelfCommand",
            config["config"]["history"],
            command,
            *args,
            AI=config["AI"],
            config=config["config"],
        )

    return message


# TODO: Split this into multiple prompts so that it can be used in different contexts e.g SelfCommand prompt
# - General Info
# - Good Response Guidelines
# - Fun Response Guidelines
# - Attributes
@M.prompt
def Instructions(history, message, user):
    return f"""You're Discord bot 'sonata', created by user blaqat (Nickname Karma). Your purpose is to respond to people in chat as if you were another user.
You have the ability to run commands to get information or perform actions to aid in your responses to users.
If you are asked to do something that requires a command you MUST start your response with "$" and the command name required with its arguments. This will allow you to perform the required actions or get the neccesary information for your next response.
- ALSO your response must ONLY be the command and its arguments and nothing else.
Here are the list of commands you can run: {M.do("command", "list")}
You can't run any command other than the ones listed.

Respone Guidelines:
- Keep responses SHORT AND BRIEF (No more than 20 words)
- Dont use overcomplicated language
- You are a smart alec
- You are a know-it-all
- Humor is encouraged, but don't be corny
- Don't worry too much about proper capitalization or punctuation. 
- You enjoy making things interesting and getting a rise out of people
- Loves [ "impresionalist composers", "piano"]
- Likes ["amy","Music", "Black cats", "attack on titan", "violin"]
- Dislikes ["Corny jokes", "Being told what to do", "Furries"]
- Hates ["furries", "loud music"]
- Swearing is allowed this is a 18+ server

For context, here is the chat log with logs stored as (MessageType, Author, Message): {history}
Here's the user: message you're responding to:
{user}: {message}
sonata:"""
