const Color = require("./Color")
const Alias = require("./Alias")
const _ = "\u200B"

class MessageType {
    static types = new Map();
    static DEFAULT_MESSAGE_DATA = {
        color: Color.get("default").color,
        thumbnail: Alias.get("default").base,
        description: " "
    }
    #args

    constructor(name, data, args){
        this.name = name;
        this.data = Object.assign({}, MessageType.DEFAULT_MESSAGE_DATA, data || {})
        this.#args = args
        MessageType.types.set(name, this)
    }

    new(...args){
        let data = Object.assign({}, this.data)
        for(let i = 0; i < args.length; i++)
            data[this.#args[i]] = args[i]

        return new Message(data, true)
    }

    static get(name){
        return MessageType.types.get(name);
    }
}

class Message {
    #data
    static MessageType = MessageType;
    static BLANK = _;
    constructor(data = {}, embed = false){
        this.#data = Object.assign({}, MessageType.DEFAULT_MESSAGE_DATA, data);
        this.embed = embed;
    }

    addField(name, value, inline){
        if(!this.#data.fields)
            this.data.fields = []

        this.data.fields.push({name: name || _, value: value || _, inline: inline || false})
    }

    send(Message, data, embed = this.embed){
        data = Object.assign({}, this.#data, data || {})
        Message.channel.send((embed)?{embed: data}:data.description)
    }

    static fromType = (type, ...args) => MessageType.get(type).new(...args)
}

new MessageType("Error", {
    color: Color.get("red").color,
    thumbnail: _,
    description: "There was an unspecified error.",
    author: {
        name: "ERROR",
        icon_url: Alias.get("red").base,
    },
    timestamp: new Date(),


}, ["title", "description"])

module.exports = Message