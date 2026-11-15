import logging


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            from .middleware import get_request_context

            record.request_id = get_request_context().get("request_id", "-")
        return True
