import imageio_ffmpeg
import os
import asyncio
import yt_dlp
import aiohttp
import uuid
import re
import instaloader
import replicate
from dotenv import load_dotenv

load_dotenv()

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

BASE_YTDLP_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'ffmpeg_location': FFMPEG_PATH,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web']
        }
    }
}

async def get_instagram_images(url: str) -> dict:
    try:
        loop = asyncio.get_event_loop()
        def _fetch():
            L = instaloader.Instaloader(quiet=True)
            match = re.search(r'(?:p|reel|tv)/([^/?#&]+)', url)
            if not match:
                return []
            shortcode = match.group(1)
            try:
                post = instaloader.Post.from_shortcode(L.context, shortcode)
                images = []
                if post.typename == 'GraphSidecar':
                    for node in post.get_sidecar_nodes():
                        if not node.is_video:
                            images.append(node.display_url)
                elif post.typename == 'GraphImage':
                    images.append(post.url)
                return images
            except:
                return []

        images = await loop.run_in_executor(None, _fetch)
        if images:
            return {"success": True, "images": images}
        return {"success": False, "error": "Rasm topilmadi."}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def get_video_info(url: str) -> dict:
    ydl_opts = {**BASE_YTDLP_OPTS}
    loop = asyncio.get_event_loop()
    try:
        def _get_info():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await loop.run_in_executor(None, _get_info)
        qualities = {}
        
        extractor = info.get('extractor', '').lower()
        youtube_target_heights = {
            144: "144p", 240: "240p", 360: "360p", 480: "480p", 
            720: "720p", 1080: "1080p", 1440: "2K", 2160: "4K"
        }

        if 'formats' in info:
            for f in info['formats']:
                if f.get('vcodec') != 'none' and f.get('height'):
                    h = f.get('height')
                    w = f.get('width') or h
                    min_dim = min(h, w)
                    
                    if 'youtube' in extractor:
                        closest_match = None
                        for target in youtube_target_heights:
                            if abs(target - min_dim) <= 25:
                                closest_match = target
                                break
                        if not closest_match:
                            continue
                        q_name = youtube_target_heights[closest_match]
                    else:
                        if h <= 144: q_name = "144p"
                        elif h <= 240: q_name = "240p"
                        elif h <= 360: q_name = "360p"
                        elif h <= 480: q_name = "480p"
                        elif h <= 720: q_name = "720p"
                        elif h <= 1080: q_name = "1080p"
                        elif h <= 1440: q_name = "2K"
                        else: q_name = "4K"

                    filesize = f.get('filesize') or f.get('filesize_approx') or 0
                    format_url = f.get('url')

                    if q_name not in qualities or filesize > qualities[q_name].get('_raw_size', -1):
                        qualities[q_name] = {"format_id": f['format_id'], "_raw_size": filesize, "url": format_url}

        all_possible_qualities = ["144p", "240p", "360p", "480p", "720p", "1080p", "2K", "4K"]
        for q in all_possible_qualities:
            if q not in qualities:
                qualities[q] = {"format_id": "best", "_raw_size": 0, "url": ""}

        base_size = 5 * 1024 * 1024
        for q, data in qualities.items():
            if data["_raw_size"] > 0:
                base_size = data["_raw_size"]
                break

        multipliers = {
            "144p": 0.3, "240p": 0.5, "360p": 0.8, "480p": 1.2, 
            "720p": 2.0, "1080p": 4.5, "2K": 8.0, "4K": 15.0
        }

        async with aiohttp.ClientSession() as session:
            for q_name, q_data in qualities.items():
                size_raw = q_data.get('_raw_size', 0)
                if not size_raw and q_data.get('url'):
                    try:
                        async with session.head(q_data['url'], timeout=3) as resp:
                            cl = resp.headers.get('Content-Length')
                            if cl:
                                size_raw = int(cl)
                    except:
                        pass
                
                if not size_raw:
                    mult = multipliers.get(q_name, 1.0)
                    size_raw = int(base_size * mult)

                qualities[q_name]['size'] = f"{round(size_raw / (1024 * 1024), 1)} MB"

        def sort_key(item):
            q = item[0]
            if q == "144p": return 144
            if q == "240p": return 240
            if q == "360p": return 360
            if q == "480p": return 480
            if q == "720p": return 720
            if q == "1080p": return 1080
            if q == "2K": return 1440
            if q == "4K": return 2160
            return 0
            
        qualities = dict(sorted(qualities.items(), key=sort_key))

        return {
            "success": True,
            "title": info.get('title', 'Media Video'),
            "thumbnail": info.get('thumbnail'),
            "url": url,
            "qualities": qualities
        }
    except Exception as e:
        return {"success": False, "error": "Havolani o'qib bo'lmadi."}

async def download_by_quality(url: str, quality: str) -> dict:
    file_id = uuid.uuid4().hex
    
    if quality == "mp3":
        filename = f"audio_{file_id}.mp3"
        ydl_opts = {
            **BASE_YTDLP_OPTS,
            'format': 'bestaudio/best',
            'outtmpl': f"audio_{file_id}.%(ext)s",
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    else:
        filename = f"video_{file_id}.mp4"
        height = quality.replace("p", "") if quality.endswith("p") else None
        if quality == "2K": height = "1440"
        elif quality == "4K": height = "2160"
            
        fmt = f"bv*[height<={height}]+ba/b" if height else "bv*+ba/b"
        ydl_opts = {
            **BASE_YTDLP_OPTS,
            'format': fmt,
            'merge_output_format': 'mp4',
            'outtmpl': filename,
        }

    loop = asyncio.get_event_loop()
    try:
        def _download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        await loop.run_in_executor(None, _download)
        if os.path.exists(filename):
            return {"success": True, "file_path": filename}
        return {"success": False, "error": "Faylni yuklab bo'lmadi."}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def download_muted_video(url: str) -> dict:
    return await download_by_quality(url, "720p")

async def download_cropped_video(url: str, start_time: str, end_time: str, quality: str = "720p") -> dict:
    res = await download_by_quality(url, quality)
    if not res["success"]:
        return res
    
    input_file = res["file_path"]
    output_file = f"cropped_{uuid.uuid4().hex}.mp4"
    
    try:
        process = await asyncio.create_subprocess_exec(
            FFMPEG_PATH,
            '-i', input_file,
            '-ss', start_time,
            '-to', end_time,
            '-c', 'copy',
            output_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if os.path.exists(input_file):
            os.remove(input_file)
            
        if os.path.exists(output_file):
            return {"success": True, "file_path": output_file}
        return {"success": False, "error": "Videoni qirqib bo'lmadi."}
    except Exception as e:
        if os.path.exists(input_file):
            os.remove(input_file)
        return {"success": False, "error": str(e)}

async def merge_audio_video(video_path: str, audio_path: str) -> dict:
    output_file = f"merged_{uuid.uuid4().hex}.mp4"
    try:
        process = await asyncio.create_subprocess_exec(
            FFMPEG_PATH,
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            output_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if os.path.exists(output_file):
            return {"success": True, "file_path": output_file}
        return {"success": False, "error": "Audio va videoni birlashtirib bo'lmadi."}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def upscale_video(input_path: str, target_resolution: str) -> dict:
    output_file = f"upscaled_{uuid.uuid4().hex}.mp4"
    resolutions = {
        "720p": (1280, 720),
        "1080p": (1920, 1080),
        "2K": (2560, 1440),
        "4K": (3840, 2160)
    }
    target_w, target_h = resolutions.get(target_resolution, (1920, 1080))
    scale_filter = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2"
    )
    
    try:
        process = await asyncio.create_subprocess_exec(
            FFMPEG_PATH,
            '-i', input_path,
            '-vf', scale_filter,
            '-c:v', 'libx264',
            '-crf', '20',
            '-c:a', 'copy',
            output_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        if os.path.exists(output_file):
            return {"success": True, "file_path": output_file}
        return {"success": False, "error": "Videoning sifatini ko'tarib bo'lmadi."}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def upscale_image(input_path: str) -> dict:
    output_file = f"upscaled_img_{uuid.uuid4().hex}.jpg"
    try:
        if not os.getenv("REPLICATE_API_TOKEN"):
            return {"success": False, "error": "Bot sozlamalarida AI kaliti (REPLICATE_API_TOKEN) ulanmagan."}

        loop = asyncio.get_event_loop()
        
        def run_replicate():
            with open(input_path, "rb") as img:
                output = replicate.run(
                    "nightmareai/real-esrgan:42fed1c4974146d4d2414e2be2c5277c7fcf05fcc3a73abf41610695738c1d7b",
                    input={"image": img, "scale": 2, "face_enhance": True}
                )
            return output
            
        output_url = await loop.run_in_executor(None, run_replicate)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(output_url) as resp:
                if resp.status == 200:
                    with open(output_file, 'wb') as f:
                        f.write(await resp.read())
                    return {"success": True, "file_path": output_file}
        return {"success": False, "error": "AI xizmatidan javob olishda xatolik yuz berdi."}
    except Exception as e:
        return {"success": False, "error": str(e)}
