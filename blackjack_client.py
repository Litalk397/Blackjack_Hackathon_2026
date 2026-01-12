import socket, struct

class BlackjackClient:
    def __init__(self, team_name="Joker"):
        self.magic_cookie = 0xabcddcba
        self.team_name = team_name.ljust(32)[:32].encode('utf-8')
        self.wins = 0

    def start_game(self, ip, port, rounds):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
                tcp.connect((ip, port))
                # שלב 6: שליחת בקשת המשחק
                tcp.sendall(struct.pack('!IbB32s', self.magic_cookie, 0x03, rounds, self.team_name) + b'\n')
                
                for r in range(1, rounds + 1):
                    print(f"\n--- Round {r} ---")
                    cards_in_round = 0
                    current_player_sum = 0
                    is_my_turn = True
                    
                    while True:
                        data = tcp.recv(9) # פורמט שרת: Magic(4), Type(1), Status(1), Rank(2), Suit(1)
                        if not data or len(data) < 9: break
                        
                        _, _, status, rank, suit = struct.unpack('!IbBHB', data)
                        
                        if status == 0: # הודעת קלף (Payload רגיל)
                            cards_in_round += 1
                            r_name = {1:'A', 11:'J', 12:'Q', 13:'K'}.get(rank, str(rank))
                            s_name = {0:'Heart', 1:'Diamond', 2:'Club', 3:'Spade'}.get(suit)
                            card_info = f"{r_name} of {s_name}"

                            if cards_in_round <= 2:
                                print(f"Your card: {card_info}")
                                val = 11 if rank == 1 else (10 if rank >= 10 else rank)
                                current_player_sum += val
                            elif cards_in_round == 3:
                                print(f"Dealer's visible card: {card_info}")
                            else:
                                # כאן ההדפסה החשובה: האם זה Hit שלנו או תור הדילר
                                if is_my_turn:
                                    print(f"Hit! Received: {card_info}")
                                    val = 11 if rank == 1 else (10 if rank >= 10 else rank)
                                    current_player_sum += val
                                else:
                                    # הדפסת קלפי הדילר (חשיפת המוסתר ומשיכת קלפים עד 17)
                                    print(f"Dealer reveals/draws: {card_info}")

                            # לוגיקת החלטה
                            if is_my_turn and cards_in_round >= 3 and current_player_sum < 21:
                                choice = input("Hit(H) or Stand(S)? ").lower().strip()
                                if choice == 's': 
                                    is_my_turn = False
                                    decision = "Stand"
                                else: 
                                    decision = "Hittt"
                                # שליחת החלטה (10 בתים)
                                tcp.sendall(struct.pack('!Ib5s', self.magic_cookie, 0x04, decision.encode()))
                            elif current_player_sum >= 21:
                                is_my_turn = False # מעבר אוטומטי לתור הדילר או תוצאה
                        
                        else: # הודעת תוצאה (Win/Loss/Tie)
                            res_msg = {1: "Tie!", 2: "Loss!", 3: "Win!"}.get(status)
                            print(f"Result: {res_msg}")
                            if status == 3: self.wins += 1
                            break # סיבוב נגמר
        except Exception as e:
            print(f"Game error: {e}")

    def run(self):
        while True:
            try:
                user_input = input("\nHow many rounds would you like to play? (or type 'exit' to quit): ").strip()
                if user_input.lower() == 'exit': break
                num_rounds = int(user_input)
            except ValueError:
                print("Please enter a valid number.")
                continue

            print("Client started, listening for offer requests...")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try: udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except: pass
                
                udp.bind(('', 13122))
                data, addr = udp.recvfrom(1024)
                magic, m_type, port, name_raw = struct.unpack('!IbH32s', data[:39])
                
                if magic == self.magic_cookie and m_type == 0x02:
                    name = name_raw.decode('utf-8', errors='ignore').strip('\x00').strip()
                    print(f"Received offer from {name} at {addr[0]}")
                    self.wins = 0
                    self.start_game(addr[0], port, num_rounds)
                    
                    win_rate = (self.wins / num_rounds) * 100 if num_rounds > 0 else 0
                    print(f"\nFinished playing {num_rounds} rounds, win rate: {win_rate}%")
                    print("-" * 35)

if __name__ == "__main__":
    BlackjackClient().run()