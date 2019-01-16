from multiprocessing import Pool
from multiprocessing import cpu_count
import time
import signal
import os
import sys
import psutil
import argparse
import threading
import random
import string
import socket
import grpc
import busypy_pb2 as busypy_pb2
import busypy_pb2_grpc as busypy_pb2_grpc

# A BUSY loop python program
# Each processor starts a thread to get accurate CPU usage.

GRPC_SERVER_PORT = "50051"
GRPC_SERVER = "localhost"

lock = threading.Lock()
PSUTIL_CAPTURE_INTERVAL_SEC = 2
MEMORY_HOG_CHUNK_SIZE_MB = 100

BusyPySettings = {
    "update": True,  # when set client will update
    "cpu": 10,
    "mem": 5,
    "exit": False,
}

SLEEP_INC = 0.0001
SLEEP_INC_FAST_FACTOR = 0.8
SLEEP_INITIAL_VALUE = 0.4  # start from a low CPU usage and go higher
SLEEP_INITIAL_BINARY_SRC_COUNT = 20   # # cycles to try sleep *= SLEEP_INC_FAST_FACTOR

MEM_TOLERANCE_PERCENT = 2

current_cpu_usage = 0
update = False
running = True
force_exit = False
processes = 1


# gRPC stuff taken from https://alexandreesl.com/tag/grpc/, https://grpc.io/docs/tutorials/basic/python.html
class gRPCClient():

    GRPC_TIMEOUT = 2

    def __init__(self, pid):
        server_addr = '{}:{}'.format(GRPC_SERVER, GRPC_SERVER_PORT)
        channel = grpc.insecure_channel(server_addr)
        self.stub = busypy_pb2_grpc.BusyPyServiceStub(channel)

        # from https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
        ip = (([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")] or [
            [(s.connect(("8.8.8.8", 53)), s.getsockname()[0], s.close()) for s in
             [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) + ["no IP found"])[0]

        self.metadata = [('ip', ip), ('pid', str(pid))]

        print("Server: {}, metadata: {}".format(server_addr, self.metadata))

    def GetSettings(self, cpu, memory, running):
        client_exit = not running
        return self.stub.GetSettings(busypy_pb2.BusyPySettings(cpuLoadPercent=cpu,
                                                               memoryPercent=int(memory),
                                                               clientExit=client_exit,
                                                               update=False),  # update has no meaning for server
                                     metadata=self.metadata,
                                     timeout=self.GRPC_TIMEOUT)


def f(x):
    """ This is a worker function that is run one per processor.
    - starts a busy loop with a sleep to burn up processor usage
    - creates an array to gobble up memory
    - gets 'commands/settings' from a gRPC Server
    :param x: not used
    """
    global current_cpu_usage, update, running, force_exit, sleep

    pid = os.getpid()
    client = gRPCClient(pid)
    p = psutil.Process(pid)
    ip = socket.gethostbyname(socket.gethostname())
    MEMORY_HOG = []

    def set_memory():
        MEMORY_HOG.clear()
        while p.memory_percent() < BusyPySettings["mem"]:
            MEMORY_HOG.append("*" * 1024 * 1024 * MEMORY_HOG_CHUNK_SIZE_MB)

    set_memory()

    def cpu_usage(arg):
        """ This function runs on a thread spawned off the process, and therefore
        does not affect the busy loop.
        - this thread is blocked by
          - PSUTIL_CAPTURE_INTERVAL_SEC
          - talking to gRPC Server
        - prints out the current status of cpu/memory usage
        - tries to talk to the gRPC server to get new targets
        - sets the flag 'update' which triggers the main process to
          update its cpu(sleep)/mem usage in order to try and hit target
        :param arg: nothing right now
        """
        global current_cpu_usage, update, running, binary_src_count, sleep
        while (not BusyPySettings["exit"]) and not force_exit:
            cp = int(p.cpu_percent(interval=PSUTIL_CAPTURE_INTERVAL_SEC))  # blocking
            mp = int(p.memory_percent())
            with lock:
                current_cpu_usage = cp
                update = True

            print("IP: {}, PID:{:5d}, CPU: {:2d}/{:2d}%, Mem: {:2d}/{:2d}%, (Sleep: {:6.5f})".format(ip,
                                                                                                     pid,
                                                                                                     current_cpu_usage,
                                                                                                     BusyPySettings["cpu"],
                                                                                                     mp,
                                                                                                     BusyPySettings["mem"],
                                                                                                     sleep))

            try:
                newTargets = client.GetSettings(cp, mp, running)
                if newTargets.update:
                    if BusyPySettings["mem"] != newTargets.memoryPercent:
                        BusyPySettings["mem"] = newTargets.memoryPercent
                        set_memory()

                    BusyPySettings["cpu"] = newTargets.cpuLoadPercent
                    BusyPySettings["exit"] = newTargets.clientExit

                    binary_src_count = SLEEP_INITIAL_BINARY_SRC_COUNT
                    sleep = SLEEP_INITIAL_VALUE

                if BusyPySettings["exit"]:
                    print("Server instructed to exit...")
                    running = False
                    client.GetSettings(cp, mp, running)  # report in one last time

            except KeyboardInterrupt:
                BusyPySettings["exit"] = True

            except Exception as e:
                # see https://stackoverflow.com/questions/43869397/how-do-you-set-a-timeout-in-pythons-grpc-library

                if str(e.code()) == u'StatusCode.UNAVAILABLE':
                    # the server may not be present, allow silent fail
                    pass

                elif str(e.code()) == u'StatusCode.DEADLINE_EXCEEDED':
                    # the server may not be present, allow silent fail
                    pass

                else:
                    print(e)

            # because memory usage does not depend on a measurement timing window
            # like cpu usage does, update on every loop thru...
            # note that this memory usage adaptation could be running on multiple
            # cpus (processes) and thus "fighting" each other... but in testing
            # this error seemed minimal... TODO: allow only one process to do memory usage
            low_mem = BusyPySettings["mem"] - MEM_TOLERANCE_PERCENT
            hi_mem = BusyPySettings["mem"] + MEM_TOLERANCE_PERCENT
            if p.memory_percent() > hi_mem:
                MEMORY_HOG.pop()
            elif p.memory_percent() < low_mem:
                MEMORY_HOG.append("*" * 1024 * 1024 * MEMORY_HOG_CHUNK_SIZE_MB)

        print("cpu_usage thread exit")

    # fire off a thread in order to read cpu/mem usage.  This is done because in order to
    # get decent accuracy the cpu_percent() call needs 2 seconds to measure.
    t = threading.Thread(target=cpu_usage, args=(None,))
    t.start()

    # create some dummy things in order to make cpu/mem busy
    sortme = ''.join(random.choice(string.ascii_uppercase) for _ in range(100))

    # quick and dirty things to make CPU busy... hacked!
    reversed = False
    sleep = SLEEP_INITIAL_VALUE
    binary_src_count = SLEEP_INITIAL_BINARY_SRC_COUNT
    busy_iterations = 500
    busy_iterations_increase_done = False

    # main busy loop
    try:
        while running:
            for i in range(busy_iterations):
                sortme = sorted(sortme, reverse=reversed)
                (x+22) * (x+33) / (i + 1) * ord(sortme[i % 10])
                reversed = not reversed
            time.sleep(sleep)

            with lock:
                # check to see if we should update 'sleep' in order to hit target
                if update:
                    update = False

                    # initially use a binary like search to approach the desired usage
                    if binary_src_count > 0:
                        binary_src_count -= 1
                        if current_cpu_usage < BusyPySettings["cpu"]:
                            sleep = sleep * SLEEP_INC_FAST_FACTOR
                        else:
                            # cpu usage is now greater than target, stop binary search
                            binary_src_count = 0

                    # then finally use small increments to get to the usage
                    else:
                        if current_cpu_usage > BusyPySettings["cpu"]:
                            sleep += SLEEP_INC
                        else:
                            if sleep >= SLEEP_INC:
                                sleep -= SLEEP_INC

                    # finally, if we exhaust the range, increase pure iterations for extra usage
                    if sleep < SLEEP_INC:
                        sleep = SLEEP_INC
                        if not busy_iterations_increase_done:
                            busy_iterations *= 2
                            busy_iterations_increase_done = True

    except Exception as e:
        print(e)

    except KeyboardInterrupt:
        running = False  # exit the thread that was started

    BusyPySettings["exit"] = True
    force_exit = True
    print("busyloop exit")

    try:
        t.join()
    except:
        pass


def exit_gracefully(signum, frame):
    # from https://stackoverflow.com/questions/18114560/python-catch-ctrl-c-command-prompt-really-want-to-quit-y-n-resume-executi
    global running

    # restore the original signal handler as otherwise evil things will happen
    # in raw_input when CTRL+C is pressed, and our signal handler is not re-entrant
    signal.signal(signal.SIGINT, original_sigint)

    running = False
    time.sleep(PSUTIL_CAPTURE_INTERVAL_SEC)  # gives a chance for the thead to run and exit

    # restore the exit gracefully handler here
    signal.signal(signal.SIGINT, exit_gracefully)


if __name__ == '__main__':
    original_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, exit_gracefully)

    parser = argparse.ArgumentParser(description='BusyPy Container')

    parser.add_argument('--cpu', type=int, default=BusyPySettings["cpu"],
                        help='Percent usage of the CPU(s), default={}'.format(BusyPySettings["cpu"]))

    parser.add_argument('--mem', type=int, default=BusyPySettings["mem"],
                        help='Percent usage of the memory, default={}'.format(BusyPySettings["mem"]))

    parser.add_argument('--cpu-all', dest="cpu_all", action='store_true', default=False,
                        help='Use all CPUs, default only one CPU is used.')

    parser.add_argument('--cpus', dest="cpus", action='store', type=int, default=1,
                        help='Number CPUs to use, default only one CPU is used.')

    parser.add_argument('--server', dest="grpc_server", action='store', default=GRPC_SERVER,
                        help='gRPC server, default={}.'.format(GRPC_SERVER))

    parser.add_argument('--port', dest="grpc_port", action='store', default=GRPC_SERVER_PORT,
                        help='gRPC server port, default={}.'.format(GRPC_SERVER_PORT))

    args = parser.parse_args()

    # TODO: limit cpu usage to 5-90%

    if args.cpu_all:  processes = cpu_count()
    else: processes = args.cpus

    # docker stats reports the total (sum) of % user per CPU,
    # busypy takes the target percent and divides per # of cpus

    BusyPySettings["cpu"] = args.cpu / processes
    BusyPySettings["mem"] = args.mem / processes
    GRPC_SERVER = args.grpc_server
    GRPC_SERVER_PORT = args.grpc_port

    print("Press CTRL-C to abort (it may take a few seconds to exit)")
    print("Targetting {} CPU(s): {}%, MEM: {}, SLEEP_INC: {}".format(processes,
                                                                     BusyPySettings["cpu"],
                                                                     BusyPySettings["mem"],
                                                                     SLEEP_INC))

    # create the busy loop on processors
    pool = Pool(processes)
    try:
        pool.map(f, range(processes))
    except:
        pool.close()

    print("main exit")
    sys.exit(0)
