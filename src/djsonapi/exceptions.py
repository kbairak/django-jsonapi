from functools import reduce


def _class_name_to_title(text):
    result = "".join((f" {char.lower()}" if char.isupper() else char for char in text))
    if result.startswith(" "):
        result = result[1:]
    result = "".join((result[:1].upper(), result[1:]))
    return result


def _class_name_to_code(text):
    result = "".join((f"_{char.lower()}" if char.isupper() else char for char in text))
    if result.startswith("_"):
        result = result[1:]
    return result


class DjsonApiException(Exception):
    def render(self):
        raise NotImplementedError()

    @property
    def status(self):
        raise NotImplementedError()


class DjsonApiExceptionSingle(DjsonApiException):
    STATUS = 500
    CODE = None
    TITLE = None
    DETAIL = "Something went wrong"
    SOURCE = None

    def __init__(self, detail=None, title=None, source=None):
        if detail is None:
            detail = self.DETAIL
        if title is None:
            if self.TITLE is None:
                title = _class_name_to_title(self.__class__.__name__)
            else:
                title = self.TITLE
        if source is None:
            source = self.SOURCE
        super().__init__(title, detail, source)

    def render(self):
        status = str(self.STATUS)
        code = self.CODE
        if code is None:
            code = _class_name_to_code(self.__class__.__name__)

        title, detail, source = self.args

        result = {
            "status": status,
            "code": code,
            "title": title,
            "detail": detail,
        }
        if source is not None:
            result["source"] = source

        return [result]

    @property
    def status(self):
        return int(self.STATUS)

    title = property(
        fget=lambda self: self.args[0], fset=lambda self, value: self._set(0, value)
    )
    detail = property(
        fget=lambda self: self.args[1], fset=lambda self, value: self._set(1, value)
    )
    source = property(
        fget=lambda self: self.args[2], fset=lambda self, value: self._set(2, value)
    )

    def _set(self, pos, value):
        args = list(self.args)
        args[pos] = value
        self.args = tuple(args)


class DjsonApiExceptionMulti(DjsonApiException):
    def render(self):
        return reduce(list.__add__, (arg.render() for arg in self.args), [])

    @property
    def status(self):
        statuses = {exc.status for exc in self.args}
        if len(statuses) == 1:
            return statuses.pop()
        statuses = {(status // 100) * 100 for status in statuses}
        return max(statuses)


class InternalServerError(DjsonApiExceptionSingle):
    pass


class BadRequest(DjsonApiExceptionSingle):
    STATUS = 400


class Unauthorized(DjsonApiExceptionSingle):
    STATUS = 401


class Forbidden(DjsonApiExceptionSingle):
    STATUS = 403


class NotFound(DjsonApiExceptionSingle):
    STATUS = 404


class MethodNotAllowed(DjsonApiExceptionSingle):
    STATUS = 405


class Conflict(DjsonApiExceptionSingle):
    STATUS = 409


class TooManyRequests(DjsonApiExceptionSingle):
    STATUS = 429


class UnsupportedMediaType(DjsonApiExceptionSingle):
    STATUS = 415


class NotAcceptable(DjsonApiExceptionSingle):
    STATUS = 406
