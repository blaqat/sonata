var request = require('request');

function findTrueUrl(url, callback){
    request({
        method: 'GET',
        url: url,
        followRedirect: false
    }, function(error, response, body){
        if(error){
            callback && callback(error);
        } else if(response.statusCode != 302 && response.statusCode != 301){
            callback && callback(response.statusCode);
        } else {
            callback && callback(error, response.headers['location']);
        }
    });
}

module.exports = findTrueUrl;
