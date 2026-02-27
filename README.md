![Build Status](https://github.com/TheWicklowWolf/ChannelTube/actions/workflows/main.yml/badge.svg)
![Docker Pulls](https://img.shields.io/docker/pulls/thewicklowwolf/channeltube.svg)


![full_logo](https://raw.githubusercontent.com/TheWicklowWolf/ChannelTube/main/src/static/full_logo.png)


ChannelTube is a tool for synchronizing and fetching content from YouTube channels using yt-dlp.


## Run using docker-compose

```yaml
services:
  channeltube:
    image: thewicklowwolf/channeltube:latest
    container_name: channeltube
    volumes:
      - /path/to/config:/channeltube/config
      - /data/media/video:/channeltube/downloads
      - /data/media/audio:/channeltube/audio_downloads
      - /etc/localtime:/etc/localtime:ro
    ports:
      - 5000:5000
    restart: unless-stopped
```

## Configuration via environment variables

Certain values can be set via environment variables:

* __PUID__: The user ID to run the app with. Defaults to `1000`. 
* __PGID__: The group ID to run the app with. Defaults to `1000`.
* __video_format_id__: Specifies the ID for the video format. The default value is `137`.
* __audio_format_id__: Specifies the ID for the audio format. The default value is `140`.
* __defer_hours__: Defines the time to defer in hours. The default value is `0`.
* __thread_limit__: Sets the maximum number of threads to use. The default value is `1`.
* __fallback_vcodec__: Specifies the fallback video codec to use. Defaults to `vp9`.  
* __fallback_acodec__ :Specifies the fallback audio codec to use. Defaults to `mp4a`.  
* __subtitles__: Controls subtitle handling. Options: `none`, `embed`, `external`. Defaults to `none`.
* __subtitle_languages__: Comma-separated list of subtitle languages to include. Defaults to `en`.
* __include_id_in_filename__: Include Video ID in filename. Set to `true` or `false`. Defaults to `false`.
* __verbose_logs__: Enable verbose logging. Set to `true` or `false`. Defaults to `false`.
* __short_video_cutoff__: Time-based cutoff (in seconds) used to filter short videos. Videos with runtime shorter than this value will be ignored. Defaults to `180`.
* __auto_update_hour__: Enables automatic nightly update of yt-dlp when set to a value between `0 and 23` (24-hour clock). The update will run once per day during the specified hour. If unset or set to any value outside `0–23`, automatic updates are disabled. Default is `disabled`

> For information on format IDs, refer to [https://github.com/yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp)
> 
> ![yt-dlp-formats](https://github.com/user-attachments/assets/e03b9dd3-028f-4c72-b822-06aa1d440cea)


## Sync Schedule

Use a comma-separated list of hours to search for new items (e.g. `2, 20` will initiate a search at 2 AM and 8 PM).
> Note: There is a deadband of up to 10 minutes from the scheduled start time.

## Media Server Integration (optional)

A media server library scan can be triggered when new content is retrieved.

For Plex, use: `Plex: http://192.168.1.2:32400`  
For Jellyfin, use: `Jellyfin: http://192.168.1.2:8096`  
To use both, enter: `Plex: http://192.168.1.2:32400, Jellyfin: http://192.168.1.2:8096`  
The same format applies for the tokens.  

The **Media Server Library Name** refers to the name of the library where the videos are stored.  

To disable this feature:
- Leave **Media Server Addresses**, **Media Server Tokens** and **Media Server Library Name** blank.  

## Cookies (optional)
To utilize a cookies file with yt-dlp, follow these steps:

* Generate Cookies File: Open your web browser and use a suitable extension (e.g. cookies.txt for Firefox) to extract cookies for a user on YT.

* Save Cookies File: Save the obtained cookies into a file named `cookies.txt` and put it into the config folder.


---

![light](https://raw.githubusercontent.com/TheWicklowWolf/ChannelTube/main/src/static/light.png)


---


![dark](https://raw.githubusercontent.com/TheWicklowWolf/ChannelTube/main/src/static/dark.png)

---


https://hub.docker.com/r/thewicklowwolf/channeltube



