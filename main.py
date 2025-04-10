from flask import Flask, render_template, request, jsonify, Response
import json
import time
import threading
import requests
import random
from uuid import uuid4
import os
from  import Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = str(uuid4())

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE = os.getenv('TWILIO_PHONE')
YOUR_PHONE = 'whatsapp:+91XXXXXXXXXX'  # अपना व्हाट्सएप नंबर डालें

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Global tasks tracker
active_tasks = {}
task_logs = {}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"
]

def send_whatsapp_notification(message):
    try:
        client.messages.create(
            body=message,
            from_=f'whatsapp:{TWILIO_PHONE}',
            to=YOUR_PHONE
        )
    except Exception as e:
        print(f"WhatsApp notification failed: {str(e)}")

def facebook_comment_task(task_id, data):
    global active_tasks, task_logs
    cookies = json.loads(data['cookies'])
    comments = [line.strip() for line in data['comments'] if line.strip()]
    
    active_tasks[task_id] = {
        'status': 'running',
        'total': len(comments),
        'success': 0,
        'failed': 0,
        'cookies_used': len(cookies)
    }
    
    try:
        for idx, comment in enumerate(comments):
            if not active_tasks[task_id]['status'] == 'running':
                break
                
            cookie = random.choice(cookies)
            full_comment = f"{data['prefix']} {comment} {data['suffix']}"
            
            try:
                headers = {
                    'authority': 'mbasic.facebook.com',
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,/;q=0.8',
                    'user-agent': random.choice(USER_AGENTS),
                    'cookie': cookie
                }
                
                response = requests.get(
                    f"https://mbasic.facebook.com/{data['post_id']}",
                    headers=headers,
                    timeout=30
                )
                
                # Anti-block technique
                time.sleep(random.randint(1, 5))
                
                fb_dtsg = re.search('name="fb_dtsg" value="([^"]+)"', response.text).group(1)
                jazoest = re.search('name="jazoest" value="([^"]+)"', response.text).group(1)
                action = re.search('method="post" action="([^"]+)"', response.text).group(1)
                
                response = requests.post(
                    f"https://mbasic.facebook.com{action}",
                    headers=headers,
                    data={
                        'fb_dtsg': fb_dtsg,
                        'jazoest': jazoest,
                        'comment_text': full_comment,
                        'comment': 'Post'
                    },
                    allow_redirects=False
                )
                
                if response.status_code == 302 and 'location' in response.headers:
                    active_tasks[task_id]['success'] += 1
                    log_msg = f"Success: {full_comment}"
                else:
                    active_tasks[task_id]['failed'] += 1
                    log_msg = f"Failed: {full_comment}"
                
            except Exception as e:
                active_tasks[task_id]['failed'] += 1
                log_msg = f"Error: {str(e)}"
            
            task_logs[task_id].append(log_msg)
            time.sleep(data['delay'])
            
        active_tasks[task_id]['status'] = 'completed'
        send_whatsapp_notification(
            f"Task {task_id} completed!\nSuccess: {active_tasks[task_id]['success']}\nFailed: {active_tasks[task_id]['failed']}"
        )
        
    except Exception as e:
        active_tasks[task_id]['status'] = 'error'
        task_logs[task_id].append(f"Critical Error: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_task():
    task_id = str(uuid4())
    
    try:
        data = {
            'post_id': request.form['post_id'],
            'prefix': request.form['prefix'],
            'suffix': request.form['suffix'],
            'delay': int(request.form['delay']),
            'cookies': request.form['cookies'],
            'comments': request.files['comments_file'].read().decode('utf-8').splitlines()
        }
        
        task_logs[task_id] = []
        threading.Thread(target=facebook_comment_task, args=(task_id, data)).start()
        
        return jsonify({
            'status': 'started',
            'task_id': task_id
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/stop/<task_id>')
def stop_task(task_id):
    if task_id in active_tasks:
        active_tasks[task_id]['status'] = 'stopped'
        return jsonify({'status': 'stopped'})
    return jsonify({'status': 'not_found'})

@app.route('/status/<task_id>')
def task_status(task_id):
    return jsonify(active_tasks.get(task_id, {}))

@app.route('/logs/<task_id>')
def get_logs(task_id):
    return Response(json.dumps(task_logs.get(task_id, [])), mimetype='application/json')

if __name__ == '__main__':
    app.run(debug=True, port=4000)