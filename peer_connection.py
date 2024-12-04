import threading
from message_handler import MessageHandler
from utils import recv_all, log_event

class PeerConnection:
    def __init__(self, peer_id, socket, peer_process):
        self.peer_id = peer_id
        self.socket = socket
        self.peer_process = peer_process
        self.is_choked = True
        self.peer_choking = True
        # self.is_interested = False
        self.is_interested_in_us = False  # Remote peer is interested in us
        self.am_interested_in_peer = False  # We are interested in the remote peer
        self.peer_bitfield = [0] * self.peer_process.num_pieces
        self.pending_requests = []
        self.lock = threading.Lock()
        self.message_handler = MessageHandler(self)
        self.downloaded_bytes = 0  # Bytes downloaded in the current interval
        self.download_rate = 0  # Download rate in bytes per second
        self.has_complete_file = False  # Indicates if the peer has the complete file
        # Send bitfield
        self.send_bitfield()
        print(f"Sent bitfield to Peer {self.peer_id}")

        # Start a thread to handle messages from this peer
        threading.Thread(target=self.handle_messages, daemon=True).start()



    def send_bitfield(self):
        bitfield_message = self.peer_process.bitfield_manager.generate_bitfield_message()
        self.socket.sendall(bitfield_message)
        print(f"Sent bitfield to Peer {self.peer_id}")

    def handle_messages(self):
        while True:
            try:
                # Read the message length
                length_bytes = recv_all(self.socket, 4)
                if not length_bytes:
                    print(f"Connection to Peer {self.peer_id} closed.")
                    break
                message_length = int.from_bytes(length_bytes, 'big')

                # Read the message type
                message_type_byte = recv_all(self.socket, 1)
                if not message_type_byte:
                    print(f"Connection to Peer {self.peer_id} closed.")
                    break
                message_type = message_type_byte[0]

                # Read the message payload
                payload_length = message_length - 1
                payload = b''
                if payload_length > 0:
                    payload = recv_all(self.socket, payload_length)
                    if not payload:
                        print(f"Connection to Peer {self.peer_id} closed.")
                        break

                # Process the message
                self.message_handler.handle_message(message_type, payload)
            except (ConnectionAbortedError, ConnectionResetError, ConnectionError, OSError) as e:
                print(f"Connection to Peer {self.peer_id} was closed: {e}")
                # Optionally log the event
                log_event(self.peer_process.peer_id, f"Connection to Peer {self.peer_id} was closed.")
                break
            except Exception as e:
                print(f"Error handling messages from Peer {self.peer_id}: {e}")
                import traceback
                traceback.print_exc()
                break
        # Peer has disconnected
        with self.peer_process.lock:
            if self.peer_id in self.peer_process.connections:
                del self.peer_process.connections[self.peer_id]
        self.socket.close()
        print(f"Connection to Peer {self.peer_id} closed.")
        log_event(self.peer_process.peer_id, f"Peer {self.peer_process.peer_id} disconnected from Peer {self.peer_id}")

    def send_choke(self):
        message = (1).to_bytes(4, 'big') + b'\x00'  # Choke message
        self.socket.sendall(message)
        with self.lock:
            self.is_choked = True
        print(f"Sent 'choke' to Peer {self.peer_id}")
        log_event(self.peer_process.peer_id, f"Peer {self.peer_process.peer_id} choked Peer {self.peer_id}")

    def send_unchoke(self):
        message = (1).to_bytes(4, 'big') + b'\x01'  # Unchoke message
        self.socket.sendall(message)
        with self.lock:
            self.is_choked = False
        print(f"Sent 'unchoke' to Peer {self.peer_id}")
        log_event(self.peer_process.peer_id, f"Peer {self.peer_process.peer_id} unchoked Peer {self.peer_id}")

    def close(self):
        try:
            self.socket.close()
        except Exception as e:
            print(f"Error closing connection to Peer {self.peer_id}: {e}")
            # Remove the connection from self.peer_process.connections without holding self.peer_process.lock
        with self.peer_process.lock:
            if self.peer_id in self.peer_process.connections:
                del self.peer_process.connections[self.peer_id]
