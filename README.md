# Socket-Aces (Blackjack UDP/TCP)

This project is a networked Blackjack game:
- **Server** broadcasts offers over **UDP** every 1 second.
- **Client** listens for offers, connects over **TCP**, plays Blackjack rounds, then returns to listening.

## Editors

- Shira Hadad 214489833
- Rotem Mualem 32501397

## Requirements

- Windows / macOS / Linux
- Python 3.x
- No external packages required (GUI uses built-in `tkinter`).

## Project Structure

- `src/Server/server.py` — runs the server (UDP offers + TCP game sessions)
- `src/Client/client.py` — runs the client
- `src/Client/BlackjackClientProtocol.py` — protocol packing/unpacking
- `src/Server/BlackjackServerProtocol.py` — protocol packing/unpacking
- `src/shared/protocol_constants.py` — message types, sizes, result codes

## How to Run

### 1) Start a server

From the repo root:

```powershell
python src/Server/server.py
```

You should see something like:
- `Server started, listening on IP address ...`

The server broadcasts offers over UDP once per second.

### 2) Start a client

In another terminal:

```powershell
python src/Client/client.py
```

Client flow:
1. Asks how many rounds to play (**once** per client run).
2. Listens for server offers over UDP.
3. Connects to the first server offer it receives.
4. Plays the requested number of rounds over TCP.
5. Prints statistics after each round
6. Closes TCP and immediately returns to listening for offers.

## Protocol (High-Level)

- **Offer (UDP)**: server broadcasts `MAGIC_COOKIE`, message type, TCP port, server name.
- **Request (TCP)**: client sends `MAGIC_COOKIE`, message type, number of rounds, team name.
- **Payload (TCP)**:
  - Server → Client: result code + optional card (rank/suit)
  - Client → Server: decision (`Hittt` or `Stand`)

See `src/shared/protocol_constants.py` for message sizes and result codes.

