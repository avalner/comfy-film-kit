# SeedVR2 local installation
Installed 2026-11-03 for a trial on the next film. ComfyUI node package:
I:/Video Generation/ComfyUI_windows_portable/ComfyUI/custom_nodes/ComfyUI-SeedVR2_VideoUpscaler
Models: ComfyUI/models/SEEDVR2, 3B FP16 + FP16 VAE.

Launcher (UTF-8, Shotcut FFmpeg, CPU model offload, VAE tiling):
`I:/Video Generation/Tools/seedvr2/seedvr2.cmd INPUT.mp4 --output OUTPUT.mp4 --resolution 1536 --batch_size 5 --temporal_overlap 1 --chunk_size 65`
Resolution means SHORT side, so a 768x1344 portrait source becomes 1536x2688.
Use a new output path; preserve the native final. Do not upscale each guide clip.
SeedVR2 is an alternative to the Real-ESRGAN final delivery stage, not an extra pass after it.
The comfy-film finalize_delivery.py now uses upscale_seedvr2.py by default (SeedVR2 3B FP16, 2×).
Before trial delivery, preserve/remux original audio and verify H.264 yuv420p, AAC, fps, dimensions, frame count, full decode and faststart. The finished generative result requires user review.
Included ComfyUI workflow: custom_nodes/ComfyUI-SeedVR2_VideoUpscaler/example_workflows/SeedVR2_HD_video_upscale.json

Validation: 2026-11-03, package v2.5.24; all 4 ComfyUI nodes imported; both model SHA256 checks passed; bundled Eyes example 5 frames, 212x120 -> 424x240 completed successfully on RTX 4090, full decode passed. This is an installation smoke test, not a quality or full-resolution performance benchmark.
