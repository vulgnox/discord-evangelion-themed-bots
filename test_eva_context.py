import unittest

from eva_context import (
    build_chain_marker,
    build_user_prompt,
    can_respond_to_message,
    format_bot_reply,
    get_chain_depth,
    resolve_mentions,
    strip_chain_marker,
)


class FakeUser:
    def __init__(self, user_id, name, display_name=None, bot=False):
        self.id = user_id
        self.name = name
        self.display_name = display_name or name
        self.global_name = None
        self.bot = bot

    def mentioned_in(self, message):
        return f"<@{self.id}>" in message.content or f"<@!{self.id}>" in message.content


class FakeMessage:
    def __init__(self, content, author, mentions):
        self.content = content
        self.author = author
        self.mentions = mentions


class EvaContextTest(unittest.TestCase):
    def test_resolves_known_pilot_mentions(self):
        rei = FakeUser(1, "Rei Bot", "Rei")
        asuka = FakeUser(2, "Asuka Bot", "Asuka")
        handler = FakeUser(99, "nox")
        message = FakeMessage("<@1> what do you think of <@!2>?", handler, [rei, asuka])

        self.assertEqual(
            resolve_mentions(message),
            "@Rei Ayanami what do you think of @Asuka Langley Soryu?",
        )

    def test_unknown_mentions_fall_back_to_display_name(self):
        rei = FakeUser(1, "Rei Bot", "Rei")
        stranger = FakeUser(3, "random_user", "Unit Tech")
        handler = FakeUser(99, "nox")
        message = FakeMessage("<@1> check with <@3>", handler, [rei, stranger])

        self.assertEqual(resolve_mentions(message), "@Rei Ayanami check with @Unit Tech")

    def test_prompt_strips_chain_marker(self):
        rei = FakeUser(1, "Rei Bot", "Rei")
        asuka = FakeUser(2, "Asuka Bot", "Asuka", bot=True)
        message = FakeMessage(f"<@1> answer me{build_chain_marker(2)}", asuka, [rei])

        prompt = build_user_prompt(message)

        self.assertIn("@Rei Ayanami answer me", prompt)
        self.assertNotIn(build_chain_marker(2), prompt)

    def test_chain_guard_allows_short_chain_only(self):
        rei = FakeUser(1, "Rei Bot", "Rei")
        asuka = FakeUser(2, "Asuka Bot", "Asuka", bot=True)
        allowed = FakeMessage(f"<@1> reply{build_chain_marker(2)}", asuka, [rei])
        blocked = FakeMessage(f"<@1> reply{build_chain_marker(3)}", asuka, [rei])

        self.assertTrue(can_respond_to_message(allowed, rei))
        self.assertFalse(can_respond_to_message(blocked, rei))

    def test_format_bot_reply_increments_chain_depth(self):
        rei = FakeUser(1, "Rei Bot", "Rei")
        handler = FakeUser(99, "nox")
        message = FakeMessage("<@1> hello", handler, [rei])

        reply = format_bot_reply("hello. [eva-chain:9]", message)

        self.assertTrue(reply.startswith("hello."))
        self.assertNotIn("[eva-chain", reply)
        self.assertEqual(get_chain_depth(reply), 1)
        self.assertEqual(strip_chain_marker(reply), "hello.")

    def test_visible_chain_markers_still_parse(self):
        message_content = "legacy reply [eva-chain:2]"

        self.assertEqual(get_chain_depth(message_content), 2)
        self.assertEqual(strip_chain_marker(message_content), "legacy reply")


if __name__ == "__main__":
    unittest.main()
