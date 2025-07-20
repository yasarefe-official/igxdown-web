import os
import subprocess
import uuid
from flask import Flask, render_template, request, send_from_directory, flash, redirect, url_for

app = Flask(__name__)
app.secret_key = os.urandom(24)
DOWNLOAD_FOLDER = 'downloads'

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    if not url:
        flash('No URL provided.')
        return redirect(url_for('index'))

    # Sanitize the URL to prevent command injection
    if not (url.startswith('https://www.instagram.com/') or url.startswith('http://www.instagram.com/')):
        flash('Invalid Instagram URL.')
        return redirect(url_for('index'))

    video_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_FOLDER, f'{video_id}.mp4')

    try:
        command = [
            'yt-dlp',
            '--ffmpeg-location', '/usr/bin/ffmpeg', # Specify ffmpeg path explicitly
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '-o', output_template,
            url
        ]

        # Using subprocess.run for better error handling
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=300) # 5-minute timeout

        # Find the downloaded file (yt-dlp might add a suffix)
        actual_filename = None
        for file in os.listdir(DOWNLOAD_FOLDER):
            if file.startswith(video_id):
                actual_filename = file
                break

        if actual_filename:
             return send_from_directory(DOWNLOAD_FOLDER, actual_filename, as_attachment=True)
        else:
            flash('Could not find downloaded video file.')
            return redirect(url_for('index'))

    except subprocess.CalledProcessError as e:
        # Log the error for debugging
        print(f"Error downloading video: {e.stderr}")
        flash(f'Error downloading video. Please check the URL and try again. Details: {e.stderr}')
        return redirect(url_for('index'))
    except subprocess.TimeoutExpired:
        flash('The download process timed out. The video might be too large or the server is slow.')
        return redirect(url_for('index'))
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        flash('An unexpected error occurred. Please try again later.')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
