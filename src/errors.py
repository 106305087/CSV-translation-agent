class UserFacingError(Exception):
    """Shown directly to the user in the chat interface."""
    pass


class RecoverableError(UserFacingError):
    """Triggers retry logic before surfacing to the user."""
    pass
