# busyPy

A python3 gRPC client/server toolset for creating dummy workloads on nodes in a cluster.  

The workload can,
 * consume CPU usage across any number of cores, specified in percent
 * consume overall node memory, specified in percent 

When the server is used, 
* a client or all the clients can be targeted
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

In this setup, clients will call into a server in order to get the target cpu/mem settings.   

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

* Choice to either start all clients first, or start the server first, then the clients.
  * If the clients are started first, they will start with cpu/mem usage based on client defaults or CLI parameters when the client was started.
* Then start the server with desired client targets,

    `python3 busypyserver.py --cpu 20 --mem 10`

  * if you know the number of clients there are, and you want the server to exit after all the clients have gotten the new settings, use,
  
    `python3 busypyserver.py --cpu 20 --mem 10 --wait-for 5`
    
### Case 2: Set one client to different target

* To set one client to different settings than the others use the client IP address,

    `python3 busypyserver.py --cpu 30 --mem 20 --client-ip 192.168.0.20`

  * if you want the server to exit after that client has been set, use,
  
      `python3 busypyserver.py --cpu 30 --mem 20 --client-ip 192.168.0.20 --wait-for 1`

### Case 3: Monitor clients only

* For just monitoring, use

    `python3 busypyserver.py --monitor`

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
    
    
    docker run -it martinguthriedocker/busypy busypyserver.py --help
    

2) How long does it take for CPU/Memory usage to stabilize?

    Memory should stabilize in one internal/reporting cycle, which is ~2 seconds.
    
    CPU usage can take up to 10 cycles to stabilize, up to ~20 seconds.


## Issues

* CPU percent activity may not work so well above ~80% on modern HW.  The algorthym for being busy is not that adaptive, so it can get to a point where it can no longer get busier.