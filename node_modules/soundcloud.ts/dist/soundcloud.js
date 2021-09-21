"use strict";
function __export(m) {
    for (var p in m) if (!exports.hasOwnProperty(p)) exports[p] = m[p];
}
exports.__esModule = true;
var API_1 = require("./API");
var index_1 = require("./entities/index");
var publicID = "BeGVhOrGmfboy1LtiHTQF6Ejpt9ULJCI";
/**
 * The main class for interacting with the Soundcloud API.
 */
var Soundcloud = /** @class */ (function () {
    function Soundcloud(clientID, oauthToken) {
        this.api = new API_1["default"](Soundcloud.clientID, Soundcloud.oauthToken);
        this.tracks = new index_1.Tracks(this.api);
        this.users = new index_1.Users(this.api);
        this.playlists = new index_1.Playlists(this.api);
        this.oembed = new index_1.Oembed(this.api);
        this.resolve = new index_1.Resolve(this.api);
        this.me = new index_1.Me(this.api);
        this.comments = new index_1.Comments(this.api);
        this.apps = new index_1.Apps(this.api);
        this.util = new index_1.Util(this.api);
        if (clientID) {
            Soundcloud.clientID = clientID;
            if (oauthToken)
                Soundcloud.oauthToken = oauthToken;
        }
        else {
            Soundcloud.clientID = publicID;
        }
        this.api = new API_1["default"](Soundcloud.clientID, Soundcloud.oauthToken);
        this.tracks = new index_1.Tracks(this.api);
        this.users = new index_1.Users(this.api);
        this.playlists = new index_1.Playlists(this.api);
        this.oembed = new index_1.Oembed(this.api);
        this.resolve = new index_1.Resolve(this.api);
        this.me = new index_1.Me(this.api);
        this.comments = new index_1.Comments(this.api);
        this.apps = new index_1.Apps(this.api);
        this.util = new index_1.Util(this.api);
    }
    return Soundcloud;
}());
exports["default"] = Soundcloud;
module.exports["default"] = Soundcloud;
__export(require("./entities/index"));
