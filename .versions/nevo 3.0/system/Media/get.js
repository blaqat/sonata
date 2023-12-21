//Media
const { readdirSync, statSync } = require('fs')
const { join } = require('path')
const media = {}
const base = "system/Media"

const path = (...p) => {return "./"+p.join("/")}
const getDirectories = p => readdirSync(p).filter(f => statSync(join(p, f)).isDirectory())

const medFiles = getDirectories(base)

for(const medName of medFiles){
    const files = readdirSync(path(base, medName))
    const med = []

    for(const fileName of files){
        med.push(path(base, medName, fileName))
    }

    media[medName] = med
}

const get = function(type, name){
    type = media[type + "s"]
    if(type){
        for(const path of type){
            if(path.toLowerCase().includes(name.toLowerCase()))
                return path
        }
    }

    return "???"
}


module.exports = get