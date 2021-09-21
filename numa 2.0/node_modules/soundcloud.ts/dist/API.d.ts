export default class API {
    clientID: string;
    oauthToken: string;
    static headers: {
        "user-agent": string;
    };
    constructor(clientID: string, oauthToken: string);
    /**
     * Gets an endpoint from the Soundcloud API.
     */
    get: (endpoint: string, params?: any) => Promise<any>;
    /**
     * Gets an endpoint from the Soundcloud V2 API.
     */
    getV2: (endpoint: string, params?: any) => Promise<any>;
    /**
     * Some endpoints use the main website as the URL.
     */
    getWebsite: (endpoint: string, params?: any) => Promise<any>;
    /**
     * Gets a URI, such as download, stream, attachment, etc.
     */
    getURI: (URI: string, params?: any) => Promise<import("axios").AxiosResponse<any>>;
    post: (endpoint: string, params?: any) => Promise<any>;
    put: (endpoint: string, params?: any) => Promise<any>;
    delete: (endpoint: string, params?: any) => Promise<any>;
}
