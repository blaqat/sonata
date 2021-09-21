var shortenedUrlResolver = require('../index.js');
var expect = require('chai').expect;

describe('Short urls', function(){


    var urls = [
        {
            shortenedUrl: 'http://bit.ly/1Sd9m5Z',
            name: 'bit.ly',
            url: 'https://app.brazenconnect.com/events/sans-cybertalent-fair-may2016?&jobAlias=issa&variant=socialmedia'
        },
        {
            shortenedUrl: 'http://ow.ly/4mPP5S',
            name: 'ow.ly',
            url: 'http://www.darkreading.com/endpoint/8-active-apt-groups-to-watch/d/d-id/1325161'
        },
        {
            shortenedUrl: 'http://goo.gl/alerts/4JGvW',
            name: 'goo.gl',
            url: 'https://www.washingtonpost.com/news/the-switch/wp/2016/04/19/box-ceo-why-the-latest-attempt-by-congress-on-cybersecurity-is-already-outdated/'
        },
        {
            shortenedUrl: 'http://ift.tt/20UZLod',
            name: 'ift.tt',
            url: 'http://www.isaca.org/About-ISACA/Press-room/News-Releases/2016/Pages/ISACA-New-Cybersecurity-Boot-Camp-Coming-to-New-York.aspx'
        },
        {
            shortenedUrl: 'http://tinyurl.com/KindleWireless',
            name: 'tinyurl.com',
            url: 'http://www.amazon.com/Kindle-Wireless-Reading-Display-Globally/dp/B003FSUDM4/ref=amb_link_353259562_2?pf_rd_m=ATVPDKIKX0DER&pf_rd_s=center-10&pf_rd_r=11EYKTN682A79T370AM3&pf_rd_t=201&pf_rd_p=1270985982&pf_rd_i=B002Y27P3M'
        },
        {
            shortenedUrl: 'http://dlvr.it/L5CVTw',
            name: 'dlvr.it',
            url: 'http://www.securityweek.com/google-tightens-security-rules-chrome-extensions?utm_source=dlvr.it&utm_medium=twitter'
        },
        {
            shortenedUrl: 'http://nr.tn/1WEhn7s',
            name: 'nr.tn',
            url: 'https://community.norton.com/en/blogs/norton-protection-blog/10-facts-about-todays-cybersecurity-landscape-you-should-know?om_ext_cid=hho_ext_social__SYMGlobal_RTM_TWITTER_Norton Protection Blog&linkId=23617224'
        }
    ];

    urls.forEach(function(url){
        it(url.name, function(done){
            shortenedUrlResolver(url.shortenedUrl, function(error, newUrl){
                expect(error).to.be.null;
                expect(newUrl).to.be.equal(url.url);
                done();
            });
        });

    });
});

describe('Not short urls', function(){
    
    it('google.fr', function(done){
        shortenedUrlResolver('https://www.google.fr', function(error, newUrl){
            expect(error).to.be.equal(200);
            done();
        });
        
    });
});

