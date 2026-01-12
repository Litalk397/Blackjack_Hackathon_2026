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
        self.team_name = (team_name.ljust(TEAM_NAME_LENGTH, '\x00')[:TEAM_NAME_LENGTH]).encode('utf-8')
        
        # --- Fix: Finding the real WiFi IP ---
        # We try to connect to Google (without sending anything) just to determine which network interface we use to reach the internet
        try:
            temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            temp_sock.connect((IP_DISCOVERY_HOST, IP_DISCOVERY_PORT))
            self.my_ip = temp_sock.getsockname()[0]
            temp_sock.close()
        except:
            self.my_ip = '0.0.0.0' # Backup in case of failure
        # -------------------------------------------

        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_sock.bind(('0.0.0.0', 0)) # Listening to everyone on TCP is fine
        self.tcp_port = self.tcp_sock.getsockname()[1]
        self.tcp_sock.listen(10)
        
        print(f"Server started, listening on IP: {self.my_ip}")

    def draw_card(self):
        """Draw a random card from the deck.
        
        Returns:
            tuple: (rank, suit, value) where rank is 1-13, suit is 0-3, and value is the card's point value.
        """
        rank = random.randint(1, 13)
        suit = random.randint(0, 3) 
        value = 11 if rank == 1 else (10 if rank >= 10 else rank)
        return rank, suit, value

    def send_card(self, conn, rank, suit, status=0):
        """Send a card packet to the client.
        
        Args:
            conn: The TCP socket connection.
            rank (int): Card rank (1-13).
            suit (int): Card suit (0-3).
            status (int): Game status (0=card, 1=tie, 2=loss, 3=win).
        """
        packet = struct.pack('!IbBHB', self.magic_cookie, MSG_TYPE_PAYLOAD, status, rank, suit)
        conn.sendall(packet)

    def handle_client(self, conn, addr):
        """Handle a client connection and manage the game session.
        
        Args:
            conn: The TCP socket connection to the client.
            addr: The client's address tuple (ip, port).
        """
        conn.settimeout(TCP_TIMEOUT)
        try:
            data = conn.recv(1024)
            if not data or len(data) < 38:
                return
            
            magic, m_type, num_rounds, team_raw = struct.unpack('!IbB32s', data[:38])
            
            if magic != self.magic_cookie or m_type != MSG_TYPE_REQUEST:
                return
            
            client_name = team_raw.decode('utf-8').strip('\x00').strip()
            print(f"Accepted connection from {addr[0]} ({client_name})")

            for r in range(1, num_rounds + 1):
                deck = [(rank, suit) for rank in range(1, 14) for suit in range(4)]
                random.shuffle(deck)
                
                def get_card_from_deck():
                    rank, suit = deck.pop()
                    val = 11 if rank == 1 else (10 if rank >= 10 else rank)
                    return rank, suit, val
                
                player_sum = 0
                dealer_sum = 0
                dealer_hidden_card = None

                for _ in range(2):
                    rank, suit, val = get_card_from_deck()
                    player_sum += val
                    self.send_card(conn, rank, suit, 0)
                
                d1_rank, d1_suit, d1_val = get_card_from_deck()
                dealer_sum += d1_val
                self.send_card(conn, d1_rank, d1_suit, 0)
                
                dealer_hidden_card = get_card_from_deck()
                dealer_sum += dealer_hidden_card[2]

                while player_sum <= 21:
                    if player_sum == 21: break 
                    decision_data = conn.recv(10)
                    if not decision_data or len(decision_data) < 10:
                        break
                    
                    magic_c, m_t, decision = struct.unpack('!Ib5s', decision_data[:10])
                    
                    # Validate message
                    if magic_c != self.magic_cookie or m_t != MSG_TYPE_PAYLOAD:
                        break
                    
                    # Robust decision parsing
                    if decision.strip().lower().startswith(b"hit"):
                        rank, suit, val = get_card_from_deck()
                        player_sum += val
                        self.send_card(conn, rank, suit, 0)
                        if player_sum > 21: break
                    else: break 

                if player_sum <= 21:
                    self.send_card(conn, dealer_hidden_card[0], dealer_hidden_card[1], 0)
                    while dealer_sum < 17:
                        r, s, v = get_card_from_deck()
                        dealer_sum += v
                        self.send_card(conn, r, s, 0)

                if player_sum > 21: result = STATUS_LOSS
                elif dealer_sum > 21: result = STATUS_WIN
                elif player_sum > dealer_sum: result = STATUS_WIN
                elif player_sum < dealer_sum: result = STATUS_LOSS
                else: result = STATUS_TIE
                
                self.send_card(conn, 0, 0, result)
            
            print(f"Game finished for {client_name}")

        except Exception as e: 
            print(f"Error: {e}")
        finally: 
            conn.close()

    def run(self):
        """Start the server and begin accepting client connections.
        
        Launches the UDP broadcast thread and enters the main TCP accept loop.
        """
        threading.Thread(target=self.send_offers, daemon=True).start()
        while True:
            c, a = self.tcp_sock.accept()
            threading.Thread(target=self.handle_client, args=(c, a)).start()

    def send_offers(self):
        """Continuously broadcast game offers via UDP.
        
        Sends offer packets every second to broadcast address on port 13122.
        """
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # This prevents Windows from sending the broadcast to virtual machines
        try:
            udp.bind((self.my_ip, 0)) 
        except:
            print("Warning: Could not bind to specific IP for broadcast")
        # -------------------------------------------------

        while True:
            udp.sendto(struct.pack('!IbH32s', self.magic_cookie, MSG_TYPE_OFFER, self.tcp_port, self.team_name), ('<broadcast>', UDP_PORT))
            time.sleep(1)

if __name__ == "__main__": 
    BlackjackServer().run()