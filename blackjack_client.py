import socket, struct

# Protocol constants
MAGIC_COOKIE = 0xabcddcba
UDP_PORT = 13122
TCP_TIMEOUT = 60
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

class BlackjackClient:
    """BlackJack client for connecting to game servers and playing multiple rounds.
    
    The client listens for UDP broadcasts from servers and initiates TCP connections
    to play BlackJack games with colored console output and win rate tracking.
    """
    
    def __init__(self, team_name="Joker"):
        """Initialize the BlackJack client.
        
        Args:
            team_name (str): The client's team name (max 32 characters).
        """
        self.magic_cookie = MAGIC_COOKIE
        # Pad team name to 32 bytes with null bytes (per protocol specification)
        self.team_name = (team_name.ljust(TEAM_NAME_LENGTH, '\x00')[:TEAM_NAME_LENGTH]).encode('utf-8')
        self.wins = 0
        self.losses = 0
        self.ties = 0
        # Card suit emojis
        self.suit_symbols = {0: '♥️', 1: '♦️', 2: '♣️', 3: '♠️'}
        self.suit_names = {0: 'Hearts', 1: 'Diamonds', 2: 'Clubs', 3: 'Spades'}
        # ANSI color codes
        self.RED = '\033[91m'
        self.GREEN = '\033[92m'
        self.YELLOW = '\033[93m'
        self.BLUE = '\033[94m'
        self.MAGENTA = '\033[95m'
        self.CYAN = '\033[96m'
        self.RESET = '\033[0m'
        self.BOLD = '\033[1m'

    def start_game(self, ip, port, rounds):
        """Connects to the server via TCP and manages the game loop for the specified number of rounds.
        Handles protocol parsing, user input validation, and game state management.
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
                tcp.settimeout(TCP_TIMEOUT)
                tcp.connect((ip, port))
                # Send game request
                tcp.sendall(struct.pack('!IbB32s', self.magic_cookie, MSG_TYPE_REQUEST, rounds, self.team_name))
                
                for r in range(1, rounds + 1):
                    print(f"\n{self.BOLD}{self.CYAN}{'='*40}")
                    print(f"🎰 ROUND {r} 🎰")
                    print(f"{'='*40}{self.RESET}")
                    
                    # Proper state management
                    player_cards_received = 0
                    dealer_cards_received = 0
                    dealer_turn = False
                    current_player_sum = 0
                    
                    while True:
                        data = tcp.recv(9)
                        if not data:
                            print(f"{self.RED}Server disconnected. Returning to listening mode.{self.RESET}")
                            return
                        
                        if len(data) < 9:
                            print(f"{self.RED}Invalid packet received. Connection error.{self.RESET}")
                            return
                        
                        magic, m_type, status, rank, suit = struct.unpack('!IbBHB', data)
                        
                        # Validate message
                        if magic != self.magic_cookie or m_type != MSG_TYPE_PAYLOAD:
                            print(f"{self.RED}Protocol error: Invalid message received.{self.RESET}")
                            return
                        
                        if status == STATUS_CARD:
                            # Format card info
                            r_name = {1:'A', 11:'J', 12:'Q', 13:'K'}.get(rank, str(rank))
                            suit_emoji = self.suit_symbols.get(suit, '')
                            suit_name = self.suit_names.get(suit, 'Unknown')
                            card_info = f"{r_name}{suit_emoji} of {suit_name}"
                            
                            # Color cards by suit
                            if suit in [0, 1]:  # Hearts, Diamonds - Red
                                card_color = self.RED
                            else:  # Clubs, Spades - Blue
                                card_color = self.BLUE

                            # State-based card identification
                            if not dealer_turn:
                                if player_cards_received < 2:
                                    # First 2 cards are player's
                                    print(f"{self.GREEN}🃏 Your card: {card_color}{card_info}{self.RESET}")
                                    val = 11 if rank == 1 else (10 if rank >= 10 else rank)
                                    current_player_sum += val
                                    player_cards_received += 1
                                elif dealer_cards_received == 0:
                                    # Third card is dealer's visible card
                                    print(f"{self.YELLOW}🎴 Dealer's visible card: {card_color}{card_info}{self.RESET}")
                                    dealer_cards_received += 1
                                else:
                                    # Additional player cards (Hit)
                                    print(f"{self.GREEN}📥 Hit! Received: {card_color}{card_info}{self.RESET}")
                                    val = 11 if rank == 1 else (10 if rank >= 10 else rank)
                                    current_player_sum += val
                                    player_cards_received += 1
                            else:
                                # Dealer's turn: hidden card reveal + additional draws
                                print(f"{self.YELLOW}🎴 Dealer reveals/draws: {card_color}{card_info}{self.RESET}")
                                dealer_cards_received += 1

                            # Decision logic
                            if not dealer_turn and dealer_cards_received > 0 and current_player_sum < 21:
                                print(f"{self.MAGENTA}💰 Your current sum: {current_player_sum}{self.RESET}")
                                
                                # Validate user input
                                while True:
                                    choice = input(f"{self.BOLD}Hit(H) or Stand(S)? {self.RESET}").lower().strip()
                                    if choice in ['h', 's']:
                                        break
                                    print(f"{self.RED}❌ Invalid input. Please enter 'H' for Hit or 'S' for Stand.{self.RESET}")
                                
                                if choice == 's':
                                    dealer_turn = True
                                    tcp.sendall(struct.pack('!Ib5s', self.magic_cookie, MSG_TYPE_PAYLOAD, DECISION_STAND))
                                else:
                                    tcp.sendall(struct.pack('!Ib5s', self.magic_cookie, MSG_TYPE_PAYLOAD, DECISION_HIT))
                            
                            elif current_player_sum >= 21:
                                # Automatic transition to dealer's turn
                                dealer_turn = True
                        
                        else:
                            # Result message
                            if status == STATUS_TIE:
                                print(f"\n{self.YELLOW}{self.BOLD}🤝 Result: TIE!{self.RESET}")
                                self.ties += 1
                            elif status == STATUS_LOSS:
                                print(f"\n{self.RED}{self.BOLD}😞 Result: LOSS!{self.RESET}")
                                self.losses += 1
                            elif status == STATUS_WIN:
                                print(f"\n{self.GREEN}{self.BOLD}🎉 Result: WIN!{self.RESET}")
                                self.wins += 1
                            break
        
        except socket.timeout:
            print(f"{self.RED}Connection timeout. Server not responding.{self.RESET}")
        except ConnectionResetError:
            print(f"{self.RED}Connection reset by server.{self.RESET}")
        except Exception as e:
            print(f"{self.RED}Game error: {e}{self.RESET}")

    def run(self):
        """Main client loop: listens for server offers via UDP broadcast and initiates games.
        Handles multiple game sessions and displays final statistics.
        """
        while True:
            try:
                user_input = input("\nHow many rounds would you like to play? (or type 'exit' to quit): ").strip()
                if user_input.lower() == 'exit':
                    break
                num_rounds = int(user_input)
            except ValueError:
                print("Please enter a valid number.")
                continue

            print("Client started, listening for offer requests...")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except:
                    pass
                
                udp.bind(('', UDP_PORT))
                data, addr = udp.recvfrom(1024)
                
                if len(data) < 39:
                    print(f"{self.RED}Invalid offer packet received.{self.RESET}")
                    continue
                
                magic, m_type, port, name_raw = struct.unpack('!IbH32s', data[:39])
                
                if magic == self.magic_cookie and m_type == MSG_TYPE_OFFER:
                    name = name_raw.decode('utf-8', errors='ignore').strip('\x00').strip()
                    print(f"{self.CYAN}✨ Received offer from {self.BOLD}{name}{self.RESET}{self.CYAN} at {addr[0]}{self.RESET}")
                    
                    # Reset statistics
                    self.wins = 0
                    self.losses = 0
                    self.ties = 0
                    
                    self.start_game(addr[0], port, num_rounds)
                    
                    # Display full statistics
                    total = self.wins + self.losses + self.ties
                    if total > 0:
                        win_rate = (self.wins / total) * 100
                        loss_rate = (self.losses / total) * 100
                        tie_rate = (self.ties / total) * 100
                        
                        print(f"\n{self.BOLD}{self.CYAN}{'='*50}")
                        print(f"📊 GAME STATISTICS")
                        print(f"{'='*50}{self.RESET}")
                        print(f"{self.GREEN}Wins: {self.wins} ({win_rate:.1f}%){self.RESET}")
                        print(f"{self.RED}Losses: {self.losses} ({loss_rate:.1f}%){self.RESET}")
                        print(f"{self.YELLOW}Ties: {self.ties} ({tie_rate:.1f}%){self.RESET}")
                        print(f"{self.CYAN}Total rounds: {total}{self.RESET}")
                    else:
                        print(f"{self.YELLOW}No rounds completed.{self.RESET}")

if __name__ == "__main__":
    BlackjackClient().run()