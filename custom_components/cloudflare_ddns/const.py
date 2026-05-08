DOMAIN = "cloudflare_ddns"

CONF_API_TOKEN = "api_token"
CONF_ZONE_NAME = "zone_name"
CONF_ZONE_ID = "zone_id"
CONF_RECORD_NAME = "record_name"
CONF_UPDATE_IPV4 = "update_ipv4"
CONF_UPDATE_IPV6 = "update_ipv6"
CONF_CUSTOM_IPV4_URLS = "custom_ipv4_urls"
CONF_CUSTOM_IPV6_URLS = "custom_ipv6_urls"

CF_BASE = "https://api.cloudflare.com/client/v4"

IPV4_SOURCES = [
    "https://myip4.ipip.net",
    "https://ddns.oray.com/checkip",
    "https://ip.3322.net",
    "https://4.ipw.cn",
]

IPV6_SOURCES = [
    "https://api64.ipify.org?format=json",
    "https://speed.neu6.edu.cn/getIP.php",
    "https://v6.ident.me",
    "https://6.ipw.cn",
    "https://v6.yinghualuo.cn/bejson",
]

UPDATE_INTERVAL_MINUTES = 5
