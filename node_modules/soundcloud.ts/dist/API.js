"use strict";
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __generator = (this && this.__generator) || function (thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g;
    return g = { next: verb(0), "throw": verb(1), "return": verb(2) }, typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (_) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
};
exports.__esModule = true;
var axios_1 = require("axios");
var apiURL = "https://api.soundcloud.com/";
var apiV2URL = "https://api-v2.soundcloud.com/";
var webURL = "https://www.soundcloud.com/";
var API = /** @class */ (function () {
    function API(clientID, oauthToken) {
        var _this = this;
        this.clientID = clientID;
        this.oauthToken = oauthToken;
        /**
         * Gets an endpoint from the Soundcloud API.
         */
        this.get = function (endpoint, params) { return __awaiter(_this, void 0, void 0, function () {
            var response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        if (!params)
                            params = {};
                        params.client_id = this.clientID;
                        if (this.oauthToken)
                            params.oauth_token = this.oauthToken;
                        if (endpoint.startsWith("/"))
                            endpoint = endpoint.slice(1);
                        endpoint = apiURL + endpoint;
                        return [4 /*yield*/, axios_1["default"].get(endpoint, { params: params, headers: API.headers }).then(function (r) { return r.data; })];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, response];
                }
            });
        }); };
        /**
         * Gets an endpoint from the Soundcloud V2 API.
         */
        this.getV2 = function (endpoint, params) { return __awaiter(_this, void 0, void 0, function () {
            var response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        if (!params)
                            params = {};
                        params.client_id = this.clientID;
                        if (this.oauthToken)
                            params.oauth_token = this.oauthToken;
                        if (endpoint.startsWith("/"))
                            endpoint = endpoint.slice(1);
                        endpoint = apiV2URL + endpoint;
                        return [4 /*yield*/, axios_1["default"].get(endpoint, { params: params, headers: API.headers }).then(function (r) { return r.data; })];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, response];
                }
            });
        }); };
        /**
         * Some endpoints use the main website as the URL.
         */
        this.getWebsite = function (endpoint, params) { return __awaiter(_this, void 0, void 0, function () {
            var response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        if (!params)
                            params = {};
                        params.client_id = this.clientID;
                        if (this.oauthToken)
                            params.oauth_token = this.oauthToken;
                        if (endpoint.startsWith("/"))
                            endpoint = endpoint.slice(1);
                        endpoint = webURL + endpoint;
                        return [4 /*yield*/, axios_1["default"].get(endpoint, { params: params, headers: API.headers }).then(function (r) { return r.data; })];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, response];
                }
            });
        }); };
        /**
         * Gets a URI, such as download, stream, attachment, etc.
         */
        this.getURI = function (URI, params) { return __awaiter(_this, void 0, void 0, function () {
            return __generator(this, function (_a) {
                if (!params)
                    params = {};
                params.client_id = this.clientID;
                if (this.oauthToken)
                    params.oauth_token = this.oauthToken;
                return [2 /*return*/, axios_1["default"].get(URI, { params: params, headers: API.headers })];
            });
        }); };
        this.post = function (endpoint, params) { return __awaiter(_this, void 0, void 0, function () {
            var response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        if (!params)
                            params = {};
                        params.client_id = this.clientID;
                        if (this.oauthToken)
                            params.oauth_token = this.oauthToken;
                        if (endpoint.startsWith("/"))
                            endpoint = endpoint.slice(1);
                        endpoint = apiURL + endpoint;
                        return [4 /*yield*/, axios_1["default"].post(endpoint, { params: params, headers: API.headers }).then(function (r) { return r.data; })];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, response];
                }
            });
        }); };
        this.put = function (endpoint, params) { return __awaiter(_this, void 0, void 0, function () {
            var response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        if (!params)
                            params = {};
                        params.client_id = this.clientID;
                        if (this.oauthToken)
                            params.oauth_token = this.oauthToken;
                        if (endpoint.startsWith("/"))
                            endpoint = endpoint.slice(1);
                        endpoint = apiURL + endpoint;
                        return [4 /*yield*/, axios_1["default"].put(endpoint, { params: params, headers: API.headers }).then(function (r) { return r.data; })];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, response];
                }
            });
        }); };
        this["delete"] = function (endpoint, params) { return __awaiter(_this, void 0, void 0, function () {
            var response;
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0:
                        if (!params)
                            params = {};
                        params.client_id = this.clientID;
                        if (this.oauthToken)
                            params.oauth_token = this.oauthToken;
                        if (endpoint.startsWith("/"))
                            endpoint = endpoint.slice(1);
                        endpoint = apiURL + endpoint;
                        return [4 /*yield*/, axios_1["default"]["delete"](endpoint, { params: params, headers: API.headers }).then(function (r) { return r.data; })];
                    case 1:
                        response = _a.sent();
                        return [2 /*return*/, response];
                }
            });
        }); };
    }
    API.headers = { "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36" };
    return API;
}());
exports["default"] = API;
