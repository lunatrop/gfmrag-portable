// save as kernel.cu
#include <stdio.h>

__global__ void hello() {
    printf("Hello from GPU! Block %d, Thread %d\n", blockIdx.x, threadIdx.x);
}

int main() {
    printf("Launching kernel...\n");
    hello<<<2, 2>>>();
    cudaError_t err = cudaGetLastError();
    if (err != cudaSuccess) {
        printf("CUDA error: %s\n", cudaGetErrorString(err));
    }
    cudaDeviceSynchronize();
    return 0;
}
