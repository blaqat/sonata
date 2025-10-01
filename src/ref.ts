import { Message, OmitPartialGroupDMChannel } from "npm:discord.js";
type die = OmitPartialGroupDMChannel<Message<boolean>> | Message<boolean>;

class Reference {
  message;
  author;
  content;
  nextId: string | null;
  constructor(
    message: die,
    name: string,
    content: string,
    nextId: string | null,
  ) {
    this.message = message;
    this.author = name;
    this.content = content;
    this.nextId = nextId;
  }
}

//TODO: Apples
const references: Map<string, Reference> = new Map();

function getAuthor(message: die) {
  let author = message.author.username;
  if (message.author.bot) return author;
  if (message.member?.nickname) {
    author += ` (Nick: ${message.member?.nickname})`;
  }
  return author;
}

function storeReference(message: die) {
  const ref = new Reference(
    message,
    getAuthor(message),
    message.content,
    message.reference?.messageId || null,
  );
  references.set(message.id, ref);
  return ref;
}

async function getNextReference(message: die) {
  if (!references.has(message.id)) {
    storeReference(message);
  }
  const nextId = references.get(message.id)?.nextId;
  if (!nextId) return null;
  if (!references.has(nextId)) {
    const nextMessage = await message.channel.messages.fetch(nextId);
    return storeReference(nextMessage);
  }
  return references.get(nextId);
}

async function getReferenceMessage(message: die, returnMessage = true) {
  if (!message.reference) return null;
  const refMessage = await getNextReference(message);
  return returnMessage ? refMessage?.message : refMessage;
}

export async function getReferenceChain(
  message: die,
  maxLength = -1,
  includeMessage = false,
) {
  if (!message) return null;
  const chain = [];

  if (includeMessage) {
    chain.push([message.author.username, message.content]);
  }

  if (!message.reference) {
    return includeMessage ? chain : null;
  }

  let reference = await getReferenceMessage(message, false);

  while (reference && maxLength !== 0) {
    chain.push([reference.author, reference.content]);
    if (!(reference instanceof Reference) || !reference.nextId) break;
    reference = await getReferenceMessage(reference.message, false);
    maxLength--;
  }

  if (chain.length === 0) return null;
  if (maxLength === 0) return chain[0];
  return chain;
}

export function getChainString(chain: Array<any> | null) {
  if (!chain) return "";
  return chain.reverse().map(([author, content]) => `${author}: ${content}`)
    .join("\n");
}

export function countChainFromUser(chain: Array<any>, user: string) {
  if (!chain) return 0;
  return chain.filter(([author]) => author === user).length;
}
