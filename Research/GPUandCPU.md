Research summary to optimize llama.cpp on Mac Studio (Apple Silicon) using both CPU and GPU, based on the latest best practices:

***

# Optimizing CPU and GPU Usage in llama.cpp on Mac Studio (Apple Silicon M3 Ultra)

## Summary

When running large models with llama.cpp on Apple Silicon, full GPU offloading is fast but often underutilizes the powerful CPU cores. Mac Studio’s unified memory architecture lets you run hybrid inference with both CPU and GPU, substantially improving throughput. The key is splitting work between CPU and GPU using partial layer offloading.

## Hybrid Layer Offloading

- Use the `--n-gpu-layers` (or `-ngl`) parameter to move only a portion of layers to the GPU, keeping the rest on CPU.
  - Example: `--n-gpu-layers 40`
- With partial offloading, both CPU and GPU process layers simultaneously via shared unified memory bandwidth, avoiding PCIe bottlenecks.[1][2]
- Optimal values:
  - Start with: `--n-gpu-layers 40`
  - Test at: `--n-gpu-layers 30`, `--n-gpu-layers 50`
  - Measure tokens/sec at each setting.

## CPU Thread Optimization

- Set CPU threads to match the count of performance cores (not efficiency cores).
  - Example: `--n-threads 24`
- Use `--n-threads-batch 24` if supported.
- Do not use all 32 cores. Efficiency cores can lower performance for matrix-heavy inference tasks.[2][3]

## Example llama.cpp Command

```bash
llama-cli -m your_model.gguf -ngl 40 -t 24 --n-threads-batch 24 --batch-size 2048
```
- `-ngl 40`: Offload 40 layers to GPU.
- `-t 24`: Use 24 CPU threads.
- `--n-threads-batch 24`: Batch processing threads (if supported).
- `--batch-size 2048`: Increases parallelism.

## Monitoring

- Use `Activity Monitor` or command line tools to observe CPU/GPU load and RAM usage.
- Memory pressure: Lower `-ngl` if RAM usage is excessive.
- Increase `-ngl` if GPU is not fully utilized.

## Advanced Tweaks

- For Metal, you can allocate more VRAM for GPU compute with:
  ```bash
  sudo sysctl iogpu.wired_limit_mb=70000
  ```
  - Useful for jobs needing higher GPU memory, but typically only necessary on low-RAM systems.[4]

## Why Hybrid Is Faster

- Apple Silicon’s unified memory allows CPU and GPU to work together at full bandwidth. Proper split avoids idle CPU cores and speeds up throughput beyond full GPU-only loads.[1][2][5]
- Run benchmarks to confirm: best settings depend on your model and system RAM.

***

**References:**
- [reddit.com - Optimal settings for Apple Silicon][2]
- [dev.to - llama.cpp CPU vs GPU, shared VRAM and Inference Speed][1]
- [learn.arm.com - Multi-threaded performance in llama.cpp][6]
- [reddit.com - VRAM allocation for Metal][4]
- [arxiv.org - Apple M-Series HPC Performance][5]

***

You can copy and refine this Markdown for direct use by an agent or in engineering documentation. All cited best practices are current as of November 2025.

Sources
[1] llama.cpp: CPU vs GPU, shared VRAM and Inference Speed https://dev.to/maximsaplin/llamacpp-cpu-vs-gpu-shared-vram-and-inference-speed-3jpl
[2] Optimal settings for apple silicon? : r/LocalLLaMA - Reddit https://www.reddit.com/r/LocalLLaMA/comments/162kf7f/optimal_settings_for_apple_silicon/
[3] llama.cpp CPU optimization : r/LocalLLaMA - Reddit https://www.reddit.com/r/LocalLLaMA/comments/190v426/llamacpp_cpu_optimization/
[4] M1/M2/M3: increase VRAM allocation with `sudo sysctl iogpu ... https://www.reddit.com/r/LocalLLaMA/comments/186phti/m1m2m3_increase_vram_allocation_with_sudo_sysctl/
[5] Evaluating the Apple Silicon M-Series SoCs for HPC Performance ... https://arxiv.org/html/2502.05317v1
[6] Examine multi-threaded performance patterns in llama.cpp https://learn.arm.com/learning-paths/servers-and-cloud-computing/llama_cpp_streamline/6_multithread_analyze/
[7] Screenshot-2025-11-07-at-2.43.19-PM.jpeg https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/images/43046750/d68cd8e6-0222-4c35-90f2-0bf4631309cd/Screenshot-2025-11-07-at-2.43.19-PM.jpeg
