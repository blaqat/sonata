
module.exports = {
	alias: ["aliases", "alts"],
	description: 'Used to find the alternate names for a command.',
	execute(message, command, commandName) {
		Message = global.numa.classes.get("Message")
		let c = numa.getCommand(".bb "+commandName)
		if(c.main){
			c = c.main.data
			new Message("Helper", ""+commandName+"'s Aliases", c.alias.join("\n")).send(message)
		}
		else {
			let m = new Message("Beepbot Error:", "ERROR", '"'+ commandName + '" is not a valid command.')
			m.sendFromEmbed(message, m.applyToEmbed(m.embed, {setColor:["#FF0144"], setAuthor:[m.header, 'https://i.imgur.com/8p3StTL.jpg']}))
		}
	}
}