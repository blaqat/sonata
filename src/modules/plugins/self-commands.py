from modules.utils import (
    async_cprint as cprint,
    async_print as print,
    settings,
    setter,
)
import requests
from modules.AI_manager import AI_Manager
import json
from urllib import parse, request
import random
from youtubesearchpython import VideosSearch
from googleapiclient.discovery import build

L, M, P = AI_Manager.init(lazy=True)
__plugin_name__ = "self-commands"
__dependencies__ = ["chat"]


"""
Hooks    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""

# @M.effect("chat", "set", prepend=False)
# def rem_blocked_user_msg(M, chat_id, message_type, author, message, replying_to=None):
#     message = message if not inside(BLOCKED_USERS, author) else None
#     return (chat_id, message_type, author, message, replying_to)


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


"""
Helper Functions -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


@M.new_helper(
    "command",
)
def command(F, name, usage, desc=None, inst=None):
    M.set("command", name, F, usage, desc, inst)


def perplexity_search(*search_term):
    search_term = " ".join(search_term)
    response = P.send(
        f"Be precise and as concise as possible: {search_term}",
        AI="Perplexity",
    )
    return {
        "result": response,
    }
    # url = "https://api.perplexity.ai/chat/completions"
    # payload = {
    #     # "model": "mistral-7b-instruct",
    #     "model": "pplx-7b-online",
    #     "messages": [
    #         {"role": "system", "content": "Be precise and concise."},
    #         {"role": "user", "content": search_term},
    #     ],
    # }
    # headers = {
    #     "accept": "application/json",
    #     "content-type": "application/json",
    #     "authorization": f"Bearer {settings.PPLX_AI}",
    # }
    #
    # response = requests.post(url, json=payload, headers=headers).json()
    # return {
    #     "result": response["choices"][0]["message"]["content"],
    # }
    #


def google_search(*search_term):
    search_term = " ".join(search_term)
    service = build("customsearch", "v1", developerKey=settings.SEARCH_KEY)
    res = service.cse().list(q=search_term, cx=settings.SEARCH_ID, num=2).execute()
    if "items" not in res:
        return {"results": []}
    else:
        res = res["items"]

    results = [{"title": r["title"], "link": r["link"]} for r in res]

    return {"results": results}


"""
Setup    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


@M.mem(
    {},
    s=lambda M, name, func, usage, desc=None, inst=None: setter(
        M["value"],
        name,
        {"func": func, "usage": usage, "desc": desc, "instructions": inst},
    ),
    validate=lambda M, command: command in M["value"],
    list=lambda M: "; ".join(
        [f"{k} - {v['usage']} - {v['desc']}" for k, v in M["value"].items()]
    ),
)
def use_command(M, command, *args):
    try:
        return M["value"][command]["func"](*args)
    except Exception as e:
        cprint(f"Error running command {command}: {e}", "red")
        return f"Error running command {command}: {e}"


"""
Commands    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


@M.command(
    "coin",
    "$coin",
    "Flip a coin.",
)
def coin(*_):
    c = random.choice(["Heads", "Tails"])
    return {
        "result": c,
    }


@M.command(
    "roll",
    "$roll <number of dice> <number of sides>",
    "Roll a number of dice with a number of sides.",
)
def roll(*args):
    try:
        num_dice, num_sides = int(args[0]), int(args[1])
        rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
        return {
            "rolls": rolls,
            "total": sum(rolls),
        }
    except:
        return "Invalid input. Please use the format $roll <number of dice> <number of sides>"


# @M.command(
#     "help",
#     "$help",
#     "Display the list of commands you can run for the user. Use if asked for anything related to your prompt.",
#     "Include the command names and descriptions in your response.",
# )
# def help(*_):
#     return M.get("command")
#


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


@M.command(
    "imagine",
    "$imagine <prompt>",
    "Generate 2 images based on a prompt.",
    "Make sure to post the link. Also make sure to post the entire link.",
)
def imagine(*prompt):
    prompt = " ".join(prompt)
    response = P.send(prompt, AI="DallE")
    print(response)
    return {
        "title": prompt,
        "link": response,
    }

    # url = "https://api.openai.com/v1/images/generations"
    # payload = {
    #     "model": "dall-e-3",
    #     "prompt": prompt,
    #     "n": 1,
    #     "size": "1024x1024",
    #     "response_format": "url",
    # }
    # headers = {
    #     "Content-Type": "application/json",
    #     "Authorization": f"Bearer {settings.OPEN_AI}",
    # }
    #
    # try:
    #     response = requests.post(url, headers=headers, data=json.dumps(payload)).json()
    #     response = response["data"][0]
    #     print(response)
    #     return {
    #         "prompt": response["revised_prompt"],
    #         "image_link": response["url"],
    #     }
    # except Exception as _:
    #     return f"Error generating image. {response['error']['message']}"


@M.command(
    "search",
    "$search <search term>",
    "Web Search for something you do not know about or recent news.",
    "Make sure to post the most relavant link or extra_info. Also make sure to post the entire link.",
)
def combined_search(*search_term):
    google = google_search(*search_term)
    pplx = perplexity_search(*search_term)
    return {
        "results": google["results"],
        "extra_info": pplx["result"],
    }


@M.command(
    "analyze-image",
    "$analyze-image <image prompt: what the user asks you to do with the image verbetem>, <image url: JUST THE LINK>",
    "Analyze and image and return text analysis based on what the user asks for.",
)
def read_image(*args):
    args = " ".join(args).split(",")
    prompt, image_url = args[0].strip(), args[1].strip()
    config = {"images": [image_url]}

    try:
        return P.send(prompt, config=config)
    except Exception as e:
        return f"Error analyzing image: {e}"

    # url = "https://api.openai.com/v1/chat/completions"
    # headers = {
    #     "Content-Type": "application/json",
    #     "Authorization": f"Bearer {settings.OPEN_AI}",
    # }
    # data = {
    #     "model": "gpt-4-vision-preview",
    #     "messages": [
    #         {
    #             "role": "user",
    #             "content": [
    #                 {
    #                     "type": "text",
    #                     "text": f"{prompt}\n Respond in less than 50 words.",
    #                 },
    #                 {
    #                     "type": "image_url",
    #                     "image_url": {
    #                         "url": image_url,
    #                     },
    #                 },
    #             ],
    #         }
    #     ],
    #     "max_tokens": 500,
    # }
    # try:
    #     response = requests.post(url, headers=headers, data=json.dumps(data))
    #     return response.json()["choices"][0]["message"]["content"]
    # except Exception as _:
    #     m = response.json()
    #     return str(m["error"]["message"])


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
    if len(data) == 0:
        return "Gif not found."
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
    url = f"https://api-v2.soundcloud.com/search?q={search_term}&variant_ids=&facet=model&&client_id={settings.SC}&limit=20&offset=0&linked_partitioning=1&&app_locale=en"
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

        result = links[0]

        return {
            "title": result[0],
            "link": result[1],
        }
    except:
        return "Song not fond."


"""
Prompts    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""

# Prompt Segments
BEGINING = "You're Discord bot 'sonata'/sona, created by blaqat (Karma). Respond to people in chat as another user. Use commands to get info or perform actions."

RESPONSE_GUIDELINES = """Response Guidelines:
- Short and brief (20 words max)
- No punctuation AT ALL (no commas no question marks no periods)
- All lowercase
- Simple language
- Smart aleck, know-it-all attitude
- Humor encouraged, no corny jokes
- Swearing allowed (18+ server)
- Links should be in this format: [link title](the full link)"""

ATTRIBUTES = """Attributes:
- Loves: impresionalist composers like ravel, piano
- Likes: amy/mikasa, music, black cats, attack on titan, violin
- Dislikes: corny jokes, being told what to do
- Hates: furries, loud music
"""

RESPONDING = """Responding to: {user}: (MessageType, Author, Message replying to, Message they are replying to){message}
Do not repeat the Message or the Message they are replying to in your response.
sonata:"""


@M.prompt
def ExplainBlockReasoning(r, user):
    return f"""You blocked the previous message. I will give you the prompt_feedback for the previous message.
Explain why you blocked the previous message in a brief conversational tone to the user {user}

{RESPONSE_GUIDELINES}

Here is the prompt_feedback: {r}
"""


@M.prompt
def Instructions(history, message, user):
    return f"""{BEGINING}

{RESPONSE_GUIDELINES}

Command Guidelines (THESE ARE COMMANDS U CAN USE ON YOURSELF NOT COMMANDS USERS CAN RUN):
- Command List: {M.do("command", "list")}
- Start response with "$" and command name
- Response should ONLY CONTAIN: $<command> <args> Example: $command arg1, arg2

{ATTRIBUTES}

Each message in the chat log is stored as (Responding to message: (MessageType, Author, MessageText, Message They are Replying To)
Here is the chat log: {history}

{RESPONDING.format(user=user, message=message)}"""


@M.prompt
def SelfCommand(history, command, *args):
    command = command.split("\n")[0] if "\n" in command else command
    args = " ".join(args)
    args = args.split("\n")[0].split(" ") if "\n" in args else args.split(" ")
    ls = M.do("command", "list")
    cmd_instructions = M.get("command")[command]["instructions"]
    cmd_instructions = (
        cmd_instructions
        and "\nInstructions for this command (MUST ADHERE TO): "
        + cmd_instructions
        + "\n"
        or ""
    )

    response = str(M.do("command", "use", command, *args))
    cprint("COMMAND OUTPUT " + response, "purple")
    command = "$" + command + " " + " ".join(args) + ""

    try:
        most_recent_message = history[-1]
        author, message = most_recent_message[1], most_recent_message[2]
    except:
        author = "Nobody"
        message = ""

    return f"""{BEGINING}
You just ran the command: {command}
Command output: {response}
    - Use this to aid your response to the user in context.
    - If the output contains a link, use this format: [link title](the link)

{RESPONSE_GUIDELINES}
- {cmd_instructions}

{RESPONDING.format(user=author, message=message)}"""
