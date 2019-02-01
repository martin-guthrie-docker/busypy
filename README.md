# busyPy

A python3 gRPC client/server toolset for creating dummy workloads on nodes in a cluster.  

The client workload can,
 * consume CPU usage across any number of cores, specified in percent
 * consume overall node memory, specified in percent 

When the server is used, client settings can be updated dynamically,
* a specific client, number of clients or all the clients can be targeted
* client cpu/memory usage can be dynamically changed
* client workload (container) can be forced to exit

This application is meant to be used from the container,
    `docker pull martinguthriedocker/busypy`

# Usage

## Client only

On client node, to set one CPU to have 15% activity, and 15% of memory, issue,

    python3 busypy.py --cpu 15 --mem 15
 
 See `--help` for other options.
 Note that setting cpu usage close to 0% and 100% will not work that well, aim for 5-90%.
 
     usage: busypy.py [-h] [--cpu CPU] [--mem MEM] [--cpu-all] [--cpus CPUS]
                     [--server GRPC_SERVER] [--port GRPC_PORT]
    
    BusyPy Container
    
    optional arguments:
      -h, --help            show this help message and exit
      --cpu CPU             Percent usage of the CPU(s), default=27
      --mem MEM             Percent usage of the memory, default=7
      --cpu-all             Use all CPUs, default only one CPU is used.
      --cpus CPUS           Number CPUs to use, default only one CPU is used.
      --server GRPC_SERVER  gRPC server, default=localhost.
      --port GRPC_PORT      gRPC server port, default=50051.

Example Docker container run command,

    docker run -it martinguthriedocker/busypy busypy.py --cpu 5 --server 10.168.2.149 --cpu-all 
 
 
### Memory Usage Note
Memory target usage is specified at the CLI as a total for the node, but it is reported per busy loop process. 
 

 ## Client/Server

In this setup, clients will call into a server in order to get the target cpu/mem settings.  When new settings are applied to the client, all the client PIDs are set to the same values.

If the server is not reachable/offline, the client will use its last known settings, either from the last time it contacted the server, or from the command line when the client was started.

The server is meant to go offline, or be restarted mulitple times.  The server is invoked multiple times to get the nodes, as a group, and/or individually, into the desired state.  The server is designed to exit when it has set the clients in order for it to be used in bash/ansible scripts.

    usage: busypyserver.py [-h] [--cpu CPU] [--mem MEM] [--grpc-port GRPC_PORT]
                           [--wait-for WAIT_FOR] [--client-exit]
                           [--client-ip CLIENT_IP] [--monitor]
    
    BusyPyServer
    
    optional arguments:
      -h, --help            show this help message and exit
      --cpu CPU             Percent usage of the CPU(s), default=27
      --mem MEM             Percent usage of the memory, default=7
      --grpc-port GRPC_PORT
                            gRPC server port, default=50051.
      --wait-for WAIT_FOR   Wait for # of clients to poll, then exit server, 0=run
                            forever (default)
      --client-exit         Client busy app should exit.
      --client-ip CLIENT_IP
                            Target client ip address only
      --monitor             Monitor clients only


### Case 1: Set all clients to cpu/mem

* Choice to use a server or just a client.
  * Just a client, setting 5 CPU cores to 5%.  The memory usage will be the default.
  
    `docker run -it martinguthriedocker/busypy busypy.py --cpus 5 --cpu 5`

  * Using a server, the server can be started before or after the clients are started.
    * if the clients are started first, they will start with cpu/mem usage based on client defaults or CLI parameters when the client was started.
    * the clients must be told the server IP address (and port if different than default).  The Docker container must expose the needed port.
    * when the clients call into the server, their settings will be updated to the server settings.
      * client command,
    
        `docker run -it -p 50051:50051 martinguthriedocker/busypy busypy.py --cpus 5 --server 10.168.2.149 --cpu 5`

      * server command, changes all clients to 10% cpu usage,
      
        `docker run -it -p 50051:50051 martinguthriedocker/busypy busypyserver.py --cpu 10` 
  
### Case 2: Set one/more client(s) to different target at later time

* To set one client to different settings than the others, tell the server to target that IP.  You must know the IP address of the client you wish to change.
  * Start the client(s),

    `docker run -it -p 50051:50051 martinguthriedocker/busypy busypy.py --cpus 5 --server 10.168.2.149 --cpu 5`

  * start the server, and use `--client-ip` to target the client you want to change,
  
    `docker run -it -p 50051:50051 martinguthriedocker/busypy busypyserver.py --cpu 10 --client-ip 172.17.0.2`
      
  * if you wanted to change a number of nodes from one setting to another, you could use `--wait-for` to count how many clients to change.
    * Note that `--wait-for` will use the first clients that check in... (non-deterministic)  
    * If for example, you had 10 nodes deployed and you wanted to change half (5) of them,

      `docker run -it -p 50051:50051 martinguthriedocker/busypy busypyserver.py --cpu 10 --wait-for 5`

* With either `--clinet-ip` or `--wait-for`, when the server is completed the task, it will exit.


### Case 3: Monitor clients only

* For just monitoring, use

    `docker run -it -p 50051:50051 martinguthriedocker/busypy busypyserver.py --monitor`

## Docker Container

* These tools are available as a container at,

    `docker pull martinguthriedocker/busypy`
    
* Run client like,

    `docker run -it martinguthriedocker/busypy busypy.py --cpu 5`

* Run server like,

    `docker run -it busypy busypyserver.py --monitor`

## FAQ
1) Where is the busypyserver container?

    Its the same container.  Use this to run busypyserver,
      
    `docker run -it martinguthriedocker/busypy busypyserver.py --help`
  
2) How long does it take for CPU/Memory usage to stabilize?

    Memory should stabilize in one internal/reporting cycle, which is ~2 seconds.
    CPU usage can take up to 10 cycles to stabilize, up to ~20 seconds.

3) Are all the client's processes set to the same CPU usage?

    Yes.  And the memory usage is for the whole node, not per process.

## Issues

* CPU percent activity may not work so well above ~80% on modern HW.  The algorithm for being busy is not that adaptive, so it can get to a point where it can no longer get busier.
* The client may have trouble contacting the server if the server has been offline.  It seems gRPC socket gets stuck for a while, or even indefinitely.  Don't have a workaround for this issue. 

## Developer

* copy `hooks` to `.git/hooks`
