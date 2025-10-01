import "jsr:@std/dotenv/load";
import {
  Client,
  Events,
  GatewayIntentBits,
  Message,
  OmitPartialGroupDMChannel,
  Partials,
  TextChannel,
} from "npm:discord.js";
import {
  countChainFromUser,
  getChainString,
  getReferenceChain,
} from "./ref.ts";
import { claudeRequest } from "./claude.ts";
import { randomInt } from "node:crypto";

const BOT_TOKEN = Deno.env.get("DC_BOT_AURIS_TOKEN");
const CLIENT_ID = Deno.env.get("DC_BOT_AURIS_APP_ID");

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.DirectMessages,
    GatewayIntentBits.DirectMessageTyping,
    GatewayIntentBits.DirectMessageReactions,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.GuildMessageReactions,
    GatewayIntentBits.GuildMessageTyping,
  ],
  partials: [
    Partials.Channel,
    Partials.Message,
    Partials.GuildMember,
    Partials.User,
  ],
});

client.once(Events.ClientReady, (client) => {
  console.log(`${client.user.tag} is loaded!`);
});
// (MessageType, Author, MessageText, Message They are Replying To)
type MessageLog = [string, string, string, string | null];
const history: Map<string, Array<MessageLog>> = new Map();

function logMessage(
  channelId: string,
  author: string,
  text: string,
  replyTo: string | null,
  messageType: string,
) {
  if (history.has(channelId)) {
    const currentHistory = history.get(channelId);
    currentHistory?.push([messageType, author, text, replyTo]);
  } else {
    history.set(channelId, [[messageType, author, text, replyTo]]);
  }
  console.log(author, ":", text);
}

let mostRecentContext:
  | string
  | OmitPartialGroupDMChannel<Message<boolean>>
  | null = null;

client.on(Events.MessageCreate, async (message) => {
  mostRecentContext = message.channelId;
  const channelId = message.channelId;
  let author = message.author.username;
  if (message.member?.nickname) {
    author += ` (Nick: ${message.member?.nickname})`;
  }
  const messageText = message.content;
  const messageType = message.author.id === CLIENT_ID ? "Bot" : "User";
  const messageReplyChain = await getReferenceChain(message);
  const replyingTo = messageReplyChain
    ? `${messageReplyChain[0][0]}: ${messageReplyChain[0][1]}`
    : null;
  const replyingToBot = messageReplyChain &&
    messageReplyChain[0][0] === "auris";

  const timesAskedForSonata = countChainFromUser(messageReplyChain, "sonata");
  if (
    timesAskedForSonata >= 1 && replyingToBot &&
    messageReplyChain[1][0] == "sonata"
  ) {
    return;
  }

  logMessage(
    channelId,
    author,
    messageText,
    replyingTo,
    messageType,
  );

  if (message.author.id === CLIENT_ID) return;
  // if (message.author.bot) return;
  const validNames = ["auris", "auri"];
  const aurisExp = new RegExp(
    `<@${CLIENT_ID}>|${validNames.map((name) => `\\b${name}\\b`).join("|")}`,
    "i",
  );

  if (
    aurisExp.test(messageText) || message.mentions.has(client.user) ||
    message.channel.isDMBased() || replyingToBot
  ) {
    const historyString =
      history.get(channelId)?.map(([t, author, text, replyTo]) =>
        `(${t}, ${author}, ${text}, ${replyTo || "null"})`
      ).join("\n") || "";

    const response = await claudeRequest(
      historyString,
      getChainString(messageReplyChain),
      author,
      messageText,
    );

    await message.reply({
      content: response,
      allowedMentions: { repliedUser: false },
    });
  }
});

client.login(BOT_TOKEN);

Deno.addSignalListener("SIGINT", async () => {
  try {
    let ch: TextChannel | null = await client.channels.fetch(
      mostRecentContext,
    ) as TextChannel;

    const sleepy_gifs = [
      "https://tenor.com/view/pokemon-togepi-anime-sleep-sleep-houndoom-gif-24354694",
      "https://tenor.com/view/kirby-kirby-and-the-forgotten-land-boredom-bored-boring-gif-25088346",
      "https://tenor.com/view/yui-sleeping-kon-sleep-gif-7511275",
      "https://tenor.com/view/gn-chat-cat-good-night-chat-kitty-gif-1739596971726164224",
      "<a:kittysleepy:1095222272450637849>",
    ];

    await ch.send(
      sleepy_gifs.at(randomInt(sleepy_gifs.length)) || "im eepy goodnight!!!",
    );
  } finally {
    Deno.exit(0);
  }
});
