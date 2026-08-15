from app.core.exceptions import TPCCoreException


class ProxiesException(TPCCoreException): ...


class ProxyConnectException(TPCCoreException):
    msg_template = "Cannot connect to proxy server {server} on port {port}"
