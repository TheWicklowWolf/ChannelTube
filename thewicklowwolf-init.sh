#!/bin/sh

echo -e "\033[1;32mTheWicklowWolf\033[0m"
echo -e "\033[1;34mChannelTube\033[0m"
echo "Initializing app..."

cat << 'EOF'
_____________________________________

               .-'''''-.             
             .'         `.           
            :             :          
           :               :         
           :      _/|      :         
            :   =/_/      :          
             `._/ |     .'           
          (   /  ,|...-'             
           \_/^\/||__                
       _/~  `""~`"` \_               
     __/  -'/  `-._ `\_\__           
    /    /-'`  `\   \  \-.\          
_____________________________________
Brought to you by TheWicklowWolf   
_____________________________________

If you'd like to buy me a coffee:
https://buymeacoffee.com/thewicklow

EOF

echo "-----------------"
echo -e "\033[1mInstalled Versions\033[0m"
# Get the version of yt-dlp
echo -n "yt-dlp: "
pip show yt-dlp | grep Version: | awk '{print $2}'

# Get the version of ffmpeg
echo -n "FFmpeg: "
ffmpeg -version | head -n 1 | awk '{print $3}'
echo "-----------------"

PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "-----------------"
echo -e "\033[1mRunning with:\033[0m"
echo "PUID=${PUID}"
echo "PGID=${PGID}"
echo "-----------------"

# Create the required directories with the correct permissions
echo "Setting up directories.."
mkdir -p /channeltube/downloads /channeltube/audio_downloads /channeltube/config /channeltube/cache
chown -R ${PUID}:${PGID} /channeltube

# Set XDG_CACHE_HOME to use the cache directory
export XDG_CACHE_HOME=/channeltube/cache

# Nightly yt-dlp auto update
auto_update_hour=${auto_update_hour:--1}
if [ "$auto_update_hour" -ge 0 ] 2>/dev/null && [ "$auto_update_hour" -le 23 ]; then
    echo "Nightly auto-update enabled at hour: $auto_update_hour"
    (
        LAST_RUN_DAY=""
        while true; do
            CURRENT_HOUR=$(date +%H)
            CURRENT_DAY=$(date +%Y-%m-%d)
            CURRENT_HOUR=${CURRENT_HOUR#0}
            CURRENT_HOUR=${CURRENT_HOUR:-0}
            if [ "$CURRENT_HOUR" -eq "$auto_update_hour" ] && [ "$CURRENT_DAY" != "$LAST_RUN_DAY" ]; then
                echo "----------------------------------------"
                echo "Running nightly yt-dlp update..."
                echo "Current version:"
                yt-dlp --version
                pip install --no-cache-dir -U --pre "yt-dlp[default]"
                echo "Updated version:"
                yt-dlp --version
                echo "----------------------------------------"
                LAST_RUN_DAY="$CURRENT_DAY"
            fi
            sleep 600
        done
    ) &
else
    echo "Nightly auto-update disabled."
fi

# Start the application with the specified user permissions
echo "Running ChannelTube..."
exec su-exec ${PUID}:${PGID} gunicorn src.ChannelTube:app -c gunicorn_config.py
