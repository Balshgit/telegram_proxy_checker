from app.core.exceptions import TPCCoreException


class ProxySourceNotFoundException(TPCCoreException):
    msg_template = "Proxies source with id {proxy_source_id} not found"
