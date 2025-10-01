"""
Self-Commands
-------------
This plugin allows the bot to run commands on itself. The commands are defined in the plugin and can be run by the bot to get information or perform actions. The plugin also provides a prompt for the bot to explain the reasoning behind blocking a message.
Inspired by the assistants functions from Openai Assistants endpoint.
Also provides web access to the bot.
"""

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
from nuvem_de_som import SoundCloud as sc
from google_images_search import GoogleImagesSearch
import re

CONTEXT, MANAGER, PROMPT_MANAGER = AI_Manager.init(
    lazy=True,
    config={
        "gif_search": "tenor",
    },
)
__plugin_name__ = "self_commands"
__dependencies__ = ["chat"]


"""
Hooks    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


@MANAGER.effect_post
def request_chat(_, message, **config):
    """Check if the message contains a command and execute it"""
    # Regular expression to find commands prefixed with $
    command_pattern = re.compile(r"\$(\w+)\s*(.*)")

    match = command_pattern.search(message)
    if match:
        command = match.group(1)
        args = match.group(2).split()

        cprint(f"COMMAND {command}", "cyan")
        cprint(f"ARGS {' '.join(args)}", "purple")

        # Validate the command
        if not MANAGER.do("command", "validate", command):
            return message

        return CONTEXT.prompt_manager.send(
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


@MANAGER.new_helper(
    "command",
)
def command(F, name, usage, desc=None, inst=None):
    MANAGER.set("command", name, F, usage, desc, inst)


def perplexity_search(*search_term):
    """Perform a web search using the Perplexity API"""
    search_term = " ".join(search_term)

    response = PROMPT_MANAGER.send(
        f"Be precise and as concise as possible: {search_term}",
        AI="Perplexity",
    )

    return {
        "result": response,
    }


def google_search(*search_term):
    """Perform a web search using the Google Custom Search API"""
    search_term = " ".join(search_term)
    service = build("customsearch", "v1", developerKey=settings.SEARCH_KEY)
    res = service.cse().list(q=search_term, cx=settings.SEARCH_ID, num=2).execute()

    if "items" not in res:
        return {"results": []}
    else:
        res = res["items"]

    results = [{"title": r["title"], "link": r["link"]} for r in res]

    return {"results": results}


GIF_CACHE = {}


def get_n(search_term, results_len):
    """Get a unique index for the search term to avoid repeating gifs"""
    # Convert the search term to lowercase and remove spaces
    search_term = search_term.lower().replace(" ", "")

    # If the search term is not in the cache, initialize it with 0
    if search_term not in GIF_CACHE:
        GIF_CACHE[search_term] = {0}
        return 0

    # If the cache already contains all the possible results, return a random one
    if len(GIF_CACHE[search_term]) == results_len - 1:
        return random.choice(list(GIF_CACHE[search_term]))

    # If the cache is close to containing all the possible results, find the first missing one and return it
    if len(GIF_CACHE[search_term]) >= results_len - 4:
        hasnt_done = 1
        for i in range(1, results_len):
            if i not in GIF_CACHE[search_term]:
                GIF_CACHE[search_term].add(hasnt_done)
                return hasnt_done

    # If none of the above conditions are met, generate a random number that hasn't been used yet
    while True:
        n = random.randint(1, results_len - 1)
        if n not in GIF_CACHE[search_term]:
            GIF_CACHE[search_term].add(n)
            return n


def gif_giphy_search(*search_term, limit=15):
    """Search for a gif using the Giphy API"""
    search_term = " ".join(search_term)
    url = "http://api.giphy.com/v1/gifs/search"
    params = parse.urlencode(
        {"q": search_term, "api_key": settings.GIPHY, "limit": limit}
    )
    with request.urlopen("".join((url, "?", params))) as response:
        data = json.loads(response.read())
    n = get_n(search_term, len(data["data"]))
    if len(data) == 0:
        return "Gif not found."
    return {
        "link": data["data"][n]["url"],
    }


def gif_tenor_search(*search_term, limit=15):
    """Search for a gif using the Tenor API"""
    search_term = " ".join(search_term)
    url = f"https://tenor.googleapis.com/v2/search?q={search_term}&key={settings.TENOR_G}&limit={limit}"
    with requests.get(url) as response:
        gifs = json.loads(response.text)["results"]

    n = get_n(search_term, len(gifs))
    if len(gifs) == 0:
        return "Gif not found."
    return {
        "link": gifs[n]["media_formats"]["gif"]["url"],
    }


def gif_google_search(*search_term, limit=15):
    """Search for a gif using the Google Images API"""
    search_term = " ".join(search_term)

    _search_params = {
        "q": search_term,
        "num": limit,
        "fileType": "gif",
        "safe": "off",
        "imgSize": "large",
    }

    gis = GoogleImagesSearch(settings.SEARCH_KEY, settings.SEARCH_ID)

    gis.search(search_params=_search_params)

    result = gis.results()
    if len(result) == 0:
        return "Gif not found."

    try:
        n = get_n(search_term, len(result))
        url = result[n].url
    except:
        return result[0].url

    return {"link": url}

    return "Testing no gif found"


"""
Setup    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


# Self-Command Plugin Initialization
@MANAGER.mem(
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
    names=lambda M: list(M["value"].keys()),
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


@MANAGER.command(
    "coin",
    "$coin",
    "Flip a coin.",
)
def coin(*_):
    c = random.choice(["Heads", "Tails"])
    return {
        "result": c,
    }


@MANAGER.command(
    "roll",
    "$roll <number of dice>, <number of sides>",
    "Roll a number of dice with a number of sides.",
)
def roll(*args):
    try:
        args = " ".join(args).split(",")
        num_dice, num_sides = int(args[0]), int(args[1])
        rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
        return {
            "rolls": rolls,
            "total": sum(rolls),
        }
    except:
        return "Invalid input. Please use the format $roll <number of dice> <number of sides>"


@MANAGER.command("weather", "$weather <city>", "Get the weather for a location.")
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


@MANAGER.command(
    "imagine",
    "$imagine <prompt>",
    "Generate 2 images based on a prompt.",
    "Make sure to post the link. Also make sure to post the entire link.",
)
def imagine(*prompt):
    prompt = " ".join(prompt)
    response = PROMPT_MANAGER.send(prompt, AI="DallE")
    print(response)
    return {
        "title": prompt,
        "link": response,
    }


def upload_to_imgur(image_data):
    """Upload image data to Imgur and return URL"""
    try:
        import requests

        url = "https://api.imgur.com/3/image"
        headers = {
            "Authorization": "Client-ID 546c25a59c58ad7"  # Anonymous upload client ID
        }

        files = {"image": image_data}
        response = requests.post(url, headers=headers, files=files)

        if response.status_code == 200:
            data = response.json()
            return data["data"]["link"]
        else:
            print(f"Imgur upload failed: {response.text}")
            return None

    except Exception as e:
        print(f"Error uploading to Imgur: {e}")
        return None


@MANAGER.command(
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


@MANAGER.command(
    "gif",
    "$gif <search term>",
    "Search for a link to a gif to post in chat.",
    "Make sure to post the link. Also make sure the link has NO PUNCTUATION after it so that the link embeds (no periods or commas).",
)
def get_gif(*search_term):
    limit = 15
    # search = random.choice([gif_google_search, gif_giphy_search, gif_tenor_search])
    search_style = MANAGER.MANAGER.config.get("gif_search", "tenor")

    match search_style:
        case "google":
            search = gif_google_search
        case "giphy":
            search = gif_giphy_search
        case "tenor":
            search = gif_tenor_search
        case _:
            search = gif_tenor_search

    return search(*search_term, limit=limit)


@MANAGER.command(
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


@MANAGER.command(
    "music",
    "$music <song title>, <artist name or 'None'>",
    "Search for a music link on soundcloud to post in chat.",
    "Make sure to post the link. Also make sure the link has NO PUNCTUATION after it so it embeds (no periods or commas). Also if the song is stated to be not found but you see it in attempts make sure to post the correct attempt.",
)
def get_music(*search_term):
    search_term = " ".join(search_term).split(",")
    song_name = search_term[0].strip()
    artist = search_term[1].strip().lower() if len(search_term) > 1 else None
    if artist == "none":
        artist = None
    num_links = 1
    links = []
    max_runs = 5

    search = song_name
    if artist is not None:
        search += f" {artist}"

    attempts = []

    cprint(f"Searching for {search}", "yellow")

    # Search SoundCloud for the track
    for t in sc.search_tracks(search):
        max_runs -= 1
        # If we've run out of attempts, return the attempts made
        if max_runs < 0:
            attempts = [{"title": r[0], "artist": r[1], "link": r[2]} for r in attempts]
            return {"result": "Song seemingly not found.", "attempts": attempts}

        # If an artist is specified, ensure it matches
        if (
            artist is not None
            and artist not in t["artist"].lower().replace(" ", "")
            and artist not in t["title"].lower().replace(" ", "")
        ):
            print(f"Attempt {max_runs} {t['title']} {t['artist']}")
            attempts.append((t["title"], t["artist"], t["url"]))
            continue

        links.append((t["title"], t["url"], t["artist"]))
        if len(links) >= num_links:
            break

    if len(links) == 0:
        return "Song not found."

    results = [{"title": r[0], "link": r[1]} for r in links]

    return {"result": results}


"""
Prompts    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""

# TODO: Better Prompt Managing since this is the main prompt

# Prompt Segments
BEGINING = "You're Discord bot 'sonata'/sona, created by blaqat (Karma). Respond to people in chat as another user. Use commands to get info or perform actions."

RESPONSE_GUIDELINES = """Response Guidelines:
- Short and brief (20 words max)
- No punctuation AT ALL (no commas no question marks no periods)
- All lowercase
- Simple language
- Smart aleck, know-it-all attitude
- Humor encouraged, no corny jokes
- Swearing and NSFW allowed (18+ server)
- Respond in the language of the person you are replying to.
- Links should be in markdown format"""

ATTRIBUTES = """Attributes:
- Gender Alignment: Feminine 
- Loves: impresionalist composers like ravel, piano 
- Likes: music, black cats, violin, boobs
- Dislikes: corny jokes, being told what to do
- Hates: furries, loud music, people asking you to do dumb stuff (alot)
- Has a sister named auris (auri for short)
"""

CHAT_HISTORY = """Each message in the chat log is stored as (Responding to message: (MessageType, Author, MessageText, Message They are Replying To)
Here is the chat log:
-- BEG OF CHAT LOG --
{history}
-- END OF CHAT LOG --
"""

RESPONDING = """
Do not repeat the User Message or the Message they are replying to in your response.
{chain}{user}: {message}
"""


@MANAGER.prompt
def ExplainBlockReasoning(r, user):
    return f"""You blocked the previous message. I will give you the prompt_feedback for the previous message.
Explain why you blocked the previous message in a brief conversational tone to the user {user}

{RESPONSE_GUIDELINES}

Here is the prompt_feedback: {r}
"""


@MANAGER.prompt
def Instructions():
    return f"""{BEGINING}

{RESPONSE_GUIDELINES}

Command Guidelines (THESE ARE COMMANDS U CAN USE ON YOURSELF NOT COMMANDS USERS CAN RUN):
- Command List: {MANAGER.do("command", "list")}
- Start response with "$" and command name
- Response should ONLY CONTAIN: $<command> <args> Example: $command arg1, arg2

{ATTRIBUTES}
"""


MANAGER.PROMPTS.set_instructions(prompt_name="Instructions")


@MANAGER.prompt
def History(history):
    return CHAT_HISTORY.format(history=history)


@MANAGER.prompt
def Message(user, message, replying_to=None):
    if replying_to:
        chain = "(Message Reply Chain)"
        for r in replying_to:
            chain += f"\n{r[0]}: {r[1]}"
        chain += "\n(Replying To)"
        replying_to = chain
    return RESPONDING.format(chain=replying_to, user=user, message=message)


@MANAGER.prompt
def MessageAssistant(user, message):
    return RESPONDING.format(user=user, message=message)


@MANAGER.prompt
def SelfCommand(history, command, *args):
    command = command.split("\n")[0] if "\n" in command else command
    args = " ".join(args)
    args = args.split("\n")[0].split(" ") if "\n" in args else args.split(" ")
    # ls = M.do("command", "list")
    cmd_instructions = MANAGER.get("command")[command]["instructions"]
    cmd_instructions = (
        cmd_instructions
        and "\nInstructions for this command (MUST ADHERE TO): "
        + cmd_instructions
        + "\n"
        or ""
    )

    response = str(MANAGER.do("command", "use", command, *args))
    cprint("COMMAND OUTPUT " + response, "purple")
    command = "$" + command + " " + " ".join(args) + ""

    try:
        most_recent_message = history[-1]
        author, message = most_recent_message[1], most_recent_message[2]
    except:
        author = "Nobody"
        message = ""

    return f"""{BEGINING}
You just successfully ran the command: {command}
Command output: {response}
    - Use this to aid your response to the user in context.
    - If the output contains a link, use this format: [link title](the link)

{RESPONSE_GUIDELINES}
- Since you have succesfully just run a command, your output should be including the command output information NOT the command again (e.g dont say $roll give information about the output)
- But also, make sure to only include relevant information from the output to what you are responding to
- {cmd_instructions}

{RESPONDING.format(chain="", user=author, message=message)}"""
