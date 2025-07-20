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
        flash('No URL provided.', 'error')
        return redirect(url_for('index'))

    # A more robust check for Instagram URLs
    if not ('instagram.com/p/' in url or 'instagram.com/reel/' in url):
        flash('Invalid Instagram URL. Please use a valid post or reel link.', 'error')
        return redirect(url_for('index'))

    video_id = str(uuid.uuid4())
    # Note: yt-dlp will add the extension, so we just provide the base name.
    output_template = os.path.join(DOWNLOAD_FOLDER, f'{video_id}.%(ext)s')

    try:
        # Improved yt-dlp command
        command = [
            'yt-dlp',
            '--no-check-certificate',
            '--quiet',  # Suppress verbose output
            '--progress', # Show progress in logs, not to user
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '-o', output_template,
            url
        ]

        # Using subprocess.run for better error handling
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=300)

        # Find the downloaded file
        actual_filename = None
        for file in os.listdir(DOWNLOAD_FOLDER):
            if file.startswith(video_id):
                actual_filename = file
                break

        if actual_filename:
             return send_from_directory(DOWNLOAD_FOLDER, actual_filename, as_attachment=True)
        else:
            # This case might happen if yt-dlp succeeds but no file is found
            flash('Download succeeded, but the file could not be found on the server.', 'error')
            return redirect(url_for('index'))

    except subprocess.CalledProcessError as e:
        # Extract a more user-friendly error message from yt-dlp's output
        error_output = e.stderr.strip()
        if "Unsupported URL" in error_output:
            flash("The provided URL is not supported by yt-dlp.", 'error')
        elif "Private video" in error_output:
            flash("This is a private video and cannot be downloaded.", 'error')
        else:
            # Generic error for other cases
            flash('Failed to download the video. The content may be private or the link is incorrect.', 'error')
        print(f"yt-dlp error: {error_output}") # Log the full error for debugging
        return redirect(url_for('index'))
    except subprocess.TimeoutExpired:
        flash('The download timed out. The video may be too large or the network is slow.', 'error')
        return redirect(url_for('index'))
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        flash('An unexpected error occurred. Please try again.', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
