from flask import Flask, render_template
from flask_sock import Sock
import uuid
import json
import os

app = Flask(__name__)
sock = Sock(app)

# Store client information
clients = {}

@app.route('/')
def home():
    return render_template('index.html')

@sock.route('/ws')
def websocket(ws):
    client_id = str(uuid.uuid4())
    clients[client_id] = {
        'websocket': ws,
        'username': f'User_{client_id[:8]}'
    }
    
    try:
        broadcast(f"[SERVER] {clients[client_id]['username']} joined the chat", client_id)
        
        while True:
            try:
                raw_message = ws.receive()
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    message = {'type': 'text', 'content': raw_message}
                
                if message.get('type') == 'username':
                    new_username = message.get('username', '').strip()
                    old_username = clients[client_id]['username']
                    clients[client_id]['username'] = new_username
                    broadcast(f"[SERVER] {old_username} changed name to {new_username}", client_id)
                
                elif message.get('type') == 'draw':
                    broadcast_to_others(message, client_id)
                
                elif message.get('type') == 'clear':
                    broadcast_to_others({'type': 'clear'}, client_id)
                    broadcast(f"[SERVER] {clients[client_id]['username']} cleared the canvas", client_id)
                
                elif message.get('type') == 'text':
                    broadcast(f"[{clients[client_id]['username']}] {message['content']}", client_id)
                    
            except Exception as e:
                print(f"Error receiving message: {e}")
                break
                
    except Exception as e:
        print(f"Error in websocket handler: {e}")
    finally:
        if client_id in clients:
            broadcast(f"[SERVER] {clients[client_id]['username']} left the chat", client_id)
            del clients[client_id]

def broadcast_to_others(message, sender_id):
    """Broadcast to all clients except the sender"""
    for client_id, client_info in list(clients.items()):
        if client_id != sender_id:
            try:
                client_info['websocket'].send(json.dumps({
                    'type': 'received',
                    'data': message
                }))
            except Exception:
                if client_id in clients:
                    del clients[client_id]

def broadcast(message, sender_id=None):
    """Broadcast text message to all clients"""
    for client_id, client_info in list(clients.items()):
        try:
            msg_type = 'sent' if client_id == sender_id else 'received'
            client_info['websocket'].send(json.dumps({
                'type': msg_type,
                'data': message
            }))
        except Exception:
            if client_id in clients:
                del clients[client_id]

if __name__ == '__main__':
    # port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=5000)