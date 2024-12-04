import os
import random
from utils import recv_all, log_event
from bitfield_manager import BitfieldManager


class MessageHandler:
    def __init__(self, peer_connection):
        self.peer_connection = peer_connection
        self.peer_process = peer_connection.peer_process

    @staticmethod
    def send_handshake(peer_socket, peer_id):
        handshake_message = b'P2PFILESHARINGPROJ' + b'\x00' * 10 + peer_id.to_bytes(4, 'big')
        peer_socket.sendall(handshake_message)

    @staticmethod
    def receive_handshake(peer_socket):
        message = recv_all(peer_socket, 32)
        if not message:
            return None
        header = message[:18]
        if header != b'P2PFILESHARINGPROJ':
            return None
        peer_id = int.from_bytes(message[28:], 'big')
        return peer_id

    def handle_message(self, message_type, payload):
        if message_type == 0:  # choke
            self.handle_choke()
        elif message_type == 1:  # unchoke
            self.handle_unchoke()
        elif message_type == 2:  # interested
            self.handle_interested()
        elif message_type == 3:  # not interested
            self.handle_not_interested()
        elif message_type == 4:  # have
            self.handle_have(payload)
        elif message_type == 5:  # bitfield
            self.handle_bitfield(payload)
        elif message_type == 6:  # request
            self.handle_request(payload)
        elif message_type == 7:  # piece
            self.handle_piece(payload)
        else:
            print(f"Unknown message type {message_type} from Peer {self.peer_connection.peer_id}")

    def handle_choke(self):
        print(f"Received 'choke' from Peer {self.peer_connection.peer_id}")
        log_event(self.peer_process.peer_id, f"Peer {self.peer_process.peer_id} is choked by Peer {self.peer_connection.peer_id}")
        with self.peer_connection.lock:
            self.peer_connection.peer_choking = True  # This peer is choked by the remote peer
            self.peer_connection.pending_requests.clear()  # Clear any pending requests

    def handle_unchoke(self):
        print(f"Received 'unchoke' from Peer {self.peer_connection.peer_id}")
        log_event(self.peer_process.peer_id, f"Peer {self.peer_process.peer_id} is unchoked by Peer {self.peer_connection.peer_id}")
        with self.peer_connection.lock:
            self.peer_connection.peer_choking = False  # This peer is unchoked by the remote peer
        # Start requesting pieces
        self.request_piece()

    def handle_interested(self):
        print(f"Received 'interested' from Peer {self.peer_connection.peer_id}")
        log_event(self.peer_process.peer_id, f"Peer {self.peer_process.peer_id} received the 'interested' message from Peer {self.peer_connection.peer_id}")
        with self.peer_connection.lock:
            self.peer_connection.is_interested_in_us = True

    def handle_not_interested(self):
        print(f"Received 'not interested' from Peer {self.peer_connection.peer_id}")
        log_event(self.peer_process.peer_id, f"Peer {self.peer_process.peer_id} received the 'not interested' message from Peer {self.peer_connection.peer_id}")
        with self.peer_connection.lock:
            self.peer_connection.is_interested_in_us = False

    def handle_have(self, payload):
        piece_index = int.from_bytes(payload, 'big')
        print(f"Received 'have' from Peer {self.peer_connection.peer_id} for piece {piece_index}")
        log_event(self.peer_process.peer_id,
                  f"Peer {self.peer_process.peer_id} received the 'have' message from Peer {self.peer_connection.peer_id} for the piece {piece_index}")
        # Update the peer's bitfield
        with self.peer_connection.lock:
            self.peer_connection.peer_bitfield[piece_index] = 1

        # Check if the connected peer has the complete file
        with self.peer_connection.lock:
            if all(self.peer_connection.peer_bitfield):
                self.peer_connection.has_complete_file = True

        # Determine if we are now interested
        if not self.peer_process.bitfield_manager.has_piece(piece_index):
            if not self.peer_connection.am_interested_in_peer:
                self.send_interested()
        else:
            # Check if we are no longer interested in any pieces from this peer
            if self.peer_connection.am_interested_in_peer:
                if not self.is_interested_in_peer():
                    self.send_not_interested()

    def handle_bitfield(self, payload):
        self.peer_connection.peer_bitfield = BitfieldManager.decode_bitfield(payload, self.peer_process.num_pieces)
        print(f"Received bitfield from Peer {self.peer_connection.peer_id}: {self.peer_connection.peer_bitfield}")
        log_event(self.peer_process.peer_id,
                  f"Peer {self.peer_process.peer_id} received 'bitfield' message from Peer {self.peer_connection.peer_id}")
        # Determine if we are interested
        if self.is_interested_in_peer():
            self.send_interested()
        else:
            self.send_not_interested()

    def handle_request(self, payload):
        piece_index = int.from_bytes(payload, 'big')
        print(f"Received 'request' from Peer {self.peer_connection.peer_id} for piece {piece_index}")
        log_event(self.peer_process.peer_id,
                  f"Peer {self.peer_process.peer_id} received 'request' message from Peer {self.peer_connection.peer_id} for piece {piece_index}")
        # Send the piece if we have it
        if self.peer_process.bitfield_manager.has_piece(piece_index):
            self.send_piece(piece_index)
        else:
            print(f"Requested piece {piece_index} not found.")

    def handle_piece(self, payload):
        piece_index = int.from_bytes(payload[:4], 'big')
        piece_data = payload[4:]
        print(f"Received 'piece' from Peer {self.peer_connection.peer_id} for piece {piece_index}")
        # Save the piece
        self.save_piece(piece_index, piece_data)
        # Update bitfield
        self.peer_process.bitfield_manager.update_bitfield(piece_index)

        # Remove from pending requests
        with self.peer_connection.lock:
            self.peer_connection.downloaded_bytes += len(piece_data)
            if piece_index in self.peer_connection.pending_requests:
                self.peer_connection.pending_requests.remove(piece_index)
        # Log the event
        num_pieces = self.peer_process.bitfield_manager.count_pieces()
        log_event(self.peer_process.peer_id, f"Peer {self.peer_process.peer_id} has downloaded the piece {piece_index} from Peer {self.peer_connection.peer_id}. Now the number of pieces it has is {num_pieces}")
        # Send 'have' messages to other peers
        self.send_have_to_all(piece_index)
        # Request next piece
        self.request_piece()

        # Check if all pieces are downloaded
        if self.peer_process.bitfield_manager.is_complete():
            self.peer_process.has_complete_file = True  # Update the flag
            self.peer_process.assemble_file_from_pieces()

    def send_interested(self):
        message = (1).to_bytes(4, 'big') + b'\x02'
        self.peer_connection.socket.sendall(message)
        with self.peer_connection.lock:
            self.peer_connection.am_interested_in_peer = True
        print(f"Sent 'interested' to Peer {self.peer_connection.peer_id}")
        log_event(self.peer_process.peer_id,
                  f"Peer {self.peer_process.peer_id} sent 'interested' message to Peer {self.peer_connection.peer_id}")

    def send_not_interested(self):
        message = (1).to_bytes(4, 'big') + b'\x03'
        self.peer_connection.socket.sendall(message)
        with self.peer_connection.lock:
            self.peer_connection.am_interested_in_peer = False
        print(f"Sent 'not interested' to Peer {self.peer_connection.peer_id}")
        log_event(self.peer_process.peer_id,
                  f"Peer {self.peer_process.peer_id} sent 'not interested' message to Peer {self.peer_connection.peer_id}")

    def send_have_to_all(self, piece_index):
        message = (5).to_bytes(4, 'big') + b'\x04' + piece_index.to_bytes(4, 'big')
        with self.peer_process.lock:
            connections = list(self.peer_process.connections.values())
        for conn in connections:
            try:
                conn.socket.sendall(message)
                print(f"Sent 'have' for piece {piece_index} to Peer {conn.peer_id}")
                log_event(self.peer_process.peer_id,
                          f"Peer {self.peer_process.peer_id} sent the 'have' message to Peer {conn.peer_id} for the piece {piece_index}")
            except Exception as e:
                print(f"Error sending 'have' message to Peer {conn.peer_id}: {e}")

    def is_interested_in_peer(self):
        with self.peer_connection.lock:
            peer_bitfield = self.peer_connection.peer_bitfield.copy()
        with self.peer_process.bitfield_manager.lock:
            local_bitfield = self.peer_process.bitfield_manager.local_bitfield.copy()
        for index in range(self.peer_process.num_pieces):
            if peer_bitfield[index] == 1 and local_bitfield[index] == 0:
                return True
        return False

    def request_piece(self):
        if self.peer_connection.peer_choking:
            return
        piece_index = self.select_piece()
        if piece_index is not None:
            message = (5).to_bytes(4, 'big') + b'\x06' + piece_index.to_bytes(4, 'big')  # Request message
            self.peer_connection.socket.sendall(message)
            with self.peer_connection.lock:
                self.peer_connection.pending_requests.append(piece_index)
            print(f"Requested piece {piece_index} from Peer {self.peer_connection.peer_id}")
            log_event(self.peer_process.peer_id, f"Peer {self.peer_process.peer_id} requested piece {piece_index} from Peer {self.peer_connection.peer_id}")
        else:
            # No more pieces needed from this peer
            self.send_not_interested()

    def select_piece(self):
        with self.peer_process.bitfield_manager.lock:
            local_bitfield = self.peer_process.bitfield_manager.local_bitfield.copy()
        with self.peer_connection.lock:
            peer_bitfield = self.peer_connection.peer_bitfield.copy()
        missing_pieces = [
            index for index in range(self.peer_process.num_pieces)
            if local_bitfield[index] == 0 and peer_bitfield[index] == 1
        ]
        if missing_pieces:
            return random.choice(missing_pieces)
        return None

    def send_piece(self, piece_index):
        piece_data = self.get_piece(piece_index)
        if piece_data is None:
            print(f"Could not read piece {piece_index} to send to Peer {self.peer_connection.peer_id}")
            return
        message = (len(piece_data) + 5).to_bytes(4, 'big') + b'\x07' + piece_index.to_bytes(4, 'big') + piece_data
        self.peer_connection.socket.sendall(message)
        print(f"Sent 'piece' {piece_index} to Peer {self.peer_connection.peer_id}")
        log_event(self.peer_process.peer_id, f"Peer {self.peer_process.peer_id} sent piece {piece_index} to Peer {self.peer_connection.peer_id}")

    def get_piece(self, piece_index):
        # Adjust the path to where your pieces are stored
        piece_path = f"peer_{self.peer_process.peer_id}/pieces/{piece_index}.dat"
        try:
            with open(piece_path, 'rb') as piece_file:
                return piece_file.read()
        except FileNotFoundError:
            return None

    def save_piece(self, piece_index, piece_data):
        try:
            dir_path = f"peer_{self.peer_process.peer_id}/pieces"
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            piece_path = os.path.join(dir_path, f"{piece_index}.dat")
            with open(piece_path, 'wb') as piece_file:
                piece_file.write(piece_data)
            print(f"Saved piece {piece_index} to {piece_path}")
        except IOError as e:
            print(f"Error saving piece {piece_index}: {e}")
            log_event(self.peer_process.peer_id, f"Error saving piece {piece_index}: {e}")

