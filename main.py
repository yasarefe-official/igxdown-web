import os
import subprocess
import uuid
import threading
import json
import time
from flask import Flask, render_template, request, jsonify, Response

app = Flask(__name__)
DOWNLOAD_FOLDER = 'downloads'

# In-memory store for task progress and results.
# In a production app, you'd use a more robust solution like Redis.
tasks = {}

if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def run_download(task_id, url):
    """
    Runs the yt-dlp download process in a separate thread.
    Updates the task status in the global `tasks` dictionary.
    """
    output_template = os.path.join(DOWNLOAD_FOLDER, f'{task_id}.%(ext)s')

    # Command to get video metadata first
    info_command = ['yt-dlp', '--dump-json', url]
    try:
        info_process = subprocess.run(info_command, check=True, capture_output=True, text=True, timeout=60)
        video_info = json.loads(info_process.stdout)
        original_filename = video_info.get('title', 'video')
        tasks[task_id]['filename'] = f"{original_filename}.{video_info.get('ext', 'mp4')}"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"Error getting video info: {e}")
        tasks[task_id].update({'status': 'error', 'message': 'Could not retrieve video information.'})
        return

    # Command to download the video with progress reporting
    command = [
        'yt-dlp',
        '--no-check-certificate',
        '--progress-template', '{"status": "downloading", "progress": %(progress.fraction)s, "eta": %(progress.eta)s, "speed": %(progress.speed_string)s}',
        '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        '-o', output_template,
        url,
    ]

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

        # Capture stdout for progress
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    progress_data = json.loads(line)
                    tasks[task_id].update(progress_data)
                except json.JSONDecodeError:
                    # Ignore lines that are not valid JSON
                    pass

        process.wait()

        if process.returncode == 0:
            # Find the actual filename after download
            downloaded_file = None
            for file in os.listdir(DOWNLOAD_FOLDER):
                if file.startswith(task_id):
                    downloaded_file = file
                    break

            if downloaded_file:
                tasks[task_id].update({'status': 'complete', 'filepath': os.path.join(DOWNLOAD_FOLDER, downloaded_file)})
            else:
                tasks[task_id].update({'status': 'error', 'message': 'File not found after download.'})
        else:
            error_output = process.stderr.read()
            print(f"yt-dlp error: {error_output}")
            tasks[task_id].update({'status': 'error', 'message': f'Download failed. {error_output[:200]}...'})

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        tasks[task_id].update({'status': 'error', 'message': 'An unexpected error occurred during download.'})


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    if not url:
        return jsonify({'error': 'No URL provided.'}), 400

    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'starting', 'progress': 0}

    # Start the download in a background thread
    thread = threading.Thread(target=run_download, args=(task_id, url))
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
                # Clean up the task entry after a short delay
                time.sleep(5)
                tasks.pop(task_id, None)
                break

            time.sleep(1)

    return Response(generate(), mimetype='text/event-stream')

@app.route('/get-file/<task_id>')
def get_file(task_id):
    task = tasks.get(task_id)
    if not task or task.get('status') != 'complete':
        return "File not available or download not complete.", 404

    filepath = task.get('filepath')
    filename = task.get('filename', 'video.mp4') # Use the fetched filename

    if not filepath or not os.path.exists(filepath):
        return "File not found.", 404

    try:
        return send_from_directory(os.path.dirname(filepath), os.path.basename(filepath), as_attachment=True, attachment_filename=filename)
    finally:
        # Clean up the task and the file after sending
        tasks.pop(task_id, None)
        # Optional: remove file after download
        # os.remove(filepath)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
