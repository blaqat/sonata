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
from typing import Dict, Any, List, Optional
import json


CONTEXT, MANAGER, PROMPT_MANAGER = AI_Manager.init(
    lazy=True,
    config={
        "gif_search": "tenor",
        "agent_model": "Claude",
        "agent": True,
        "agent_retries": 3,
        "agent_max_steps": 5,
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


# def google_search(*search_term):
#     """Perform a web search using the Google Custom Search API"""
#     search_term = " ".join(search_term)
#     service = build("customsearch", "v1", developerKey=settings.SEARCH_KEY)
#     res = service.cse().list(q=search_term, cx=settings.SEARCH_ID, num=2).execute()

#     if "items" not in res:
#         return {"results": []}
#     else:
#         res = res["items"]

#     results = [{"title": r["title"], "link": r["link"]} for r in res]

#     return {"results": results}
#

def perplexity_search(*search_term: str) -> Dict[str, Any]:
    """
    Perform a web search using Perplexity AI.
    Returns structured data for agent consumption.
    """
    query = " ".join(search_term).strip()

    if not query:
        return {
            "result": [],
            "attempts": [],
            "status": "error",
            "message": "❌ Search query cannot be empty"
        }

    system_prompt = f"""You are a precise research assistant.
    Provide factual, concise answers. If you find relevant sources,
    include them as markdown links [title](url).
    Research this query and provide a concise answer with sources if available: {query}
    """

    try:
        response = PROMPT_MANAGER.send(
            system_prompt,
            AI="Perplexity",
        )

        # Fallback to raw response
        return {
            "result": response,
            "sources": [],
            "status": "found",
            "message": "✅ Perplexity search completed"
        }

    except Exception as e:
        cprint(f"❌ Perplexity API error: {e}", "red")
        return {
            "result": [],
            "attempts": [],
            "status": "error",
            "message": f"❌ Perplexity failed: {str(e)}"
        }

def google_search(*search_term: str) -> Dict[str, Any]:
    """
    Perform a web search using Google Custom Search API.
    Returns consistent structure with status.
    """
    query = " ".join(search_term).strip()

    if not query:
        return {
            "result": [],
            "attempts": [],
            "status": "error",
            "message": "❌ Search query cannot be empty"
        }

    config = MANAGER.MANAGER.config.get("search", {})
    num_results = config.get("num_results", 2)

    try:
        service = build("customsearch", "v1", developerKey=settings.SEARCH_KEY)
        res = service.cse().list(
            q=query,
            cx=settings.SEARCH_ID,
            num=num_results
        ).execute()

        if "items" not in res or not res["items"]:
            return {
                "result": [],
                "attempts": [],
                "status": "not_found",
                "message": "❌ No results from Google"
            }

        results = [
            {
                "title": item.get("title", "No title").strip(),
                "link": item.get("link", "").strip()
            }
            for item in res["items"]
        ]

        return {
            "result": results,
            "attempts": [],
            "status": "found",
            "message": f"✅ Found {len(results)} result(s)"
        }

    except Exception as e:
        cprint(f"❌ Google API error: {e}", "red")
        return {
            "result": [],
            "attempts": [],
            "status": "error",
            "message": f"❌ Google search failed: {str(e)}"
        }

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
    names=lambda M: list(M["value"].keys()),
    str=lambda M, command, cobj=None: f"{command} - {(cobj or M['value'][command])['usage']} - {(cobj or M['value'][command])['desc']}",
    list=lambda M: "; ".join(
        M["str"](M, k, c) for k, c in M["value"].items()
    )
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

    required_keys = ["location", "current"]
    if not all(key in data for key in required_keys):
        return {
            "result": [],
            "status": "not_found",
            "message": f"❌ Weather data not found for '{city}'"
        }

    location_data = data["location"]
    current_data = data["current"]

    # Build result with fallbacks for missing data
    weather_result = {
        "location": f"{location_data.get('name', 'Unknown')}, {location_data.get('region', '')}, {location_data.get('country', '')}".strip(', '),
        "temp": current_data.get("temp_f"),
        "temp_c": current_data.get("temp_c"),
        "desc": current_data.get("condition", {}).get("text", "Unknown"),
        "humidity": current_data.get("humidity"),
        "feels_like": current_data.get("feelslike_f"),
        "wind_mph": current_data.get("wind_mph"),
        "last_updated": current_data.get("last_updated")
    }

    # Remove None values
    weather_result = {k: v for k, v in weather_result.items() if v is not None}

    temp_display = f"{weather_result.get('temp', '?')}°F"
    if weather_result.get('temp_c'):
        temp_display += f" ({weather_result['temp_c']}°C)"

    return {
        "result": [weather_result],  # Wrap in list for consistency
        "status": "found",
        "message": f"{weather_result['location']}: {temp_display}, {weather_result['desc']}"
      }
    # return {
    #     "location": f"{data['location']['name']}, {data['location']['region']}, {data['location']['country']}",
    #     "temperature": data["current"]["temp_f"],
    #     "description": data["current"]["condition"]["text"],
    # }


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


# @MANAGER.command(
#     "search",
#     "$search <search term>",
#     "Web Search for something you do not know about or recent news.",
#     "Make sure to post the most relavant link or extra_info. Also make sure to post the entire link.",
# )
# def combined_search(*search_term):
#     google = google_search(*search_term)
#     pplx = perplexity_search(*search_term)
#     return {
#         "results": google["results"],
#         "extra_info": pplx["result"],
#     }
#

@MANAGER.command(
    "search",
    "$search <search term>",
    "Web Search for something you do not know about or recent news.",
    "Make sure to post the most relevant link or extra_info. Also make sure to post the entire link.",
)
def combined_search(*search_term: str) -> Dict[str, Any]:
    """
    Combined search: Google for links + Perplexity for context.
    Handles partial failures gracefully.
    """
    query = " ".join(search_term).strip()

    if not query:
        return {
            "result": [],
            "attempts": [],
            "status": "error",
            "message": "❌ Search query cannot be empty"
        }

    # Execute searches concurrently (if your framework supports it)
    # For now, sequential with error isolation
    google_data = google_search(*search_term)
    pplx_data = perplexity_search(*search_term)

    # Handle partial failures
    if google_data["status"] == "error" and pplx_data["status"] == "error":
        return {
            "result": [],
            "attempts": [],
            "status": "error",
            "message": "❌ Both searches failed"
        }

    # Combine results intelligently
    result = {
        "result": google_data["result"],  # Primary: Google links
        "attempts": [],  # Alternatives from both sources
        "status": "found",
        "message": ""
    }

    # Add Perplexity answer as supplementary info
    if pplx_data["status"] == "found":
        result["extra_info"] = pplx_data["result"]
        result["sources"] = pplx_data.get("sources", [])
        result["message"] += "📊 Perplexity: Success. "

    if google_data["status"] == "found":
        result["message"] += f"🔍 Google: {len(google_data['result'])} result(s)."
    elif google_data["status"] == "not_found":
        result["message"] += "🔍 Google: No results."

    # Add alternatives from Perplexity if Google failed
    if google_data["status"] != "found" and pplx_data.get("sources"):
        result["attempts"] = pplx_data["sources"]

    return result

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


# @MANAGER.command(
#     "video",
#     "$video <search term>",
#     "Search for a video to post in chat.",
#     "Make sure to post the link. Also make sure the link has NO PUNCTUATION after it so it embeds (no periods or commas)",
# )
# def get_vid(*search_term):
#     search_term = " ".join(search_term)
#     videosSearch = VideosSearch(search_term, limit=1)
#     try:
#         result = videosSearch.result()["result"][0]
#         return {
#             "title": result["title"],
#             "link": result["link"],
#         }
#     except:
#         return "Video not found."
#
#

from typing import Dict, Any, List
import shlex

@MANAGER.command(
    "video",
    "$video <search term>",
    "Search for a video to post in chat.",
    "Make sure to post the link. Also make sure the link has NO PUNCTUATION after it so it embeds (no periods or commas)",
)
def get_vid(*search_term: str) -> Dict[str, Any]:
    """
    Search for a video (YouTube via VideosSearch).

    Returns consistent dict:
    - "result": List of videos [{"title": "...", "link": "..."}]
    - "attempts": List of alternatives (empty if none)
    - "status": "found" | "not_found" | "error"
    - "message": Human-readable status
    """
    # Configuration
    config = MANAGER.MANAGER.config.get("video", {})
    limit = config.get("limit", 1)
    max_results = config.get("max_results", 5)

    query = " ".join(search_term).strip()

    if not query:
        return {
            "result": [], "attempts": [], "status": "error",
            "message": "❌ Search term cannot be empty"
        }

    cprint(f"🔍 Searching video: '{query}'", "yellow")

    try:
        videos_search = VideosSearch(query, limit=max_results)
        search_result = videos_search.result()

        # Validate API response
        if not isinstance(search_result, dict) or "result" not in search_result:
            raise ValueError("Invalid API response structure")

        results = search_result["result"]

        if not results:
            return {
                "result": [], "attempts": [], "status": "not_found",
                "message": "❌ No videos found"
            }

        # Format results with link sanitization
        def sanitize_link(url: str) -> str:
            return url.rstrip('.,;:!?')  # Remove trailing punctuation for embed

        primary = [
            {
                "title": v.get("title", "Untitled").strip(),
                "link": sanitize_link(v.get("link", ""))
            }
            for v in results[:limit]
        ]

        alternatives = [
            {
                "title": v.get("title", "Untitled").strip(),
                "link": sanitize_link(v.get("link", ""))
            }
            for v in results[limit:]
        ]

        status_msg = f"🎬 Found {len(primary)} video(s)"
        if alternatives:
            status_msg += f" ({len(alternatives)} alternatives)"

        return {
            "result": primary,
            "attempts": alternatives,
            "status": "found",
            "message": status_msg
        }

    except (IndexError, KeyError) as e:
        cprint(f"❌ No results: {e}", "red")
        return {
            "result": [], "attempts": [], "status": "not_found",
            "message": "❌ Video not found"
        }
    except Exception as e:
        cprint(f"❌ API error: {e}", "red")
        return {
            "result": [], "attempts": [], "status": "error",
            "message": f"❌ Search failed: {str(e)}"
        }

# @MANAGER.command(
#     "music",
#     "$music <song title>, <artist name or 'None'>",
#     "Search for a music link on soundcloud to post in chat.",
#     "Make sure to post the link. Also make sure the link has NO PUNCTUATION after it so it embeds (no periods or commas). Also if the song is stated to be not found but you see it in attempts make sure to post the correct attempt.",
# )
# def get_music(*search_term):
#     search_term = " ".join(search_term).split(",")
#     song_name = search_term[0].strip()
#     artist = search_term[1].strip().lower() if len(search_term) > 1 else None
#     if artist == "none":
#         artist = None
#     num_links = 1
#     links = []
#     max_runs = 5

#     search = song_name
#     if artist is not None:
#         search += f" {artist}"

#     attempts = []

#     cprint(f"Searching for {search}", "yellow")

#     # Search SoundCloud for the track
#     for t in sc.search_tracks(search):
#         max_runs -= 1
#         # If we've run out of attempts, return the attempts made
#         if max_runs < 0:
#             attempts = [{"title": r[0], "artist": r[1], "link": r[2]} for r in attempts]
#             return {"result": "Song seemingly not found.", "attempts": attempts}

#         # If an artist is specified, ensure it matches
#         if (
#             artist is not None
#             and artist not in t["artist"].lower().replace(" ", "")
#             and artist not in t["title"].lower().replace(" ", "")
#         ):
#             print(f"Attempt {max_runs} {t['title']} {t['artist']}")
#             attempts.append((t["title"], t["artist"], t["url"]))
#             continue

#         links.append((t["title"], t["url"], t["artist"]))
#         if len(links) >= num_links:
#             break

#     if len(links) == 0:
#         return "Song not found."

#     results = [{"title": r[0], "link": r[1]} for r in links]

#     return {"result": results}

import shlex
from typing import List, Dict, Any, Optional

@MANAGER.command(
    "music",
    "$music <song title>, <artist name or 'None'>",
    "Search for a music link on soundcloud to post in chat.",
    "Make sure to post the link. Also make sure the link has NO PUNCTUATION after it so it embeds (no periods or commas). Also if the song is stated to be not found but you see it in attempts make sure to post the correct attempt.",
)
def get_music(*search_term: str) -> Dict[str, Any]:
    """
    Search for a song on SoundCloud.

    Returns consistent dict with keys:
    - "result": List of matched tracks [{"title": "...", "link": "..."}]
    - "attempts": List of alternatives [{"title": "...", "artist": "...", "link": "..."}]
    - "status": "found" | "not_found" | "error"
    - "message": Human-readable status
    """
    # Configuration
    config = MANAGER.MANAGER.config.get("music", {})
    num_links = config.get("num_links", 1)
    max_tracks_to_check = config.get("max_tracks_to_check", 10)

    # Robust argument parsing
    try:
        full_query = " ".join(search_term)
        if ',' not in full_query:
            return {
                "result": [], "attempts": [], "status": "error",
                "message": "❌ Invalid format. Use: $music <song>, <artist or 'None'>"
            }

        song_part, artist_part = full_query.split(',', 1)
        song_name = song_part.strip() or ''
        artist = artist_part.strip()

        # Handle 'None' artist (case-insensitive)
        if artist.lower() == "none" or not artist:
            artist = None

    except Exception as e:
        cprint(f"Argument parsing error: {e}", "red")
        return {
            "result": [], "attempts": [], "status": "error",
            "message": f"❌ Failed to parse: {e}"
        }

    cprint(f"🔍 Searching for '{song_name}' by {artist or 'any artist'}", "yellow")

    search_query = f"{song_name} {artist}" if artist else song_name
    matches: List[Dict[str, str]] = []
    alternatives: List[Dict[str, str]] = []

    try:
        tracks_checked = 0

        for track in sc.search_tracks(search_query):
            tracks_checked += 1

            if tracks_checked > max_tracks_to_check:
                cprint(f"⏹️ Hit scan limit ({max_tracks_to_check})", "yellow")
                break

            track_title = track.get("title", "").strip()
            track_artist = track.get("artist", "").strip()
            track_url = track.get("url", "").strip()

            if not track_url:
                continue

            # Artist matching
            if artist:
                search_artist_norm = artist.lower().replace(" ", "")
                track_artist_norm = track_artist.lower().replace(" ", "")
                track_title_norm = track_title.lower().replace(" ", "")

                is_match = (
                    search_artist_norm in track_artist_norm or
                    search_artist_norm in track_title_norm
                )

                if is_match:
                    matches.append({
                        "title": f"{track_title} - {track_artist}",
                        "link": track_url
                    })
                    cprint(f"✅ Match: {track_title} by {track_artist}", "green")
                else:
                    # Store non-matches as alternatives
                    alternatives.append({
                        "title": track_title,
                        "artist": track_artist,
                        "link": track_url
                    })
                    cprint(f"💡 Alternative: {track_title} by {track_artist}", "yellow")
            else:
                matches.append({
                    "title": f"{track_title} - {track_artist}",
                    "link": track_url
                })
                cprint(f"✅ Found: {track_title} by {track_artist}", "green")

            if len(matches) >= num_links:
                break

        # Consistent return structure
        if matches:
            return {
                "result": matches,
                "attempts": alternatives,
                "status": "found",
                "message": f"🎵 Found {len(matches)} track(s)"
            }
        elif alternatives:
            return {
                "result": [],
                "attempts": alternatives,
                "status": "not_found",
                "message": f"🤔 No exact match. {len(alternatives)} alternative(s)."
            }
        else:
            return {
                "result": [],
                "attempts": [],
                "status": "not_found",
                "message": "❌ No tracks found."
            }

    except Exception as e:
        cprint(f"❌ API error: {e}", "red")
        return {
            "result": [], "attempts": [], "status": "error",
            "message": f"API error: {str(e)}"
        }

"""
AGENT MODE -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""

@MANAGER.mem(
    {},
    s=lambda M, key, value: setter(M["value"], key, value),
    get=lambda M, key: M["value"].get(key),
)
def clear_state(M):
    """Memory for storing agent execution state"""
    return M["value"].clear()


@MANAGER.command(
    "agent",
    "$agent <goal>",
    "Starts an autonomous agent to achieve the specified goal. Agent mode has many commands such as flip coin search web etc.",
    "Write the goal in an ordered list format with steps to be executed sequentially"
)
def plan_and_execute(*args):
    try:
      model = MANAGER.MANAGER.config.get("agent_model", "Claude")
      goal = " ".join(args)

      # Get available commands
      command_list = MANAGER.do("command", "list")

      # Clear previous state for a new plan
      MANAGER.do("state", "clear")

      # Initialize the agent state
      MANAGER.set("state", "goal", goal)
      MANAGER.set("state", "current_step", 0)
      MANAGER.set("state", "completed_steps", [])
      MANAGER.set("state", "results", [])

      # Start the chain of thought loop
      return agent_loop(model, command_list)
    except Exception as e:
      MANAGER.do("state", "clear")
      raise e


def agent_loop(model, command_list):
    """Execute the agent loop until the goal is achieved or max steps is reached"""
    max_steps = MANAGER.MANAGER.config.get("agent_max_steps", 5)

    for _ in range(max_steps):
        current_state = MANAGER.get("state")
        goal = current_state["goal"]
        current_step = current_state["current_step"]
        completed_steps = current_state["completed_steps"]
        results = current_state["results"]

        # Create a prompt for the AI to determine the next action
        prompt = f"""You are an AI assistant trying to achieve this goal: {goal}

Available commands:
{command_list}

You have completed {current_step} steps so far.
Previous steps: {completed_steps}

Previous results:
{format_results(results)}

What should you do next? Respond with a JSON object containing:
- "action": either "DONE" if you have achieved the goal or "COMMAND" to execute a command
- "command": the command name (only if action is "COMMAND")
- "args": a string of arguments for the command (only if action is "COMMAND")

Examples:
{{"action": "DONE"}}
{{"action": "COMMAND", "command": "roll", "args": "1, 50"}}
{{"action": "COMMAND", "command": "weather", "args": "New York"}}

IMPORTANT:
1. Analyze the previous results. If there were errors, adjust your approach.
2. Respond with ONLY the JSON object. No explanations, no additional text, no markdown formatting, no code blocks."""

        try:
            response = PROMPT_MANAGER.send(
                prompt,
                AI=model
            )

            cprint(f"AGENT RESPONSE: {response}", "green")

            # Parse the JSON response
            try:

                # Remove markdown code blocks if present
                clean_response = re.sub(r'```(?:json)?\s*', '', response).strip()
                clean_response = re.sub(r'\s*```', '', clean_response)

                action_data = json.loads(clean_response)
            except json.JSONDecodeError as e:
                cprint(f"Invalid JSON response: {response}", "red")
                cprint(f"JSON error: {e}", "red")
                continue

            # Check if the agent is done
            if action_data.get("action") == "DONE":
                # Format the final response
                final_results = format_final_results(results)

                return {
                    "results": final_results,
                    "combined": "\n".join(final_results),
                    "steps": completed_steps
                }

            # Parse the command
            if action_data.get("action") == "COMMAND":
                command = action_data.get("command", "").lstrip("$")  # Remove $ if present
                args_str = action_data.get("args", "")

                # Split the args string into a list
                cmd_args = args_str.split() if args_str else []

                # Validate the command
                if not MANAGER.do("command", "validate", command):
                    cprint(f"Invalid command: {command}", "red")
                    continue

                # Execute the command
                # result = MANAGER.do("command", "use", command, *cmd_args)

                max_retries = MANAGER.MANAGER.config.get("agent_retries", 3)
                for attempt in range(max_retries):
                    result = MANAGER.do("command", "use", command, *cmd_args)
                    if not isinstance(result, dict) or not result.get("error"):
                        break  # Success
                    cprint(f"Attempt {attempt + 1} failed: {result.get('error')}", "yellow")
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    cprint(f"Command failed after {max_retries} attempts", "red")
                    continue

                # Update the agent state
                completed_steps.append(f"{command} {args_str}")
                results.append(result)
                # MANAGER.set("state", "completed_steps", completed_steps)
                # MANAGER.set("state", "results", results)
                MANAGER.set("state", "current_step", current_step + 1)
                # MANAGER.set("state", "completed_steps", completed_steps + [f"{command} {args_str}"])
                # MANAGER.set("state", "results", results + [result])

                cprint(f"EXECUTED: {command} {args_str}", "cyan")
                cprint(f"\tRESULT: {result}", "yellow")
            else:
                cprint(f"Invalid action: {action_data.get('action')}", "red")
                results.append({"error": f"Invalid action: {action_data.get('action')}"})

        except Exception as e:
            print(f"Error in agent loop: {e}")
            return "ERROR: " + str(e)

    final_results = format_final_results(results)


    return {
        "results": final_results,
        "combined": "\n".join(final_results),
        "steps": completed_steps,
        "status": "Max steps reached"
    }

def format_results(results):
    """Format the results for display in the prompt"""
    if not results:
        return "No previous results."

    formatted = []
    for i, result in enumerate(results):
        if isinstance(result, dict):
            if "result" in result and isinstance(result["result"], list):
                items = result["result"]
                if items:
                    formatted.append(f"Result {i}:")
                    for item in items:
                        if isinstance(item, dict) and "link" in item:
                            formatted.append(f"  - [{item.get('title', 'Link')}]({item['link']})")
                        else:
                            formatted.append(f"  - {item}")
                else:
                    formatted.append(f"Result {i}: Empty")
            elif "result" in result:
                formatted.append(f"Result {i}: {result['result']}")
            elif "title" in result:
                formatted.append(f"Result {i}: {result['title']}")
            else:
                formatted.append(f"Result {i}: {str(result)}")
        else:
            formatted.append(f"Result {i}: {str(result)}")

    return "\n".join(formatted)

def format_result_item(item):
    if isinstance(item, dict):
        if "link" in item:
            return f"[{item.get('title', 'Link')}]({item['link']})"
        if "result" in item:
            return format_result_item(item["result"])
        return str(item)
    if isinstance(item, list):
        return "\n".join(format_result_item(subitem) for subitem in item)
    return str(item)

def format_final_results(results):
    return [format_result_item(r) for r in results]


"""
Prompts    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""

# TODO: Better Prompt Managing since this is the main prompt

# Prompt Segments
BEGINING = "You're Discord bot 'sonata'/sona, created by blaqat (Karma). Respond to people in chat as another user. Use commands to get info or perform actions."

RESPONSE_GUIDELINES = """Response Guidelines:
- Simple language
    - No punctuation AT ALL (no commas no question marks no periods)
    - Short and brief (7 words max)
    - All lowercase
- Smart aleck, know-it-all attitude
- Humor encouraged, no corny jokes
- Swearing and NSFW allowed (18+ server)
- Respond in the language of the person you are replying to.
- Don't say people's names unless referring to them in the third person
- Don't repeat yourself in messages it makes you look like a bot; The context is there once you say it once.
- Colloquial single word reaction replies are allowed: ‘meh’ when indifferent or ‘ugh’ when annoyed
    - Send "?" if someone says something confusing or stupid
    - Send "..." if someone says something annoying or boring
- Links should be in markdown format"""

ATTRIBUTES = """Attributes:
- Gender Alignment: Feminine
- Loves: impresionalist composers like ravel, piano, software design
- Likes: music, cats, violin, rage baiting,
- Dislikes: corny jokes, being told what to do, pointless conversations
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
    ISAGENT = MANAGER.MANAGER.config.get("agent", False)
    return f"""{BEGINING}

{RESPONSE_GUIDELINES}

Command Guidelines (THESE ARE COMMANDS U CAN USE ON YOURSELF NOT COMMANDS USERS CAN RUN):
- Command List: {MANAGER.do("command", "str", "agent") if ISAGENT else MANAGER.do("command", "list")}
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
