import socket, struct, threading, time, random

class BlackjackServer:
    def __init__(self, team_name="TeamIronMan"):
        self.magic_cookie = 0xabcddcba
        # Pad team name to 32 bytes with null bytes (per protocol specification)
        self.team_name = (team_name.ljust(32, '\x00')[:32]).encode('utf-8')
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_sock.bind(('0.0.0.0', 0))
        self.tcp_port = self.tcp_sock.getsockname()[1]
        self.tcp_sock.listen(10)
        print(f"Server started, listening on {socket.gethostbyname(socket.gethostname())}")

    def draw_card(self):
        """
        Generates a random card from a standard deck and calculates its Blackjack value.
        
        Returns:
            tuple: (rank, suit, value)
        """
        # Generate a random rank between 1 (Ace) and 13 (King)
        rank = random.randint(1, 13)
        # 0:Heart, 1:Diamond, 2:Club, 3:Spade
        suit = random.randint(0, 3) 

        # Calculate the card's point value for Blackjack:
        # If it's an Ace (1) - value is 11.
        # If it's a 10,J,Q,K card (10, 11, 12, 13) - value is 10.
        # Otherwise, the value is the rank itself.
        value = 11 if rank == 1 else (10 if rank >= 10 else rank)
        return rank, suit, value

    def send_card(self, conn, rank, suit, status=0):
        """
        Packs card information into a binary packet and sends it to the client.
        """
        # Format: Magic(4), Type(1), Status(1), Rank(2), Suit(1) = 9 Bytes total
        packet = struct.pack('!IbBHB', self.magic_cookie, 0x04, status, rank, suit)
        conn.sendall(packet)

    def handle_client(self, conn, addr):
        """
        Handles a client connection: validates protocol, manages game rounds, and processes player decisions.
        Sets timeout to prevent zombie connections and validates all incoming packets against magic cookie.
        """
        conn.settimeout(60)  # Prevent zombie connections - 60 second timeout
        try:
            # Receive the initial game request from the client
            data = conn.recv(1024)
            if not data: return
            magic, m_type, num_rounds, team_raw = struct.unpack('!IbB32s', data[:38])
            
            # Validate Magic Cookie and Message Type (Protocol Security)
            if magic != self.magic_cookie:
                print(f"Invalid Magic Cookie received from {addr[0]}. Dropping.")
                return
            if m_type != 0x03:  # 0x03 = Request message type
                print(f"Invalid Message Type received from {addr[0]}. Dropping.")
                return
            
            client_name = team_raw.decode('utf-8').strip('\x00').strip()
            print(f"Accepted connection from {addr[0]} ({client_name}). Playing {num_rounds} rounds.")

            # Loop through the number of rounds requested by the client
            for r in range(1, num_rounds + 1):
                # Create a fresh, shuffled 52-card deck for this round
                deck = [(rank, suit) for rank in range(1, 14) for suit in range(4)]
                random.shuffle(deck)
                
                def get_card_from_deck():
                    """Draw a card from the shuffled deck"""
                    rank, suit = deck.pop()
                    val = 11 if rank == 1 else (10 if rank >= 10 else rank)
                    return rank, suit, val
                
                player_sum = 0
                dealer_sum = 0
                dealer_hidden_card = None

                # --- Game Setup ---
                # Player: 2 cards face-up
                for _ in range(2):
                    rank, suit, val = get_card_from_deck()
                    player_sum += val
                    self.send_card(conn, rank, suit, 0)
                
                # Dealer: first card face-up
                d1_rank, d1_suit, d1_val = get_card_from_deck()
                dealer_sum += d1_val
                self.send_card(conn, d1_rank, d1_suit, 0)
                
                # Dealer: second card hidden - drawn but not sent yet
                dealer_hidden_card = get_card_from_deck()
                dealer_sum += dealer_hidden_card[2]

                # --- Player Turn ---
                while player_sum <= 21:
                    # Turn ends automatically - No need to hit
                    if player_sum == 21: break 
                    
                    # Receive player decision: 10 bytes (Magic 4, Type 1, "Hittt"/"Stand" 5)
                    decision_data = conn.recv(10) 
                    if not decision_data: break
                    
                    # Unpack the decision string
                    magic_c, m_t, decision = struct.unpack('!Ib5s', decision_data[:10])
                    
                    # Validate Magic Cookie in decision packet
                    if magic_c != self.magic_cookie:
                        print(f"Invalid Magic Cookie in decision from {addr[0]}. Dropping.")
                        break
                    
                    choice = decision.decode().strip('\x00').lower()
                    
                    # # Player chooses "HIT" - Deal a new card 
                    if choice == "hittt":
                        rank, suit, val = get_card_from_deck()
                        player_sum += val
                        self.send_card(conn, rank, suit, 0)
                        if player_sum > 21: break

                    # Player chooses "Stand"
                    else: break 

                # --- Dealer Turn --- (Only if player didn't bust)
                if player_sum <= 21:
                    # Reveal the hidden second card to the client
                    self.send_card(conn, dealer_hidden_card[0], dealer_hidden_card[1], 0)
                    # Dealer must hit until the total sum is at least 17
                    while dealer_sum < 17:
                        r, s, v = get_card_from_deck()
                        dealer_sum += v
                        self.send_card(conn, r, s, 0)

                # --- Decide Winner ---
                if player_sum > 21: result = 2 # Loss
                elif dealer_sum > 21: result = 3 # Win
                elif player_sum > dealer_sum: result = 3 # Win
                elif player_sum < dealer_sum: result = 2 # Loss
                else: result = 1 # Tie
                
                # --- End of Round ---
                # Send a final packet with the result status (1, 2, or 3)
                self.send_card(conn, 0, 0, result)

        except socket.timeout:
            print(f"Connection with {addr[0]} timed out.")
        except Exception as e: 
            print(f"Error handling {addr[0]}: {e}")
        finally: 
            conn.close()

    def run(self):
        """
        Main server loop. Starts the broadcaster and listens for incoming TCP connections.
        """
        threading.Thread(target=self.send_offers, daemon=True).start()
        while True:
            # Wait and accept a new TCP connection from a client: 'c'- client socket 'a'- client address
            c, a = self.tcp_sock.accept()
            threading.Thread(target=self.handle_client, args=(c, a)).start()

    def send_offers(self):
        """
        Continuously broadcasts UDP offer messages to the network.
        """
        # Create a UDP socket for broadcasting
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Enable broadcasting mode for this socket
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while True:
            # Send the offer packet to the broadcast address on port 13122
            # Offer format: Magic(4), Message Type (0x02), TCP Port (2), Team Name (32)
            udp.sendto(struct.pack('!IbH32s', self.magic_cookie, 0x02, self.tcp_port, self.team_name), ('<broadcast>', 13122))
            time.sleep(1)

if __name__ == "__main__": 
    BlackjackServer().run()