module.exports = {
	alias: ['ping', 'test', 'ho'],
	description: 'Ping!',
	execute(message, command, ...args) {
		m = new (global.numa.classes.get('Message'))("TEST", "Pong.")
		
		m.sendFromEmbed(message, m.applyToEmbed(m.embed, {setTimestamp:[0], setColor:['#ff0000']}))
		message.channel.send('Pong.');
	},
}
