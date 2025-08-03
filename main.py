import os
import subprocess
import uuid
import threading
import json
import time
import re
from flask import Flask, render_template, request, jsonify, Response, send_from_directory

app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'
tasks = {}

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def is_valid_url(url):
    """
    Validates if the URL is from YouTube or Instagram.
    """
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')
    instagram_regex = r'(https?://)?(www\.)?instagram\.com/(p|reel)/[\w-]+'

    return re.match(youtube_regex, url) or re.match(instagram_regex, url)

def run_download(task_id, url, format_choice):
    """
    Runs the yt-dlp download process in a separate thread.
    """
    tasks[task_id]['status'] = 'starting'
    output_template = os.path.join(DOWNLOAD_FOLDER, f'{task_id}.%(ext)s')

    try:
        # Get video metadata to determine filename and extension
        info_command = ['yt-dlp', '--dump-json', '--cookies-from-browser', 'firefox', '--no-warnings', url]
        info_process = subprocess.run(info_command, check=True, capture_output=True, text=True, timeout=60)
        video_info = json.loads(info_process.stdout)
        original_filename = video_info.get('title', 'media')

        # Determine the final extension and filename
        final_ext = format_choice
        if format_choice == 'mp4':
            final_ext = video_info.get('ext', 'mp4')

        tasks[task_id]['filename'] = f"{original_filename}.{final_ext}"

        # Build the command based on format
        command = ['yt-dlp', '--no-check-certificate', '--cookies-from-browser', 'firefox', '--no-warnings']

        if format_choice == 'mp4':
            command.extend([
                '--progress-template', '{"status": "downloading", "progress": %(progress.fraction)s, "eta": %(progress.eta)s, "speed": %(progress.speed_string)s}',
                '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                '-o', output_template
            ])
        else: # Audio formats
            command.extend([
                '--progress-template', '{"status": "downloading", "progress": %(progress.fraction)s, "eta": %(progress.eta)s, "speed": %(progress.speed_string)s, "post_process": true}',
                '--extract-audio',
                '--audio-format', format_choice,
                '--audio-quality', '0', # Best quality
                '-o', output_template
            ])

        command.append(url)

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)

        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    progress_data = json.loads(line)
                    # For audio extraction, yt-dlp might not show progress, but post-processing status
                    if progress_data.get('post_process'):
                        tasks[task_id].update({'status': 'processing', 'message': 'Converting to audio...'})
                    else:
                         tasks[task_id].update(progress_data)
                except json.JSONDecodeError:
                    pass

        process.wait()

        if process.returncode == 0:
            downloaded_file = None
            for file in os.listdir(DOWNLOAD_FOLDER):
                if file.startswith(task_id):
                    downloaded_file = file
                    break

            if downloaded_file:
                tasks[task_id].update({'status': 'complete', 'filepath': os.path.join(DOWNLOAD_FOLDER, downloaded_file)})
            else:
                tasks[task_id].update({'status': 'error', 'message': 'File not found after conversion.'})
        else:
            error_output = process.stderr.read()
            print(f"yt-dlp error: {error_output}")
            tasks[task_id].update({'status': 'error', 'message': f'Download failed. Check URL or format. {error_output[:150]}...'})

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        tasks[task_id].update({'status': 'error', 'message': 'An unexpected server error occurred.'})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    format_choice = request.form.get('format', 'mp4')

    if not url:
        return jsonify({'error': 'No URL provided.'}), 400
    if not is_valid_url(url):
        return jsonify({'error': 'Invalid URL. Only YouTube and Instagram links are supported.'}), 400
    if format_choice not in ['mp4', 'mp3', 'opus', 'wav']:
        return jsonify({'error': 'Invalid format selected.'}), 400

    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'pending', 'progress': 0}

    thread = threading.Thread(target=run_download, args=(task_id, url, format_choice))
    thread.daemon = True
    thread.start()

    return jsonify({'task_id': task_id})

@app.route('/progress/<task_id>')
def progress(task_id):
    def generate():
        while True:
            task = tasks.get(task_id)
            if not task:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Task not found.'})}\n\n"
                break

            yield f"data: {json.dumps(task)}\n\n"

            if task['status'] in ['complete', 'error']:
                time.sleep(5)
                tasks.pop(task_id, None)
                break

            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream')

@app.route('/get-file/<task_id>')
def get_file(task_id):
    task = tasks.get(task_id)
    if not task or task.get('status') != 'complete':
        return "File not available.", 404

    filepath = task.get('filepath')
    filename = task.get('filename', 'media.bin')

    if not filepath or not os.path.exists(filepath):
        return "File not found.", 404

    try:
        return send_from_directory(os.path.dirname(filepath), os.path.basename(filepath), as_attachment=True, download_name=filename)
    finally:
        tasks.pop(task_id, None)
        try:
            os.remove(filepath)
        except OSError as e:
            print(f"Error removing file {filepath}: {e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
