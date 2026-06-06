# test_torchrun.py
import torch
import torch.distributed as dist
import torch.multiprocessing as mp

def setup_process(rank, world_size):
    # Initialize process group
    dist.init_process_group(backend="gloo" if not torch.cuda.is_available() else "nccl",
                            init_method="env://",
                            world_size=world_size,
                            rank=rank)
    print(f"Process {rank} of {world_size} is working!")
    dist.destroy_process_group()


if __name__ == "__main__":
    world_size = 2  # Simulate 2 processes
    mp.spawn(setup_process, args=(world_size,), nprocs=world_size, join=True)
