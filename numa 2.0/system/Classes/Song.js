const Message = require("./Message.js")
const ytdl = require('ytdl-core')
const youtube = require("discord-youtube-api")
const soundcloud = require("soundcloud.ts")
const Utility = require("./Utility")
const Alias = require("./Alias")

const tools = new Utility();

// SONGTYPES



class Song {
    name
    duration
    artist
    url
    #stream
    #state
    #connection

    constructor(url, name, artist){
        this.url = url;
        this.name = name || "Unnamed"
        this.artist = artist || "Unknown"
    }

    set url(link){
        tools.getBaseLink(link, (link) => {
            
        })
    }

    async play(message, bot){
        let VC = message.member.voice.channel
        
        VC.join().then(bot => {
           
        })
        
    }
}


/**
 * new Song(link, [NAME, ARTIST])
 */