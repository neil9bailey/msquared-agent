from email.mime.text import MIMEText

from msquared_agent.email_adapter import _connect_imap, _send_smtp_message


def test_smtp_starttls_alt_uses_plain_smtp_then_starttls(monkeypatch):
    events = []

    class FakeSMTP:
        def __init__(self, server, port, timeout):
            events.append(("connect", server, port, timeout))

        def __enter__(self):
            events.append(("enter",))
            return self

        def __exit__(self, exc_type, exc, traceback):
            events.append(("exit",))

        def ehlo(self):
            events.append(("ehlo",))

        def starttls(self):
            events.append(("starttls",))

        def login(self, email_address, password):
            events.append(("login", email_address, password))

        def send_message(self, message):
            events.append(("send", message["To"]))

    def fail_ssl(*args, **kwargs):
        raise AssertionError("STARTTLS should not use SMTP_SSL")

    monkeypatch.setattr("msquared_agent.email_adapter.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("msquared_agent.email_adapter.smtplib.SMTP_SSL", fail_ssl)

    message = MIMEText("Hello")
    message["To"] = "lead@example.com"
    _send_smtp_message("smtp.porkbun.com", 50587, "STARTTLS Alt.", "msquared@example.com", "mail-secret", message)

    assert events == [
        ("connect", "smtp.porkbun.com", 50587, 30),
        ("enter",),
        ("ehlo",),
        ("starttls",),
        ("ehlo",),
        ("login", "msquared@example.com", "mail-secret"),
        ("send", "lead@example.com"),
        ("exit",),
    ]


def test_smtp_implicit_tls_uses_ssl_connector(monkeypatch):
    events = []

    class FakeSMTPSSL:
        def __init__(self, server, port, timeout):
            events.append(("connect_ssl", server, port, timeout))

        def __enter__(self):
            events.append(("enter",))
            return self

        def __exit__(self, exc_type, exc, traceback):
            events.append(("exit",))

        def login(self, email_address, password):
            events.append(("login", email_address, password))

        def send_message(self, message):
            events.append(("send", message["To"]))

    def fail_plain(*args, **kwargs):
        raise AssertionError("Implicit TLS should not use plain SMTP")

    monkeypatch.setattr("msquared_agent.email_adapter.smtplib.SMTP", fail_plain)
    monkeypatch.setattr("msquared_agent.email_adapter.smtplib.SMTP_SSL", FakeSMTPSSL)

    message = MIMEText("Hello")
    message["To"] = "lead@example.com"
    _send_smtp_message("smtp.porkbun.com", 465, "Implicit TLS", "msquared@example.com", "mail-secret", message)

    assert events == [
        ("connect_ssl", "smtp.porkbun.com", 465, 30),
        ("enter",),
        ("login", "msquared@example.com", "mail-secret"),
        ("send", "lead@example.com"),
        ("exit",),
    ]


def test_imap_ssl_label_uses_ssl_connector(monkeypatch):
    events = []

    class FakeIMAPSSL:
        def __init__(self, server, port):
            events.append(("connect_ssl", server, port))

    def fail_plain(*args, **kwargs):
        raise AssertionError("SSL/TLS should not use plain IMAP")

    monkeypatch.setattr("msquared_agent.email_adapter.imaplib.IMAP4", fail_plain)
    monkeypatch.setattr("msquared_agent.email_adapter.imaplib.IMAP4_SSL", FakeIMAPSSL)

    _connect_imap("imap.porkbun.com", 993, "SSL (SSL/TLS)")

    assert events == [("connect_ssl", "imap.porkbun.com", 993)]
