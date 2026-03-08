"""
I Spy
-----
This plugin converts image attachments into compact text descriptions
and appends them to the chat history so that image context is preserved
even after the raw images leave the current context window.

Depends on: chat
"""

from modules.AI_manager import AI_Manager, Context
from modules.utils import async_cprint as cprint

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

PROMPT_MANAGER.add("describe_images", ISPY_PROMPT)


@MANAGER.with_context(config=True, manager=True)
def ispy_init(context: Context):

    @MANAGER.effect_post("chat", "set", prepend=True)
    def describe_images(M, chat_id, message_type, author, message, replying_to=None):
        """Describe any queued images for this chat and append text to the message."""
        images_map = context.config.get("images", {})
        images = images_map.get(chat_id, [])
        tracked = context.config.get("ispy_tracked", {})
        processed_count = tracked.get(chat_id, 0)

        if not images:
            if processed_count:
                tracked[chat_id] = 0
                context.config.set(ispy_tracked=tracked)
            return (chat_id, message_type, author, message, replying_to)

        # Only describe new images since last run. This avoids repetitive
        # behavior without clearing images before the main chat request uses them.
        if processed_count > len(images):
            processed_count = 0
        new_images = images[processed_count:]
        if len(new_images) == 0:
            return (chat_id, message_type, author, message, replying_to)

        # Process images in batches of 4 to reduce hallucination risk
        descriptions = []
        batch_size = 4
        for i in range(0, len(new_images), batch_size):
            batch = new_images[i : i + batch_size]
            try:
                result = PROMPT_MANAGER.send(
                    "describe_images",
                    config={"images": batch, "instructions": ""},
                    AI="Gemini",
                    model="gemini-2.5-flash",
                )
                descriptions.append(result)
            except Exception:
                # If description fails, skip silently — images are still
                # available for the next AI request via the normal path.
                cprint("Failed to describe image batch", "red")
                pass

        tracked[chat_id] = len(images)
        context.config.set(ispy_tracked=tracked)

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

        return (chat_id, message_type, author, message, replying_to)
