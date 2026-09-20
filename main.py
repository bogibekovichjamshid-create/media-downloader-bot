import asyncio
import os
import sys
import io
import uuid

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

from aiogram import Bot, Dispatcher, F, types
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import FSInputFile, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, BOT_USERNAME, ADMIN_USERNAME

from downloader import (
    get_video_info, 
    download_by_quality, 
    download_cropped_video,
    download_muted_video,
    recognize_music,
    merge_audio_video,
    upscale_video,
    upscale_image,
    get_instagram_images,
    FFMPEG_PATH
)
from keyboards import build_quality_keyboard, build_crop_quality_keyboard

session = AiohttpSession(timeout=600.0)
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())
user_urls = {}
gallery_videos = {}

# Foydalanuvchilarning tillarini saqlash uchun lug'at (Kelajakda buni bazaga ulash mumkin)
user_langs = {}

# Tillar lug'ati
LANGS = {
    "uz": {
        "start": "Assalomu alaykum! Video yuklab olish uchun YouTube/Instagram havolasini yuboring yoki galereyadan rasm/video tashlang.",
        "services": "📁 Xizmatlar",
        "deposit": "💵 Hisob to'ldirish",
        "balance": "💰 Mening hisobim",
        "guide": "📖 Qo'llanma",
        "support": "☎️ Qo'llab-Quvvatlash",
        "settings": "⚙️ Sozlamalar",
        "choose_lang": "🇺🇿 Tilni tanlang:\n🇷🇺 Выберите язык:\n🇬🇧 Choose a language:",
        "lang_saved": "✅ O'zbek tili tanlandi!"
    },
    "ru": {
        "start": "Здравствуйте! Отправьте ссылку на YouTube/Instagram для скачивания или загрузите фото/видео из галереи.",
        "services": "📁 Услуги",
        "deposit": "💵 Пополнить счет",
        "balance": "💰 Мой баланс",
        "guide": "📖 Инструкция",
        "support": "☎️ Поддержка",
        "settings": "⚙️ Настройки",
        "choose_lang": "🇺🇿 Tilni tanlang:\n🇷🇺 Выберите язык:\n🇬🇧 Choose a language:",
        "lang_saved": "✅ Русский язык выбран!"
    },
    "en": {
        "start": "Hello! Send a YouTube/Instagram link to download or upload a photo/video from your gallery.",
        "services": "📁 Services",
        "deposit": "💵 Deposit",
        "balance": "💰 My Balance",
        "guide": "📖 Guide",
        "support": "☎️ Support",
        "settings": "⚙️ Settings",
        "choose_lang": "🇺🇿 Tilni tanlang:\n🇷🇺 Выберите язык:\n🇬🇧 Choose a language:",
        "lang_saved": "✅ English language selected!"
    }
}

class CropState(StatesGroup):
    waiting_for_quality = State()
    waiting_for_time = State()

class ServiceState(StatesGroup):
    waiting_for_audio = State()
    waiting_for_video = State()
    waiting_for_upscale_res = State()
    waiting_for_image = State()

def get_lang(user_id):
    return user_langs.get(user_id, "uz")

def get_main_menu(user_id):
    lang = get_lang(user_id)
    t = LANGS[lang]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t["services"])],
            [KeyboardButton(text=t["deposit"]), KeyboardButton(text=t["balance"])],
            [KeyboardButton(text=t["guide"]), KeyboardButton(text=t["support"])],
            [KeyboardButton(text=t["settings"])]
        ],
        resize_keyboard=True
    )

@dp.message(F.text == "/start")
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    lang = get_lang(message.from_user.id)
    await message.answer(LANGS[lang]["start"], reply_markup=get_main_menu(message.from_user.id))

# --- SOZLAMALAR VA TIL TANLASH ---
@dp.message(lambda msg: msg.text in [LANGS["uz"]["settings"], LANGS["ru"]["settings"], LANGS["en"]["settings"]])
async def menu_settings(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz")],
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")]
    ])
    lang = get_lang(message.from_user.id)
    await message.answer(LANGS[lang]["choose_lang"], reply_markup=kb)

@dp.callback_query(F.data.startswith("lang:"))
async def set_language(call: CallbackQuery):
    selected_lang = call.data.split(":")[1]
    user_langs[call.from_user.id] = selected_lang
    await call.message.delete()
    await call.message.answer(LANGS[selected_lang]["lang_saved"], reply_markup=get_main_menu(call.from_user.id))
    await call.answer()

# --- QOLGAN MENYULAR ---
@dp.message(lambda msg: msg.text in [LANGS["uz"]["services"], LANGS["ru"]["services"], LANGS["en"]["services"]])
async def menu_xizmatlar(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Rasm sifatini ko'tarish", callback_data="serv:upscale_img")],
        [InlineKeyboardButton(text="⚡️ Video sifatini ko'tarish (Upscale)", callback_data="serv:upscale_menu")],
        [InlineKeyboardButton(text="🎬 Videoga audio qo'shish", callback_data="serv:merge")],
        [InlineKeyboardButton(text="🔇 Videodan ovozni o'chirish", callback_data="serv:mute_info")]
    ])
    await message.answer("📁 <b>Xizmatlar bo'limi</b>\n\nQuyidagi xizmatlardan birini tanlang:", reply_markup=kb, parse_mode="HTML")

@dp.message(lambda msg: msg.text in [LANGS["uz"]["deposit"], LANGS["ru"]["deposit"], LANGS["en"]["deposit"]])
async def menu_hisob_toldirish(message: types.Message):
    await message.answer("💵 Hisobni to'ldirish tizimi tez orada ishga tushadi.")

@dp.message(lambda msg: msg.text in [LANGS["uz"]["balance"], LANGS["ru"]["balance"], LANGS["en"]["balance"]])
async def menu_mening_hisobim(message: types.Message):
    await message.answer("💰 <b>Hisobingiz:</b> 0 so'm / 0.0$ \nStatus: Bepul foydalanuvchi", parse_mode="HTML")

@dp.message(lambda msg: msg.text in [LANGS["uz"]["guide"], LANGS["ru"]["guide"], LANGS["en"]["guide"]])
async def menu_qollanma(message: types.Message):
    await message.answer("📖 <b>Qo'llanma:</b>\n\n1. YouTube/Instagram havolasini yuboring.\n2. Galereyadan rasm/video tashlab sifatini oshirishingiz mumkin.\n3. Xizmatlar orqali audio qo'shing.", parse_mode="HTML")

@dp.message(lambda msg: msg.text in [LANGS["uz"]["support"], LANGS["ru"]["support"], LANGS["en"]["support"]])
async def menu_qollab_quvvatlash(message: types.Message):
    await message.answer(f"☎️ Savollar uchun admin: {ADMIN_USERNAME}")


# --- XIZMATLAR CALLBACKLARI ---
@dp.callback_query(F.data == "serv:upscale_img")
async def callback_upscale_img(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🖼 <b>Rasm sifatini ko'tarish:</b>\n\nIltimos, sifatini oshirmoqchi bo'lgan <b>rasmni yuboring</b>.", parse_mode="HTML")
    await state.set_state(ServiceState.waiting_for_image)
    await call.answer()

@dp.callback_query(F.data == "serv:upscale_menu")
async def callback_upscale_menu(call: CallbackQuery, state: FSMContext):
    await call.message.answer("⚡️ <b>Video sifatini ko'tarish:</b>\n\nIltimos, galereyangizdan yoki fayl ko'rinishida <b>videoni yuboring</b>.", parse_mode="HTML")
    await state.set_state(ServiceState.waiting_for_upscale_res)
    await call.answer()

@dp.callback_query(F.data == "serv:merge")
async def callback_merge_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🎵 <b>1-qadam:</b> Iltimos, qo'shmoqchi bo'lgan <b>Audio (MP3) yoki Ovozli xabar (Voice)</b> yuboring.", parse_mode="HTML")
    await state.set_state(ServiceState.waiting_for_audio)
    await call.answer()

@dp.callback_query(F.data == "serv:mute_info")
async def callback_mute_info(call: CallbackQuery):
    await call.message.answer("🔇 Videodan ovozni o'chirish uchun YouTube/Instagram havolasini yuboring yoki galereyadan video tashlang.", parse_mode="HTML")
    await call.answer()

# --- FAYLLARNI QABUL QILISH ---
@dp.message(ServiceState.waiting_for_image, F.photo | F.document)
async def process_service_image(message: types.Message, state: FSMContext):
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id
    else:
        await message.answer("Iltimos, rasm formatidagi fayl yuboring.")
        return

    file = await bot.get_file(file_id)
    input_path = f"temp_img_{message.from_user.id}.jpg"
    await bot.download_file(file.file_path, destination=input_path)
    
    status_msg = await message.answer("⏳ Rasm sifati oshirilmoqda, biroz kuting...")
    res = await upscale_image(input_path)
    await state.clear()
    if os.path.exists(input_path): os.remove(input_path)
    
    if res["success"]:
        file_size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
        if file_size_mb > 49.5:
            await status_msg.edit_text("❌ Rasm sifati oshirildi, lekin hajmi 50 MB dan oshib ketdi.")
            if os.path.exists(res["file_path"]): os.remove(res["file_path"])
        else:
            await status_msg.edit_text("📤 Telegram'ga yuklanmoqda...")
            file_input = FSInputFile(res["file_path"])
            await message.answer_document(document=file_input, caption=f"✨ Tayyor! Rasm sifati oshirildi.\n\n👉 {BOT_USERNAME}")
            if os.path.exists(res["file_path"]): os.remove(res["file_path"])
    else:
        await status_msg.edit_text(f"❌ Xatolik: {res['error']}")

@dp.message(ServiceState.waiting_for_audio, F.audio | F.document | F.voice)
async def process_service_audio(message: types.Message, state: FSMContext):
    if message.audio:
        file_id = message.audio.file_id
    elif message.voice:
        file_id = message.voice.file_id
    else:
        file_id = message.document.file_id
        
    file = await bot.get_file(file_id)
    audio_path = f"temp_audio_{message.from_user.id}.mp3"
    await bot.download_file(file.file_path, destination=audio_path)
    await state.update_data(audio_path=audio_path)
    await message.answer("✅ Audio qabul qilindi!\n\n🎬 <b>2-qadam:</b> Endi o'sha audio qo'shilishi kerak bo'lgan <b>Video</b> faylini yuboring.", parse_mode="HTML")
    await state.set_state(ServiceState.waiting_for_video)

@dp.message(ServiceState.waiting_for_video, F.video | F.document)
async def process_service_video(message: types.Message, state: FSMContext):
    data = await state.get_data()
    audio_path = data.get("audio_path")
    document = message.video or message.document
    if document.file_size and document.file_size > 20 * 1024 * 1024:
        await message.answer("❌ Kichikroq hajmdagi videoni yuboring.")
        return

    file = await bot.get_file(document.file_id)
    video_path = f"temp_video_{message.from_user.id}.mp4"
    await bot.download_file(file.file_path, destination=video_path)
    status_msg = await message.answer("⏳ Audio va video birlashtirilmoqda, biroz kuting...")
    
    res = await merge_audio_video(video_path, audio_path)
    await state.clear()
    
    if os.path.exists(audio_path): os.remove(audio_path)
    if os.path.exists(video_path): os.remove(video_path)
    
    if res["success"]:
        file_size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
        if file_size_mb > 49.5:
            await status_msg.edit_text("❌ Natija hajmi 50 MB dan oshdi.")
            if os.path.exists(res["file_path"]): os.remove(res["file_path"])
        else:
            await status_msg.edit_text("📤 Telegram'ga yuklanmoqda...")
            file_input = FSInputFile(res["file_path"])
            await message.answer_video(video=file_input, caption=f"✨ Tayyor! \n\n👉 {BOT_USERNAME}")
            if os.path.exists(res["file_path"]): os.remove(res["file_path"])
    else:
        await status_msg.edit_text(f"❌ Xatolik: {res['error']}")


@dp.message(F.video | F.document)
async def handle_gallery_video(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        return
        
    if message.document and not message.document.mime_type.startswith("video/"):
        return

    document = message.video or message.document
    if document.file_size and document.file_size > 20 * 1024 * 1024:
        await message.answer("❌ Telegram orqali faqat kichik hajmdagi videolarni qayta ishlash mumkin (hozircha 20 MBgacha).")
        return

    file = await bot.get_file(document.file_id)
    video_path = f"gallery_video_{message.from_user.id}.mp4"
    await bot.download_file(file.file_path, destination=video_path)
    gallery_videos[message.from_user.id] = video_path

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 720p", callback_data="gal:720p"), InlineKeyboardButton(text="🔥 1080p", callback_data="gal:1080p")],
        [InlineKeyboardButton(text="⚡️ 2K", callback_data="gal:2K"), InlineKeyboardButton(text="💎 4K", callback_data="gal:4K")],
        [InlineKeyboardButton(text="🔇 Ovozni o'chirish", callback_data="gal:mute")]
    ])
    await message.answer("📥 <b>Video qabul qilindi! (Pullik xizmat)</b>\n\nQuyidagi amallardan birini tanlang:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("gal:"))
async def handle_gallery_actions(call: CallbackQuery):
    action = call.data.split(":")[1]
    user_id = call.from_user.id
    if user_id not in gallery_videos or not os.path.exists(gallery_videos[user_id]):
        await call.answer("❌ Video topilmadi yoki vaqti o'tdi.", show_alert=True)
        return

    video_path = gallery_videos[user_id]
    status = await call.message.answer("⏳ Video qayta ishlanmoqda, biroz kuting...")

    if action == "mute":
        output_file = f"muted_{uuid.uuid4().hex}.mp4"
        process = await asyncio.create_subprocess_exec(
            FFMPEG_PATH, '-i', video_path, '-an', '-c:v', 'copy', output_file,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        res = {"success": True, "file_path": output_file} if os.path.exists(output_file) else {"success": False, "error": "Xatolik"}
    else:
        res = await upscale_video(video_path, action)

    if res["success"]:
        file_size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
        if file_size_mb > 49.5:
            await status.edit_text("❌ Natija hajmi 50 MB dan oshdi.", parse_mode="HTML")
            if os.path.exists(res["file_path"]): os.remove(res["file_path"])
        else:
            await status.edit_text("📤 Telegram'ga yuklanmoqda...")
            file_input = FSInputFile(res["file_path"])
            await call.message.answer_video(video=file_input, caption=f"✨ Tayyor! \n\n👉 {BOT_USERNAME}")
            await status.delete()
            if os.path.exists(res["file_path"]): os.remove(res["file_path"])
    else:
        await status.edit_text(f"❌ Xatolik: {res['error']}")

@dp.message(F.text.startswith("http"))
async def handle_link(message: types.Message):
    url = message.text.strip()
    status_msg = await message.answer("🔍 Havola tekshirilmoqda...")
    
    if "instagram.com" in url:
        ig_res = await get_instagram_images(url)
        if ig_res.get("success") and ig_res.get("images"):
            media = []
            for i, img_url in enumerate(ig_res["images"]):
                if i == 0:
                    media.append(types.InputMediaPhoto(media=img_url, caption=f"📸 <b>Instagram post</b>\n\n👉 {BOT_USERNAME}", parse_mode="HTML"))
                else:
                    media.append(types.InputMediaPhoto(media=img_url))
            try:
                if len(media) == 1:
                    await message.answer_photo(photo=ig_res["images"][0], caption=f"📸 <b>Instagram rasm</b>\n\n👉 {BOT_USERNAME}", parse_mode="HTML")
                else:
                    await message.answer_media_group(media=media[:10]) 
                await status_msg.delete()
                return
            except Exception as e:
                pass 

    info = await get_video_info(url)
    if not info["success"]:
        await status_msg.edit_text(f"❌ Xatolik: {info['error']}")
        return

    user_urls[message.from_user.id] = info
    text = f"📹 <b>{info['title']}</b>\n\n"
    for q_name, q_data in info["qualities"].items():
        text += f"🚀 <b>{q_name}:</b> {q_data['size']}\n"
        
    text += "\n<b>Yuklab olish uchun formatni tanlang ↓</b>"
    kb = build_quality_keyboard(info["qualities"])
    
    await status_msg.delete()
    if info.get("thumbnail"):
        await message.answer_photo(photo=info["thumbnail"], caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text=text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("dl:"))
async def handle_download_callback(call: CallbackQuery, state: FSMContext):
    quality = call.data.split(":")[1]
    user_id = call.from_user.id
    if user_id not in user_urls:
        await call.answer("❌ Havola eskirgan. Qaytadan havola yuboring.", show_alert=True)
        return

    info = user_urls[user_id]
    caption_text = f"👉 {BOT_USERNAME}"

    if quality == "shazam":
        await call.answer("🔍 Qo'shiq qidirilmoqda...")
        status = await call.message.answer("🔎 Videodagi qo'shiq aniqlanmoqda, biroz kuting...")
        res = await recognize_music(info["url"])
        if res["success"]:
            text_cap = f"🎵 <b>Topilgan qo'shiq:</b>\n🎤 {res['subtitle']} - {res['title']}\n\n👉 {BOT_USERNAME}"
            file_size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
            if file_size_mb > 49.5:
                 await status.edit_text("❌ Musiqa hajmi 50 MB dan katta. Yuborib bo'lmaydi.")
            else:
                 file = FSInputFile(res["file_path"])
                 await call.message.answer_audio(audio=file, performer=res['subtitle'], title=res['title'], caption=text_cap, parse_mode="HTML")
                 await status.delete()
            if os.path.exists(res["file_path"]): os.remove(res["file_path"])
        else:
            await status.edit_text(f"❌ Xatolik: {res['error']}")
        return
    
    if quality == "mute":
        await call.answer("🔇 Video ovozsiz ishlanmoqda...")
        status = await call.message.answer("⏳ Videodan ovoz olib tashlanmoqda...")
        res = await download_muted_video(info["url"])
        if res["success"]:
             file_size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
             if file_size_mb > 49.5:
                  await status.edit_text("❌ Natijaviy fayl hajmi 50 MB dan oshib ketdi.")
             else:
                 await status.edit_text("📤 Telegram'ga yuklanmoqda...")
                 file = FSInputFile(res["file_path"])
                 await call.message.answer_video(video=file, caption=f"🔇 <b>{info['title']} (Ovozsiz)</b>\n\n👉 {BOT_USERNAME}", parse_mode="HTML")
                 await status.delete()
             if os.path.exists(res["file_path"]): os.remove(res["file_path"])
        else:
            await status.edit_text(f"❌ Xatolik: {res['error']}")
        return

    if quality == "crop_menu":
        kb = build_crop_quality_keyboard(info["qualities"])
        await call.message.answer("✂️ <b>Qirqib olish uchun video sifatini tanlang:</b>", reply_markup=kb, parse_mode="HTML")
        await call.answer()
        return

    if quality == "thumb":
        if info.get("thumbnail"):
            await call.message.answer_photo(photo=info["thumbnail"], caption=f"🖼 Video prevyusi\n\n👉 {BOT_USERNAME}")
        return

    await call.answer(f"Yuklanmoqda...")
    status = await call.message.answer(f"⏳ Video yuklab olinmoqda, kuting...")
    res = await download_by_quality(info["url"], quality)
    
    if res["success"]:
        file_size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
        if file_size_mb > 49.5:
            await status.edit_text("❌ <b>Xatolik:</b> Telegram botlar orqali 50 MB dan katta fayllarni yuborish ruxsat etilmagan. Iltimos, hajmi kichikroq sifatni tanlang.", parse_mode="HTML")
            if os.path.exists(res["file_path"]): os.remove(res["file_path"])
        else:
            await status.edit_text("📤 Telegram'ga yuklanmoqda...")
            file = FSInputFile(res["file_path"])
            if quality == "mp3":
                await call.message.answer_audio(audio=file, title=info['title'], caption=caption_text)
            else:
                await call.message.answer_video(video=file, caption=f"🎬 <b>{info['title']}</b>\n\n👉 {BOT_USERNAME}", parse_mode="HTML")
            await status.delete()
            if os.path.exists(res["file_path"]): os.remove(res["file_path"])
    else:
        await status.edit_text(f"❌ Xatolik: {res['error']}")

@dp.callback_query(F.data.startswith("crop_q:"))
async def process_crop_quality_selection(call: CallbackQuery, state: FSMContext):
    selected_quality = call.data.split(":")[1]
    user_id = call.from_user.id
    if user_id not in user_urls:
        await call.answer("❌ Havola eskirgan.", show_alert=True)
        return
    info = user_urls[user_id]
    await state.set_state(CropState.waiting_for_time)
    await state.update_data(url=info["url"], title=info["title"], quality=selected_quality)
    await call.message.answer(f"✂️ <b>{selected_quality}</b> sifati tanlandi.\n\nVaqt oralig'ini yuboring (Misol: <code>0:10 - 0:45</code>)", parse_mode="HTML")
    await call.answer()

@dp.message(CropState.waiting_for_time)
async def process_crop_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    url, title, quality = data.get("url"), data.get("title", "Video"), data.get("quality", "720p")
    time_text = message.text.strip()
    if "-" not in time_text:
        await message.answer("❌ Noto'g'ri format. Misol uchun: <code>0:10 - 0:45</code> shaklida yuboring.", parse_mode="HTML")
        return
    times = [t.strip() for t in time_text.split("-")]
    status = await message.answer(f"✂️ Video qirqib olinmoqda...")
    res = await download_cropped_video(url, times[0], times[1], quality)
    await state.clear()
    
    if res["success"]:
         file_size_mb = os.path.getsize(res["file_path"]) / (1024 * 1024)
         if file_size_mb > 49.5:
              await status.edit_text("❌ Qirqilgan video hajmi 50 MB dan katta bo'lib ketdi.")
         else:
             await status.edit_text("📤 Telegram'ga yuklanmoqda...")
             file = FSInputFile(res["file_path"])
             await message.answer_video(video=file, caption=f"✂️ <b>{title}</b>\n\n👉 {BOT_USERNAME}", parse_mode="HTML")
             await status.delete()
         if os.path.exists(res["file_path"]): os.remove(res["file_path"])
    else:
        await status.edit_text(f"❌ Xatolik: {res['error']}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("---------------------------------------")
    print("🚀 BOT ISHGA TUSHDI VA XABAR KUTMOQDA!")
    print("---------------------------------------")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot to'xtatildi.")
    except Exception as e:
        print(f"❌ Xatolik: {e}")