const Discord = require('discord.js');
const client = new Discord.Client();
const config = require('./config.json');

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
		client.user.setActivity('the stars weave into the umbra around me...', { type: 'WATCHING' });
		if (command) command[1](message, ...args);
	}
});

// Initialization for nevo
var prefix = [".", ".nevo ", config.prefix];
var cmds = [];
// cmds are {Names...}, Function

//example command: .sum 4, 1, 2, 3

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
	cmds.push([[name,...aliases], func, data])
};


function getCommand(name){
	let command;

	cmds.forEach(cma=>{
		cma[0].forEach(cName=>{
			if(name == cName){
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
		let commandNames = getCommand(commandName)[0];

		//message.channel.send(quote(encode("Alternate Command Names for " + commandNames[0]).toUpperCase(),"",...commandNames))
		nevoSend(message, "Alternate Command Names for " + commandNames[0], ...commandNames);
	}
}, {description: "Used to find the alternate names for a command.", args: "CommandName"}, "a", "alt");

newCommand("help", function(message, commandName){
	let command = getCommand(commandName?commandName:"");
	let m;
	if(command){
		m = ["HELP FOR " + command[0][0], "**Names**","\t"+command[0],"**Arguments**","\t"+command[2].args,"**Description:**","\t"+command[2].description];
	}
	else if (!commandName) {
		let list = [];
		cmds.forEach(cmd=>{
			list.push([cmd[0][0], "\t"+cmd[2].description]);
		})

		m = ["List of Commands:", ...list];
	}
	nevoSend(message, ...(m?m:["OOF","I made a mistake :("]));
},{description: "Used to get help with the bot or with specific commands.", args: "CommandName (Optional)"},"h", "whats")