"""Emoji archive helpers: parse Discord custom emojis, download, and list them."""

from __future__ import annotations

import os
import re

import requests

IMAGES_DIR = "images/"


def get_emoji_id(emoji_str):
    """
    Extracts the emoji ID, animation status, and name from a Discord emoji string.
    """
    animated = "a:" in emoji_str
    name = re.search(r":\w*:", emoji_str)
    if name:
        name = name.group()[1:-1]
    match = re.search(r":\d*>", emoji_str)
    if match:
        return match.group()[1:-1], animated, name
    return None, False, None


def get_emoji_link_from_id(emoji_id, animated=False, name=""):
    """
    Constructs a direct link to a Discord emoji given its ID, animation status, and name.
    """
    if emoji_id is None:
        return
    link = f"https://cdn.discordapp.com/emojis/{emoji_id}"
    if animated:
        ext = ".gif"
    else:
        ext = ".png"
    link += ext
    return link, name, ext


def trans_emo(emoji):
    """
    Transforms a Discord emoji string into a direct link, filename, and extension.
    """
    return get_emoji_link_from_id(*get_emoji_id(emoji))


def download_emoji(direct_link, filename, ext, directory=IMAGES_DIR):
    """
    Downloads an emoji from a direct link and saves it to the images directory.
    """
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(directory + filename + ext, "wb") as f:
        f.write(requests.get(direct_link).content)


def chunk_list(lst, chunk_size):
    """
    Splits a list into chunks of a specified size.
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i : i + chunk_size]


def read_images(directory=IMAGES_DIR):
    """
    Reads all images from the images directory and formats them as emoji codes.
    """
    if not os.path.exists(directory):
        os.makedirs(directory)
    files = os.listdir(directory)
    image_list = [f":{f[:-4]}:" for f in files]
    # sort by name
    image_list.sort()
    image_str = ""
    for i in chunk_list(image_list, 12):
        image_str += " ".join(i) + "\n"
    return image_str
