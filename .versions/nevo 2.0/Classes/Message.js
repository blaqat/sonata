const DC = require('discord.js')

/*
class message
properties: 
    title: str
    title link: str
    title desc: str
    timestamp: bool
    footer
    fields: array
    image: str
*/

class Message { //constructor(title, message, image, link, color, fields, footer){
    constructor(header, title, message, image, link, color, fields, footer, rest){
        this.fields = []
        this.header = header || "\u200B"
        this.title = title || "\u200B"
        this.desc = message || ""
        this.color = color || '#01FFA9'
        this.image = image || false
        this.url = link || 'https://beepbox.co/'
        this.footer = footer || ""
        this.functions = rest || {}
        fields = fields || []
        fields.forEach(field => {
            this.addField(...field)
        })
    }

    addField(name, value, inline){
        fields.append({name:name!=''&&name||'\u200B', value:value!=''&&value||'\u200B', inline:inline||false})
    }

    get embed(){
        let embed = new DC.MessageEmbed()
        embed.setAuthor(this.header, "https://i.imgur.com/zSAolZp.jpg")
        embed.setTitle(this.title)
        embed.setDescription(this.desc)
        //embed.setTimestamp()
        embed.setColor(this.color)
        embed.setURL(this.link)
        embed.setFooter(this.footer, 'https://i.imgur.com/pwNVCb4.png')
        embed.addFields(...this.fields)

        return embed
    }

    send(message, text){
        let embed
        if(text){
            let temp = this.desc
            this.desc = text
            embed = this.embed()
            this.desc = temp
        }

        embed = !embed && this.embed || embed

       return message.channel.send(embed)
    }

    sendFromEmbed(message, embed){
        return message.channel.send(embed)
    }

    applyToEmbed(embed, funcs){
        funcs = funcs || this.functions

        for (const [i, v] of Object.entries(funcs)) {
            embed[i](...v)
        }

        return embed
    }
}


messageTypes = {
    error: new Message()
}

module.exports = Message