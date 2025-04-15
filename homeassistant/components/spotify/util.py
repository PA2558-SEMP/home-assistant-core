"""Utils for Spotify."""

from __future__ import annotations

from typing import Any

import yarl

from homeassistant.components.media_player import MediaPlayerQueueItem

from .const import MEDIA_PLAYER_PREFIX


def is_spotify_media_type(media_content_type: str) -> bool:
    """Return whether the media_content_type is a valid Spotify media_id."""
    return media_content_type.startswith(MEDIA_PLAYER_PREFIX)


def resolve_spotify_media_type(media_content_type: str) -> str:
    """Return actual spotify media_content_type."""
    return media_content_type.removeprefix(MEDIA_PLAYER_PREFIX)


def fetch_image_url(item: dict[str, Any], key="images") -> str | None:
    """Fetch image url."""
    source = item.get(key, [])
    if isinstance(source, list) and source:
        return source[0].get("url")
    return None


def spotify_uri_from_media_browser_url(media_content_id: str) -> str:
    """Extract spotify URI from media browser URL."""
    if media_content_id and media_content_id.startswith(MEDIA_PLAYER_PREFIX):
        parsed_url = yarl.URL(media_content_id)
        media_content_id = parsed_url.name
    return media_content_id


def format_queue(
    spotify_queue_response: dict[str, Any] | None,
) -> list[MediaPlayerQueueItem]:
    """Format the queue response."""

    if spotify_queue_response is None:
        return []

    unfiltered_queue = spotify_queue_response.get("queue", [])

    return [
        {
            "media_title": item.get("name", None),
            "media_type": item.get("type", None),
            "media_id": item.get("id", None),
            "image": item.get("album", {}).get("images", [{}])[0].get("url", None),
            "href": item.get("href", None),
            "duration_ms": item.get("duration_ms", None),
            "media_creators": [
                {
                    "name": creator.get("name", None),
                    "id": creator.get("id", None),
                    "creator_type": creator.get("type", None),
                }
                for creator in item.get("artists", [])
            ]
            or None,
        }
        for item in unfiltered_queue
    ]
