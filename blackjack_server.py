import socket, struct, threading, time, random

# Protocol constants
MAGIC_COOKIE = 0xabcddcba
UDP_PORT = 13122
TCP_TIMEOUT = 60
IP_DISCOVERY_HOST = "8.8.8.8"
IP_DISCOVERY_PORT = 80
TEAM_NAME_LENGTH = 32

# Message types
MSG_TYPE_OFFER = 0x02
MSG_TYPE_REQUEST = 0x03
MSG_TYPE_PAYLOAD = 0x04

# Game status codes
STATUS_CARD = 0
STATUS_TIE = 1
STATUS_LOSS = 2
STATUS_WIN = 3

# Decision strings
DECISION_HIT = b"Hittt"
DECISION_STAND = b"Stand"

class BlackjackServer:
    """BlackJack server implementing a multi-threaded TCP/UDP game server.
    
    The server broadcasts offers via UDP and handles multiple client connections
    via TCP, managing complete BlackJack games with multiple rounds.
    """
    
    def __init__(self, team_name="TeamIronMan"):
        """Initialize the BlackJack server.
        
        Args:
            team_name (str): The server's team name (max 32 characters).
        """
        self.magic_cookie = MAGIC_COOKIE
        # Pad team name to 32 bytes with null bytes to match protocol specifications
        self.team_name = (team_name.ljust(TEAM_NAME_LENGTH, '\x00')[:TEAM_NAME_LENGTH]).encode('utf-8')
        
        # Determine the actual IP address that will be used for broadcasting
        # We cannot just use '0.0.0.0' for broadcasts - we need the real IP the system will use
        # We trick the system by creating a temporary UDP socket and connecting to an external address
        # (Google's DNS at 8.8.8.8). This doesn't send any packets, but tells us which local IP
        # the OS would use to route traffic to that destination. This gives us the real WiFi/network IP.
        try:
            temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            temp_sock.connect((IP_DISCOVERY_HOST, IP_DISCOVERY_PORT))  # Connect to Google (no actual data sent)
            self.my_ip = temp_sock.getsockname()[0]  # Get the local IP address used for this connection
            temp_sock.close()
        except:
            self.my_ip = '0.0.0.0'  # Fallback if IP discovery fails - will still work on localhost

        # Create and configure TCP server socket
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # SO_REUSEADDR allows reusing the port immediately after a restart without waiting for timeout
        self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind to all interfaces (0.0.0.0) on any available port (0 = OS picks a free port)
        self.tcp_sock.bind(('0.0.0.0', 0))
        self.tcp_port = self.tcp_sock.getsockname()[1]  # Get the actual port the OS assigned to us
        # Listen queue of 10 - allows up to 10 incoming connections to queue up waiting for acceptance
        self.tcp_sock.listen(10)
        
        print(f"Server started, listening on IP: {self.my_ip}")

    def draw_card(self):
        """Draw a random card from the deck.
        
        Note: This is a simplified implementation that allows infinite cards.
        In a real BlackJack game, you'd use a standard deck with 52 cards and shuffle.
        
        Returns:
            tuple: (rank, suit, value) where:
                - rank: 1=Ace, 2-10=pip value, 11=Jack, 12=Queen, 13=King
                - suit: 0=Hearts, 1=Diamonds, 2=Clubs, 3=Spades
                - value: BlackJack point value (Ace=11, Face cards=10, others=pip value)
        """
        rank = random.randint(1, 13)  # Ace through King
        suit = random.randint(0, 3)   # Any of the 4 suits
        # Calculate BlackJack value: Ace=11, Face cards (11-13)=10, others=their rank number
        value = 11 if rank == 1 else (10 if rank >= 10 else rank)
        return rank, suit, value

    def send_card(self, conn, rank, suit, status=0):
        """Send a card packet to the client.
        
        This function sends either a card to display or a game result message.
        The client determines whether it's a card or result based on the status field.
        
        Args:
            conn: The TCP socket connection to the client
            rank (int): Card rank (1-13) or ignored if sending a result
            suit (int): Card suit (0-3) or ignored if sending a result  
            status (int): Game status code:
                - 0 = Card (display rank and suit)
                - 1 = Tie game
                - 2 = Player loss (dealer won)
                - 3 = Player win
        """
        # Pack data as big-endian binary: magic cookie (4 bytes), message type (1 byte),
        # status (1 byte), rank (2 bytes), suit (1 byte) = 9 bytes total
        packet = struct.pack('!IbBHB', self.magic_cookie, MSG_TYPE_PAYLOAD, status, rank, suit)
        conn.sendall(packet)

    def handle_client(self, conn, addr):
        """Handle a client connection and manage the game session.
        
        This is called when a client connects. The server receives the game request,
        validates it, then plays the requested number of BlackJack rounds.
        
        Args:
            conn: The TCP socket connection to the client
            addr: The client's address tuple (ip, port)
        """
        conn.settimeout(TCP_TIMEOUT)  # Timeout if client doesn't respond within 60 seconds
        try:
            # Receive the game request from the client
            data = conn.recv(1024)
            if not data or len(data) < 38:
                # Invalid request - missing data or too short
                return
            
            # Parse the request packet: magic cookie, message type, number of rounds requested, team name
            magic, m_type, num_rounds, team_raw = struct.unpack('!IbB32s', data[:38])
            
            # Verify the client is speaking the correct protocol
            if magic != self.magic_cookie or m_type != MSG_TYPE_REQUEST:
                return
            
            # Extract client's team name from the binary data
            client_name = team_raw.decode('utf-8').strip('\x00').strip()
            print(f"Accepted connection from {addr[0]} ({client_name})")

            # Play the requested number of rounds
            for r in range(1, num_rounds + 1):
                # Create a standard deck of 52 cards (13 ranks × 4 suits) and shuffle it
                # This creates a fresh deck for each round - in real BlackJack, you'd use shoe management
                deck = [(rank, suit) for rank in range(1, 14) for suit in range(4)]
                random.shuffle(deck)
                
                def get_card_from_deck():
                    """Helper function to draw a card from the deck and calculate its BlackJack value"""
                    rank, suit = deck.pop()  # Remove and return a card from the deck
                    # Calculate BlackJack value: Ace=11, Face cards=10, others=pip value
                    val = 11 if rank == 1 else (10 if rank >= 10 else rank)
                    return rank, suit, val
                
                # Initialize player and dealer hands for this round
                player_sum = 0  # Running total of player's hand value
                dealer_sum = 0  # Running total of dealer's hand value
                dealer_hidden_card = None  # The dealer's second card (initially hidden from player)

                # Deal initial hands: Each player gets 2 cards
                # Player's cards are sent to the client
                for _ in range(2):
                    rank, suit, val = get_card_from_deck()
                    player_sum += val
                    self.send_card(conn, rank, suit, 0)  # Send card with status=0 (card, not result)
                
                # Dealer gets their first visible card (shown to the player)
                d1_rank, d1_suit, d1_val = get_card_from_deck()
                dealer_sum += d1_val
                self.send_card(conn, d1_rank, d1_suit, 0)  # Send dealer's visible card
                
                # Dealer gets their second card (hidden from player initially)
                # This will be revealed later when the dealer's turn starts
                dealer_hidden_card = get_card_from_deck()
                dealer_sum += dealer_hidden_card[2]

                # Player's turn: Keep asking for Hit/Stand decisions until they bust or stand
                while player_sum <= 21:
                    # If player already has 21 (Blackjack), auto-stand (they can't improve)
                    if player_sum == 21:
                        break
                    
                    # Wait for player's decision (Hit or Stand) from the client
                    decision_data = conn.recv(10)
                    if not decision_data or len(decision_data) < 10:
                        # No response from client - connection issue
                        break
                    
                    # Parse the decision packet: magic cookie, message type, decision string
                    magic_c, m_t, decision = struct.unpack('!Ib5s', decision_data[:10])
                    
                    # Verify the decision is valid and from a legitimate client
                    if magic_c != self.magic_cookie or m_t != MSG_TYPE_PAYLOAD:
                        break
                    
                    # Check what the player decided
                    # "Hittt" = Hit, anything else = Stand
                    if decision.strip().lower().startswith(b"hit"):
                        # Player wants another card
                        rank, suit, val = get_card_from_deck()
                        player_sum += val
                        self.send_card(conn, rank, suit, 0)  # Send the new card
                        # If player busted, exit player's turn (dealer wins automatically)
                        if player_sum > 21:
                            break
                    else:
                        # Player chose Stand - exit player's turn
                        break 

                # Dealer's turn: Only happens if player didn't bust
                if player_sum <= 21:
                    # First, reveal the dealer's hidden card to the client
                    self.send_card(conn, dealer_hidden_card[0], dealer_hidden_card[1], 0)
                    
                    # Dealer must hit on 16 or less and stand on 17 or more
                    # This is the standard BlackJack dealer rule
                    while dealer_sum < 17:
                        # Dealer draws another card
                        r, s, v = get_card_from_deck()
                        dealer_sum += v
                        self.send_card(conn, r, s, 0)  # Send the card to show the dealer's drawing

                # Determine the round result based on final hand values
                # Note: Blackjack hand values are "soft" (Aces can be 1 or 11),
                # but this simple implementation uses fixed values
                if player_sum > 21:
                    # Player busted - instant loss
                    result = STATUS_LOSS
                elif dealer_sum > 21:
                    # Dealer busted and player didn't - player wins
                    result = STATUS_WIN
                elif player_sum > dealer_sum:
                    # Player's hand is higher than dealer's
                    result = STATUS_WIN
                elif player_sum < dealer_sum:
                    # Dealer's hand is higher
                    result = STATUS_LOSS
                else:
                    # Both have the same hand value
                    result = STATUS_TIE
                
                # Send the final result to the client
                # Using dummy rank/suit values (0,0) since only status matters for results
                self.send_card(conn, 0, 0, result)
            
            # All rounds completed successfully
            print(f"Game finished for {client_name}")

        except Exception as e:
            # Handle any errors that occurred during the game
            print(f"Error: {e}")
        finally:
            # Always close the connection when done, even if an error occurred
            conn.close()

    def run(self):
        """Start the server and begin accepting client connections.
        
        Launches the UDP broadcast thread (sends server offers) and enters the main TCP loop.
        Each incoming client connection is handled in its own thread for concurrent games.
        """
        # Start the UDP broadcast thread in daemon mode
        # Daemon threads shut down automatically when the main program exits
        threading.Thread(target=self.send_offers, daemon=True).start()
        
        # Main server loop: accept incoming client connections
        while True:
            c, a = self.tcp_sock.accept()  # Wait for a client to connect
            # Handle each client in a separate thread so multiple clients can play simultaneously
            threading.Thread(target=self.handle_client, args=(c, a)).start()

    def send_offers(self):
        """Continuously broadcast game offers via UDP.
        
        Sends offer packets every second to the broadcast address on port 13122.
        Clients listen for these offers to discover available BlackJack servers.
        """
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Enable broadcast mode - allows sending to <broadcast> address
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        # Bind to the specific local IP address (not 0.0.0.0)
        # This ensures Windows sends broadcasts to the correct network interface
        # and prevents confusion in multi-interface systems
        try:
            udp.bind((self.my_ip, 0))  # Bind to our discovered IP, any available port
        except:
            print("Warning: Could not bind to specific IP for broadcast")

        # Continuously broadcast offers at regular intervals
        while True:
            # Create an offer packet: magic cookie, message type (OFFER), TCP port, server team name
            # Clients will read this to learn where to connect
            packet = struct.pack('!IbH32s', self.magic_cookie, MSG_TYPE_OFFER, self.tcp_port, self.team_name)
            # Send to the broadcast address so all clients on the network can receive it
            udp.sendto(packet, ('<broadcast>', UDP_PORT))
            # Send offers once per second
            time.sleep(1)

if __name__ == "__main__": 
    BlackjackServer().run()