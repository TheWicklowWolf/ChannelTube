import logging
import re
import os
import json
import time
import datetime
import threading
from mutagen.mp4 import MP4
import concurrent.futures
from flask import Flask, render_template
from flask_socketio import SocketIO
import yt_dlp
from plexapi.server import PlexServer
import requests
import tempfile

PERMANENT_RETENTION = -1
VIDEO_EXTENSIONS = {".mp4"}
AUDIO_EXTENSIONS = {".m4a"}
MEDIA_FILE_EXTENSIONS = VIDEO_EXTENSIONS.union(AUDIO_EXTENSIONS)


class DataHandler:
    def __init__(self):
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        self.general_logger = logging.getLogger()

        app_name_text = os.path.basename(__file__).replace(".py", "")
        release_version = os.environ.get("RELEASE_VERSION", "unknown")
        self.general_logger.warning(f"{'*' * 50}\n")
        self.general_logger.warning(f"{app_name_text} Version: {release_version}\n")
        self.general_logger.warning(f"{'*' * 50}")

        self.config_folder = "config"
        self.download_folder = "downloads"
        self.audio_download_folder = "audio_downloads"
        self.media_server_addresses = "Plex: http://192.168.1.2:32400, Jellyfin: http://192.168.1.2:8096"
        self.media_server_tokens = "Plex: abc, Jellyfin: xyz"
        self.media_server_library_name = "YouTube"
        self.media_server_scan_req_flag = False
        self.video_format_id = os.environ.get("video_format_id", "137")
        self.audio_format_id = os.environ.get("audio_format_id", "140")
        self.defer_hours = float(os.environ.get("defer_hours", "0"))
        self.thread_limit = int(os.environ.get("thread_limit", "1"))
        self.fallback_vcodec = os.environ.get("fallback_vcodec", "vp9")
        self.fallback_acodec = os.environ.get("fallback_acodec", "mp4a")
        self.subtitles = os.environ.get("subtitles", "none").lower()
        self.subtitles = "none" if self.subtitles not in ("none", "embed", "external") else self.subtitles
        self.subtitle_languages = os.environ.get("subtitle_languages", "en").split(",")
        self.include_id_in_filename = os.environ.get("include_id_in_filename", "false").lower() == "true"
        self.verbose_logs = os.environ.get("verbose_logs", "false").lower() == "true"

        os.makedirs(self.config_folder, exist_ok=True)
        os.makedirs(self.download_folder, exist_ok=True)
        os.makedirs(self.audio_download_folder, exist_ok=True)

        self.sync_start_times = []
        self.settings_config_file = os.path.join(self.config_folder, "settings_config.json")

        self.req_channel_list = []
        self.channel_list_config_file = os.path.join(self.config_folder, "channel_list.json")

        if os.path.exists(self.settings_config_file):
            self.load_settings_from_file()

        if os.path.exists(self.channel_list_config_file):
            self.load_channel_list_from_file()

        full_cookies_path = os.path.join(self.config_folder, "cookies.txt")
        self.cookies_path = full_cookies_path if os.path.exists(full_cookies_path) else None

        task_thread = threading.Thread(target=self.schedule_checker, daemon=True)
        task_thread.start()

    def load_settings_from_file(self):
        try:
            with open(self.settings_config_file, "r") as json_file:
                ret = json.load(json_file)
            self.sync_start_times = ret["sync_start_times"]
            self.media_server_addresses = ret["media_server_addresses"]
            self.media_server_tokens = ret["media_server_tokens"]
            self.media_server_library_name = ret["media_server_library_name"]

        except Exception as e:
            self.general_logger.error(f"Error Loading Config: {str(e)}")

    def save_settings_to_file(self):
        try:
            with open(self.settings_config_file, "w") as json_file:
                json.dump(
                    {
                        "sync_start_times": self.sync_start_times,
                        "media_server_addresses": self.media_server_addresses,
                        "media_server_tokens": self.media_server_tokens,
                        "media_server_library_name": self.media_server_library_name,
                    },
                    json_file,
                    indent=4,
                )

        except Exception as e:
            self.general_logger.error(f"Error Saving Config: {str(e)}")

        else:
            self.general_logger.warning(f"Settings Saved.")

    def load_channel_list_from_file(self):
        try:
            with open(self.channel_list_config_file, "r") as json_file:
                channels = json.load(json_file)
            sorted_channels = sorted(channels, key=lambda channel: channel.get("Name", "").lower())

            for idx, channel in enumerate(sorted_channels):
                synced_state = channel.get("Last_Synced", "Never")
                synced_state = "Incomplete" if synced_state in ["In Progress", "Failed", "Queued"] else synced_state
                full_channel_data = {
                    "Id": idx,
                    "Name": channel.get("Name", ""),
                    "Link": channel.get("Link", ""),
                    "DL_Days": channel.get("DL_Days", 0),
                    "Keep_Days": channel.get("Keep_Days", 0),
                    "Last_Synced": synced_state,
                    "Item_Count": channel.get("Item_Count", 0),
                    "Filter_Title_Text": channel.get("Filter_Title_Text", ""),
                    "Negate_Filter": channel.get("Negate_Filter", False),
                    "Media_Type": channel.get("Media_Type", "Video"),
                    "Search_Limit": channel.get("Search_Limit", ""),
                    "Live_Rule": channel.get("Live_Rule", "Ignore"),
                }

                self.req_channel_list.append(full_channel_data)

        except Exception as e:
            self.general_logger.error(f"Error Loading Channels: {str(e)}")

    def save_channel_list_to_file(self):
        try:
            with open(self.channel_list_config_file, "w") as json_file:
                json.dump(self.req_channel_list, json_file, indent=4)

        except Exception as e:
            self.general_logger.error(f"Error Saving Channels: {str(e)}")

    def schedule_checker(self):
        self.general_logger.warning("Starting periodic checks every 10 minutes to monitor sync start times.")
        self.general_logger.warning(f"Current scheduled hours to start sync (in 24-hour format): {self.sync_start_times}")
        while True:
            current_time = datetime.datetime.now()
            within_sync_window = current_time.hour in self.sync_start_times

            if within_sync_window:
                self.general_logger.warning(f"Time to Start Sync - as current hour: {current_time.hour} in schedule {str(self.sync_start_times)}")
                self.master_queue()

                current_time = datetime.datetime.now()
                next_hour = (current_time + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=1)
                sleep_seconds = (next_hour - current_time).total_seconds()

                self.general_logger.warning(f"Sync Complete - Sleeping for {int(sleep_seconds)} seconds until {next_hour.time()}")
                time.sleep(sleep_seconds)
                self.general_logger.warning(f"Checking sync schedule every 10 minutes: {str(self.sync_start_times)}")

            else:
                time.sleep(600)

    def get_list_of_videos_from_youtube(self, channel, current_channel_files):
        days_to_retrieve = channel["DL_Days"]
        channel_link = channel["Link"]
        search_limit = channel["Search_Limit"]
        video_to_download_list = []

        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "ffmpeg_location": "/usr/bin/ffmpeg",
            "verbose": self.verbose_logs,
        }
        if search_limit:
            ydl_opts["playlist_items"] = f"1-{search_limit}"
        ydl = yt_dlp.YoutubeDL(ydl_opts)

        if "playlist?list" in channel_link.lower():
            playlist = ydl.extract_info(channel_link, download=False)
            channel_title = playlist.get("title")
            channel_name = playlist.get("channel")
            channel_id = playlist.get("channel_id")
            self.general_logger.warning(f"Playlist Title: {channel_title} from Channel: {channel_name} and Channel ID: {channel_id}")

        else:
            channel_info = ydl.extract_info(channel_link, download=False)
            channel_id = channel_info.get("channel_id")
            channel_title = channel_info.get("title")

            if not channel_id:
                raise Exception("No Channel ID")
            if not channel_title:
                raise Exception("No Channel Title")

            self.general_logger.warning(f"Channel Title: {channel_title} and Channel ID: {channel_id}")

            if channel["Live_Rule"] == "Only":
                self.general_logger.warning(f"Getting list of live videos for channel: {channel_title}")
                playlist_url = f"{channel_link}/streams"
            else:
                self.general_logger.warning(f"Getting list of videos for channel: {channel_title}")
                playlist_url = f"https://www.youtube.com/playlist?list=UU{channel_id[2:]}"

            playlist = ydl.extract_info(playlist_url, download=False)

        today = datetime.datetime.now()
        cutoff_date = today - datetime.timedelta(days=days_to_retrieve)

        for video in playlist["entries"]:
            try:
                video_title = f'{video["title"]} [{video["id"]}]' if self.include_id_in_filename else video["title"]
                video_link = video["url"]
                duration = 0 if not video["duration"] else video["duration"]
                youtube_video_id = video["id"]
                live_status = video["live_status"]

                if channel["Live_Rule"] == "Only":
                    if len(video_to_download_list):
                        self.general_logger.warning(f"Live video found for channel: {channel_title}")
                        self.general_logger.warning(f"Downloading first live video and ignoring everything else for channel: {channel_title}")
                        break

                    if live_status == "is_upcoming":
                        self.general_logger.warning(f"Skipping upcoming live video: {video_title} - {video_link}")
                        continue

                    if not (live_status == "is_live" or live_status == "post_live"):
                        self.general_logger.warning(f"No active live videos for channel: {channel_title}")
                        break

                if channel["Live_Rule"] == "Ignore" and live_status is not None:
                    self.general_logger.warning(f"Ignoring live video: {video_title} - {video_link}")
                    continue

                if duration <= 180 and live_status is None:
                    self.general_logger.warning(f"Ignoring short video: {video_title} - {video_link}")
                    continue

                if youtube_video_id in current_channel_files["id_list"] or video_title in current_channel_files["filename_list"]:
                    self.general_logger.warning(f"File for video: {video_title} already in folder.")
                    continue

                self.general_logger.warning(f"Extracting info for: {video_title} -> Duration: {duration} seconds")
                video_extracted_info = ydl.extract_info(video_link, download=False)

                video_upload_date_raw = video_extracted_info["upload_date"]
                video_upload_date = datetime.datetime.strptime(video_upload_date_raw, "%Y%m%d")
                video_timestamp = video_extracted_info["timestamp"]

                current_time = time.time()
                age_in_hours = (current_time - video_timestamp) / 3600

                if video_upload_date < cutoff_date:
                    self.general_logger.warning(f"Ignoring video: {video_title} as it is older than the cut-off {cutoff_date}.")
                    self.general_logger.warning("No more videos in date range")
                    break

                if age_in_hours < self.defer_hours and live_status is None:
                    self.general_logger.warning(f"Video: {video_title} is {age_in_hours:.2f} hours old. Waiting until it's older than {self.defer_hours} hours.")
                    continue

                if channel.get("Filter_Title_Text"):
                    if channel["Negate_Filter"] and channel["Filter_Title_Text"].lower() in video_title.lower():
                        self.general_logger.warning(f'Skipped video: {video_title} as it contains the filter text: {channel["Filter_Title_Text"]}')
                        continue

                    if not channel["Negate_Filter"] and channel["Filter_Title_Text"].lower() not in video_title.lower():
                        self.general_logger.warning(f'Skipped video: {video_title} as it does not contain the filter text: {channel["Filter_Title_Text"]}')
                        continue

                video_to_download_list.append({"title": video_title, "upload_date": video_upload_date, "link": video_link, "id": youtube_video_id, "channel_name": channel_title})
                self.general_logger.warning(f"Added video to download list: {video_title} -> {video_link}")

            except Exception as e:
                self.general_logger.error(f"Error extracting details of {video_title}: {str(e)}")

        return video_to_download_list

    def get_list_of_files_from_channel_folder(self, channel_folder_path):
        try:
            folder_info = {"id_list": [], "filename_list": []}
            raw_directory_list = os.listdir(channel_folder_path)
            for filename in raw_directory_list:
                file_path = os.path.join(channel_folder_path, filename)
                if not os.path.isfile(file_path):
                    continue

                try:
                    file_base_name, file_ext = os.path.splitext(filename)
                    if file_ext.lower() in MEDIA_FILE_EXTENSIONS:
                        folder_info["filename_list"].append(file_base_name)
                        mp4_file = MP4(file_path)
                        embedded_video_id = mp4_file.get("\xa9cmt", [None])[0]
                        folder_info["id_list"].append(embedded_video_id)

                except Exception as e:
                    self.general_logger.error(f"No video ID present or cannot read it from metadata of {filename}: {e}")

        except Exception as e:
            self.general_logger.error(f"Error getting list of files for channel folder: {e}")

        finally:
            self.general_logger.warning(f'Found {len(folder_info["filename_list"])} files and {len(folder_info["id_list"])} IDs in {channel_folder_path}.')
            return folder_info

    def count_media_files(self, channel_folder_path):
        video_item_count = 0
        audio_item_count = 0

        raw_directory_list = os.listdir(channel_folder_path)
        for filename in raw_directory_list:
            file_path = os.path.join(channel_folder_path, filename)
            if not os.path.isfile(file_path):
                continue

            file_base_name, file_ext = os.path.splitext(filename.lower())
            if file_ext in VIDEO_EXTENSIONS:
                video_item_count += 1
            elif file_ext in AUDIO_EXTENSIONS:
                audio_item_count += 1

        self.general_logger.info(f"Found {video_item_count} video files and {audio_item_count} audio files in {channel_folder_path}.")

        return video_item_count + audio_item_count

    def cleanup_old_files(self, channel_folder_path, channel):
        days_to_keep = channel["Keep_Days"]
        selected_media_type = channel["Media_Type"]

        if days_to_keep == PERMANENT_RETENTION:
            self.general_logger.warning(f"Skipping cleanup for channel: {channel['Name']} due to permanent retention policy.")
            return

        current_datetime = datetime.datetime.now()
        raw_directory_list = os.listdir(channel_folder_path)
        for filename in raw_directory_list:
            try:
                file_path = os.path.join(channel_folder_path, filename)
                if not os.path.isfile(file_path):
                    continue

                file_base_name, file_ext = os.path.splitext(filename.lower())

                video_file_check = file_ext in VIDEO_EXTENSIONS and selected_media_type == "Video"
                audio_file_check = file_ext in AUDIO_EXTENSIONS and selected_media_type == "Audio"
                subtitle_file_check = file_ext == ".srt" and self.subtitles == "external"

                if not (video_file_check or audio_file_check or subtitle_file_check):
                    continue

                file_mtime = self.get_file_modification_time(file_path, filename, file_ext)
                age = current_datetime - file_mtime

                if age > datetime.timedelta(days=days_to_keep):
                    os.remove(file_path)
                    self.general_logger.warning(f"Deleted: {filename} as it is {age.days} days old.")
                    self.media_server_scan_req_flag = True
                else:
                    self.general_logger.warning(f"File: {filename} is {age.days} days old, keeping file as not over {days_to_keep} days.")

            except Exception as e:
                self.general_logger.error(f"Error Cleaning Old Files: {filename} {str(e)}")

    def get_file_modification_time(self, file_path, filename, file_ext):
        try:
            if file_ext == ".srt":
                file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                return file_mtime

            mpeg4_file = MP4(file_path)
            mpeg4_file_created_timestamp = mpeg4_file.get("\xa9day", [None])[0]
            if mpeg4_file_created_timestamp:
                file_mtime = datetime.datetime.strptime(mpeg4_file_created_timestamp, "%Y-%m-%d %H:%M:%S")
                self.general_logger.warning(f"Extracted datetime {file_mtime} from metadata of {filename}")
                return file_mtime
            else:
                raise Exception("No timestamp found")

        except Exception as e:
            self.general_logger.warning(f"Error extracting datetime from metadata for {filename}: {e}")
            file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
            self.general_logger.warning(f"Using filesystem modified timestamp {file_mtime} for {filename}")
            return file_mtime

    def download_items(self, item_list, channel_folder_path, channel):
        for item in item_list:
            self.general_logger.warning(f'Starting download: {item["title"]}')

            try:
                temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
                link = item["link"]
                cleaned_title = self.string_cleaner(item["title"])
                selected_media_type = channel["Media_Type"]
                post_processors = [
                    {"key": "SponsorBlock", "categories": ["sponsor"]},
                    {"key": "ModifyChapters", "remove_sponsor_segments": ["sponsor"]},
                ]

                if selected_media_type == "Video":
                    selected_ext = "mp4"
                    selected_format = f"{self.video_format_id}+{self.audio_format_id}/bestvideo[vcodec^={self.fallback_vcodec}]+bestaudio[acodec^={self.fallback_acodec}]/bestvideo+bestaudio/best"
                    merge_output_format = selected_ext

                else:
                    selected_ext = "m4a"
                    selected_format = f"{self.audio_format_id}/bestaudio[acodec^={self.fallback_acodec}]/bestaudio"
                    merge_output_format = None
                    post_processors.append(
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": selected_ext,
                            "preferredquality": 0,
                        }
                    )

                post_processors.extend(
                    [
                        {"key": "FFmpegMetadata"},
                        {"key": "EmbedThumbnail"},
                    ]
                )

                folder_and_filename = os.path.join(channel_folder_path, cleaned_title)
                ydl_opts = {
                    "paths": {"home": channel_folder_path, "temp": temp_dir.name},
                    "logger": self.general_logger,
                    "ffmpeg_location": "/usr/bin/ffmpeg",
                    "format": selected_format,
                    "outtmpl": f"{cleaned_title}.%(ext)s",
                    "quiet": True,
                    "writethumbnail": True,
                    "progress_hooks": [self.progress_callback],
                    "postprocessors": post_processors,
                    "no_mtime": True,
                    "live_from_start": True,
                    "extractor_args": {"youtubetab": {"skip": ["authcheck"]}},
                    "verbose": self.verbose_logs,
                    "writeinfojson": True,
                    "addmetadata": True,
                    "addchapters": True,
                }

                if self.subtitles in ["embed", "external"]:
                    ydl_opts.update(
                        {
                            "subtitlesformat": "best",
                            "writeautomaticsub": True,
                            "writesubtitles": True,
                            "subtitleslangs": self.subtitle_languages,
                        }
                    )
                    if self.subtitles == "embed":
                        post_processors.extend([{"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False}])
                    elif self.subtitles == "external":
                        post_processors.extend([{"key": "FFmpegSubtitlesConvertor", "format": "srt", "when": "before_dl"}])

                if merge_output_format:
                    ydl_opts["merge_output_format"] = merge_output_format
                if self.cookies_path:
                    ydl_opts["cookiefile"] = self.cookies_path

                yt_downloader = yt_dlp.YoutubeDL(ydl_opts)
                self.general_logger.warning(f"yt_dlp -> Starting to download: {link}")

                yt_downloader.download([link])
                self.general_logger.warning(f"yt_dlp -> Finished: {link}")

                self.add_extra_metadata(f"{folder_and_filename}.{selected_ext}", item)

            except Exception as e:
                self.general_logger.error(f"Error downloading video: {link}. Error message: {e}")

            finally:
                temp_dir.cleanup()

        self.media_server_scan_req_flag = True

    def progress_callback(self, progress_data):
        status = progress_data.get("status", "unknown")
        is_live_video = progress_data.get("info_dict", {}).get("is_live", False)
        fragment_index = progress_data.get("fragment_index", 1)
        show_live_log_message = fragment_index % 10 == 0
        elapsed = progress_data.get("elapsed", 1)
        minutes, seconds = divmod(elapsed, 60)

        if status == "finished":
            self.general_logger.warning("Download complete")
            self.general_logger.warning("Processing file...")

        elif status == "downloading" and is_live_video and show_live_log_message:
            downloaded_bytes_str = progress_data.get("_downloaded_bytes_str", "0")
            elapsed_str = f"{int(minutes)} minutes and {int(seconds)} seconds"
            self.general_logger.warning(f"Live Video - Downloaded: {downloaded_bytes_str} (Fragment Index: {fragment_index}, Elapsed: {elapsed_str})")

        elif status == "downloading" and not is_live_video and int(seconds) % 5 == 0:
            percent_str = progress_data.get("_percent_str", "unknown")
            total_bytes_str = progress_data.get("_total_bytes_str", "unknown")
            speed_str = progress_data.get("_speed_str", "unknown")
            eta_str = progress_data.get("_eta_str", "unknown")

            self.general_logger.warning(f"Downloaded {percent_str} of {total_bytes_str} at {speed_str} with ETA {eta_str}")

    def add_extra_metadata(self, file_path, item):
        try:
            current_datetime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            m4_file = MP4(file_path)
            m4_file["\xa9day"] = current_datetime
            m4_file["\xa9cmt"] = item["id"]
            m4_file["\xa9nam"] = item["title"]
            m4_file["\xa9ART"] = item["channel_name"]
            m4_file["\xa9gen"] = item["channel_name"]
            m4_file["\xa9pub"] = item["channel_name"]
            m4_file.save()
            self.general_logger.warning(f'Added timestamp: {current_datetime} and video ID: {item["id"]} to metadata of: {file_path}')

        except Exception as e:
            self.general_logger.error(f"Error adding metadata to {file_path}: {e}")

    def master_queue(self):
        try:
            self.media_server_scan_req_flag = False
            self.general_logger.warning("Sync Task started...")

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.thread_limit) as executor:
                futures = []
                for channel in self.req_channel_list:
                    if channel.get("Last_Synced") not in ["In Progress", "Queued"]:
                        channel["Last_Synced"] = "Queued"
                        futures.append(executor.submit(self.process_channel, channel))
                socketio.emit("update_channel_list", {"Channel_List": self.req_channel_list})
            concurrent.futures.wait(futures)

            if self.req_channel_list:
                self.save_channel_list_to_file()
            else:
                self.general_logger.warning("Channel list empty")

            if self.media_server_scan_req_flag == True and self.media_server_tokens:
                self.sync_media_servers()
            else:
                self.general_logger.warning("Media Server Sync not required")

        except Exception as e:
            self.general_logger.error(f"Error in Queue: {str(e)}")
            self.general_logger.warning("Sync Finished: Incomplete")

        else:
            self.general_logger.warning("Sync Finished: Complete")

        finally:
            socketio.emit("update_channel_list", {"Channel_List": self.req_channel_list})

    def process_channel(self, channel):
        try:
            channel["Last_Synced"] = "In Progress"
            channel_folder_path = os.path.join(self.audio_download_folder, channel["Name"]) if channel["Media_Type"] == "Audio" else os.path.join(self.download_folder, channel["Name"])
            os.makedirs(channel_folder_path, exist_ok=True)

            self.general_logger.warning(f'Getting current list of files for channel: {channel["Name"]} from {channel_folder_path}')
            current_channel_files = self.get_list_of_files_from_channel_folder(channel_folder_path)

            self.general_logger.warning(f'Getting list of videos for channel: {channel["Name"]} from {channel["Link"]}')
            item_download_list = self.get_list_of_videos_from_youtube(channel, current_channel_files)

            if item_download_list:
                self.general_logger.warning(f'Downloading video list for: {channel["Name"]}')
                self.download_items(item_download_list, channel_folder_path, channel)
                self.general_logger.warning(f'Finished downloading videos for channel: {channel["Name"]}')
            else:
                self.general_logger.warning(f'No videos to download for: {channel["Name"]}')

            self.general_logger.warning(f'Clearing Files for: {channel["Name"]}')
            self.cleanup_old_files(channel_folder_path, channel)
            self.general_logger.warning(f'Finished Clearing Files for channel: {channel["Name"]}')

            self.general_logger.warning(f'Counting Files for: {channel["Name"]}')
            channel["Item_Count"] = self.count_media_files(channel_folder_path)
            self.general_logger.warning(f'Finished Counting Files for channel: {channel["Name"]}')

            channel["Last_Synced"] = datetime.datetime.now().strftime("%d-%m-%y %H:%M:%S")
            self.general_logger.warning(f'Completed processing for channel: {channel["Name"]}')

        except Exception as e:
            self.general_logger.error(f'Error processing channel {channel["Name"]}: {str(e)}')
            channel["Last_Synced"] = "Failed"

        finally:
            socketio.emit("update_channel_list", {"Channel_List": self.req_channel_list})

    def add_channel(self):
        existing_ids = [channel.get("Id", 0) for channel in self.req_channel_list]
        next_id = max(existing_ids, default=-1) + 1
        new_channel = {
            "Id": next_id,
            "Name": "New Channel",
            "Link": "https://www.youtube.com/@NewChannel",
            "Keep_Days": 28,
            "DL_Days": 14,
            "Last_Synced": "Never",
            "Item_Count": 0,
            "Filter_Title_Text": "",
            "Negate_Filter": False,
            "Media_Type": "Video",
            "Search_Limit": "",
            "Live_Rule": "Ignore",
        }
        self.req_channel_list.append(new_channel)
        socketio.emit("new_channel_added", new_channel)
        self.save_channel_list_to_file()

    def remove_channel(self, channel_to_be_removed):
        self.req_channel_list = [channel for channel in self.req_channel_list if channel["Id"] != channel_to_be_removed["Id"]]
        self.save_channel_list_to_file()

    def sync_media_servers(self):
        media_servers = self.convert_string_to_dict(self.media_server_addresses)
        media_tokens = self.convert_string_to_dict(self.media_server_tokens)
        if "Plex" in media_servers and "Plex" in media_tokens:
            try:
                token = media_tokens.get("Plex")
                address = media_servers.get("Plex")
                self.general_logger.warning("Attempting Plex Sync")
                media_server_server = PlexServer(address, token)
                library_section = media_server_server.library.section(self.media_server_library_name)
                library_section.update()
                self.general_logger.warning(f"Plex Library scan for '{self.media_server_library_name}' started.")
            except Exception as e:
                self.general_logger.warning(f"Plex Library scan failed: {str(e)}")

        if "Jellyfin" in media_servers and "Jellyfin" in media_tokens:
            try:
                token = media_tokens.get("Jellyfin")
                address = media_servers.get("Jellyfin")
                self.general_logger.warning("Attempting Jellyfin Sync")
                url = f"{address}/Library/Refresh?api_key={token}"
                response = requests.post(url)
                if response.status_code == 204:
                    self.general_logger.warning("Jellyfin Library refresh request successful.")
                else:
                    self.general_logger.warning(f"Jellyfin Error: {response.status_code}, {response.text}")
            except Exception as e:
                self.general_logger.warning(f"Jellyfin Library scan failed: {str(e)}")

    def string_cleaner(self, input_string):
        if isinstance(input_string, str):
            raw_string = re.sub(r'[\/:*?"<>|]', " ", input_string)
            temp_string = re.sub(r"\s+", " ", raw_string)
            cleaned_string = temp_string.strip()
            return cleaned_string

        elif isinstance(input_string, list):
            cleaned_strings = []
            for string in input_string:
                file_name_without_extension, file_extension = os.path.splitext(string)
                raw_string = re.sub(r'[\/:*?"<>|]', " ", file_name_without_extension)
                temp_string = re.sub(r"\s+", " ", raw_string)
                cleaned_string = temp_string.strip()
                cleaned_strings.append(cleaned_string)
            return cleaned_strings

    def convert_string_to_dict(self, raw_string):
        result = {}
        if not raw_string:
            return result

        pairs = raw_string.split(",")
        for pair in pairs:
            key_value = pair.split(":", 1)
            if len(key_value) == 2:
                key, value = key_value
                result[key.strip()] = value.strip()

        return result

    def save_settings(self, data):
        self.media_server_addresses = data["media_server_addresses"]
        self.media_server_tokens = data["media_server_tokens"]
        self.media_server_library_name = data["media_server_library_name"]

        try:
            if data["sync_start_times"] == "":
                self.sync_start_times = []
            else:
                raw_sync_start_times = [int(re.sub(r"\D", "", start_time.strip())) for start_time in data["sync_start_times"].split(",")]
                temp_sync_start_times = [0 if x < 0 or x > 23 else x for x in raw_sync_start_times]
                cleaned_sync_start_times = sorted(list(set(temp_sync_start_times)))
                self.sync_start_times = cleaned_sync_start_times

        except Exception as e:
            self.general_logger.error(f"Error Updating Settings: {str(e)}")
            self.sync_start_times = []

        finally:
            self.general_logger.warning(f"Sync Hours: {str(self.sync_start_times)}")
            self.save_settings_to_file()

    def save_channel_changes(self, channel_to_be_saved):
        try:
            for channel in self.req_channel_list:
                if channel["Id"] == channel_to_be_saved.get("Id"):
                    channel.update(channel_to_be_saved)
                    self.general_logger.warning(f"Channel: {channel_to_be_saved.get('Name')} saved.")
                    break
            else:
                self.general_logger.warning(f"Channel Name: {channel_to_be_saved.get('Name')} not found.")

        except Exception as e:
            self.general_logger.error(f"Error Saving Channel: {str(e)}")

        else:
            self.save_channel_list_to_file()

    def manual_start(self):
        self.general_logger.warning("Manual sync triggered.")
        task_thread = threading.Thread(target=self.master_queue, daemon=True)
        task_thread.start()
        socketio.emit("settings_save_message", "Manual sync initiated.")


app = Flask(__name__)
app.secret_key = "secret_key"
socketio = SocketIO(app)
data_handler = DataHandler()


@app.route("/")
def home():
    return render_template("base.html")


@socketio.on("connect")
def connection():
    socketio.emit("update_channel_list", {"Channel_List": data_handler.req_channel_list})


@socketio.on("get_settings")
def get_settings():
    data = {
        "sync_start_times": data_handler.sync_start_times,
        "media_server_addresses": data_handler.media_server_addresses,
        "media_server_tokens": data_handler.media_server_tokens,
        "media_server_library_name": data_handler.media_server_library_name,
    }
    socketio.emit("current_settings", data)


@socketio.on("save_channel_changes")
def save_channel_changes(channel_to_be_saved):
    data_handler.save_channel_changes(channel_to_be_saved)
    socketio.emit("channel_save_message", "Channel Settings Saved Successfully.")


@socketio.on("save_settings")
def save_settings(data):
    data_handler.save_settings(data)
    socketio.emit("settings_save_message", "Settings Saved Successfully.")


@socketio.on("add_channel")
def add_channel():
    data_handler.add_channel()


@socketio.on("remove_channel")
def remove_channel(channel_to_be_removed):
    data_handler.remove_channel(channel_to_be_removed)


@socketio.on("manual_start")
def manual_start():
    data_handler.manual_start()


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
