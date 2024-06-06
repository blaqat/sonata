
module.exports = {
	alias: ['play', 'pause', 'stop', 'skip', 'repeat'],
	description: 'Default',
	execute(message, command, link) {
		const Message = global.numa.classes.get("Message")
		switch(command.namecall){
			case 'play': {
				const song = new (global.box.Song)(link)
				song.loadBuffer().then(() => {
					stream = song.stream
					if (message.channel.type === 'dm') return;
			
					const voiceChannel = message.member.voice.channel;
			
					if (!voiceChannel) {
						return message.reply('please join a voice channel first!');
					}

					voiceChannel.join().then(connection => {
						const dispatcher = connection.play(stream);

						let m = new Message("Beepbot", "Playing", song.title)
						const [min, sec] = unitConvertor(song.duration, 60)
						
						m.sendFromEmbed(message, m.applyToEmbed(m.embed, {setFooter:[`Duration: ${min>0?"":min} mins and ${sec} seconds`]}))
						dispatcher.on('finish', () => voiceChannel.leave());
					})
				})
			}

		}
	}
}
