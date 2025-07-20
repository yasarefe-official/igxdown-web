import os
import subprocess
import uuid
from flask import Flask, render_template, request, send_from_directory, flash, redirect, url_for

app = Flask(__name__)
app.secret_key = os.urandom(24)
DOWNLOAD_FOLDER = 'downloads'
INSTAGRAM_SESSION_ID = os.environ.get('INSTAGRAM_SESSION_ID')

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    if not url:
        flash('No URL provided.', 'error')
        return redirect(url_for('index'))

    if not ('instagram.com/p/' in url or 'instagram.com/reel/' in url):
        flash('Invalid Instagram URL. Please use a valid post or reel link.', 'error')
        return redirect(url_for('index'))

    video_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_FOLDER, f'{video_id}.%(ext)s')

    try:
        command = [
            'yt-dlp',
            '--no-check-certificate',
            '--quiet',
            '--progress',
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '-o', output_template,
        ]

        if INSTAGRAM_SESSION_ID:
            command.extend(['--add-header', f'Cookie: sessionid={INSTAGRAM_SESSION_ID}'])

        command.append(url)

        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)

        actual_filename = None
        for file in os.listdir(DOWNLOAD_FOLDER):
            if file.startswith(video_id):
                actual_filename = file
                break

        if actual_filename:
             return send_from_directory(DOWNLOAD_FOLDER, actual_filename, as_attachment=True)
        else:
            flash('Download succeeded, but the file could not be found on the server.', 'error')
            return redirect(url_for('index'))

    except subprocess.CalledProcessError as e:
        error_output = e.stderr.strip()
        if "login is required" in error_output.lower() or "private user" in error_output.lower():
             flash("This content is private and requires a session ID to download. Please set the INSTAGRAM_SESSION_ID environment variable on the server.", 'error')
        elif "unsupported url" in error_output.lower():
            flash("The provided URL is not supported.", 'error')
        else:
            flash('Failed to download the video. The content may be private or the link is incorrect.', 'error')
        print(f"yt-dlp error: {error_output}")
        return redirect(url_for('index'))
    except subprocess.TimeoutExpired:
        flash('The download timed out. The video may be too large or the network is slow.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    # Add a note for local development
    if not INSTAGRAM_SESSION_ID:
        print("\n[NOTE] INSTAGRAM_SESSION_ID environment variable is not set. Downloads for private content may fail.\n")
    app.run(host='0.0.0.0', port=10000)
