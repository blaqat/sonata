
const { SystemChannelFlags } = require('discord.js');
const fs = require('fs')
const { Readable } = require('stream');
const Synths = new Map()

const synthFiles = fs.readdirSync('./BeepboxAPI/Synths').filter(file => file.endsWith('.js'))
for (const file of synthFiles){
    let s = require("./Synths/"+file)
    Synths.set(file.slice(0,-3), s)
}

function bufferToStream(buffer) { 
    var stream = new Readable();
    stream.push(buffer);
    stream.push(null);
  
    return stream;
}

const beepboxLinkToMod = new Map([
    [["jummbus.bitbucket.io/1_2"], "Jummbox 1_2"],
    [["moddedbeepbox.github.io/3.3", "jummbus.bitbucket.io", "beepbox.co","bluaxolotlbox.neocities.org","jummbus.bitbucket.io/2_0_orig"], "Jummbox 2_0"],
    [["moddedbeepbox.github.io"], "Modbox Beta"],
    [["theepicosity.github.io"], "Modbox 2_3"],
    [["parad0xstuff.github.io/sandbox"], "Sandbox 1_0"],
    [["parad0xstuff.github.io/sandbox-2.0"], "Sandbox 2_0"],
    [["parad0xstuff.github.io"], "Sandbox 3_0"],
    [["fillygroove.github.io"], "Sandbox 3_1"],
    [["synthbox.co", "synthboxtest.neocities.org"], "Synthbox"],
    [["hidden-realm.github.io/cardboardbox"], "Cardboardbox"]
])

class BeepboxSong {
    #modType
    #URL
    #title
    #synth
    #buffer
    #synthKey
    #duration

    static isABeepboxLink(url) {
        return this.#linkToMod(url)!=false
    }

    constructor(url, title){
        this.#title = title || ""
        this.link = url
    }

    get link(){
        return this.#URL
    }

    #linkToMod(url){
        let mod;
        for(let [links,val] of beepboxLinkToMod){
            if(links.some(link => url.includes(link))){
                mod = val
                break;
            }
        }
        if(mod)
            return mod
        else
            return false
    }

    set link(url){
        this.#URL = url
        const typ = this.#linkToMod(url)
        const bb = Synths.get(typ)
        console.log(typ, bb)

        this.#modType = typ
        url = url.slice(url.indexOf("#")+1)

        const bbid = url.slice(url.indexOf("=")+1)
        this.#synthKey = bbid
        console.log(bb)
        const synth = new bb.classes.Synth(bbid)
        this.#synth = synth
        if(this.#title == "")
            this.#title = synth.song.title || ""

        if(this.#title == "Unnamed" || this.#title == "")
            this.#title+=` ${typ} song`
        
        this.#duration = synth.totalSamples / synth.samplesPerSecond
        this.#buffer = bb.getBuffer(this.#synth)
    }

    get modType(){
        return this.#modType
    }

    get title(){
        return this.#title
    }

    get link(){
        return this.#URL
    }

    get duration(){
        return this.#duration
    }

    async getLoadedBuffer(){
        return await this.#buffer
    }

    get buffer(){
        return this.#buffer
    }

    async loadBuffer(){
        this.#buffer = await this.#buffer
        return true
    }

    get stream(){
        return bufferToStream(this.buffer)
    }

    get songData(){
        return this.#synth.song;
    }
}


module.exports = {
    Song: BeepboxSong,
    Synths: Synths,
}
