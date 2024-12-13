from flask import Flask, render_template, jsonify
from flask_sock import Sock
import uuid
import json
import os

app = Flask(__name__)
sock = Sock(app)

# Store room information
rooms = {}
# Store client information
clients = {}


def generate_room_code():
    """Generate a 6-character alphanumeric room code"""
    return uuid.uuid4().hex[:6].upper()



@app.route('/')
def home():
    return render_template('index.html')



@app.route('/api/rooms/create')
def create_room():
    """Create a new room and return the room code"""
    room_code = generate_room_code()
    while room_code in rooms:  # Ensure unique code
        room_code = generate_room_code()
    
    rooms[room_code] = {
        'clients': {},
        'canvas_state': []  # Store canvas state for late joiners
    }
    
    return jsonify({
        'success': True,
        'room_code': room_code
    })



@app.route('/api/rooms/join/<room_code>')
def join_room(room_code):
    """Validate if a room exists"""
    if room_code in rooms:
        return jsonify({
            'success': True,
            'active_users': len(rooms[room_code]['clients'])
        })
    return jsonify({
        'success': False,
        'message': 'Room not found'
    })



@sock.route('/ws/room/<room_code>')
def websocket(ws, room_code):
    """Handle WebSocket connections for a specific room"""
    if room_code not in rooms:
        ws.send(json.dumps({
            'type': 'error',
            'message': 'Room not found'
        }))
        return
    
    client_id = str(uuid.uuid4())
    clients[client_id] = {
        'websocket': ws,
        'username': f'User_{client_id[:8]}',
        'room': room_code
    }
    rooms[room_code]['clients'][client_id] = clients[client_id]
    
    try:
        # Send current canvas state to new user
        if rooms[room_code]['canvas_state']:
            ws.send(json.dumps({
                'type': 'canvas_state',
                'data': rooms[room_code]['canvas_state']
            }))
        
        broadcast_to_room(
            {'type': 'user_joined', 'username': clients[client_id]['username']},
            None,
            room_code
        )
        
        while True:
            try:
                message = json.loads(ws.receive())
                
                if message['type'] == 'username_change':
                    old_username = clients[client_id]['username']
                    new_username = message['username']
                    clients[client_id]['username'] = new_username
                    rooms[room_code]['clients'][client_id]['username'] = new_username
                    broadcast_to_room({
                        'type': 'system_message',
                        'message': f"{old_username} changed name to {new_username}"
                    }, None, room_code)
                
                elif message['type'] == 'draw':
                    # Store drawing data
                    stroke_data = message['data']
                    rooms[room_code]['canvas_state'].append(stroke_data)
                    
                    # Broadcast to all clients in room (including sender for confirmation)
                    broadcast_to_room({
                        'type': 'draw',
                        'data': stroke_data
                    }, None, room_code)
                
                elif message['type'] == 'clear_canvas':
                    rooms[room_code]['canvas_state'] = []
                    broadcast_to_room({
                        'type': 'clear_canvas',
                        'username': clients[client_id]['username']
                    }, None, room_code)
                
                elif message['type'] == 'chat':
                    broadcast_to_room({
                        'type': 'chat',
                        'username': clients[client_id]['username'],
                        'message': message['message']
                    }, None, room_code)
                    
            except Exception as e:
                print(f"Error handling message: {e}")
                break
                
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if client_id in clients:
            broadcast_to_room({
                'type': 'user_left',
                'username': clients[client_id]['username']
            }, None, room_code)
            
            # Cleanup
            del rooms[room_code]['clients'][client_id]
            del clients[client_id]
            
            # Remove room if empty
            if not rooms[room_code]['clients']:
                del rooms[room_code]



def broadcast_to_room(message, sender_id, room_code):
    """Send message to all clients in a room"""
    if room_code not in rooms:
        return
        
    for client_id, client_info in list(rooms[room_code]['clients'].items()):
        if sender_id and client_id == sender_id:
            continue
        try:
            client_info['websocket'].send(json.dumps(message))
        except Exception:
            # Clean up disconnected client
            del rooms[room_code]['clients'][client_id]
            if client_id in clients:
                del clients[client_id]

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)