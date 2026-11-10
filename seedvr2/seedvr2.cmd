@echo off
setlocal
set "PATH=C:\Program Files\Shotcut;%PATH%"
set "PYTHONUTF8=1"
"I:\Video Generation\ComfyUI_windows_portable\python_embeded\python.exe" -X utf8 "I:\Video Generation\ComfyUI_windows_portable\ComfyUI\custom_nodes\ComfyUI-SeedVR2_VideoUpscaler\inference_cli.py" %* --model_dir "I:\Video Generation\ComfyUI_windows_portable\ComfyUI\models\SEEDVR2" --dit_model seedvr2_ema_3b_fp16.safetensors --video_backend ffmpeg --dit_offload_device cpu --vae_offload_device cpu --vae_encode_tiled --vae_decode_tiled
