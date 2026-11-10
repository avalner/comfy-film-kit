# Real-ESRGAN (optional)

The delivery pipeline can finish a film with a cosmetic sharpening pass. For that it
calls `I:/Video Generation/Tools/realesrgan/realesrgan-ncnn-vulkan.exe` with
`realesr-animevideov3`, which is what `finalize_delivery.py --no-upscale` skips and what
the SeedVR2 route replaces entirely.

## Binaries are not committed

The ncnn release is ~100 MB of executables and model weights, so this repository keeps
only this note. To restore a working copy, download the Windows release from

<https://github.com/xinntao/Real-ESRGAN/releases>

and unpack it here so the folder looks like:

```
realesrgan/
  realesrgan-ncnn-vulkan.exe
  vcomp140.dll
  vcomp140d.dll
  models/
    realesr-animevideov3-x2.bin
    realesr-animevideov3-x2.param
    realesr-animevideov3-x3.bin
    realesr-animevideov3-x3.param
    realesr-animevideov3-x4.bin
    realesr-animevideov3-x4.param
    realesrgan-x4plus.bin
    realesrgan-x4plus.param
    realesrgan-x4plus-anime.bin
    realesrgan-x4plus-anime.param
```

`README_windows.md` in this folder is the upstream command reference.

## Which upscaler to use

| Route | Use it when |
|---|---|
| `--no-upscale` | Default. Delivery stays at native resolution. |
| SeedVR2 3B FP16, 2× | The default when upscaling is requested. Runs outside ComfyUI, keeps motion and grain, takes ~40 s per 480 frames. |
| Real-ESRGAN `animevideov3` | Cheap cosmetic sharpening when SeedVR2 is unavailable. Keeps clean 3D renders smooth. `x4plus` can crunch pollen and fine texture — check a 1:1 crop before accepting. |

Upscaling is not a substitute for shooting at native resolution: it cannot restore
detail the VAE never encoded, and the motion profile does not change.
