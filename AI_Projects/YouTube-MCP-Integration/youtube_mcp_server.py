#!/usr/bin/env python3
"""
YouTube Channel Management MCP Server
A Model Context Protocol server for managing YouTube channels via the YouTube Data API v3.

Author: Obi1 (Hackerobi)
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

# MCP SDK
from mcp.server.fastmcp import FastMCP

# Google API
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# Logging (stderr so it doesn't interfere with MCP stdio)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [YouTube-MCP] %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("youtube-mcp")

# ---------------------------------------------------------------------------
# YouTube API client
# ---------------------------------------------------------------------------
API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
if not API_KEY:
    log.error("YOUTUBE_API_KEY environment variable is not set!")

def get_youtube_client():
    """Build and return a YouTube Data API v3 client."""
    return build("youtube", "v3", developerKey=API_KEY)

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP("YouTube Channel Manager")


# ===========================
# CHANNEL TOOLS
# ===========================

@mcp.tool()
def get_channel_info(channel_id: str = "", username: str = "", handle: str = "") -> str:
    """
    Get detailed information about a YouTube channel.
    Provide ONE of: channel_id (UC...), username, or handle (@handle).
    Returns subscriber count, view count, video count, description, and more.
    """
    try:
        youtube = get_youtube_client()
        params = {"part": "snippet,statistics,brandingSettings,contentDetails"}
        
        if channel_id:
            params["id"] = channel_id
        elif username:
            params["forUsername"] = username
        elif handle:
            search = youtube.search().list(
                part="snippet", q=handle, type="channel", maxResults=1
            ).execute()
            if search.get("items"):
                params["id"] = search["items"][0]["snippet"]["channelId"]
            else:
                return json.dumps({"error": f"No channel found for handle: {handle}"})
        else:
            return json.dumps({"error": "Provide channel_id, username, or handle"})

        response = youtube.channels().list(**params).execute()
        
        if not response.get("items"):
            return json.dumps({"error": "Channel not found"})

        channel = response["items"][0]
        snippet = channel.get("snippet", {})
        stats = channel.get("statistics", {})
        branding = channel.get("brandingSettings", {}).get("channel", {})
        content = channel.get("contentDetails", {})

        result = {
            "channel_id": channel["id"],
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "custom_url": snippet.get("customUrl", ""),
            "published_at": snippet.get("publishedAt", ""),
            "country": snippet.get("country", "N/A"),
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            "statistics": {
                "subscribers": stats.get("subscriberCount", "hidden"),
                "total_views": stats.get("viewCount", "0"),
                "total_videos": stats.get("videoCount", "0"),
            },
            "keywords": branding.get("keywords", ""),
            "uploads_playlist": content.get("relatedPlaylists", {}).get("uploads", ""),
        }
        return json.dumps(result, indent=2)

    except HttpError as e:
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {e.content.decode()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_channel_videos(
    channel_id: str,
    max_results: int = 10,
    order: str = "date",
    published_after: str = "",
    published_before: str = "",
) -> str:
    """
    List videos from a YouTube channel.
    
    Args:
        channel_id: The YouTube channel ID (UC...)
        max_results: Number of videos to return (1-50, default 10)
        order: Sort order - 'date', 'viewCount', 'rating', 'title' (default 'date')
        published_after: Filter videos after this date (ISO 8601, e.g. '2025-01-01T00:00:00Z')
        published_before: Filter videos before this date (ISO 8601)
    """
    try:
        youtube = get_youtube_client()
        max_results = min(max(1, max_results), 50)

        params = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": order,
            "maxResults": max_results,
        }
        if published_after:
            params["publishedAfter"] = published_after
        if published_before:
            params["publishedBefore"] = published_before

        search_response = youtube.search().list(**params).execute()
        video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]

        if not video_ids:
            return json.dumps({"videos": [], "total_results": 0})

        videos_response = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids),
        ).execute()

        videos = []
        for video in videos_response.get("items", []):
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})
            videos.append({
                "video_id": video["id"],
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:200] + "...",
                "published_at": snippet.get("publishedAt", ""),
                "duration": video.get("contentDetails", {}).get("duration", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "statistics": {
                    "views": stats.get("viewCount", "0"),
                    "likes": stats.get("likeCount", "0"),
                    "comments": stats.get("commentCount", "0"),
                },
            })

        return json.dumps({
            "channel_id": channel_id,
            "video_count": len(videos),
            "total_results": search_response.get("pageInfo", {}).get("totalResults", 0),
            "videos": videos,
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {e.content.decode()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ===========================
# VIDEO TOOLS
# ===========================

@mcp.tool()
def get_video_details(video_id: str) -> str:
    """
    Get comprehensive details for a specific YouTube video.
    Includes title, description, statistics, tags, category, and more.
    """
    try:
        youtube = get_youtube_client()
        response = youtube.videos().list(
            part="snippet,statistics,contentDetails,status,topicDetails",
            id=video_id,
        ).execute()

        if not response.get("items"):
            return json.dumps({"error": f"Video not found: {video_id}"})

        video = response["items"][0]
        snippet = video.get("snippet", {})
        stats = video.get("statistics", {})
        content = video.get("contentDetails", {})
        status = video.get("status", {})

        result = {
            "video_id": video["id"],
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "channel_id": snippet.get("channelId", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt", ""),
            "tags": snippet.get("tags", []),
            "category_id": snippet.get("categoryId", ""),
            "thumbnail": snippet.get("thumbnails", {}).get("maxres", 
                         snippet.get("thumbnails", {}).get("high", {})).get("url", ""),
            "duration": content.get("duration", ""),
            "definition": content.get("definition", ""),
            "caption": content.get("caption", "false"),
            "statistics": {
                "views": stats.get("viewCount", "0"),
                "likes": stats.get("likeCount", "0"),
                "comments": stats.get("commentCount", "0"),
                "favorites": stats.get("favoriteCount", "0"),
            },
            "status": {
                "privacy": status.get("privacyStatus", ""),
                "license": status.get("license", ""),
                "embeddable": status.get("embeddable", False),
                "made_for_kids": status.get("madeForKids", False),
            },
            "topics": video.get("topicDetails", {}).get("topicCategories", []),
        }
        return json.dumps(result, indent=2)

    except HttpError as e:
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {e.content.decode()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_video_comments(
    video_id: str,
    max_results: int = 20,
    order: str = "relevance",
) -> str:
    """
    Get comments on a YouTube video.
    """
    try:
        youtube = get_youtube_client()
        max_results = min(max(1, max_results), 100)

        response = youtube.commentThreads().list(
            part="snippet,replies",
            videoId=video_id,
            order=order,
            maxResults=max_results,
            textFormat="plainText",
        ).execute()

        comments = []
        for item in response.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            thread = {
                "comment_id": item["id"],
                "author": top.get("authorDisplayName", ""),
                "author_channel_id": top.get("authorChannelId", {}).get("value", ""),
                "text": top.get("textDisplay", ""),
                "likes": top.get("likeCount", 0),
                "published_at": top.get("publishedAt", ""),
                "updated_at": top.get("updatedAt", ""),
                "reply_count": item["snippet"].get("totalReplyCount", 0),
            }

            if item.get("replies"):
                thread["replies"] = []
                for reply in item["replies"]["comments"]:
                    r = reply["snippet"]
                    thread["replies"].append({
                        "author": r.get("authorDisplayName", ""),
                        "text": r.get("textDisplay", ""),
                        "likes": r.get("likeCount", 0),
                        "published_at": r.get("publishedAt", ""),
                    })

            comments.append(thread)

        return json.dumps({
            "video_id": video_id,
            "comment_count": len(comments),
            "total_results": response.get("pageInfo", {}).get("totalResults", 0),
            "comments": comments,
        }, indent=2)

    except HttpError as e:
        error_content = e.content.decode() if e.content else str(e)
        if "commentsDisabled" in error_content:
            return json.dumps({"error": "Comments are disabled on this video"})
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {error_content}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ===========================
# SEARCH TOOLS
# ===========================

@mcp.tool()
def search_youtube(
    query: str,
    max_results: int = 10,
    search_type: str = "video",
    order: str = "relevance",
    channel_id: str = "",
    published_after: str = "",
    region_code: str = "",
    video_duration: str = "",
) -> str:
    """
    Search YouTube for videos, channels, or playlists.
    """
    try:
        youtube = get_youtube_client()
        max_results = min(max(1, max_results), 50)

        params = {
            "part": "snippet",
            "q": query,
            "type": search_type,
            "order": order,
            "maxResults": max_results,
        }
        if channel_id:
            params["channelId"] = channel_id
        if published_after:
            params["publishedAfter"] = published_after
        if region_code:
            params["regionCode"] = region_code
        if video_duration and search_type == "video":
            params["videoDuration"] = video_duration

        response = youtube.search().list(**params).execute()

        results = []
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            result = {
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "channel_id": snippet.get("channelId", ""),
                "published_at": snippet.get("publishedAt", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            }
            
            id_info = item.get("id", {})
            if id_info.get("videoId"):
                result["video_id"] = id_info["videoId"]
                result["url"] = f"https://youtube.com/watch?v={id_info['videoId']}"
            elif id_info.get("channelId"):
                result["channel_id"] = id_info["channelId"]
                result["url"] = f"https://youtube.com/channel/{id_info['channelId']}"
            elif id_info.get("playlistId"):
                result["playlist_id"] = id_info["playlistId"]
                result["url"] = f"https://youtube.com/playlist?list={id_info['playlistId']}"

            results.append(result)

        if search_type == "video" and results:
            video_ids = [r["video_id"] for r in results if "video_id" in r]
            if video_ids:
                stats_response = youtube.videos().list(
                    part="statistics,contentDetails",
                    id=",".join(video_ids),
                ).execute()
                stats_map = {v["id"]: v for v in stats_response.get("items", [])}
                for r in results:
                    vid = r.get("video_id")
                    if vid and vid in stats_map:
                        s = stats_map[vid].get("statistics", {})
                        r["statistics"] = {
                            "views": s.get("viewCount", "0"),
                            "likes": s.get("likeCount", "0"),
                            "comments": s.get("commentCount", "0"),
                        }
                        r["duration"] = stats_map[vid].get("contentDetails", {}).get("duration", "")

        return json.dumps({
            "query": query,
            "result_count": len(results),
            "total_results": response.get("pageInfo", {}).get("totalResults", 0),
            "results": results,
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {e.content.decode()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ===========================
# PLAYLIST TOOLS
# ===========================

@mcp.tool()
def get_playlist_details(playlist_id: str) -> str:
    """
    Get details about a YouTube playlist.
    """
    try:
        youtube = get_youtube_client()
        response = youtube.playlists().list(
            part="snippet,contentDetails,status",
            id=playlist_id,
        ).execute()

        if not response.get("items"):
            return json.dumps({"error": f"Playlist not found: {playlist_id}"})

        playlist = response["items"][0]
        snippet = playlist.get("snippet", {})

        return json.dumps({
            "playlist_id": playlist["id"],
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "channel_id": snippet.get("channelId", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt", ""),
            "item_count": playlist.get("contentDetails", {}).get("itemCount", 0),
            "privacy": playlist.get("status", {}).get("privacyStatus", ""),
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {e.content.decode()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_playlist_items(playlist_id: str, max_results: int = 25) -> str:
    """
    Get all videos in a YouTube playlist.
    """
    try:
        youtube = get_youtube_client()
        max_results = min(max(1, max_results), 50)

        response = youtube.playlistItems().list(
            part="snippet,contentDetails,status",
            playlistId=playlist_id,
            maxResults=max_results,
        ).execute()

        items = []
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            items.append({
                "position": snippet.get("position", 0),
                "video_id": snippet.get("resourceId", {}).get("videoId", ""),
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:200],
                "channel_title": snippet.get("videoOwnerChannelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                "privacy": item.get("status", {}).get("privacyStatus", ""),
            })

        return json.dumps({
            "playlist_id": playlist_id,
            "item_count": len(items),
            "total_results": response.get("pageInfo", {}).get("totalResults", 0),
            "items": items,
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {e.content.decode()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_channel_playlists(channel_id: str, max_results: int = 25) -> str:
    """
    List all playlists for a YouTube channel.
    """
    try:
        youtube = get_youtube_client()
        max_results = min(max(1, max_results), 50)

        response = youtube.playlists().list(
            part="snippet,contentDetails,status",
            channelId=channel_id,
            maxResults=max_results,
        ).execute()

        playlists = []
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            playlists.append({
                "playlist_id": item["id"],
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:200],
                "published_at": snippet.get("publishedAt", ""),
                "item_count": item.get("contentDetails", {}).get("itemCount", 0),
                "privacy": item.get("status", {}).get("privacyStatus", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            })

        return json.dumps({
            "channel_id": channel_id,
            "playlist_count": len(playlists),
            "playlists": playlists,
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {e.content.decode()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ===========================
# ANALYTICS TOOLS
# ===========================

@mcp.tool()
def compare_videos(video_ids: str) -> str:
    """
    Compare statistics across multiple YouTube videos.
    """
    try:
        youtube = get_youtube_client()
        ids = [v.strip() for v in video_ids.split(",") if v.strip()]
        
        if not ids:
            return json.dumps({"error": "No video IDs provided"})
        if len(ids) > 50:
            return json.dumps({"error": "Maximum 50 videos can be compared"})

        response = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(ids),
        ).execute()

        videos = []
        for video in response.get("items", []):
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            
            engagement_rate = ((likes + comments) / views * 100) if views > 0 else 0

            videos.append({
                "video_id": video["id"],
                "title": snippet.get("title", ""),
                "published_at": snippet.get("publishedAt", ""),
                "duration": video.get("contentDetails", {}).get("duration", ""),
                "views": views,
                "likes": likes,
                "comments": comments,
                "engagement_rate": round(engagement_rate, 3),
                "likes_per_view": round(likes / views * 100, 3) if views > 0 else 0,
            })

        videos.sort(key=lambda x: x["views"], reverse=True)

        total_views = sum(v["views"] for v in videos)
        avg_views = total_views // len(videos) if videos else 0
        avg_engagement = sum(v["engagement_rate"] for v in videos) / len(videos) if videos else 0

        return json.dumps({
            "video_count": len(videos),
            "summary": {
                "total_views": total_views,
                "average_views": avg_views,
                "average_engagement_rate": round(avg_engagement, 3),
                "best_performing": videos[0]["title"] if videos else "",
                "worst_performing": videos[-1]["title"] if videos else "",
            },
            "videos": videos,
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {e.content.decode()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_trending_videos(
    region_code: str = "US",
    category_id: str = "",
    max_results: int = 10,
) -> str:
    """
    Get trending/popular videos for a region.
    """
    try:
        youtube = get_youtube_client()
        max_results = min(max(1, max_results), 50)

        params = {
            "part": "snippet,statistics,contentDetails",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": max_results,
        }
        if category_id:
            params["videoCategoryId"] = category_id

        response = youtube.videos().list(**params).execute()

        videos = []
        for video in response.get("items", []):
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})
            videos.append({
                "video_id": video["id"],
                "title": snippet.get("title", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
                "duration": video.get("contentDetails", {}).get("duration", ""),
                "url": f"https://youtube.com/watch?v={video['id']}",
                "statistics": {
                    "views": stats.get("viewCount", "0"),
                    "likes": stats.get("likeCount", "0"),
                    "comments": stats.get("commentCount", "0"),
                },
            })

        return json.dumps({
            "region": region_code,
            "category_id": category_id or "all",
            "video_count": len(videos),
            "videos": videos,
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {e.content.decode()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_video_categories(region_code: str = "US") -> str:
    """
    Get available YouTube video categories for a region.
    """
    try:
        youtube = get_youtube_client()
        response = youtube.videoCategories().list(
            part="snippet",
            regionCode=region_code,
        ).execute()

        categories = []
        for item in response.get("items", []):
            if item["snippet"].get("assignable", False):
                categories.append({
                    "id": item["id"],
                    "title": item["snippet"]["title"],
                })

        return json.dumps({
            "region": region_code,
            "categories": categories,
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {e.content.decode()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def channel_competitor_analysis(channel_ids: str) -> str:
    """
    Compare multiple YouTube channels side by side.
    Great for competitor analysis.
    """
    try:
        youtube = get_youtube_client()
        ids = [c.strip() for c in channel_ids.split(",") if c.strip()]

        if not ids:
            return json.dumps({"error": "No channel IDs provided"})

        response = youtube.channels().list(
            part="snippet,statistics,brandingSettings",
            id=",".join(ids),
        ).execute()

        channels = []
        for ch in response.get("items", []):
            snippet = ch.get("snippet", {})
            stats = ch.get("statistics", {})
            subs = int(stats.get("subscriberCount", 0))
            views = int(stats.get("viewCount", 0))
            videos = int(stats.get("videoCount", 0))

            channels.append({
                "channel_id": ch["id"],
                "title": snippet.get("title", ""),
                "custom_url": snippet.get("customUrl", ""),
                "subscribers": subs,
                "total_views": views,
                "total_videos": videos,
                "views_per_video": views // videos if videos > 0 else 0,
                "views_per_subscriber": round(views / subs, 1) if subs > 0 else 0,
                "country": snippet.get("country", "N/A"),
                "created": snippet.get("publishedAt", ""),
            })

        channels.sort(key=lambda x: x["subscribers"], reverse=True)

        return json.dumps({
            "channel_count": len(channels),
            "comparison": channels,
        }, indent=2)

    except HttpError as e:
        return json.dumps({"error": f"YouTube API error: {e.resp.status} - {e.content.decode()}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ===========================
# ENTRY POINT
# ===========================

if __name__ == "__main__":
    log.info("Starting YouTube Channel Management MCP Server v1.0.0")
    log.info(f"API Key configured: {'Yes' if API_KEY else 'NO - set YOUTUBE_API_KEY!'}")
    mcp.run(transport="stdio")
