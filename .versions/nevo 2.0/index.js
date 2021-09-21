const testMode = false
global.numa;

//Functions
process.on('unhandledRejection', error => console.error('Uncaught Promise Rejection', error));
const print = console.log
const mod = (n, m) => {
    return ((n % m) + m) % m;
}
global.unitConvertor = (x, div) => {
    return [Math.floor(x/div), Math.floor(x%div)]
}


//Requires
const Discord = require('discord.js')
const config = require('./config.js')
const fs = require('fs')
const box = require("./BeepboxAPI/main.js")
global.box = box
//Testing
if(testMode){


let id = `https://jummbus.bitbucket.io/1_2/#j1N07Unnamedn31s0k0l00e03t2Cm0a7g0fj07i0r1o3310T6v0pub8q1L0Od2f8y2z9C0c0WN5T0v0pu00q0L0Od0f6y0z1C2w2c0h0T0v0pu00q2L0Od0f8y0z1C0w2c0h0T4v0puf0q1L0Oz6666ji8k8k3jSBKSJJAArriiiiii07JCABrzrrrrrrr00YrkqHrsrrrrjr005zrAqzrjzrrqr1jRjrqGGrrzsrsA099ijrABJJJIAzrrtirqrqjqixzsrAjrqjiqaqqysttAJqjikikrizrHtBJJAzArzrIsRCITKSS099ijrAJS____Qg99habbCAYrDzh00b4zg00000000id0000000018i000000004h400000000p21UFBWy1jdslBlobOGEozj8ZJdddejr8Wrri-CKij8RR6z64qp7ojf8N8jzSp7y6yeCjwWV8ZcD1Od4tcD1Q1AuyjPKqZC4tcAt54td71xs3FZ0tl0yorbHTg00`


const BeepboxSong = new box.Song(`https://jummbus.bitbucket.io/1_2/#j1N07Unnamedn31s0k0l00e03t2Cm0a7g0fj07i0r1o3310T6v0pub8q1L0Od2f8y2z9C0c0WN5T0v0pu00q0L0Od0f6y0z1C2w2c0h0T0v0pu00q2L0Od0f8y0z1C0w2c0h0T4v0puf0q1L0Oz6666ji8k8k3jSBKSJJAArriiiiii07JCABrzrrrrrrr00YrkqHrsrrrrjr005zrAqzrjzrrqr1jRjrqGGrrzsrsA099ijrABJJJIAzrrtirqrqjqixzsrAjrqjiqaqqysttAJqjikikrizrHtBJJAzArzrIsRCITKSS099ijrAJS____Qg99habbCAYrDzh00b4zg00000000id0000000018i000000004h400000000p21UFBWy1jdslBlobOGEozj8ZJdddejr8Wrri-CKij8RR6z64qp7ojf8N8jzSp7y6yeCjwWV8ZcD1Od4tcD1Q1AuyjPKqZC4tcAt54td71xs3FZ0tl0yorbHTg00`)
const [min, sec] = unitConvertor(BeepboxSong.duration, 60)

print("Title: ",BeepboxSong.title, ` | Duration: ${min>0?"":min} mins and ${sec} seconds`)

let a = ()=> {
    BeepboxSong.loadBuffer().then(passed => {
    let stream = BeepboxSong.stream
    const numa = new Discord.Client()

    numa.once('ready', () => {
        console.log('Ready!')
    });
    
    numa.login(config.token);
    
    numa.on('message', message => {
        if (message.content === '!play test') {
            if (message.channel.type === 'dm') return;
    
            const voiceChannel = message.member.voice.channel;
    
            if (!voiceChannel) {
                return message.reply('please join a voice channel first!');
            }
            voiceChannel.join().then(connection => {
                const dispatcher = connection.play(stream);
    
                dispatcher.on('finish', () => voiceChannel.leave());
            });
        }
   });})
}

a()

}

if(!testMode){
//Instantion
const numa = new Discord.Client()
global.numa = numa
const {prefix, token, ids} = config
const cmdFiles = fs.readdirSync('./Commands').filter(file => file.endsWith('.js'))
const classFiles = fs.readdirSync('./Classes').filter(file => file.endsWith('.js'))

//Message Parsing
function checkCommandArgument(arg){
    return arg
    //return storage.has(arg) && storage.get(arg).args.join(" ") || arg
  }
  
function getCommand(message){
    message = message.trim()
    let cmd = [], ifd = []

    for( const [id, val] of ids.entries() ){
        if(message.includes(id)){
            message = message.split(id)
            ifd.push({data:val,args:[message.pop().trim()]})
            message = message.join("")
        }
    }

    message = message.trim()
    message = message.split(" ")
    
    for( const [_, command] of numa.cmds.entries()){
        if(prefix.includes(message[0]) && command.alias.includes(message[1])){
        //command.execute(bot, ...message.slice(2))
        cmd = {data:command, args:message.slice(2).join(" ").trim().split(" ").map(arg => checkCommandArgument(arg)), namecall:message[1]}
        break
        }
        else {
            cmd = false
        }
    }

    return {main:cmd, sub:ifd, execute: function(bot){
        let main = this.main
        if(!main)
            return false
        this.sub.forEach(cmd => {
            cmd.data.execute(bot, this, ...cmd.args)
        })
        main.data.execute(bot, main, ...main.args)
        return true
    }}
}

numa.getCommand = getCommand
async function exeCommand(bot, command, args){
    return command.execute(bot, command, ...args)
}



//Beep Bot
numa.cmds = new Discord.Collection()
numa.classes = new Discord.Collection()

for (const file of cmdFiles){
    let cmd = require("./Commands/"+file)
    numa.cmds.set(cmd.alias[0], cmd)
}

for (const file of classFiles){
    let cls = require("./Classes/"+file)
    numa.classes.set(file.slice(0,-3), cls)
}

numa.once('ready', () => {
	console.log('Ready!')
});

numa.login(token);

numa.on('message', message => {
    let base = getCommand(message.content)

    if(base.execute(message))
        print(base.main.data.alias[0], " has been executed.")
    else
        return 1
        //print(message.content, " is not a correct command.")
});

}