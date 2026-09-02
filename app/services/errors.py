class ApplicationError(Exception):
    """An error safe to show to the user."""


class ValidationError(ApplicationError):
    pass


class DependencyError(ApplicationError):
    pass


class NotFoundError(ApplicationError):
    pass


class AccessDeniedError(ApplicationError):
    pass

