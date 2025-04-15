from unittest.mock import Mock  # noqa: D100

import pytest

from homeassistant.components.spotify.media_player import SpotifyMediaPlayer
from homeassistant.components.spotify.util import format_queue


@pytest.fixture
def mock_spotify_data():
    """Mock HomeAssistantSpotifyData with fake data."""

    mock_data = Mock()
    mock_data.current_user = {"product": "premium"}

    mock_data.client = Mock()
    return mock_data


@pytest.fixture
def mock_raw_queue():
    """Provide raw queue data from thr spotify web api to be used for testing."""
    return {
        "queue": [
            {
                "album": {
                    "album_type": "single",
                    "total_tracks": 1,
                    "href": "https://api.spotify.com/v1/albums/test",
                    "id": "test",
                    "name": "test song",
                    "release_date": "2024-10-11",
                    "release_date_precision": "day",
                    "type": "album",
                    "uri": "spotify:album:test",
                    "artists": [
                        {
                            "external_urls": {
                                "spotify": "https://open.spotify.com/artist/test"
                            },
                            "href": "https://api.spotify.com/v1/artists/test",
                            "id": "test",
                            "name": "testArtist",
                            "type": "artist",
                            "uri": "spotify:artist:test",
                        },
                        {
                            "external_urls": {
                                "spotify": "https://open.spotify.com/artist/test"
                            },
                            "href": "https://api.spotify.com/v1/artists/test",
                            "id": "test",
                            "name": "testArtist2",
                            "type": "artist",
                            "uri": "spotify:artist:test",
                        },
                    ],
                },
                "artists": [
                    {
                        "href": "https://api.spotify.com/v1/artists/test",
                        "id": "test",
                        "name": "testArtist",
                        "type": "artist",
                        "uri": "spotify:artist:test",
                    },
                    {
                        "external_urls": {
                            "spotify": "https://open.spotify.com/artist/test"
                        },
                        "href": "https://api.spotify.com/v1/artists/test",
                        "id": "test",
                        "name": "testArtist2",
                        "type": "artist",
                        "uri": "spotify:artist:test",
                    },
                ],
                "available_markets": [
                    "NONE",
                ],
                "href": "https://api.spotify.com/v1/tracks/test",
                "id": "test",
                "name": "test song",
                "popularity": 60,
                "track_number": 1,
                "type": "track",
                "uri": "spotify:track:test",
            },
        ]
    }


def test_media_queue(
    mock_spotify_data: Mock, mock_raw_queue: dict[str, list[dict[str, str | int]]]
) -> None:
    """Test the SpotifyMediaPlayer media queue formatting."""
    mock_spotify_data.client.queue.return_value = mock_raw_queue

    media_player = SpotifyMediaPlayer(
        data=mock_spotify_data,
        user_id="mock_user_id",
        name="Mock User",
    )

    formatted_queue = media_player._queue = format_queue(
        mock_spotify_data.client.queue()
    )

    assert formatted_queue[0]["media_title"] == "test song"
