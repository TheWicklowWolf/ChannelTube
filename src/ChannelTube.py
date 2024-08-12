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


class DataHandler:
    def __init__(self):
        logging.basicConfig(level=logging.WARNING, format="%(message)s")
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

        if not os.path.exists(self.config_folder):
            os.makedirs(self.config_folder)
        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)
        if not os.path.exists(self.audio_download_folder):
            os.makedirs(self.audio_download_folder)

        self.sync_start_times = [0]
        self.settings_config_file = os.path.join(self.config_folder, "settings_config.json")

        self.req_channel_list = []
        self.channel_list_config_file = os.path.join(self.config_folder, "channel_list.json")

        if os.path.exists(self.settings_config_file):
            self.load_settings_from_file()

        if os.path.exists(self.channel_list_config_file):
            self.load_channel_list_from_file()

        full_cookies_path = os.path.join(self.config_folder, "cookies.txt")
        self.cookies_path = full_cookies_path if os.path.exists(full_cookies_path) else None

        task_thread = threading.Thread(target=self.schedule_checker)
        task_thread.daemon = True
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
                full_channel_data = {
                    "Id": idx,
                    "Name": channel.get("Name", ""),
                    "Link": channel.get("Link", ""),
                    "DL_Days": channel.get("DL_Days", 0),
                    "Keep_Days": channel.get("Keep_Days", 0),
                    "Last_Synced": channel.get("Last_Synced", "Never"),
                    "Item_Count": channel.get("Item_Count", 0),
                    "Filter_Title_Text": channel.get("Filter_Title_Text", ""),
                    "Negate_Filter": channel.get("Negate_Filter", False),
                    "Media_Type": channel.get("Media_Type", "Video"),
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
            current_time = datetime.datetime.now().time()
            within_sync_window = any(datetime.time(t, 0, 0) <= current_time <= datetime.time(t, 59, 59) for t in self.sync_start_times)

            if within_sync_window:
                self.general_logger.warning(f"Time to Start Sync - as in a time window {str(self.sync_start_times)}")
                self.master_queue()
                self.general_logger.warning("Big sleep for 1 Hour - Sync Complete")
                time.sleep(3600)
                self.general_logger.warning(f"Checking every 10 minutes as not in sync time window {str(self.sync_start_times)}")
            else:
                time.sleep(600)

    def get_list_of_videos(self, channel):
        days_to_retrieve = channel["DL_Days"]

        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
        }
        ydl = yt_dlp.YoutubeDL(ydl_opts)

        channel_link = channel["Link"]
        channel_info = ydl.extract_info(channel_link, download=False)
        channel_id = channel_info["channel_id"]
        channel_title = channel_info["title"]

        if not channel_id:
            raise Exception("No Channel ID")
        if not channel_title:
            raise Exception("No Channel Title")

        self.general_logger.warning(f"Channel Title: {channel_title} and Channel ID: {channel_id}")
        uploads_playlist_url = f"https://www.youtube.com/playlist?list=UU{channel_id[2:]}"
        playlist = ydl.extract_info(uploads_playlist_url, download=False)

        today = datetime.datetime.now()
        last_date = today - datetime.timedelta(days=days_to_retrieve)

        video_list = []
        for video in playlist["entries"]:
            try:
                video_title = video["title"]
                video_link_in_playlist = video["url"]
                duration = video["duration"]
                actual_channel_name = video["channel"]

                self.general_logger.warning(f"Processing: {video_title} -> Duration: {duration} seconds")

                actual_video_info = ydl.extract_info(video_link_in_playlist, download=False)
                video_id = actual_video_info["id"]
                actual_video_link = actual_video_info["webpage_url"]
                video_date_raw = actual_video_info["upload_date"]
                video_date = datetime.datetime.strptime(video_date_raw, "%Y%m%d")
                video_timestamp = actual_video_info["timestamp"]

                current_time = time.time()
                age_in_hours = (current_time - video_timestamp) / 3600

                if video_date < last_date:
                    self.general_logger.warning("No more videos in date range")
                    break

                if duration <= 60:
                    self.general_logger.warning(f"Ignoring Short Video: {video_title} - {actual_video_link}")
                    continue

                if age_in_hours < self.defer_hours:
                    self.general_logger.warning(f"Video: {video_title} is {age_in_hours:.2f} hours old. Waiting until it's older than {self.defer_hours} hours.")
                    continue

                if channel.get("Filter_Title_Text"):
                    if channel["Negate_Filter"] and channel["Filter_Title_Text"].lower() in video_title.lower():
                        self.general_logger.warning(f'Skipped Video: {video_title} as it contains the filter text: {channel["Filter_Title_Text"]}')
                        continue

                    if not channel["Negate_Filter"] and channel["Filter_Title_Text"].lower() not in video_title.lower():
                        self.general_logger.warning(f'Skipped Video: {video_title} as it does not contain the filter text: {channel["Filter_Title_Text"]}')
                        continue

                video_list.append({"title": video_title, "upload_date": video_date, "link": actual_video_link, "id": video_id, "channel_name": actual_channel_name})
                self.general_logger.warning(f"Added Video to Download List: {video_title} -> {actual_video_link}")

            except Exception as e:
                self.general_logger.error(f"Error extracting details of {video_title}: {str(e)}")

        return video_list

    def check_and_download(self, item_list, channel):
        try:
            channel_folder = channel["Name"]

            if channel["Media_Type"] == "Audio":
                channel_folder_path = os.path.join(self.audio_download_folder, channel_folder)
            else:
                channel_folder_path = os.path.join(self.download_folder, channel_folder)

            if not os.path.exists(channel_folder_path):
                os.makedirs(channel_folder_path)

            for item in item_list:
                if not self.is_file_in_folder(item, channel_folder_path, channel):
                    self.general_logger.warning(f'Starting Download: {item["title"]}')
                    self.download_item(item, channel_folder_path, channel)

        except Exception as e:
            self.general_logger.error(f"Error checking file download: {str(e)}")

    def is_file_in_folder(self, video, channel_folder_path, channel):
        try:
            raw_directory_list = os.listdir(channel_folder_path)
            selected_media_type = channel["Media_Type"]
            search_text = f'{self.string_cleaner(video["title"])}.mp4' if selected_media_type == "Video" else f'{self.string_cleaner(video["title"])}.m4a'
            if search_text in raw_directory_list:
                self.general_logger.warning(f'Video File Already in folder: {video["title"]}')
                return True

            for filename in raw_directory_list:
                file_path = os.path.join(channel_folder_path, filename)
                if not os.path.isfile(file_path):
                    continue

                file_ext = filename.lower().split(".")[-1]
                if (file_ext == "mp4" and selected_media_type == "Video") or (file_ext == "m4a" and selected_media_type == "Audio"):
                    try:
                        mp4_file = MP4(file_path)
                        embedded_video_id = mp4_file.get("\xa9cmt", [None])[0]
                        if embedded_video_id == video["id"]:
                            self.general_logger.warning(f'Video ID for: {video["title"]} found embedded in: {file_path}')
                            return True

                    except Exception as e:
                        self.general_logger.error(f"No Video ID present or cannot read it from metadata: {e}")
            return False

        except Exception as e:
            self.general_logger.error(f"Error checking if video is in folder: {str(e)}")
            return False

    def cleanup_old_files(self, channel):
        channel_folder = channel["Name"]
        days_to_keep = channel["Keep_Days"]
        selected_media_type = channel["Media_Type"]

        if selected_media_type == "Audio":
            channel_folder_path = os.path.join(self.audio_download_folder, channel_folder)
        elif selected_media_type == "Video":
            channel_folder_path = os.path.join(self.download_folder, channel_folder)
        else:
            self.general_logger.error(f"Unsupported media type: {selected_media_type}")
            return

        raw_directory_list = os.listdir(channel_folder_path)
        current_datetime = datetime.datetime.now()
        channel["Item_Count"] = 0

        try:
            for filename in raw_directory_list:
                file_path = os.path.join(channel_folder_path, filename)
                if not os.path.isfile(file_path):
                    continue

                file_ext = filename.lower().split(".")[-1]
                if (file_ext == "mp4" and selected_media_type == "Video") or (file_ext == "m4a" and selected_media_type == "Audio"):
                    try:
                        m4_file = MP4(file_path)
                        m4_file_created_timestamp = m4_file.get("\xa9day", [None])[0]
                        if m4_file_created_timestamp:
                            file_mtime = datetime.datetime.strptime(m4_file_created_timestamp, "%Y-%m-%d %H:%M:%S")
                            self.general_logger.warning(f"Extracted datetime {file_mtime} from metadata of {filename}")
                        else:
                            raise Exception("No timestamp found")

                    except Exception as e:
                        self.general_logger.error(f"Error extracting datetime from metadata: {e}")
                        file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                        self.general_logger.error(f"Using Modified timestamp instead.... {file_mtime} for {filename}")

                    age = current_datetime - file_mtime

                    if age > datetime.timedelta(days=days_to_keep):
                        os.remove(file_path)
                        self.general_logger.warning(f"Deleted: {filename} as it is {age.days} days old.")
                        if self.media_server_scan_req_flag == False:
                            self.media_server_scan_req_flag = True
                    else:
                        channel["Item_Count"] += 1
                        self.general_logger.warning(f"File: {filename} is {age.days} days old, keeping file as not over {days_to_keep} days.")

        except Exception as e:
            self.general_logger.error(f"Error Cleaning Old Files: {str(e)}")

    def download_item(self, item, channel_folder_path, channel):
        if self.media_server_scan_req_flag == False:
            self.media_server_scan_req_flag = True
        try:
            link = item["link"]
            title = self.string_cleaner(item["title"])
            selected_media_type = channel["Media_Type"]
            post_processors = [
                {"key": "SponsorBlock", "categories": ["sponsor"]},
                {"key": "ModifyChapters", "remove_sponsor_segments": ["sponsor"]},
            ]

            if selected_media_type == "Video":
                selected_ext = "mp4"
                selected_format = f"{self.video_format_id}+{self.audio_format_id}/bestvideo+bestaudio/best"
                merge_output_format = selected_ext
            else:
                selected_ext = "m4a"
                selected_format = f"bestaudio[ext={selected_ext}]/{self.audio_format_id}/bestaudio"
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
                    {"key": "EmbedThumbnail"},
                    {"key": "FFmpegMetadata"},
                ]
            )

            folder_and_filename = os.path.join(channel_folder_path, title)
            ydl_opts = {
                "ffmpeg_location": "/usr/bin/ffmpeg",
                "format": selected_format,
                "outtmpl": f"{folder_and_filename}.%(ext)s",
                "quiet": True,
                "writethumbnail": True,
                "progress_hooks": [self.progress_callback],
                "postprocessors": post_processors,
                "no_mtime": True,
            }
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

    def progress_callback(self, d):
        if d["status"] == "finished":
            self.general_logger.warning("Download complete")
            self.general_logger.warning("Processing File...")

        elif d["status"] == "downloading":
            self.general_logger.warning(f'Downloaded {d["_percent_str"]} of {d["_total_bytes_str"]} at {d["_speed_str"]}')

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
            self.general_logger.warning(f'Added timestamp: {current_datetime} and Video ID: {item["id"]} to metadata of: {file_path}')

        except Exception as e:
            self.general_logger.error(f"Error adding metadata to {file_path}: {e}")

    def master_queue(self):
        try:
            self.media_server_scan_req_flag = False
            self.general_logger.warning("Sync Task started...")

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.thread_limit) as executor:
                futures = [executor.submit(self.process_channel, channel) for channel in self.req_channel_list]
                concurrent.futures.wait(futures)

            if self.req_channel_list:
                self.save_channel_list_to_file()
            else:
                self.general_logger.warning("Channel List Empty")

            data = {"Channel_List": self.req_channel_list}
            socketio.emit("update_channel_list", data)

            if self.media_server_scan_req_flag == True and self.media_server_tokens:
                self.sync_media_servers()
            else:
                self.general_logger.warning("Media Server Sync not required")

        except Exception as e:
            self.general_logger.error(f"Error in Queue: {str(e)}")
            self.general_logger.warning("Sync Finished: Incomplete")

        else:
            self.general_logger.warning("Sync Finished: Complete")

    def process_channel(self, channel):
        try:
            self.general_logger.warning(f'Getting list of videos for channel: {channel["Name"]} from {channel["Link"]}')
            item_download_list = self.get_list_of_videos(channel)

            self.general_logger.warning(f'Downloading Video List for: {channel["Name"]}')
            self.check_and_download(item_download_list, channel)
            self.general_logger.warning(f'Finished Downloading Videos for channel: {channel["Name"]}')

            self.general_logger.warning(f'Clearing Files for: {channel["Name"]}')
            self.cleanup_old_files(channel)
            self.general_logger.warning(f'Finished Clearing Files for channel: {channel["Name"]}')

            channel["Last_Synced"] = datetime.datetime.now().strftime("%d-%m-%y %H:%M:%S")
            self.general_logger.warning(f'Completed processing for channel: {channel["Name"]}')

        except Exception as e:
            self.general_logger.error(f'Error processing channel {channel["Name"]}: {str(e)}')

    def add_channel(self):
        existing_ids = [channel.get("Id", 0) for channel in self.req_channel_list]
        next_id = max(existing_ids, default=-1) + 1
        new_channel = {
            "Id": next_id,
            "Name": "New Channel",
            "Link": "Channel URL",
            "Keep_Days": 28,
            "DL_Days": 14,
            "Last_Synced": "Never",
            "Item_Count": 0,
            "Filter_Title_Text": "",
            "Negate_Filter": False,
            "Media_Type": "Video",
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

    def update_settings(self, data):
        self.media_server_addresses = data["media_server_addresses"]
        self.media_server_tokens = data["media_server_tokens"]
        self.media_server_library_name = data["media_server_library_name"]

        try:
            if data["sync_start_times"] == "":
                raise Exception("No Hours Entered, defaulting to 0 (i.e. 12 am)")
            raw_sync_start_times = [int(re.sub(r"\D", "", start_time.strip())) for start_time in data["sync_start_times"].split(",")]
            temp_sync_start_times = [0 if x < 0 or x > 23 else x for x in raw_sync_start_times]
            cleaned_sync_start_times = sorted(list(set(temp_sync_start_times)))
            self.sync_start_times = cleaned_sync_start_times

        except Exception as e:
            self.general_logger.error(f"Error Updating settings: {str(e)}")
            self.sync_start_times = [0]

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


app = Flask(__name__)
app.secret_key = "secret_key"
socketio = SocketIO(app)
data_handler = DataHandler()


@app.route("/")
def home():
    return render_template("base.html")


@socketio.on("connect")
def connection():
    data = {"Channel_List": data_handler.req_channel_list}
    socketio.emit("update_channel_list", data)


@socketio.on("get_settings")
def get_settings():
    data = {
        "sync_start_times": data_handler.sync_start_times,
        "media_server_addresses": data_handler.media_server_addresses,
        "media_server_tokens": data_handler.media_server_tokens,
        "media_server_library_name": data_handler.media_server_library_name,
    }
    socketio.emit("updated_settings", data)


@socketio.on("save_channel_changes")
def save_channel_changes(channel_to_be_saved):
    data_handler.save_channel_changes(channel_to_be_saved)


@socketio.on("update_settings")
def update_settings(data):
    data_handler.update_settings(data)


@socketio.on("add_channel")
def add_channel():
    data_handler.add_channel()


@socketio.on("remove_channel")
def remove_channel(channel_to_be_removed):
    data_handler.remove_channel(channel_to_be_removed)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
