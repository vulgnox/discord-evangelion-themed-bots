import asyncio

from eva_context import build_user_prompt, format_bot_reply


async def reply_with_model(message, bot_user, client, model, system_prompt, fallback_message):
    try:
        async with message.channel.typing():
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": build_user_prompt(message, bot_user=bot_user)},
                ],
            )

        reply = response.choices[0].message.content
        await message.channel.send(format_bot_reply(reply, message, bot_user=bot_user))
    except Exception as e:
        print(f"Error calling NVIDIA API: {e}")
        await message.channel.send(fallback_message)
