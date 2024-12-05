# P2P File Sharing Software #

### Team Members 
* Pratiksha Deodhar - 70692093
* Sanket Jadhao - 54137689
* Vaidehi Sudele - 47267125

## Introduction ##
This project is a Peer-to-Peer (P2P) file-sharing software inspired by the BitTorrent protocol. The system enables multiple peers to collaborate in downloading and sharing file pieces, ensuring efficient file distribution across a network.

## Features ##
* __Handshake Mechanism:__ Ensures secure and reliable peer connections.
* __Bitfield Management:__ Tracks file pieces available to a peer.
* __Message Handling:__ Manages various peer-to-peer messages, including choke, unchoke, interested, and piece.
* __File Segmentation and Assembly:__ Splits large files into smaller pieces for transmission and reassembles them upon download.
* __Choking/Unchoking:__ Implements preferred and optimistic unchoking for optimal data sharing.
* __Logging:__ Logs peer activities for auditing and debugging.
* __Dynamic Peer Connections:__ Supports establishing and managing connections with multiple peers.
* __Optimistically Unchoked Neighbor:__ Periodically selects a random choked but interested peer to unchoke, ensuring fairness and encouraging participation in the network.

## File Structure ##

### Major Files ###
__1. peerProcess.py:__ <br/>
   * Main entry point for the software.
   * Manages peer initialization, connection setup, and task scheduling.
   * Handles unchoking intervals and termination upon file completion.

__2. peer_connection.py:__ <br/>
   * Defines the PeerConnection class for managing individual peer connections.
   * Handles sending and receiving messages between peers.

__3. message_handler.py:__ <br/>
   * Defines the MessageHandler class to process incoming messages and respond appropriately.
   * Supports message types like bitfield, piece, interested, and have.

__4. bitfield_manager.py:__ <br/>
   * Tracks the availability of file pieces for each peer.
   * Provides methods for encoding/decoding bitfields and managing piece availability.

__5. utils.py:__ <br/>
   * Utility functions for socket communication and logging.

__6. Configuration Files:__ <br/>
   * __Common.cfg:__ Defines global configuration settings such as file size and piece size.
   * __PeerInfo.cfg:__ Specifies details of each peer, including peer_id, host, and port.


## Configuration ##

### Common.cfg ###
Define the following parameters: <br/>
   * NumberOfPreferredNeighbors: Number of preferred neighbors for unchoking.
   * UnchokingInterval: Interval for selecting preferred neighbors.
   * OptimisticUnchokingInterval: Interval for selecting an optimistically unchoked peer.
   * FileName: Name of the file to be shared.
   * FileSize: Size of the file in bytes.
   * PieceSize: Size of each file piece in bytes.

### PeerInfo.cfg ###
List details of all peers in the format:
```commandline
<peer_id> <host> <port> <has_file>
```

Example: 
```commandline
1001 localhost 5000 1
1002 localhost 5001 0
```

## Usage ##

### Requirements ###
  * Python 3.8 or above.
  * socket and threading modules (default in Python).

### Setup ###
1. Clone the repository: <br/>
  ```commandline
  git clone <repository_url>
  cd BITTORRENT-P2P-FILESHARING
  ```
2. Prepare configuration files:<br/>
    * Edit Common.cfg and PeerInfo.cfg with your setup. 
3. Create directories: <br/>
    * Each peer will create a peer_<peer_id>/pieces directory to store file pieces.

### Running the Program ###
Start a peer by specifying its ID as a command-line argument:
```commandline
python3 peerProcess.py <peer_id>
```
Example:
```commandline
python3 peerProcess.py 1001
```
### Process ###
  * Peers establish connections as specified in PeerInfo.cfg.
  * File is split into pieces and shared among peers.
  * Each peer logs its actions in a dedicated log file.

### Example Workflow ###
  1. Peer 1001 starts with the complete file and begins sharing it.
  2. Peer 1002 connects to 1001, receives the file in pieces, and shares them with other peers.
  3. Once all pieces are downloaded, peers reconstruct the file.

## File Descriptions ##

1. __peerProcess.py:__ <br/>
    * Role: Entry point for the application, responsible for initializing peer-specific settings and orchestrating the P2P communication process.

    * Key Responsibilities: <br/>
      * Reads configuration files (Common.cfg and PeerInfo.cfg).
      * Sets up server sockets to accept connections from other peers.
      * Establishes outgoing connections to other peers.
      * Coordinates file splitting, assembly, and download completion checks.
      * Manages unchoking and optimistic unchoking tasks.
    * Significance: Acts as the central control for the entire peer's lifecycle.

2. __peer_connection.py__
    * Role: Manages individual connections between a peer and other peers in the network.

    * Key Responsibilities: <br/>
      * Handles sending and receiving P2P messages.
      * Maintains state information such as whether the peer is choked, interested, or has the complete file.
      * Ensures synchronization with other peers using threading and locks.
    * Significance: Enables direct interaction with other peers and forms the backbone of the communication layer.

3. __message_handler.py__
    * Role: Processes incoming P2P messages and generates appropriate responses.

    * Key Responsibilities: <br/>
      * Handles messages such as choke, unchoke, interested, bitfield, and piece.
      * Updates the peer's state and bitfield based on received messages.
      * Manages file piece requests and responses.
    * Significance: Provides the logic for interpreting and responding to P2P protocol messages.

4. __bitfield_manager.py__
    * Role: Manages the bitfield, a data structure that tracks which file pieces a peer has.

    * Key Responsibilities: <br/>
      * Encodes and decodes the bitfield for network transmission.
      * Updates the bitfield as new pieces are downloaded.
      * Checks the completeness of the file and identifies missing pieces.
    * Significance: Ensures efficient and accurate tracking of file piece availability.









