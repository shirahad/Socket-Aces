import struct

class BlackjackServerProtocol:
    """
    Protocol logic for Server.
    Handles all packet formatting and strict validation.
    """
    
    # --- Constants ---
    MAGIC_COOKIE = 0xabcddcba
    MSG_OFFER = 0x2
    MSG_REQUEST = 0x3
    MSG_PAYLOAD = 0x4
    
    # --- 1. Offer Message (Server -> Broadcast) ---
    # Format: [Magic 4] [Type 1] [Port 2] [Name 32]

    @staticmethod
    def pack_offer(server_port, server_name):
        """Used by Server to broadcast availability."""
        name_bytes = server_name.encode('utf-8')[:32].ljust(32, b'\x00')
        return struct.pack('!I B H 32s', 
                           BlackjackServerProtocol.MAGIC_COOKIE, 
                           BlackjackServerProtocol.MSG_OFFER, 
                           server_port, 
                           name_bytes)

    @staticmethod
    def unpack_request(data):
        """Used by Server to accept a game."""
        if len(data) < 38:
            raise ValueError("Request packet too short")
            
        cookie, msg_type, rounds, name_bytes = struct.unpack('!I B B 32s', data[:38])
        
        if cookie != BlackjackServerProtocol.MAGIC_COOKIE:
            raise ValueError("Invalid Magic Cookie")
        if msg_type != BlackjackServerProtocol.MSG_REQUEST:
            raise ValueError("Invalid Message Type (Expected Request)")
            
        team_name = name_bytes.decode('utf-8').strip('\x00')
        return rounds, team_name

    # --- 3. Payload: Game Status / Card (Server -> Client) ---
    # Format: [Magic 4] [Type 1] [Result 1] [Rank 2] [Suit 1]

    @staticmethod
    def pack_payload_server(result_code, card_rank=0, card_suit=0):
        """Used by Server to send cards or game results."""
        return struct.pack('!I B B H B',
                           BlackjackServerProtocol.MAGIC_COOKIE,
                           BlackjackServerProtocol.MSG_PAYLOAD,
                           result_code,
                           card_rank,
                           card_suit)

    @staticmethod
    def unpack_player_decision(data):
        """Used by Server to read player decision."""
        if len(data) < 10: # 4 + 1 + 5 = 10 bytes
            raise ValueError("Player Payload packet too short")
            
        cookie, msg_type, decision_bytes = struct.unpack('!I B 5s', data[:10])
        
        if cookie != BlackjackServerProtocol.MAGIC_COOKIE:
            raise ValueError("Invalid Magic Cookie")
        if msg_type != BlackjackServerProtocol.MSG_PAYLOAD:
            raise ValueError("Invalid Message Type (Expected Payload)")
            
        raw_decision = decision_bytes.decode('utf-8').strip('\x00')
        
        if raw_decision == "Hittt":
            return "Hit"
        elif raw_decision == "Stand":
            return "Stand"
        else:
            raise ValueError(f"Protocol Violation: Expected 'Hittt' or 'Stand', got '{raw_decision}'")