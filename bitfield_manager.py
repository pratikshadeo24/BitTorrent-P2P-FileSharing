import math

class BitfieldManager:
    def __init__(self, num_pieces):
        self.num_pieces = num_pieces
        self.local_bitfield = [0] * num_pieces

    def set_all(self):
        self.local_bitfield = [1] * self.num_pieces

    def update_bitfield(self, piece_index):
        self.local_bitfield[piece_index] = 1

    def is_complete(self):
        return all(self.local_bitfield)

    def has_piece(self, piece_index):
        return self.local_bitfield[piece_index] == 1

    def count_pieces(self):
        return sum(self.local_bitfield)

    def generate_bitfield_message(self):
        bitfield_bytes = self.encode_bitfield(self.local_bitfield)
        message_length = (1 + len(bitfield_bytes)).to_bytes(4, 'big')
        message_type = b'\x05'  # bitfield type is 5
        return message_length + message_type + bitfield_bytes

    @staticmethod
    def encode_bitfield(bitfield):
        bitfield_bytes = bytearray()
        for byte_index in range(0, len(bitfield), 8):
            byte = 0
            for i in range(8):
                if byte_index + i < len(bitfield) and bitfield[byte_index + i] == 1:
                    byte |= 1 << (7 - i)
            bitfield_bytes.append(byte)
        return bytes(bitfield_bytes)

    @staticmethod
    def decode_bitfield(bitfield_bytes, num_pieces):
        bitfield = []
        total_bits = num_pieces
        for byte in bitfield_bytes:
            for i in range(8):
                if len(bitfield) < total_bits:
                    bitfield.append((byte >> (7 - i)) & 1)
        return bitfield
