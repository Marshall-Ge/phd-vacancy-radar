from __future__ import annotations

import unittest
from unittest import mock

from phd_radar.config import Notify
from phd_radar.notify import Attachment, send_email


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=45, context=None):
        self.message = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, username, password):
        pass

    def send_message(self, message):
        self.message = message


class NotifyAttachmentTests(unittest.TestCase):
    def setUp(self):
        FakeSMTP.instances = []

    def test_attachment_added(self):
        cfg = Notify(
            provider="smtp", recipients=["a@example.com"], username="a@example.com",
            password="code", smtp_host="smtp.163.com", smtp_port=465, smtp_ssl=True,
        )
        with mock.patch("smtplib.SMTP_SSL", FakeSMTP):
            provider = send_email(
                cfg, "subject", "text", "<p>html</p>",
                attachments=[Attachment("list.csv", b"a,b\n", "text", "csv")],
            )
        self.assertEqual(provider, "smtp")
        message = FakeSMTP.instances[0].message
        attachments = list(message.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "list.csv")


if __name__ == "__main__":
    unittest.main()
