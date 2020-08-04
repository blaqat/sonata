const Discord = require('discord.js');
const client = new Discord.Client();
const config = require('./config.json');
const fs = require('fs');
const cooldowns = new Discord.Collection();
const Keyv = require('keyv');



print = (...str) => {
	console.log(...str);
}

nl = (...str) => {
	let ns = ""
	str.forEach(t=>{
		ns += (t + "\n");
	})
	return ns;
}

printl = (...str) => {
	console.log(nl(str));
}

client.once('ready', () => {
	console.log('Ready!');
});


client.login(config.token);

client.on('message', message => {
	let m = message.content
	let [nevo, prefix] = wantsNevo(m)

	if(nevo){
		let [command, args] = parseMessage(m, prefix);

		command = getCommand(command)
		//client.user.setActivity('the stars weave into the umbra around me...', { type: 'WATCHING' });

		if(commandChecker(message, command)){

			print(message.author.username," used:", command[1].names[0], ...args)

			try{command[0](message, ...args)}
				catch(err){
					print("CAUGHT ERROR:\n",err)
					message.channel.send("thats not how arguments work idiot 🤦 use a comma next time.")
				};
		}
	}
});

// Initialization for nevo
var prefix = [".", ".numa ", config.prefix];
var cmds = [];
var defaultProfile = ['3AD1CA', 'NumaBot', '', ["VUPA.jpg"]]
var Profiles = {//color, nickname, status, images
	Allumna : ['AE0A27', 'The All Seyeing',`Before I got my eye put out, I liked as well to see, As other creatures that have eyes, And know no other way.`, ["Allure.png", "alunis.jpg"]],
	Karma : ['F003F9', 'Purple Eyes', "It's bad luck to step on the cracks in the sidewalk, you know",
		["blaqat.png","Darkarmaid.png","Karma.png","meow2.png"	]],
	bubly: ['ABC1E8', ".｡:+*", ".｡:+* by Snailhouse",
		["bubly.png","boobly.png"	]],
	Canary: ['F04F60', "Original Sun Bird", "",
		["Canary.png"]],
	Carma : ['CED0F8', 'Beyond Lucky', "meow",
		["Carma.png", "carmax.png"	]],
	Trigectory : ['820A00', "Triggasaurus Rex", "see me in phantom forces",
		["Trigectory.jpg","Trigectory.png"	]],
	Rouge : ['E63232', "The best.", "-_-",
		["Rouge.png","Roug.png"	]],
	Rougism : ['FF484D', "the best!", "o-o",
		["Rougism.png"	]],
	rouge : ['FD3E6F', "Its a hood", "All the better to eat you up with.",
		["rouge.jpg","gato de negro.jpg"	]],
	RoyaleRuby: ['C43141', "KOTW!", "o-o",
		["RoyaleRuby.png"	]],
	Velocity: ['C62D32', "Botty Allen The Fas-", "My name is barry allen and I'm the fasest man alive, accorind to the ou-",
		["Velocity.jpg"	]],
	["meh-gan"]: ['EC76CE', "Ghost", "Hi bye 👋",
		["meghan.png","meh-gan.jpg"	]],
	Moirae: ['B423F2', "Not Real", "If you got money hmu",
		["Moirae.png", "Muse.jpg"]],
	MagikMagiik: ['B64FDE', 'Better Maark', "the lights stay hushed; fixed on invading the umbra around me. MY umbra...",
		["Nemesis.png","Moira.png"	]],
	nobo: ['CCD4E2', "Karma's alt","nose goes",
		["nobo.png"	]],
	nevo: ['7131ce', "Social Butterfly","the stars weave into the umbra around me",
		["butterfly.png"]],
	bananaqat: ['FFF7B2', "🍌😺🍌", "mrow ima qt ;3"]
}

var defaultData = {
	names: ["Name"],
	description: "Default Description",
	arguments: "None",
	whitelist: false,
	blacklist: false,
	cooldown: 0,
	timeLeft: 0
}

var commandData = (given)=>{ 
	let def = defaultData

	for ([i, v] of Object.entries(def)){
		if(given[i] == true)
			given[i] = config[i]
		else if(given[i] == null)
			given[i] = def[i]
	}

	setInterval(function () {
	  if(given.timeLeft > 0)
	  	given.timeLeft--;
	}, 1000)

	return given;
}

var commandChecker = (message, command) => {
	if(!command) return false;

	let commandData = command[1]
	let failed = false

	if (!(!commandData.whitelist||commandData.whitelist.includes(message.author.id))) {
		message.channel.send("You are not whitelisted for this command >:)))))")
		failed = true
	}
	else if (!( commandData.timeLeft <= 0 )) {
		message.channel.send(`Please wait ${commandData.timeLeft} more second${commandData.timeLeft==1?'':'s'} to use this command :0`)
		failed = true
	}
	else if (commandData.blacklst && commandData.blacklist.includes(message.author.id)) {
		message.channel.send("HAHAHAHHAH LOSER You are blacklisted from this command")
		failed = true
	}

	if(!failed){
		commandData.timeLeft += commandData.cooldown;
		return true;
	}
	else
		return false;
}

function parseMessage(message, usedPrefix){
	message = message.replace(usedPrefix, "");

	let cmd, args;

	if(message.search(" ")==-1){
		cmd = message;
		args = [];
	}
	else {
		cmd = message.slice(0,message.indexOf(" ")).toLowerCase();
		args = message.slice(message.indexOf(" ")+1).replace(", ",",").split(",");
	}

	return [cmd, args];
}

function wantsNevo(message){

	for(let i = 0; i < prefix.length; i++){
		let pf = prefix[i];

		if (message.startsWith(pf) && !(pf == "." && message.startsWith(".nevo"))){
			return [true, pf];
		}
	}

	return [false, null];
}

function newCommand(name, func, data, ...aliases){
	data.names = [name,...aliases]
	cmds.push([func, commandData(data)])
};

function getCommand(name){
	let command;

	cmds.forEach(cma=>{
		cma[1].names.forEach(cName=>{

			if(name == cName.toLowerCase()){
				command = cma;
				return true;
			}

		})

	})

	return command?command:null;
}

encode = (string, full) => {
	return (full?"```\n":"`") + string + (full?"\n```":"`");
}

quote = (...str) => {
	let ns = ""

	str.forEach(t=>{
		ns += ("> "+t + "\n");
	})

	return ns;
}

nevoSend = (m, title, ...str) => m.channel.send(quote(encode(title.toUpperCase()),"",...str));

//Commands

newCommand("alias", function(message, commandName){
	let command = getCommand(commandName);
	if(command){
		let commandNames = getCommand(commandName)[1].names;

		//message.channel.send(quote(encode("Alternate Command Names for " + commandNames[0]).toUpperCase(),"",...commandNames))
		nevoSend(message, "Alternate Command Names for " + commandNames[1].names[0], ...commandNames);
	}
}, {description: "Used to find the alternate names for a command.", arguments: "CommandName"}, "a", "altfor");

newCommand("help", function(message, commandName){
	let command = getCommand(commandName?commandName:"");
	let m;

	if(command){
		m = ["HELP FOR " + command[1].names[0], "**Names**","\t"+command[1].names,"**Arguments**","\t"+command[1].arguments,"**Description:**","\t"+command[1].description];
	}

	else if (!commandName) {
		let list = [];
		cmds.forEach(cmd=>{
			list.push([cmd[1].names[0], "\t"+cmd[1].description]);
		})

		m = ["List of Commands:", ...list];
	}
	nevoSend(message, ...(m?m:["OOF","I made a mistake :("]));
},{description: "Used to get help with the bot or with specific commands.", arguments: "CommandName (Optional)"},"h", "whats")


newCommand("changePersona", function(message, name, pic){
	let k = Object.keys(Profiles)

	name = name?(name=="Default"?".ᑎᑌᗰᗩ":name):k[Math.floor(k.length*Math.random())]

	let pf = name==".ᑎᑌᗰᗩ"?defaultProfile:Profiles[name]
	let is = pf[3]

	if(!(pf[3])) return 0;

	let test = client.user.setAvatar("./Media/Avatars/"+(pic?pic:is[Math.floor(Math.random()*is.length)]));
	print("TEST:", test)

	//client.user.setUsername(name)
	let bot = message.guild.members.fetch('740013958106447882').then(user => user.setNickname(name))
	bot.catch()
	client.user.setActivity(pf[2])

	let role = message.guild.roles.fetch('740019521762361426').then(role => role.setName(pf[1])).then(role => role.setColor(pf[0]))
	role.catch()

	message.channel.send("Changing persona... o-o")
},{description: "who am i? am i not unique? maybe i'm not here at all", arguments: "PersonaName (Optional), AvatarName (Optional)", whitelist: true, cooldown: 30},"alt","PERSONA!")


newCommand("ping", function(message){
	message.reply('pong')
},{description: "PING PONG PING PONG PING", cooldown: 5}, "hey")