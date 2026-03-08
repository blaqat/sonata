"""
I Spy
-----
This plugin converts image attachments into compact text descriptions
and appends them to the chat history so that image context is preserved
even after the raw images leave the current context window.

Depends on: chat
"""

from modules.utils import Colors
from modules.AI_manager import AI_Manager, Context
from modules.utils import async_print as print, async_cprint as cprint

CONTEXT, MANAGER, PROMPT_MANAGER = AI_Manager.init(lazy=True)
__plugin_name__ = "ispy"
__dependencies__ = ["chat"]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

ISPY_PROMPT = """
You are converting an image into a compact memory entry for an AI assistant.

Goals:
- Be concise (max ~60 words).
- Use plain text only.
- Make it easy to search later.

Describe each image in this exact JSON format, with no extra text:

{
  "summary": "1–2 sentence high-level description.",
  "entities": ["key person/object 1", "key person/object 2"],
  "text_in_image": ["exact visible text 1", "exact visible text 2"],
  "context_tags": ["short tags about topic or setting"]
}

Guidelines:
- Focus on what a future assistant would need to recall: who/what is in the image, what they're doing, where they are, and any important visible text.
- Do NOT include colors or artistic style unless they are crucial.
- Prefer fewer, more informative entities and tags over many generic ones.
- If there is no visible text, return an empty array for "text_in_image".
- Keep all values short to minimize tokens.
"""

# ---------------------------------------------------------------------------
# Post-effect on chat.set — describe images and append to message
# ---------------------------------------------------------------------------

COMPLETED = []


@MANAGER.with_context(config=True, manager=True)
def ispy_init(context: Context):

    @MANAGER.effect_post("chat", "set", prepend=True)
    def describe_images(M, chat_id, message_type, author, message, replying_to=None):
        """Describe any queued images for this chat and append text to the message."""
        images_map = context.config.get("images", {})
        images = images_map.get(chat_id, [])

        # Only run when there are images and they haven't been processed yet
        # (the last element being True is the sentinel used by clear_images)
        if not images or (images and images[-1] is True):
            cprint("No images to describe", Colors.YELLOW)
            return (chat_id, message_type, author, message, replying_to)

        images = list(filter(lambda x: x not in COMPLETED, images))
        cprint(f"Describing {len(images)} images...", Colors.CYAN)

        if len(images) == 0:
            cprint("No images to describe", Colors.YELLOW)
            return (chat_id, message_type, author, message, replying_to)

        # Process images in batches of 4 to reduce hallucination risk
        descriptions = []
        batch_size = 4
        for i in range(0, len(images), batch_size):
            batch = images[i : i + batch_size]
            for image in batch:
                COMPLETED.append(image)
            try:
                result = PROMPT_MANAGER.send(
                    lambda *_: ISPY_PROMPT,
                    config={"images": batch, "instructions": ""},
                )
                print(result)
                descriptions.append(result)
            except Exception:
                # If description fails, skip silently — images are still
                # available for the next AI request via the normal path.
                cprint("Failed to describe images", Colors.RED)
                pass

        if descriptions:
            attachment_text = "\n".join(descriptions)
            message = (
                f"{message}\nAttachments ({len(descriptions)}):\n{attachment_text}"
            )

            # Update the last entry in chat history so the description persists
            # chat_history = context.manager.get("chat")
            # if chat_history.get(chat_id) and len(chat_history[chat_id]) > 0:
            #     last = chat_history[chat_id][-1]
            #     chat_history[chat_id][-1] = (last[0], last[1], message, last[3])

        # Mark images as processed so clear_images can clean them up
        # images.append(True)
        # images_map[chat_id] = images
        # context.config.set(images=images_map)

        return (chat_id, message_type, author, message, replying_to)
