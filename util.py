import multiprocessing as mp
from queue import Empty


def clear_pipe(pipe: mp.Queue, size=0):
    while pipe.qsize() > size:
        try:
            pipe.get_nowait()
        except Empty:
            pass
