import argparse
import time
import grpc
import socket
import busypy_pb2 as busypy_pb2
import busypy_pb2_grpc as busypy_pb2_grpc
from concurrent import futures

# code based on https://alexandreesl.com/tag/grpc/

GRPC_SERVER_PORT = "50051"


# defaults that can be overridden from command line
BusyPySettings = {
    "update": True,  # when set client will update
    "cpu": 27,
    "mem": 7,
    "exit": False,
}


wait_for_num_clients = 0  # # of clients to wait for, after all seen, exit
run_server = True         # control infinite loop of server
target_client_ip = None   # set to affect only one client by ip address
monitor_only = False


def set_run_server(enable=True):
    global run_server
    run_server = enable


class clientIPs(object):
    """ Keeps track of clients via ip and pid
    """

    def __init__(self):
        self._clients = {}
        self._clients_updated = {}

    def add_ip(self, ip, pid):
        """ Add ip:pid only once
        :param ip:
        :param pid:
        :return: True if added, False if not added (already present)
        """
        if not ip in self._clients:
            self._clients[ip] = [pid]
            return True
        else:
            if not pid in self._clients[ip]:
                self._clients[ip].append(pid)
                return True

        return False

    def is_ip_active(self, ip):
        """ Checks if ip is active
        :param ip:
        :return:
        """
        return ip in self._clients

    def remove_ip_pid(self, ip, pid):
        """ Remove ip:pid
        :param ip:
        :param pid:
        :return: True ip:pid was removed, False otherwise
        """
        if not ip in self._clients: return False
        if not pid in self._clients[ip]: return False

        self._clients[ip].remove(pid)

        # if the list of pids is empty, delete the key
        if not self._clients[ip]:
            self._clients.pop(ip, None)
        return True

    def total(self):
        return len(self._clients)

    def targeted_client(self, ip, pid):
        """ Add ip:pid only once
        :param ip:
        :param pid:
        :return: True if added, False if not added (already present)
        """
        if not ip in self._clients_updated:
            self._clients_updated[ip] = [pid]
            return True
        else:
            if not pid in self._clients_updated[ip]:
                self._clients_updated[ip].append(pid)
                return True
        return False

    def is_targeted_updated(self, ip):
        if not ip in self._clients_updated: return False
        if not ip in self._clients: return False

        l1 = self._clients_updated[ip]
        l2 = self._clients[ip]
        return set(l1) == set(l2)


clients = clientIPs()


class gRPCServer(busypy_pb2_grpc.BusyPyServiceServicer):

    CLIENT_POLLING_TIME = 5

    def __init__(self):
        self._start = time.time()

    def __map_kv_dict(self, context):
        """ Map gRPC context invocation_metadata into a python dict
        :param context: gRPC context
        :return: dict of context.invocation_metadata()
        """
        #print(context.invocation_metadata())
        ctx = {}
        for item in context.invocation_metadata():
            #print(dir(item))
            #print(item.key, item.value)
            ctx[item.key] = item.value
        return ctx

    def GetSettings(self, request, context):
        """ Clients call this method to get their target settings.
        - when client calls, they also send their current state

        :param request: client current state, see BusyPySettings for structure
        :param context: gRPC context
        :return: gRPC handler
        """
        # print(dir(context))
        # [..., '_abc_cache', '_abc_negative_cache', '_abc_negative_cache_version', '_abc_registry', '_request_deserializer',
        # '_rpc_event', '_state', 'abort', 'add_callback', 'auth_context', 'cancel', 'disable_next_message_compression',
        # 'invocation_metadata', 'is_active', 'peer', 'peer_identities', 'peer_identity_key', 'send_initial_metadata',
        # 'set_code', 'set_details', 'set_trailing_metadata', 'time_remaining']

        ctx = self.__map_kv_dict(context)

        print("IP: {:12s}, PID:{:>7s}, CPU: {:3d}%, MEM: {:3d}%, Exit: {}".format(ctx['ip'], ctx['pid'],
                                                                              request.cpuLoadPercent,
                                                                              request.memoryPercent,
                                                                              request.clientExit))

        if target_client_ip is not None:
            BusyPySettings["update"] = False

        if monitor_only:
            BusyPySettings["update"] = False
            self._start = time.time()  # Never open window for other actions

        if clients.add_ip(ctx['ip'], ctx['pid']):
            # new client was added
            if wait_for_num_clients:
                print("{} of {} clients have checked in".format(clients.total(), wait_for_num_clients))
            else:
                print("{} clients have checked in".format(clients.total()))

            # every time we see a new client, reset the clock
            self._start = time.time()

        else:
            if (time.time() - self._start) > self.CLIENT_POLLING_TIME:
                #print("window open: wait_for_num_clients: {}, target_client_ip: {}, BusyPySettings: {}, client: {}:{}".format(wait_for_num_clients, target_client_ip, BusyPySettings, ctx['ip'], ctx['pid']))
                # if no new clients have been added during this polling window, then operations
                # can be done - we have seen all the clients by now

                if wait_for_num_clients and wait_for_num_clients == clients.total():
                    # this IMPLIES that all clients have received their new targets, so we can exit
                    print("Expected number ({}) of clients checked in, exiting server...".format(wait_for_num_clients))
                    set_run_server(False)

                if target_client_ip is not None and ctx['ip'] == target_client_ip:
                    if clients.targeted_client(ctx['ip'], ctx['pid']):
                        # first time we see the client, update it
                        BusyPySettings["update"] = True
                        print("target {}:{} -> {}".format(ctx['ip'], ctx['pid'], BusyPySettings))

                        # once client, all PIDs have been updated, we can exit
                        if clients.is_targeted_updated(ctx['ip']):
                            print("Targeted client updated, exiting server...")
                            set_run_server(False)

        return busypy_pb2.BusyPySettings(cpuLoadPercent=BusyPySettings["cpu"],
                                         memoryPercent=BusyPySettings["mem"],
                                         clientExit=BusyPySettings["exit"],
                                         update=BusyPySettings["update"])


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    busypy_pb2_grpc.add_BusyPyServiceServicer_to_server(gRPCServer(), server)
    server.add_insecure_port('[::]:{}'.format(GRPC_SERVER_PORT))
    server.start()
    try:
        while run_server:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopped by user")

    finally:
        server.stop(0)


if __name__ == '__main__':
    epilog = ("This server can be started and stopped anytime, clients will continue to"  
              "operate to their last known target settings.  Restart this Server with new"
              "parameters to affect change in the clients.")

    parser = argparse.ArgumentParser(description='BusyPyServer',
                                     epilog='')

    parser.add_argument('--cpu', type=int, default=BusyPySettings["cpu"],
                        help='Percent usage of the CPU(s), default={}'.format(BusyPySettings["cpu"]))

    parser.add_argument('--mem', type=int, default=BusyPySettings["mem"],
                        help='Percent usage of the memory, default={}'.format(BusyPySettings["mem"]))

    parser.add_argument('--grpc-port', dest="grpc_port", action='store', default=GRPC_SERVER_PORT,
                        help='gRPC server port, default={}.'.format(GRPC_SERVER_PORT))

    parser.add_argument('--wait-for', dest="wait_for", action='store', default=0,
                        help='Wait for # of clients to poll, then exit server, 0=run forever (default)')
                        # the idea here is that you want to update all the running clients
                        # with new parameters, presumably the number of clients expected is known,
                        # thus when that many clients are observes, they have all been updated, so quit.

    parser.add_argument('--client-exit', dest="client_exit", action='store_true', default=False,
                        help='Client busy app should exit.')

    parser.add_argument('--client-ip', dest="client_ip", action='store',
                        help='Target client ip address only')

    parser.add_argument('--monitor', dest="monitor", action='store_true',
                        help='Monitor clients only')

    args = parser.parse_args()

    BusyPySettings["cpu"] = args.cpu
    BusyPySettings["mem"] = args.mem
    BusyPySettings["exit"] = args.client_exit

    wait_for_num_clients = int(args.wait_for)
    target_client_ip = args.client_ip
    monitor_only = args.monitor

    # from https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
    ip = (([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")] or [
        [(s.connect(("8.8.8.8", 53)), s.getsockname()[0], s.close()) for s in
         [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) + ["no IP found"])[0]

    print("IP: {}, targets are CPU: {}, Memory: {}".format(ip, BusyPySettings["cpu"], BusyPySettings["mem"]))
    if wait_for_num_clients:
        print("init: waiting for {} clients to check in... will exit when they do.".format(wait_for_num_clients))
    serve()
