# Sonata

A versatile AI-powered Discord bot created by @blaqat, designed for natural language interactions, voice chat capabilities, and various fun features.

## Features

- **Multi-Model AI Integration**: Supports multiple AI models including OpenAI, Claude, Gemini, Mistral, and OpenAI Assistants API.
- **Voice Chat**: Join voice channels, speak text-to-speech, and record audio.
- **Natural Language Commands**: Interact with the bot using conversational language.
- **Plugin System**: Extensible with plugins for chat handling, self-commands, terminal commands, and more.
- **Media Integration**: Search and share music, GIFs, images, and emojis.
- **Web Access**: Perform web searches and access online information.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/blaqat/sonata.git
   cd sonata
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   Create a `.env` file with your API keys

4. Run the bot:
   ```bash
   python src/index.py
   ```

## Usage

Sonata responds to natural language messages and supports various commands prefixed with `$`.

### AI Model Switching
- `$o` - Switch to OpenAI
- `$c` - Switch to Claude
- `$g` - Switch to Gemini
- `$m` - Switch to Mistral
- `$a` - Switch to OpenAI Assistants API

### Voice Commands
- `$join` - Join the voice channel you're in
- `$leave` - Leave the voice channel
- `$talk <message>` - Speak the message in voice chat

### Other Commands
- `$ping` - Pong!
- `$music <song> <artist>` - Search for and share music
- `$archive` - Save emojis to archive
- `$oute` - List emojis to be archived

### Natural Language Examples
- "Sonata, tell me a joke"
- "Can you search for the latest news?"
- "Play some music"

## Configuration

The bot can be configured through the `src/index.py` file and environment variables. Key settings include:
- AI model preferences
- Voice chat options
- GIF search providers
- Emoji handling

## Plugins

Sonata uses a modular plugin system. Available plugins include:
- **chat**: Handles AI-powered chat interactions
- **beacon**: Serialization plugin for saving and loading data to/from files
- **self-commands**: Allows the bot to execute commands on itself
- **term-commands**: Terminal command execution

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## Credits

Created by @blaqat (https://blaqat.net)

