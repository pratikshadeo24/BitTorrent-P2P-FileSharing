import os
from datetime import datetime

def recv_all(sock, length):
    data = b''
    while len(data) < length:
        packet = sock.recv(length - len(data))
        if not packet:
            return None
        data += packet
    return data

def log_event(peer_id, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}]: {message}\n"
    log_file = f"logs/log_peer_{peer_id}.log"
    with open(log_file, 'a') as f:
        f.write(log_message)
