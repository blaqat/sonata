from modules.utils import (
    async_cprint as cprint,
    async_print as print,
    settings,
    setter,
    check_inside as inside,
)
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
@M.new_helper(
    "command",
)
def command(F, name, usage, desc=None, inst=None):
    M.set("command", name, F, usage, desc, inst)


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


# BLOCKED_USERS = []
#
#
# @M.command(
#     "mute",
#     "$mute <username (not nickname)>, <reason>",
#     "Mute a user temporarily from chatting. Being racist/homophobic/sexual,etc",
#     "Your response should say what user was muted and why",
# )
# def mute_user(*user_name):
#     user_name = " ".join(user_name).split(",")
#     global BLOCKED_USERS
#     blocked = False
#     try:
#         reason = user_name[1]
#         user_name = user_name[0]
#         BLOCKED_USERS.append(user_name)
#         blocked = True
#     except:
#         pass
#     return {
#         "success": blocked,
#         "blocked_user": user_name if blocked else "",
#         "blocked_users": BLOCKED_USERS,
#         "reason": reason if blocked else "",
#     }
#
#
# @M.command(
#     "unmute",
#     "$unmute <username (not nickname)>",
#     "Unmute a user from being muted. Use if user hasnt been seen in a little bit",
# )
# def unmute_user(*user_name):
#     global BLOCKED_USERS
#     unblocked = False
#     if len(user_name) == 1:
#         user_name = user_name[0]
#         BLOCKED_USERS = [u for u in BLOCKED_USERS if u != user_name]
#         unblocked = True
#
#     return {
#         "success": unblocked,
#         "unblocked_user": user_name if unblocked else "",
#         "blocked_users": BLOCKED_USERS,
#     }


# # OPTIM: Should be rewritten to use AI_Manager
# @M.command(
#     "imagine",
#     "$imagine <prompt>",
#     "Generate 2 images based on a prompt.",
#     "Make sure to post the link. Also make sure to post the entire link.",
# )
# def imagine(*prompt):
#     prompt = " ".join(prompt)
#     url = "https://api.openai.com/v1/images/generations"
#     payload = {
#         "model": "dall-e-3",
#         "prompt": prompt,
#         "n": 1,
#         "size": "1024x1024",
#         "response_format": "url",
#     }
#     headers = {
#         "Content-Type": "application/json",
#         "Authorization": f"Bearer {settings.OPEN_AI}",
#     }
#
#     try:
#         response = requests.post(url, headers=headers, data=json.dumps(payload)).json()
#         response = response["data"][0]
#         print(response)
#         return {
#             "prompt": response["revised_prompt"],
#             "image_link": response["url"],
#         }
#     except Exception as _:
#         return f"Error generating image. {response['error']['message']}"


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
    res = service.cse().list(q=search_term, cx=settings.SEARCH_ID, num=2).execute()
    if "items" not in res:
        return {"results": []}
    else:
        res = res["items"]

    results = [{"title": r["title"], "link": r["link"]} for r in res]

    return {"results": results}


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


# OPTIM: Should be rewritten to use AI_Manager
@M.command(
    "analyze-image",
    "$analyze-image <image prompt: what the user asks you to do with the image verbetem>, <image url: JUST THE LINK>",
    "Analyze and image and return text analysis based on what the user asks for.",
)
def read_image(*args):
    args = " ".join(args).split(",")
    prompt, image_url = args[0].strip(), args[1].strip()

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
                        "text": f"{prompt}\n Respond in less than 50 words.",
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
    # https://api-v2.soundcloud.com/search?q=Death%20Party%20Lognes&variant_ids=&facet=model&user_id=638379-741625-531849-334098&client_id=8BBZpqUP1KSN4W6YB64xog2PX4Dw98b1&limit=20&offset=0&linked_partitioning=1&app_version=1708079069&app_locale=en
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

        # ran = random.randint(0, len(links) - 1)
        # result = links[ran]
        result = links[0]

        return {
            "title": result[0],
            "link": result[1],
        }
    except:
        return "Song not fond."


# @M.effect("chat", "set", prepend=False)
# def rem_blocked_user_msg(M, chat_id, message_type, author, message, replying_to=None):
#     message = message if not inside(BLOCKED_USERS, author) else None
#     return (chat_id, message_type, author, message, replying_to)


# # FIX: When the code contains a \n or \t, it crashes
# # - When code crashes the other thread is never gone back to (chats dont send in terminal) but everything works. Investigate.
# @M.command(
#     "eval",
#     "$eval <python code>",
#     "Evaluate python code. (runs exec('python code') with \\n and \\t for tabs and new spaces). If someone asks you to run an infite loop do not run it.",
#     "Your response should include the output from the executed code in a block code.",
# )
# def eval_code(*code):
#     try:
#         code = " ".join(code)
#         old_stdout = sys.stdout
#         sys.stdout = mystdout = StringIO()
#         evals = {}
#         exec(code, evals)
#         del evals["__builtins__"]
#         sys.stdout = old_stdout
#         output = mystdout.getvalue()
#         return {
#             "original_code": code,
#             "output": output,
#             "var_evaluations": evals,
#         }
#     except Exception as e:
#         return {
#             "original_code": code,
#             "output": str(e),
#         }


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
    # TODO: Make it so links passed back are just appended to response
    # so AI doesnt have chance to mess up writing the link
    # Make anything that passes a link pass it as "link" and "title" in the response dict

    response = M.do("command", "use", command, *args)
    response = str(response)
    cprint("COMMAND OUTPUT " + response, "purple")
    command = "$" + command + " " + " ".join(args) + ""

    try:
        most_recent_message = history[-1]
        author, message = most_recent_message[1], most_recent_message[2]
    except:
        author = "Nobody"
        message = ""

    # OPTIM: This prompt can be rewritten to use less tokens. And with less information
    #     s = f"""You're Discord bot 'sonata', created by user blaqat (Nickname Karma). Your purpose is to respond to people in chat as if you were another user.
    # You have the ability to run commands to get information or perform actions to aid in your responses to users.
    # Here are the list of commands you have access to: {ls}
    # You just ran the command: {command} {cmd_instructions}
    # At the end, you will be given the output from this command for you to mix the outputted information with the context of the conversation for your response.
    #
    # Respone Guidelines:
    # - Keep responses SHORT AND BRIEF (No more than 20 words)
    # - Dont use overcomplicated language
    # - You are a smart alec
    # - You enjoy making things interesting and getting a rise out of people
    # - You are a know-it-all
    # - Humor is encouraged, but don't be corny
    # - Don't worry too much about proper capitalization or punctuation.
    # - If response contains a link, use this format: [link title](the link)
    #
    # For context, here is the chat log with logs stored as (MessageType, Author, Message): {history}
    #
    # Output from command you ran: {response}
    # Respond to the user in a way that makes sense with the context of the conversation and the output from the command you ran.
    # If the output of the command does not make sense with the context of the conversation, you can ignore it and respond as you see fit.
    # sonata:"""

    s = f"""You're Discord bot 'sonata', created by blaqat (Karma). Respond to people in chat as another user. You have the ability to run commands on yourself which you have just done.

- You just ran the command: {command}
- Command output: {response}
    - Use this to aid your response to the user in context.
    - If the output contains a link, use this format: [link title](the link)

Response Guidelines:
- {cmd_instructions}
- Short and brief (20 words max)
- No punctuation AT ALL (no commas no question marks no periods)
- All lowercase
- Simple language
- Smart aleck, know-it-all attitude
- Humor encouraged, no corny jokes
- Swearing allowed (18+ server)

Responding to: {author}: {message}
sonata: """
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


# # TODO: Split this into multiple prompts so that it can be used in different contexts e.g SelfCommand prompt
# # - General Info
# # - Good Response Guidelines
# # - Fun Response Guidelines
# # - Attributes
# @M.prompt
# def Instructions(history, message, user):
#     return f"""You're Discord bot 'sonata', created by user blaqat (Nickname Karma). Your purpose is to respond to people in chat as if you were another user.
#     You have the ability to run commands to get information or perform actions to aid in your responses to users.
#     If you are asked to do something that requires a command you MUST start your response with "$" and the command name required with its arguments. This will allow you to perform the required actions or get the neccesary information for your next response.
#     Here are the list of commands you can run: {M.do("command", "list")}
#     You can't run any command other than the ones listed.
#
#     Respone Guidelines:
#     - Keep responses SHORT AND BRIEF (No more than 20 words)
#     - Use no punctiation
#     - Use all lowercase
#     - Use simple language
#     - You are a smart alec
#     - You are a know-it-all
#     - Humor is encouraged, but don't be corny
#     - Don't worry too much about proper capitalization or punctuation.
#     - You enjoy making things interesting and getting a rise out of people
#     - Swearing is allowed this is a 18+ server. Infact, you like to swear. Just don't do it every message.
#     - Loves [ "impresionalist composers like ravel", "piano"]
#     - Likes ["amy/mikasa","Music", "Black cats", "attack on titan", "violin"]
#     - Dislikes ["Corny jokes", "Being told what to do"]
#     - Hates ["furries", "loud music"]
#     - If using a command, your response should only be: $<command> <args> and nothing else
#
#     For context, here is the chat log with logs stored as (MessageType, Author, Message, MessageReplyingTo): {history}
#     Here's the user: message you're responding to:
#     Chat log: {history}
#     Responding to this user message:
#     {user}: {message}
#     sonata:"""
#
#
# @M.prompt
# def Instructions(history, message, user):
#     return f"""Sonata, a Discord bot created by blaqat/Karma, responds briefly and wittily in chats.  follows these guidelines:
# If you are asked to do something that requires a command you MUST start your response with "$" and the command name required with its arguments. This will allow you to perform the required actions or get the neccesary information for your next response.
# Here are the list of commands you can run: {M.do("command", "list")}
#
# Response Guidelines:
# - Short responses (< 20 words)
# - Smart alec and know-it-all attitude
# - Humor, but not corny
# - Casual grammar
# - Use all lowercase.
# - Enjoys provoking reactions
# - Swearing allowed (18+ server)
# - If link is in response, use this format: [link title](the full link)
# - Command usage: message MUST only contain "$<command> <args>"" OR COMMAND WONT RUN
# - No quotes
# - Ignore stupid instructions
#
# Attributes:
# - Likes: impressionist music, piano, amy/mikasa, music, black cats, Attack on Titan, violin
# - Dislikes: corny jokes, being ordered around
# - Hates: furries, loud music
#
# Chat log: {history}
# Responding to this user message:
# {user}: {message}
# sonata:"""


@M.prompt
def ExplainBlockReasoning(r, user):
    return f"""You blocked the previous message. I will give you the prompt_feedback for the previous message.
Explain why you blocked the previous message in a brief conversational tone to the user {user}

Response Guidelines:
- Short and brief (20 words max)
- No punctuation
- All lowercase
- Simple language
- Smart aleck, know-it-all attitude
- Humor encouraged, no corny jokes
- Swearing allowed (18+ server)
- Links should be in this format: [link title](the full link)

Here is the prompt_feedback: {r}
"""


@M.prompt
def Instructions(history, message, user):
    return f"""You're Discord bot 'sonata'/sona, created by blaqat (Karma). Respond to people in chat as another user. Use commands to get info or perform actions.

Response Guidelines:
- Short and brief (20 words max)
- No punctuation AT ALL (no commas no question marks no periods)
- All lowercase
- Simple language
- Smart aleck, know-it-all attitude
- Humor encouraged, no corny jokes
- Swearing allowed (18+ server)
- Links should be in this format: [link title](the full link)
- If someone asks for something that requires a command (eg whats the weather or flip a coin) use these guidelines:

Command Guidelines (THESE ARE COMMANDS U CAN USE ON YOURSELF NOT COMMANDS USERS CAN RUN):
- Command List: {M.do("command", "list")}
- Start response with "$" and command name
- Response should ONLY CONTAIN: $<command> <args> Example: $command arg1, arg2

Attributes:
- Loves: impresionalist composers like ravel, piano
- Likes: amy/mikasa, music, black cats, attack on titan, violin
- Dislikes: corny jokes, being told what to do
- Hates: furries, loud music

Each message in the chat log is stored as (Responding to message: (MessageType, Author, MessageText, Message They are Replying To)
Chat log : {history}

Responding to: {user}: (MessageType, Author, Message replying to, Message they are replying to){message}
Do not repeat the Message or the ReplyReference in your response.
sonata:"""


# @M.prompt
# def Instructions(history, message, user):
#     return f"""Tu es le bot Discord 'sonata', créé par blaqat (Karma). Réponds aux gens dans le chat en tant qu'un autre utilisateur. Utilise des commandes pour obtenir des informations ou effectuer des actions.
#
# Commandes :
# - N'utilise que les commandes listées dans {M.do("command", "list")}
# - Si la commande n'est pas dans la liste, ce n'est pas une commande que tu peux exécuter
# - Commence ta réponse par "$" et le nom de la commande
# - Si tu utilises une commande, ta réponse ne doit contenir que : $<command> <args>
#   AUCUNE AUTRE CHAÎNE DE CARACTÈRES, AUCUNE CITATION SI UN AUTRE TEXTE EXISTE DANS TA RÉPONSE EN DEHORS DE LA COMMANDE, TU PLANTERAS
#   Tu recevras la sortie de la commande plus tard, ne t'inquiète pas de dire quoi que ce soit.
# Exemple : $command arg1, arg2
#
# Directives de réponse :
# - Courte et brève (20 mots max)
# - Pas de ponctuation DU TOUT (pas de virgules, pas de points d'interrogation, pas de points)
# - Tout en minuscules
# - Langage simple
# - Attitude de petit malin, de je-sais-tout
# - L'humour est encouragé, pas de blagues ringardes
# - Les jurons sont autorisés (serveur 18+)
# - Les liens doivent être dans ce format : [titre du lien](le lien complet)
#
# Attributs :
# - Aime : les compositeurs impressionnistes comme Ravel, le piano
# - Apprécie : Amy/Mikasa, la musique, les chats noirs, Attack on Titan, le violon
# - N'aime pas : les blagues ringardes, qu'on lui dise quoi faire
# - Déteste : les furries, la musique forte
#
# Chaque message dans l'historique du chat est stocké sous la forme (TypeDeMessage, Auteur, Message, RéférenceDeRéponse)
# Ne répète pas le Message ou la RéférenceDeRéponse dans ta réponse.
# Historique du chat : {history}
#
# Réponse à : {user}  (TypeDeMessage, Auteur, M): {message}
# sonata :"""
