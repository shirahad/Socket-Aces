"""
Shared protocol constants for Blackjack Client/Server communication.
All magic numbers and message types are defined here to ensure consistency.
"""

# Magic Cookie - Used to validate all packets
MAGIC_COOKIE = 0xabcddcba

# Message Types
MSG_OFFER = 0x2      # Server -> Broadcast (UDP)
MSG_REQUEST = 0x3    # Client -> Server (TCP handshake)
MSG_PAYLOAD = 0x4    # Bidirectional game data (TCP)

# Result Codes (sent in Payload packets)
RESULT_CONTINUE = 0x0  # Game still in progress, card attached
RESULT_TIE = 0x1       # Round ended in a tie
RESULT_LOSS = 0x2      # Player lost
RESULT_WIN = 0x3       # Player won

# Packet Sizes (bytes)
OFFER_PACKET_SIZE = 39      # 4 + 1 + 2 + 32
REQUEST_PACKET_SIZE = 38    # 4 + 1 + 1 + 32
SERVER_PAYLOAD_SIZE = 9     # 4 + 1 + 1 + 2 + 1
CLIENT_PAYLOAD_SIZE = 10    # 4 + 1 + 5

# Card Constants
VALID_RANKS = range(1, 14)  # 1-13 (Ace through King)
VALID_SUITS = range(0, 4)   # 0-3 (Hearts, Diamonds, Clubs, Spades)
