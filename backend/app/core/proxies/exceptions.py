from app.core.exceptions import TPCCoreException


class ProxiesException(TPCCoreException): ...


class ProxyConnectException(TPCCoreException):
    msg_template = "Cannot connect to proxy server {server} on port {port}"


class ProxyNotFoundException(TPCCoreException):
    msg_template = "Proxy with id {proxy_id} not found"


class NoProxiesAddedException(TPCCoreException):
    msg_template = "No proxies to add"
