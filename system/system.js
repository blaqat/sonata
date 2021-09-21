//System
const { readdirSync, statSync } = require('fs')
const { join } = require('path')
const numa = {}
const base = "system"

numa.config = require('./config')

const path = (...p) => {return "./"+p.join("/")}
const getDirectories = p => readdirSync(p).filter(f => statSync(join(p, f)).isDirectory())

const sysFiles = getDirectories(base)

for(const sysName of sysFiles){
    const files = readdirSync(path(base, sysName)).filter(file => file.endsWith('.js'))
    const sys = {}

    for(const fileName of files){
        sys[fileName.slice(0, -3)] = require(path(sysName, fileName))
    }

    numa[sysName] = sys
}

numa.config.prefix = new numa.Classes.Alias("hey numa,", ...numa.config.prefix)

module.exports = numa