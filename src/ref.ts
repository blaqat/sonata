import { Message, OmitPartialGroupDMChannel } from "npm:discord.js";
type die = OmitPartialGroupDMChannel<Message<boolean>> | Message<boolean>;

/**
 * Represents a reference to a message with associated metadata.
 */
class Reference {
  /**
   * The message object.
   */
  message;

  /**
   * The author of the message.
   */
  author;

  /**
   * The content of the message.
   */
  content;

  /**
   * The ID of the next reference in a chain, or null if none.
   */
  nextId: string | null;

  /**
   * Creates a new Reference instance.
   * @param message - The message object.
   * @param name - The name of the author.
   * @param content - The content of the message.
   * @param nextId - The ID of the next reference, or null.
   */
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

/**
 * Retrieves the author's display name from a message, appending the nickname if available and the author is not a bot.
 *
 * @param message - The message object containing author and member details.
 * @returns The author's username, or username with nickname in parentheses if a nickname exists and the author is not a bot.
 */
function getAuthor(message: die) {
  let author = message.author.username;
  if (message.author.bot) return author;
  if (message.member?.nickname) {
    author += ` (Nick: ${message.member?.nickname})`;
  }
  return author;
}

/**
 * Stores a reference object for the given message in the references map.
 *
 * @param message - The message object of type `die` to create a reference for.
 * @returns The created `Reference` object.
 */
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

/**
 * Retrieves the next reference in the message chain for the given message.
 * If the message is not yet stored, it stores it first.
 * If the next reference ID exists but is not cached, it fetches the message and stores it.
 * Returns null if there is no next reference.
 *
 * @param message - The message object to get the next reference for.
 * @returns A promise that resolves to the next reference message or null if none exists.
 */
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

/**
 * Retrieves the reference message associated with the given message.
 * If the message has no reference, returns null.
 * Otherwise, fetches the next reference and returns either the message content or the full reference object based on the returnMessage flag.
 *
 * @param message - The message object to get the reference for.
 * @param returnMessage - If true, returns the message content; if false, returns the full reference object. Defaults to true.
 * @returns A promise that resolves to the reference message content, the full reference object, or null if no reference exists.
 */
async function getReferenceMessage(message: die, returnMessage = true) {
  if (!message.reference) return null;
  const refMessage = await getNextReference(message);
  return returnMessage ? refMessage?.message : refMessage;
}

/**
 * Retrieves a chain of referenced messages starting from the given message.
 * The chain includes author usernames and message contents, optionally including the original message.
 * It traverses references until no more exist or the maximum length is reached.
 *
 * @param message - The initial message to start the reference chain from.
 * @param maxLength - The maximum number of references to include in the chain. Use -1 for no limit.
 * @param includeMessage - Whether to include the original message at the start of the chain.
 * @returns A promise that resolves to an array of [author, content] pairs representing the reference chain,
 *          or null if no chain is found, or a single pair if maxLength is 0.
 */
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

/**
 * Generates a string representation of a message chain by reversing the order,
 * formatting each message as "author: content", and joining them with newlines.
 * If the chain is null, returns an empty string.
 * @param chain - An array of tuples [author, content] representing the message chain, or null.
 * @returns A formatted string of the reversed message chain, or an empty string if chain is null.
 */
export function getChainString(chain: Array<any> | null) {
  if (!chain) return "";
  return chain.reverse().map(([author, content]) => `${author}: ${content}`)
    .join("\n");
}

/**
 * Counts the number of items in the chain where the author matches the specified user.
 * @param chain - An array of items, each represented as an array where the first element is the author.
 * @param user - The user string to match against the author in each item.
 * @returns The count of matching items, or 0 if the chain is falsy.
 */
export function countChainFromUser(chain: Array<any>, user: string) {
  if (!chain) return 0;
  return chain.filter(([author]) => author === user).length;
}
