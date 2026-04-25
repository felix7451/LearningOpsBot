import asyncio
import dotenv
import httpx
import os
import config
import logging

logging.basicConfig(level=logging.INFO)
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

dotenv.load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if BOT_TOKEN is None:
    raise ValueError("BOT_TOKEN environment variable is not set.")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class QuizStates(StatesGroup):
    choosing_topic = State()
    waiting_for_answer = State()
    
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

async def model_response(topic, user_answer):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": config.TOPICS[topic]["system_prompt"]},
            {"role": "user", "content": user_answer}
        ]
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions", 
                json=data, 
                headers=headers
            )
            response.raise_for_status()
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except httpx.HTTPStatusError as e:
            return f"Ошибка API: {e.response.status_code}"
        except Exception as e:
            return f"Произошла ошибка: {str(e)}"
        
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(
        text="Start Quiz", 
        callback_data="choose_topic")
    )
    await message.answer(
        "HI! This is a test startup message.",
        reply_markup=builder.as_markup()
    )
    
@dp.callback_query(F.data == "choose_topic")
async def show_topics(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    
    for topic_key, topic_data in config.TOPICS.items():
        builder.row(types.InlineKeyboardButton(
            text=topic_data["name"],
            callback_data=f"select_topic:{topic_key}")
        )
    
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Select a topic:",
            reply_markup=builder.as_markup()
        )
        
@dp.callback_query(F.data.startswith("select_topic:"))
async def topic_selected(callback: types.CallbackQuery, state: FSMContext):
    if not callback.data:
        await callback.answer("Error: unable to determine topic.", show_alert=True)
        return
    topic = callback.data.split(":")[1]

    await state.update_data(chosen_topic=topic)

    await state.set_state(QuizStates.waiting_for_answer)

    if callback.message is not None:
        await callback.message.answer(f"Excellent! Starting quiz on topic {topic}. Generating first question...")

        first_question = await model_response(topic, "Hello! Give me the first question for knowledge checking.")

        await callback.message.answer(first_question)
    await callback.answer()

@dp.message(QuizStates.waiting_for_answer)
async def handle_answer(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    topic = user_data.get("chosen_topic")
    
    await message.answer("🔄 Checking your answer...")
    ai_feedback = await model_response(topic, message.text)
    
    await message.answer(ai_feedback)

import logging

async def main():
    logging.basicConfig(level=logging.INFO)
    
    await bot.delete_webhook(drop_pending_updates=True)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())