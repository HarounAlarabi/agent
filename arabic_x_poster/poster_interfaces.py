"""Posting abstractions."""

from abc import ABC, abstractmethod

class TweetPoster(ABC):
    """Post a single tweet and return its ID."""

    @abstractmethod
    def post(
        self,
        text: str,
        reply_to_id: str | None = None,
        image_path: str | None = None,
    ) -> str: ...

class ThreadablePoster(TweetPoster, ABC):
    """Extends TweetPoster with native thread-posting support.

    I: Only implementations that can post threads implement this interface.
       ThreadPostingService checks isinstance rather than hasattr.
    """

    @abstractmethod
    def post_thread(
        self,
        tweets: list[str],
        source_url: str | None = None,
        first_image_path: str | None = None,
    ) -> list[str]: ...
