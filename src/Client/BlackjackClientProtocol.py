import struct

class BlackjackClientProtocol:
    """
    protocol logic for Client.
    Implements packing and unpacking of messages according to the Blackjack protocol."""
    
    # --- Constants ---
    MAGIC_COOKIE = 0xabcddcba
    MSG_OFFER = 0x2
    MSG_REQUEST = 0x3
    MSG_PAYLOAD = 0x4
    
    # --- 1. Offer Message (Server -> Broadcast) ---
    # [cite_start]Format: [Magic 4] [Type 1] [Port 2] [Name 32] [cite: 85-90]

    @staticmethod
    def unpack_offer(data):
        """Used by Client to find the Server."""
        if len(data) < 39:
            raise ValueError("Offer packet too short")
            
        cookie, msg_type, server_port, name_bytes = struct.unpack('!I B H 32s', data[:39])
        
        if cookie != BlackjackClientProtocol.MAGIC_COOKIE:
            raise ValueError("Invalid Magic Cookie")
        if msg_type != BlackjackClientProtocol.MSG_OFFER:
            raise ValueError("Invalid Message Type (Expected Offer)")
            
        server_name = name_bytes.decode('utf-8').strip('\x00')
        return server_port, server_name

    # --- 2. Request Message (Client -> Server) ---
    # [cite_start]Format: [Magic 4] [Type 1] [Rounds 1] [Name 32] [cite: 91-95]

    @staticmethod
    def pack_request(rounds, team_name):
        """Used by Client to initiate a game."""
        name_bytes = team_name.encode('utf-8')[:32].ljust(32, b'\x00')
        return struct.pack('!I B B 32s', 
                           BlackjackClientProtocol.MAGIC_COOKIE, 
                           BlackjackClientProtocol.MSG_REQUEST, 
                           rounds, 
                           name_bytes)


    # --- 3. Payload: Game Status / Card (Server -> Client) ---
    # [cite_start]Format: [Magic 4] [Type 1] [Result 1] [Rank 2] [Suit 1] [cite: 96, 101-103]
    @staticmethod
    def unpack_payload_server(data):
        """Used by Client to read cards or game results."""
        if len(data) < 9: # 4 + 1 + 1 + 2 + 1 = 9 bytes
            raise ValueError("Server Payload packet too short")
            
        cookie, msg_type, result_code, card_rank, card_suit = struct.unpack('!I B B H B', data[:9])
        
        if cookie != BlackjackClientProtocol.MAGIC_COOKIE:
            raise ValueError("Invalid Magic Cookie")
        if msg_type != BlackjackClientProtocol.MSG_PAYLOAD:
            raise ValueError("Invalid Message Type (Expected Payload)")
            
        return result_code, card_rank, card_suit

    # --- 4. Payload: Player Action (Client -> Server) ---
    # [cite_start]Format: [Magic 4] [Type 1] [Decision 5] [cite: 96, 100]

    @staticmethod
    def pack_player_decision(decision):
        """Used by Client to send Hit/Stand decision."""
        # Map logical commands to protocol strings
        decision_map = { "Hit": "Hittt", "Stand": "Stand" }
        normalized_decision = decision.strip().title()
        
        if normalized_decision not in decision_map:
            raise ValueError(f"Invalid input: '{decision}'. Expected 'Hit' or 'Stand'.")
        
        protocol_string = decision_map[normalized_decision]
        
        return struct.pack('!I B 5s',
                           BlackjackClientProtocol.MAGIC_COOKIE,
                           BlackjackClientProtocol.MSG_PAYLOAD,
                           protocol_string.encode('utf-8'))